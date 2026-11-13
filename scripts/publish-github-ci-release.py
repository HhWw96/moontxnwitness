"""Prepare exact PUSH-CI release assets; publish only with explicit --publish.

Never imports or executes artifact content. The network client is injectable.
The existing published-downloads workflow remains a separate post-publication
registry/public-consumer verification step.
"""
from __future__ import annotations
import argparse
import datetime as dt
import gzip
import hashlib
import http.client
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPOSITORY = 'HhWw96/moontxnwitness'
WORKFLOW = '.github/workflows/ci.yml'
ARTIFACT = 'evidence-ubuntu-24.04'
MAX_ARCHIVE = 1024 ** 3
MAX_EXPANDED = 4 * 1024 ** 3
MAX_MEMBER = 512 * 1024 ** 2
SHA = re.compile(r'[0-9a-f]{64}\Z')
COMMIT = re.compile(r'[0-9a-f]{40}\Z')
VERSION = re.compile(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z')
# Mirrors distribution_manifest.py's explicit inventory exclusions. Frozen
# cache omissions additionally require the commit-bound data index below.
SOURCE_EXCLUDED_DIRS = {'.git', '_build', '.mooncakes', 'node_modules', 'artifacts', 'dist', '__pycache__', '.venv-pg'}
SOURCE_EXCLUDED_NAMES = {'.local-toolchain.json', '.DS_Store'}
UNIT_LOG_APPENDIX = 'receipt-bound-unit-logs.json'
UNIT_LOG_LIMITS = {'perLogBytes': 8 * 1024 ** 2, 'totalLogReadBytes': 64 * 1024 ** 2,
                   'indexBytes': 8 * 1024 ** 2, 'perReceiptBytes': 8 * 1024 ** 2,
                   'totalReceiptBytes': 64 * 1024 ** 2, 'receiptCount': 4096}


class ReleaseError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ReleaseError(message)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def file_digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def strict_json(raw, maximum=32 * 1024 ** 2):
    require(isinstance(raw, bytes) and len(raw) <= maximum, 'JSON size boundary exceeded')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate decoded JSON key: ' + key)
            result[key] = value
        return result
    try:
        return json.loads(raw.decode('utf8'), object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ReleaseError('Nonfinite JSON')))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ReleaseError('Invalid UTF-8 JSON') from error


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as output:
        output.write(value if isinstance(value, bytes) else (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def safe_name(name, directory=False):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name,
            'Unsafe ZIP/member path')
    require(not any(ord(c) < 32 or ord(c) == 127 for c in name), 'Control character in member path')
    clean = name[:-1] if directory and name.endswith('/') else name
    path = PurePosixPath(clean)
    require(not path.is_absolute() and all(part not in ('', '.', '..') for part in clean.split('/'))
            and path.as_posix() == clean, 'ZIP path traversal or noncanonical path')
    require(all(not part.endswith((' ', '.')) for part in path.parts), 'Ambiguous member path')
    return clean


def zip_inventory(archive):
    rows, seen, expanded = {}, set(), 0
    for item in archive.infolist():
        name = safe_name(item.filename, item.is_dir())
        require(name.casefold() not in seen, 'Duplicate/case-colliding ZIP member')
        seen.add(name.casefold())
        mode = item.external_attr >> 16
        require(stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR) and not item.flag_bits & 1,
                'Special, symlink or encrypted ZIP member')
        if item.is_dir():
            continue
        require(item.file_size <= MAX_MEMBER, 'ZIP member size exceeded')
        expanded += item.file_size
        require(expanded <= MAX_EXPANDED, 'Expanded ZIP size exceeded')
        rows[name] = item
    require(len(rows) <= 100000, 'ZIP member count exceeded')
    return rows


def member_digest(archive, item):
    result, count = hashlib.sha256(), 0
    with archive.open(item) as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            count += len(chunk)
            require(count <= item.file_size, 'Member length exceeded declaration')
            result.update(chunk)
    require(count == item.file_size, 'Truncated member')
    return result.hexdigest()


def read_member(archive, rows, name, maximum=32 * 1024 ** 2):
    require(name in rows and rows[name].file_size <= maximum, 'Missing/oversized required member: ' + name)
    return archive.read(rows[name])


def git_blob(content):
    return hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()


def moon_source_name(name):
    return name == 'moon.mod' or (name.startswith('src/') and (name.endswith('.mbt') or name.endswith('/moon.pkg')))


