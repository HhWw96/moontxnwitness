# Full SDK paired performance on a Linux job

This workflow builds the actual candidate checkout with compiler
v0.10.16+b1a0e846e and compares its complete shared analyze /
analyzeWithOptions calls against original public031 bytes. It does not reuse
Windows c7 bytecode, Windows preflight results or the earlier incomplete
Windows baseline30 samples. It does not measure CLI renderer output or claim
that every SDK method has the same speed.

The fixed baseline portable archive must be from HhWw96/moontxnwitness v0.3.1,
83038095 bytes, SHA05ce492f51c75f99dc49a1d95658d0d128102913cab6c806956493f1b79b2597.
Its original core5b004a50... and SDK534b4c0a... are checked against PUBLIC031 and
the frozen source input index. Only the complete static SDK import closure,
build manifest and licenses are read from the ZIP; no historical runtime trees
are unpacked. The cache is rehashed even on a hit.

The candidate uses newly compiled Linux JS and capture bridges plus unchanged
host SDK source files. The artifact retains actual source commit, compiler and
binary digests, repository sourceFingerprint(root), and a separately named
trackedSourceClosureSha256 with its own path/NUL/content-SHA/LF contract.
It never labels Linux output as the Windows c7 hash.

All downloads, compiler info/check/build, source checks and16 functional
preflight workers finish before the formal step. The original8 histories/roles,
complete report validation (including49770 edges), original6 negative controls,
and strict root report.version normalization remain. Legacy cases use
analyze(historyObject); balanced cases use analyzeWithOptions(historyObject,{}),
matching the original options default. Text-renderer input has a distinct SDK
report scenario name.

Each measured worker is a fresh process for one version/scenario/batch. It uses
Node24.13.0 and --max-old-space-size=768 for both versions,5 warmups and30
samples,3 batches with AB/BA/AB. Actual Node binary, CPU/job metadata, heap limit,
raw timings, median/P95/maxRSS/cold metrics and full output bytes/digests are
retained. The old-space flag is not a total RSS cap. Results are for the recorded
GitHub-hosted job on its recorded CPU, without a dedicated physical-host claim.
No SQL, package build, download or upload runs concurrently in this job's timed
step. Cache saving and artifact compression happen afterwards.

The same1.3x/RSS0.8 goals and control threshold (10% or2ms, whichever is larger,
for median and P95) remain visible. Measurement completion and
performanceTargetsPassed are separate; a completed experiment is not proof
that a target was met. Failed attempts are retained and not automatically retried.
Each scene/version keeps one complete gzip from its successful preflight.
Formal samples store metrics/digests, not30 repeated large reports.

## Running

The first push containing only this workflow/runner payload registers and
triggers it through the path filter, including on a new benchmark branch. It
does not depend on a new file already being present on the default branch.
workflow_dispatch is also declared for subsequent registered runs. The
candidate_ref input selects a separate candidate checkout; empty uses the
benchmark ref. No benchmark file needs to be merged into a product branch just
to compare its source. A new explicit run-request nonce can bootstrap another
path-filtered push if dispatch is not available.

Preparation is disabled on local non-Linux/non-Actions hosts. No local download,
MoonBit build, full-SDK preflight or measurement was performed while preparing
this patch. Actual workflow execution and resulting artifacts remain pending.

The cache action is fixed to its [upstream commit](https://github.com/actions/cache/commit/5a3ec84eff668545956fd18022155c47e93e2684).
# Setup history

The first Linux setup run, [41193937285](https://github.com/HhWw96/moontxnwitness/actions/runs/41193937285), stopped before measurement because the input index reused an identical original-source licence member. The loader now accepts that checksum-bound reuse while still reading the fixed public portable ZIP and checking each member's full digest and length. The baseline ZIP, core, SDK, inputs, timing limits and output comparison remain unchanged. Eight setup boundary checks run before each subsequent CI preparation.
