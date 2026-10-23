"""Retain only direct, digest-bound current receipt logs for CI upload.

This supplements the original staging index. It never edits that index, a
receipt, an original log, test expectations, or the publication privacy scanner.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys

MiB = 1024 * 1024
INDEX = 'artifacts/ci-evidence/current-run-index.json'
DESTINATION = 'artifacts/ci-evidence'
APPENDIX = 'receipt-bound-unit-logs.json'
SHA256 = re.compile(r'^[0-9a-f]{64}$')


class RetentionError(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    log_bytes: int = 8 * MiB
    total_log_bytes: int = 64 * MiB
    index_bytes: int = 8 * MiB
    receipt_bytes: int = 8 * MiB
    total_receipt_bytes: int = 64 * MiB
    receipt_count: int = 4096

    def __post_init__(self):
        for name, maximum in [('log_bytes', 8 * MiB), ('total_log_bytes', 64 * MiB),
                              ('index_bytes', 8 * MiB), ('receipt_bytes', 8 * MiB),
                              ('total_receipt_bytes', 64 * MiB), ('receipt_count', 4096)]:
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= maximum:
                raise ValueError('Retention budgets must be positive and cannot exceed fixed limits')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def relative_name(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise RetentionError('unsafe-relative-path')
    if any(ord(c) < 32 for c in value):
        raise RetentionError('unsafe-relative-path')
    parts = value.split('/')
    if any(part in ('', '.', '..') for part in parts) or PurePosixPath(value).is_absolute():
        raise RetentionError('unsafe-relative-path')
    return PurePosixPath(value)


def safe_path(root, name):
    relative = relative_name(name)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or getattr(current, 'is_junction', lambda: False)():
            raise RetentionError('symlink-or-junction-refused')
    try:
        current.resolve(strict=False).relative_to(root)
    except (ValueError, OSError):
        raise RetentionError('path-outside-root') from None
    return current


def read_regular(root, name, maximum, label):
    path = safe_path(root, name)
    try:
        before = path.stat()
        if not stat.S_ISREG(before.st_mode):
            raise RetentionError(label + '-not-regular')
        if before.st_size > maximum:
            raise RetentionError(label + '-byte-budget')
        with path.open('rb') as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                raise RetentionError(label + '-identity-changed')
            raw = stream.read(maximum + 1)
            after_open = os.fstat(stream.fileno())
        safe_path(root, name)
        after = path.stat()
        if len(raw) > maximum:
            raise RetentionError(label + '-byte-budget')
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        if identity(before) != identity(after_open) or identity(before) != identity(after) or len(raw) != before.st_size:
            raise RetentionError(label + '-changed-during-read')
        return raw
    except FileNotFoundError:
        raise RetentionError(label + '-missing') from None


def json_object(raw, label):
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise RetentionError(label + '-duplicate-json-key')
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError):
        raise RetentionError(label + '-invalid-json') from None
    if not isinstance(value, dict):
        raise RetentionError(label + '-not-object')
    return value


def known_error(error):
    return str(error) if isinstance(error, RetentionError) else 'filesystem-' + type(error).__name__


def retain_receipt_logs(root, *, limits=Limits(), expected_run_id=None, expected_run_attempt=None):
    root = Path(root).resolve(strict=True)
    destination = safe_path(root, DESTINATION)
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = safe_path(root, DESTINATION + '/' + APPENDIX)
    if manifest_path.exists():
        raise RetentionError('retention-appendix-already-exists')
    result = {'schema': 1, 'kind': 'current-receipt-bound-unit-log-retention',
              'passed': False, 'scope': 'Log retention only; does not change unit results or prove performance.',
              'originalIndexModified': False, 'originalReceiptsModified': False, 'originalLogsModified': False,
              'limits': {'perLogBytes': limits.log_bytes, 'totalLogReadBytes': limits.total_log_bytes,
                         'indexBytes': limits.index_bytes, 'perReceiptBytes': limits.receipt_bytes,
                         'totalReceiptBytes': limits.total_receipt_bytes, 'receiptCount': limits.receipt_count},
              'sourceIndex': None, 'selectedReceipts': 0, 'receiptsWithoutDirectLog': 0,
              'logBytesRead': 0, 'retainedLogBytes': 0, 'logs': [], 'errors': []}
    try:
        raw_index = read_regular(root, INDEX, limits.index_bytes, 'index')
        index = json_object(raw_index, 'index')
        result['sourceIndex'] = {'file': INDEX, 'bytes': len(raw_index), 'sha256': digest(raw_index),
                                 'sourceCommit': index.get('sourceCommit'), 'runId': index.get('runId'),
                                 'runAttempt': index.get('runAttempt')}
        if expected_run_id is not None and index.get('runId') != str(expected_run_id):
            raise RetentionError('index-run-id-mismatch')
        if expected_run_attempt is not None and index.get('runAttempt') != str(expected_run_attempt):
            raise RetentionError('index-run-attempt-mismatch')
        rows = index.get('files')
        if not isinstance(rows, list):
            raise RetentionError('index-files-not-array')
        seen = set()
        candidates = []
        for row in rows:
            if not isinstance(row, dict):
                raise RetentionError('invalid-index-entry')
            name = relative_name(row.get('file')).as_posix()
            if name in seen:
                raise RetentionError('duplicate-index-file')
            seen.add(name)
            if name.startswith('verification/') and PurePosixPath(name).name == 'receipt.json':
                candidates.append((name, row))
        if len(candidates) > limits.receipt_count:
            raise RetentionError('receipt-count-budget')
        receipt_bytes = 0
        for name, row in candidates:
            result['selectedReceipts'] += 1
            item = {'receipt': name, 'retained': False}
            try:
                size, expected_sha = row.get('bytes'), row.get('sha256')
                if type(size) is not int or size < 0 or not isinstance(expected_sha, str) or not SHA256.fullmatch(expected_sha):
                    raise RetentionError('invalid-index-receipt-binding')
                if size > limits.receipt_bytes or receipt_bytes + size > limits.total_receipt_bytes:
                    raise RetentionError('receipt-byte-budget')
                receipt_bytes += size
                staged = read_regular(root, DESTINATION + '/' + name, limits.receipt_bytes, 'staged-receipt')
                if len(staged) != size or digest(staged) != expected_sha:
                    raise RetentionError('staged-receipt-index-mismatch')
                original = read_regular(root, name, limits.receipt_bytes, 'original-receipt')
                if original != staged:
                    raise RetentionError('original-receipt-differs-from-staging')
                receipt = json_object(staged, 'receipt')
                item['receiptSha256'] = expected_sha
                if 'log' not in receipt:
                    result['receiptsWithoutDirectLog'] += 1
                    continue
                reference = receipt['log']
                if not isinstance(reference, dict) or not isinstance(reference.get('sha256'), str) or not SHA256.fullmatch(reference['sha256']):
                    raise RetentionError('invalid-direct-log-binding')
                leaf = relative_name(reference.get('file'))
                if len(leaf.parts) != 1:
                    raise RetentionError('log-must-be-in-receipt-directory')
                source_name = (PurePosixPath(name).parent / leaf).as_posix()
                if not source_name.startswith('verification/'):
                    raise RetentionError('log-outside-verification')
                item.update({'source': source_name, 'sha256': reference['sha256']})
                source = safe_path(root, source_name)
                try:
                    source_size = source.stat().st_size
                except FileNotFoundError:
                    raise RetentionError('source-log-missing') from None
                item['sourceBytes'] = source_size
                if source_size > limits.log_bytes:
                    raise RetentionError('source-log-byte-budget')
                if result['logBytesRead'] + source_size > limits.total_log_bytes:
                    raise RetentionError('total-log-byte-budget')
                raw = read_regular(root, source_name, limits.log_bytes, 'source-log')
                result['logBytesRead'] += len(raw)
                if digest(raw) != reference['sha256']:
                    raise RetentionError('source-log-sha256-mismatch')
                target_name = DESTINATION + '/' + source_name
                target = safe_path(root, target_name)
                if target.exists():
                    if read_regular(root, target_name, limits.log_bytes, 'existing-staged-log') != raw:
                        raise RetentionError('existing-staged-log-differs')
                    item['status'] = 'already-present-verified'
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open('xb') as stream:
                        view = memoryview(raw)
                        while view:
                            count = stream.write(view)
                            if type(count) is not int or not 0 < count <= len(view):
                                raise RetentionError('staged-log-short-write')
                            view = view[count:]
                        stream.flush()
                    if read_regular(root, target_name, limits.log_bytes, 'copied-staged-log') != raw:
                        raise RetentionError('staged-log-verification-failed')
                    item['status'] = 'copied-exact-original'
                item['retained'] = True
                item['retainedBytes'] = len(raw)
                result['retainedLogBytes'] += len(raw)
            except (RetentionError, OSError) as error:
                item['error'] = known_error(error)
            result['logs'].append(item)
        result['passed'] = not result['errors'] and all(item['retained'] for item in result['logs'])
    except (RetentionError, OSError) as error:
        result['errors'].append(known_error(error))
    with manifest_path.open('xb') as stream:
        stream.write((json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode('utf8'))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        print(json.dumps({'passed': False, 'error': 'CI-only-controller'}))
        return 2
    try:
        if not os.environ.get('GITHUB_RUN_ID') or not os.environ.get('GITHUB_RUN_ATTEMPT'):
            raise RetentionError('missing-current-ci-run-context')
        result = retain_receipt_logs(args.root, expected_run_id=os.environ['GITHUB_RUN_ID'],
                                     expected_run_attempt=os.environ['GITHUB_RUN_ATTEMPT'])
        print(json.dumps({'passed': result['passed'], 'appendix': DESTINATION + '/' + APPENDIX,
                          'logs': len(result['logs']), 'retainedLogBytes': result['retainedLogBytes'],
                          'errors': result['errors']}))
        return 0 if result['passed'] else 1
    except (RetentionError, OSError) as error:
        print(json.dumps({'passed': False, 'error': known_error(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
