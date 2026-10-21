"""Independent finite abstract-execution oracle; no dependency graph imports.

The pre-implementation contract and input classes are frozen alongside this file.
This private reference is not a production classifier or a database authenticator.
"""
from __future__ import annotations

from dataclasses import dataclass
import argparse
import hashlib
import itertools
import json
from pathlib import Path


ALGORITHM = "abstract-si-independent-1"
MAX_BYTES = 8 * 1024 * 1024
MAX_STATES = 100_000
MAX_CHECKS = 1_000_000


class Invalid(ValueError):
    pass


class Exhausted(Exception):
    pass


@dataclass
class Budget:
    max_states: int
    max_checks: int
    states: int = 0
    checks: int = 0
    exhausted: bool = False

    def state(self):
        if self.states >= self.max_states:
            self.exhausted = True
            raise Exhausted
        self.states += 1

    def check(self):
        if self.checks >= self.max_checks:
            self.exhausted = True
            raise Exhausted
        self.checks += 1


def _fields(value, names, where):
    if type(value) is not dict or set(value) != set(names):
        raise Invalid(where + " must contain exactly " + ",".join(names))


def _identity(value, where):
    if type(value) is not str or not value:
        raise Invalid(where + " must be a nonempty scalar string")
    units = 0
    for char in value:
        point = ord(char)
        if 0xD800 <= point <= 0xDFFF:
            raise Invalid(where + " contains an unpaired surrogate")
        units += 2 if point > 0xFFFF else 1
    if units > 256:
        raise Invalid(where + " exceeds 256 UTF-16 units")
    return value


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise Invalid("duplicate JSON object key")
        result[key] = value
    return result


def _parse(text):
    if type(text) is not str:
        raise Invalid("input must be original JSON text")
    try:
        raw = text.encode("utf-8")
    except UnicodeError as error:
        raise Invalid("input is not scalar UTF-8") from error
    if len(raw) > MAX_BYTES:
        raise Invalid("input byte budget")
    try:
        value = json.loads(text, object_pairs_hook=_pairs,
            parse_constant=lambda constant: (_ for _ in ()).throw(Invalid("non-finite JSON number")))
    except (ValueError, RecursionError) as error:
        raise Invalid(str(error)) from error
    stack = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > 4096 or depth > 16:
            raise Invalid("JSON node/depth budget")
        if type(item) is dict:
            for key, child in item.items():
                nodes += 1  # Keys are part of the retained JSON tree too.
                if nodes > 4096:
                    raise Invalid("JSON node/depth budget")
                stack.append((child, depth + 1))
        elif type(item) is list:
            stack.extend((child, depth + 1) for child in item)
    return value, hashlib.sha256(raw).hexdigest()


def _budget(value, default, where):
    if value is None:
        return default
    if type(value) is not int or not 0 <= value <= default:
        raise Invalid(where + " must be an integer between zero and " + str(default))
    return value


