# Separate batch evaluator: preparation slice

The independently frozen original dataset is preserved unchanged. This candidate
prepares its 2,000 records into 40 EDN batches of 50 using the exact accepted raw
adapter. It does not create expected validity labels, infer version order or add
initialization transactions. Every original input is accounted for.

All 2,000 requests were decoded by the previously independently authored EDN
reader and compared against its separate raw converter: full representations,
source references, identity renaming and list order/duplicates agree. Only the
six pure parser/converter definitions were loaded; its audit runner did not run.
This is a conversion test, not independent acceptance of the new batch harness.

The new Clojure wrapper retains the original serializable options and persists
each first result and raw EDN before starting the next. It has passed only a
delimiter/string/comment static scan. It has not been compiled or executed.
No expansion checker or MoonBit expansion run has occurred.

Before actual execution, finish and independently review the remote coordinator:
fresh process groups, maximum 50 requests per 300-second JVM, 10-second upstream
cycle searches, credential removal, complete missing-ID accounting, runtime and
dependency bindings, and separate raw-program/report evidence verification.
Timeout, unknown, range errors and mismatches must remain visible. Original
inputs and first results must never be replaced based on outcomes.

`prepare_batches.py --root REPOSITORY --output NEW_DIRECTORY` is opt-in. The
retained `check_prepared.py` uses its original two-level artifacts layout and the
retained prepared directory; restore that layout before re-executing it. This
archival bundle does not promise that relocating an audit changes its paths.

This experiment is not six-model parity, an accepted new mainline or a release.

Independent read-only review subsequently verified all 50 frozen files against
this archive and identified an execution blocker: `valid` currently becomes
`timeout` whenever cycle-search-timeout appears, even when Elle also returned
`:valid? false`. The fixed upstream tests contain this combination. The original
raw EDN preserves it, but a new wrapper must keep the original typed judgement
and timeout flag independently before any expanded execution. A missing result
must distinguish an actual process timeout, execution failure and an input never
invoked. The original R1 source remains unchanged; no checker execution or harness
acceptance is implied by this review.

The separate [result transport revision](../elle-result-transport-r3-2026-10-21/README.md)
now preserves both fields and retains returned raw EDN before summary generation.
Its pure/synthetic tests are distinct from actual expanded Elle execution.