def production_source_name(name):
    if moon_source_name(name) or name == 'package.json':
        return True
    path = PurePosixPath(name)
    return path.parts[0] in ('cmd', 'integrations') and not (
        any(part in SOURCE_EXCLUDED_DIRS or part.startswith(('moontxnwitness-demo-', 'moontxnwitness-postgres-')) for part in path.parts)
        or path.name in SOURCE_EXCLUDED_NAMES or path.suffix in ('.log', '.pyc'))


def generated_data_output_name(name):
    # Current compiled runtime slots are checked against tested manifest bytes.
    # Other changed tracked outputs may only be data/receipts, never helpers.
    if name.startswith('dist/'):
        return True
    return name.startswith(('verification/', 'artifacts/')) and name.endswith(
        ('.json', '.jsonl', '.ndjson', '.json.gz', '.jsonl.gz', '.csv', '.tsv', '.txt', '.log', '.md'))


def source_cache_exclusions(archive, rows, prefix, source_tree):
    """Read trusted pinned omission data; do not import the artifact's packager."""
    manifest_name = 'scripts/frozen-inputs.json'
    require(manifest_name in source_tree and prefix + manifest_name in rows, 'Missing commit-bound cache omission manifest')
    manifest_raw = read_member(archive, rows, prefix + manifest_name, 1024 ** 2)
    require(git_blob(manifest_raw) == source_tree[manifest_name], 'Cache omission manifest differs from commit')
    manifest = strict_json(manifest_raw, 1024 ** 2)
    require(manifest.get('format') == 'moontxnwitness-frozen-input-index/v1', 'Unknown cache omission format')
    name = safe_name(manifest.get('index'))
    require('/' not in name, 'Cache index must be a sibling file')
    path = 'scripts/' + name
    require(path in source_tree and prefix + path in rows, 'Missing commit-bound cache index')
    compressed = read_member(archive, rows, prefix + path, 32 * 1024 ** 2)
    require(git_blob(compressed) == source_tree[path] and len(compressed) == manifest.get('indexBytes')
            and digest(compressed) == manifest.get('indexSha256'), 'Cache omission data binding differs')
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        expanded = stream.read(32 * 1024 ** 2 + 1)
    entries = strict_json(expanded)
    require(isinstance(entries, dict) and len(entries) == manifest.get('fileCount') and len(entries) <= 20000, 'Invalid cache omission inventory')
    return {safe_name(name) for name in entries}


def validate_run(run, jobs, source_sha, run_id):
    require(run.get('id') == run_id and run.get('head_sha') == source_sha, 'CI head/run identity mismatch')
    require(run.get('path') == WORKFLOW and run.get('event') == 'push', 'Exact PUSH ci.yml required; PR merge previews are forbidden')
    require(run.get('status') == 'completed' and run.get('conclusion') == 'success', 'CI has not completed successfully')
    require(run.get('repository', {}).get('full_name') == REPOSITORY
            and run.get('head_repository', {}).get('full_name') == REPOSITORY, 'Wrong CI repository')
    require(type(run.get('run_attempt')) is int and run['run_attempt'] > 0, 'Missing run attempt')
    selected = {}
    for os_name in ('ubuntu-24.04', 'windows-2022'):
        matches = [job for job in jobs if job.get('name') == 'verify (' + os_name + ')']
        require(len(matches) == 1, 'Exactly one current-attempt ' + os_name + ' verification job required')
        job = matches[0]
        require(job.get('status') == 'completed' and job.get('conclusion') == 'success'
                and job.get('head_sha') == source_sha, 'Failed or wrong-head platform job')
        selected[os_name] = job
    native = [step for step in selected['ubuntu-24.04'].get('steps', []) if step.get('name') == 'Execute Native core on Linux']
    require(len(native) == 1 and native[0].get('status') == 'completed' and native[0].get('conclusion') == 'success', 'Native execution was not successful')
    return selected


def artifact_metadata(artifact, run):
    require(artifact.get('name') == ARTIFACT and artifact.get('expired') is False, 'Wrong/expired CI artifact')
    require(artifact.get('workflow_run', {}).get('id') == run['id']
            and artifact['workflow_run'].get('head_sha') == run['head_sha'], 'Artifact run/head mismatch')
    require(type(artifact.get('id')) is int and artifact['id'] > 0, 'Invalid artifact ID')
    require(type(artifact.get('size_in_bytes')) is int and 0 < artifact['size_in_bytes'] <= MAX_ARCHIVE, 'Artifact byte limit exceeded')
    require(isinstance(artifact.get('digest'), str) and re.fullmatch(r'sha256:[0-9a-f]{64}', artifact['digest']), 'GitHub artifact SHA-256 required')
    try:
        require(dt.datetime.fromisoformat(artifact['created_at'].replace('Z', '+00:00')) >=
                dt.datetime.fromisoformat(run['run_started_at'].replace('Z', '+00:00')), 'Stale artifact from an older attempt')
    except (KeyError, TypeError, ValueError) as error:
        raise ReleaseError('Invalid artifact/run timestamps') from error


