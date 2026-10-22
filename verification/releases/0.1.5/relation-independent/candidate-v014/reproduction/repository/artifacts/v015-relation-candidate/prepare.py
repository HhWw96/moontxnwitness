"""Build a relation-only additive candidate with frozen baseline inputs."""
from pathlib import Path
import hashlib
import json
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf8", newline="\n")
def transform(text):
    return (text.replace("append-list-v1", "relation-set-v1")
            .replace("append-list-serializable-v1", "relation-set-serializable-v1")
            .replace("AppendListCaptureV3", "RelationCaptureV3")
            .replace("List", "Relation").replace("list", "relation"))

sdk = (ROOT / "cmd/sdk.mjs").read_text(encoding="utf8")
assert "analyzeRelationV3" not in sdk
assert "analyzeListV3" in sdk
additions = transform((HERE / "templates/list-sdk-base.mjs").read_text(encoding="utf8"))
additions = additions.replace("@property {{exclusiveWriters: boolean}} scope", "@property {{exclusiveWriters: boolean, completeSnapshotTables: ReadonlyArray<string>}} scope\n * @property {Object} relationSchema")
write(HERE / "relation-sdk-additions.mjs", additions)
write(HERE / "payload/cmd/sdk.mjs", sdk + additions)
fixture = ROOT / "fixtures/relation-v3/reduction-source-closure.json"
expected = json.loads((ROOT / "fixtures/relation-v3/reduction-source-closure.expected.json").read_text(encoding="utf8"))
assert sha(fixture.read_bytes()) == expected["inputSha256"]
(HERE / "payload/examples").mkdir(parents=True, exist_ok=True)
shutil.copyfile(fixture, HERE / "payload/examples/relation-source-closure.json")

example = transform((HERE / "templates/list-example-base.mjs").read_text(encoding="utf8"))
example = (example.replace("relation-cycle.json", "relation-source-closure.json")
           .replace("['noise']", "['N']")
           .replace("transactions.length, 2", "transactions.length, 3")
           .replace("Bounded append-relation serializability", "Bounded relation-set serializability"))
example = example.replace("Synthetic append-relation example.", "Synthetic relation-set source-closure example.")
example = example.replace("append-relation-v3-sdk-example", "relation-set-v3-sdk-example")
write(HERE / "payload/examples/relation-roundtrip.mjs", example)

tests = transform((HERE / "templates/list-tests-base.mjs").read_text(encoding="utf8"))
tests = tests.replace("fixtures/relation-v3/manual.json", "fixtures/relation-v3/boundary.json")
tests = tests.replace("row.expected.analysis", "row.expected")
tests = tests.replace("const traceText = byId.get('two-key-read-append-cycle').traceText;", "const traceText = readFileSync(resolve(root, 'fixtures/relation-v3/reduction-source-closure.json'), 'utf8');")
tests = tests.replace("register-and-relation-captures-cannot-use-relation-entries", "register-and-list-captures-cannot-use-relation-entries")
tests = tests.replace("const relation = JSON.parse(load('fixtures/relation-v3/boundary.json')[0].traceText);", "const list = JSON.parse(load('fixtures/list-v3/manual.json')[0].traceText);")
tests = tests.replace("[register, relation]", "[register, list]")
tests = tests.replace("['unknown-item-source', 'disconnect-keeps-unknown', 'future-producer-does-not-repair-source']", "['unknown-read-version', 'unknown-commit', 'supplement-later-read-source-does-not-repair-gap', 'partial-query', 'snapshot-coverage-omitted']")
tests = tests.replace("['seven-committed-exceeds-capacity', '129-operations-exceeds-capacity']", "['seven-committed-capacity', 'aborted-ops-exact-capacity-129']")
tests = tests.replace("reduction-keeps-aborted-producer-source-and-remaps-ack", "reduction-keeps-required-producer-and-original-facts")
tests = tests.replace("['S', 'U']", "['P', 'A', 'B']")
tests = tests.replace("    const rollback = got.reducedCapture.events.find(event => event.kind === 'rollback_ok');\n    assert.equal(got.reducedCapture.events[rollback.commitResponse.request - 1].kind, 'commit_request');", "    for (let index = 0; index < got.retainedOriginalSeq.length; index++) {\n      const original = copy(source.events.find(event => event.seq === got.retainedOriginalSeq[index]));\n      original.seq = index + 1; assert.deepEqual(got.reducedCapture.events[index], original);\n    }")
tests = tests.replace("r.evidence.sourceEvidence[0].value = 'forged'", "r.evidence.sourceEvidence[0].values.t = 'forged'")
tests = tests.replace("got.originalTransactions, 3", "got.originalTransactions, 4")
tests = tests.replace("got.reducedTransactions, 2", "got.reducedTransactions, 3")
tests = tests.replace("relation-cycle.json", "relation-source-closure.json")
tests = tests.replace("return ['delete-' + tx.id, input, 'consistent'];", "return ['delete-' + tx.id, input, tx.id === 'P' ? 'inconclusive' : 'consistent'];")
tests = tests.replace("JSON.parse(p.stdout).analysis", "JSON.parse(p.stdout).status")
tests = tests.replace("independent-interpreter-rejects-cycle-and-each-single-delete-removes-violation", "independent-interpreter-confirms-source-closure-and-all-single-deletes")
tests = tests.replace("  receipt.passed = receipt.checks.every(item => item.passed);", (HERE / "extra-tests.mjs").read_text(encoding="utf8") + "\n  receipt.passed = receipt.checks.every(item => item.passed);")
write(HERE / "payload/scripts/relation-sdk-test.mjs", tests)
(HERE / "payload/docs").mkdir(parents=True, exist_ok=True)
shutil.copyfile(HERE / "relation-sdk.md", HERE / "payload/docs/relation-sdk.md")

runtime = HERE / "runtime"
runtime.mkdir(exist_ok=True)
for name in ("core.mjs", "capture-core.mjs", "evidence.mjs", "build-manifest.json"):
    shutil.copyfile(ROOT / "dist" / name, runtime / name)
shutil.copyfile(HERE / "payload/cmd/sdk.mjs", runtime / "sdk.mjs")
shutil.copyfile(ROOT / "dist/sdk.mjs", runtime / "generic-sdk.mjs")
example_root = HERE / "example-repository"
for name in ("dist", "examples"):
    (example_root / name).mkdir(parents=True, exist_ok=True)
for path in runtime.iterdir():
    if path.is_file(): shutil.copyfile(path, example_root / "dist" / path.name)
for path in (HERE / "payload/examples").iterdir():
    if path.is_file(): shutil.copyfile(path, example_root / "examples" / path.name)
paths = ["cmd/sdk.mjs", "cmd/evidence.mjs", "dist/build-manifest.json", "dist/core.mjs", "dist/capture-core.mjs", "dist/sdk.mjs", "dist/evidence.mjs", "fixtures/relation-v3/boundary.json", "fixtures/relation-v3/reduction-source-closure.json", "fixtures/relation-v3/reduction-source-closure.expected.json", "scripts/relation-v3-oracle.py"]
before = {name: {"bytes": len((ROOT / name).read_bytes()), "sha256": sha((ROOT / name).read_bytes())} for name in paths}
baseline = HERE / "baseline-inputs.json"
if baseline.exists(): assert json.loads(baseline.read_text(encoding="utf8")) == before
else: write(baseline, json.dumps(before, indent=2) + "\n")
print(json.dumps({"prepared": True, "payloadFiles": 5, "fixtureUnchanged": True, "runtime": json.loads((runtime / 'build-manifest.json').read_text())}))
