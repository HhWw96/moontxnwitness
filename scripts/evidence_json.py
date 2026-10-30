"""Bounded JSON receipt IO, with optional deterministic gzip storage."""
from __future__ import annotations
import gzip
import io
import json
from pathlib import Path

MAX_RECEIPT_BYTES = 16 * 1024 * 1024


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate receipt field")
        result[key] = value
    return result


def load_receipt(path):
    path = Path(path)
    if path.stat().st_size > MAX_RECEIPT_BYTES:
        raise ValueError("Receipt input budget exceeded")
    raw = path.read_bytes()
    if path.suffix == ".gz":
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            raw = stream.read(MAX_RECEIPT_BYTES + 1)
    if len(raw) > MAX_RECEIPT_BYTES:
        raise ValueError("Receipt expansion budget exceeded")
    return json.loads(raw.decode("utf8"), object_pairs_hook=_object)


def write_compressed_receipt(path, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf8")
    if len(raw) > MAX_RECEIPT_BYTES:
        raise ValueError("Receipt expansion budget exceeded")
    Path(path).write_bytes(gzip.compress(raw, mtime=0))
