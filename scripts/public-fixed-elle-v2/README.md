# Retained Elle campaign reference v2

This independent validation tool reconstructs a **new reference contract** from
the retained outputs of actual fixed Elle executions. It does not execute a
checker, import MoonTxnWitness, read SDK verdicts, modify the original corpus, or
replace the missing v1 reference.

`sdkResultsRead: false` describes this reference generator: it does not read SDK
judgments or derive expected results from them. It is **not a personnel-blinding
claim**. The old v0.4.1 aggregate counts were seen during file-location work;
those counts are not inputs to this generator.

The contract is `fixed-elle-serializable-original-capture-reference/v2`. It is
limited to the original `serializable` profile for point registers and append
lists. It makes no fourteen-model parity claim.

## Reproduce the audit

Python 3.11 or newer and the standard library are sufficient. Keep the original
archive, job, and fixed adapter sources; use a **new** destination directory.

```powershell
python test_audit_reference.py
python audit_reference.py `
  --job PATH/fixed2000-job.original.json `
  --artifact PATH/artifact-12578114941.original.zip `
  --source-root PATH/r4 `
  --previous-reference PATH/original-bb5/upstream-reference-v2.json `
  --output PATH/new-reference-v2
```

The source-root contains `elle_batch_r4.clj`, `r4_controller.py`,
`original-r3/{result_summary,transport}.clj`, `campaign-plan-final2.json`, and all
forty `plans-final2/batch-NNN.json` files. The exported `adapter` directory retains
these same source bytes and can be supplied as source-root for another audit.

The output contains the original unchanged 2,000-case job and JSONL, forty actual
EDN batches and control files, all actual raw results and summaries, registrations,
accounting and hash-linked completion ledgers, fixed source/option/license
evidence, runtime manifests, a deterministic reference and an evidence index.
JAR files are checked in-place from the nested original archive and are not
duplicated in the export. No SDK-containing member is opened. No archive member
is executed or extracted to a caller-controlled path.

`upstream-reference-v2.sha256` seals the new reference.
`audit-summary.json` records the tool hash and actual opened upstream members.
When `--previous-reference` is supplied, its exact original `bb5ac45a…` hash is
required. The new cases are first derived entirely from original captures and
actual upstream outputs, then compared byte-for-byte in canonical form with all
2,000 previous cases. The resulting `casesContentSha256` and equality proof bind
unchanged input identities, projections, typed judgments and eligibility. The
old reference is retained unchanged under `previous/`; it is not used to derive
new results. Resealing changes auditor/provenance metadata, not expected cases.
If an audit fails after creating the destination, it retains partial evidence and
`audit-failure.json`; a retry must use another directory.

## Input and execution binding

The auditor requires the exact SHA-256 hashes of the original JSON job, retained
106,794,428-byte artifact ZIP, nested runtime ZIP, fixed runtime manifest, fixed
Elle sources, adapter sources, campaign plan and each of the forty batch plans.
It verifies Java 21, Clojure 1.12.6, the Leiningen 2.11.2 standalone JAR, all 141
original dependency bindings and every classpath entry. Before/after runtime
manifests must retain every original file. The two documented dom-top generated
classes are recorded as generated files, not checker rule modifications.

Each request is independently reconstructed from the original capture and
compared in full to the actual retained EDN. This includes transaction programs,
invoke read placeholders, actual completion read sources, write/append identities,
transaction outcomes, logical checker processes, dense checker indexes, original
event mappings, and initial-state renaming. The verified actual adapter only runs
`serializable`, with no additional graphs and with linearizable/sequential/WFR
key assumptions disabled. The data-only parser cannot execute EDN tags or code.
Its map-key subset is explicitly limited to keywords and strings; unsupported
boolean/integer map keys fail closed instead of colliding in Python dictionaries.
JSON rejects floating-point overflow and nonfinite values at every nesting level
while retaining finite numbers. Duplicate ZIP central-directory names are rejected.

All 2,000 results must have actual invocation-intent, returned and completed
phases in order, a valid ledger hash chain, a successful complete process,
matching raw/summary byte bindings, and a summary that agrees with the typed
raw `:valid?` and `:anomaly-types`. The typed boolean is eligible for comparison
only when the original checker did not report a cycle-search timeout. An
upstream unknown remains unknown and is not converted to a boolean.

## Shared facts and comparison boundaries

- Every register key has at most one writer in this corpus and its declared
  predecessor is the initial version. No noninitial write/write order is
  discarded. Initial versions map to Elle's `nil` and other versions retain their
  original identities. Missing/wrong-key sources are rejected.
- Lists start empty. Actual append identities and read order are preserved.
  Business values are checked against their original unique producer identity
  before being projected to Elle identities; equal business values do not merge
  distinct append operations. Repeated identities in an observed read are
  preserved as anomaly input and counted explicitly; they are not confused
  with duplicate producer declarations or silently removed.
- Only confirmed `commit_ok` observations form successful completions.
  `commit_request` alone never implies success. The mapping preserves original
  begin/completion order, but timestamps, physical connections and clock labels
  do not add session or real-time edges for `serializable`.
- The original corpus has no explicit version-order or logical-client fields.
  The auditor rejects new/unmapped root or event fields, nonempty initial lists,
  multiple register writes per key, unsupported outcomes and coverage gaps.
  These cases cannot silently inherit comparison eligibility.
- The new reference contains only upstream judgments. A future SDK comparison
  must independently bind the exact SDK bytes and input hashes and preserve
  differences, unknowns, execution errors and unsupported cases separately.

## Provenance and availability

Original execution: GitHub Actions run `40139252465`, attempt 1, job
`121007283470`, artifact `12578114941`, source commit
`be08ec7d639acbcdd8120e752758eb3c539f45e7`. Fixed Elle:
`4e359e597c52938b0afebb8bc42273914d68a424`. The original artifact's present
public availability is not asserted by this offline audit. Public reproduction
requires preserving the original archive plus this derived evidence as
downloadable attachments; the manifest explicitly records that publication is
still needed.

The expected old v1 normalized reference SHA-256
`cd03c00a5c14c8ede612fdc1e15c40d35e0229c980ba2d08c651a15b7f2dc860`
was unavailable in the searched project archives. The v2 reference always records
`v1ReferenceMissing: true` and `upstreamElleReexecuted: false`. Its new hash is
not an attempted reconstruction of that missing file. Existing v1 code and
expectations remain unchanged.

The fixed upstream Elle LICENSE is included with the copied source excerpt.
Adapter sources retain their original notices. The evidence bundle is separate
from the production package and introduces no new runtime dependency.
