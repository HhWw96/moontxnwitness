"""Bounded raw-fact representation adapter. It is not a consistency oracle."""
import argparse
import hashlib
import json
from pathlib import Path
import re


class Invalid(ValueError): pass
class Outside(ValueError): pass


def require(ok, reason):
    if not ok: raise Invalid(reason)


def identity(value):
    require(type(value) is str and bool(value), "nonempty scalar identity required")
    require(all(not 0xd800 <= ord(c) <= 0xdfff for c in value), "invalid Unicode scalar")
    require(len(value.encode("utf-16-le")) <= 512, "identity length")
    return value


def exact(value, names):
    require(type(value) is dict and set(value) == set(names), "exact object fields required")


def adapt(trace):
    exact(trace, ("traceSchema", "dataModel", "clockDomain", "scope", "events", "gaps"))
    require(type(trace["traceSchema"]) is int and trace["traceSchema"] == 3, "trace schema")
    identity(trace["clockDomain"])
    model = trace["dataModel"]
    if model not in ("point-register-v1", "append-list-v1"): raise Outside("unsupported model")
    exact(trace["scope"], ("exclusiveWriters",))
    if trace["scope"]["exclusiveWriters"] is not True or trace["gaps"] != []:
        raise Outside("incomplete original coverage")
    events = trace["events"]
    require(type(events) is list and 1 <= len(events) <= 512, "event capacity")
    previous = -1
    for index, event in enumerate(events, 1):
        require(type(event) is dict and type(event.get("seq")) is int and event["seq"] == index,
                "original event sequence")
        t = event.get("time")
        require(type(t) is int and 0 <= t <= 9007199254740991 and previous <= t, "safe monotonic time")
        previous = t
        require(type(event.get("kind")) is str, "event kind")
    first = events[0]
    exact(first, ("seq", "time", "kind", "initial", "consistent"))
    require(first["kind"] == "snapshot", "first original snapshot")
    if first["consistent"] is not True: raise Outside("inconsistent initial snapshot")
    initial = first["initial"]
    require(type(initial) is dict and len(initial) <= 128, "initial key capacity")
    for key in initial: identity(key)
    versions, appends, key_writes = {}, {}, set()
    if model == "point-register-v1":
        for key, version in initial.items():
            identity(version)
            require(version not in versions, "duplicate global initial version")
            versions[version] = key
    else:
        require(all(type(items) is list for items in initial.values()), "list snapshot arrays required")
        if any(initial.values()): raise Outside("nonempty initial lists cannot become synthetic transactions")
    txs, connections, processes, operations, seq_map = {}, {}, {}, [], []
    data_ops = 0
    for event in events[1:]:
        kind = event["kind"]
        if kind not in ("begin", "read", "write", "append", "list_read", "commit_request", "commit_ok"):
            raise Outside("unsupported lifecycle or statement: " + kind)
        tx = identity(event.get("tx"))
        if kind == "begin":
            exact(event, ("seq", "time", "kind", "tx", "connection"))
            conn = identity(event["connection"])
            require(tx not in txs and conn not in connections, "transaction/connection overlap")
            if len(txs) >= 6: raise Outside("transaction capacity")
            process = processes.setdefault(conn, len(processes))
            txs[tx] = {"state": "active", "conn": conn, "process": process, "mops": [], "invoke": len(operations)}
            connections[conn] = tx
            operations.append({"index": len(operations), "process": process, "type": "invoke", "f": "txn", "value": []})
            seq_map.append({"checkerIndex": len(operations)-1, "rawSeq": event["seq"], "tx": tx})
            continue
        require(tx in txs, "event before begin")
        current = txs[tx]
        if kind == "commit_request":
            exact(event, ("seq", "time", "kind", "tx"))
            require(current["state"] == "active", "invalid commit request")
            current["state"] = "committing"
            continue
        if kind == "commit_ok":
            exact(event, ("seq", "time", "kind", "tx"))
            require(current["state"] == "committing", "commit acknowledgement without request")
            current["state"] = "committed"
            del connections[current["conn"]]
            operations[current["invoke"]]["value"] = [[f, k, None if f == "r" else v] for f,k,v in current["mops"]]
            operations.append({"index": len(operations), "process": current["process"], "type": "ok", "f": "txn", "value": current["mops"]})
            seq_map.append({"checkerIndex": len(operations)-1, "rawSeq": event["seq"], "tx": tx})
            continue
        require(current["state"] == "active", "operation outside active transaction")
        key = identity(event.get("key"))
        if key not in initial: raise Outside("key absent from actual initial snapshot")
        data_ops += 1
        if data_ops > 128: raise Outside("data-operation capacity")
        if model == "point-register-v1":
            if kind not in ("read", "write"): raise Invalid("mixed register/list operation")
            fields = ("seq", "time", "kind", "tx", "key", "version") + (("predecessor",) if kind == "write" else ())
            exact(event, fields)
            version = identity(event["version"])
            if kind == "write":
                require(version not in versions, "duplicate global write version")
                if key in key_writes: raise Outside("multiple writers require unavailable factual total transaction order")
                if event["predecessor"] != initial[key]: raise Outside("unsupported predecessor source")
                key_writes.add(key); versions[version] = key
                mop = ["w", key, version]
            else:
                if versions.get(version) != key: raise Outside("missing, future or wrong-key source")
                mop = ["r", key, None if version == initial[key] else version]
        else:
            if kind not in ("append", "list_read"): raise Invalid("mixed list/register operation")
            if kind == "append":
                exact(event, ("seq", "time", "kind", "tx", "key", "id", "value"))
                item = identity(event["id"])
                require(item not in appends, "duplicate global append identity")
                require(type(event["value"]) is str, "string append business value")
                appends[item] = (key, event["value"])
                mop = ["append", key, item]
            else:
                exact(event, ("seq", "time", "kind", "tx", "key", "items"))
                require(type(event["items"]) is list and len(event["items"]) <= 128, "list observation capacity")
                values = []
                for item in event["items"]:
                    exact(item, ("id", "value")); identity(item["id"])
                    require(type(item["value"]) is str, "string observed business value")
                    if appends.get(item["id"]) != (key, item["value"]):
                        raise Outside("missing, future, wrong-key or content-mismatched append source")
                    values.append(item["id"])
                mop = ["r", key, values]
        current["mops"].append(mop)
    if any(tx["state"] != "committed" for tx in txs.values()): raise Outside("incomplete outcome")
    return {"model": model, "operations": operations, "originalSeqMapping": seq_map,
            "initialRegisterVersionRenaming": initial if model == "point-register-v1" else None}


