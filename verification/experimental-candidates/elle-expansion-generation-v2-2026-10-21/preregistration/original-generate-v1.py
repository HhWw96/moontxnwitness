"""Remote-only input authoring. Imports neither checker, SDK nor adapter."""
import argparse
import hashlib
import json
from pathlib import Path

SEED = "MoonTxnWitness-Elle-common-raw-20261021-v1"
FAMILIES = {
    "point-register-v1": ("suffix-points", "repeat-points", "prefix-and-suffix", "multi-key-owners", "alternating-sources"),
    "append-list-v1": ("source-subsets", "reversed-observations", "repeated-observed-identity", "prefix-and-suffix", "mixed-list-orders"),
}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class Draw:
    def __init__(self, model, family, candidate):
        self.prefix, self.at = [SEED, model, family, candidate], 0
    def take(self, modulus):
        block = hashlib.sha256(canonical(self.prefix + [self.at])).digest()
        self.at += 1
        return int.from_bytes(block[:8], "big") % modulus
    def order(self, values):
        return [value for _, _, value in sorted((self.take(1 << 63), index, value)
                for index, value in enumerate(values))]


def trace(model, family, candidate):
    draw = Draw(model, family, candidate)
    n, k = 2 + draw.take(5), 2 + draw.take(3)
    keys = ["key-" + str(i) for i in range(k)]
    events = []
    def event(kind, **facts):
        events.append({"seq": len(events) + 1, "time": len(events) + 1, "kind": kind, **facts})
    initial = {key: ("initial-" + key if model == "point-register-v1" else []) for key in keys}
    event("snapshot", initial=initial, consistent=True)
    for t in range(n):
        event("begin", tx="T" + str(t), connection="C" + str(t))
    has_prefix = family == "prefix-and-suffix"
    if has_prefix:
        for t in draw.order(list(range(n))):
            for _ in range(1 + draw.take(3)):
                key = keys[draw.take(k)]
                if model == "point-register-v1":
                    event("read", tx="T" + str(t), key=key, version=initial[key])
                else:
                    event("list_read", tx="T" + str(t), key=key, items=[])
    if model == "point-register-v1":
        written = {key: "written-" + key for key in keys}
        for key in draw.order(keys):
            owner = draw.take(n)
            if family == "multi-key-owners":
                owner %= min(2, n)
            event("write", tx="T" + str(owner), key=key,
                  version=written[key], predecessor=initial[key])
        for t in draw.order(list(range(n))):
            count = 6 if family == "repeat-points" else 1 + draw.take(5)
            last = None
            for position in range(count):
                key = last if last is not None and family == "repeat-points" and position % 2 else keys[draw.take(k)]
                use_written = draw.take(2) if family != "alternating-sources" else position % 2
                event("read", tx="T" + str(t), key=key,
                      version=written[key] if use_written else initial[key])
                last = key
    else:
        per_key = {key: [] for key in keys}
        appends = []
        for i in range(2 + draw.take(7)):
            key = keys[draw.take(k)]
            item = {"id": "append-" + str(i), "value": ("same", "same", "different", "")[draw.take(4)]}
            event("append", tx="T" + str(draw.take(n)), key=key, **item)
            per_key[key].append(item)
            appends.append((key, item))
        duplicate_emitted = False
        for t in draw.order(list(range(n))):
            for _ in range(1 + draw.take(5)):
                if family == "repeated-observed-identity" and not duplicate_emitted:
                    key, item = appends[draw.take(len(appends))]
                    items = [dict(item), dict(item)]
                    duplicate_emitted = True
                else:
                    key = keys[draw.take(k)]
                    items = [dict(item) for item in per_key[key] if draw.take(2)]
                    if family == "reversed-observations":
                        items.reverse()
                    elif family == "mixed-list-orders":
                        items = draw.order(items)
                event("list_read", tx="T" + str(t), key=key, items=items)
    for t in draw.order(list(range(n))):
        event("commit_request", tx="T" + str(t))
    for t in draw.order(list(range(n))):
        event("commit_ok", tx="T" + str(t))
    return {"traceSchema": 3, "dataModel": model, "clockDomain": "generated-original-domain",
            "scope": {"exclusiveWriters": True}, "events": events, "gaps": []}


