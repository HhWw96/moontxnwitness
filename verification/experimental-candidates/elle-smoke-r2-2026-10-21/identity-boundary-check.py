"""Remote-only adapter-domain checks; never invokes either consistency checker."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    fixture_path = here / "identity-boundaries-v2.json"
    raw = fixture_path.read_bytes()
    data = json.loads(raw)
    spec = importlib.util.spec_from_file_location("frozen_elle_v2_adapter", here / "prepare.py")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    rows = []
    for case in data["identityCases"]:
        try:
            adapter.identity(case["value"])
            actual = "valid"
        except (adapter.Invalid, UnicodeError):
            actual = "invalid"
        rows.append({"id": case["id"], "kind": "identity", "expected": case["expected"],
                     "actual": actual, "passed": actual == case["expected"]})
    for case in data["traceCases"]:
        try:
            adapter.adapt(case["input"])
            actual = "eligible"
        except adapter.Outside:
            actual = "outside"
        except (adapter.Invalid, KeyError, TypeError, UnicodeError):
            actual = "invalid"
        rows.append({"id": case["id"], "kind": "full-raw-trace", "expected": case["expected"],
                     "actual": actual, "passed": actual == case["expected"]})
    receipt = {"schema": 1, "kind": "actual-v2-adapter-identity-boundaries",
               "passed": all(row["passed"] for row in rows), "checks": len(rows),
               "fixtureSha256": hashlib.sha256(raw).hexdigest(),
               "adapterSha256": hashlib.sha256((here / "prepare.py").read_bytes()).hexdigest(),
               "actualAdapterExecuted": True, "actualElleExecuted": False,
               "actualMoonBitExecuted": False, "cases": rows}
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2, ensure_ascii=True)
        stream.write("\n")
    print(json.dumps({"passed": receipt["passed"], "checks": len(rows)}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
