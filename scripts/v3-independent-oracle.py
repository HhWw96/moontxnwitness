"""Independent v3 lifecycle reference: persistent scope snapshots, not a trail.

The lifecycle reference imports no production module, database, compiler, or
analyzer. Fixture expectations are manually declared and never rewritten.
The separate optional journal audit exercises production storage against raw
byte checks and injected IO failures; it is not part of reference().
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import itertools
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures/v3"
SAFE = 9007199254740991
BASE = {"seq", "time", "kind"}
FIELDS = {
    "snapshot": {"initial", "consistent"}, "begin": {"tx", "connection"},
    "read": {"tx", "key", "version"},
    "write": {"tx", "key", "version", "predecessor"},
    "condition": {"tx", "predicate", "matched", "sourceVersion"},
    "savepoint": {"tx", "name", "instance"},
    "rollback_to": {"tx", "instance"}, "release": {"tx", "instance"},
    "commit_request": {"tx"}, "commit_ok": {"tx"},
    "rollback_ok": {"tx"}, "disconnect": {"tx"},
    "statement": {"tx", "sql", "parameters"},
    "rows": {"tx", "statement", "rows", "complete"},
}


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def identifier(value):
    require(isinstance(value, str), "identifier must be text")
    require(0 < len(value.encode("utf-16-le", errors="surrogatepass")) // 2 <= 256,
            "identifier length")
    require(all(ord(c) >= 32 and ord(c) != 127 and not 0xD800 <= ord(c) <= 0xDFFF for c in value),
            "identifier control/surrogate")
    return value


def safe_integer(value, minimum=0):
    require(type(value) in [int, float] and math.isfinite(value)
            and minimum <= value <= SAFE and int(value) == value, "safe integer required")
    return int(value)


def fields(value, allowed, required=()):
    require(type(value) is dict, "object required")
    require(set(value) <= set(allowed) and set(required) <= set(value), "unknown or missing field")
    return value


def duplicate_free(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def parse(text):
    require(len(text.encode("utf-8")) <= 8388608, "trace UTF-8 size")
    result = json.loads(text, object_pairs_hook=duplicate_free,
                        parse_constant=lambda _value: (_ for _ in ()).throw(Invalid("nonfinite JSON")))
    pending = [(result, 0)]
    while pending:
        value, depth = pending.pop()
        if type(value) in [dict, list]:
            require(depth < 64, "JSON container depth")
            pending.extend((child, depth + 1) for child in (value.values() if type(value) is dict else value))
    return result


def serial_feasible(history):
    """Small independent atomic register interpreter; no dependency graph."""
    committed = [tx for tx in history["transactions"] if tx["status"] == "committed"]
    if len(committed) > 7:
        return None
    for order in itertools.permutations(committed):
        state = dict(history["initial"])
        positions = {key: 0 for key in state}
        valid = True
        for tx in order:
            final = {op["key"]: index for index, op in enumerate(tx["ops"]) if op["type"] == "write"}
            for index, op in enumerate(tx["ops"]):
                if op["type"] == "read":
                    if state.get(op["key"]) != op["version"]:
                        valid = False
                        break
                else:
                    state[op["key"]] = op["version"]
                    if final[op["key"]] == index:
                        chain = history["versionOrders"][op["key"]]
                        positions[op["key"]] += 1
                        if positions[op["key"]] >= len(chain) or chain[positions[op["key"]]] != op["version"]:
                            valid = False
                            break
            if not valid:
                break
        if valid:
            return True
    return False


def reference(document):
    """Return a reference ledger and conservative register projection."""
    issues = []
    effects, transactions, reads = [], {}, []
    initial, sources, connections, instances, statements = {}, {}, {}, set(), {}

    def gap(code):
        if code not in issues:
            issues.append(code)

    try:
        root = parse(document) if isinstance(document, str) else copy.deepcopy(document)
        fields(root, ["traceSchema", "clockDomain", "scope", "events", "gaps"],
               ["traceSchema", "clockDomain", "scope", "events", "gaps"])
        require(safe_integer(root["traceSchema"]) == 3, "trace schema")
        identifier(root["clockDomain"])
        scope = fields(root["scope"], ["exclusiveWriters"], ["exclusiveWriters"])
        require(type(scope["exclusiveWriters"]) is bool, "scope boolean")
        if not scope["exclusiveWriters"]:
            gap("writer_scope_unproven")
        require(type(root["gaps"]) is list, "gaps array")
        for item in root["gaps"]:
            fields(item, ["code", "message"], ["code", "message"])
            identifier(item["code"])
            require(isinstance(item["message"], str) and 0 < len(item["message"]) <= 4096, "gap message")
            gap(item["code"])
        require(type(root["events"]) is list and len(root["events"]) <= 65536, "events limit")
        previous_seq, previous_time, snapshot_seen, operations = 0, 0, False, 0
        for event in root["events"]:
            require(type(event) is dict, "event object")
            kind = identifier(event.get("kind"))
            require(kind in FIELDS, "unsupported event")
            required = BASE | (FIELDS[kind] - {"sourceVersion", "parameters"})
            fields(event, BASE | FIELDS[kind], required)
            seq, time = safe_integer(event["seq"], 1), safe_integer(event["time"])
            require(seq > previous_seq and time >= previous_time, "sequence or time reversal")
            if seq != previous_seq + 1:
                gap("sequence_gap")
            previous_seq, previous_time = seq, time
            if kind == "snapshot":
                require(not snapshot_seen and not transactions, "snapshot position")
                snapshot_seen = True
                require(type(event["consistent"]) is bool, "snapshot boolean")
                if not event["consistent"]:
                    gap("inconsistent_snapshot")
                require(type(event["initial"]) is dict, "initial object")
                for key, version in event["initial"].items():
                    identifier(key), identifier(version)
                    require(version not in sources, "global version reuse")
                    initial[key] = version
                    sources[version] = {"key": key, "initial": True, "seq": seq}
                continue
            require(snapshot_seen, "snapshot must precede transactions")
            tx_id = identifier(event["tx"])
            if kind == "begin":
                connection = identifier(event["connection"])
                require(tx_id not in transactions and connection not in connections, "transaction/connection reuse")
                require(len(transactions) < 512, "transaction limit")
                transactions[tx_id] = {"id": tx_id, "connection": connection, "status": "unknown",
                    "beginSeq": seq, "endSeq": None, "events": [seq], "overlay": {},
                    "marks": {}, "requested": False, "active": True, "operations": []}
                connections[connection] = tx_id
                continue
            require(tx_id in transactions and transactions[tx_id]["active"], "inactive transaction")
            tx = transactions[tx_id]
            tx["events"].append(seq)
            if tx["requested"]:
                require(kind in ["commit_ok", "rollback_ok", "disconnect"], "operation after commit request")
            if kind in ["read", "write", "condition"]:
                operations += 1
                require(operations <= 10000, "operation limit")
            if kind in ["read", "write"]:
                key, version = identifier(event["key"]), identifier(event["version"])
                if key not in initial:
                    gap("missing_initial")
                if kind == "read":
                    if version not in sources:
                        gap("missing_version_source")
                    record = {"seq": seq, "tx": tx_id, "key": key, "version": version,
                              "ownAtRead": tx["overlay"].get(key)}
                    reads.append(record)
                    tx["operations"].append((seq, "read", record))
                else:
                    predecessor = identifier(event["predecessor"])
                    require(version not in sources and version != predecessor, "global version reuse/self predecessor")
                    effect = {"seq": seq, "tx": tx_id, "key": key, "version": version,
                              "predecessor": predecessor, "revertedBy": None}
                    sources[version] = {**effect, "initial": False, "effect": effect,
                                        "ownBeforeWrite": tx["overlay"].get(key)}
                    effects.append(effect)
                    tx["overlay"][key] = seq
                    tx["operations"].append((seq, "write", effect))
            elif kind == "condition":
                require(type(event["matched"]) is bool, "condition boolean")
                if "sourceVersion" in event:
                    identifier(event["sourceVersion"])
                gap("unsupported_condition")
            elif kind == "savepoint":
                identifier(event["name"])
                instance = identifier(event["instance"])
                require(instance not in instances and len(tx["marks"]) < 64, "scope instance/depth")
                instances.add(instance)
                tx["marks"][instance] = {"seq": seq, "name": event["name"], "overlay": dict(tx["overlay"])}
            elif kind in ["rollback_to", "release"]:
                instance = identifier(event["instance"])
                require(instance in tx["marks"], "inactive or foreign scope instance")
                target = tx["marks"][instance]
                require(not any(mark["name"] == target["name"] and mark["seq"] > target["seq"]
                                for mark in tx["marks"].values()), "older same-name scope is hidden")
                if kind == "rollback_to":
                    for effect in effects:
                        if effect["tx"] == tx_id and effect["seq"] > target["seq"] and effect["revertedBy"] is None:
                            effect["revertedBy"] = seq
                    tx["overlay"] = dict(target["overlay"])
                tx["marks"] = {name: mark for name, mark in tx["marks"].items()
                               if mark["seq"] < target["seq"] or kind == "rollback_to" and name == instance}
            elif kind == "commit_request":
                require(not tx["requested"], "repeated commit request")
                tx["requested"] = True
            elif kind in ["commit_ok", "rollback_ok", "disconnect"]:
                if kind == "commit_ok":
                    require(tx["requested"], "commit acknowledgement without request")
                    tx["status"] = "committed"
                elif kind == "rollback_ok" and not tx["requested"]:
                    tx["status"] = "aborted"
                    for effect in effects:
                        if effect["tx"] == tx_id and effect["revertedBy"] is None:
                            effect["revertedBy"] = seq
                    tx["overlay"] = {}
                else:
                    gap("unknown_commit")
                tx["active"], tx["endSeq"] = False, seq
                del connections[tx["connection"]]
            elif kind == "statement":
                require(isinstance(event["sql"], str) and 0 < len(event["sql"]) <= 65536, "SQL text")
                statements[seq] = {"tx": tx_id, "hasRows": False, "complete": False}
                gap("unmapped_statement")
            elif kind == "rows":
                statement = safe_integer(event["statement"], 1)
                require(statement in statements and statements[statement]["tx"] == tx_id, "rows source statement")
                require(not statements[statement]["complete"], "rows after complete")
                require(type(event["rows"]) is list and type(event["complete"]) is bool, "rows shape")
                statements[statement].update(hasRows=True, complete=event["complete"])
        if not snapshot_seen:
            gap("missing_snapshot")
        for tx in transactions.values():
            if tx["active"]:
                gap("outstanding_transaction")
        for statement in statements.values():
            if statement["hasRows"] and not statement["complete"]:
                gap("incomplete_rows")

        by_seq = {effect["seq"]: effect for effect in effects}
        final_writes = {tx["id"]: sorted(tx["overlay"].values()) for tx in transactions.values()}
        for effect in effects:
            predecessor = sources.get(effect["predecessor"])
            if predecessor is None:
                gap("missing_version_source")
                continue
            require(predecessor["key"] == effect["key"] and predecessor["seq"] < effect["seq"], "predecessor key/order")
            own = sources[effect["version"]]["ownBeforeWrite"]
            if own is not None:
                require(by_seq[own]["version"] == effect["predecessor"], "predecessor is not current own overlay")
            elif not predecessor["initial"]:
                require(predecessor["tx"] != effect["tx"], "predecessor is revoked own write")
            if not predecessor["initial"] and predecessor["tx"] != effect["tx"]:
                owner = transactions[predecessor["tx"]]
                if owner["status"] != "committed" or predecessor["effect"]["revertedBy"] is not None or predecessor["seq"] not in final_writes[owner["id"]]:
                    gap("unsafe_write_source")
        projected_reads = set()
        for read in reads:
            source = sources.get(read["version"])
            if source is None:
                continue
            require(source["key"] == read["key"], "read source key")
            if read["ownAtRead"] is not None:
                own = by_seq[read["ownAtRead"]]
                # Own reads are checked against the overlay at observation time.
                # A later rollback revokes effects, not this earlier observation.
                if own["version"] != read["version"]:
                    gap("own_read_mismatch")
                continue
            if not source["initial"]:
                if source["tx"] == read["tx"]:
                    gap("own_read_mismatch")
                    continue
                owner = transactions[source["tx"]]
                if owner["status"] != "committed" or source["effect"]["revertedBy"] is not None or source["seq"] not in final_writes[owner["id"]]:
                    gap("unsafe_read_source")
                    continue
            projected_reads.add(read["seq"])

        orders = {}
        for key, first in initial.items():
            committed = {e["version"] for e in effects if e["key"] == key and e["revertedBy"] is None
                         and transactions[e["tx"]]["status"] == "committed" and e["seq"] in final_writes[e["tx"]]}
            successor = {}
            for version in committed:
                predecessor = sources[version]["predecessor"]
                seen = {version}
                while predecessor != first and predecessor not in committed:
                    if predecessor not in sources or predecessor in seen:
                        gap("version_order_gap")
                        break
                    seen.add(predecessor)
                    previous = sources[predecessor]
                    if previous["initial"]:
                        gap("version_order_gap")
                        break
                    predecessor = previous["predecessor"]
                if predecessor in successor and successor[predecessor] != version:
                    gap("version_order_gap")
                successor[predecessor] = version
            chain, current = [first], first
            while current in successor and len(chain) <= len(committed):
                current = successor[current]
                chain.append(current)
            if set(chain[1:]) != committed:
                gap("version_order_gap")
            orders[key] = chain
        public_transactions = [{key: tx[key] for key in ["id", "connection", "status", "beginSeq", "endSeq", "events"]}
                               | {"finalWrites": final_writes[tx["id"]]} for tx in transactions.values()]
        history = None
        if not issues:
            history = {"schemaVersion": 1, "model": "serializable", "initial": initial,
                       "versionOrders": orders, "transactions": []}
            for tx in transactions.values():
                operations = []
                for seq, kind, record in tx["operations"]:
                    if kind == "write" and record["revertedBy"] is None or kind == "read" and seq in projected_reads:
                        operations.append({"type": kind, "key": record["key"], "version": record["version"]})
                history["transactions"].append({"id": tx["id"], "status": tx["status"], "ops": operations,
                                                "start": None, "end": None})
        return {"schema": 1, "independentReference": True,
                "status": "inconclusive" if issues else "ready", "complete": not issues,
                "issues": issues, "observations": root["events"], "effects": effects,
                "transactions": public_transactions, "retainedReads": [{k: v for k, v in r.items() if k != "ownAtRead"} for r in reads],
                "history": history, "serialFeasible": serial_feasible(history) if history is not None else None}
    except (Invalid, ValueError, TypeError, KeyError, UnicodeError, RecursionError) as error:
        return {"schema": 1, "independentReference": True, "status": "invalid", "complete": False,
                "issues": ["invalid_capture_v3"], "reason": str(error), "history": None}


def trace(events, *, initial=None, exclusive=True, gaps=None):
    events = [{"kind": "snapshot", "initial": initial if initial is not None else {"x": "x0", "y": "y0"},
               "consistent": True}] + events
    return {"traceSchema": 3, "clockDomain": "independent-fixture-clock", "scope": {"exclusiveWriters": exclusive},
            "events": [{"seq": i + 1, "time": i, **event} for i, event in enumerate(events)], "gaps": gaps or []}


def corpus():
    """Manual examples and expected observable behavior, independent of reference()."""
    def b(tx="T", connection="C"): return {"kind": "begin", "tx": tx, "connection": connection}
    def r(version="x0", tx="T", key="x"): return {"kind": "read", "tx": tx, "key": key, "version": version}
    def w(version="x1", predecessor="x0", tx="T", key="x"): return {"kind": "write", "tx": tx, "key": key, "version": version, "predecessor": predecessor}
    def sp(instance="s1", name="same", tx="T"): return {"kind": "savepoint", "tx": tx, "name": name, "instance": instance}
    def e(kind, tx="T", **extra): return {"kind": kind, "tx": tx, **extra}
    def done(tx="T"): return [e("commit_request", tx), e("commit_ok", tx)]
    cases = []
    def add(name, events, status="ready", **expected):
        cases.append({"id": name, "trace": trace(events), "expected": {"status": status, **expected}})
    add("empty-snapshot", [], activeVersions=[], revertedVersions=[], readCount=0)
    add("initial-read-commit", [b(), r(), *done()], txOutcomes={"T": "committed"}, readCount=1)
    add("same-key-multiple-writes", [b(), w(), w("x2", "x1"), *done()], activeVersions=["x1", "x2"], finalVersions=["x2"])
    add("own-read-preserved-as-observation", [b(), w(), r("x1"), *done()], readCount=1, legacyReadCount=0)
    add("rollback-revokes-write-retains-read", [b(), r(), w(), e("rollback_ok")], txOutcomes={"T": "aborted"}, revertedVersions=["x1"], readCount=1)
    add("rollback-to-restores-overlay", [b(), w(), sp(), w("x2", "x1"), e("rollback_to", instance="s1"), r("x1"), *done()], revertedVersions=["x2"], finalVersions=["x1"], readCount=1)
    add("read-of-later-reverted-own-write", [b(), sp(), w(), r("x1"), e("rollback_to", instance="s1"), *done()], "inconclusive", issue="own_read_mismatch", readCount=1)
    add("release-is-not-commit", [b(), sp(), w(), e("release", instance="s1")], "inconclusive", issue="outstanding_transaction", txOutcomes={"T": "unknown"})
    add("released-inner-write-outer-rollback", [b(), sp("outer"), sp("inner"), w(), e("release", instance="inner"), e("rollback_to", instance="outer"), *done()], revertedVersions=["x1"], finalVersions=[])
    add("same-name-different-instances", [b(), sp("s1"), w(), sp("s2"), w("x2", "x1"), e("rollback_to", instance="s2"), e("release", instance="s2"), e("release", instance="s1"), *done()], revertedVersions=["x2"], finalVersions=["x1"])
    add("rollback-to-target-remains-active", [b(), sp(), w(), e("rollback_to", instance="s1"), w("x2"), e("rollback_to", instance="s1"), *done()], revertedVersions=["x1", "x2"], finalVersions=[])
    add("released-instance-cannot-be-reused", [b(), sp(), e("release", instance="s1"), sp()], "invalid")
    add("rollback-descendant-destroyed", [b(), sp("outer"), sp("inner"), e("rollback_to", instance="outer"), e("release", instance="inner")], "invalid")
    add("foreign-savepoint-instance", [b(), sp(), b("U", "D"), e("rollback_to", "U", instance="s1")], "invalid")
    add("commit-ack-needs-request", [b(), e("commit_ok")], "invalid")
    add("repeated-commit-request", [b(), e("commit_request"), e("commit_request")], "invalid")
    add("operation-after-commit-request", [b(), e("commit_request"), r()], "invalid")
    add("disconnect-after-request", [b(), w(), e("commit_request"), e("disconnect")], "inconclusive", issue="unknown_commit", txOutcomes={"T": "unknown"})
    add("rollback-after-request-not-proof", [b(), w(), e("commit_request"), e("rollback_ok")], "inconclusive", issue="unknown_commit", activeVersions=["x1"], revertedVersions=[])
    add("connection-reuse-does-not-resolve-unknown", [b(), e("commit_request"), e("disconnect"), b("U"), *done("U")], "inconclusive", txOutcomes={"T": "unknown", "U": "committed"})
    add("connection-reuse-after-known-commit", [b(), *done(), b("U"), r(tx="U"), *done("U")], txOutcomes={"T": "committed", "U": "committed"})
    add("overlapping-connection-transactions", [b(), b("U")], "invalid")
    add("transaction-id-reuse", [b(), *done(), b()], "invalid")
    add("missing-read-version-never-inferred", [b(), r("missing"), *done()], "inconclusive", issue="missing_version_source")
    add("future-write-does-not-repair-missing-source", [b(), r("later"), *done(), b("U", "D"), w("later", tx="U"), *done("U")], "inconclusive", issue="missing_version_source")
    add("external-read-before-commit-log", [b(), w(), e("commit_request"), b("U", "D"), r("x1", "U"), e("commit_ok"), *done("U")], readCount=1)
    add("aborted-external-read-not-complete", [b(), w(), e("rollback_ok"), b("U", "D"), r("x1", "U"), *done("U")], "inconclusive", issue="unsafe_read_source")
    add("intermediate-external-read-not-complete", [b(), w(), w("x2", "x1"), *done(), b("U", "D"), r("x1", "U"), *done("U")], "inconclusive", issue="unsafe_read_source")
    add("committed-predecessor-fork-not-log-order", [b(), w(), *done(), b("U", "D"), w("x2", tx="U"), *done("U")], "inconclusive", issue="version_order_gap")
    add("proven-external-predecessor-chain", [b(), w(), *done(), b("U", "D"), w("x2", "x1", "U"), *done("U")], finalVersions=["x1", "x2"])
    add("global-version-id-reuse-across-keys", [b(), w(), w("x1", "y0", key="y"), *done()], "invalid")
    add("predecessor-wrong-key", [b(), w(predecessor="y0"), *done()], "invalid")
    add("unknown-predecessor-not-invented", [b(), w(predecessor="missing"), *done()], "inconclusive", issue="missing_version_source")
    add("false-condition-still-observation", [b(), e("condition", predicate={"field": "balance", "operator": ">", "value": 0}, matched=False), *done()], "inconclusive", issue="unsupported_condition")
    add("condition-source-not-a-supported-mapping", [b(), e("condition", predicate={"equals": ["x", "x0"]}, matched=True, sourceVersion="x0"), *done()], "inconclusive", issue="unsupported_condition")
    add("statement-without-semantic-map", [b(), e("statement", sql="DELETE FROM business"), *done()], "inconclusive", issue="unmapped_statement")
    add("complete-rows-do-not-prove-mapping", [b(), e("statement", sql="SELECT value FROM business", parameters=[]), e("rows", statement=3, rows=[["x0"]], complete=True), *done()], "inconclusive", issue="unmapped_statement")
    add("unconsumed-row-result", [b(), e("statement", sql="SELECT value FROM business"), e("rows", statement=3, rows=[], complete=False), *done()], "inconclusive", issue="incomplete_rows")
    add("rows-reference-other-transaction", [b(), e("statement", sql="SELECT 1"), b("U", "D"), e("rows", "U", statement=3, rows=[[1]], complete=True)], "invalid")
    add("self-asserted-mapped-field-rejected", [b(), e("statement", sql="DELETE FROM business", mapped=True), *done()], "invalid")
    add("write-skew-safe-projection", [b(), b("U", "D"), r(), r("y0", "U", "y"), w("y1", "y0", key="y"), w("x1", tx="U"), *done(), *done("U")], analysisExpected="violation")
    # Envelope and transport corruption retain their own immutable fixtures.
    for name, mutation, status, issue in [
        ("sequence-gap", lambda t: t["events"][2].update(seq=4), "inconclusive", "sequence_gap"),
        ("duplicate-sequence", lambda t: t["events"][2].update(seq=2), "invalid", None),
        ("backwards-clock", lambda t: t["events"][3].update(time=0), "invalid", None),
        ("unproven-writer-scope", lambda t: t["scope"].update(exclusiveWriters=False), "inconclusive", "writer_scope_unproven"),
        ("inconsistent-initial-snapshot", lambda t: t["events"][0].update(consistent=False), "inconclusive", "inconsistent_snapshot"),
        ("explicit-log-write-failure", lambda t: t["gaps"].append({"code": "log_write_failed", "message": "Injected failure"}), "inconclusive", "log_write_failed"),
        ("unsupported-root-field", lambda t: t.update(untrustedComplete=True), "invalid", None),
        ("wrong-schema", lambda t: t.update(traceSchema=2), "invalid", None),
        ("fractional-sequence", lambda t: t["events"][2].update(seq=3.5), "invalid", None),
        ("unsafe-clock-integer", lambda t: t["events"][2].update(time=9007199254740992), "invalid", None),
        ("boolean-schema-not-integer", lambda t: t.update(traceSchema=True), "invalid", None),
    ]:
        value = trace([b(), r(), *done()])
        mutation(value)
        if name == "sequence-gap":
            for event in value["events"][3:]: event["seq"] += 1
        cases.append({"id": name, "trace": value, "expected": {"status": status, **({"issue": issue} if issue else {})}})
    return cases


def summary(result):
    effects, txs = result.get("effects", []), result.get("transactions", [])
    final = {seq for tx in txs for seq in tx["finalWrites"]}
    return {"status": result["status"], "txOutcomes": {tx["id"]: tx["status"] for tx in txs},
            "activeVersions": [e["version"] for e in effects if e["revertedBy"] is None],
            "revertedVersions": [e["version"] for e in effects if e["revertedBy"] is not None],
            "finalVersions": [e["version"] for e in effects if e["seq"] in final],
            "readCount": len(result.get("retainedReads", [])),
            "legacyReadCount": sum(op["type"] == "read" for tx in (result.get("history") or {}).get("transactions", []) for op in tx["ops"])}


def freeze():
    require(not (FIXTURES / "manifest.json").exists(), "Frozen fixture manifest already exists")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": 1, "contract": "v3-lifecycle-1", "independentOracle": "scripts/v3-independent-oracle.py",
                "expectations": "Manually declared observable outcomes, never generated by the oracle", "cases": []}
    for case in corpus():
        path = FIXTURES / (case["id"] + ".json")
        raw = (json.dumps(case["trace"], ensure_ascii=False, indent=2) + "\n").encode()
        with path.open("xb") as stream: stream.write(raw)
        manifest["cases"].append({"id": case["id"], "trace": path.relative_to(ROOT).as_posix(),
                                  "sha256": hashlib.sha256(raw).hexdigest(), "expected": case["expected"]})
    with (FIXTURES / "manifest.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    return {"frozen": True, "cases": len(manifest["cases"])}


def fixture_cases():
    manifest = json.loads((FIXTURES / "manifest.json").read_bytes())
    cases = copy.deepcopy(manifest["cases"])
    corrections = json.loads((FIXTURES / "protocol-correction-1.json").read_bytes())
    require(hashlib.sha256((FIXTURES / "manifest.json").read_bytes()).hexdigest() == corrections["originalManifestSha256"],
            "Correction must bind the unmodified original manual expectations")
    for change in corrections["supersedingExpectations"]:
        item = next(item for item in cases if item["id"] == change["id"])
        require(item["sha256"] == change["traceSha256"] and item["expected"] == change["originalExpected"],
                "Superseded expectation provenance changed")
        item["expected"] = change["correctedExpected"]
        item["expectationOrigin"] = "fixtures/v3/protocol-correction-1.json"
    cases.extend(corrections["additionalCases"])
    require(len({item["id"] for item in cases}) == len(cases), "Duplicate fixture identity")
    return cases


def batch():
    results = []
    for item in fixture_cases():
        raw = (ROOT / item["trace"]).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == item["sha256"], "Frozen trace changed")
        result = reference(raw.decode("utf-8"))
        observed = summary(result)
        failures = [key for key, expected in item["expected"].items()
                    if key != "analysisExpected" and (expected not in result["issues"] if key == "issue" else observed[key] != expected)]
        results.append({"id": item["id"], "fixture": item, "manualExpectationsPassed": not failures,
                        "failedExpectedFields": failures, "summary": observed, "reference": result})
    return {"schema": 1, "independentReference": True, "actualDatabaseExecution": False,
            "passed": all(item["manualExpectationsPassed"] for item in results), "cases": results}


def journal_audit(scratch):
    """Bounded real-file audit. All raw files, including failures, are retained."""
    import importlib.util
    import os
    import shutil
    import sqlite3
    import sys
    import threading
    import uuid
    import zipfile
    from unittest import mock

    module_path = ROOT / "integrations/python/moontxnwitness_capture/journal_v3.py"
    source_bytes, audit_bytes = module_path.read_bytes(), Path(__file__).read_bytes()
    # Isolate the storage package from sys.path and any ambient module named
    # _durable_policy. Execute the exact sibling bytes bound in this receipt.
    import types
    policy_path = module_path.with_name("_durable_policy.py")
    policy_bytes = policy_path.read_bytes()
    package_name = "mtw_storage_under_audit_" + uuid.uuid4().hex
    package = types.ModuleType(package_name)
    package.__path__ = []
    sys.modules[package_name] = package
    policy_spec = importlib.util.spec_from_file_location(package_name + "._durable_policy", policy_path)
    policy = importlib.util.module_from_spec(policy_spec)
    sys.modules[policy_spec.name] = policy
    exec(compile(policy_bytes, str(policy_path), "exec"), policy.__dict__)
    # The experimental capacity dependency is also isolated and byte-bound.
    budget_path = module_path.with_name("_experimental_budget.py")
    budget_bytes = budget_path.read_bytes()
    budget_spec = importlib.util.spec_from_file_location(package_name + "._experimental_budget", budget_path)
    budget = importlib.util.module_from_spec(budget_spec)
    sys.modules[budget_spec.name] = budget
    exec(compile(budget_bytes, str(budget_path), "exec"), budget.__dict__)
    spec = importlib.util.spec_from_file_location(package_name + ".journal_v3", module_path)
    storage = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = storage
    # Compile the exact bound bytes, rather than relying on a possibly cached
    # bytecode file or on a later read of a concurrently edited source file.
    exec(compile(source_bytes, str(module_path), "exec"), storage.__dict__)
    run = scratch.resolve() / ("independent-v3-journal-" + uuid.uuid4().hex)
    run.mkdir(parents=True, exist_ok=False)
    os.environ["MTW_JOURNAL_SCRATCH"] = str(run)
    checks, details = [], {}

    def digest(raw):
        return hashlib.sha256(raw).hexdigest()

    def check(name, action):
        try:
            action()
            checks.append({"name": name, "passed": True})
        except Exception as error:
            checks.append({"name": name, "passed": False, "errorClass": type(error).__name__,
                           "message": str(error).replace(str(ROOT), "<workspace>").replace(str(run), "<journal-audit>")})

    def demand(condition, message):
        if not condition:
            raise AssertionError(message)

    def independent_bindings(directory):
        raw = (directory / "journal-index.json").read_bytes()
        index = json.loads(raw, object_pairs_hook=duplicate_free)
        checksum = index.pop("indexSha256")
        # Independent encoder: no journal serialization/checksum helper called.
        canonical = json.dumps(index, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
        demand(checksum == digest(canonical), "Independent canonical index hash mismatch")
        actual = []
        for segment in index["segments"]:
            data = (directory / segment["name"]).read_bytes()
            demand(len(data) == segment["bytes"] and digest(data) == segment["sha256"], "Independent raw segment binding mismatch")
            lines = data.splitlines(keepends=True)
            demand(all(line.endswith(b"\n") for line in lines), "Partial raw line")
            records = [json.loads(line, object_pairs_hook=duplicate_free) for line in lines]
            demand(len(records) == segment["eventCount"], "Independent segment event count mismatch")
            demand((records[0]["seq"], records[-1]["seq"]) == (segment["firstSeq"], segment["lastSeq"]), "Independent segment sequence endpoints mismatch")
            actual.extend(records)
        demand(len(actual) == index["eventCount"], "Independent total event count mismatch")
        rows = sorted((event["tx"], event["seq"]) for event in actual if event["kind"] == "begin")
        cache = sqlite3.connect((directory / "transactions.sqlite3").as_uri() + "?mode=ro&immutable=1", uri=True)
        try:
            demand(cache.execute("SELECT tx,begin_seq FROM transactions ORDER BY tx").fetchall() == rows,
                   "Independent transaction cache rows do not match original begin events")
        finally:
            cache.close()
        return {"indexBytes": len(raw), "indexSha256": digest(raw), "rawEvents": actual,
                "segments": [{"name": item["name"], "bytes": item["bytes"], "sha256": item["sha256"]} for item in index["segments"]]}

    source = json.loads((FIXTURES / "initial-read-commit.json").read_bytes())
    good = run / "good"
    writer = storage.SegmentedJournal(good, segment_bytes=512, max_record_bytes=256, max_queue_bytes=512)
    accepted = [writer.append(event) for event in source["events"]]
    durable = writer.flush()
    status = writer.close(source_closed=True)
    details["completeSource"] = status.as_dict()

    def roundtrip():
        demand(all(result.accepted for result in accepted), "A complete source append was rejected")
        demand(durable == source["events"][-1]["seq"], "flush did not acknowledge the complete durable tail")
        demand(status.complete, "Valid closed source did not seal")
        bound = independent_bindings(good)
        demand(bound.pop("rawEvents") == source["events"], "Actual raw event bytes do not decode to the supplied observations")
        details["independentBindings"] = bound
        demand(list(storage.JournalReader(good).iter_events()) == source["events"], "Streaming reader observation mismatch")
    check("independent-index-raw-bytes-and-durable-tail", roundtrip)

    def export_roundtrip():
        target = run / "export.json"
        exported = storage.JournalReader(good).export(target, clock_domain=source["clockDomain"], exclusive_writers=True)
        raw = target.read_bytes()
        demand(exported["bytes"] == len(raw) and exported["sha256"] == digest(raw), "Export actual bytes differ from receipt")
        decoded = json.loads(raw)
        demand(decoded == source, "Export altered observed source facts")
        interpreted = reference(raw.decode("utf-8"))
        demand(interpreted["status"] == "ready" and interpreted["serialFeasible"] is True, "Export is not a complete independent register history")
        sentinel = raw
        try:
            storage.JournalReader(good).export(target, clock_domain="clock", exclusive_writers=True)
            raise AssertionError("Export overwrote an existing path")
        except FileExistsError:
            pass
        demand(target.read_bytes() == sentinel, "Rejected overwrite changed prior bytes")
        details["export"] = {"bytes": len(raw), "sha256": digest(raw), "independentStatus": interpreted["status"]}
    check("export-independent-reference-and-existing-file-preservation", export_roundtrip)

    def archive_roundtrip():
        before = {file.name: digest(file.read_bytes()) for file in good.iterdir() if file.is_file()}
        archive = run / "complete.zip"
        result = storage.JournalReader(good).archive(archive)
        with zipfile.ZipFile(archive) as zipped:
            demand(set(zipped.namelist()) == set(before), "Archive member set differs from original evidence")
            for name, expected in before.items():
                demand(digest(zipped.read(name)) == expected, "Archive changed source file " + name)
        demand(before == {file.name: digest(file.read_bytes()) for file in good.iterdir() if file.is_file()}, "Archive changed or deleted original evidence")
        demand(result["verified"] is True and result["sourceFilesDeleted"] is False, "Archive receipt misstates state")
        details["archive"] = {"sha256": digest(archive.read_bytes()), "members": before}
    check("archive-full-original-byte-set-and-source-preservation", archive_roundtrip)

    for corruption in ("same-size", "partial-tail"):
        def corrupt(kind=corruption):
            target = run / ("corrupt-" + kind)
            shutil.copytree(good, target)
            segment = next(target.glob("segment-*.jsonl"))
            data = segment.read_bytes()
            segment.write_bytes(data.replace(b"x0", b"z0", 1) if kind == "same-size" else data + b'{"seq":999')
            verified = storage.JournalReader(target).verify()
            details[kind] = verified.as_dict()
            demand(not verified.valid and not verified.complete, "Corrupt raw source was accepted complete")
            output = run / (kind + ".json")
            try:
                storage.JournalReader(target).export(output, clock_domain="clock", exclusive_writers=True)
                raise AssertionError("Corrupt source was exported successfully")
            except storage.JournalVerificationError:
                pass
            demand(not output.exists(), "Corrupt source published a final JSON")
        check("corrupt-" + corruption + "-cannot-export", corrupt)

    def outcome_unknown():
        unknown = run / "unknown-outcome"
        w = storage.SegmentedJournal(unknown)
        events = trace([{"kind": "begin", "tx": "T", "connection": "C"},
                        {"kind": "commit_request", "tx": "T"}, {"kind": "rollback_ok", "tx": "T"}])["events"]
        for event in events:
            demand(w.append(event).accepted, "Unknown-outcome input was not retained")
        verified = w.close(source_closed=True)
        details["unknownOutcome"] = verified.as_dict()
        demand(not verified.complete, "Idle rollback incorrectly resolved unknown COMMIT")
        demand(reference(trace(events[1:]))["status"] == "inconclusive", "Reference failed to keep unknown outcome")
    check("commit-request-rollback-source-remains-unknown", outcome_unknown)

    def late_sync_failure():
        target = run / "final-seal-sync-and-marker-failure"
        w = storage.SegmentedJournal(target)
        demand(w.append(source["events"][0]).accepted, "Fault input not retained")
        w.flush()
        real_sync, real_open = storage._sync_directory, Path.open
        faults = {"finalDirectorySync": 0, "failureMarkerOpen": 0}

        def sync(folder):
            path = Path(folder) / "journal-index.json"
            if path.exists() and json.loads(path.read_bytes()).get("closed") is True:
                faults["finalDirectorySync"] += 1
                raise OSError("injected final sealed-index directory sync failure")
            return real_sync(folder)

        def open_file(path, *args, **kwargs):
            if path.name == "journal-failure.json":
                faults["failureMarkerOpen"] += 1
                raise OSError("injected failure-marker persistence failure")
            return real_open(path, *args, **kwargs)

        close_error = None
        with mock.patch.object(storage, "_sync_directory", sync), mock.patch.object(Path, "open", open_file):
            try:
                w.close(source_closed=True)
            except storage.JournalIOError as error:
                close_error = type(error).__name__
        verified = storage.JournalReader(target).verify()
        details["lateSealFailure"] = {"injectedFaults": faults, "closeErrorClass": close_error,
                                      "verifiedAfterFailedClose": verified.as_dict(),
                                      "failureMarkerPresent": (target / "journal-failure.json").exists(),
                                      "writerLockPresent": (target / "writer.lock").exists()}
        demand(faults["finalDirectorySync"] == 1 and faults["failureMarkerOpen"] == 1, "Both real IO failure paths must execute")
        demand(close_error == "JournalIOError", "A failed sync must not be acknowledged by close")
        demand(not verified.complete, "A failed final sync plus unavailable failure marker left a complete public journal")
    check("failed-final-seal-and-unpersistable-failure-marker-fail-closed", late_sync_failure)

    def wal_archive():
        target = run / "foreign-wal-cache"
        shutil.copytree(good, target)
        cache = sqlite3.connect(target / "transactions.sqlite3")
        archive = run / "foreign-wal.zip"
        try:
            expected_rows = cache.execute("SELECT tx,begin_seq FROM transactions").fetchall()
            cache.execute("PRAGMA journal_mode=WAL")
            cache.execute("PRAGMA wal_autocheckpoint=0")
            cache.execute("DELETE FROM transactions")
            cache.commit()
            cache.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            cache.executemany("INSERT INTO transactions VALUES (?,?)", expected_rows)
            cache.commit()
            verified = storage.JournalReader(target).verify()
            archive_error, restored = None, None
            try:
                storage.JournalReader(target).archive(archive)
                unpacked = run / "foreign-wal-restored"
                with zipfile.ZipFile(archive) as zipped:
                    zipped.extractall(unpacked)
                restored = storage.JournalReader(unpacked).verify().as_dict()
            except storage.JournalVerificationError as error:
                archive_error = type(error).__name__
            details["walArchive"] = {"verifiedWithWal": verified.as_dict(), "archiveErrorClass": archive_error,
                                     "restoredArchive": restored,
                                     "sidecarsDuringVerification": sorted(file.name for file in target.glob("transactions.sqlite3-*"))}
            demand(not verified.complete, "A foreign WAL cache was accepted despite the declared DELETE binding")
            demand(archive_error is not None, "Archive did not reject an unsupported WAL cache")
        finally:
            cache.close()
    check("foreign-wal-cache-cannot-produce-non-restorable-successful-archive", wal_archive)

    def reopen_during_iteration():
        target = run / "reopen-iteration-window"
        shutil.copytree(good, target)
        reader = storage.JournalReader(target)
        iterator = reader.iter_events()
        observed = [next(iterator)]
        paused, resume = threading.Event(), threading.Event()
        original = storage.SegmentedJournal._persist_index
        result = {}

        def pause_initial_index(writer, closed):
            if writer.path == target and not closed:
                paused.set()
                if not resume.wait(5):
                    raise RuntimeError("Bounded reopen probe timed out")
            return original(writer, closed)

        def reopen():
            try:
                result["writer"] = storage.SegmentedJournal.reopen(target, exclusive_continuation=True)
            except Exception as error:
                result["errorClass"] = type(error).__name__

        try:
            with mock.patch.object(storage.SegmentedJournal, "_persist_index", pause_initial_index):
                worker = threading.Thread(target=reopen, daemon=True)
                worker.start()
                demand(paused.wait(3), "Reopen did not reach the owned-lock-before-index-replacement window")
                demand((target / "writer.lock").exists(), "Probe did not hold the real writer lock")
                iteration_error = None
                try:
                    observed.extend(iterator)
                except storage.JournalVerificationError as error:
                    iteration_error = type(error).__name__
                status_during_window = storage.JournalReader(target).verify()
                details["reopenIteration"] = {"iterationErrorClass": iteration_error, "yieldedEvents": len(observed),
                                              "verifiedDuringWindow": status_during_window.as_dict(),
                                              "observationsEqualOriginal": observed == source["events"]}
                resume.set()
                worker.join(5)
                demand(not worker.is_alive(), "Bounded reopen worker failed to terminate")
        finally:
            resume.set()
            if result.get("writer") is not None:
                result["writer"].close(source_closed=True)
        demand(not result.get("errorClass"), "Reopen probe itself failed")
        demand(iteration_error is not None, "The complete-only iterator exhausted successfully while a real reopened writer held its lock")
    check("complete-iterator-detects-real-reopen-before-index-replacement", reopen_during_iteration)
    check("audit-executed-exact-frozen-source-bytes", lambda: demand(
        module_path.read_bytes() == source_bytes and Path(__file__).read_bytes() == audit_bytes,
        "Production journal or independent audit changed during the audit"))

    demand(policy_path.read_bytes() == policy_bytes,
           "Bound durable policy changed during the independent storage audit")
    demand(budget_path.read_bytes() == budget_bytes,
           "Bound experimental budget changed during the independent storage audit")
    receipt = {"schema": 1, "check": "independent-v3-journal-real-file-audit", "actualDatabaseExecution": False,
               "performanceMeasurement": False, "complete": True, "passed": all(case["passed"] for case in checks),
               "sourceSha256": digest(source_bytes), "sourceAfterSha256": digest(module_path.read_bytes()),
               "auditSourceSha256": digest(audit_bytes),
               "dependencySourceBindings": {"integrations/python/moontxnwitness_capture/_durable_policy.py":
                   {"bytes": len(policy_bytes), "sha256": digest(policy_bytes),
                    "afterSha256": digest(policy_path.read_bytes()), "loadedFromExactBoundBytes": True},
                   "integrations/python/moontxnwitness_capture/_experimental_budget.py":
                   {"bytes": len(budget_bytes), "sha256": digest(budget_bytes),
                    "afterSha256": digest(budget_path.read_bytes()), "loadedFromExactBoundBytes": True}},
               "inputFixture": {"path": "fixtures/v3/initial-read-commit.json", "sha256": digest((FIXTURES / "initial-read-commit.json").read_bytes())},
               "rawArtifacts": str(run).replace(str(ROOT), "<workspace>"), "checks": checks, "details": details,
               "boundaries": ["A storage checksum is not database/source authentication", "No garbage collection or database workload was run"]}
    stamp = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(":", "-").replace("+00-00", "Z")
    public = ROOT / "verification/v3" / ("journal-independent-audit-" + stamp + ".json")
    with public.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"passed": receipt["passed"], "checks": len(checks), "failures": [case for case in checks if not case["passed"]],
                      "receipt": public.relative_to(ROOT).as_posix(), "sha256": digest(public.read_bytes())}))
    return 0 if receipt["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--write-fixtures", action="store_true")
    parser.add_argument("--manifest", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--journal-audit", action="store_true")
    parser.add_argument("--scratch", type=Path)
    args = parser.parse_args()
    if args.journal_audit:
        require(args.scratch is not None and args.scratch.is_dir(), "Existing explicit journal scratch directory required")
        return journal_audit(args.scratch)
    if args.write_fixtures:
        print(json.dumps(freeze()))
        return 0
    if args.trace:
        print(json.dumps(reference(args.trace.read_text(encoding="utf-8")), ensure_ascii=True))
        return 0
    report = batch()
    if args.self_test:
        directory = ROOT / "verification/v3"
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(":", "-").replace("+00-00", "Z")
        output = directory / ("oracle-" + stamp + ".json")
        report.update({"sourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       "fixtureManifestSha256": hashlib.sha256((FIXTURES / "manifest.json").read_bytes()).hexdigest(),
                       "protocolCorrectionSha256": hashlib.sha256((FIXTURES / "protocol-correction-1.json").read_bytes()).hexdigest()})
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
        print(json.dumps({"passed": report["passed"], "cases": len(report["cases"]),
                          "failures": [{"id": r["id"], "fields": r["failedExpectedFields"], "summary": r["summary"], "issues": r["reference"]["issues"]} for r in report["cases"] if not r["manualExpectationsPassed"]],
                          "receipt": output.relative_to(ROOT).as_posix()}))
    else:
        print(json.dumps(report, ensure_ascii=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
