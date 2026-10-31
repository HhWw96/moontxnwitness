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

The first Linux setup run, [41193937285](https://github.com/HhWw96/moontxnwitness/actions/runs/41193937285), stopped before measurement because the input index reused an identical original-source licence member. The loader accepts that checksum-bound reuse while still reading the fixed public portable ZIP and checking each member's full digest and length. The next setup run, [41194367729](https://github.com/HhWw96/moontxnwitness/actions/runs/41194367729), built both candidate bridges and then exposed a missing generated-notices input. Preparation now builds notices from the selected compiler's original LICENSE and NOTICE, using the ordinary build's byte composition. The baseline ZIP, core, SDK, inputs, timing limits and output comparison remain unchanged. The ten original setup boundary checks remain, with six additional parser integration checks. Neither setup failure produced formal samples.

The third Linux setup run, [41195156954](https://github.com/HhWw96/moontxnwitness/actions/runs/41195156954), also produced zero formal samples. Both static-import regular expressions omitted multiline declarations, leaving model-profile.mjs unstaged. Preparation and protocol closure discovery now share parse-static-imports.mjs, using Node's SourceTextModule.dependencySpecifiers. VM modules are enabled only for these setup calls. The parser never links or evaluates an SDK; actual SDK checks still run in their original later preparation step. Known node: builtins are identified separately, while bare dependencies, root escapes and encoded/decorated path identities are refused. Dynamic import() and other lazy compatibility paths are explicitly outside the static closure and are not claimed as exercised. Tests cover multiline imports/reexports, Unicode, comments and string false positives, syntax rejection and this dynamic boundary.

A read-only audit of retained original public031 bytes found the complete static closure has 25 modules. All 18 declarations in the old Windows protocol retain exactly their original hashes and lengths; seven modules were omitted: classification.mjs, legacy-v024.mjs, legacy-v025.mjs, legacy-v025-runtime.mjs, legacy-v025-binding.mjs, model-profile.mjs and orm-profile.mjs. Every newly inventoried baseline module matches the unchanged PUBLIC031 declarations and independently pinned frozen index. The retained old Windows candidate similarly has 36 static modules rather than its 27 declarations; its additional omissions include v4.mjs and relation-v4.mjs. Its original 27 file bindings are unchanged. Current candidate source has 34 host modules plus the two actual bridges that Linux CI must build and parse afresh.

The old Windows protocol and its actual 16 preflight results and single-worker 30 samples remain historical records. The old complete-closure claim is corrected here; neither its preflight nor its samples authorize this new Linux baseline or a paired comparison. New protocol and runner hashes identify the corrected closure. Local parser checks used Node24.22.1, with 29 pure checks and all 16 setup unit checks passing; no SDK, MoonBit build, download or formal measurement was executed locally. The fresh Linux run remains pinned to Node24.13.0. Worker flags, heap768, the eight inputs, six report negative controls, 5 warmups, 30 samples per batch, three batches and complete output comparison have not changed.
