"""Restore checksum-pinned public inputs without adding payloads to Git."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import errno
import time
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MAX_INDEX = 8 * 1024 * 1024
MAX_MEMBER = 32 * 1024 * 1024
MAX_ARCHIVE = 128 * 1024 * 1024


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def safe_name(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value or any(p in ('', '.', '..') for p in value.split('/')) or PurePosixPath(value).is_absolute():
        raise ValueError('Unsafe frozen-input member')
    return value


def regular(path):
    s = Path(path).lstat()
    if not stat.S_ISREG(s.st_mode) or getattr(s, 'st_file_attributes', 0) & 0x400:
        raise ValueError('Frozen input must be a regular file')
    return s


def directory(path):
    path = Path(os.path.abspath(path))
    for p in [*reversed(path.parents), path]:
        if p.exists():
            s = p.lstat()
            if not stat.S_ISDIR(s.st_mode) or getattr(s, 'st_file_attributes', 0) & 0x400:
                raise ValueError('Cache directory cannot contain links')
        else:
            try:
                p.mkdir()
            except FileExistsError:
                pass
            checked = p.lstat()
            if not stat.S_ISDIR(checked.st_mode) or getattr(checked, 'st_file_attributes', 0) & 0x400:
                raise ValueError('Concurrent cache directory is unsafe')
    return path


def verify_file(path, entry):
    s = regular(path)
    if s.st_size != entry['bytes'] or sha_file(path) != entry['sha256']:
        raise ValueError('Frozen input bytes differ')


def load_index(root=ROOT):
    root = Path(root)
    manifest_path = root / 'scripts/frozen-inputs.json'
    manifest = json.loads(manifest_path.read_text('utf8'))
    if manifest.get('format') != 'moontxnwitness-frozen-input-index/v1':
        raise ValueError('Unsupported frozen input index')
    index_name = safe_name(manifest['index'])
    if '/' in index_name:
        raise ValueError('Index must be a sibling file')
    index_path = root / 'scripts' / index_name
    verify_file(index_path, {'bytes': manifest['indexBytes'], 'sha256': manifest['indexSha256']})
    with gzip.GzipFile(fileobj=io.BytesIO(index_path.read_bytes())) as compressed:
        raw = compressed.read(MAX_INDEX + 1)
    if len(raw) > MAX_INDEX:
        raise ValueError('Frozen index expansion budget')
    entries = json.loads(raw)
    if not isinstance(entries, dict) or len(entries) != manifest['fileCount'] or len(entries) > 20000:
        raise ValueError('Frozen input count differs')
    folded = set()
    hash_sizes = {}
    for name, row in entries.items():
        safe_name(name)
        if not name.startswith(('cmd/legacy/', 'cmd/legacy-components/', 'fixtures/', 'verification/', 'artifacts/compat-v030/runtime/', 'artifacts/compat-v031/runtime/')):
            raise ValueError('Frozen input cannot replace active sources')
        if name.casefold() in folded:
            raise ValueError('Case-colliding frozen members')
        folded.add(name.casefold())
        previous_size = hash_sizes.setdefault(row['sha256'], row['bytes'])
        if previous_size != row['bytes']:
            raise ValueError('Conflicting content-addressed size')
        safe_name(row['member'])
        if row['provider'] not in manifest['providers'] or row['group'] not in ('runtime', 'tests'):
            raise ValueError('Unknown frozen input group/provider')
        if type(row['bytes']) is not int or not 0 <= row['bytes'] <= MAX_MEMBER or len(row['sha256']) != 64 or any(c not in '0123456789abcdef' for c in row['sha256']):
            raise ValueError('Frozen member budget/hash')
    for p in manifest['providers'].values():
        u = urllib.parse.urlsplit(p['url'])
        if u.scheme != 'https' or u.hostname != 'github.com' or u.username or u.password or u.port not in (None, 443) or not u.path.startswith('/HhWw96/moontxnwitness/releases/download/') or u.query or u.fragment:
            raise ValueError('Frozen provider must be a declared public release')
        if type(p['bytes']) is not int or not 0 < p['bytes'] <= MAX_ARCHIVE:
            raise ValueError('Frozen archive budget')
        if len(p['sha256']) != 64 or any(c not in '0123456789abcdef' for c in p['sha256']):
            raise ValueError('Frozen provider hash')
        if '/' in safe_name(p['seed']):
            raise ValueError('Seed must be a file name')
    if not 0 <= manifest['logicalBytes'] <= 1024 * 1024 * 1024 or sum(r['bytes'] for r in entries.values()) != manifest['logicalBytes']:
        raise ValueError('Frozen logical byte count differs')
    return manifest, entries


def exclusive_copy(source, target, entry):
    # Fallback volumes expose the new file only to a serialized prepare writer.
    # Interrupted/partial bytes are never accepted by a subsequent hash check.
    try:
        out = Path(target).open('xb')
    except FileExistsError:
        verify_file(target, entry)
        return 'reused'
    created = os.fstat(out.fileno())
    try:
        with Path(source).open('rb') as incoming:
            shutil.copyfileobj(incoming, out, 1024 * 1024)
        out.flush()
        os.fsync(out.fileno())
        verify_file(target, entry)
        return 'copied'
    except BaseException:
        out.close()
        if Path(target).exists():
            current = regular(target)
            if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                Path(target).unlink()
        raise
    finally:
        out.close()


def immutable_publish(temp, target, entry):
    verify_file(temp, entry)
    try:
        try:
            os.link(temp, target)
        except FileExistsError:
            verify_file(target, entry)
        except OSError:
            exclusive_copy(temp, target, entry)
    finally:
        Path(temp).unlink(missing_ok=True)


@contextmanager
def preparation_lock(cache):
    path = cache / '.prepare.lock'
    if path.exists() or path.is_symlink():
        before = regular(path)
        if before.st_nlink != 1 or before.st_size not in (0, 1):
            raise ValueError('Unsafe cache lock file')
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        opened, named = os.fstat(fd), regular(path)
        if opened.st_nlink != 1 or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
            raise ValueError('Cache lock identity differs')
        if opened.st_size == 0:
            os.write(fd, b'0')
        deadline = time.monotonic() + 600
        while True:
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK) or time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
        yield
    finally:
        os.close(fd)


class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise ValueError('Provider redirect must retain HTTPS')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def archive_file(root, cache, provider, offline):
    target = directory(cache / 'archives') / (provider['sha256'] + '.zip')
    if target.exists() or target.is_symlink():
        verify_file(target, provider)
        return target
    seed = root / 'artifacts' / provider['seed']
    fd, tmp = tempfile.mkstemp(prefix='archive-', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            if seed.exists():
                verify_file(seed, provider)
                with seed.open('rb') as stream:
                    shutil.copyfileobj(stream, out, 1024 * 1024)
            elif offline:
                raise FileNotFoundError('Pinned archive is unavailable offline')
            else:
                request = urllib.request.Request(provider['url'], headers={'User-Agent': 'MoonTxnWitness-frozen-inputs/v1'})
                with urllib.request.build_opener(HTTPSRedirect).open(request, timeout=45) as response:
                    count = 0
                    started = time.monotonic()
                    while part := response.read(1024 * 1024):
                        count += len(part)
                        if time.monotonic() - started > 300:
                            raise ValueError('Archive download time budget exceeded')
                        if count > provider['bytes']:
                            raise ValueError('Archive download budget exceeded')
                        out.write(part)
            out.flush()
            os.fsync(out.fileno())
        immutable_publish(tmp, target, provider)
        return target
    finally:
        Path(tmp).unlink(missing_ok=True)


def ensure_blob(cache, archive, entry):
    blob = directory(cache / 'blobs' / entry['sha256'][:2]) / entry['sha256']
    if blob.exists() or blob.is_symlink():
        verify_file(blob, entry)
        return blob
    info = archive.getinfo(entry['member'])
    if info.is_dir() or info.file_size != entry['bytes'] or stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG):
        raise ValueError('Pinned ZIP member shape differs')
    fd, tmp = tempfile.mkstemp(prefix='blob-', dir=blob.parent)
    try:
        with os.fdopen(fd, 'wb') as out, archive.open(info) as source:
            count = 0
            while part := source.read(1024 * 1024):
                count += len(part)
                if count > entry['bytes']:
                    raise ValueError('Member expansion budget exceeded')
                out.write(part)
            out.flush()
            os.fsync(out.fileno())
        immutable_publish(tmp, blob, entry)
        return blob
    finally:
        Path(tmp).unlink(missing_ok=True)


def materialize(root, name, blob, entry):
    target = directory((root / name).parent) / Path(name).name
    if target.exists() or target.is_symlink():
        regular(target)
        if not os.path.samefile(target, blob):
            verify_file(target, entry)
        return 'reused'
    # link is an atomic no-clobber publication, even if another writer wins.
    try:
        os.link(blob, target)
        return 'linked'
    except FileExistsError:
        verify_file(target, entry)
        return 'reused'
    except OSError:
        return exclusive_copy(blob, target, entry)


def prepare(root=ROOT, scope='tests', offline=False, cache_dir=None):
    if scope not in ('runtime', 'tests'):
        raise ValueError('Unknown preparation scope')
    root = Path(os.path.abspath(root))
    manifest, entries = load_index(root)
    selected = {n: r for n, r in entries.items() if scope == 'tests' or r['group'] == 'runtime'}
    cache = directory(cache_dir or os.environ.get('MTW_INPUT_CACHE', str(root / 'artifacts/input-cache')))
    counts = {'linked': 0, 'copied': 0, 'reused': 0}
    verified = set()
    with preparation_lock(cache):
        for provider_id in sorted({r['provider'] for r in selected.values()}):
            archive = None
            try:
                for name, entry in selected.items():
                    if entry['provider'] != provider_id:
                        continue
                    blob = cache / 'blobs' / entry['sha256'][:2] / entry['sha256']
                    if entry['sha256'] not in verified:
                        if blob.exists() or blob.is_symlink():
                            verify_file(blob, entry)
                        else:
                            if archive is None:
                                archive = zipfile.ZipFile(archive_file(root, cache, manifest['providers'][provider_id], offline))
                                names = archive.namelist()
                                if len(names) != len(set(names)) or len(names) > 20000:
                                    raise ValueError('Duplicate/oversized ZIP inventory')
                            blob = ensure_blob(cache, archive, entry)
                        verified.add(entry['sha256'])
                    counts[materialize(root, name, blob, entry)] += 1
            finally:
                if archive is not None:
                    archive.close()
    return {'passed': True, 'scope': scope, 'verifiedFiles': len(selected), 'logicalBytes': sum(r['bytes'] for r in selected.values()), 'indexSha256': manifest['indexSha256'], **counts}


def public_cached_entries(root=ROOT):
    """Known immutable inputs; this does not authorize any unindexed ignored file."""
    if not (Path(root) / 'scripts/frozen-inputs.json').is_file():
        return {}
    return {n: r for n, r in load_index(root)[1].items() if not n.startswith('artifacts/')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'inventory'])
    parser.add_argument('--scope', choices=['runtime', 'tests'], default='tests')
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(scope=args.scope, offline=args.offline) if args.command == 'prepare' else {k: v for k, v in load_index()[0].items() if k != 'providers'}))
    except Exception as error:
        print(json.dumps({'passed': False, 'error': type(error).__name__, 'reason': str(error) if isinstance(error, ValueError) else 'Frozen input preparation did not complete'}))
        raise SystemExit(1)
