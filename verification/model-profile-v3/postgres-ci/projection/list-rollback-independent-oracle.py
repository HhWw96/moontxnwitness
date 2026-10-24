"""Independent append-list reference: enumerate transactions, replay scopes.

No product module is imported. Manual/template expectations are frozen before
production comparison. The interpreter uses whole-state savepoint snapshots,
and exact serial replay includes every committed transaction's original journal.
"""
from __future__ import annotations
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import inspect
import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures/list-v3"
EVIDENCE = ROOT / "verification/list-v3"
SEED = 0x4C495354
SAFE = 9007199254740991
sha = lambda raw: hashlib.sha256(raw).hexdigest()
encoded = lambda obj: json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf8")


class Invalid(ValueError):
    pass


def require(test, reason):
    if not test:
        raise Invalid(reason)


def identifier(value):
    require(isinstance(value, str) and 0 < len(value.encode("utf-16-le")) // 2 <= 256,
            "bounded identifier required")
    require(all(ord(c) >= 32 and ord(c) != 127 for c in value), "identifier control character")
    return value


def integer(value, minimum=0, maximum=SAFE):
    require(type(value) in (int, float) and minimum <= value <= maximum and int(value) == value,
            "safe integer required")
    return int(value)


def fields(value, allowed, required=()):
    require(type(value) is dict and set(value) <= set(allowed) and set(required) <= set(value),
            "unknown/missing field or non-object")