def _prepare(root):
    _fields(root, ("schema", "dataModel", "complete", "initial", "versionOrders", "transactions"), "history")
    if type(root["schema"]) is not int or root["schema"] != 1:
        raise Invalid("unsupported oracle schema")
    if type(root["dataModel"]) is not str or type(root["complete"]) is not bool:
        raise Invalid("dataModel/complete type")
    gaps = []

    def gap(code, message):
        gaps.append({"code": code, "message": message})

    if root["dataModel"] != "point-register-v1":
        gap("unsupported_data_model", "Only unique-version point registers are supported.")
    if not root["complete"]:
        gap("incomplete_input", "Input does not declare complete supported facts.")
    if type(root["initial"]) is not dict or type(root["versionOrders"]) is not dict or type(root["transactions"]) is not list:
        raise Invalid("initial/versionOrders/transactions type")
    initial = {}
    sources = {}
    for key, version in root["initial"].items():
        key = _identity(key, "initial key")
        version = _identity(version, "initial version")
        initial[key] = version
        sources[(key, version)] = {"writer": None, "opIndex": None}
    if len(initial) > 128:
        gap("key_capacity", "More than 128 keys.")
    if len(root["transactions"]) > 6:
        gap("transaction_capacity", "More than six transactions.")
    txs = {}
    operations = 0
    for tx in root["transactions"]:
        _fields(tx, ("id", "status", "ops"), "transaction")
        name = _identity(tx["id"], "transaction id")
        if name in txs:
            raise Invalid("duplicate transaction id")
        if type(tx["status"]) is not str or tx["status"] not in ("committed", "aborted", "unknown"):
            raise Invalid("transaction outcome")
        if tx["status"] != "committed":
            gap("unsupported_outcome", "Every oracle transaction must be confirmed committed: " + name)
        if type(tx["ops"]) is not list:
            raise Invalid("transaction ops must be an array")
        ops, final = [], {}
        for index, op in enumerate(tx["ops"]):
            operations += 1
            if type(op) is not dict or type(op.get("type")) is not str:
                raise Invalid("operation shape")
            if op["type"] in ("savepoint", "rollback_to", "release", "condition", "statement", "rows"):
                gap("unsupported_journal", "Scoped/SQL/predicate observations need a separate model contract.")
                continue
            _fields(op, ("type", "key", "version"), "operation")
            if op["type"] not in ("read", "write"):
                raise Invalid("unknown operation type")
            key = _identity(op["key"], "operation key")
            version = _identity(op["version"], "operation version")
            if key not in initial:
                gap("missing_initial_key", "Operation references an uninitialized key: " + key)
            copied = {"type": op["type"], "key": key, "version": version, "opIndex": index}
            ops.append(copied)
            if op["type"] == "write":
                if (key, version) in sources:
                    raise Invalid("duplicate write producer or initial/write version collision")
                sources[(key, version)] = {"writer": name, "opIndex": index}
                final[key] = copied
        txs[name] = {"id": name, "status": tx["status"], "ops": ops, "final": final}
    if operations > 128:
        gap("operation_capacity", "More than 128 original operations.")
    for tx in txs.values():
        for op in tx["ops"]:
            if op["type"] == "read" and (op["key"], op["version"]) not in sources:
                gap("missing_read_source", "Unknown source at " + tx["id"] + ":" + str(op["opIndex"]))
    orders = {}
    for key, order in root["versionOrders"].items():
        _identity(key, "order key")
        if key not in initial:
            raise Invalid("version order for an uninitialized key")
        if type(order) is not list or not order:
            raise Invalid("version order must be a nonempty array")
        values = [_identity(version, "ordered version") for version in order]
        if len(set(values)) != len(values) or values[0] != initial[key]:
            raise Invalid("duplicate order version or initializer is not first")
        expected = {initial[key]}
        for tx in txs.values():
            if key in tx["final"]:
                expected.add(tx["final"][key]["version"])
        for version in values:
            source = sources.get((key, version))
            if source is None:
                gap("missing_order_source", "Order contains an unknown version on " + key)
            elif source["writer"] is not None and txs[source["writer"]]["final"][key]["version"] != version:
                raise Invalid("nonfinal version in final-write order")
        if not expected.issubset(values):
            gap("partial_version_order", "Order omits a committed final version on " + key)
        orders[key] = values
    for key in initial:
        if key not in orders:
            gap("missing_version_order", "No explicit complete order for " + key)
    return {"initial": initial, "sources": sources, "txs": txs, "orders": orders}, gaps


def _preflight(p, budget):
    for name in sorted(p["txs"]):
        tx = p["txs"][name]
        previous = {}
        for op in tx["ops"]:
            budget.check()
            key, version = op["key"], op["version"]
            if op["type"] == "read":
                budget.check()  # Inspect the actual source role, including initializer.
                source = p["sources"][(key, version)]
                if key in previous:
                    budget.check()
                    if previous[key]["version"] != version:
                        return {"kind": "INT", "tx": name, "opIndex": op["opIndex"],
                            "key": key, "observedVersion": version,
                            "previousOpIndex": previous[key]["opIndex"],
                            "requiredVersion": previous[key]["version"]}
                writer = source["writer"]
                if writer is not None and writer != name and p["txs"][writer]["final"][key]["version"] != version:
                    return {"kind": "external_intermediate_source", "axiom": "EXT",
                        "tx": name, "opIndex": op["opIndex"], "key": key, "version": version,
                        "sourceWriter": writer, "sourceOpIndex": source["opIndex"],
                        "notAutomaticallyLabelledG1b": True}
            previous[key] = op
    return None


