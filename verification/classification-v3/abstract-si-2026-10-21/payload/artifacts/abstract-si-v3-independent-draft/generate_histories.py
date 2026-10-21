"""Frozen seeded histories, constructed without importing/calling any oracle."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random


ROOT = Path(__file__).resolve().parent
SEED = 1397313861
PLAN_SHA = "b78dc5056e49906431d6d431d343063002d9aa2176906f1334a40da716a21dac"


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def event(kind, key, version):
    return {"type": kind, "key": key, "version": version}


def finish(initial, transactions, co):
    txmap = {tx["id"]: tx for tx in transactions}
    orders = {key: [version] for key, version in initial.items()}
    for name in co:
        final = {}
        for op in txmap[name]["ops"]:
            if op["type"] == "write":
                final[op["key"]] = op["version"]
        for key, version in final.items():
            orders[key].append(version)
    return {"schema": 1, "dataModel": "point-register-v1", "complete": True,
        "initial": initial, "versionOrders": orders, "transactions": transactions}


def valid_history(rng, serial=False):
    n, k = rng.randint(2, 6), rng.randint(1, 4)
    keys = ["k" + str(index) for index in range(k)]
    initial = {key: key + ":initial" for key in keys}
    co = ["T" + str(index) for index in range(n)]
    rng.shuffle(co)
    last_writer, finals, txs, cuts = {}, {}, [], []
    for index, name in enumerate(co):
        planned = [key for key in keys if rng.random() < 0.45]
        if index == 0 and not planned:
            planned = [keys[0]]
        minimum = max((last_writer.get(key, 0) for key in planned), default=0)
        cut = index if serial else rng.randint(minimum, index)
        state = dict(initial)
        for visible in co[:cut]:
            state.update(finals[visible])
        actions = [("read", rng.choice(keys)) for _ in range(rng.randint(1, 5))]
        actions += [("write", key) for key in planned]
        for _ in range(rng.randint(0, 5)):
            actions.append(("write", rng.choice(planned)) if planned and rng.random() < 0.5
                else ("read", rng.choice(keys)))
        rng.shuffle(actions)
        ops, final, number = [], {}, 0
        for kind, key in actions:
            if kind == "write":
                number += 1
                version = key + ":" + name + ":w" + str(number)
                state[key] = version
                final[key] = version
            else:
                version = state[key]
            ops.append(event(kind, key, version))
        finals[name] = final
        for key in final:
            last_writer[key] = index + 1
        txs.append({"id": name, "status": "committed", "ops": ops})
        cuts.append({"tx": name, "prefixLength": cut, "initializationVisible": True})
    rng.shuffle(txs)
    return finish(initial, txs, co), {"kind": "existential-abstract-execution",
        "arbitration": co, "visibility": cuts}


def all_sources(history):
    result = {(key, version): (None, None) for key, version in history["initial"].items()}
    for tx in history["transactions"]:
        for index, op in enumerate(tx["ops"]):
            if op["type"] == "write":
                result[(op["key"], op["version"])] = (tx["id"], index)
    return result


def mutate_read(rng, history, own_future):
    sources = all_sources(history)
    eligible = []
    for tx in history["transactions"]:
        for index, op in enumerate(tx["ops"]):
            if op["type"] != "read":
                continue
            choices = [version for (key, version), (writer, producer_index) in sources.items()
                if key == op["key"] and version != op["version"] and
                (not own_future or (writer == tx["id"] and producer_index > index))]
            if choices:
                eligible.append((op, choices))
    if not eligible:
        return False
    op, choices = rng.choice(eligible)
    op["version"] = rng.choice(choices)
    return True


def skew_ring(rng):
    n = rng.randint(2, 6)
    names = ["T" + str(index) for index in range(n)]
    initial = {"ring" + str(index): "r" + str(index) + ":initial" for index in range(n)}
    initial["noise"] = "noise:initial"
    txs = []
    for index, name in enumerate(names):
        own, other = "ring" + str(index), "ring" + str((index + 1) % n)
        state, ops = dict(initial), []
        for step in range(rng.randint(1, 6)):
            if rng.random() < 0.5:
                ops.append(event("read", "noise", initial["noise"]))
            else:
                value = "r" + str(index) + ":own" + str(step)
                ops.append(event("write", own, value)); state[own] = value
                if rng.random() < 0.6:
                    ops.append(event("read", own, value))
        ops.append(event("read", other, initial[other]))
        ops.append(event("write", own, "r" + str(index) + ":final"))
        if rng.random() < 0.5:
            ops.append(event("read", own, "r" + str(index) + ":final"))
        txs.append({"id": name, "status": "committed", "ops": ops})
    co = list(names); rng.shuffle(co); rng.shuffle(txs)
    witness = {"kind": "existential-abstract-execution", "arbitration": co,
        "visibility": [{"tx": name, "prefixLength": 0, "initializationVisible": True} for name in co]}
    return finish(initial, txs, co), witness


def make(rng, family, ordinal):
    value, construction = valid_history(rng, serial=(family == "constructed-serial"))
    options = {}
    if family in ("constructed-si", "constructed-serial"):
        return value, construction, options
    if family == "known-source-read-mutation":
        if not mutate_read(rng, value, own_future=ordinal < 50):
            return None
    elif family == "INT-refutation":
        sources = all_sources(value)
        key, version = next((key, version) for (key, version), (writer, _) in sources.items() if writer is not None)
        rng.choice(value["transactions"])["ops"].extend([
            event("read", key, value["initial"][key]), event("read", key, version)])
    elif family in ("lost-update", "external-intermediate-source"):
        key = "fresh"
        value["initial"][key] = "fresh:initial"
        txmap = {tx["id"]: tx for tx in value["transactions"]}
        a, b = construction["arbitration"][:2]
        if family == "lost-update":
            txmap[a]["ops"].extend([event("read", key, "fresh:initial"), event("write", key, "fresh:A")])
            txmap[b]["ops"].extend([event("read", key, "fresh:initial"), event("write", key, "fresh:B")])
        else:
            txmap[a]["ops"].extend([event("write", key, "fresh:intermediate"), event("write", key, "fresh:final")])
            txmap[b]["ops"].append(event("read", key, "fresh:intermediate"))
        value = finish(value["initial"], value["transactions"], construction["arbitration"])
    elif family == "write-skew-ring":
        return (*skew_ring(rng), options)
    elif family == "unknown-source":
        key = rng.choice(list(value["initial"]))
        rng.choice(value["transactions"])["ops"].append(event("read", key, "unobserved:source"))
    elif family == "zero-semantic-or-state-budget":
        options = {"max_states": 0} if ordinal % 2 == 0 else {"max_semantic_checks": 0}
        return value, construction, options
    else:
        raise ValueError(family)
    return value, None, options


def shape_of(value):
    keys = {key: index for index, key in enumerate(value["initial"])}
    txs = {tx["id"]: index for index, tx in enumerate(value["transactions"])}
    sources = all_sources(value)
    unknown = {}

    def source(key, version):
        producer = sources.get((key, version))
        if producer is None:
            unknown.setdefault((key, version), len(unknown))
            return ["unknown", unknown[(key, version)]]
        writer, index = producer
        return ["initial", keys[key]] if writer is None else ["write", txs[writer], index]

    return {"transactions": [[op["type"], keys[op["key"]], source(op["key"], op["version"])]
        for tx in value["transactions"] for op in [{"type": "begin", "key": next(iter(keys)), "version": value["initial"][next(iter(keys))]}] + tx["ops"]],
        "operationCounts": [len(tx["ops"]) for tx in value["transactions"]],
        "orders": [[source(key, version) for version in value["versionOrders"][key]] for key in keys]}


def main():
    plan_file = ROOT / "generation-plan-v1.json"
    if hashlib.sha256(plan_file.read_bytes()).hexdigest() != PLAN_SHA:
        raise SystemExit("Generation plan differs from its pre-generator freeze")
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    target, manifest = ROOT / "generated-inputs-v1.jsonl", ROOT / "generated-inputs-v1-manifest.json"
    if target.exists() or manifest.exists():
        raise SystemExit("Refusing to overwrite frozen generated inputs")
    rng = random.Random(SEED)
    records, inputs, shapes = [], set(), set()
    attempts, duplicates, unavailable = 0, 0, 0
    family_attempts = Counter()
    for quota in plan["quotas"]:
        accepted = 0
        while accepted < quota["count"]:
            attempts += 1; family_attempts[quota["family"]] += 1
            if attempts > 100_000:
                raise SystemExit("Registered generation attempt limit exceeded; no oracle outputs read")
            result = make(rng, quota["family"], accepted)
            if result is None:
                unavailable += 1
                continue
            value, construction, options = result
            if sum(len(tx["ops"]) for tx in value["transactions"]) > 128:
                raise SystemExit("Generator exceeded registered operation capacity")
            input_sha, shape_sha = digest(value), digest(shape_of(value))
            if input_sha in inputs or shape_sha in shapes:
                duplicates += 1
                continue
            inputs.add(input_sha); shapes.add(shape_sha)
            payload_facts = []
            if len(records) % 3 == 0:
                payload_facts = [{"key": key, "version": version, "payload": "same-business-value"}
                    for key, version in all_sources(value)]
            records.append({"id": "si-generated-" + str(len(records)).zfill(4),
                "family": quota["family"], "input": value, "inputSha256": input_sha,
                "programShapeSha256": shape_sha, "options": options,
                "expectedSi": quota["expectedSi"], "expectedSerial": quota["expectedSerial"],
                "constructionWitness": construction, "businessValueFacts": payload_facts})
            accepted += 1
    raw = "".join(canonical(record) + "\n" for record in records).encode()
    target.write_bytes(raw)
    result = {"schema": 1, "phase": "generated-input-freeze-before-evaluation",
        "seed": SEED, "generatorSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "generationPlanSha256": PLAN_SHA, "inputFile": target.name,
        "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        "histories": len(records), "uniqueInputHashes": len(inputs), "uniqueProgramShapeHashes": len(shapes),
        "programShapeMethod": "literal-identity normalized, first-appearance producer positions; not graph-isomorphism canonicalization",
        "familyCounts": dict(Counter(record["family"] for record in records)),
        "familyAttempts": dict(family_attempts), "generationAttempts": attempts,
        "duplicateInputsOrShapesRetriedBeforeEvaluation": duplicates,
        "unavailableRequiredOwnFutureMutationRetriedBeforeEvaluation": unavailable,
        "repeatedPayloadSidecarHistories": sum(bool(record["businessValueFacts"]) for record in records),
        "oracleOutputsRead": False, "productionOutputsRead": False, "testsExecuted": False}
    manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
