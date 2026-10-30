"""Receipt compression preserves every field and rejects ambiguous or oversized input."""
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from evidence_json import load_receipt, write_compressed_receipt


class EvidenceJsonTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)

    def test_compressed_roundtrip_keeps_full_bindings(self):
        value = {"testedFileSha256Before": {"a": "abc"}, "testedFileSha256After": {"a": "abc"}, "passed": True}
        a, b = self.root / "a.json.gz", self.root / "b.json.gz"
        write_compressed_receipt(a, value)
        write_compressed_receipt(b, value)
        self.assertEqual(a.read_bytes(), b.read_bytes())
        self.assertEqual(load_receipt(a), value)

    def test_plain_compatibility_and_duplicate_field_refusal(self):
        p = self.root / "a.json"
        p.write_text('{"passed":true}', encoding="utf8")
        self.assertEqual(load_receipt(p), {"passed": True})
        for suffix, data in ((".json", b'{"passed":true,"passed":false}'), (".json.gz", gzip.compress(b'{"passed":true,"passed":false}'))):
            q = self.root / ("bad" + suffix)
            q.write_bytes(data)
            with self.assertRaises(ValueError):
                load_receipt(q)

    def test_corrupt_and_truncated_gzip_refused(self):
        for raw in (b"bad", gzip.compress(b"{}")[0:-3]):
            p = self.root / "bad.json.gz"
            p.write_bytes(raw)
            with self.assertRaises((ValueError, OSError, EOFError)):
                load_receipt(p)

    def test_expansion_and_plain_input_budgets(self):
        p = self.root / "large.json.gz"
        p.write_bytes(gzip.compress(b'"' + b'x' * 2000 + b'"'))
        with patch("evidence_json.MAX_RECEIPT_BYTES", 1024):
            with self.assertRaises(ValueError):
                load_receipt(p)
            with self.assertRaises(ValueError):
                write_compressed_receipt(p, "x" * 2000)
        q = self.root / "large.json"
        q.write_bytes(b" " * 2000)
        with patch("evidence_json.MAX_RECEIPT_BYTES", 1024):
            with self.assertRaises(ValueError):
                load_receipt(q)


if __name__ == "__main__":
    unittest.main()
