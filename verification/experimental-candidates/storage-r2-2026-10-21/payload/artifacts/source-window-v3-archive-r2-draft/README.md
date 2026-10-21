# Archive reader / original cold-segment prune — revision 2

**Static, unexecuted candidate.** This new ignored directory preserves original
`source-window-v3-archive-draft` index `b68bd42f…` and all its source/evidence bytes.
The old 32 results belong to old source: 30 passed and two Windows dangling-link
cases skipped. They are not revision-2 results.

Copied contract-v1 and the original 24-case plan retain their SHA. The amendment
is `contract-r2-amendment.json`. **33 new gap cases are written, none locally run.**
Local Python, subprocesses, databases, builds and filesystem tests remain paused
for this revision. Syntax and runtime behavior need independent execution.

Changes include strict checkpoint/pin/intent fields, checking the current manifest
every phase, retaining pre-existing guards even if a second marker IO fails, and
completedIntent recovery across terminal cleanup. Metadata IO shares the same
operation budget. Physical event counts are checked before raw decode. A competing
reader on the same instance cannot reset a mutating owner's dirty state.

Run only new cases with Python 3.12 and stdlib, once authorized:

```
python -B artifacts/source-window-v3-archive-r2-draft/test_gaps.py
```

Precreate an isolated temporary base and set `MTW_JOURNAL_SCRATCH`, `TEMP`, `TMP`
to it. The runner creates a new `archive-r2-gap-run-UUID`, preserves raw inputs and
failures, and writes `test-receipt.json`. It filters to `test_r2_…`; it does not
rerun the old 32. Two new cases start a Python child only to exit at preregistered
publication stages. No database, Node, MoonBit, Java or third-party package is used.

Preserve repository layout in independent checkout/bundle:

- This directory's four Python modules and three contract/plan JSON inputs.
- Frozen `artifacts/source-window-v3-draft/windows.py`, exact SHA enforced by code.
- `integrations/python/moontxnwitness_capture/{__init__,capture,journal_v3}.py`.

The package initializer imports capture.py, which defers optional psycopg until
connect; these tests never connect. `repository-dependencies.json` binds required
files. Check each SHA first. No installation script or external business code runs.

New cases add actual active/unread/unknown source refusal, versionSources and
read-window retention, ZIP rejection, cache substitutions rebound through raw
lifecycle checks, archive/manifest races, publication+marker IO faults, process
exits between replace/sync and after intent clear, plus scaled budget branches.
`gap-test-plan.json` freezes expected mapping before execution. Written expectations
are not passing receipts.

The original two Windows symlink skips remain unexecuted. ZIP symlink metadata
needs no host symlink privilege and cannot replace that gate. Small-file configured
cap injections are not maximum-size stress, OS hard quotas, performance evidence
or physical power-loss certification. Relation/list closure, archive deletion and
stable/default journal integration remain unsupported.