def duplicate_free(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def parse(text):
    require(len(text.encode("utf8")) <= 8 * 1024 * 1024, "trace UTF8 byte budget")
    root = json.loads(text, object_pairs_hook=duplicate_free,
                      parse_constant=lambda _: (_ for _ in ()).throw(Invalid("nonfinite JSON")))
    pending = [(root, 0)]
    while pending:
        value, depth = pending.pop()
        if type(value) in (dict, list):
            require(depth < 64, "JSON depth budget")
            pending.extend((item, depth + 1) for item in (value.values() if type(value) is dict else value))
    return root


def item(value):
    fields(value, ["id", "value"], ["id", "value"])
    identifier(value["id"])
    require(isinstance(value["value"], str), "list values are strings")
    # UTF8 encoding rejects unpaired Unicode surrogates, including in values.
    value["value"].encode("utf8")
    return {"id": value["id"], "value": value["value"]}


EVENT_FIELDS = {
    "snapshot": {"initial", "consistent"}, "begin": {"tx", "connection"},
    "append": {"tx", "key", "id", "value"}, "list_read": {"tx", "key", "items"},
    "savepoint": {"tx", "name", "instance"}, "rollback_to": {"tx", "instance"}, "release": {"tx", "instance"},
    "commit_request": {"tx"}, "commit_ok": {"tx"}, "rollback_ok": {"tx", "commitResponse"}, "disconnect": {"tx"},
    "statement": {"tx", "sql", "parameters"}, "rows": {"tx", "statement", "rows", "complete"},
    "condition": {"tx", "predicate", "matched", "sourceVersion"},
}


def normalize(document):
    issues, effects, transactions, sources, reads = [], [], {}, {}, []
    connections, instances, statements, initial = {}, set(), {}, {}

    def gap(code):
        if code not in issues:
            issues.append(code)

    try:
        trace = parse(document) if isinstance(document, str) else parse(encoded(document).decode())
        fields(trace, ["traceSchema", "dataModel", "clockDomain", "scope", "events", "gaps"],
               ["traceSchema", "dataModel", "clockDomain", "scope", "events", "gaps"])
        require(integer(trace["traceSchema"]) == 3 and trace["dataModel"] == "append-list-v1", "list model discriminator")
        identifier(trace["clockDomain"])
        fields(trace["scope"], ["exclusiveWriters"], ["exclusiveWriters"])
        require(type(trace["scope"]["exclusiveWriters"]) is bool, "writer scope boolean")
        if not trace["scope"]["exclusiveWriters"]:
            gap("writer_scope_unproven")
        require(type(trace["gaps"]) is list, "gaps array")
        for issue in trace["gaps"]:
            fields(issue, ["code", "message"], ["code", "message"])
            identifier(issue["code"])
            require(isinstance(issue["message"], str) and 0 < len(issue["message"]) <= 4096, "gap message")
            gap(issue["code"])
        require(type(trace["events"]) is list and len(trace["events"]) <= 65536, "event budget")
        previous, clock, snapshot, operations = 0, 0, False, 0
        for event in trace["events"]:
            require(type(event) is dict and event.get("kind") in EVENT_FIELDS, "unknown or mixed-model event")
            kind = event["kind"]
            required = {"seq", "time", "kind"} | (EVENT_FIELDS[kind] - {"commitResponse", "parameters", "sourceVersion"})
            fields(event, {"seq", "time", "kind"} | EVENT_FIELDS[kind], required)
            seq, moment = integer(event["seq"], 1), integer(event["time"])
            require(seq > previous and moment >= clock, "sequence/time reversal")
            if seq != previous + 1:
                gap("sequence_gap")
            previous, clock = seq, moment
            if kind == "snapshot":
                require(not snapshot and not transactions, "snapshot position")
                snapshot = True
                require(type(event["consistent"]) is bool and type(event["initial"]) is dict, "snapshot fields")
                if not event["consistent"]:
                    gap("inconsistent_snapshot")
                for key, values in event["initial"].items():
                    identifier(key)
                    require(type(values) is list, "initial lists required")
                    initial[key] = [item(value) for value in values]
                    for value in initial[key]:
                        require(value["id"] not in sources, "global initial identity reuse")
                        sources[value["id"]] = {"key": key, "value": value["value"], "initial": True, "seq": seq}
                continue
            require(snapshot, "snapshot must precede transactions")
            tx_id = identifier(event["tx"])
            if kind == "begin":
                connection = identifier(event["connection"])
                require(tx_id not in transactions and connection not in connections and len(transactions) < 512,
                        "transaction/connection identity or capacity")
                tx = {"id": tx_id, "connection": connection, "status": "unknown", "beginSeq": seq, "endSeq": None,
                      "events": [seq], "active": True, "requested": None, "marks": {}, "activeEffects": [], "journal": []}
                transactions[tx_id], connections[connection] = tx, tx_id
                continue
            require(tx_id in transactions and transactions[tx_id]["active"], "inactive/unknown transaction")
            tx = transactions[tx_id]
            tx["events"].append(seq)
            tx["journal"].append(event)
            if tx["requested"] is not None:
                require(kind in ("commit_ok", "rollback_ok", "disconnect"), "operation after COMMIT request")
            if kind in ("append", "list_read", "condition"):
                operations += 1
                require(operations <= 10000, "normalization operation budget")
            if kind in ("append", "list_read"):
                key = identifier(event["key"])
                if key not in initial:
                    gap("missing_initial")
                if kind == "append":
                    value = item({"id": event["id"], "value": event["value"]})
                    require(value["id"] not in sources, "global append identity reuse")
                    effect = {"seq": seq, "tx": tx_id, "key": key, **value, "revertedBy": None}
                    effects.append(effect)
                    tx["activeEffects"].append(seq)
                    sources[value["id"]] = {**effect, "initial": False, "effect": effect}
                else:
                    require(type(event["items"]) is list, "read item array")
                    values = [item(value) for value in event["items"]]
                    for value in values:
                        # A future producer event does not repair source coverage.
                        if value["id"] not in sources:
                            gap("missing_item_source")
                    reads.append({"seq": seq, "tx": tx_id, "key": key, "items": values,
                                  "activeEffectsAtRead": list(tx["activeEffects"])})
            elif kind == "savepoint":
                name, instance = identifier(event["name"]), identifier(event["instance"])
                require(instance not in instances and len(tx["marks"]) < 64, "scope identity/depth")
                instances.add(instance)
                tx["marks"][instance] = {"seq": seq, "name": name, "activeEffects": list(tx["activeEffects"])}
            elif kind in ("rollback_to", "release"):
                instance = identifier(event["instance"])
                require(instance in tx["marks"], "inactive or foreign savepoint")
                target = tx["marks"][instance]
                require(not any(mark["name"] == target["name"] and mark["seq"] > target["seq"] for mark in tx["marks"].values()),
                        "hidden same-name savepoint")
                if kind == "rollback_to":
                    keep = set(target["activeEffects"])
                    for effect in effects:
                        if effect["seq"] in tx["activeEffects"] and effect["seq"] not in keep:
                            effect["revertedBy"] = seq
                    tx["activeEffects"] = list(target["activeEffects"])
                tx["marks"] = {identity: mark for identity, mark in tx["marks"].items()
                               if mark["seq"] < target["seq"] or kind == "rollback_to" and identity == instance}
            elif kind == "commit_request":
                require(tx["requested"] is None, "duplicate COMMIT request")
                tx["requested"] = seq
            elif kind in ("commit_ok", "rollback_ok", "disconnect"):
                reliable_rollback = False
                if "commitResponse" in event:
                    response = event["commitResponse"]
                    require(kind == "rollback_ok" and tx["requested"] is not None and type(response) is dict,
                            "COMMIT response without matching request")
                    require(integer(response.get("request"), 1) == tx["requested"], "wrong COMMIT response request")
                    if "commandTag" in response:
                        fields(response, ["request", "commandTag"], ["request", "commandTag"])
                        require(response["commandTag"] == "ROLLBACK", "untrusted COMMIT command tag")
                    else:
                        fields(response, ["request", "sqlstate", "diagnosticSqlstate", "transactionStatus"],
                               ["request", "sqlstate", "diagnosticSqlstate", "transactionStatus"])
                        require(response["sqlstate"] in ("40001", "40P01") and response["diagnosticSqlstate"] == response["sqlstate"]
                                and response["transactionStatus"] == "IDLE", "untrusted COMMIT error diagnostic")
                    reliable_rollback = True
                if kind == "commit_ok":
                    require(tx["requested"] is not None, "COMMIT acknowledgement without request")
                    tx["status"] = "committed"
                elif kind == "rollback_ok" and (tx["requested"] is None or reliable_rollback):
                    tx["status"] = "aborted"
                    for effect in effects:
                        if effect["seq"] in tx["activeEffects"]:
                            effect["revertedBy"] = seq
                    tx["activeEffects"] = []
                else:
                    gap("unknown_commit")
                tx["active"], tx["endSeq"] = False, seq
                del connections[tx["connection"]]
            elif kind == "statement":
                require(isinstance(event["sql"], str) and 0 < len(event["sql"]) <= 65536, "SQL text")
                statements[seq] = {"tx": tx_id, "seen": False, "complete": False}
                gap("unmapped_statement")
            elif kind == "rows":
                statement = integer(event["statement"], 1)
                require(statement in statements and statements[statement]["tx"] == tx_id and not statements[statement]["complete"],
                        "row source statement")
                require(type(event["rows"]) is list and type(event["complete"]) is bool, "rows shape")
                statements[statement].update(seen=True, complete=event["complete"])
            elif kind == "condition":
                require(type(event["matched"]) is bool, "predicate result boolean")
                if "sourceVersion" in event:
                    identifier(event["sourceVersion"])
                gap("unsupported_condition")
        if not snapshot:
            gap("missing_snapshot")
        if any(tx["active"] for tx in transactions.values()):
            gap("outstanding_transaction")
        if any(statement["seen"] and not statement["complete"] for statement in statements.values()):
            gap("incomplete_rows")
        public = [{key: tx[key] for key in ("id", "connection", "status", "beginSeq", "endSeq", "events")}
                  | {"finalWrites": list(tx["activeEffects"])} for tx in transactions.values()]
        return {"status": "inconclusive" if issues else "ready", "complete": not issues, "issues": issues,
                "observations": trace["events"], "effects": effects, "transactions": public,
                "initial": initial, "operations": operations, "journals": transactions, "reads": reads, "sources": sources}
    except (Invalid, ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError) as error:
        return {"status": "invalid", "complete": False, "issues": ["invalid_capture_v3"], "reason": str(error)}


def serial_replay(normalized, max_states=100000, max_operation_checks=1000000):
    """Enumerate whole TX permutations; no dependency graph or production code."""
    committed = [tx for tx in normalized["journals"].values() if tx["status"] == "committed"]
    if len(committed) > 6 or normalized["operations"] > 128:
        return {"status": "inconclusive", "reason": "capacity", "states": 0, "operationChecks": 0, "witness": None}
    states, checks = 0, 0
    for order in itertools.permutations(committed):
        if states >= max_states:
            return {"status": "inconclusive", "reason": "state_budget", "states": states, "operationChecks": checks, "witness": None}
        states += 1
        state, valid = copy.deepcopy(normalized["initial"]), True
        for tx in order:
            local, marks = copy.deepcopy(state), {}
            for event in tx["journal"]:
                kind = event["kind"]
                if kind in ("append", "list_read"):
                    if checks >= max_operation_checks:
                        return {"status": "inconclusive", "reason": "operation_budget", "states": states, "operationChecks": checks, "witness": None}
                    checks += 1
                    if kind == "append":
                        local[event["key"]].append({"id": event["id"], "value": event["value"]})
                    elif local[event["key"]] != event["items"]:
                        valid = False
                        break
                elif kind == "savepoint":
                    marks[event["instance"]] = {"seq": event["seq"], "state": copy.deepcopy(local)}
                elif kind in ("rollback_to", "release"):
                    target = marks[event["instance"]]
                    if kind == "rollback_to":
                        local = copy.deepcopy(target["state"])
                    marks = {identity: mark for identity, mark in marks.items()
                             if mark["seq"] < target["seq"] or kind == "rollback_to" and identity == event["instance"]}
            if not valid:
                break
            state = local
        if valid:
            return {"status": "consistent", "reason": "serial_witness", "states": states, "operationChecks": checks,
                    "witness": [tx["id"] for tx in order]}
    return {"status": "violation", "reason": "no_serial_execution", "states": states, "operationChecks": checks, "witness": None}


def reference(document, options=None):
    normalized = normalize(document)
    result = {"independentReference": True, "normalization": normalized["status"], "coverageComplete": normalized["complete"],
              "issues": normalized["issues"], "normalized": normalized, "analysis": normalized["status"]}
    if normalized["status"] != "ready":
        return result
    try:
        opts = {} if options is None else options
        fields(opts, ["maxStates", "maxOperationChecks"])
        max_states = integer(opts.get("maxStates", 100000), 0, 100000)
        max_checks = integer(opts.get("maxOperationChecks", 1000000), 0, 1000000)
    except (Invalid, TypeError, ValueError, OverflowError) as error:
        result.update(analysis="invalid", optionError=str(error))
        return result
    exact = serial_replay(normalized, max_states, max_checks)
    result.update(analysis=exact["status"], exact=exact)
    return result


def event(kind, tx="T", **extra):
    return {"kind": kind, "tx": tx, **extra}


def make_trace(events, initial=None):
    base = {"kind": "snapshot", "initial": initial if initial is not None else {"x": [{"id": "x0", "value": "same"}],
                                                                                 "y": [{"id": "y0", "value": "same"}]}, "consistent": True}
    return {"traceSchema": 3, "dataModel": "append-list-v1", "clockDomain": "independent-list-clock",
            "scope": {"exclusiveWriters": True}, "events": [{"seq": i + 1, "time": i, **value} for i, value in enumerate([base] + events)], "gaps": []}


def manual():
    cases = []
    def b(tx="T", connection="C"): return event("begin", tx, connection=connection)
    def a(identity="x1", tx="T", key="x", value="same"): return event("append", tx, key=key, id=identity, value=value)
    def r(ids=("x0",), tx="T", key="x", values=None):
        return event("list_read", tx, key=key, items=[{"id": identity, "value": (values or ["same"] * len(ids))[i]} for i, identity in enumerate(ids)])
    def sp(identity="s1", name="scope"): return event("savepoint", instance=identity, name=name)
    def done(tx="T"): return [event("commit_request", tx), event("commit_ok", tx)]
    def add(name, events, analysis="consistent", normalization="ready", issue=None, options=None, initial=None):
        expected = {"normalization": normalization, "analysis": analysis}
        if issue: expected["issue"] = issue
        cases.append({"id": name, "trace": make_trace(events, initial), "options": options or {}, "expected": expected})
    add("empty-snapshot", [])
    add("initial-read", [b(), r(), *done()])
    add("single-append", [b(), a(), *done()])
    add("same-business-values-distinct-identities", [b(), a(), r(("x0", "x1")), *done()])
    add("initial-duplicate-business-values", [b(), r(("i1", "i2")), *done()], initial={"x": [{"id": "i1", "value": "same"}, {"id": "i2", "value": "same"}]})
    add("own-read-after-append", [b(), a(), r(("x0", "x1")), *done()])
    add("multiple-appends-same-key", [b(), a(), a("x2"), r(("x0", "x1", "x2")), *done()])
    add("own-read-omits-earlier-append", [b(), a(), a("x2"), r(("x0", "x2")), *done()], "violation")
    add("own-read-reorders-appends", [b(), a(), a("x2"), r(("x0", "x2", "x1")), *done()], "violation")
    add("read-reorders-initial", [b(), r(("i2", "i1")), *done()], "violation", initial={"x": [{"id": "i1", "value": "same"}, {"id": "i2", "value": "same"}]})
    add("read-truncates-initial", [b(), r(()), *done()], "violation")
    add("read-duplicates-identity", [b(), r(("x0", "x0")), *done()], "violation")
    add("known-identity-wrong-value", [b(), r(values=["wrong"]), *done()], "violation")
    add("known-identity-wrong-key", [b(), r(("y0",)), *done()], "violation")
    add("empty-initial-list", [b(), r(()), a(), r(("x1",)), *done()], initial={"x": []})
    add("two-key-read-append-cycle", [b(), b("U", "D"), r(), r(("y0",), "U", "y"), a("y1", key="y"), a(tx="U"), *done(), *done("U")], "violation")
    add("three-transaction-cycle", [b(), b("U", "D"), b("V", "E"), r(), a("y1", key="y"), r(("y0",), "U", "y"), a("z1", "U", "z"), r(("z0",), "V", "z"), a("x1", "V"), *done(), *done("U"), *done("V")], "violation", initial={key: [{"id": key + "0", "value": "same"}] for key in ("x", "y", "z")})
    add("external-append-visible", [b(), a(), *done(), b("U", "D"), r(("x0", "x1"), "U"), *done("U")])
    add("producer-commit-ack-can-arrive-later", [b(), a(), event("commit_request"), b("U", "D"), r(("x0", "x1"), "U"), event("commit_ok"), *done("U")])
    add("unknown-item-source", [b(), r(("x0", "missing")), *done()], "inconclusive", "inconclusive", "missing_item_source")
    add("future-producer-does-not-repair-source", [b(), r(("x0", "later")), *done(), b("U", "D"), a("later", "U"), *done("U")], "inconclusive", "inconclusive", "missing_item_source")
    add("read-from-aborted-append", [b(), a(), event("rollback_ok"), b("U", "D"), r(("x0", "x1"), "U"), *done("U")], "violation")
    add("external-read-from-reverted-append", [b(), sp(), a(), event("rollback_to", instance="s1"), *done(), b("U", "D"), r(("x0", "x1"), "U"), *done("U")], "violation")
    add("own-read-before-later-rollback-valid", [b(), sp(), a(), r(("x0", "x1")), event("rollback_to", instance="s1"), r(), *done()])
    add("own-read-after-rollback-invalid-model", [b(), sp(), a(), event("rollback_to", instance="s1"), r(("x0", "x1")), *done()], "violation")
    add("aborted-known-anomalous-read-not-opacity", [b(), r(("x0", "x0"), values=["wrong", "same"]), event("rollback_ok")])
    add("aborted-unknown-item-still-coverage-gap", [b(), r(("missing",)), event("rollback_ok")], "inconclusive", "inconclusive", "missing_item_source")
    add("whole-rollback-revokes-all-appends", [b(), a(), a("x2"), event("rollback_ok")])
    add("release-is-not-commit", [b(), sp(), a(), event("release", instance="s1")], "inconclusive", "inconclusive", "outstanding_transaction")
    add("release-child-parent-rollback", [b(), sp("outer", "outer"), sp("inner", "inner"), a(), event("release", instance="inner"), r(("x0", "x1")), event("rollback_to", instance="outer"), *done()])
    add("same-name-distinct-instances", [b(), sp("old"), a(), sp("new"), a("x2"), event("rollback_to", instance="new"), event("release", instance="new"), event("release", instance="old"), *done()])
    for action in ("rollback_to", "release"):
        add("hidden-name-" + action, [b(), sp("old"), sp("new"), event(action, instance="old"), *done()], "invalid", "invalid")
    add("released-instance-cannot-be-reused", [b(), sp(), event("release", instance="s1"), sp()], "invalid", "invalid")
    add("rollback-destroys-descendant", [b(), sp("outer", "outer"), sp("inner", "inner"), event("rollback_to", instance="outer"), event("release", instance="inner")], "invalid", "invalid")
    add("foreign-savepoint", [b(), sp(), b("U", "D"), event("rollback_to", "U", instance="s1")], "invalid", "invalid")
    add("rollback-target-remains-active", [b(), sp(), a(), event("rollback_to", instance="s1"), a("x2"), event("rollback_to", instance="s1"), *done()])
    add("commit-ack-without-request", [b(), event("commit_ok")], "invalid", "invalid")
    add("duplicate-commit-request", [b(), event("commit_request"), event("commit_request")], "invalid", "invalid")
    add("operation-after-commit-request", [b(), event("commit_request"), r()], "invalid", "invalid")
    add("disconnect-keeps-unknown", [b(), a(), event("commit_request"), event("disconnect")], "inconclusive", "inconclusive", "unknown_commit")
    add("idle-rollback-cannot-resolve-commit", [b(), a(), event("commit_request"), event("rollback_ok")], "inconclusive", "inconclusive", "unknown_commit")
    add("sequential-connection-reuse", [b(), *done(), b("U"), r(tx="U"), *done("U")])
    add("connection-reuse-does-not-cure-unknown", [b(), event("disconnect"), b("U"), *done("U")], "inconclusive", "inconclusive", "unknown_commit")
    add("overlapping-connection-reuse", [b(), b("U")], "invalid", "invalid")
    add("transaction-id-reuse", [b(), *done(), b()], "invalid", "invalid")
    add("append-id-reuse-across-keys", [b(), a(), a("x1", key="y")], "invalid", "invalid")
    add("initial-id-global-reuse", [], "invalid", "invalid", initial={"x": [{"id": "same", "value": "v"}], "y": [{"id": "same", "value": "v"}]})
    add("append-reuses-initial-id", [b(), a("x0")], "invalid", "invalid")
    add("mixed-register-write-rejected", [b(), event("write", key="x", version="v", predecessor="x0")], "invalid", "invalid")
    add("wrong-model-discriminator", [b(), *done()], "invalid", "invalid")
    cases[-1]["trace"]["dataModel"] = "register-v1"
    add("sequence-gap", [b(), r(), *done()], "inconclusive", "inconclusive", "sequence_gap")
    for value in cases[-1]["trace"]["events"][2:]: value["seq"] += 1
    add("duplicate-sequence", [b(), r(), *done()], "invalid", "invalid")
    cases[-1]["trace"]["events"][2]["seq"] = 2
    add("backwards-clock", [b(), r(), *done()], "invalid", "invalid")
    cases[-1]["trace"]["events"][3]["time"] = 0
    add("unproven-writer-scope", [b(), r(), *done()], "inconclusive", "inconclusive", "writer_scope_unproven")
    cases[-1]["trace"]["scope"]["exclusiveWriters"] = False
    add("inconsistent-snapshot", [b(), r(), *done()], "inconclusive", "inconclusive", "inconsistent_snapshot")
    cases[-1]["trace"]["events"][0]["consistent"] = False
    add("explicit-log-gap", [b(), r(), *done()], "inconclusive", "inconclusive", "log_failed")
    cases[-1]["trace"]["gaps"] = [{"code": "log_failed", "message": "Injected lost source record"}]
    add("missing-key-not-inferred", [b(), r((), key="unknown"), *done()], "inconclusive", "inconclusive", "missing_initial")
    add("seven-committed-exceeds-capacity", [value for i in range(7) for value in [b("T" + str(i)), *done("T" + str(i))]], "inconclusive")
    add("129-operations-exceeds-capacity", [b(), *[r() for _ in range(129)], *done()], "inconclusive")
    add("zero-state-budget", [b(), r(), *done()], "inconclusive", options={"maxStates": 0})
    add("zero-operation-budget", [b(), r(), *done()], "inconclusive", options={"maxOperationChecks": 0})
    add("negative-options-invalid", [b(), r(), *done()], "invalid", options={"maxStates": -1})
    add("non-string-append-value-invalid", [b(), a(value=1)], "invalid", "invalid")
    for label, response in [("command-tag", {"request": 4, "commandTag": "ROLLBACK"}),
                            ("serialization-error", {"request": 4, "sqlstate": "40001", "diagnosticSqlstate": "40001", "transactionStatus": "IDLE"}),
                            ("deadlock-error", {"request": 4, "sqlstate": "40P01", "diagnosticSqlstate": "40P01", "transactionStatus": "IDLE"})]:
        add("reliable-commit-rollback-" + label, [b(), a(), event("commit_request"), event("rollback_ok", commitResponse=response)])
    for label, response in [("wrong-request", {"request": 3, "commandTag": "ROLLBACK"}),
                            ("wrong-tag", {"request": 4, "commandTag": "COMMIT"}),
                            ("mismatched-sqlstate", {"request": 4, "sqlstate": "40001", "diagnosticSqlstate": "40P01", "transactionStatus": "IDLE"}),
                            ("wrong-transaction-status", {"request": 4, "sqlstate": "40001", "diagnosticSqlstate": "40001", "transactionStatus": "INERROR"})]:
        add("untrusted-commit-rollback-" + label, [b(), a(), event("commit_request"), event("rollback_ok", commitResponse=response)], "invalid", "invalid")
    return cases


def generated(count=10000, seed=SEED):
    """Independent handwritten families; xorshift32 is stable across Python versions."""
    state = seed
    for index in range(count):
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= state >> 17
        state ^= (state << 5) & 0xFFFFFFFF
        state &= 0xFFFFFFFF
        value = ("same", "业务重复值", "", "alpha", "beta")[state % 5]
        initial = {key: [{"id": key + "0", "value": value}] for key in ("x", "y")}
        def b(tx="T", connection="C"): return event("begin", tx, connection=connection)
        def a(identity="x1", tx="T", key="x"): return event("append", tx, key=key, id=identity, value=value)
        def r(ids=("x0",), tx="T", key="x"):
            return event("list_read", tx, key=key, items=[{"id": identity, "value": value} for identity in ids])
        def done(tx="T"): return [event("commit_request", tx), event("commit_ok", tx)]
        family = index % 12
        normalization, verdict, issue = "ready", "consistent", None
        if family == 0:
            events = [b(), a(), r(("x0", "x1")), *done()]
        elif family == 1:
            events = [b(), b("U", "D"), r(), r(("y0",), "U", "y"), a("y1", key="y"), a(tx="U"), *done(), *done("U")]
            verdict = "violation"
        elif family == 2:
            events = [b(), a(), a("x2"), r(("x0", "x2")), *done()]
            verdict = "violation"
        elif family == 3:
            events = [b(), r(("x0", "x0")), *done()]
            verdict = "violation"
        elif family == 4:
            events = [b(), r(("x0", "missing")), *done()]
            normalization, verdict, issue = "inconclusive", "inconclusive", "missing_item_source"
        elif family == 5:
            events = [b(), a(), event("commit_request"), event("disconnect")]
            normalization, verdict, issue = "inconclusive", "inconclusive", "unknown_commit"
        elif family == 6:
            events = [b(), event("savepoint", name="scope", instance="s"), a(), r(("x0", "x1")), event("rollback_to", instance="s"), r(), *done()]
        elif family == 7:
            events = [b(), a(), event("rollback_ok"), b("U", "D"), r(("x0", "x1"), "U"), *done("U")]
            verdict = "violation"
        elif family == 8:
            events = [b(), a(), event("commit_request"), b("U", "D"), r(("x0", "x1"), "U"), event("commit_ok"), *done("U")]
        elif family == 9:
            events = [b(), r(("y0",), key="x"), event("rollback_ok")]
        elif family == 10:
            events = [b(), a(), a("x2"), r(("x0", "x2", "x1")), *done()]
            verdict = "violation"
        else:
            n = 2 + state % 5
            events = [record for i in range(n) for record in [b("T" + str(i)), a("a" + str(i), "T" + str(i)), *done("T" + str(i))]]
        expected = {"normalization": normalization, "analysis": verdict}
        if issue: expected["issue"] = issue
        yield {"id": "generated-" + str(index).zfill(5), "family": family, "trace": make_trace(events, initial), "options": {}, "expected": expected}


def generator_hash():
    return sha((inspect.getsource(generated) + inspect.getsource(make_trace) + inspect.getsource(event)).encode())


def generated_unique(count=10000, seed=SEED ^ 0x41AD):
    """Expand semantic templates with nontrivial scope/program/key variation.

    Added writes inside immediately rolled-back scopes have no committed effect;
    independent noise appends touch only z. The original family verdict therefore
    remains manually justified without consulting either analyzer implementation.
    """
    state = seed
    for index, original in enumerate(generated(count, seed)):
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= state >> 17
        state ^= (state << 5) & 0xFFFFFFFF
        state &= 0xFFFFFFFF
        trace = copy.deepcopy(original["trace"])
        initial = trace["events"][0]["initial"]
        for ordinal, key in enumerate(("x", "y")):
            for extra in range((state >> (ordinal * 3)) % 3):
                initial[key].append({"id": key + "0-extra" + str(extra), "value": ("same", "业务重复值")[extra % 2]})
        initial["z"] = [{"id": "z0-" + str(extra), "value": "same"} for extra in range((state >> 7) % 3)]
        events = []
        for current in trace["events"][1:]:
            if current["kind"] == "list_read":
                expanded = []
                for value in current["items"]:
                    key = value["id"][:1]
                    if value["id"] in ("x0", "y0"):
                        expanded.extend(copy.deepcopy(initial[key]))
                    else:
                        expanded.append(value)
                current["items"] = expanded
            events.append(current)
            if original["family"] == 11 and current["kind"] == "append":
                for extra in range((state >> (len(events) % 19)) % 4):
                    events.append({**current, "id": current["id"] + "-burst" + str(extra)})
        wrapped, active_marks = [], {}
        for current in events:
            tx = current["tx"]
            if current["kind"] == "begin":
                wrapped.append(current)
                if (state >> (len(wrapped) % 23)) & 1:
                    instance = "generated_scope_" + tx
                    active_marks[tx] = instance
                    wrapped.append(event("savepoint", tx, name="generated_scope", instance=instance))
                    if (state >> (len(wrapped) % 17)) & 1:
                        wrapped.append(event("append", tx, key="z", id="revoked_" + tx, value="temporary"))
                        wrapped.append(event("rollback_to", tx, instance=instance))
            else:
                if current["kind"] in ("commit_request", "rollback_ok", "disconnect") and tx in active_marks:
                    wrapped.append(event("release", tx, instance=active_marks.pop(tx)))
                wrapped.append(current)
        committed = sum(value["kind"] == "commit_ok" for value in wrapped)
        noise_count = (state >> 12) % (min(2, 6 - committed) + 1)
        for noise in range(noise_count):
            tx = "Noise" + str(noise)
            program = [event("begin", tx, connection="noise_connection_" + str(noise))]
            program.extend(event("append", tx, key="z", id="noise_" + str(noise) + "_" + str(j), value="same")
                           for j in range(1 + ((state >> (noise + 15)) % 3)))
            program.extend([event("commit_request", tx), event("commit_ok", tx)])
            insertion = (state >> (noise + 4)) % (len(wrapped) + 1)
            wrapped[insertion:insertion] = program
        trace["events"] = [trace["events"][0]] + wrapped
        prefix = "u" + str(index).zfill(5) + ":" + ("#" * ((state >> 18) % 97)) + "|"
        key_map = {key: "k" + str(index % 13) + ":" + key for key in initial}
        trace["events"][0]["initial"] = {key_map[key]: [{**value, "id": prefix + value["id"]} for value in values]
                                          for key, values in initial.items()}
        for sequence, current in enumerate(trace["events"], 1):
            current["seq"], current["time"] = sequence, sequence - 1
            if "key" in current:
                current["key"] = key_map[current["key"]]
            if current["kind"] == "append":
                current["id"] = prefix + current["id"]
            elif current["kind"] == "list_read":
                current["items"] = [{**value, "id": prefix + value["id"]} for value in current["items"]]
        yield {"id": "generated-unique-" + str(index).zfill(5), "family": original["family"], "trace": trace,
               "options": {}, "expected": original["expected"]}


def unique_generator_hash():
    return sha((inspect.getsource(generated_unique) + inspect.getsource(generated)
                + inspect.getsource(make_trace) + inspect.getsource(event)).encode())


def freeze_unique():
    require(not (FIXTURES / "extension-unique.json").exists(), "Unique corpus already frozen")
    original_manifest = json.loads((FIXTURES / "manifest.json").read_bytes())
    prior_hashes = {record["inputSha256"] for binding in original_manifest["files"]
                    for record in json.loads((ROOT / binding["file"]).read_bytes())}
    path, hashes, features = FIXTURES / "unique-10000.json", set(), set()
    with path.open("xb") as stream:
        stream.write(b"[\n")
        for index, record in enumerate(generated_unique()):
            trace = record.pop("trace")
            feature = (record["family"], tuple(len(value) for value in trace["events"][0]["initial"].values()),
                       tuple(event["kind"] for event in trace["events"]))
            features.add(feature)
            text = encoded(trace).decode()
            digest = sha(text.encode())
            require(digest not in hashes and digest not in prior_hashes, "Unique corpus input duplicated")
            hashes.add(digest)
            entry = {**record, "traceText": text, "inputSha256": digest}
            stream.write((b",\n" if index else b"") + encoded(entry))
        stream.write(b"\n]\n")
    binding = {"file": path.relative_to(ROOT).as_posix(), "cases": len(hashes), "bytes": path.stat().st_size,
               "sha256": sha(path.read_bytes())}
    manifest = {"schema": 1, "originalManifestSha256": sha((FIXTURES / "manifest.json").read_bytes()),
                "seed": SEED ^ 0x41AD, "generatorSourceSha256": unique_generator_hash(),
                "uniqueInputSha256Count": len(hashes), "overlapWithOriginalInputHashes": 0,
                "distinctProgramAndInitialLengthShapes": len(features),
                "originalGeneratedRecords": 10000, "originalUniqueGeneratedInputHashes": len({record["inputSha256"] for record in json.loads((FIXTURES / "generated-10000.json").read_bytes())}),
                "originalArtifactsModified": False,
                "expectations": "Original handwritten semantic families; independent noise writes and scope-reverted temporary appends do not alter family verdicts",
                "variation": ["initial list lengths", "per-transaction append bursts", "savepoint/release programs",
                              "scope-reverted temporary appends", "noise transaction count and placement", "key and item identity lengths"],
                "files": [binding]}
    with (FIXTURES / "extension-unique.json").open("xb") as stream:
        stream.write(json.dumps(manifest, indent=2).encode() + b"\n")
    return manifest


def freeze():
    require(not (FIXTURES / "manifest.json").exists(), "Frozen list corpus already exists; never rewrite expectations")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    bindings = []
    for filename, records in (("manual.json", manual()), ("generated-10000.json", generated())):
        path, count = FIXTURES / filename, 0
        with path.open("xb") as stream:
            stream.write(b"[\n")
            for record in records:
                text = encoded(record.pop("trace")).decode()
                entry = {**record, "traceText": text, "inputSha256": sha(text.encode())}
                stream.write((b",\n" if count else b"") + encoded(entry))
                count += 1
            stream.write(b"\n]\n")
        bindings.append({"file": path.relative_to(ROOT).as_posix(), "cases": count, "bytes": path.stat().st_size, "sha256": sha(path.read_bytes())})
    manifest = {"schema": 1, "contract": "append-list-v1", "seed": SEED, "generator": "xorshift32 + 12 handwritten semantic families",
                "generatorSourceSha256": generator_hash(), "frozenOracleSourceSha256": sha(Path(__file__).read_bytes()),
                "expectedSource": "Handwritten case/family outcomes fixed independently before any production result comparison",
                "committedTransactionsOnly": True, "scopeReplayIncludesRevertedOwnReadObservations": True,
                "unknownItemsRemainCoverageGapsIncludingAbortedReads": True, "serverCommitAcknowledgementOrderIsNotCommitOrder": True,
                "automaticG2OrPLClassification": False, "files": bindings}
    with (FIXTURES / "manifest.json").open("xb") as stream:
        stream.write(json.dumps(manifest, indent=2).encode() + b"\n")
    return manifest


def corpus_records():
    manifest = json.loads((FIXTURES / "manifest.json").read_bytes())
    require(manifest["generatorSourceSha256"] == generator_hash(), "Frozen generator changed")
    bindings = list(manifest["files"])
    if (FIXTURES / "extension-unique.json").exists():
        extension = json.loads((FIXTURES / "extension-unique.json").read_bytes())
        require(extension["originalManifestSha256"] == sha((FIXTURES / "manifest.json").read_bytes()), "Original corpus provenance changed")
        require(extension["generatorSourceSha256"] == unique_generator_hash(), "Frozen unique generator changed")
        bindings.extend(extension["files"])
    for binding in bindings:
        raw = (ROOT / binding["file"]).read_bytes()
        require(len(raw) == binding["bytes"] and sha(raw) == binding["sha256"], "Frozen corpus bytes changed")
        records = json.loads(raw)
        require(len(records) == binding["cases"], "Corpus case count changed")
        for record in records:
            require(sha(record["traceText"].encode()) == record["inputSha256"], "Frozen original input digest mismatch")
            yield record


def batch():
    results, failures = [], []
    for case in corpus_records():
        actual = reference(case["traceText"], case["options"])
        fields_failed = [name for name in ("normalization", "analysis") if actual[name] != case["expected"][name]]
        if case["expected"].get("issue") not in actual["issues"] and case["expected"].get("issue"):
            fields_failed.append("issue")
        record = {"id": case["id"], "inputSha256": case["inputSha256"], "normalization": actual["normalization"],
                  "analysis": actual["analysis"], "issues": actual["issues"], "passed": not fields_failed,
                  "referenceResultSha256": sha(encoded(actual))}
        results.append(record)
        if fields_failed:
            failures.append({"id": case["id"], "fields": fields_failed, "expected": case["expected"], "actual": actual})
    return {"schema": 1, "independentReference": True, "passed": not failures, "cases": len(results),
            "manualCases": len(manual()), "generatedCases": len(results) - len(manual()), "actualDatabaseExecution": False,
            "distinctInputHashes": len({result["inputSha256"] for result in results}),
            "automaticG2OrPLClassification": False, "results": results, "failures": failures}


def verify_orders(path):
    cases = {case["id"]: case for case in corpus_records()}
    outcomes = []
    for supplied in json.loads(path.read_bytes()):
        identity, order = supplied["id"], supplied["order"]
        try:
            case = cases[identity]
            normalized = normalize(case["traceText"])
            require(normalized["status"] == "ready", "Witness supplied for incomplete input")
            journals = normalized["journals"]
            committed = [tx["id"] for tx in journals.values() if tx["status"] == "committed"]
            require(type(order) is list and len(order) == len(set(order)) and set(order) == set(committed),
                    "Witness must contain each committed TX exactly once")
            # Enumerating at most one candidate now forces the independently
            # implemented scope interpreter to check this supplied order.
            normalized["journals"] = {tx: journals[tx] for tx in order + [tx for tx in journals if tx not in order]}
            replayed = serial_replay(normalized, max_states=1)
            require(replayed["status"] == "consistent", "Supplied order does not independently replay all committed observations")
            outcomes.append({"id": identity, "passed": True})
        except (Invalid, TypeError, KeyError, ValueError) as error:
            outcomes.append({"id": identity, "passed": False, "reason": str(error)})
    return {"independentReference": True, "passed": all(result["passed"] for result in outcomes),
            "checkedOrders": len(outcomes), "results": outcomes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--freeze-unique", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--options", type=Path)
    parser.add_argument("--manual-results", action="store_true")
    parser.add_argument("--verify-orders", type=Path)
    args = parser.parse_args()
    if args.freeze:
        result = freeze()
        print(json.dumps({"frozen": True, "files": result["files"], "generatorSourceSha256": result["generatorSourceSha256"]}))
        return 0
    if args.freeze_unique:
        result = freeze_unique()
        print(json.dumps(result))
        return 0
    if args.trace:
        print(json.dumps(reference(args.trace.read_text(encoding="utf8"), json.loads(args.options.read_bytes()) if args.options else None), ensure_ascii=True))
        return 0
    if args.manual_results:
        cases = [case for case in corpus_records() if not case["id"].startswith("generated-")]
        print(json.dumps({"cases": [{"id": case["id"], "reference": reference(case["traceText"], case["options"])} for case in cases]}, ensure_ascii=True))
        return 0
    if args.verify_orders:
        result = verify_orders(args.verify_orders)
        print(json.dumps(result))
        return 0 if result["passed"] else 1
    result = batch()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(":", "-").replace("+00-00", "Z")
    output = EVIDENCE / ("oracle-" + stamp + ".json")
    result.update({"sourceSha256": sha(Path(__file__).read_bytes()), "manifestSha256": sha((FIXTURES / "manifest.json").read_bytes())})
    with output.open("xb") as stream:
        stream.write(json.dumps(result, indent=2).encode() + b"\n")
    print(json.dumps({"passed": result["passed"], "cases": result["cases"], "manualCases": result["manualCases"],
                      "generatedCases": result["generatedCases"], "failures": [{"id": item["id"], "fields": item["fields"]} for item in result["failures"]],
                      "receipt": output.relative_to(ROOT).as_posix(), "sha256": sha(output.read_bytes())}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
