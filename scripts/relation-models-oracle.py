"""Independent bounded original-program relation reference.

No production library or dependency-graph imports are used. Serial decisions
enumerate transaction orders and replay the original row programs. RC and SI
add independently enumerated committed-prefix certificates. Those sufficient
operational certificates do NOT turn unsuccessful weak-model searches into
fixed-Adya refutations. Unimplemented weak-model completion stays pending.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
import hashlib
import itertools
import json
from pathlib import Path
import re
import sys


MODELS = (
    "read-uncommitted", "read-committed", "repeatable-read", "serializable",
    "strict-serializable", "snapshot-isolation", "consistent-view",
    "strong-session-read-uncommitted", "strong-read-uncommitted",
    "strong-session-read-committed", "strong-read-committed",
    "strong-session-serializable", "strong-session-snapshot-isolation",
    "strong-snapshot-isolation",
)
SERIAL_MODELS = {"serializable", "strict-serializable", "strong-session-serializable"}
RU_MODELS = {"read-uncommitted", "strong-session-read-uncommitted", "strong-read-uncommitted"}
RC_MODELS = {"read-committed", "strong-session-read-committed", "strong-read-committed"}
SI_MODELS = {"snapshot-isolation", "strong-session-snapshot-isolation", "strong-snapshot-isolation"}
SESSION_MODELS = {m for m in MODELS if m.startswith("strong-session-")}
REALTIME_MODELS = {"strict-serializable", "strong-read-uncommitted", "strong-read-committed", "strong-snapshot-isolation"}
DECIMAL = re.compile(r"(?:0|-[1-9][0-9]*|[1-9][0-9]*)\Z")
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}\Z")
MAX_STATES, MAX_CHECKS = 100000, 1000000
MAX_TX, MAX_OPS = 6, 128
FORMAT = "moontxnwitness-independent-relation-model-oracle/v1"
DEFINITION = "original-relation-program-serial-and-prefix-certificates/v1"


class Invalid(ValueError):
    pass


class Exhausted(Exception):
    pass


def need(condition, message):
    if not condition:
        raise Invalid(message)


def text(value):
    need(isinstance(value, str) and not any(0xD800 <= ord(c) <= 0xDFFF for c in value), "Unicode scalar text required")
    return value


def ident(value):
    text(value)
    need(1 <= sum(2 if ord(c) > 0xFFFF else 1 for c in value) <= 256, "identity length")
    return value


def fields(value, required, optional=()):
    need(isinstance(value, dict), "object required")
    need(set(required) <= set(value) <= set(required) | set(optional), "unsupported or missing field")


def scalar(kind, value):
    if kind == "int64":
        need(isinstance(value, str) and DECIMAL.fullmatch(value), "canonical int64 text required")
        number = int(value)
        need(-(1 << 63) <= number < (1 << 63), "int64 range")
        return number
    if kind == "bool":
        need(type(value) is bool, "boolean required")
        return value
    need(kind == "text", "unsupported scalar type")
    return text(value)


def decode(source):
    if not isinstance(source, str):
        # Apply the same JSON-domain and byte boundary to object callers.
        source = json.dumps(source, ensure_ascii=False, allow_nan=False)
    need(len(source.encode("utf8")) <= 8 * 1024 * 1024, "source byte capacity")

    def pairs(values):
        result = {}
        for key, value in values:
            need(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def constant(_):
        raise Invalid("non-JSON numeric constant")

    return json.loads(source, object_pairs_hook=pairs, parse_constant=constant)


@dataclass
class Budget:
    states_limit: int
    checks_limit: int
    states: int = 0
    checks: int = 0

    def state(self):
        if self.states >= self.states_limit:
            raise Exhausted("state-budget")
        self.states += 1

    def check(self):
        if self.checks >= self.checks_limit:
            raise Exhausted("semantic-check-budget")
        self.checks += 1


class Program:
    """Independent parse, effect journal and typed predicate interpretation."""

    def __init__(self, source):
        self.raw = source
        fields(source, ["traceSchema", "dataModel", "relationSchema", "scope", "events", "gaps"], ["clockDomain"])
        need(source["traceSchema"] == 3 and source["dataModel"] == "relation-set-v1", "relation-set-v1 traceSchema 3 required")
        self.clock = source.get("clockDomain")
        if self.clock is not None:
            ident(self.clock)
        self.schemas = source["relationSchema"]
        need(isinstance(self.schemas, dict) and 1 <= len(self.schemas) <= 8, "relation capacity")
        for table, schema in self.schemas.items():
            need(isinstance(table, str) and NAME.fullmatch(table), "relation identifier")
            fields(schema, ["primaryKey", "columns"])
            cols = schema["columns"]
            need(isinstance(cols, dict) and 1 <= len(cols) <= 16, "column capacity")
            need(all(isinstance(c, str) and NAME.fullmatch(c) and k in ("int64", "bool", "text") for c, k in cols.items()), "column declaration")
            need(schema["primaryKey"] in cols and cols[schema["primaryKey"]] in ("int64", "text"), "single typed primary key")
        fields(source["scope"], ["exclusiveWriters", "completeSnapshotTables"])
        need(type(source["scope"]["exclusiveWriters"]) is bool, "writer scope type")
        tables = source["scope"]["completeSnapshotTables"]
        need(isinstance(tables, list) and all(isinstance(t, str) for t in tables) and len(set(tables)) == len(tables) and set(tables) <= set(self.schemas), "snapshot scope")
        need(isinstance(source["gaps"], list), "gap array")
        self.gaps = ["declared-coverage-gap"] if source["gaps"] else []
        if not source["scope"]["exclusiveWriters"]:
            self.gaps.append("writer-universe-incomplete")
        if set(tables) != set(self.schemas):
            self.gaps.append("initial-table-universe-incomplete")
        self.initial, self.versions, self.txs, self.effects = {}, {}, {}, []
        self.observed_reads = []
        self.operations = 0
        self.keys = set()
        events = source["events"]
        need(isinstance(events, list) and 1 <= len(events) <= 65536, "event capacity")
        last_seq, last_time = 0, None
        connections, mark_ids = set(), set()
        for index, event in enumerate(events):
            need(isinstance(event, dict), "event object")
            seq, stamp, kind = event.get("seq"), event.get("time"), event.get("kind")
            need(type(seq) is int and last_seq < seq <= (1 << 53) - 1, "event sequence")
            if seq != last_seq + 1:
                self.gaps.append("event-sequence-hole")
            if stamp is not None:
                need(type(stamp) is int and 0 <= stamp <= (1 << 53) - 1 and (last_time is None or stamp >= last_time), "monotone bounded observation time")
                last_time = stamp
            last_seq = seq
            if index == 0:
                fields(event, ["seq", "kind", "consistent", "initial"], ["time"])
                need(kind == "snapshot" and type(event["consistent"]) is bool, "single initial snapshot")
                if not event["consistent"]:
                    self.gaps.append("initial-snapshot-unproven")
                need(isinstance(event["initial"], dict) and set(event["initial"]) == set(self.schemas), "initial table set")
                for table, rows in event["initial"].items():
                    need(isinstance(rows, list), "initial rows")
                    for row in rows:
                        slot = self.row(table, row)
                        need(slot not in self.initial, "duplicate initial key")
                        self.initial[slot] = copy.deepcopy(row)
                        self.producer(row["version"], slot, row, None, seq)
                continue
            txid = ident(event.get("tx"))
            if kind == "begin":
                fields(event, ["seq", "kind", "tx", "connection"], ["time"])
                connection = ident(event["connection"])
                need(txid not in self.txs and connection not in connections and len(self.txs) < 128, "fresh transaction and available connection")
                connections.add(connection)
                self.txs[txid] = dict(id=txid, connection=connection, status="active", request=None,
                                      start=stamp, end=None, ops=[], active=[], marks=[], overlay={})
                continue
            need(txid in self.txs and self.txs[txid]["status"] == "active", "active transaction required")
            tx = self.txs[txid]
            if kind in ("row_read", "row_write", "savepoint", "rollback_to", "release"):
                need(tx["request"] is None, "operation after commit request")
                tx["ops"].append(copy.deepcopy(event))
                self.operations += 1
            if kind == "row_read":
                fields(event, ["seq", "kind", "tx", "relation", "predicate", "rows", "complete"], ["time"])
                table = event["relation"]
                self.predicate(table, event["predicate"])
                need(type(event["complete"]) is bool and isinstance(event["rows"], list), "query result declaration")
                if not event["complete"]:
                    self.gaps.append("query-result-incomplete")
                seen = set()
                for row in event["rows"]:
                    slot = self.row(table, row)
                    need(slot not in seen, "duplicate returned primary key")
                    seen.add(slot)
                self.observed_reads.append((event, dict(tx["overlay"])))
            elif kind == "row_write":
                fields(event, ["seq", "kind", "tx", "relation", "key", "action", "version", "predecessor", "values"], ["time"])
                slot = self.slot(event["relation"], event["key"])
                need(event["action"] in ("insert", "update", "delete"), "write action")
                predecessor = event["predecessor"]
                need(predecessor is None or isinstance(predecessor, str), "predecessor identity")
                if predecessor is not None:
                    ident(predecessor)
                if event["action"] != "insert":
                    need(predecessor is not None, "update/delete predecessor required")
                if event["action"] == "delete":
                    need(event["values"] is None, "delete tombstone")
                else:
                    self.values(event["relation"], event["values"])
                row = {"key": event["key"], "version": ident(event["version"]), "values": copy.deepcopy(event["values"])}
                self.producer(row["version"], slot, row, txid, seq)
                self.effects.append((txid, copy.deepcopy(event), slot))
                tx["active"].append(len(self.effects) - 1)
                tx["overlay"][slot] = row["version"]
            elif kind == "savepoint":
                fields(event, ["seq", "kind", "tx", "name", "instance"], ["time"])
                name, instance = ident(event["name"]), ident(event["instance"])
                need(instance not in mark_ids and len(tx["marks"]) < 64, "fresh bounded savepoint instance")
                mark_ids.add(instance)
                tx["marks"].append((name, instance, list(tx["active"]), dict(tx["overlay"])))
            elif kind in ("rollback_to", "release"):
                fields(event, ["seq", "kind", "tx", "instance"], ["time"])
                i = next((i for i, mark in enumerate(tx["marks"]) if mark[1] == event["instance"]), None)
                need(i is not None, "active savepoint instance required")
                mark = tx["marks"][i]
                need(not any(m[0] == mark[0] for m in tx["marks"][i + 1:]), "hidden savepoint instance")
                if kind == "rollback_to":
                    tx["active"], tx["overlay"] = list(mark[2]), dict(mark[3])
                    tx["marks"] = tx["marks"][:i + 1]
                else:
                    tx["marks"] = tx["marks"][:i]
            elif kind == "commit_request":
                fields(event, ["seq", "kind", "tx"], ["time"])
                need(tx["request"] is None, "single commit request")
                tx["request"] = seq
            elif kind in ("commit_ok", "rollback_ok", "disconnect"):
                fields(event, ["seq", "kind", "tx"], ["time", "commitResponse"] if kind == "rollback_ok" else ["time"])
                if kind == "commit_ok":
                    need(tx["request"] is not None and "commitResponse" not in event, "confirmed requested commit")
                    tx["status"] = "committed"
                elif kind == "rollback_ok" and tx["request"] is None:
                    need("commitResponse" not in event, "commit response without request")
                    tx["status"] = "aborted"
                elif kind == "rollback_ok" and self.definite_abort(event.get("commitResponse"), tx["request"]):
                    tx["status"] = "aborted"
                else:
                    tx["status"] = "unknown"
                tx["end"] = stamp
                connections.remove(tx["connection"])
            else:
                # Raw observations remain a coverage gap; they are never ignored
                # to turn a partially projected trace into a complete history.
                self.gaps.append("unprojected-operation")
        self.committed = []
        for tx in self.txs.values():
            if tx["status"] in ("active", "unknown"):
                self.gaps.append("transaction-outcome-unknown")
            if tx["status"] == "committed":
                self.committed.append(tx["id"])
            final = {}
            for i in tx["active"]:
                _, effect, slot = self.effects[i]
                final[slot] = copy.deepcopy(self.versions[effect["version"]]["row"])
            tx["final"] = final if tx["status"] == "committed" else {}
        need(len(self.keys) <= 128, "primary key capacity")

    @staticmethod
    def definite_abort(response, request):
        if not isinstance(response, dict) or type(response.get("request")) is not int or response["request"] != request:
            return False
        if set(response) == {"request", "commandTag"}:
            return response["commandTag"] == "ROLLBACK"
        return (set(response) == {"request", "sqlstate", "diagnosticSqlstate", "transactionStatus"}
                and response["sqlstate"] in ("40001", "40P01")
                and response["diagnosticSqlstate"] == response["sqlstate"]
                and response["transactionStatus"] == "IDLE")

    def slot(self, table, key):
        need(table in self.schemas, "declared relation required")
        schema = self.schemas[table]
        kind = schema["columns"][schema["primaryKey"]]
        value = scalar(kind, key)
        slot = (table, kind, value)
        self.keys.add(slot)
        return slot

    def values(self, table, values):
        schema = self.schemas[table]
        expected = set(schema["columns"]) - {schema["primaryKey"]}
        need(isinstance(values, dict) and set(values) == expected, "complete non-key row values required")
        for col in expected:
            scalar(schema["columns"][col], values[col])

    def row(self, table, row):
        fields(row, ["key", "version", "values"])
        slot = self.slot(table, row["key"])
        ident(row["version"])
        self.values(table, row["values"])
        return slot

    def producer(self, version, slot, row, writer, seq):
        need(version not in self.versions, "unique row-version identity required")
        self.versions[version] = dict(slot=slot, row=copy.deepcopy(row), writer=writer, seq=seq)

    def predicate(self, table, predicate):
        need(table in self.schemas and isinstance(predicate, list) and len(predicate) <= 8, "bounded AND query")
        schema = self.schemas[table]
        for term in predicate:
            fields(term, ["column", "op", "value"])
            need(term["column"] in schema["columns"], "declared predicate column")
            kind = schema["columns"][term["column"]]
            need(term["op"] in ("eq", "lt", "le", "gt", "ge") and (kind != "bool" or term["op"] == "eq"), "supported comparison")
            scalar(kind, term["value"])

    def matches(self, table, row, predicate, budget):
        schema = self.schemas[table]
        for term in predicate:
            budget.check()
            kind = schema["columns"][term["column"]]
            actual = row["key"] if term["column"] == schema["primaryKey"] else row["values"][term["column"]]
            a, b = scalar(kind, actual), scalar(kind, term["value"])
            op = term["op"]
            if not ({"eq": a == b, "lt": a < b, "le": a <= b, "gt": a > b, "ge": a >= b}[op]):
                return False
        return True

    def query(self, state, event, budget):
        rows = {}
        for slot, row in state.items():
            budget.check()
            if slot[0] == event["relation"] and row["values"] is not None and self.matches(slot[0], row, event["predicate"], budget):
                rows[slot] = row
        actual = {self.slot(event["relation"], r["key"]): r for r in event["rows"]}
        budget.check()
        if set(rows) != set(actual):
            return False
        for key in rows:
            budget.check()
            if rows[key] != actual[key]:
                return False
        return True

    def source_findings(self, budget):
        findings = []
        # These are source-lineage facts, not a transaction dependency graph.
        # Even an unobserved aborted write cannot give itself a strict parent.
        parents = {e["version"]: e["predecessor"] for _, e, _ in self.effects}
        for version in parents:
            seen = set()
            current = version
            while current in parents:
                budget.check()
                if current in seen:
                    self.gaps.append("cyclic-write-predecessor-facts")
                    break
                seen.add(current)
                current = parents[current]
        for event, owned in self.observed_reads:
            if self.txs[event["tx"]]["status"] != "committed":
                continue
            for row in event["rows"]:
                budget.check()
                slot = self.slot(event["relation"], row["key"])
                source = self.versions.get(row["version"])
                if source is None:
                    self.gaps.append("read-producer-missing")
                    continue
                if source["slot"] != slot or source["row"] != row:
                    self.gaps.append("read-source-content-mismatch")
                    continue
                if not self.matches(event["relation"], row, event["predicate"], budget):
                    self.gaps.append("returned-row-outside-predicate")
                writer = source["writer"]
                if writer is None or writer == event["tx"]:
                    continue
                producer = self.txs[writer]
                if producer["status"] == "aborted":
                    findings.append(dict(category="G1a", readSeq=event["seq"], writeSeq=source["seq"], writer=writer, reader=event["tx"]))
                elif producer["status"] == "committed" and producer["final"].get(slot, {}).get("version") != row["version"]:
                    findings.append(dict(category="G1b", readSeq=event["seq"], writeSeq=source["seq"], writer=writer, reader=event["tx"]))
        for txid, effect, slot in self.effects:
            budget.check()
            predecessor = effect["predecessor"]
            if predecessor is not None and predecessor not in self.versions:
                self.gaps.append("write-predecessor-missing")
            elif predecessor is not None and self.versions[predecessor]["slot"] != slot:
                self.gaps.append("write-predecessor-slot-mismatch")
        return findings


def options(raw):
    opts = {} if raw is None else copy.deepcopy(raw)
    fields(opts, [], ["maxStates", "maxOperationChecks", "clients", "clientsComplete"])
    for name, maximum in [("maxStates", MAX_STATES), ("maxOperationChecks", MAX_CHECKS)]:
        opts.setdefault(name, maximum)
        need(type(opts[name]) is int and 0 <= opts[name] <= maximum, "budget range")
    opts.setdefault("clients", [])
    opts.setdefault("clientsComplete", False)
    need(isinstance(opts["clients"], list) and len(opts["clients"]) <= 128 and type(opts["clientsComplete"]) is bool, "logical client declaration")
    return opts


def context(program, model, opts):
    edges = set()
    active = set(program.committed)
    process_complete = opts["clientsComplete"]
    seen_clients, assigned = set(), set()
    for client in opts["clients"]:
        fields(client, ["id", "transactions"])
        cid = ident(client["id"])
        need(cid not in seen_clients and isinstance(client["transactions"], list), "unique logical client")
        seen_clients.add(cid)
        members = []
        for txid in client["transactions"]:
            need(isinstance(txid, str) and txid in program.txs and txid not in assigned, "unique original logical membership")
            assigned.add(txid)
            if txid in active:
                members.append(txid)
        for a, b in zip(members, members[1:]):
            left, right = program.txs[a], program.txs[b]
            if program.clock is not None and left["end"] is not None and right["start"] is not None and left["end"] < right["start"]:
                edges.add((a, b))
            else:
                process_complete = False
    process_complete = process_complete and active <= assigned
    realtime_complete = program.clock is not None and all(program.txs[t]["start"] is not None and program.txs[t]["end"] is not None for t in active)
    realtime = {(a, b) for a in active for b in active if a != b and program.txs[a]["end"] is not None and program.txs[b]["start"] is not None and program.txs[a]["end"] < program.txs[b]["start"]}
    if len(active) <= 1 and not any(t["status"] in ("unknown", "active") for t in program.txs.values()):
        process_complete = realtime_complete = True
    if model in SESSION_MODELS:
        return edges, process_complete, "process"
    if model in REALTIME_MODELS:
        # Fixed strong definitions also include process obligations. Require the
        # explicit client universe rather than assuming a connection is a client.
        if model == "strict-serializable":
            return realtime, realtime_complete, "realtime"
        return edges | realtime, process_complete and realtime_complete, "process-and-realtime"
    return set(), True, "data-only"


def ordered(order, edges):
    positions = {tx: i for i, tx in enumerate(order)}
    return all(positions[a] < positions[b] for a, b in edges)


def write(program, state, event, budget):
    budget.check()
    slot = program.slot(event["relation"], event["key"])
    previous = state.get(slot)
    alive = previous is not None and previous["values"] is not None
    if event["predecessor"] != (previous["version"] if previous else None):
        return False
    if event["action"] == "insert" and alive or event["action"] != "insert" and not alive:
        return False
    state[slot] = {"key": event["key"], "version": event["version"], "values": copy.deepcopy(event["values"])}
    return True


def replay(program, txid, base, budget):
    """One original transaction against one concrete state, including rollback."""
    state = copy.deepcopy(base)
    marks = []
    for event in program.txs[txid]["ops"]:
        budget.check()
        kind = event["kind"]
        if kind == "savepoint":
            marks.append((event["instance"], copy.deepcopy(state)))
        elif kind in ("rollback_to", "release"):
            index = next(i for i, mark in enumerate(marks) if mark[0] == event["instance"])
            if kind == "rollback_to":
                state = copy.deepcopy(marks[index][1])
                marks = marks[:index + 1]
            else:
                marks = marks[:index]
        elif kind == "row_write":
            if not write(program, state, event, budget):
                return None
        elif not program.query(state, event, budget):
            return None
    return state


def serial(program, edges, budget, fixed=None):
    candidates = [tuple(fixed)] if fixed is not None else itertools.permutations(program.committed)
    for order in candidates:
        budget.state()
        if not ordered(order, edges):
            continue
        state = copy.deepcopy(program.initial)
        for tx in order:
            state = replay(program, tx, state, budget)
            if state is None:
                break
        if state is not None:
            return {"kind": "original-program-serial", "commitOrder": list(order)}
    return None


def prefix_program(program, txid, prefixes, position, mode, floor, budget, fixed=None, fixed_snapshot=None):
    """Search actual query-prefix/own-overlay choices without dependency edges.

    Query result matching always compares the entire returned set. Rollback
    changes only the overlay/marks; selected query observations remain checked.
    """
    events = program.txs[txid]["ops"]

    def visit(index, overlay, marks, last, selected, snapshot):
        budget.state()
        if index == len(events):
            return selected
        event = events[index]
        kind = event["kind"]
        if kind == "savepoint":
            return visit(index + 1, overlay, marks + [(event["instance"], dict(overlay))], last, selected, snapshot)
        if kind in ("rollback_to", "release"):
            i = next(i for i, mark in enumerate(marks) if mark[0] == event["instance"])
            return visit(index + 1, dict(marks[i][1]) if kind == "rollback_to" else overlay,
                         marks[:i + 1] if kind == "rollback_to" else marks[:i], last, selected, snapshot)
        choices = [snapshot] if mode == "snapshot" else range(last, position + 1)
        if fixed is not None:
            choices = [fixed[len(selected)]] if len(selected) < len(fixed) else []
        for cut in choices:
            budget.check()
            if type(cut) is not int or not floor <= cut <= position or cut < last or (snapshot is not None and cut != snapshot):
                continue
            state = dict(prefixes[cut])
            state.update(overlay)
            next_overlay = dict(overlay)
            if kind == "row_read":
                if not program.query(state, event, budget):
                    continue
            elif kind == "row_write":
                if not write(program, state, event, budget):
                    continue
                slot = program.slot(event["relation"], event["key"])
                next_overlay[slot] = state[slot]
            else:
                raise Invalid("unprojected program")
            found = visit(index + 1, next_overlay, marks, cut, selected + [cut], snapshot)
            if found is not None:
                return found
        return None

    if mode == "snapshot" and fixed is not None:
        if type(fixed_snapshot) is not int or not floor <= fixed_snapshot <= position:
            return None
        snapshots = [fixed_snapshot]
    else:
        snapshots = range(floor, position + 1) if mode == "snapshot" else [None]
    for snapshot in snapshots:
        if mode == "snapshot":
            # First-committer-wins is a sufficient operational SI condition.
            for slot in program.txs[txid]["final"]:
                budget.check()
                before = prefixes[snapshot].get(slot)
                latest = prefixes[position].get(slot)
                if (before or {}).get("version") != (latest or {}).get("version"):
                    break
            else:
                found = visit(0, {}, [], floor, [], snapshot)
                if found is not None:
                    return found, snapshot
        else:
            found = visit(0, {}, [], 0, [], None)
            if found is not None:
                return found, None
    return None


def prefixes(program, order, budget):
    result = [copy.deepcopy(program.initial)]
    for txid in order:
        budget.state()
        state = dict(result[-1])
        # A source predecessor denotes an actual row-version predecessor, not
        # an invented SELECT. Validate the committed active write chain against
        # the installation state; an old query snapshot cannot authorize a
        # contradictory final installation chain.
        for index in program.txs[txid]["active"]:
            _, event, _ = program.effects[index]
            if not write(program, state, event, budget):
                return None
        result.append(state)
    return result


def committed_prefix(program, edges, budget, mode, fixed=None):
    orders = [tuple(fixed["commitOrder"])] if fixed is not None else itertools.permutations(program.committed)
    for order in orders:
        budget.state()
        if not ordered(order, edges):
            continue
        states = prefixes(program, order, budget)
        if states is None:
            continue
        positions = {tx: i for i, tx in enumerate(order)}
        programs = []
        for i, txid in enumerate(order):
            # A snapshot strengthened with an order relation must see its
            # original predecessors. RC only constrains CO here, not visibility.
            floor = max([positions[a] + 1 for a, b in edges if b == txid] or [0]) if mode == "snapshot" else 0
            supplied = next((p for p in fixed["programs"] if p["transaction"] == txid), None) if fixed else None
            if fixed and supplied is None:
                break
            found = prefix_program(program, txid, states, i, mode, floor, budget,
                                   None if supplied is None else supplied["prefixes"],
                                   None if supplied is None else supplied["snapshot"])
            if found is None:
                break
            chosen, snapshot = found
            if fixed and supplied.get("snapshot") != snapshot:
                break
            programs.append({"transaction": txid, "prefixes": chosen, "snapshot": snapshot})
        else:
            return {"kind": "snapshot-prefix" if mode == "snapshot" else "committed-query-prefixes", "commitOrder": list(order), "programs": programs}
    return None


def check_certificate_shape(program, certificate):
    need(isinstance(certificate, dict), "certificate object")
    kind = certificate.get("kind")
    need(kind in ("original-program-serial", "snapshot-prefix", "committed-query-prefixes"), "certificate kind")
    fields(certificate, ["kind", "commitOrder"], ["programs"])
    order = certificate["commitOrder"]
    need(isinstance(order, list) and all(isinstance(t, str) for t in order) and len(order) == len(set(order)) and set(order) == set(program.committed), "certificate transaction permutation")
    if kind != "original-program-serial":
        programs = certificate.get("programs")
        need(isinstance(programs, list) and len(programs) == len(program.committed), "certificate program count")
        need(all(isinstance(p, dict) and isinstance(p.get("transaction"), str) for p in programs), "certificate program identity")
        need(len({p["transaction"] for p in programs}) == len(program.committed) and {p["transaction"] for p in programs} == set(program.committed), "certificate program universe")
        for p in programs:
            fields(p, ["transaction", "prefixes", "snapshot"])
            count = sum(e["kind"] in ("row_read", "row_write") for e in program.txs[p["transaction"]]["ops"])
            need(isinstance(p["prefixes"], list) and len(p["prefixes"]) == count and all(type(v) is int for v in p["prefixes"]), "one selected prefix per original semantic operation")
            need(p["snapshot"] is None or type(p["snapshot"]) is int, "snapshot prefix type")
    else:
        need("programs" not in certificate, "serial certificate has no substituted query program")


def analyze(source, model="serializable", options=None, certificate=None):
    """Return exact serial decisions or sufficient weaker-model certificates.

    A failed weak search is unknown/pending. It is never an Adya refutation.
    Compatibility is conditional on supplied source facts, not authentication of
    the observer, and includes the original write-predecessor preconditions.
    """
    result = {"format": FORMAT, "referenceDefinition": DEFINITION, "model": model,
              "status": "invalid", "complete": False, "exactDecision": False,
              "supportsExhaustiveRefutation": model in SERIAL_MODELS,
              "sourceAssurance": "conditional on supplied original observations and write-predecessor facts; not observer authentication"}
    budget = None
    try:
        need(model in MODELS, "unknown canonical model")
        opts = globals()["options"](options)
        budget = Budget(opts["maxStates"], opts["maxOperationChecks"])
        program = Program(decode(source))
        if certificate is not None:
            check_certificate_shape(program, certificate)
        result["sourceSha256"] = hashlib.sha256(json.dumps(program.raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        findings = program.source_findings(budget)
        if findings and model not in RU_MODELS:
            result.update(status="refuted", complete=True, reason="direct-aborted-or-intermediate-source", findings=findings, exactDecision=True)
            return result
        if program.gaps:
            result.update(status="unknown", reason="incomplete-source", gaps=sorted(set(program.gaps)))
            return result
        if len(program.committed) > MAX_TX or program.operations > MAX_OPS:
            result.update(status="unknown", reason="exact-capacity")
            return result
        edges, known, order_context = context(program, model, opts)
        result["orderContext"] = order_context
        if not known:
            # A basic serial impossibility remains a valid stronger-serial
            # refutation even if its additional order facts are unavailable.
            if model in SERIAL_MODELS and certificate is None and serial(program, set(), budget) is None:
                result.update(status="refuted", complete=True, reason="original-program-has-no-serial-order", exactDecision=True)
            else:
                result.update(status="unknown", reason="order-facts-incomplete")
            return result
        if certificate is not None:
            kind = certificate["kind"]
            allowed = kind == "original-program-serial" or (kind == "committed-query-prefixes" and model in RU_MODELS | RC_MODELS) or (kind == "snapshot-prefix" and model in SI_MODELS)
            need(allowed, "certificate kind cannot establish requested model")
            if kind == "original-program-serial":
                found = serial(program, edges, budget, certificate["commitOrder"])
            else:
                found = committed_prefix(program, edges, budget, "snapshot" if kind == "snapshot-prefix" else "query", certificate)
            result.update(status="checked-compatible" if found == certificate else "unknown", complete=found == certificate,
                          reason="certificate-replayed" if found == certificate else "certificate-does-not-replay",
                          certificate=found if found == certificate else None)
            return result
        found = serial(program, edges, budget)
        if found is not None:
            result.update(status="checked-compatible", complete=True, reason="original-program-serial-certificate", certificate=found, exactDecision=model in SERIAL_MODELS)
            return result
        if model in SERIAL_MODELS:
            result.update(status="refuted", complete=True, reason="original-program-has-no-serial-order", exactDecision=True)
            return result
        if model in RU_MODELS | RC_MODELS:
            found = committed_prefix(program, edges, budget, "query")
        elif model in SI_MODELS:
            found = committed_prefix(program, edges, budget, "snapshot")
        else:
            result.update(status="pending", reason="model-specific-nonserial-completion-not-implemented")
            return result
        if found is not None:
            result.update(status="checked-compatible", complete=True, reason="sufficient-operational-certificate", certificate=found)
        else:
            result.update(status="unknown", reason="no-sufficient-certificate-found",
                          caveat="No certificate under this operational prefix construction does not refute the fixed Adya model.")
    except Exhausted as error:
        result.update(status="unknown", complete=False, reason=str(error))
    except (Invalid, KeyError, TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as error:
        result.update(status="invalid", complete=False, reason=str(error))
    finally:
        if budget:
            result["metrics"] = {"states": budget.states, "semanticChecks": budget.checks}
            result["limits"] = {"committedTransactions": MAX_TX, "operations": MAX_OPS,
                                "states": budget.states_limit, "semanticChecks": budget.checks_limit}
    return result


def verify_certificate(source, model, certificate, expected_options=None):
    """Reinterpret original inputs; producer limits/status are not authority."""
    result = analyze(source, model, expected_options, certificate)
    return {"valid": result["status"] == "checked-compatible" and result.get("certificate") == certificate,
            "scope": DEFINITION, "result": result}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="relation trace JSON file, or - for stdin")
    parser.add_argument("--model", choices=MODELS, default="serializable")
    parser.add_argument("--options", help="independent caller options JSON file")
    parser.add_argument("--certificate", help="concrete certificate to replay")
    args = parser.parse_args(argv)
    source = sys.stdin.read() if args.source == "-" else Path(args.source).read_text("utf8")
    opts = None if args.options is None else decode(Path(args.options).read_text("utf8"))
    if args.certificate:
        value = verify_certificate(source, args.model, decode(Path(args.certificate).read_text("utf8")), opts)
    else:
        value = analyze(source, args.model, opts)
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    return 2 if value.get("status") == "invalid" or value.get("valid") is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
