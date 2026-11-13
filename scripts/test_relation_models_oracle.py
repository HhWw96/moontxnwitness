"""Independent source-program certificates, including legal weak histories."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

PATH = Path(__file__).with_name("relation-models-oracle.py")
SPEC = importlib.util.spec_from_file_location("independent_relation_models_oracle", PATH)
ORACLE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ORACLE
SPEC.loader.exec_module(ORACLE)


def row(key="1", version="v0", value="0", enabled=True, label="same"):
    return {"key": key, "version": version, "values": {"value": value, "enabled": enabled, "label": label}}


def begin(tx, connection=None):
    return {"kind": "begin", "tx": tx, "connection": connection or tx}


def commit(tx):
    return [{"kind": "commit_request", "tx": tx}, {"kind": "commit_ok", "tx": tx}]


def read(tx, rows, predicate=None, complete=True):
    return {"kind": "row_read", "tx": tx, "relation": "items", "predicate": predicate if predicate is not None else [{"column": "id", "op": "eq", "value": "1"}], "rows": rows, "complete": complete}


def write(tx, after, predecessor="v0", action="update"):
    return {"kind": "row_write", "tx": tx, "relation": "items", "key": after["key"], "action": action, "version": after["version"], "predecessor": predecessor, "values": after["values"]}


def trace(body, initial=None):
    if initial is None:
        initial = [row()]
    return {"traceSchema": 3, "dataModel": "relation-set-v1", "clockDomain": "independent-relation-test",
            "relationSchema": {"items": {"primaryKey": "id", "columns": {"id": "int64", "value": "int64", "enabled": "bool", "label": "text"}}},
            "scope": {"exclusiveWriters": True, "completeSnapshotTables": ["items"]}, "gaps": [],
            "events": [dict(event, seq=i + 1, time=i) for i, event in enumerate([{"kind": "snapshot", "consistent": True, "initial": {"items": initial}}, *body])]}


def simple():
    return trace([begin("A"), read("A", [row()]), write("A", row(version="v1", value="1")), read("A", [row(version="v1", value="1")]), *commit("A")])


def reread():
    return trace([begin("R"), read("R", [row()]), begin("W"), write("W", row(version="v1", value="1")), *commit("W"), read("R", [row(version="v1", value="1")]), *commit("R")])


class SourcePrograms(unittest.TestCase):
    def test_single_serial_program_supplies_every_model_a_positive_certificate(self):
        source = simple()
        original = copy.deepcopy(source)
        for model in ORACLE.MODELS:
            with self.subTest(model=model):
                result = ORACLE.analyze(source, model)
                self.assertEqual(result["status"], "checked-compatible", result)
                self.assertTrue(ORACLE.verify_certificate(source, model, result["certificate"])["valid"])
        self.assertEqual(source, original)

    def test_rc_external_rereads_have_a_nonserial_certificate(self):
        result = ORACLE.analyze(reread(), "read-committed")
        self.assertEqual(result["status"], "checked-compatible", result)
        self.assertEqual(result["certificate"]["kind"], "committed-query-prefixes")
        self.assertFalse(result["exactDecision"])
        self.assertTrue(ORACLE.verify_certificate(reread(), "read-committed", result["certificate"])["valid"])
        self.assertEqual(ORACLE.analyze(reread(), "serializable")["status"], "refuted")

    def test_missing_si_certificate_is_not_a_fixed_model_refutation(self):
        result = ORACLE.analyze(reread(), "snapshot-isolation")
        self.assertEqual(result["status"], "unknown", result)
        self.assertEqual(result["reason"], "no-sufficient-certificate-found")
        self.assertFalse(result["supportsExhaustiveRefutation"])

    def test_si_write_skew_has_a_snapshot_certificate_but_no_serial_order(self):
        a0, b0 = row("1", "a0"), row("2", "b0")
        a1, b1 = row("1", "a1", "1"), row("2", "b1", "1")
        source = trace([begin("A"), begin("B"), read("A", [b0], [{"column": "id", "op": "eq", "value": "2"}]), read("B", [a0]), write("A", a1, "a0"), write("B", b1, "b0"), *commit("A"), *commit("B")], [a0, b0])
        result = ORACLE.analyze(source, "snapshot-isolation")
        self.assertEqual(result["status"], "checked-compatible", result)
        self.assertEqual(result["certificate"]["kind"], "snapshot-prefix")
        self.assertTrue(ORACLE.verify_certificate(source, "snapshot-isolation", result["certificate"])["valid"])
        self.assertEqual(ORACLE.analyze(source, "serializable")["status"], "refuted")
        # No serial order alone proves an RR violation. This partial reference
        # does not implement the model-specific mixed item/predicate criterion.
        self.assertEqual(ORACLE.analyze(source, "repeatable-read")["status"], "pending")

    def test_rr_phantom_is_not_rejected_by_a_serial_only_reference(self):
        fresh = row("1", "inserted", "1")
        predicate = [{"column": "enabled", "op": "eq", "value": True}]
        source = trace([begin("R"), read("R", [], predicate), begin("W"), write("W", fresh, None, "insert"), *commit("W"), read("R", [fresh], predicate), *commit("R")], [])
        self.assertEqual(ORACLE.analyze(source, "serializable")["status"], "refuted")
        self.assertEqual(ORACLE.analyze(source, "repeatable-read")["status"], "pending")
        self.assertEqual(ORACLE.analyze(source, "read-committed")["status"], "checked-compatible")

    def test_mixed_item_predicate_cycle_is_not_claimed_as_independent_rr_parity(self):
        a0, c0 = row("1", "a0", enabled=False), row("3", "c0", enabled=False)
        b1 = row("1", "b1", "1", enabled=False)
        c1 = row("3", "c1", "1", enabled=False)
        inserted = row("4", "c2", "1", enabled=True)
        point3 = [{"column": "id", "op": "eq", "value": "3"}]
        enabled = [{"column": "enabled", "op": "eq", "value": True}]
        source = trace([begin("A"), begin("B"), begin("C"), write("C", c1, "c0"),
                        read("A", [a0]), read("B", [], enabled), write("B", b1, "a0"),
                        write("C", inserted, None, "insert"), read("A", [c1], point3),
                        *commit("A"), *commit("B"), *commit("C")], [a0, c0])
        # Original programs require A before B, B before C and C before A.
        # RC has a committed-query-prefix certificate; the dedicated Adya RR
        # mixed-cycle decision belongs to the production/category checker.
        self.assertEqual(ORACLE.analyze(source, "serializable")["status"], "refuted")
        self.assertEqual(ORACLE.analyze(source, "read-committed")["status"], "checked-compatible")
        rr = ORACLE.analyze(source, "repeatable-read")
        self.assertEqual(rr["status"], "pending", rr)
        self.assertFalse(rr["exactDecision"])
        self.assertFalse(rr["supportsExhaustiveRefutation"])

    def test_stale_real_time_read_distinguishes_serial_from_strict(self):
        source = trace([begin("W"), write("W", row(version="v1", value="1")), *commit("W"), begin("R"), read("R", [row()]), *commit("R")])
        self.assertEqual(ORACLE.analyze(source, "serializable")["status"], "checked-compatible")
        self.assertEqual(ORACLE.analyze(source, "strict-serializable")["status"], "refuted")
        options = {"clients": [{"id": "logical-client", "transactions": ["W", "R"]}], "clientsComplete": True}
        self.assertEqual(ORACLE.analyze(source, "strong-session-serializable", options)["status"], "refuted")

    def test_missing_clock_prevents_strict_compatibility(self):
        source = trace([begin("A"), read("A", [row()]), *commit("A"), begin("B"), read("B", [row()]), *commit("B")])
        source.pop("clockDomain")
        self.assertEqual(ORACLE.analyze(source, "strict-serializable")["status"], "unknown")
        self.assertEqual(ORACLE.analyze(source, "serializable")["status"], "checked-compatible")

    def test_connection_pool_reuse_does_not_supply_logical_session(self):
        source = trace([begin("A", "pooled"), read("A", [row()]), *commit("A"), begin("B", "pooled"), read("B", [row()]), *commit("B")])
        result = ORACLE.analyze(source, "strong-session-serializable")
        self.assertEqual(result["status"], "unknown", result)
        opts = {"clients": [{"id": "user-session", "transactions": ["A", "B"]}], "clientsComplete": True}
        self.assertEqual(ORACLE.analyze(source, "strong-session-serializable", opts)["status"], "checked-compatible")

    def test_data_refutation_survives_missing_strong_order_facts(self):
        result = ORACLE.analyze(reread(), "strong-session-serializable")
        self.assertEqual(result["status"], "refuted", result)

    def test_savepoint_rollback_keeps_delivered_reads_and_releases_only_scope(self):
        temp, final = row(version="temp", value="1"), row(version="final", value="2")
        source = trace([begin("A"), {"kind": "savepoint", "tx": "A", "name": "s", "instance": "s1"}, write("A", temp), read("A", [temp]), {"kind": "rollback_to", "tx": "A", "instance": "s1"}, read("A", [row()]), {"kind": "savepoint", "tx": "A", "name": "s", "instance": "s2"}, write("A", final), {"kind": "release", "tx": "A", "instance": "s2"}, read("A", [final]), *commit("A")])
        result = ORACLE.analyze(source)
        self.assertEqual(result["status"], "checked-compatible", result)
        altered = copy.deepcopy(source)
        next(e for e in altered["events"] if e["kind"] == "row_read")["rows"] = [row()]
        self.assertEqual(ORACLE.analyze(altered)["status"], "refuted")

    def test_release_does_not_commit(self):
        source = trace([begin("A"), {"kind": "savepoint", "tx": "A", "name": "s", "instance": "s1"}, {"kind": "release", "tx": "A", "instance": "s1"}])
        self.assertEqual(ORACLE.analyze(source)["status"], "unknown")

    def test_hidden_duplicate_savepoint_name_is_not_resolved_by_instance(self):
        source = trace([begin("A"), {"kind": "savepoint", "tx": "A", "name": "s", "instance": "s1"}, {"kind": "savepoint", "tx": "A", "name": "s", "instance": "s2"}, {"kind": "rollback_to", "tx": "A", "instance": "s1"}, *commit("A")])
        self.assertEqual(ORACLE.analyze(source)["status"], "invalid")

    def test_insert_delete_reinsert_preserves_tombstone_predecessor(self):
        inserted = row(version="inserted")
        deleted = {"key": "1", "version": "deleted", "values": None}
        restored = row(version="restored", value="2")
        source = trace([begin("A"), write("A", inserted, None, "insert"), read("A", [inserted]), write("A", deleted, "inserted", "delete"), read("A", []), write("A", restored, "deleted", "insert"), read("A", [restored]), *commit("A")], [])
        self.assertEqual(ORACLE.analyze(source)["status"], "checked-compatible")

    def test_complete_empty_queries_and_cross_predicate_updates(self):
        zero, one = row(), row(version="v1", value="1")
        p0 = [{"column": "value", "op": "eq", "value": "0"}]
        p1 = [{"column": "value", "op": "eq", "value": "1"}]
        source = trace([begin("A"), read("A", [zero], p0), write("A", one), read("A", [], p0), read("A", [one], p1), *commit("A")])
        self.assertEqual(ORACLE.analyze(source)["status"], "checked-compatible")

    def test_typed_int64_bool_text_and_and_range_predicates(self):
        high = row("1", "high", "9223372036854775807", True, "😀")
        low = row("2", "low", "-9223372036854775808", False, "\ue000")
        predicate = [{"column": "value", "op": "gt", "value": "9007199254740992"}, {"column": "enabled", "op": "eq", "value": True}, {"column": "label", "op": "gt", "value": "\ue000"}]
        source = trace([begin("A"), read("A", [high], predicate), *commit("A")], [high, low])
        self.assertEqual(ORACLE.analyze(source)["status"], "checked-compatible")

    def test_unproved_missing_row_source_is_a_gap_not_g1a(self):
        source = trace([begin("A"), read("A", [row(version="unobserved")]), *commit("A")])
        result = ORACLE.analyze(source, "read-committed")
        self.assertEqual(result["status"], "unknown", result)
        self.assertNotIn("findings", result)

    def test_aborted_read_is_independent_rc_refutation(self):
        dirty = row(version="dirty", value="1")
        source = trace([begin("W"), write("W", dirty), {"kind": "rollback_ok", "tx": "W"}, begin("R"), read("R", [dirty]), *commit("R")])
        result = ORACLE.analyze(source, "read-committed")
        self.assertEqual(result["status"], "refuted", result)
        self.assertEqual(result["findings"][0]["category"], "G1a")
        self.assertNotEqual(ORACLE.analyze(source, "read-uncommitted")["status"], "refuted")

    def test_intermediate_read_is_g1b_and_does_not_require_global_search(self):
        temporary, final = row(version="temp", value="1"), row(version="final", value="2")
        source = trace([begin("W"), write("W", temporary), write("W", final, "temp"), *commit("W"), begin("R"), read("R", [temporary]), *commit("R")])
        result = ORACLE.analyze(source, "read-committed", {"maxStates": 0})
        self.assertEqual(result["status"], "refuted", result)
        self.assertEqual(result["findings"][0]["category"], "G1b")

    def test_partial_query_cannot_establish_absence(self):
        source = trace([begin("A"), read("A", [], complete=False), *commit("A")])
        self.assertEqual(ORACLE.analyze(source)["status"], "unknown")

    def test_unknown_commit_and_sequence_holes_remain_unknown(self):
        source = simple()
        source["events"][-1]["kind"] = "disconnect"
        self.assertEqual(ORACLE.analyze(source)["status"], "unknown")
        source = simple()
        source["events"] = [e for e in source["events"] if e["seq"] != 3]
        self.assertEqual(ORACLE.analyze(source)["status"], "unknown")

    def test_commit_request_followed_by_unproven_rollback_is_unknown(self):
        source = simple()
        source["events"][-1]["kind"] = "rollback_ok"
        self.assertEqual(ORACLE.analyze(source)["status"], "unknown")

    def test_post_commit_abort_requires_matching_native_response(self):
        for mode in ["tag", "error", "forged"]:
            source = simple()
            request = source["events"][-2]["seq"]
            source["events"][-1]["kind"] = "rollback_ok"
            response = {"request": request, "commandTag": "ROLLBACK"} if mode == "tag" else {"request": request, "sqlstate": "40001", "diagnosticSqlstate": "40001", "transactionStatus": "IDLE"}
            if mode == "forged":
                response = {"request": request, "outcome": "aborted", "sqlstate": "40001"}
            source["events"][-1]["commitResponse"] = response
            self.assertEqual(ORACLE.analyze(source)["status"], "unknown" if mode == "forged" else "checked-compatible")

    def test_no_rc_certificate_can_hide_a_forked_installation_chain(self):
        source = trace([begin("A"), begin("B"), write("A", row(version="a", value="1")), write("B", row(version="b", value="2")), *commit("A"), *commit("B")])
        result = ORACLE.analyze(source, "read-committed")
        self.assertEqual(result["status"], "unknown", result)

    def test_cyclic_source_lineage_is_not_blessed_after_abort(self):
        bad = row(version="self-parent", value="1")
        source = trace([begin("W"), write("W", bad, "self-parent"), {"kind": "rollback_ok", "tx": "W"}, begin("R"), read("R", [row()]), *commit("R")])
        result = ORACLE.analyze(source)
        self.assertEqual(result["status"], "unknown", result)
        self.assertIn("cyclic-write-predecessor-facts", result["gaps"])

    def test_budget_exhaustion_is_unknown_not_refuted(self):
        for opts in [{"maxStates": 0}, {"maxOperationChecks": 0}, {"maxOperationChecks": 1}]:
            result = ORACLE.analyze(reread(), "serializable", opts)
            self.assertEqual(result["status"], "unknown", result)
            self.assertFalse(result["complete"])

    def test_exact_committed_transaction_limit(self):
        body = []
        for i in range(7):
            body += [begin(str(i)), read(str(i), [row()]), *commit(str(i))]
        self.assertEqual(ORACLE.analyze(trace(body))["reason"], "exact-capacity")

    def test_exact_operation_limit(self):
        source = trace([begin("A"), *[read("A", [row()]) for _ in range(129)], *commit("A")])
        self.assertEqual(ORACLE.analyze(source)["reason"], "exact-capacity")

    def test_tampered_certificate_and_independent_budget_are_rejected(self):
        source = reread()
        c = ORACLE.analyze(source, "read-committed")["certificate"]
        self.assertTrue(ORACLE.verify_certificate(source, "read-committed", c)["valid"])
        mutated = copy.deepcopy(c)
        next(p for p in mutated["programs"] if p["transaction"] == "R")["prefixes"] = [0, 0]
        self.assertFalse(ORACLE.verify_certificate(source, "read-committed", mutated)["valid"])
        self.assertFalse(ORACLE.verify_certificate(source, "read-committed", c, {"maxStates": 0})["valid"])
        self.assertFalse(ORACLE.verify_certificate(source, "snapshot-isolation", c)["valid"])

    def test_certificate_universe_and_query_choices_are_exact(self):
        source = reread()
        cert = ORACLE.analyze(source, "read-committed")["certificate"]
        for mutate in [lambda c: c["commitOrder"].append("R"), lambda c: c["programs"].append(copy.deepcopy(c["programs"][0])), lambda c: c["programs"][0]["prefixes"].append(0)]:
            bad = copy.deepcopy(cert)
            mutate(bad)
            self.assertFalse(ORACLE.verify_certificate(source, "read-committed", bad)["valid"])

    def test_verifier_uses_original_row_values_not_certificate_status(self):
        source = simple()
        c = ORACLE.analyze(source)["certificate"]
        changed = copy.deepcopy(source)
        next(e for e in changed["events"] if e["kind"] == "row_read")["rows"][0]["values"]["value"] = "99"
        self.assertFalse(ORACLE.verify_certificate(changed, "serializable", c)["valid"])

    def test_unknown_models_options_duplicate_keys_and_null_are_rejected(self):
        self.assertEqual(ORACLE.analyze(simple(), "postgresql-repeatable-read")["status"], "invalid")
        self.assertEqual(ORACLE.analyze(simple(), options={"maxStates": 100001})["status"], "invalid")
        raw = json.dumps(simple()).replace('"traceSchema": 3', '"traceSchema": 3, "traceSchema": 3')
        self.assertEqual(ORACLE.analyze(raw)["status"], "invalid")
        source = simple()
        source["relationSchema"]["items"]["columns"]["value"] = "nullable-int64"
        self.assertEqual(ORACLE.analyze(source)["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
