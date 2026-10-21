"""Freeze an independently constructed synthetic SQL source-closure example.

No production imports, SDK calls or database run. Catalog bytes are copied as a
DECLARED TEMPLATE from a retained capture; changed row facts are synthetic and
are never claimed to have executed in that database. Refuses existing output.
"""
from pathlib import Path
import copy
import hashlib
import itertools
import json

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "verification/business/dislock/v3-647afacfcbe14586b46714bac34c8f30"
OUT = ROOT / "verification/v3/synthetic-dislock-source-closure-v1"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(name):
    return json.loads((BASE / name / "capture.json").read_bytes())


def dt(value):
    return {"captureType": "datetime", "value": value}


def main():
    OUT.mkdir(exist_ok=False)
    busy, acquire = load("busy-acquisition"), load("acquire-heartbeat-cleanup")
    profile = copy.deepcopy(busy["sqlProfiles"][0])
    schema = profile["schema"]
    other_schema = acquire["sqlProfiles"][0]["schema"]
    read_template = next(e for e in busy["events"] if e.get("mappingId") == "dislock.read-current/1" and e["kind"] == "statement")
    renew_template = next(e for e in acquire["events"] if e.get("mappingId") == "dislock.renew/1" and e["kind"] == "statement")
    read_sql, read_executed = read_template["sql"], read_template["executedSql"]
    renew_sql = renew_template["sql"].replace(other_schema, schema)
    renew_executed = renew_template["executedSql"].replace(other_schema, schema)
    keys = {letter: "synthetic-source-closure-" + letter for letter in "xyz"}
    ids = {name: "00000000-0000-4000-8000-%012d" % n for n, name in enumerate(["x0", "y0", "z0", "x1", "x2", "y1", "z1"], 1)}
    old_expire = dt("2026-10-20 00:00:00+00:00")
    now = dt("2026-10-21 00:00:00+00:00")
    new_expire = dt("2026-10-21 00:00:05+00:00")
    owner = "synthetic-owner"
    profile["knownKeys"] = [keys[k] for k in "xyz"]
    profile["initialState"] = [{"key": keys[k], "version": ids[k + "0"], "present": True, "owner": owner, "expireAt": old_expire} for k in "xyz"]
    snapshot_window = next(e for e in profile["metadata"]["initializationWindow"] if e["kind"] == "snapshot")
    snapshot_window["rows"] = copy.deepcopy(profile["initialState"])
    profile["effectLedger"] = []
    trace = {"traceSchema": 3, "clockDomain": "synthetic-dislock-source-closure-v1", "scope": {"exclusiveWriters": True}, "sqlProfiles": [profile], "events": [], "gaps": []}

    def event(kind, **fields):
        seq = len(trace["events"]) + 1
        trace["events"].append({"seq": seq, "time": seq, "kind": kind, **fields})
        return seq

    def begin(tx):
        event("begin", tx=tx, connection="connection-" + tx)

    def commit(tx):
        event("commit_request", tx=tx)
        event("commit_ok", tx=tx)

    def read(tx, key, version, expiry):
        s = event("statement", tx=tx, sql=read_sql, executedSql=read_executed, mappingId="dislock.read-current/1", parameters=[key])
        event("rows", tx=tx, statement=s, rows=[[expiry, owner]], serverRows=[[expiry, owner, version]], columns=[{"name": "expire_at", "typeCode": 1184}, {"name": "value", "typeCode": 25}], complete=True)
        event("read", tx=tx, statement=s, mappingId="dislock.read-current/1", key=key, version=version, evidence={"serverRow": 0})

    def renew(tx, key, previous, token, expiry):
        s = event("statement", tx=tx, sql=renew_sql, executedSql=renew_executed, mappingId="dislock.renew/1", parameters=[5.0, key, owner])
        event("rows", tx=tx, statement=s, rows=[[new_expire]], serverRows=[[new_expire, previous, token, owner, expiry, now]], columns=[{"name": "expire_at", "typeCode": 1184}], complete=True)
        event("write", tx=tx, statement=s, mappingId="dislock.renew/1", key=key, version=token, predecessor=previous, evidence={"serverRow": 0, "action": "UPDATE"})
        event("condition", tx=tx, statement=s, mappingId="dislock.renew/1", predicate="owner-equals", matched=True, sourceVersion=previous,
              evidence={"serverRow": 0, "key": key, "owner": owner, "oldOwner": owner, "oldExpireAt": expiry, "serverNow": now, "oldToken": previous, "newToken": token, "action": "UPDATE"})
        profile["effectLedger"].append({"key": key, "version": token, "predecessor": previous, "action": "UPDATE", "owner": owner, "expireAt": new_expire})

    event("snapshot", initial={keys[k]: ids[k + "0"] for k in "xyz"}, consistent=True)
    begin("N"); renew("N", keys["z"], ids["z0"], ids["z1"], old_expire); commit("N")
    begin("P"); renew("P", keys["x"], ids["x0"], ids["x1"], old_expire); commit("P")
    begin("A"); read("A", keys["y"], ids["y0"], old_expire)
    begin("B"); read("B", keys["x"], ids["x1"], new_expire)
    renew("A", keys["x"], ids["x1"], ids["x2"], new_expire); commit("A")
    renew("B", keys["y"], ids["y0"], ids["y1"], old_expire); commit("B")
    profile["effectLedger"].sort(key=lambda e: (e["key"], e["version"]))
    programs = {
        "N": [("write", "z", "z0", "z1")],
        "P": [("write", "x", "x0", "x1")],
        "A": [("read", "y", "y0"), ("write", "x", "x1", "x2")],
        "B": [("read", "x", "x1"), ("write", "y", "y0", "y1")],
    }

    def replay(order):
        state = {k: k + "0" for k in "xyz"}
        for tx in order:
            for op in programs[tx]:
                if state[op[1]] != op[2]:
                    return False
                if op[0] == "write":
                    state[op[1]] = op[3]
        return True

    outcomes = {}
    for removed in [None, "N", "P", "A", "B"]:
        retained = [name for name in programs if name != removed]
        witnesses = [list(order) for order in itertools.permutations(retained) if replay(order)]
        outcomes[removed or "none"] = {"transactions": retained, "permutations": len(list(itertools.permutations(retained))), "serialWitnesses": witnesses,
                                      "sourceComplete": removed != "P", "expectedAnalysis": "inconclusive" if removed == "P" else "consistent" if witnesses else "violation"}
    assert outcomes["none"]["expectedAnalysis"] == outcomes["N"]["expectedAnalysis"] == "violation"
    assert outcomes["P"]["expectedAnalysis"] == "inconclusive"
    assert all(outcomes[k]["expectedAnalysis"] == "consistent" for k in ["A", "B"])
    files = {}
    for name, data in [("trace.json", trace), ("independent-serial-oracle.json", {"programs": programs, "outcomes": outcomes})]:
        raw = (json.dumps(data, ensure_ascii=True, separators=(",", ":")) + "\n").encode()
        with (OUT / name).open("xb") as file: file.write(raw)
        files[name] = {"sha256": sha(raw), "bytes": len(raw)}
    expected = {"schema": 1, "synthetic": True, "actualDatabaseExecution": False, "constructedBeforeProductionEvaluation": True,
                "scope": "Synthetic register/SQL source-closure reduction fixture. Database catalog/function data is a declared copied template; altered initialization, row observations and effects did not run on that database.",
                "generatorSha256": sha(Path(__file__).read_bytes()), "files": files, "initialIds": ids, "keys": keys,
                "templateBindings": {name: {"sha256": sha((BASE / name / "capture.json").read_bytes())} for name in ["busy-acquisition", "acquire-heartbeat-cleanup"]},
                "expected": {"default": "inconclusive", "explicit": "violation", "removedTransactions": ["N"], "retainedTransactions": ["P", "A", "B"], "retainedLedgerVersions": [ids["x1"], ids["x2"], ids["y1"]], "removedLedgerVersions": [ids["z1"]], "oneMinimalAfterCompleteChecks": True, "zeroBudgetOneMinimal": False},
                "deletionOutcomes": {name: value["expectedAnalysis"] for name, value in outcomes.items()}}
    raw = (json.dumps(expected, ensure_ascii=True, indent=2) + "\n").encode()
    with (OUT / "expectations.json").open("xb") as file: file.write(raw)
    print(json.dumps({"path": OUT.relative_to(ROOT).as_posix(), "events": len(trace["events"]), "expectationsSha256": sha(raw), "files": files}))


if __name__ == "__main__":
    main()