def validate_nested(path, kind, version, manifest, tested, outer_bindings, record, source_tree):
    prefix = 'MoonTxnWitness-v' + version + '/'
    with zipfile.ZipFile(path) as archive:
        rows = zip_inventory(archive)
        require(len(rows) == record.get('files') and all(name.startswith(prefix) for name in rows), 'Nested archive root/file count differs')
        root_package = strict_json(read_member(archive, rows, prefix + 'package.json', 1024 ** 2))
        require(root_package.get('version') == version, 'Nested package version mismatch')
        if kind == 'source':
            moon = read_member(archive, rows, prefix + 'moon.mod', 1024 ** 2)
            require(re.findall(rb'^version\s*=\s*"([^"]+)"\s*$', moon, re.M) == [version.encode()], 'MoonBit source version mismatch')
            names = sorted(name[len(prefix):] for name in rows
                           if name == prefix + 'moon.mod' or
                           (name.startswith(prefix + 'src/') and (name.endswith('.mbt') or name.endswith('/moon.pkg'))))
            require(any(name.startswith('src/') and name.endswith('.mbt') for name in names), 'No current MoonBit source')
            require(set(names) == {name for name in source_tree if moon_source_name(name)}, 'Source ZIP differs from committed MoonBit source inventory')
            for name in [*names, 'package.json']:
                expected = source_tree[name]
                require(prefix + name in rows, 'Committed source file missing: ' + name)
                content = read_member(archive, rows, prefix + name, MAX_MEMBER)
                blob = git_blob(content)
                require(blob == expected, 'Source ZIP bytes differ from explicit commit tree: ' + name)
            value = hashlib.sha256()
            for name in names:
                value.update(name.encode() + b'\0')
                with archive.open(rows[prefix + name]) as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b''):
                        value.update(chunk)
                value.update(b'\0')
            require(value.hexdigest() == manifest.get('sourceSha256'), 'Source ZIP/current build fingerprint mismatch')
            missing = {name for name in source_tree if production_source_name(name) and prefix + name not in rows}
            if missing:
                require(missing <= source_cache_exclusions(archive, rows, prefix, source_tree), 'Tracked production source is missing from ZIP')
        else:
            require(strict_json(read_member(archive, rows, prefix + 'dist/build-manifest.json')) == manifest, 'Portable build manifest differs')
        for name, item in rows.items():
            relative = name[len(prefix):]
            actual = member_digest(archive, item)  # CRC and full bytes checked, never executed.
            if relative in source_tree and not relative.endswith('.mbti'):
                committed = git_blob(read_member(archive, rows, name, MAX_MEMBER)) == source_tree[relative]
                if not committed:
                    generated = generated_data_output_name(relative)
                    require(generated and relative in outer_bindings and actual == outer_bindings[relative]['sha256'],
                            'Present tracked source differs from explicit commit: ' + relative)
            if relative in tested:
                require(actual == tested[relative], 'Nested executable source/runtime differs from tested bytes: ' + relative)
            if kind == 'portable' and relative.startswith('dist/'):
                require(relative in outer_bindings and actual == outer_bindings[relative]['sha256'], 'Portable current runtime differs from indexed CI bytes')
        if kind == 'portable':
            for name in ['core.mjs', 'capture-core.mjs', *manifest.get('configuredCoreSha256', {})]:
                require(prefix + 'dist/' + name in rows, 'Portable missing current core: ' + name)


