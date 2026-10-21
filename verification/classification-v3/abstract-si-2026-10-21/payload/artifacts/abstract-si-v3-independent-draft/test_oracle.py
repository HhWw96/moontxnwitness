"""Author self-tests from preregistered semantic classes, not kernel outputs."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from oracle import analyze, verify_witness, MAX_BYTES


ROOT = Path(__file__).resolve().parent


def op(kind, key, version):
    return {"type": {"r": "read", "w": "write"}.get(kind, kind), "key": key, "version": version}


def tx(name, *ops, status="committed"):
    return {"id": name, "status": status, "ops": list(ops)}


def history(initial=None, transactions=(), orders=None):
    initial = {"x": "x0"} if initial is None else initial
    if orders is None:
        orders = {key: [version] for key, version in initial.items()}
        for transaction in transactions:
            final = {}
            for event in transaction["ops"]:
                if event.get("type") == "write" and event.get("key") in initial:
                    final[event["key"]] = event["version"]
            for key, version in final.items():
                orders[key].append(version)
    return {"schema": 1, "dataModel": "point-register-v1", "complete": True,
        "initial": initial, "versionOrders": orders, "transactions": list(transactions)}


def encode(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def registered_fixtures():
    cases = []

    def add(name, value, si, serial=None):
        cases.append({"id": name, "input": value, "expectedSi": si, "expectedSerial": serial or si})

    yes, no, gap, bad = "satisfiable", "unsatisfiable", "inconclusive", "invalid"
    add("empty-history-zero-budget", history(transactions=()), yes)
    add("initial-point-read", history(transactions=[tx("A", op("r", "x", "x0"))]), yes)
    add("repeated-initial-read", history(transactions=[tx("A", op("r", "x", "x0"), op("r", "x", "x0"))]), yes)
    add("read-only-array-order-not-CO", history(transactions=[tx("Z", op("r", "x", "x0")), tx("A", op("r", "x", "x0"))]), yes)
    add("write-then-own-read", history(transactions=[tx("A", op("w", "x", "x1"), op("r", "x", "x1"))]), yes)
    add("own-intermediate-read-then-overwrite", history(transactions=[tx("A", op("w", "x", "x1"), op("r", "x", "x1"), op("w", "x", "x2"))]), yes)
    add("multi-key-own-overlay", history({"x": "x0", "y": "y0"}, [tx("A", op("w", "x", "x1"), op("r", "y", "y0"), op("w", "y", "y1"), op("r", "x", "x1"), op("r", "y", "y1"))]), yes)
    add("read-write-read", history(transactions=[tx("A", op("r", "x", "x0"), op("w", "x", "x1"), op("r", "x", "x1"))]), yes)
    add("nonrepeatable-read", history(transactions=[tx("A", op("r", "x", "x0"), op("r", "x", "x1")), tx("B", op("w", "x", "x1"))]), no)
    add("read-old-after-own-write", history(transactions=[tx("A", op("w", "x", "x1"), op("r", "x", "x0"))]), no)
    add("wrong-own-intermediate", history(transactions=[tx("A", op("w", "x", "x1"), op("w", "x", "x2"), op("r", "x", "x1"))]), no)
    add("read-own-future-write", history(transactions=[tx("A", op("r", "x", "x1"), op("w", "x", "x1"))]), no)
    add("other-TX-intermediate-read", history(transactions=[tx("A", op("w", "x", "x1"), op("w", "x", "x2")), tx("B", op("r", "x", "x1"))]), no)
    add("fractured-two-key-writer-visibility", history({"x": "x0", "y": "y0"}, [tx("A", op("w", "x", "x1"), op("w", "y", "y1")), tx("B", op("r", "x", "x1"), op("r", "y", "y0"))]), no)
    add("two-key-write-skew", history({"x": "x0", "y": "y0"}, [tx("A", op("r", "x", "x0"), op("r", "y", "y0"), op("w", "x", "x1")), tx("B", op("r", "x", "x0"), op("r", "y", "y0"), op("w", "y", "y1"))]), yes, no)
    add("three-key-write-skew-ring", history({"x": "x0", "y": "y0", "z": "z0"}, [tx("A", op("r", "y", "y0"), op("w", "x", "x1")), tx("B", op("r", "z", "z0"), op("w", "y", "y1")), tx("C", op("r", "x", "x0"), op("w", "z", "z1"))]), yes, no)
    add("same-key-lost-update", history(transactions=[tx("A", op("r", "x", "x0"), op("w", "x", "x1")), tx("B", op("r", "x", "x0"), op("w", "x", "x2"))]), no)
    add("four-TX-long-fork", history({"x": "x0", "y": "y0"}, [tx("A", op("w", "x", "x1")), tx("B", op("w", "y", "y1")), tx("C", op("r", "x", "x1"), op("r", "y", "y0")), tx("D", op("r", "x", "x0"), op("r", "y", "y1"))]), no)
    add("cross-key-factual-write-order-cycle", history({"x": "x0", "y": "y0"}, [tx("A", op("w", "x", "x1"), op("w", "y", "y1")), tx("B", op("w", "x", "x2"), op("w", "y", "y2"))], {"x": ["x0", "x1", "x2"], "y": ["y0", "y2", "y1"]}), no)
    add("two-blind-same-key-writes", history(transactions=[tx("A", op("w", "x", "x1")), tx("B", op("w", "x", "x2"))]), yes)
    add("independent-key-blind-writes", history({"x": "x0", "y": "y0"}, [tx("A", op("w", "x", "x1")), tx("B", op("w", "y", "y1"))]), yes)
    add("reader-of-later-array-writer", history(transactions=[tx("R", op("r", "x", "x1")), tx("W", op("w", "x", "x1"))]), yes)
    add("source-token-reused-on-different-keys", history({"x": "v0", "y": "v0"}, [tx("A", op("w", "x", "v1"), op("w", "y", "v1"), op("r", "x", "v1"), op("r", "y", "v1"))]), yes)
    complete_false = history(); complete_false["complete"] = False
    add("complete-false", complete_false, gap)
    missing_written = history(transactions=[tx("A", op("w", "x", "x1"))]); missing_written["versionOrders"] = {}
    add("missing-written-key-order", missing_written, gap)
    missing_read = history(transactions=[tx("A", op("r", "x", "x0"))]); missing_read["versionOrders"] = {}
    add("missing-read-only-key-order", missing_read, gap)
    add("partial-final-order", history(transactions=[tx("A", op("w", "x", "x1"))], orders={"x": ["x0"]}), gap)
    add("unknown-read-source", history(transactions=[tx("A", op("r", "x", "missing"))]), gap)
    add("unknown-order-source", history(orders={"x": ["x0", "missing"]}), gap)
    add("uninitialized-key", history(transactions=[tx("A", op("r", "y", "y0"))]), gap)
    add("unknown-outcome", history(transactions=[tx("A", op("r", "x", "x0"), status="unknown")]), gap)
    add("aborted-outcome", history(transactions=[tx("A", op("r", "x", "x0"), status="aborted")]), gap)
    add("savepoint-journal", history(transactions=[tx("A", {"type": "savepoint", "name": "s", "instance": "s1"})]), gap)
    for model in ("append-list-v1", "relation-set-v1"):
        value = history(); value["dataModel"] = model
        add(model + "-declined", value, gap)
    add("valid-NUL-version", history({"x": "\0"}, [tx("A", op("r", "x", "\0"))]), yes)
    scalar_256 = "\U0001f680" * 128
    add("supplementary-scalar-256-UTF16", history({"x": scalar_256}, [tx("A", op("r", "x", scalar_256))]), yes)
    add("duplicate-TX-ID", history(transactions=[tx("A"), tx("A")]), bad)
    add("duplicate-producer", history(transactions=[tx("A", op("w", "x", "x1")), tx("B", op("w", "x", "x1"))]), bad)
    add("initial-write-version-collision", history(transactions=[tx("A", op("w", "x", "x0"))]), bad)
    add("duplicate-order-member", history(orders={"x": ["x0", "x0"]}), bad)
    add("nonfinal-write-in-final-order", history(transactions=[tx("A", op("w", "x", "x1"), op("w", "x", "x2"))], orders={"x": ["x0", "x1", "x2"]}), bad)
    add("order-initial-not-first", history(transactions=[tx("A", op("w", "x", "x1"))], orders={"x": ["x1", "x0"]}), bad)
    unknown_field = history(); unknown_field["sessionOrder"] = []
    add("unknown-field", unknown_field, bad)
    add("unpaired-surrogate", history({"x": "\ud800"}), bad)
    add("identity-257-UTF16", history({"x": "a" * 257}), bad)
    add("six-TX-supported", history(transactions=[tx("T" + str(i)) for i in range(6)]), yes)
    add("seven-TX-decline", history(transactions=[tx("T" + str(i)) for i in range(7)]), gap)
    add("128-ops-supported", history(transactions=[tx("A", *[op("r", "x", "x0") for _ in range(128)])]), yes)
    add("129-ops-decline", history(transactions=[tx("A", *[op("r", "x", "x0") for _ in range(129)])]), gap)
    add("128-keys-supported", history({"k" + str(i): "v0" for i in range(128)}), yes)
    add("129-keys-decline", history({"k" + str(i): "v0" for i in range(129)}), gap)
    return cases


FIXTURES = registered_fixtures()


class OracleTests(unittest.TestCase):
    def test_registered_semantic_and_structural_cases(self):
        for fixture in FIXTURES:
            text = encode(fixture["input"])
            original = deepcopy(fixture["input"])
            for model, field in (("si", "expectedSi"), ("serial", "expectedSerial")):
                with self.subTest(case=fixture["id"], model=model):
                    actual = analyze(text, model=model)
                    self.assertEqual(actual["status"], fixture[field], actual)
                    self.assertLessEqual(actual["execution"]["states"], 100_000)
                    self.assertLessEqual(actual["execution"]["semanticChecks"], 1_000_000)
                    if actual["status"] == "satisfiable":
                        self.assertTrue(verify_witness(text, actual["witness"], model=model), actual)
                        if model == "serial":
                            self.assertTrue(verify_witness(text, actual["witness"], model="si"))
                    else:
                        self.assertIsNone(actual["witness"])
            self.assertEqual(fixture["input"], original)

    def test_literal_initial_read_budget_boundary(self):
        text = encode(history(transactions=[tx("A", op("r", "x", "x0"))]))
        for model in ("si", "serial"):
            for states, checks, expected in ((2, 5, "satisfiable"), (1, 5, "inconclusive"),
                    (2, 4, "inconclusive"), (0, 5, "inconclusive"), (2, 0, "inconclusive")):
                with self.subTest(model=model, states=states, checks=checks):
                    result = analyze(text, model=model, max_states=states, max_semantic_checks=checks)
                    self.assertEqual(result["status"], expected, result)
                    self.assertLessEqual(result["execution"]["states"], states)
                    self.assertLessEqual(result["execution"]["semanticChecks"], checks)
                    if expected == "satisfiable":
                        self.assertEqual(result["execution"]["states"], 2)
                        self.assertEqual(result["execution"]["semanticChecks"], 5)
                        self.assertFalse(result["execution"]["budgetExhausted"])
                    else:
                        self.assertTrue(result["execution"]["budgetExhausted"])
                        self.assertFalse(result["execution"]["searchedAllCandidates"])
                        self.assertIsNone(result["witness"])

    def test_empty_execution_needs_no_search_visits(self):
        result = analyze(encode(history()), max_states=0, max_semantic_checks=0)
        self.assertEqual(result["status"], "satisfiable")
        self.assertEqual(result["execution"]["states"], 0)
        self.assertEqual(result["execution"]["semanticChecks"], 0)
        self.assertTrue(verify_witness(encode(history()), result["witness"]))

    def test_invalid_budget_types_ranges_and_model(self):
        text = encode(history())
        for field, values in (("max_states", (-1, True, 100001, "1")),
                ("max_semantic_checks", (-1, False, 1000001, 1.5))):
            for value in values:
                with self.subTest(field=field, value=value):
                    self.assertEqual(analyze(text, **{field: value})["status"], "invalid")
        self.assertEqual(analyze(text, model="pl-si")["status"], "invalid")

    def test_json_wire_byte_depth_nodes_and_duplicate_keys(self):
        text = encode(history())
        bad_inputs = [text.replace('"schema":1', '"schema":1,"schema":1', 1),
            " " * MAX_BYTES + text, '{"x":' * 20 + "0" + "}" * 20,
            encode([0] * 4097), text.replace('"complete":true', '"complete":NaN')]
        for index, value in enumerate(bad_inputs):
            with self.subTest(index=index):
                result = analyze(value)
                self.assertEqual(result["status"], "invalid")
                self.assertIsNone(result["witness"])

    def test_direct_source_refutation_is_separate_from_INT(self):
        fixtures = {item["id"]: item for item in FIXTURES}
        internal = analyze(encode(fixtures["nonrepeatable-read"]["input"]))
        external = analyze(encode(fixtures["other-TX-intermediate-read"]["input"]))
        self.assertEqual(internal["findings"][0]["kind"], "INT")
        self.assertEqual(external["findings"][0]["kind"], "external_intermediate_source")
        self.assertEqual(external["findings"][0]["sourceWriter"], "A")
        self.assertEqual(external["findings"][0]["sourceOpIndex"], 0)
        self.assertTrue(external["findings"][0]["notAutomaticallyLabelledG1b"])
        for value in (internal, external):
            self.assertEqual(value["execution"]["decisionBasis"], "axiom-refutation")
            self.assertFalse(value["execution"]["searchedAllCandidates"])

    def test_given_order_cycle_exhausts_without_inventing_an_order(self):
        fixture = next(item for item in FIXTURES if item["id"] == "cross-key-factual-write-order-cycle")
        result = analyze(encode(fixture["input"]))
        self.assertEqual(result["status"], "unsatisfiable")
        self.assertTrue(result["execution"]["searchedAllCandidates"])
        self.assertEqual(result["execution"]["states"], 2)
        self.assertEqual(result["inputFacts"]["versionOrders"], fixture["input"]["versionOrders"])

    def test_transaction_array_permutation_and_scalar_renaming(self):
        for fixture in FIXTURES:
            if fixture["expectedSi"] not in ("satisfiable", "unsatisfiable"):
                continue
            original = fixture["input"]
            permuted = deepcopy(original)
            permuted["transactions"].reverse()
            with self.subTest(case=fixture["id"], change="array-order"):
                self.assertEqual(analyze(encode(permuted))["status"], fixture["expectedSi"])
            renamed = deepcopy(original)
            # These injective renamings deliberately include a valid NUL scalar.
            renamed["initial"] = {"K\0" + key: "V\0" + version for key, version in original["initial"].items()}
            renamed["versionOrders"] = {"K\0" + key: ["V\0" + version for version in versions]
                for key, versions in original["versionOrders"].items()}
            for transaction in renamed["transactions"]:
                transaction["id"] = "T\0" + transaction["id"]
                for event in transaction["ops"]:
                    event["key"] = "K\0" + event["key"]
                    event["version"] = "V\0" + event["version"]
            # The 256-unit fixture cannot accept a length-increasing renaming.
            if fixture["id"] != "supplementary-scalar-256-UTF16":
                with self.subTest(case=fixture["id"], change="scalar-renaming"):
                    result = analyze(encode(renamed))
                    self.assertEqual(result["status"], fixture["expectedSi"], result)
                    if result["witness"]:
                        self.assertTrue(verify_witness(encode(renamed), result["witness"]))

    def test_relation_checker_rejects_tampered_witnesses(self):
        fixture = next(item for item in FIXTURES if item["id"] == "two-blind-same-key-writes")
        text = encode(fixture["input"])
        witness = analyze(text)["witness"]
        self.assertTrue(verify_witness(text, witness))
        candidates = []
        value = deepcopy(witness); value["arbitration"] = ["A", "A"]; candidates.append(value)
        value = deepcopy(witness); value["arbitration"] = ["A"]; candidates.append(value)
        value = deepcopy(witness); value["visibility"][0]["prefixLength"] = 1; candidates.append(value)
        value = deepcopy(witness); value["visibility"][0]["initializationVisible"] = False; candidates.append(value)
        value = deepcopy(witness); value["arbitration"].reverse(); candidates.append(value)
        value = deepcopy(witness); value["visibility"][0]["tx"] = "Z"; candidates.append(value)
        value = deepcopy(witness); value["visibility"][1]["prefixLength"] = 0; candidates.append(value)
        for index, value in enumerate(candidates):
            with self.subTest(index=index):
                self.assertFalse(verify_witness(text, value))

    def test_write_skew_witness_is_SI_but_not_TOTALVIS(self):
        fixture = next(item for item in FIXTURES if item["id"] == "two-key-write-skew")
        text = encode(fixture["input"])
        witness = analyze(text)["witness"]
        self.assertTrue(verify_witness(text, witness, model="si"))
        self.assertFalse(verify_witness(text, witness, model="serial"))

    def test_budgets_increase_without_invalidating_a_witness(self):
        text = encode(history(transactions=[tx("A", op("r", "x", "x0"))]))
        small = analyze(text, max_states=2, max_semantic_checks=5)
        large = analyze(text)
        self.assertEqual(small["witness"], large["witness"])
        self.assertTrue(verify_witness(text, small["witness"]))


if __name__ == "__main__":
    import sys
    if "--freeze-inputs" in sys.argv:
        frozen = [{**fixture, "inputSha256": hashlib.sha256(encode(fixture["input"]).encode()).hexdigest()}
            for fixture in FIXTURES]
        path = ROOT / "frozen-boundaries-v1.json"
        if path.exists():
            raise SystemExit("Refusing to replace an existing frozen fixture file")
        path.write_text(json.dumps({"schema": 1, "productionOutputsRead": False,
            "fixtureCount": len(frozen), "fixtures": frozen}, ensure_ascii=True, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"fixtureCount": len(frozen), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}))
    else:
        unittest.main(verbosity=2)