def _orders_hold(p, ranks, budget):
    for key in sorted(p["orders"]):
        order = p["orders"][key]
        for left, right in zip(order, order[1:]):
            budget.check()
            a = p["sources"][(key, left)]["writer"]
            b = p["sources"][(key, right)]["writer"]
            if (0 if a is None else ranks[a]) >= (0 if b is None else ranks[b]):
                return False
    return True


def _cut_holds(p, co, target, cut, budget):
    tx = p["txs"][target]
    rank = co.index(target) + 1
    # Any earlier writer of a shared key must be in this target's snapshot.
    for key in sorted(tx["final"]):
        for earlier_rank, earlier in enumerate(co[:rank - 1], 1):
            budget.check()
            if key in p["txs"][earlier]["final"] and earlier_rank > cut:
                return False
    state = {}
    for key in sorted(p["initial"]):
        budget.check()
        state[key] = p["initial"][key]
    for visible in co[:cut]:
        for key in sorted(p["txs"][visible]["final"]):
            budget.check()
            state[key] = p["txs"][visible]["final"][key]["version"]
    for op in tx["ops"]:
        budget.check()
        if op["type"] == "write":
            state[op["key"]] = op["version"]
        else:
            budget.check()
            if state[op["key"]] != op["version"]:
                return False
    return True


def analyze(text, *, model="si", max_states=None, max_semantic_checks=None):
    """Return a decision with literal semantic counters and no graph reasoning."""
    budget = Budget(MAX_STATES, MAX_CHECKS)
    definition = "cerone-no-session-si-register-v1" if model == "si" else "cerone-no-session-serial-register-v1"
    report = {"schema": 1, "algorithm": ALGORITHM, "modelDefinition": definition,
        "status": "invalid", "coverage": {"complete": False, "gaps": []},
        "findings": [], "witness": None, "execution": {}}
    decision, searched_all = "invalid-input", False
    try:
        if model not in ("si", "serial"):
            raise Invalid("model must be si or serial")
        budget = Budget(_budget(max_states, MAX_STATES, "maxStates"),
            _budget(max_semantic_checks, MAX_CHECKS, "maxSemanticChecks"))
        root, digest = _parse(text)
        report["inputSha256"] = digest
        p, gaps = _prepare(root)
        report["coverage"] = {"complete": not gaps, "gaps": gaps}
        if gaps:
            report["status"], decision = "inconclusive", "unsupported-or-incomplete-input"
        else:
            report["inputFacts"] = {"versionOrders": p["orders"]}
            finding = _preflight(p, budget)
            if finding is not None:
                report["status"], decision = "unsatisfiable", "axiom-refutation"
                report["findings"] = [finding]
            elif not p["txs"]:
                report["status"], decision = "satisfiable", "empty-execution"
                report["witness"] = {"kind": "existential-abstract-execution", "arbitration": [], "visibility": []}
            else:
                for co in itertools.permutations(sorted(p["txs"])):
                    budget.state()
                    ranks = {name: rank for rank, name in enumerate(co, 1)}
                    if not _orders_hold(p, ranks, budget):
                        continue
                    visibility = []
                    for rank, target in enumerate(co, 1):
                        candidates = range(rank) if model == "si" else (rank - 1,)
                        for cut in candidates:
                            budget.state()
                            if _cut_holds(p, co, target, cut, budget):
                                visibility.append({"tx": target, "prefixLength": cut, "initializationVisible": True})
                                break
                        else:
                            break
                    else:
                        report["status"], decision = "satisfiable", "existential-witness"
                        report["witness"] = {"kind": "existential-abstract-execution",
                            "arbitration": list(co), "visibility": visibility}
                        break
                else:
                    report["status"], decision, searched_all = "unsatisfiable", "exhaustive-search", True
    except Exhausted:
        report["status"], decision = "inconclusive", "semantic-budget"
        report["witness"] = None
    except (Invalid, TypeError, UnicodeError) as error:
        report["status"], decision = "invalid", "invalid-input"
        report["coverage"] = {"complete": False, "gaps": []}
        report["error"] = str(error)
        report["witness"] = None
    report["execution"] = {"maxStates": budget.max_states, "maxSemanticChecks": budget.max_checks,
        "states": budget.states, "semanticChecks": budget.checks,
        "budgetExhausted": budget.exhausted, "searchedAllCandidates": searched_all,
        "decisionBasis": decision,
        "counterScope": "Frozen semantic visits only; excludes bounded input validation, permutation bookkeeping and serialization."}
    return report


