"""Audit Git's index, without walking build trees or changing repository history."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import subprocess


def command(root, *args, input=None):
    return subprocess.check_output(["git", "-C", str(root), *args], input=input)


def inventory(root):
    records = []
    for item in command(root, "ls-files", "--stage", "-z").split(b"\0"):
        if not item:
            continue
        meta, name = item.split(b"\t", 1)
        mode, oid, stage = meta.decode("ascii").split()
        if stage != "0":
            raise ValueError("Resolve merge conflicts before auditing the index")
        records.append({"path": name.decode("utf-8"), "mode": mode, "oid": oid})
    oids = sorted({r["oid"] for r in records})
    sizes = {}
    output = command(root, "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)",
                     input=("\n".join(oids) + "\n").encode("ascii")) if oids else b""
    for row in output.decode("ascii").splitlines():
        oid, kind, size = row.split()
        if kind != "blob":
            raise ValueError("Only regular tracked blobs are supported by this policy")
        sizes[oid] = int(size)
    for record in records:
        record["bytes"] = sizes[record["oid"]]
    return records


def check(records, policy):
    failures, groups, blobs = [], defaultdict(lambda: [0, 0]), defaultdict(list)
    total = sum(r["bytes"] for r in records)
    if len(records) > policy["maxTrackedFiles"]:
        failures.append("tracked file count exceeds the reviewed limit")
    if total > policy["maxTrackedBytes"]:
        failures.append("tracked expanded bytes exceed the reviewed limit")
    for r in records:
        p = r["path"]
        parts = p.split("/")
        groups[parts[0]][0] += 1
        groups[parts[0]][1] += r["bytes"]
        blobs[r["oid"]].append(r)
        if r["mode"] not in ("100644", "100755"):
            failures.append(p + ": unsupported tracked link or submodule")
        if r["bytes"] > policy["maxNewFileBytes"] and policy["frozenLargeFiles"].get(p) != r["oid"]:
            failures.append(p + ": oversized new/changed blob; publish it as an external artifact")
        if p.endswith(".mbt") and not p.startswith("src/"):
            if policy["frozenExternalMoonbit"].get(p) != r["oid"]:
                failures.append(p + ": historical/foreign MoonBit source belongs outside the current tree")
        if parts[-1] == "moon.mod" and p != "moon.mod":
            if policy["frozenExternalMoonbit"].get(p) != r["oid"]:
                failures.append(p + ": nested complete MoonBit project")
        if any(x in parts for x in ("_build", "node_modules", "__pycache__", ".git")):
            failures.append(p + ": generated/cache tree must not be tracked")
        if parts[0] in ("artifacts", "dist"):
            failures.append(p + ": build/release output must not be tracked")
    for copies in blobs.values():
        sources = sorted(r["path"] for r in copies if r["path"].endswith(".mbt"))
        if len(sources) > 1 and sources not in policy.get("frozenSourceDuplicateGroups", []):
            failures.append("duplicated MoonBit source: " + ", ".join(sources))
    return {
        "passed": not failures, "scope": "Git index; expanded blob bytes, not .git disk usage",
        "trackedFiles": len(records), "trackedBytes": total,
        "duplicateFiles": sum(len(v) - 1 for v in blobs.values()),
        "duplicateExpandedBytes": sum(v[0]["bytes"] * (len(v) - 1) for v in blobs.values()),
        "topLevel": dict(sorted(groups.items())), "failures": failures,
        "historyRewritten": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--policy", type=Path)
    args = parser.parse_args()
    policy = args.policy or args.root / "scripts/repository-policy.json"
    report = check(inventory(args.root), json.loads(policy.read_text("utf-8")))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
