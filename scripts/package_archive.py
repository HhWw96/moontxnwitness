"""Bounded, deterministic ZIP output for source and portable distribution."""
import hashlib
import zipfile
from pathlib import Path

CHUNK_BYTES = 64 * 1024


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        while chunk := source.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def write_archive(root, files, path, prefix, private_values):
    root, path = Path(root), Path(path)
    private = tuple(value.encode('utf8') for value in private_values if value)
    overlap = max((len(value) - 1 for value in private), default=0)
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as output:
        for relative in sorted(files):
            scan = relative.endswith(('.mjs', '.cjs', '.json', '.mbt', '.md', '.mbti', '.txt'))
            info = zipfile.ZipInfo(prefix + '/' + relative, date_time=(2026, 10, 10, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            # Python 3.12's explicit ZipInfo streaming path uses this field.
            info._compresslevel = 9
            info.external_attr = (0o100644 << 16)
            tail = b''
            with (root / relative).open('rb') as source, output.open(info, 'w', force_zip64=True) as target:
                while chunk := source.read(CHUNK_BYTES):
                    if scan:
                        window = tail + chunk
                        assert not any(value in window for value in private), 'Local path found in ' + relative
                        tail = window[-overlap:] if overlap else b''
                    target.write(chunk)
    with zipfile.ZipFile(path) as built:
        assert built.testzip() is None, 'ZIP integrity failure'
    return {'file': path.name, 'bytes': path.stat().st_size,
            'sha256': sha256(path), 'files': len(files)}
