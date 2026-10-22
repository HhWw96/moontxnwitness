"""Prepare an additive SDK candidate without changing the release checkout."""
from pathlib import Path
import hashlib
import json
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PAYLOAD = HERE / "payload"
sha = lambda raw: hashlib.sha256(raw).hexdigest()
for directory in ("cmd", "examples", "scripts", "docs"):
    (PAYLOAD / directory).mkdir(parents=True, exist_ok=True)

sdk = (ROOT / "cmd/sdk.mjs").read_text(encoding="utf8")
assert "analyzeListV3" not in sdk, "Do not duplicate an existing fixed-model entry"
sdk = sdk.replace("export { makeCapsuleV3, replayCapsuleV3 } from './evidence.mjs';",
                  "import { makeCapsuleV3, replayCapsuleV3 } from './evidence.mjs';\nexport { makeCapsuleV3, replayCapsuleV3 };")
sdk += (HERE / "list-sdk-additions.mjs").read_text(encoding="utf8")
(PAYLOAD / "cmd/sdk.mjs").write_text(sdk, encoding="utf8", newline="\n")

manual = json.loads((ROOT / "fixtures/list-v3/manual.json").read_text(encoding="utf8"))
source = next(case for case in manual if case["id"] == "two-key-read-append-cycle")
trace = json.loads(source["traceText"])
initial_y = trace["events"][0]["initial"]["y"]
trace["events"][1:1] = [
    {"kind": "begin", "tx": "noise", "connection": "noise"},
    {"kind": "list_read", "tx": "noise", "key": "y", "items": initial_y},
    {"kind": "commit_request", "tx": "noise"},
    {"kind": "commit_ok", "tx": "noise"},
]
for index, event in enumerate(trace["events"]):
    event["seq"] = index + 1
    event["time"] = index
(PAYLOAD / "examples/list-cycle.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")
for name in ("examples/list-roundtrip.mjs", "scripts/list-sdk-test.mjs", "docs/list-sdk.md"):
    shutil.copyfile(HERE / "drafts" / name, PAYLOAD / name)

before = {}
for path in ("cmd/sdk.mjs", "cmd/evidence.mjs", "dist/build-manifest.json", "dist/core.mjs", "dist/capture-core.mjs", "dist/sdk.mjs", "dist/evidence.mjs", "fixtures/list-v3/manual.json", "scripts/list-v3-oracle.py"):
    raw = (ROOT / path).read_bytes()
    before[path] = {"bytes": len(raw), "sha256": sha(raw)}
runtime = HERE / "runtime"
runtime.mkdir(exist_ok=True)
for name in ("core.mjs", "capture-core.mjs", "evidence.mjs", "build-manifest.json"):
    shutil.copyfile(ROOT / "dist" / name, runtime / name)
shutil.copyfile(PAYLOAD / "cmd/sdk.mjs", runtime / "sdk.mjs")
shutil.copyfile(ROOT / "dist/sdk.mjs", runtime / "generic-sdk.mjs")
baseline = HERE / "baseline-inputs.json"
if baseline.exists():
    assert json.loads(baseline.read_text(encoding="utf8")) == before, "Keep the original source baseline frozen"
else:
    baseline.write_text(json.dumps(before, indent=2) + "\n", encoding="utf8", newline="\n")
print(json.dumps({"prepared": True, "payloadFiles": 5, "sourceFixture": source["id"], "fixtureInputSha256": source["inputSha256"], "runtime": json.loads((runtime / "build-manifest.json").read_text())}))