def validate_unit_log_appendix(archive, rows, bindings, index_raw, index):
    """Independently replay the fixed v1 data protocol, never producer code.

    Original index rows stay sealed. Only their direct receipt-bound log bytes
    can justify additional files; a retention pass is not a unit-test verdict.
    """
    if UNIT_LOG_APPENDIX not in rows:
        return set(), None, None
    require(UNIT_LOG_APPENDIX not in bindings, 'Retention appendix cannot replace an indexed file')
    raw = read_member(archive, rows, UNIT_LOG_APPENDIX, 8 * 1024 ** 2)
    appendix = strict_json(raw, 8 * 1024 ** 2)
    fields = {'schema', 'kind', 'passed', 'scope', 'originalIndexModified', 'originalReceiptsModified',
              'originalLogsModified', 'limits', 'sourceIndex', 'selectedReceipts',
              'receiptsWithoutDirectLog', 'logBytesRead', 'retainedLogBytes', 'logs', 'errors'}
    require(isinstance(appendix, dict) and set(appendix) == fields, 'Unknown/incomplete retention appendix')
    require(type(appendix['schema']) is int and appendix['schema'] == 1
            and appendix['kind'] == 'current-receipt-bound-unit-log-retention'
            and appendix['scope'] == 'Log retention only; does not change unit results or prove performance.'
            and appendix['passed'] is True and appendix['errors'] == []
            and all(appendix[name] is False for name in ('originalIndexModified', 'originalReceiptsModified', 'originalLogsModified')),
            'Failed, mutable or unsupported retention appendix')
    source_index = {'file': 'artifacts/ci-evidence/current-run-index.json', 'bytes': len(index_raw),
                    'sha256': digest(index_raw), 'sourceCommit': index['sourceCommit'],
                    'runId': index['runId'], 'runAttempt': index['runAttempt']}
    require(appendix['sourceIndex'] == source_index and type(appendix['sourceIndex'].get('bytes')) is int,
            'Retention appendix is not bound to original index bytes and run')
    limits = appendix['limits']
    require(isinstance(limits, dict) and set(limits) == set(UNIT_LOG_LIMITS)
            and all(type(limits[name]) is int and 0 < limits[name] <= maximum for name, maximum in UNIT_LOG_LIMITS.items()),
            'Retention limit contract differs')
    require(len(index_raw) <= limits['indexBytes'], 'Retention index budget exceeded')
    candidates = [name for name in bindings if name.startswith('verification/') and PurePosixPath(name).name == 'receipt.json']
    require(len(candidates) <= limits['receiptCount'], 'Retention receipt count exceeded')
    logs, additions, receipt_bytes, no_log, log_bytes = [], set(), 0, 0, 0
    for name in candidates:
        row = bindings[name]
        receipt_bytes += row['bytes']
        require(row['bytes'] <= limits['perReceiptBytes'] and receipt_bytes <= limits['totalReceiptBytes'],
                'Retention receipt byte budget exceeded')
        receipt = strict_json(read_member(archive, rows, name, limits['perReceiptBytes']), limits['perReceiptBytes'])
        require(isinstance(receipt, dict), 'Retention source receipt must be an object')
        if 'log' not in receipt:
            no_log += 1
            continue
        reference = receipt['log']
        require(isinstance(reference, dict) and isinstance(reference.get('sha256'), str)
                and SHA.fullmatch(reference['sha256']), 'Missing actual receipt direct-log binding')
        leaf = safe_name(reference.get('file'))
        require(len(PurePosixPath(leaf).parts) == 1 and leaf.lower().endswith(('.log', '.txt', '.out', '.stdout', '.stderr')),
                'Retained log must be a non-executable same-directory leaf')
        source = (PurePosixPath(name).parent / leaf).as_posix()
        require(source.startswith('verification/') and source in rows
                and not (rows[source].external_attr >> 16) & 0o111, 'Retained log missing or marked executable')
        length = rows[source].file_size
        log_bytes += length
        require(length <= limits['perLogBytes'] and log_bytes <= limits['totalLogReadBytes'], 'Retention log byte budget exceeded')
        require(member_digest(archive, rows[source]) == reference['sha256'], 'Retained log differs from actual receipt SHA-256')
        already = source in bindings
        if already:
            require(bindings[source]['bytes'] == length and bindings[source]['sha256'] == reference['sha256'], 'Existing indexed log differs')
        else:
            require(source not in additions, 'Duplicate appended log source')
            additions.add(source)
        logs.append({'receipt': name, 'retained': True, 'receiptSha256': row['sha256'],
                     'source': source, 'sha256': reference['sha256'], 'sourceBytes': length,
                     'status': 'already-present-verified' if already else 'copied-exact-original',
                     'retainedBytes': length})
    require(isinstance(appendix['logs'], list) and appendix['logs'] == logs
            and all(type(item.get('sourceBytes')) is int and type(item.get('retainedBytes')) is int
                    and item.get('retained') is True for item in appendix['logs']),
            'Retention log rows, sources, statuses or counters differ')
    counts = {'selectedReceipts': len(candidates), 'receiptsWithoutDirectLog': no_log,
              'logBytesRead': log_bytes, 'retainedLogBytes': log_bytes}
    require(all(type(appendix[name]) is int and appendix[name] == value for name, value in counts.items()),
            'Retention summary counters differ')
    metadata = {'passed': True, 'schema': 1, 'file': UNIT_LOG_APPENDIX, 'bytes': len(raw), 'sha256': digest(raw),
                'originalIndexSha256': digest(index_raw), 'retainedLogs': len(logs), 'appendedLogs': len(additions),
                **counts, 'originalIndexAndReceiptsUnchanged': True,
                'scope': 'Direct receipt log retention only; original unit outcomes are not promoted'}
    return additions | {UNIT_LOG_APPENDIX}, metadata, raw