def edn(value):
    if value is None: return "nil"
    if value is True: return "true"
    if value is False: return "false"
    if type(value) is int: return str(value)
    if type(value) is str: return json.dumps(value, ensure_ascii=False)
    if type(value) is list: return "[" + " ".join(edn(x) for x in value) + "]"
    if type(value) is dict: return "{" + " ".join(edn(k)+" "+edn(v) for k,v in value.items()) + "}"
    raise Invalid("unsupported EDN transport value")


def unique(pairs):
    out = {}
    for k,v in pairs:
        require(k not in out, "duplicate JSON key")
        out[k] = v
    return out


def wire_budget(raw):
    require(len(raw) <= 8*1024*1024, "smoke input byte limit")
    quoted, escaped, scalar, depth, nodes = False, False, False, 0, 0
    for ch in raw.decode("utf-8"):
        if quoted:
            if escaped: escaped = False
            elif ch == "\\": escaped = True
            elif ch == '"': quoted = False
            continue
        if ch == '"': quoted = True; scalar = False; nodes += 1
        elif ch in "[{": depth += 1; nodes += 1; scalar = False
        elif ch in "]}": depth -= 1; scalar = False
        elif ch in " \t\r\n,:": scalar = False
        elif not scalar: nodes += 1; scalar = True
        require(0 <= depth <= 32 and nodes <= 65536, "preparse depth/node budget")
    require(not quoted and depth == 0, "incomplete JSON input")


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--input", type=Path, default=Path(__file__).parent/"smoke-inputs-v1.json")
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    require(args.input.stat().st_size <= 8*1024*1024, "smoke input byte limit")
    with args.input.open("rb") as file: raw = file.read(8*1024*1024+1)
    wire_budget(raw); data = json.loads(raw, object_pairs_hook=unique)
    require(data["schema"] == 1 and 1 <= len(data["cases"]) <= 2000, "case capacity")
    rows, requests = [], []
    for case in data["cases"]:
        require(type(case["id"]) is str and re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", case["id"]), "safe unique case id")
        require(all(row["id"] != case["id"] for row in rows), "duplicate case id")
        try:
            converted = adapt(case["input"]); status, reason = "eligible", None
        except Outside as error: converted, status, reason = None, "outside", str(error)
        except (Invalid, KeyError, TypeError, UnicodeError) as error:
            converted, status, reason = None, "invalid", str(error)
        row = {"id": case["id"], "disposition": status, "reason": reason,
               "expected": case["expected"], "passed": status == case["expected"]["adapter"]}
        if converted is not None:
            request = {"id": case["id"], **converted, "expectedElleValid": case["expected"]["elleValid"]}
            requests.append(request); row["converted"] = converted
        rows.append(row)
    for name,value in (("adapter-receipt.json", {"schema":1,"passed":all(r["passed"] for r in rows),
                        "sourceInputSha256":hashlib.sha256(raw).hexdigest(),"actualElleExecuted":False,"cases":rows}),
                       ("requests.json", requests)):
        with (args.output/name).open("x",encoding="utf-8",newline="\n") as file:
            json.dump(value,file,ensure_ascii=True,indent=2); file.write("\n")
    with (args.output/"requests.edn").open("x",encoding="utf-8",newline="\n") as file:
        for request in requests: file.write(edn(request)+"\n")
    return 0 if all(r["passed"] for r in rows) else 1


if __name__ == "__main__": raise SystemExit(main())
