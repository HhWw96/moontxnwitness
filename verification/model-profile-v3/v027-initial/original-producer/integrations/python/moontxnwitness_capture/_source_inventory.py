"""Exact installed presence source bytes, not shim hashes or authentication."""
from pathlib import Path
import hashlib
import os
import stat

SOURCE_FILES = ('__init__.py', 'capture.py', '_provenance.py', '_column_profile.py',
                '_initialization_guard.py', '_source_inventory.py', 'presence.py')


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def implementation_bindings():
    """Hash bounded package sources at call time; no experiment lookup/import.

    Receipts call this before and after execution. This detects changed source
    files; it does not authenticate observations or prove loaded bytecode against
    an administrator changing files. Source-stripped installs cannot emit this
    evidence and raise instead of substituting an experiment shim's digest.
    """
    root = Path(__file__).resolve().parent
    result = {}
    for name in SOURCE_FILES:
        path = root / name
        if path.is_symlink():
            raise ValueError('Regular installed source required')
        digest, size = hashlib.sha256(), 0
        with path.open('rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > 1024 * 1024:
                raise ValueError('Installed source exceeds evidence bound')
            while raw := stream.read(min(65536, 1024 * 1024 - size + 1)):
                size += len(raw)
                if size > 1024 * 1024:
                    raise ValueError('Installed source grew beyond evidence bound')
                digest.update(raw)
            after = os.fstat(stream.fileno())
        with path.open('rb') as second:
            reopened = os.fstat(second.fileno())
        current = path.stat()
        # Windows Python 3.12 exposes ctime differently through path stat and
        # fstat. Compare ctime only within descriptor APIs, never across them.
        if (path.is_symlink() or _identity(before) != _identity(after) or _identity(after) != _identity(reopened)
                or not stat.S_ISREG(current.st_mode) or size != after.st_size
                or (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise ValueError('Installed source changed while hashing')
        result['moontxnwitness_capture/' + name] = {'bytes': size, 'sha256': digest.hexdigest()}
    return result