def program_shape(value):
    # Identity spelling, global ACK order and timestamps cannot manufacture shapes.
    keys = {key: i for i, key in enumerate(value["events"][0]["initial"])}
    txs, programs, sources, values = {}, [], {}, {}
    if value["dataModel"] == "point-register-v1":
        sources = {version: ["initial", keys[key]]
                   for key, version in value["events"][0]["initial"].items()}
    def payload(text):
        return values.setdefault(text, len(values))
    for event in value["events"][1:]:
        kind, tx = event["kind"], event["tx"]
        if kind == "begin":
            txs[tx] = len(txs)
            programs.append([])
            continue
        if kind in {"commit_request", "commit_ok"}:
            continue
        program = programs[txs[tx]]
        key = keys[event["key"]]
        if kind == "write":
            pointer = ["write", txs[tx], len(program)]
            item = [kind, key, pointer, sources[event["predecessor"]]]
            sources[event["version"]] = pointer
        elif kind == "read":
            item = [kind, key, sources[event["version"]]]
        elif kind == "append":
            pointer = ["append", txs[tx], len(program)]
            item = [kind, key, pointer, payload(event["value"])]
            sources[event["id"]] = pointer
        elif kind == "list_read":
            item = [kind, key, [[sources[x["id"]], payload(x["value"])] for x in event["items"]]]
        else:
            raise ValueError("Unexpected generated kind")
        program.append(item)
    return {"model": value["dataModel"], "keyCount": len(keys), "programs": programs}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-comparison", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    smoke_raw = args.smoke_comparison.read_bytes()
    if len(smoke_raw) > 8 * 1024 * 1024:
        raise ValueError("Smoke receipt byte bound")
    smoke = json.loads(smoke_raw)
    if not (smoke.get("passed") is True and smoke.get("actualElleResultConsumed") is True
            and smoke.get("actualMoonBitExecuted") is True and smoke.get("actualDualCheckerCases") == 8
            and smoke.get("originalInputSha256") == "e9430dbf5faca86c337fca8a090464004a362370c6e134f710a344f5b8ef8d90"):
        raise ValueError("Actual original smoke prerequisite missing")
    args.output.mkdir(parents=True, exist_ok=False)
    here = Path(__file__).resolve().parent
    receipt = {"schema": 1, "kind": "input-generation-before-evaluator", "passed": False,
               "smokeComparisonSha256": sha(smoke_raw), "seed": SEED,
               "actualElleExecutedDuringGeneration": False, "actualMoonBitExecutedDuringGeneration": False,
               "generatorSha256": sha(Path(__file__).read_bytes()),
               "contractSha256": sha((here / "contract.json").read_bytes()), "families": []}
    raw_hashes, shapes, count, byte_count = set(), set(), 0, 0
    dataset = args.output / "inputs.jsonl"
    try:
        with dataset.open("xb") as stream:
            for model, families in FAMILIES.items():
                for family in families:
                    accepted = 0
                    family_row = {"model": model, "family": family, "accepted": 0, "duplicateCandidates": 0}
                    receipt["families"].append(family_row)
                    for candidate in range(20000):
                        original = trace(model, family, candidate)
                        original_sha, shape_sha = sha(canonical(original)), sha(canonical(program_shape(original)))
                        if original_sha in raw_hashes or shape_sha in shapes:
                            family_row["duplicateCandidates"] += 1
                            continue
                        row = {"schema": 1, "id": ("register" if model == "point-register-v1" else "list") + "-" + str(count),
                               "family": family, "candidate": candidate, "inputSha256": original_sha,
                               "programShapeSha256": shape_sha, "input": original}
                        line = canonical(row) + b"\n"
                        if len(line) > 1048576 or byte_count + len(line) > 33554432:
                            raise ValueError("Frozen dataset byte budget")
                        stream.write(line)
                        raw_hashes.add(original_sha)
                        shapes.add(shape_sha)
                        byte_count += len(line)
                        count += 1
                        accepted += 1
                        family_row["accepted"] = accepted
                        if accepted == 200:
                            break
                    if accepted != 200:
                        raise ValueError("Preregistered family candidate space exhausted")
        receipt.update(passed=count == 2000, records=count, bytes=byte_count,
                       exactUnique=len(raw_hashes), alphaProgramShapeUnique=len(shapes),
                       datasetSha256=sha(dataset.read_bytes()), evaluatorMayRunOnlyAfterIndependentInputFreeze=True)
    except Exception as error:
        receipt.update(errorClass=type(error).__name__, reason=str(error), records=count, bytes=byte_count)
    finally:
        with (args.output / "generation-receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(receipt, stream, indent=2)
            stream.write("\n")
    print(json.dumps({"passed": receipt["passed"], "records": count}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
