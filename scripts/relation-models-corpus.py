"""Generate frozen original relation programs and check declared reference cases.

This campaign is deliberately labelled as a partial certificate reference. A
pending/unknown weak model is retained and is not a successful parity check.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys


ORACLE_PATH = Path(__file__).with_name("relation-models-oracle.py")
SPEC = importlib.util.spec_from_file_location("relation_model_corpus_reference", ORACLE_PATH)
REFERENCE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REFERENCE
SPEC.loader.exec_module(REFERENCE)


def generate(index, seed=20261113):
    rng = random.Random((seed << 20) + index)
    prefix = "case-" + str(index) + "-"
    x = rng.randint(-9007199254740999, 9007199254740999)
    label = rng.choice(["same", "😀", "\ue000", "e\u0301", "中文"])
    enabled = rng.choice([True, False])

    def row(key, version, value):
        return {"key": str(key), "version": prefix + version, "values": {"value": str(value), "enabled": enabled, "label": label}}

    def begin(tx):
        return {"kind": "begin", "tx": tx, "connection": "connection-" + tx}

    def commit(tx):
        return [{"kind": "commit_request", "tx": tx}, {"kind": "commit_ok", "tx": tx}]

    def point(key):
        return [{"column": "id", "op": "eq", "value": str(key)}]

    def read(tx, rows, predicate):
        return {"kind": "row_read", "tx": tx, "relation": "items", "predicate": copy.deepcopy(predicate), "rows": copy.deepcopy(rows), "complete": True}

    def write(tx, value, predecessor, action="update"):
        return {"kind": "row_write", "tx": tx, "relation": "items", "key": value["key"], "action": action, "version": value["version"], "predecessor": predecessor, "values": copy.deepcopy(value["values"])}

    a0, b0 = row(1, "a0", x), row(2, "b0", -x)
    a1, b1 = row(1, "a1", x + 1), row(2, "b1", 1 - x)
    family = index % 5
    expected = {}
    if family == 0:
        temporary = row(1, "temporary", x - 1)
        deleted = {"key": "2", "version": prefix + "deleted", "values": None}
        conjunction = [{"column": "id", "op": "ge", "value": "1"}, {"column": "enabled", "op": "eq", "value": enabled}, {"column": "label", "op": "eq", "value": label}]
        body = [begin("A"), read("A", [a0, b0], conjunction),
                {"kind": "savepoint", "tx": "A", "name": "s", "instance": "A-s"},
                write("A", temporary, a0["version"]), read("A", [temporary], point(1)),
                {"kind": "rollback_to", "tx": "A", "instance": "A-s"},
                read("A", [a0], point(1)), write("A", a1, a0["version"]), *commit("A"),
                begin("B"), read("B", [a1, b0], conjunction), write("B", deleted, b0["version"], "delete"),
                read("B", [], point(2)), write("B", b1, deleted["version"], "insert"),
                read("B", [a1, b1], conjunction), *commit("B")]
        clients = [{"id": "declared-logical-session", "transactions": ["A", "B"]}]
        expected = {m: "checked-compatible" for m in REFERENCE.MODELS}
        family_name = "serial-savepoint-and-delete-reinsert"
    elif family == 1:
        body = [begin("R"), read("R", [a0], point(1)), begin("W"), write("W", a1, a0["version"]), *commit("W"), read("R", [a1], point(1)), *commit("R")]
        clients = [{"id": "reader", "transactions": ["R"]}, {"id": "writer", "transactions": ["W"]}]
        expected = {m: "checked-compatible" for m in REFERENCE.RU_MODELS | REFERENCE.RC_MODELS}
        expected.update({m: "refuted" for m in REFERENCE.SERIAL_MODELS})
        expected.update({m: "unknown" for m in REFERENCE.SI_MODELS})
        expected.update({m: "pending" for m in ["repeatable-read", "consistent-view"]})
        family_name = "legal-rc-external-reread"
    elif family == 2:
        body = [begin("A"), begin("B"), read("A", [b0], point(2)), read("B", [a0], point(1)),
                write("A", a1, a0["version"]), write("B", b1, b0["version"]), *commit("A"), *commit("B")]
        clients = [{"id": "session-A", "transactions": ["A"]}, {"id": "session-B", "transactions": ["B"]}]
        expected = {m: "checked-compatible" for m in REFERENCE.RU_MODELS | REFERENCE.RC_MODELS | REFERENCE.SI_MODELS}
        expected.update({m: "refuted" for m in REFERENCE.SERIAL_MODELS})
        expected.update({m: "pending" for m in ["repeatable-read", "consistent-view"]})
        family_name = "si-write-skew"
    elif family == 3:
        body = [begin("W"), write("W", a1, a0["version"]), *commit("W"), begin("R"), read("R", [a0], point(1)), *commit("R")]
        clients = [{"id": "declared-session", "transactions": ["W", "R"]}]
        expected = {m: "checked-compatible" for m in REFERENCE.MODELS}
        for m in ["strict-serializable", "strong-session-serializable"]:
            expected[m] = "refuted"
        for m in ["strong-session-snapshot-isolation", "strong-snapshot-isolation"]:
            expected[m] = "unknown"
        family_name = "real-time-and-process-stale-read"
    else:
        body = [begin("W"), write("W", a1, a0["version"]), {"kind": "rollback_ok", "tx": "W"}, begin("R"), read("R", [a1], point(1)), *commit("R")]
        clients = [{"id": "declared-session", "transactions": ["W", "R"]}]
        expected = {m: "refuted" for m in REFERENCE.MODELS if m not in REFERENCE.RU_MODELS}
        expected.update({m: "unknown" for m in REFERENCE.RU_MODELS})
        family_name = "known-aborted-row-source"
    source = {"traceSchema": 3, "dataModel": "relation-set-v1", "clockDomain": "generated-source-clock",
              "relationSchema": {"items": {"primaryKey": "id", "columns": {"id": "int64", "value": "int64", "enabled": "bool", "label": "text"}}},
              "scope": {"exclusiveWriters": True, "completeSnapshotTables": ["items"]}, "gaps": [],
              "events": [dict(e, seq=i + 1, time=i) for i, e in enumerate([{"kind": "snapshot", "consistent": True, "initial": {"items": [a0, b0]}}, *body])]}
    # Exercise schema-driven interpretation rather than one fixed table/column
    # spelling. Half the corpus uses text primary-key identities.
    table = ["accounts", "inventory", "reservations"][index % 3]
    names = {"id": "key_id", "value": "amount", "enabled": "active", "label": "region"} if index % 2 else {n: n for n in ["id", "value", "enabled", "label"]}
    text_key = index % 2 == 1

    def rewrite_row(value):
        if text_key:
            value["key"] = "row-" + value["key"]
        if value["values"] is not None:
            value["values"] = {names[k]: v for k, v in value["values"].items()}

    original_schema = source["relationSchema"].pop("items")
    original_schema["primaryKey"] = names["id"]
    original_schema["columns"] = {names[k]: ("text" if k == "id" and text_key else v) for k, v in original_schema["columns"].items()}
    source["relationSchema"][table] = original_schema
    source["scope"]["completeSnapshotTables"] = [table]
    for event in source["events"]:
        if event["kind"] == "snapshot":
            rows = event["initial"].pop("items")
            for value in rows:
                rewrite_row(value)
            event["initial"][table] = rows
        if event["kind"] in ["row_read", "row_write"]:
            event["relation"] = table
        if event["kind"] == "row_write":
            rewrite_row(event)
        if event["kind"] == "row_read":
            for value in event["rows"]:
                rewrite_row(value)
            for term in event["predicate"]:
                if term["column"] == "id" and text_key:
                    term["value"] = "row-" + term["value"]
                term["column"] = names[term["column"]]
    return {"id": "relation-reference-" + str(index), "family": family_name, "source": source,
            "options": {"clients": clients, "clientsComplete": True}, "expectedReferenceStatuses": expected}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new output directory")
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261113)
    args = parser.parse_args(argv)
    if not 1 <= args.count <= 10000:
        parser.error("count must be 1..10000")
    args.output.mkdir(exist_ok=False)
    cases = [generate(i, args.seed) for i in range(args.count)]
    data = (json.dumps(cases, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf8")
    (args.output / "histories.json").write_bytes(data)
    results, failures, statuses = [], [], {}
    certificate_replays = 0
    for case in cases:
        for model in REFERENCE.MODELS:
            expected = case["expectedReferenceStatuses"][model]
            result = REFERENCE.analyze(case["source"], model, case["options"])
            passed = result["status"] == expected
            if result["status"] == "checked-compatible":
                certificate_replays += 1
                passed = passed and REFERENCE.verify_certificate(case["source"], model, result["certificate"], case["options"])["valid"]
            row = {"id": case["id"], "family": case["family"], "model": model, "expected": expected,
                   "actual": result["status"], "passed": passed, "exactDecision": result["exactDecision"]}
            results.append(row)
            statuses[model + "/" + result["status"]] = statuses.get(model + "/" + result["status"], 0) + 1
            if not passed:
                failures.append({"case": case, "model": model, "actual": result})
    raw = ("\n".join(json.dumps(r, separators=(",", ":")) for r in results) + "\n").encode()
    (args.output / "results.jsonl").write_bytes(raw)
    if failures:
        (args.output / "failures.json").write_bytes((json.dumps(failures, ensure_ascii=False, indent=2) + "\n").encode("utf8"))
    digest = lambda b: hashlib.sha256(b).hexdigest()
    summary = {"format": "independent-relation-certificate-corpus/v1", "passed": not failures,
               "histories": len(cases), "seed": args.seed, "judgments": len(results), "certificateReplays": certificate_replays,
               "failures": len(failures), "statuses": statuses, "fullFourteenModelParity": False,
               "scope": "Exact serial decisions, direct G1a/G1b findings and sufficient weak-model certificates; pending/unknown retained.",
               "historiesSha256": digest(data), "resultsSha256": digest(raw),
               "oracleSha256": digest(ORACLE_PATH.read_bytes()), "generatorSha256": digest(Path(__file__).read_bytes())}
    (args.output / "summary.json").write_bytes((json.dumps(summary, indent=2) + "\n").encode())
    print(json.dumps({k: summary[k] for k in ["passed", "histories", "judgments", "certificateReplays", "failures", "fullFourteenModelParity"]}))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
