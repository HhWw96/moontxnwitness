"""Bounded public-asset transport and fresh ZIP extraction.

Downloads retain their uniquely named partial file on failure. Extraction never
overwrites an existing destination and leaves first-failure output in place.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import time
import unicodedata
import urllib.parse
import urllib.request
import uuid
import zipfile

CHUNK_BYTES = 64 * 1024
MAX_DOWNLOAD_BYTES = 256 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_ZIP_ENTRIES = 32768
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_DIRECTORY_BYTES = 32 * 1024 * 1024


class PublicationDownloadError(ValueError):
    pass


def _limit(value, maximum, label):
    if type(value) is not int or not 0 < value <= maximum:
        raise PublicationDownloadError('Invalid ' + label + ' budget')
    return value


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _regular(path, info, maximum):
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
        raise PublicationDownloadError('Regular bounded file required')


def _confirm_path(path, info, maximum):
    # Windows3.12 exposes different ctime meanings via stat(path) and fstat(fd).
    # Keep full identity comparisons within fd APIs; still prove the path binds
    # the same device/inode/size/mtime and is not a symlink.
    if path.is_symlink():
        raise PublicationDownloadError('File path became a symlink')
    with path.open('rb') as probe:
        reopened = os.fstat(probe.fileno())
    _regular(path, reopened, maximum)
    current = path.stat()
    _regular(path, current, maximum)
    if (_identity(reopened) != _identity(info)
            or (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) !=
               (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)):
        raise PublicationDownloadError('File path changed during bounded reading')


def sha256_file(path, *, max_bytes=MAX_DOWNLOAD_BYTES):
    """Hash without loading the asset into memory; reject size/path changes."""
    _limit(max_bytes, MAX_EXPANDED_BYTES, 'hash')
    path = Path(path)
    digest, count = hashlib.sha256(), 0
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        _regular(path, before, max_bytes)
        while raw := stream.read(min(CHUNK_BYTES, max_bytes - count + 1)):
            count += len(raw)
            if count > max_bytes:
                raise PublicationDownloadError('Hash byte budget exceeded')
            digest.update(raw)
        after = os.fstat(stream.fileno())
    if _identity(before) != _identity(after) or count != after.st_size:
        raise PublicationDownloadError('File changed while hashing')
    _confirm_path(path, after, max_bytes)
    return digest.hexdigest()


def download_file(url, destination, *, max_bytes=MAX_DOWNLOAD_BYTES,
                  timeout=60, max_seconds=900, user_agent='MoonTxnWitness-public-verification',
                  expected_sha256=None, opener=None):
    """Stream one anonymous HTTPS response, preserving any failed partial."""
    _limit(max_bytes, MAX_DOWNLOAD_BYTES, 'download')
    if not 0 < timeout <= 300 or not 0 < max_seconds <= 1800:
        raise PublicationDownloadError('Invalid download time budget')
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.username is not None or parsed.password is not None:
        raise PublicationDownloadError('Anonymous HTTPS URL required')
    if expected_sha256 is not None and not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
        raise PublicationDownloadError('Expected SHA-256 must be lowercase hexadecimal')
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise PublicationDownloadError('Download destination already exists')
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise PublicationDownloadError('Existing owned parent directory required')
    partial = destination.with_name(destination.name + '.partial-' + uuid.uuid4().hex)
    request = urllib.request.Request(url, headers={'User-Agent': user_agent})
    opener = opener or urllib.request.urlopen
    digest, count, started = hashlib.sha256(), 0, time.monotonic()
    # Create first, so connection/header failures also leave a distinct attempt.
    with partial.open('xb') as stream:
        with opener(request, timeout=timeout) as response:
            if response.status != 200:
                raise PublicationDownloadError('Public download did not return HTTP 200')
            final_url = urllib.parse.urlsplit(response.geturl())
            if (final_url.scheme != 'https' or not final_url.netloc
                    or final_url.username is not None or final_url.password is not None):
                raise PublicationDownloadError('Public redirect must remain anonymous HTTPS')
            length = response.headers.get('Content-Length')
            if length is not None:
                if not re.fullmatch(r'[0-9]+', str(length)):
                    raise PublicationDownloadError('Malformed Content-Length')
                length = int(length)
                if length > max_bytes:
                    raise PublicationDownloadError('Advertised download exceeds byte budget')
            while True:
                if time.monotonic() - started > max_seconds:
                    raise PublicationDownloadError('Download wall-clock budget exceeded')
                requested = min(CHUNK_BYTES, max_bytes - count + 1)
                raw = response.read(requested)
                if not isinstance(raw, bytes) or len(raw) > requested:
                    raise PublicationDownloadError('Response violated bounded read contract')
                if not raw:
                    break
                count += len(raw)
                if stream.write(raw) != len(raw):
                    raise PublicationDownloadError('Short download write')
                digest.update(raw)
                if count > max_bytes:
                    raise PublicationDownloadError('Actual download exceeds byte budget')
            if length is not None and count != length:
                raise PublicationDownloadError('Actual bytes differ from Content-Length')
        if expected_sha256 is not None and digest.hexdigest() != expected_sha256:
            raise PublicationDownloadError('Published asset digest mismatch')
        stream.flush()
        os.fsync(stream.fileno())
    # Atomic, exclusive publication. A concurrently created target is never lost.
    os.link(partial, destination)
    try:
        partial.unlink()
    except OSError:
        pass  # Both names still identify the same complete verified bytes.
    return destination


def _zip_directory_bound(stream, file_size, max_entries):
    """Bound the classic central directory before ZipFile allocates its entries."""
    if file_size < 22:
        raise PublicationDownloadError('Truncated ZIP')
    stream.seek(max(0, file_size - 65557))
    tail = stream.read(min(file_size, 65557))
    offset = tail.rfind(b'PK\x05\x06')
    if offset < 0 or len(tail) - offset < 22:
        raise PublicationDownloadError('ZIP end record missing')
    fields = struct.unpack('<4s4H2LH', tail[offset:offset + 22])
    _, disk, directory_disk, disk_entries, entries, size, start, comment_bytes = fields
    end_record = file_size - len(tail) + offset
    if offset + 22 + comment_bytes != len(tail):
        raise PublicationDownloadError('Noncanonical ZIP end/comment length')
    if disk or directory_disk or disk_entries != entries:
        raise PublicationDownloadError('Multi-volume ZIP is unsupported')
    if entries == 65535 or size == 0xffffffff or start == 0xffffffff:
        raise PublicationDownloadError('ZIP64 exceeds this bounded publication profile')
    if entries > max_entries or size > MAX_DIRECTORY_BYTES:
        raise PublicationDownloadError('ZIP directory count/byte budget exceeded')
    if start + size != end_record or start > file_size:
        raise PublicationDownloadError('Noncanonical ZIP central-directory range')
    stream.seek(0)
    return entries


_WINDOWS_RESERVED = {'CON', 'PRN', 'AUX', 'NUL'} | {
    kind + str(number) for kind in ('COM', 'LPT') for number in range(1, 10)
}


def _member_parts(info):
    name = info.filename
    if not isinstance(name, str) or name != info.orig_filename or not name or len(name) > 4096:
        raise PublicationDownloadError('Invalid ZIP member name')
    if '\\' in name or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise PublicationDownloadError('Nonportable ZIP member name')
    canonical = name[:-1] if info.is_dir() else name
    relative = PurePosixPath(canonical)
    if not canonical or relative.is_absolute() or relative.as_posix() != canonical:
        raise PublicationDownloadError('Noncanonical ZIP member path')
    for part in relative.parts:
        if part in ('.', '..') or part[-1:] in ('.', ' ') or any(char in part for char in '<>:"|?*'):
            raise PublicationDownloadError('Unsafe ZIP member path component')
        if part.split('.', 1)[0].upper() in _WINDOWS_RESERVED or len(part.encode('utf8')) > 255:
            raise PublicationDownloadError('Nonportable ZIP member path component')
    mode = stat.S_IFMT(info.external_attr >> 16)
    if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or (mode == stat.S_IFDIR and not info.is_dir()) or (mode == stat.S_IFREG and info.is_dir()):
        raise PublicationDownloadError('ZIP links or special files are unsupported')
    if info.flag_bits & 1:
        raise PublicationDownloadError('Encrypted ZIP members are unsupported')
    return relative.parts


def _directory(root, parts):
    current = root
    for part in parts:
        current = current / part
        try:
            current.mkdir()
        except FileExistsError:
            pass
        if current.is_symlink() or (hasattr(current, 'is_junction') and current.is_junction()) or not current.is_dir():
            raise PublicationDownloadError('Extraction parent is not an owned directory')
        if not current.resolve().is_relative_to(root):
            raise PublicationDownloadError('Extraction parent escaped destination')
    return current


def extract_zip(archive, destination, *, max_entries=MAX_ZIP_ENTRIES,
                max_member_bytes=MAX_MEMBER_BYTES, max_total_bytes=MAX_EXPANDED_BYTES):
    """Extract a fresh, canonical, bounded publication ZIP using streamed reads."""
    _limit(max_entries, MAX_ZIP_ENTRIES, 'entry')
    _limit(max_member_bytes, MAX_MEMBER_BYTES, 'member')
    _limit(max_total_bytes, MAX_EXPANDED_BYTES, 'expanded')
    archive, destination = Path(archive), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise PublicationDownloadError('Fresh extraction destination required')
    destination.mkdir()
    root = destination.resolve()
    members, total_written = {}, 0
    with archive.open('rb') as stream:
        before = os.fstat(stream.fileno())
        _regular(archive, before, MAX_DOWNLOAD_BYTES)
        expected_entries = _zip_directory_bound(stream, before.st_size, max_entries)
        with zipfile.ZipFile(stream) as packed:
            entries = packed.infolist()
            if len(entries) != expected_entries:
                raise PublicationDownloadError('ZIP directory entry count differs')
            namespace, names, declared_total = {}, set(), 0
            admitted = []
            for info in entries:
                parts = _member_parts(info)
                name = '/'.join(parts)
                if name in names:
                    raise PublicationDownloadError('Duplicate ZIP member')
                names.add(name)
                if info.file_size < 0 or info.file_size > max_member_bytes or info.compress_size > before.st_size:
                    raise PublicationDownloadError('ZIP member byte budget exceeded')
                if info.is_dir() and info.file_size:
                    raise PublicationDownloadError('ZIP directory has payload')
                declared_total += info.file_size
                if declared_total > max_total_bytes:
                    raise PublicationDownloadError('ZIP expanded byte budget exceeded')
                for index in range(1, len(parts) + 1):
                    prefix = '/'.join(parts[:index])
                    key = unicodedata.normalize('NFC', prefix).casefold()
                    directory = index < len(parts) or info.is_dir()
                    previous = namespace.get(key)
                    if previous is not None and (previous[0] != prefix or not previous[1] or not directory):
                        raise PublicationDownloadError('ZIP path alias or file/directory conflict')
                    namespace[key] = (prefix, directory)
                admitted.append((info, parts))
            for info, parts in admitted:
                if info.is_dir():
                    _directory(root, parts)
                    continue
                parent = _directory(root, parts[:-1])
                target = parent / parts[-1]
                digest, count = hashlib.sha256(), 0
                with packed.open(info, 'r') as source, target.open('xb') as output:
                    while True:
                        requested = min(CHUNK_BYTES, info.file_size - count + 1)
                        raw = source.read(requested)
                        if not isinstance(raw, bytes) or len(raw) > requested:
                            raise PublicationDownloadError('ZIP stream violated bounded read contract')
                        if not raw:
                            break
                        count += len(raw)
                        total_written += len(raw)
                        if count > info.file_size or count > max_member_bytes or total_written > max_total_bytes:
                            raise PublicationDownloadError('Actual ZIP output exceeds declared byte budget')
                        if output.write(raw) != len(raw):
                            raise PublicationDownloadError('Short extracted-file write')
                        digest.update(raw)
                if count != info.file_size:
                    raise PublicationDownloadError('Extracted bytes differ from ZIP metadata')
                members['/'.join(parts)] = {'bytes': count, 'sha256': digest.hexdigest()}
        after = os.fstat(stream.fileno())
    if _identity(before) != _identity(after):
        raise PublicationDownloadError('ZIP changed during extraction')
    _confirm_path(archive, after, MAX_DOWNLOAD_BYTES)
    return {'entries': len(entries), 'files': len(members), 'uncompressedBytes': total_written, 'members': members}