def validate_archive(path, artifact, run, version, source_sha, output, source_tree):
    artifact_metadata(artifact, run)
    require(Path(path).stat().st_size == artifact['size_in_bytes']
            and 'sha256:' + file_digest(path) == artifact['digest'], 'Original artifact ZIP SHA-256/length mismatch')
    output = Path(output)
    review = output.parent / 'archive-review'
    review.mkdir(exist_ok=False)
    stem = 'MoonTxnWitness-v' + version
    asset_names = [stem + '-source.zip', stem + '-portable.zip', stem + '-SHA256SUMS.txt']
    with zipfile.ZipFile(path) as archive:
        rows = zip_inventory(archive)
        index_raw = read_member(archive, rows, 'current-run-index.json', 8 * 1024 ** 2)
        index = strict_json(index_raw, 8 * 1024 ** 2)
        require(type(index.get('schema')) is int and index['schema'] == 1 and index.get('version') == version and index.get('sourceCommit') == source_sha, 'Current-run index source/version mismatch (merge preview or stale packet)')
        require(index.get('runId') == str(run['id']) and index.get('runAttempt') == str(run['run_attempt']), 'Current-run index run/attempt mismatch')
        require(isinstance(index.get('files'), list), 'Missing per-file index')
        bindings = {}
        for row in index['files']:
            require(isinstance(row, dict) and set(row) == {'file', 'bytes', 'sha256'}, 'Unknown/invalid index row')
            name = safe_name(row['file'])
            require(name not in bindings and type(row['bytes']) is int and row['bytes'] >= 0
                    and isinstance(row['sha256'], str) and SHA.fullmatch(row['sha256']), 'Invalid/duplicate indexed binding')
            require(name in rows and rows[name].file_size == row['bytes'] and member_digest(archive, rows[name]) == row['sha256'], 'Indexed member bytes differ: ' + name)
            bindings[name] = row
        additions, retention, retention_raw = validate_unit_log_appendix(archive, rows, bindings, index_raw, index)
        require(set(rows) == set(bindings) | {'current-run-index.json'} | additions, 'Unindexed or missing artifact files')
        summary = strict_json(read_member(archive, rows, 'verification/summary.json'))
        package = strict_json(read_member(archive, rows, 'verification/package.json'))
        manifest = strict_json(read_member(archive, rows, 'dist/build-manifest.json'))
        require(summary.get('passed') is True and summary.get('version') == version
                and package.get('passed') is True and package.get('version') == version, 'Current tests/package did not pass')
        require(package.get('sourceRebuilt') is True and type(package.get('freshConsumerChecks')) is int and package['freshConsumerChecks'] > 0, 'Fresh source/portable consumers were not verified')
        require(manifest.get('version') == version and summary.get('buildManifest') == manifest
                and isinstance(manifest.get('sourceSha256'), str) and SHA.fullmatch(manifest['sourceSha256']), 'Current build/summary binding differs')
        require(set(summary.get('executedTargets', [])) >= {'js', 'wasm-gc', 'wasm'}, 'Actual three-target execution missing')
        counts = summary.get('coreTestCountsByTarget', {})
        require(all(type(counts.get(target)) is int and counts[target] > 0 for target in ('js', 'wasm-gc', 'wasm')), 'Current core test counts missing')
        tested = summary.get('testedFileSha256')
        require(isinstance(tested, dict), 'Tested current-file bindings missing')
        configured = manifest.get('configuredCoreSha256')
        require(isinstance(configured, dict) and set(configured) == {'configured-session-core.mjs', 'source-components-core.mjs', 'sql-projection-core.mjs', 'sql-fetch-core.mjs'}, 'Four current configured cores required')
        cores = {'core.mjs': manifest.get('coreSha256'), 'capture-core.mjs': manifest.get('captureCoreSha256'), **configured}
        for name, expected in cores.items():
            key = 'dist/' + name
            require(isinstance(expected, str) and SHA.fullmatch(expected)
                    and key in bindings and bindings[key]['sha256'] == expected == tested.get(key), 'Current tested compiled-core binding differs: ' + name)
        require('dist/build-manifest.json' in tested and tested['dist/build-manifest.json'] == bindings['dist/build-manifest.json']['sha256'], 'Tested manifest bytes differ')
        for name, row in bindings.items():
            if name in tested:
                require(row['sha256'] == tested[name], 'Indexed tested source/runtime binding differs: ' + name)
        archives = package.get('archives')
        require(isinstance(archives, list) and len(archives) == 2 and {record.get('file') for record in archives} == set(asset_names[:2]), 'Exactly two current-version archive targets required')
        for record in archives:
            require(set(record) == {'file', 'bytes', 'sha256', 'files'} and type(record['files']) is int and record['files'] > 0, 'Invalid archive receipt')
            member = 'artifacts/' + record['file']
            require(member in bindings and record['bytes'] == bindings[member]['bytes'] and record['sha256'] == bindings[member]['sha256'], 'Archive differs from fresh-consumer receipt')
        sums = read_member(archive, rows, 'artifacts/' + asset_names[2], 4096)
        require(sums == ''.join(record['sha256'] + '  ' + record['file'] + '\n' for record in archives).encode(), 'SHA256SUMS must bind exactly both current targets')
        for name in asset_names:
            with archive.open(rows['artifacts/' + name]) as source, (review / name).open('xb') as target:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    target.write(chunk)
        for record in archives:
            validate_nested(review / record['file'], 'source' if record['file'].endswith('-source.zip') else 'portable', version, manifest, tested, bindings, record, source_tree)
        output.mkdir(exist_ok=False)
        for name in asset_names:
            (review / name).rename(output / name)
        return {'index': index, 'summary': summary, 'package': package, 'buildManifest': manifest,
                'unitLogRetention': retention, 'unitLogAppendixRaw': retention_raw,
                'assets': [{'name': name, 'bytes': (output / name).stat().st_size, 'sha256': file_digest(output / name)} for name in asset_names],
                'nativeExecution': 'successful exact-run Linux Native job step; not synthesized into the three-target summary'}


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        require(urllib.parse.urlparse(newurl).scheme == 'https', 'Insecure download redirect')
        result = super().redirect_request(request, fp, code, message, headers, newurl)
        if urllib.parse.urlparse(newurl).hostname != 'api.github.com':
            result.remove_header('Authorization')
        return result