def verify_witness(text, witness, *, model="si"):
    """Literal CO/VIS relation and axiom checker, separate from cut search.

    This checker does not call analyze, _preflight, _orders_hold or _cut_holds.
    It is a small-input validation helper, not another exhaustive search.
    """
    try:
        root, _ = _parse(text)
        p, gaps = _prepare(root)
        if gaps or model not in ("si", "serial"):
            return False
        _fields(witness, ("kind", "arbitration", "visibility"), "witness")
        if witness["kind"] != "existential-abstract-execution":
            return False
        co = witness["arbitration"]
        if type(co) is not list or len(co) != len(p["txs"]) or set(co) != set(p["txs"]):
            return False
        if any(type(name) is not str for name in co):
            return False
        position = {None: 0, **{name: index for index, name in enumerate(co, 1)}}
        vis = {}
        if type(witness["visibility"]) is not list or len(witness["visibility"]) != len(co):
            return False
        for observation in witness["visibility"]:
            _fields(observation, ("tx", "prefixLength", "initializationVisible"), "visibility")
            name, cut = observation["tx"], observation["prefixLength"]
            if type(name) is not str or name not in p["txs"] or name in vis:
                return False
            if type(cut) is not int or not 0 <= cut < position[name] or observation["initializationVisible"] is not True:
                return False
            vis[name] = {None, *co[:cut]}
        for target, seen in vis.items():
            if any(position[source] >= position[target] for source in seen):
                return False
            # Evaluate CO;VIS subset VIS literally, including initialization.
            for middle in seen:
                for earlier in position:
                    if position[earlier] < position[middle] and earlier not in seen:
                        return False
            if model == "serial" and seen != {source for source in position if position[source] < position[target]}:
                return False
        for key, order in p["orders"].items():
            writers = [p["sources"][(key, version)]["writer"] for version in order]
            if any(position[a] >= position[b] for a, b in zip(writers, writers[1:])):
                return False
        for a, b in itertools.combinations(co, 2):
            if set(p["txs"][a]["final"]) & set(p["txs"][b]["final"]):
                if a not in vis[b] and b not in vis[a]:
                    return False
        for name in co:
            previous = {}
            for op in p["txs"][name]["ops"]:
                key, version = op["key"], op["version"]
                if op["type"] == "read":
                    if key in previous:
                        if previous[key] != version:
                            return False
                    else:
                        writers = [source for source in vis[name]
                            if source is None or key in p["txs"][source]["final"]]
                        source = max(writers, key=lambda item: position[item])
                        expected = p["initial"][key] if source is None else p["txs"][source]["final"][key]["version"]
                        if expected != version:
                            return False
                previous[key] = version
        return True
    except (Invalid, ValueError, TypeError, KeyError, IndexError):
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--model", choices=("si", "serial"), default="si")
    parser.add_argument("--max-states", type=int)
    parser.add_argument("--max-semantic-checks", type=int)
    args = parser.parse_args()
    report = analyze(args.input.read_text(encoding="utf-8"), model=args.model,
        max_states=args.max_states, max_semantic_checks=args.max_semantic_checks)
    print(json.dumps(report, ensure_ascii=True, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
