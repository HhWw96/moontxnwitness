"""Fault tests for independent comparison accounting; not SDK executions."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest


BASE = Path(__file__).resolve().parent


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, BASE / file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


COMPARE = load("relation_comparison_fault_tests", "relation-models-compare.py")
ORACLE = load("relation_comparison_reference", "relation-models-oracle.py")
GENERATOR = load("relation_comparison_generator", "relation-models-corpus.py")


def fixture(index=0):
    case = GENERATOR.generate(index, COMPARE.SEED)
    options = COMPARE.canonical_options(case)
    row = {"id": case["id"], "verified": True, "options": options,
           "sourceSha256": COMPARE.sha(COMPARE.compact(case["source"]).encode()),
           "optionsSha256": COMPARE.sha(COMPARE.compact(options).encode()),
           "report": {"format": "moontxnwitness-relation-model-composition/v4",
                      "schemaVersion": 4, "referenceCommit": COMPARE.REFERENCE_COMMIT,
                      "semanticContract": "relation-predicate-models/v1",
                      "models": [{"model": model, "status": "unknown", "rules": []} for model in ORACLE.MODELS]}}
    return case, row


def model_row(row, model):
    return next(item for item in row["report"]["models"] if item["model"] == model)


def supply_certificate(row, model, certificate):
    model_row(row, model).update(status="checked-compatible", rules=[{
        "rule": "synthetic-accounting-certificate", "status": "checked-compatible", "evidence": {"certificate": certificate}}])


def production_prefix(case, model):
    original = ORACLE.analyze(case["source"], model, case["options"])["certificate"]
    program = ORACLE.Program(ORACLE.decode(case["source"]))
    assert original["kind"] in ("snapshot-prefix", "committed-query-prefixes")
    programs = []
    for entry in original["programs"]:
        if original["kind"] == "snapshot-prefix":
            programs.append({"transaction": entry["transaction"], "snapshotPrefix": entry["snapshot"]})
        else:
            indices = [i for i, event in enumerate(program.txs[entry["transaction"]]["ops"])
                       if event["kind"] in ("row_read", "row_write")]
            programs.append({"transaction": entry["transaction"], "statementPrefixes": [
                {"actionIndex": i, "prefix": cut} for i, cut in zip(indices, entry["prefixes"])]})
    return {"kind": "original-fixed-snapshot" if original["kind"] == "snapshot-prefix" else "original-committed-query-prefixes",
            "commitOrder": original["commitOrder"], "programs": programs}


class AccountingFaults(unittest.TestCase):
    def test_unknown_is_not_counted_as_determinate_agreement(self):
        case, row = fixture()
        _, _, counts, failures = COMPARE.compare_case(case, row, ORACLE)
        self.assertFalse(failures)
        self.assertEqual(counts["conservative-sdk-unknown"], 14)
        self.assertEqual(counts["determinate-agreement"], 0)

    def test_pending_independent_model_never_becomes_model_parity(self):
        case, row = fixture(2)
        model_row(row, "repeatable-read")["status"] = "refuted"
        items, _, _, failures = COMPARE.compare_case(case, row, ORACLE)
        result = next(item for item in items if item["model"] == "repeatable-read")
        self.assertEqual(result["referenceStatus"], "pending")
        self.assertEqual(result["category"], "independent-reference-undecided")
        self.assertFalse(failures)

    def test_known_serial_program_cannot_be_accepted_as_an_sdk_refutation(self):
        case, row = fixture()
        model_row(row, "serializable")["status"] = "refuted"
        _, _, counts, failures = COMPARE.compare_case(case, row, ORACLE)
        self.assertEqual(counts["contradiction"], 1)
        self.assertEqual(failures[0]["kind"], "sdk-refutation-conflicts-with-independent-certificate")

    def test_original_serial_certificate_is_replayed(self):
        case, row = fixture()
        supply_certificate(row, "serializable", {"kind": "original-serial", "commitOrder": ["A", "B"]})
        _, _, counts, failures = COMPARE.compare_case(case, row, ORACLE)
        self.assertEqual(counts["model-certificate-replays"], 1)
        self.assertFalse(failures)

    def test_serial_certificate_cannot_substitute_a_wrong_order(self):
        case, row = fixture()
        supply_certificate(row, "serializable", {"kind": "original-serial", "commitOrder": ["B", "A"]})
        _, _, _, failures = COMPARE.compare_case(case, row, ORACLE)
        self.assertEqual(failures[0]["kind"], "independent-certificate-replay-failed")

    def test_rc_prefix_certificate_keeps_actual_statement_positions(self):
        case, row = fixture(1)
        certificate = production_prefix(case, "read-committed")
        supply_certificate(row, "read-committed", certificate)
        _, _, counts, failures = COMPARE.compare_case(case, row, ORACLE)
        self.assertEqual(counts["model-certificate-replays"], 1)
        self.assertFalse(failures)
        certificate["programs"][0]["statementPrefixes"][0]["actionIndex"] = 999
        with self.assertRaisesRegex(ValueError, "statement positions"):
            COMPARE.compare_case(case, row, ORACLE)

    def test_snapshot_certificate_is_replayed(self):
        case, row = fixture(2)
        supply_certificate(row, "snapshot-isolation", production_prefix(case, "snapshot-isolation"))
        _, _, counts, failures = COMPARE.compare_case(case, row, ORACLE)
        self.assertEqual(counts["model-certificate-replays"], 1)
        self.assertFalse(failures)

    def test_nonserial_cv_certificate_is_only_an_rc_premise_check(self):
        case, row = fixture(2)
        # Build a valid operational RC prefix certificate for the SI skew.
        certificate = production_prefix(case, "snapshot-isolation")
        program = ORACLE.Program(ORACLE.decode(case["source"]))
        certificate["kind"] = "original-committed-query-prefixes"
        for entry in certificate["programs"]:
            prefix = entry.pop("snapshotPrefix")
            entry["statementPrefixes"] = [{"actionIndex": i, "prefix": prefix}
                                          for i, event in enumerate(program.txs[entry["transaction"]]["ops"])
                                          if event["kind"] in ("row_read", "row_write")]
        supply_certificate(row, "consistent-view", certificate)
        items, _, counts, failures = COMPARE.compare_case(case, row, ORACLE)
        item = next(item for item in items if item["model"] == "consistent-view")
        self.assertEqual(item["independentCertificateScope"], "semantic-premises-only")
        self.assertEqual(counts["premise-certificate-replays"], 1)
        self.assertEqual(counts["determinate-agreement"], 0)
        self.assertFalse(failures)

    def test_original_source_binding_cannot_be_omitted_or_swapped(self):
        case, row = fixture()
        for value in [None, "0" * 64]:
            altered = copy.deepcopy(row)
            altered["sourceSha256"] = value
            with self.assertRaisesRegex(ValueError, "Original source"):
                COMPARE.compare_case(case, altered, ORACLE)

    def test_independent_options_and_their_digest_are_both_bound(self):
        case, row = fixture()
        altered = copy.deepcopy(row)
        altered["options"]["maxStates"] = 0
        with self.assertRaisesRegex(ValueError, "supplied options"):
            COMPARE.compare_case(case, altered, ORACLE)
        row["optionsSha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "options digest"):
            COMPARE.compare_case(case, row, ORACLE)

    def test_missing_or_duplicate_model_is_rejected(self):
        case, row = fixture()
        row["report"]["models"][1] = copy.deepcopy(row["report"]["models"][0])
        with self.assertRaisesRegex(ValueError, "model universe"):
            COMPARE.compare_case(case, row, ORACLE)

    def test_failed_sdk_recomputation_is_not_a_comparison_success(self):
        case, row = fixture()
        row["verified"] = False
        with self.assertRaisesRegex(ValueError, "recomputation failed"):
            COMPARE.compare_case(case, row, ORACLE)

    def test_another_history_identity_is_not_accepted(self):
        case, row = fixture()
        row["id"] = "another-history"
        with self.assertRaisesRegex(ValueError, "identity differs"):
            COMPARE.compare_case(case, row, ORACLE)

    def test_json_duplicate_fields_and_non_json_numbers_are_refused(self):
        with self.assertRaisesRegex(ValueError, "Duplicate JSON field"):
            COMPARE.decode_json('{"verified":false,"verified":true}')
        with self.assertRaisesRegex(ValueError, "Non-JSON numeric"):
            COMPARE.decode_json('{"maxStates":NaN}')

    def test_other_reference_definition_is_not_accepted(self):
        case, row = fixture()
        row["report"]["referenceCommit"] = "another-definition"
        with self.assertRaisesRegex(ValueError, "report identity"):
            COMPARE.compare_case(case, row, ORACLE)


if __name__ == "__main__":
    unittest.main()
