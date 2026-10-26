"""Independent relation-set reference and frozen-corpus selfcheck. No MoonTxnWitness imports.

Scope rollback copies whole row maps. Serial search enumerates transaction orders
without dependency graphs or production caches. Native Python integers and scalar
strings provide signed-int64 precision and Unicode codepoint ordering.
"""
from __future__ import annotations
import copy
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

MIN_I64, MAX_I64 = -(1 << 63), (1 << 63) - 1
DECIMAL = re.compile(r"(?:0|-[1-9][0-9]*|[1-9][0-9]*)\Z")
OPERATIONS = {"row_read", "row_write"}
CONTROLS = {"savepoint", "rollback_to", "release"}


class Invalid(ValueError):
    pass


class BudgetStop(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def fields(value, required, optional=()):
    require(isinstance(value, dict), "object required")
    require(set(required) <= set(value) <= set(required) | set(optional), "field set")


def scalar_text(value):
    require(isinstance(value, str), "text required")
    require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value), "Unicode scalar required")
    return value


def identity(value):
    scalar_text(value)
    require(1 <= len(value) <= 256 and all(ord(c) >= 32 for c in value), "bounded identity")
    return value


def version_identity(value):
    scalar_text(value)
    units = sum(1 if ord(c) <= 0xFFFF else 2 for c in value)
    require(1 <= units <= 256, "version identity UTF16 bound")
    return value


def typed(kind, value):
    if kind == "int64":
        require(isinstance(value, str) and DECIMAL.fullmatch(value), "canonical int64 string")
        number = int(value)
        require(MIN_I64 <= number <= MAX_I64, "signed int64 range")
        return number
    if kind == "bool":
        require(type(value) is bool, "boolean required")
        return value
    require(kind == "text", "known scalar type")
    return scalar_text(value)


def strict_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    def bad_constant(_):
        raise Invalid("non-JSON number")
    require(len(text.encode("utf-8")) <= 8 * 1024 * 1024, "input bytes")
    return json.loads(text, object_pairs_hook=unique, parse_constant=bad_constant)


@dataclass
class Work:
    states_limit: int
    checks_limit: int
    states: int = 0
    checks: int = 0

    def state(self):
        if self.states == self.states_limit:
            raise BudgetStop("state_budget")
        self.states += 1

    def check(self):
        if self.checks == self.checks_limit:
            raise BudgetStop("operation_budget")
        self.checks += 1


def analyze(text, options=None, forced_order=None):
    """Return an internal reference result, not a public production report."""
    try:
        trace = strict_json(text) if isinstance(text, str) else copy.deepcopy(text)
        return interpret(trace, options if options is not None else {}, forced_order)
    except (Invalid, TypeError, KeyError, ValueError, UnicodeError, RecursionError) as error:
        return {"status": "invalid", "reason": str(error), "complete": False}


