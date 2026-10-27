"""Bounded, synchronized JSONL for unaccepted source carriers; not traceSchema3."""
import hashlib
import json
import os
from pathlib import Path
import threading
from .capture import CaptureSession, _Budget


class _Encoder:
    _value = CaptureSession._value


class SourceSink:
    def __init__(self, path, *, max_record_bytes=128 * 1024, max_total_bytes=16 * 1024 * 1024):
        if (type(max_record_bytes) is not int or not 256 <= max_record_bytes <= 128 * 1024
                or type(max_total_bytes) is not int or not max_record_bytes <= max_total_bytes <= 16 * 1024 * 1024):
            raise ValueError("Source budgets exceed hard record/total bounds")
        self.path, self._file = Path(path), Path(path).open("xb")
        self._lock, self._digest = threading.RLock(), hashlib.sha256()
        self.count = self.size = 0
        self.max_record, self.max_total = max_record_bytes, max_total_bytes
        self.failed = self.closed = False
        self.append({"kind": "header", "sourceSchema": "orm-source-draft/2", "controlSchema": "orm-control-query/1", "coreProofAccepted": False})

    def preview(self, record):
        if "sourceSeq" in record:
            raise ValueError("sourceSeq is assigned only by the journal")
        value = _Encoder()._value({"sourceSeq": self.count + 1, **record}, _Budget(4096, self.max_record))
        raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        if len(raw) > self.max_record or len(raw) > self.max_total - self.size:
            raise ValueError("Aggregate source journal budget exhausted")
        return raw

    def append(self, record):
        with self._lock:
            if self.closed or self.failed:
                raise ValueError("Source journal is not writable")
            try:
                if self.count >= 16384 or self.count == 16383 and record.get("kind") != "seal":
                    raise ValueError("Source record count budget exhausted")
                raw = self.preview(record)
                written = self._file.write(raw)
                if written != len(raw):
                    raise OSError("Short source journal write")
                self._file.flush(); os.fsync(self._file.fileno())
                self._digest.update(raw); self.size += len(raw); self.count += 1
                return self.count
            except BaseException:
                self.failed = True
                raise

    def close(self):
        with self._lock:
            if not self.closed:
                try:
                    if not self.failed:
                        self.append({"kind": "seal", "prefixSha256": self._digest.hexdigest(), "sourceRecords": self.count})
                finally:
                    self._file.close(); self.closed = True
            return {"sourceSchema": "orm-source-draft/2", "storageSealed": self.closed and not self.failed,
                "records": self.count, "bytes": self.size, "sha256": self._digest.hexdigest(),
                "coreProofAccepted": False, "completeCapture": False}


def verify(path):
    digest, count, total, sealed = hashlib.sha256(), 0, 0, False
    with Path(path).open("rb") as file:
        while True:
            raw = file.readline(128 * 1024 + 1)
            if not raw:
                break
            if sealed or len(raw) > 128 * 1024 or not raw.endswith(b"\n"):
                raise ValueError("Partial/oversized/trailing source record")
            record = json.loads(raw)
            count += 1; total += len(raw)
            if count == 1 and (record.get("kind") != "header" or record.get("sourceSchema") != "orm-source-draft/2" or record.get("controlSchema") != "orm-control-query/1" or record.get("coreProofAccepted") is not False):
                raise ValueError("Explicit unaccepted source header required")
            if record.get("kind") not in ("header", "control-query", "installation", "source-batch", "source-gap", "final-effect-ledger", "seal"):
                raise ValueError("Unknown source observation kind")
            if record["sourceSeq"] != count or count > 16384 or total > 16 * 1024 * 1024:
                raise ValueError("Invalid source ordering/budget")
            if record.get("kind") == "seal":
                if record.get("prefixSha256") != digest.hexdigest() or record.get("sourceRecords") != count - 1:
                    raise ValueError("Source prefix binding changed")
                sealed = True
            digest.update(raw)
    if not sealed:
        raise ValueError("Source observations are not sealed")
    return {"records": count, "bytes": total, "sha256": digest.hexdigest(), "coreProofAccepted": False}