class GitHub:
    def __init__(self, token):
        self.token = token
        self.opener = urllib.request.build_opener(Redirect())

    def api(self, method, path, body=None, optional=False):
        require(path.startswith('/repos/' + REPOSITORY + '/'), 'Unexpected API path')
        headers = {'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
        data = None if body is None else json.dumps(body).encode()
        if data is not None:
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request('https://api.github.com' + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=60) as response:
                return strict_json(response.read(8 * 1024 ** 2 + 1), 8 * 1024 ** 2)
        except urllib.error.HTTPError as error:
            if optional and error.code == 404:
                return None
            raise ReleaseError('GitHub API failed: ' + str(error.code) + ' ' + method + ' ' + path) from error

    def download(self, artifact, target):
        request = urllib.request.Request('https://api.github.com/repos/' + REPOSITORY + '/actions/artifacts/' + str(artifact['id']) + '/zip', headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json'})
        count = 0
        with self.opener.open(request, timeout=120) as source, Path(target).open('xb') as output:
            while chunk := source.read(1024 * 1024):
                count += len(chunk)
                require(count <= artifact['size_in_bytes'], 'Artifact download exceeds API length')
                output.write(chunk)
        require(count == artifact['size_in_bytes'], 'Artifact download length mismatch')

    def upload(self, release_id, path):
        path = Path(path)
        route = '/repos/' + REPOSITORY + '/releases/' + str(release_id) + '/assets?name=' + urllib.parse.quote(path.name, safe='')
        connection = http.client.HTTPSConnection('uploads.github.com', timeout=120)
        try:
            connection.putrequest('POST', route)
            connection.putheader('Authorization', 'Bearer ' + self.token)
            connection.putheader('Content-Type', 'application/octet-stream')
            connection.putheader('Content-Length', str(path.stat().st_size))
            connection.endheaders()
            with path.open('rb') as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    connection.send(chunk)
            response = connection.getresponse()
            require(response.status == 201, 'GitHub asset upload failed: ' + str(response.status))
            return strict_json(response.read(8 * 1024 ** 2 + 1), 8 * 1024 ** 2)
        finally:
            connection.close()


def paged(client, path, field=None):
    result = []
    for page in range(1, 11):
        value = client.api('GET', path + ('&' if '?' in path else '?') + 'per_page=100&page=' + str(page))
        rows = value.get(field) if field else value
        require(isinstance(rows, list), 'Invalid paginated GitHub response')
        result.extend(rows)
        if len(rows) < 100:
            return result
    raise ReleaseError('GitHub pagination limit exceeded')


def remote_tag(client, tag):
    value = client.api('GET', '/repos/' + REPOSITORY + '/git/ref/tags/' + tag, optional=True)
    if value is None:
        return None
    require(value.get('ref') == 'refs/tags/' + tag, 'Tag identity mismatch')
    obj = value.get('object', {})
    for _ in range(5):
        if obj.get('type') == 'commit':
            return obj.get('sha')
        require(obj.get('type') == 'tag' and COMMIT.fullmatch(obj.get('sha', '')), 'Unsupported tag object')
        obj = client.api('GET', '/repos/' + REPOSITORY + '/git/tags/' + obj['sha']).get('object', {})
    raise ReleaseError('Excessive annotated tag depth')


def notes_bytes(path, version):
    path = Path(path)
    require(not path.is_symlink() and path.is_file(), 'Notes must be a regular caller file')
    raw = path.read_bytes()
    require(0 < len(raw) <= 65536 and b'\0' not in raw, 'Invalid notes byte boundary')
    text = raw.decode('utf8')
    require(re.search(r'^#{1,6}[ \t]+MoonTxnWitness[ \t]+v' + re.escape(version) + r'[ \t]*\r?$', text, re.M), 'Notes must have the exact explicit-version Markdown heading')
    require(not re.search(r'\b(?:AI|contest|competition)\b|AI辅助|比赛|竞赛|审核|申报', text, re.I), 'Release notes must contain only technical product content')
    return raw, text


def release_state(client, tag, sha, notes, assets):
    actual = remote_tag(client, tag)
    require(actual is None or actual == sha, 'Preexisting tag points to unexpected source')
    release = client.api('GET', '/repos/' + REPOSITORY + '/releases/tags/' + tag, optional=True)
    if release is None:
        return actual, None, {}
    require(actual == sha and release.get('tag_name') == tag and release.get('target_commitish') == sha
            and release.get('name') == 'MoonTxnWitness ' + tag and release.get('body') == notes
            and release.get('draft') is False and release.get('prerelease') is False, 'Unexpected preexisting release; no replacement permitted')
    existing = paged(client, '/repos/' + REPOSITORY + '/releases/' + str(release['id']) + '/assets')
    by_name, expected = {}, {row['name']: row for row in assets}
    for row in existing:
        name = row.get('name')
        require(name in expected and name not in by_name and row.get('state') == 'uploaded'
                and row.get('size') == expected[name]['bytes'] and row.get('digest') == 'sha256:' + expected[name]['sha256'], 'Unexpected or changed existing release asset; no overwrite permitted')
        by_name[name] = row
    return actual, release, by_name


def prepare(client, version, source_sha, run_id, notes, output, publish=False):
    require(VERSION.fullmatch(version) and len(version) <= 32, 'Explicit canonical stable version required')
    require(COMMIT.fullmatch(source_sha) and type(run_id) is int and run_id > 0, 'Explicit full source SHA and CI run ID required')
    raw_notes, text_notes = notes_bytes(notes, version)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    repo = '/repos/' + REPOSITORY
    run = client.api('GET', repo + '/actions/runs/' + str(run_id))
    jobs = paged(client, repo + '/actions/runs/' + str(run_id) + '/attempts/' + str(run.get('run_attempt')) + '/jobs', 'jobs')
    selected_jobs = validate_run(run, jobs, source_sha, run_id)
    workflow = client.api('GET', repo + '/actions/workflows/ci.yml')
    require(run.get('workflow_id') == workflow.get('id') and workflow.get('path') == WORKFLOW, 'CI workflow definition identity mismatch')
    commit = client.api('GET', repo + '/git/commits/' + source_sha)
    require(commit.get('sha') == source_sha and COMMIT.fullmatch(commit.get('tree', {}).get('sha', '')), 'Source commit/tree is unavailable')
    tree = client.api('GET', repo + '/git/trees/' + commit['tree']['sha'] + '?recursive=1')
    require(tree.get('truncated') is False and isinstance(tree.get('tree'), list), 'Complete commit source tree required')
    source_tree = {}
    for row in tree['tree']:
        name = row.get('path', '')
        if row.get('type') == 'blob':
            require(row.get('mode') in ('100644', '100755') and COMMIT.fullmatch(row.get('sha', '')) and name not in source_tree, 'Invalid committed source tree member')
            source_tree[safe_name(name)] = row['sha']
    require({'moon.mod', 'package.json'} <= set(source_tree), 'Incomplete commit source binding')
    artifacts = paged(client, repo + '/actions/runs/' + str(run_id) + '/artifacts', 'artifacts')
    matches = [row for row in artifacts if row.get('name') == ARTIFACT and row.get('expired') is False]
    require(len(matches) == 1, 'Exactly one nonexpired Linux current-run artifact required')
    artifact = matches[0]
    artifact_metadata(artifact, run)
    save(output / 'evidence/run.json', run)
    save(output / 'evidence/jobs.json', selected_jobs)
    save(output / 'evidence/artifact.json', artifact)
    save(output / 'evidence/committed-source-tree.json', source_tree)
    save(output / 'evidence/release-notes.md', raw_notes)
    original = output / 'original-artifact.zip'
    client.download(artifact, original)
    packet = validate_archive(original, artifact, run, version, source_sha, output / 'release', source_tree)
    for name in ('index', 'summary', 'package', 'buildManifest'):
        save(output / ('evidence/' + name + '.json'), packet[name])
    if packet['unitLogAppendixRaw'] is not None:
        save(output / 'evidence' / UNIT_LOG_APPENDIX, packet['unitLogAppendixRaw'])
    tag = 'v' + version
    actual_tag, release, existing = release_state(client, tag, source_sha, text_notes, packet['assets'])
    receipt = {'format': 'moontxnwitness-github-ci-release/v1', 'version': version, 'sourceCommit': source_sha,
               'runId': run_id, 'runAttempt': run['run_attempt'], 'artifactId': artifact['id'],
               'originalArtifactSha256': artifact['digest'].removeprefix('sha256:'), 'assets': packet['assets'],
               'notesSha256': digest(raw_notes), 'nativeExecution': packet['nativeExecution'],
               'unitLogRetention': packet['unitLogRetention'],
               'artifactCodeExecuted': False, 'publishRequested': publish, 'published': False,
               'plan': {'createTag': actual_tag is None, 'createRelease': release is None,
                        'uploadAssets': [row['name'] for row in packet['assets'] if row['name'] not in existing]},
               'scope': 'GitHub source/portable assets only; Mooncakes and public consumers are separate validations'}
    save(output / 'candidate.json', receipt)
    if not publish:
        return receipt
    if actual_tag is None:
        client.api('POST', repo + '/git/refs', {'ref': 'refs/tags/' + tag, 'sha': source_sha})
    require(remote_tag(client, tag) == source_sha, 'Tag changed before publication')
    if release is None:
        release = client.api('POST', repo + '/releases', {'tag_name': tag, 'target_commitish': source_sha,
                             'name': 'MoonTxnWitness ' + tag, 'body': text_notes,
                             'draft': False, 'prerelease': False, 'generate_release_notes': False})
    require(type(release.get('id')) is int and release['id'] > 0, 'Invalid release identity')
    for asset in packet['assets']:
        if asset['name'] not in existing:
            uploaded = client.upload(release['id'], output / 'release' / asset['name'])
            require(uploaded.get('name') == asset['name'] and uploaded.get('size') == asset['bytes']
                    and uploaded.get('digest') == 'sha256:' + asset['sha256'], 'Uploaded asset bytes differ')
    _, checked, checked_assets = release_state(client, tag, source_sha, text_notes, packet['assets'])
    require(checked and len(checked_assets) == 3, 'Published release asset set incomplete')
    receipt = {**receipt, 'published': True, 'releaseId': checked['id'],
               'url': 'https://github.com/' + REPOSITORY + '/releases/tag/' + tag}
    save(output / 'published.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--ci-run-id', required=True, type=int)
    parser.add_argument('--notes', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    require(bool(token), 'A GitHub Actions read token is required; publication additionally requires contents:write')
    result = prepare(GitHub(token), args.version, args.source_sha, args.ci_run_id, args.notes, args.output, args.publish)
    print(json.dumps({key: result[key] for key in ('version', 'sourceCommit', 'runId', 'runAttempt', 'artifactId', 'originalArtifactSha256', 'assets', 'unitLogRetention', 'published', 'artifactCodeExecuted')}))


if __name__ == '__main__':
    main()