def interpret(trace, options, forced_order=None):
    fields(options, [], ["maxStates", "maxOperationChecks"])
    limits = {"maxStates": 100000, "maxOperationChecks": 1000000}
    limits.update(options)
    for name, maximum in [("maxStates", 100000), ("maxOperationChecks", 1000000)]:
        require(type(limits[name]) is int and 0 <= limits[name] <= maximum, "budget range")
    fields(trace, ["traceSchema", "dataModel", "clockDomain", "relationSchema", "scope", "events", "gaps"])
    require(trace["traceSchema"] == 3 and trace["dataModel"] == "relation-set-v1", "relation header")
    identity(trace["clockDomain"])
    schemas = trace["relationSchema"]
    require(isinstance(schemas, dict) and 1 <= len(schemas) <= 8, "relation count")
    for relation, schema in schemas.items():
        require(isinstance(relation, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", relation), "ASCII relation name")
        fields(schema, ["primaryKey", "columns"])
        columns = schema["columns"]
        require(isinstance(columns, dict) and 1 <= len(columns) <= 16, "column count")
        for column, kind in columns.items():
            require(isinstance(column, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", column), "ASCII column name")
            require(kind in ("int64", "bool", "text"), "column type")
        require(schema["primaryKey"] in columns and columns[schema["primaryKey"]] in ("int64", "text"), "primary key type")
    fields(trace["scope"], ["exclusiveWriters", "completeSnapshotTables"])
    require(type(trace["scope"]["exclusiveWriters"]) is bool, "exclusive writers type")
    covered = trace["scope"]["completeSnapshotTables"]
    require(isinstance(covered, list) and all(isinstance(r, str) for r in covered) and len(set(covered)) == len(covered) and set(covered) <= set(schemas), "snapshot coverage declaration")
    require(isinstance(trace["gaps"], list), "gaps array")
    gaps = []
    for gap in trace["gaps"]:
        fields(gap, ["code", "message"])
        gaps.append(identity(gap["code"]))
        scalar_text(gap["message"])

    def gap(code):
        if code not in gaps:
            gaps.append(code)

    if not trace["scope"]["exclusiveWriters"]:
        gap("exclusive_writers_unproven")
    for relation in schemas:
        if relation not in covered:
            gap("incomplete_snapshot_table")
    events = trace["events"]
    require(isinstance(events, list) and 1 <= len(events) <= 65536, "event count")
    initial, versions, all_keys, transactions, connections, effects = {}, {}, set(), {}, {}, []
    seen_marks, reads, writes, raw_statements = set(), [], [], {}
    previous_seq, previous_time, semantic_ops, row_refs = 0, -1, 0, 0
    initialized = False

    def row(relation, raw):
        fields(raw, ["key", "version", "values"])
        s = schemas[relation]
        key = typed(s["columns"][s["primaryKey"]], raw["key"])
        version_identity(raw["version"])
        value(raw["values"], relation)
        all_keys.add((relation, s["columns"][s["primaryKey"]], key))
        return key

    def value(values, relation):
        s = schemas[relation]
        wanted = {k: v for k, v in s["columns"].items() if k != s["primaryKey"]}
        require(isinstance(values, dict) and set(values) == set(wanted), "complete non-PK values")
        for column, kind in wanted.items():
            typed(kind, values[column])

    def pred(predicate, relation):
        require(isinstance(predicate, list) and len(predicate) <= 8, "AND predicate count")
        for term in predicate:
            fields(term, ["column", "op", "value"])
            require(term["column"] in schemas[relation]["columns"], "predicate column")
            kind = schemas[relation]["columns"][term["column"]]
            require(term["op"] in ("eq", "lt", "le", "gt", "ge") and (kind != "bool" or term["op"] == "eq"), "predicate operator")
            typed(kind, term["value"])

    def revert(tx, active, seq):
        for index in set(tx["activeEffects"]) - set(active):
            effects[index]["revertedBy"] = seq
        tx["activeEffects"] = list(active)

    for position, e in enumerate(events):
        require(isinstance(e, dict), "event object")
        seq, time, kind = e.get("seq"), e.get("time"), e.get("kind")
        require(type(seq) is int and previous_seq < seq <= (1 << 53) - 1, "event sequence")
        require(type(time) is int and previous_time <= time <= (1 << 53) - 1, "event time")
        if seq != previous_seq + 1:
            gap("sequence_gap")
        previous_seq, previous_time = seq, time
        if kind == "snapshot":
            fields(e, ["seq", "time", "kind", "initial", "consistent"])
            require(position == 0 and not initialized and type(e["consistent"]) is bool, "single first snapshot")
            require(isinstance(e["initial"], dict) and set(e["initial"]) == set(schemas), "explicit initial array for every declared relation")
            if not e["consistent"]:
                gap("inconsistent_snapshot")
            for relation, rows in e["initial"].items():
                require(isinstance(rows, list), "initial row array")
                initial[relation] = {}
                for r in rows:
                    key = row(relation, r)
                    require(key not in initial[relation] and r["version"] not in versions, "duplicate initial key/version")
                    initial[relation][key] = copy.deepcopy(r)
                    versions[r["version"]] = {"relation": relation, "key": key, "row": copy.deepcopy(r), "writer": None, "effect": None, "sourceSeq": seq, "tombstone": False}
            initialized = True
            require(len(all_keys) <= 1024, "distinct relation primary key budget")
            continue
        require(initialized, "activity before snapshot")
        tx_id = identity(e.get("tx"))
        if kind == "begin":
            fields(e, ["seq", "time", "kind", "tx", "connection"])
            connection = identity(e["connection"])
            require(tx_id not in transactions and connection not in connections and len(transactions) < 512, "fresh transaction/available connection")
            transactions[tx_id] = {"id": tx_id, "connection": connection, "status": "active", "request": None, "journal": [], "marks": [], "activeEffects": [], "overlay": {}, "beginSeq": seq, "endSeq": None, "events": [seq]}
            connections[connection] = tx_id
            continue
        require(tx_id in transactions and transactions[tx_id]["status"] == "active", "active transaction")
        tx = transactions[tx_id]
        tx["events"].append(seq)
        if kind in {"statement", "rows"}:
            require(tx["request"] is None, "observation after commit request")
        if kind in OPERATIONS | CONTROLS:
            require(tx["request"] is None, "operation after commit request")
            tx["journal"].append(copy.deepcopy(e))
        if kind == "statement":
            fields(e, ["seq", "time", "kind", "tx", "sql"], ["parameters", "mappingId", "executedSql"])
            scalar_text(e["sql"])
            if "executedSql" in e:
                scalar_text(e["executedSql"])
            if "mappingId" in e:
                identity(e["mappingId"])
            raw_statements[seq] = {"tx": tx_id, "complete": False}
            gap("unmapped_statement")
        elif kind == "rows":
            fields(e, ["seq", "time", "kind", "tx", "statement", "rows", "complete"], ["error", "serverRows", "columns"])
            require(type(e["statement"]) is int and e["statement"] in raw_statements and raw_statements[e["statement"]]["tx"] == tx_id, "same-TX raw statement source")
            require(type(e["complete"]) is bool and isinstance(e["rows"], list) and not raw_statements[e["statement"]]["complete"], "raw result shape/EOF")
            raw_statements[e["statement"]]["complete"] = e["complete"]
        elif kind in OPERATIONS:
            semantic_ops += 1
            require(semantic_ops <= 10000 and e.get("relation") in schemas, "semantic operation/relation")
            relation = e["relation"]
            s = schemas[relation]
            if kind == "row_read":
                fields(e, ["seq", "time", "kind", "tx", "relation", "predicate", "rows", "complete"])
                pred(e["predicate"], relation)
                require(isinstance(e["rows"], list) and type(e["complete"]) is bool, "query rows/complete")
                if not e["complete"]:
                    gap("incomplete_query")
                records = []
                row_refs += len(e["rows"])
                require(row_refs <= 100000, "returned row reference budget")
                for r in e["rows"]:
                    key = row(relation, r)
                    source = versions.get(r["version"])
                    if source is None:
                        gap("missing_row_source")
                    own_at_read = bool(source and source["writer"] == tx_id and tx["overlay"].get((relation, key)) == r["version"])
                    records.append((r, key, source, own_at_read))
                reads.append((e, records))
            else:
                fields(e, ["seq", "time", "kind", "tx", "relation", "key", "action", "version", "predecessor", "values"])
                key = typed(s["columns"][s["primaryKey"]], e["key"])
                all_keys.add((relation, s["columns"][s["primaryKey"]], key))
                require(e["action"] in ("insert", "update", "delete"), "row action")
                version = version_identity(e["version"])
                require(version not in versions, "duplicate version producer")
                if e["action"] == "delete":
                    require(e["values"] is None, "delete null values")
                else:
                    value(e["values"], relation)
                predecessor = e["predecessor"]
                require(predecessor is None or isinstance(predecessor, str), "predecessor token/null")
                if predecessor is None:
                    require(e["action"] == "insert", "only insert may have null predecessor")
                    source = None
                else:
                    version_identity(predecessor)
                    source = versions.get(predecessor)
                    if source is None:
                        gap("missing_predecessor_source")
                effect = {"seq": seq, "tx": tx_id, "relation": relation, "key": e["key"], "action": e["action"], "version": version, "predecessor": predecessor, "values": copy.deepcopy(e["values"]), "revertedBy": None}
                effects.append(effect)
                index = len(effects) - 1
                tx["activeEffects"].append(index)
                tx["overlay"][(relation, key)] = version
                produced = {"relation": relation, "key": key, "row": {"key": e["key"], "version": version, "values": copy.deepcopy(e["values"])}, "writer": tx_id, "effect": index, "sourceSeq": seq, "tombstone": e["action"] == "delete"}
                versions[version] = produced
                writes.append((e, source, produced))
        elif kind == "savepoint":
            fields(e, ["seq", "time", "kind", "tx", "name", "instance"])
            name, instance = identity(e["name"]), identity(e["instance"])
            require(instance not in seen_marks and len(tx["marks"]) < 64, "fresh bounded savepoint instance")
            seen_marks.add(instance)
            tx["marks"].append((name, instance, list(tx["activeEffects"]), dict(tx["overlay"])))
        elif kind in ("rollback_to", "release"):
            fields(e, ["seq", "time", "kind", "tx", "instance"])
            index = next((i for i, mark in enumerate(tx["marks"]) if mark[1] == e["instance"]), None)
            require(index is not None, "active savepoint instance")
            mark = tx["marks"][index]
            require(not any(m[0] == mark[0] for m in tx["marks"][index + 1:]), "hidden savepoint instance")
            if kind == "rollback_to":
                revert(tx, mark[2], seq)
                tx["overlay"] = dict(mark[3])
                tx["marks"] = tx["marks"][:index + 1]
            else:
                tx["marks"] = tx["marks"][:index]
        elif kind == "commit_request":
            fields(e, ["seq", "time", "kind", "tx"])
            require(tx["request"] is None, "single commit request")
            tx["request"] = seq
        elif kind in ("commit_ok", "rollback_ok", "disconnect"):
            fields(e, ["seq", "time", "kind", "tx"], ["commitResponse"] if kind == "rollback_ok" else [])
            if kind == "commit_ok":
                require(tx["request"] is not None, "commit request required")
                tx["status"] = "committed"
            elif kind == "disconnect":
                tx["status"] = "unknown"
                gap("transaction_outcome_unknown")
            elif tx["request"] is None:
                require("commitResponse" not in e, "response without commit request")
                revert(tx, [], seq)
                tx["status"] = "aborted"
            else:
                response = e.get("commitResponse")
                proven = False
                if isinstance(response, dict) and response.get("request") == tx["request"]:
                    proven = (set(response) == {"request", "commandTag"} and response["commandTag"] == "ROLLBACK") or (set(response) == {"request", "sqlstate", "diagnosticSqlstate", "transactionStatus"} and response["sqlstate"] in ("40001", "40P01") and response["diagnosticSqlstate"] == response["sqlstate"] and response["transactionStatus"] == "IDLE")
                if proven:
                    revert(tx, [], seq)
                    tx["status"] = "aborted"
                else:
                    tx["status"] = "unknown"
                    gap("transaction_outcome_unknown")
            tx["endSeq"] = seq
            connections.pop(tx["connection"])
        else:
            raise Invalid("unsupported or mixed event kind")
        require(len(all_keys) <= 1024, "distinct relation primary key budget")

    for tx in transactions.values():
        if tx["status"] == "active":
            tx["status"] = "unknown"
            gap("transaction_outcome_unknown")
    if any(not statement["complete"] for statement in raw_statements.values()):
        gap("incomplete_rows")
    committed = [tx for tx in transactions.values() if tx["status"] == "committed"]
    ledger = []
    for tx in transactions.values():
        final = {}
        for index in tx["activeEffects"]:
            effect = effects[index]
            schema = schemas[effect["relation"]]
            kind = schema["columns"][schema["primaryKey"]]
            final[(effect["relation"], kind, typed(kind, effect["key"]))] = effect["seq"]
        ledger.append({"id": tx["id"], "connection": tx["connection"], "status": tx["status"],
                       "beginSeq": tx["beginSeq"], "endSeq": tx["endSeq"], "events": tx["events"],
                       "finalWrites": sorted(final.values())})
    normalized = {"schema": 3, "dataModel": "relation-set-v1", "algorithm": "v3-relation-lifecycle-1",
                  "status": "inconclusive" if gaps else "ready",
                  "coverage": {"complete": not gaps, "gaps": [{"code": code, "message": "Independent reference: " + code} for code in gaps]},
                  "relationSchema": copy.deepcopy(schemas), "observations": copy.deepcopy(events),
                  "effects": copy.deepcopy(effects), "transactions": ledger, "history": None}
    result = {"status": "inconclusive", "complete": False, "gaps": gaps, "effects": effects,
              "transactions": ledger, "normalization": normalized, "limits": limits,
              "metrics": {"states": 0, "operationChecks": 0}}
    if gaps:
        result["reason"] = "coverage_gap"
        return result
    if len(committed) > 6 or semantic_ops > 128:
        result["reason"] = "exact_capacity"
        return result

    def matches(relation, r, predicate, work=None):
        s = schemas[relation]
        for term in predicate:
            if work:
                work.check()
            kind = s["columns"][term["column"]]
            left = typed(kind, r["key"] if term["column"] == s["primaryKey"] else r["values"][term["column"]])
            right = typed(kind, term["value"])
            op = term["op"]
            answer = left == right if op == "eq" else left < right if op == "lt" else left <= right if op == "le" else left > right if op == "gt" else left >= right
            if not answer:
                return False
        return True

    findings = []
    for e, records in reads:
        if transactions[e["tx"]]["status"] != "committed":
            continue
        seen = set()
        for r, key, source, own_at_read in records:
            if key in seen:
                findings.append("duplicate_returned_key")
            seen.add(key)
            if source and (source["relation"] != e["relation"] or source["key"] != key):
                findings.append("read_identity_mismatch")
            if source and (source["tombstone"] or source["row"]["values"] != r["values"]):
                findings.append("read_content_or_tombstone_mismatch")
            if source and source["writer"] is not None and not own_at_read:
                if transactions[source["writer"]]["status"] == "aborted":
                    findings.append("read_from_aborted_row")
                if effects[source["effect"]]["revertedBy"] is not None:
                    findings.append("read_from_reverted_row")
            if not matches(e["relation"], r, e["predicate"]):
                findings.append("returned_row_does_not_match_predicate")
    for e, source, produced in writes:
        if transactions[e["tx"]]["status"] != "committed" or produced["effect"] not in transactions[e["tx"]]["activeEffects"]:
            continue
        if source and (source["relation"] != e["relation"] or source["key"] != produced["key"]):
            findings.append("predecessor_identity_mismatch")
        if source and source["writer"] is not None and source["writer"] != e["tx"]:
            if transactions[source["writer"]]["status"] == "aborted":
                findings.append("predecessor_from_aborted_row")
            if effects[source["effect"]]["revertedBy"] is not None:
                findings.append("predecessor_from_reverted_row")
    if findings:
        result.update(status="violation", complete=True, reason="source_proven_anomaly", findings=findings)
        return result
    work = Work(limits["maxStates"], limits["maxOperationChecks"])

    def apply(tx, state):
        state = copy.deepcopy(state)
        marks = []
        for e in tx["journal"]:
            work.check()
            kind = e["kind"]
            if kind == "savepoint":
                marks.append((e["instance"], copy.deepcopy(state)))
            elif kind in ("rollback_to", "release"):
                index = next(i for i, mark in enumerate(marks) if mark[0] == e["instance"])
                if kind == "rollback_to":
                    state = copy.deepcopy(marks[index][1])
                    marks = marks[:index + 1]
                else:
                    marks = marks[:index]
            elif kind == "row_write":
                relation = e["relation"]
                schema = schemas[relation]
                key = typed(schema["columns"][schema["primaryKey"]], e["key"])
                current = state[relation].get(key)
                alive = current is not None and current["values"] is not None
                if e["action"] == "insert":
                    if alive or e["predecessor"] != (current["version"] if current else None):
                        return None
                elif not alive or e["predecessor"] != current["version"]:
                    return None
                state[relation][key] = {"key": e["key"], "version": e["version"], "values": copy.deepcopy(e["values"])}
            else:
                relation = e["relation"]
                schema = schemas[relation]
                candidates = [state[relation][k] for k in sorted(state[relation]) if state[relation][k]["values"] is not None]
                expected = [r for r in candidates if matches(relation, r, e["predicate"], work)]
                work.check()  # Result cardinality, including two empty sets.
                if len(expected) != len(e["rows"]):
                    return None
                actual = sorted(e["rows"], key=lambda r: typed(schema["columns"][schema["primaryKey"]], r["key"]))
                for left, right in zip(expected, actual):
                    work.check()
                    if left["key"] != right["key"]:
                        return None
                    work.check()
                    if left["version"] != right["version"]:
                        return None
                    for column in schema["columns"]:
                        if column == schema["primaryKey"]:
                            continue
                        work.check()
                        if left["values"][column] != right["values"][column]:
                            return None
        return state

    def search(order, pending, state):
        if not pending:
            return order
        for tx in pending:
            work.state()
            next_state = apply(tx, state)
            if next_state is not None:
                found = search(order + [tx["id"]], [other for other in pending if other is not tx], next_state)
                if found is not None:
                    return found
        return None

    try:
        if forced_order is None:
            order = search([], committed, initial)
        else:
            require(isinstance(forced_order,list) and len(forced_order)==len(committed) and len(set(forced_order))==len(forced_order) and set(forced_order)=={tx["id"] for tx in committed},"serial witness permutation")
            state=copy.deepcopy(initial)
            order=list(forced_order)
            for tx_id in forced_order:
                work.state()
                state=apply(next(tx for tx in committed if tx["id"]==tx_id),state)
                if state is None:
                    order=None
                    break
        result.update(status="consistent" if order is not None else "violation", complete=True, reason="found" if order is not None else "exhausted", serialOrder=order)
    except BudgetStop as error:
        result.update(reason=str(error))
    result["metrics"] = {"states": work.states, "operationChecks": work.checks}
    return result



def self_test():
    """Recompute immutable expectations without importing or executing production."""
    import hashlib
    from datetime import datetime, timezone
    import zipfile
    root = Path(__file__).resolve().parents[1]
    folder = root / 'fixtures/relation-v3'
    manifest = json.loads((folder / 'manifest.json').read_bytes())
    digest = lambda raw: hashlib.sha256(raw).hexdigest()
    failures, status_counts, normalizations, budgets_checked = [], {}, 0, 0
    for name, binding in manifest['files'].items():
        raw = (folder / name).read_bytes()
        require(len(raw) == binding['bytes'] and digest(raw) == binding['sha256'], 'Frozen file changed: ' + name)
    records = json.loads((folder / 'boundary.json').read_bytes()) + json.loads((folder / 'generated-1000.json').read_bytes())
    refs = {r['id']: r for r in json.loads((folder / 'normalization-oracle.json').read_bytes())}
    budgets = {r['id']: r for r in json.loads((folder / 'budget-expectations.json').read_bytes())['cases']}
    require(len(records) == manifest['totalRecords'] == 1170, 'Record count')
    require(len({r['id'] for r in records}) == len(records), 'Duplicate test identity')
    require(len({r['inputSha256'] for r in records[170:]}) == 1000, 'Unique generated histories')
    for r in records:
        require(digest(r['traceText'].encode('utf8')) == r['inputSha256'], 'Input digest: ' + r['id'])
        a = analyze(r['traceText'], r['options'])
        status_counts[a['status']] = status_counts.get(a['status'], 0) + 1
        if a['status'] != r['expected']:
            failures.append({'id': r['id'], 'field': 'status', 'expected': r['expected'], 'actual': a})
        expected = refs[r['id']]
        require(expected['inputSha256'] == r['inputSha256'], 'Reference identity: ' + r['id'])
        if a.get('normalization') != expected['normalization']:
            failures.append({'id': r['id'], 'field': 'complete_normalization', 'actual': a.get('normalization')})
        if a.get('normalization') is not None:
            normalizations += 1
        if r['id'] in budgets:
            b = budgets[r['id']]
            if a['status'] != b['status'] or a['reason'] != b['reason'] or a['metrics'] != b['metrics']:
                failures.append({'id': r['id'], 'field': 'frozen_budget', 'actual': a})
            budgets_checked += 1
    require(status_counts == manifest['independentExpectedStatusCounts'], 'Status counts')
    promotion = json.loads((root / 'verification/relation-v3/frozen-corpus-promotion.json').read_bytes())
    archive_members = 0
    for archive in promotion['archives']:
        raw = (root / archive['file']).read_bytes()
        require(digest(raw) == archive['sha256'] and len(raw) == archive['bytes'], 'Historical audit archive binding')
        with zipfile.ZipFile(root / archive['file']) as zipped:
            require(set(zipped.namelist()) == {x['file'] for x in archive['members']}, 'Historical member set')
            for member in archive['members']:
                data = zipped.read(member['file'])
                require(len(data) == member['bytes'] and digest(data) == member['sha256'], 'Historical original byte binding')
                archive_members += 1
    result = {'schema': 1, 'kind': 'independent-relation-v3-oracle', 'passed': not failures,
              'cases': len(records), 'boundaryCases': 170, 'generatedCases': 1000,
              'generatedUniqueInputSha256Count': 1000, 'normalizationCases': normalizations,
              'budgetCases': budgets_checked, 'statusCounts': status_counts,
              'historicalArchiveMembersVerified': archive_members,
              'productionImports': False, 'actualDatabaseExecution': False,
              'sourceSha256': digest(Path(__file__).read_bytes()),
              'fixtureManifestSha256': digest((folder / 'manifest.json').read_bytes()), 'failures': failures}
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%S-%fZ')
    receipt = root / 'verification/relation-v3' / ('oracle-' + stamp + '.json')
    raw = (json.dumps(result, ensure_ascii=True, indent=2) + '\n').encode('utf8')
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with receipt.open('xb') as stream:
        stream.write(raw)
    result.update(receipt=receipt.relative_to(root).as_posix(), sha256=digest(raw))
    return result


def verify_generator():
    """Run the preserved pre-production generator in an isolated temporary folder."""
    import hashlib
    import subprocess
    import tempfile
    root = Path(__file__).resolve().parents[1]
    fixtures = root / 'fixtures/relation-v3'
    digest = lambda raw: hashlib.sha256(raw).hexdigest()
    with tempfile.TemporaryDirectory(prefix='moontxnwitness-independent-relation-generator-') as directory:
        scratch = Path(directory)
        for old, name in [('frozen-oracle.py', 'relation_oracle.py'), ('frozen-generator.py', 'freeze_inputs.py')]:
            (scratch / name).write_bytes((fixtures / 'provenance' / old).read_bytes())
        process = subprocess.run([sys.executable, '-B', 'freeze_inputs.py'], cwd=scratch, capture_output=True,
                                 text=True, encoding='utf8', timeout=120)
        require(process.returncode == 0, 'Independent frozen generator did not pass: ' + process.stderr)
        output = json.loads(process.stdout)
        generated = Path(output['directory'])
        if not generated.is_absolute():
            generated = scratch / generated
        files = []
        for name in ['boundary.json', 'generated-1000.json', 'normalization-oracle.json']:
            expected, actual = (fixtures / name).read_bytes(), (generated / name).read_bytes()
            require(actual == expected, 'Generator did not reproduce frozen bytes: ' + name)
            files.append({'file': name, 'bytes': len(actual), 'sha256': digest(actual)})
    return {'passed': True, 'cases': 1170, 'productionImports': False,
            'expectedBytesOverwritten': False, 'files': files}


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('--self-test', '--self-check'):
        result = self_test()
        print(json.dumps(result, ensure_ascii=True, separators=(',', ':')))
        return 0 if result['passed'] else 1
    if len(sys.argv) > 1 and sys.argv[1] == '--verify-orders':
        records = json.loads(Path(sys.argv[2]).read_bytes())
        failures = []
        for index, record in enumerate(records):
            reference = analyze(record['traceText'], forced_order=record['order'])
            if reference['status'] != 'consistent':
                failures.append({'index': index, 'id': record.get('id'), 'reference': reference})
        print(json.dumps({'passed': not failures, 'cases': len(records), 'failures': failures}, ensure_ascii=True, separators=(',', ':')))
        return 0 if not failures else 1
    if len(sys.argv) > 1 and sys.argv[1] == '--verify-generator':
        print(json.dumps(verify_generator(), ensure_ascii=True, separators=(',', ':')))
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == '--trace':
        path = Path(sys.argv[2])
        options = strict_json(Path(sys.argv[3]).read_text(encoding='utf8')) if len(sys.argv) > 3 else {}
    else:
        path = Path(sys.argv[1])
        options = strict_json(Path(sys.argv[2]).read_text(encoding='utf8')) if len(sys.argv) > 2 else {}
    print(json.dumps(analyze(path.read_text(encoding='utf8'), options), ensure_ascii=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
