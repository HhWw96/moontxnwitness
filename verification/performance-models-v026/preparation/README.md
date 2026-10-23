# Six-model complete SDK cost preparation

This directory contains a new absolute-cost protocol. It does not contain a performance result, an accepted final runtime, or a comparison with v0.2.5. No product source, existing controls, or their expectations were changed.

Six fixed cases cover G0, source-closed noisy G2, list write skew, explicitly bound synthetic strict intervals, absent strict intervals, and an independently generated 128-transaction/256-operation register chain. Five cases preserve the repository input bytes; the last case preserves an independently generated complete version chain, not a new database capture. All cases request all six model definitions with unchanged default per-rule budgets.

Each case runs in three separate child processes. Each child imports the full SDK, records cold import and the first complete call separately, performs five warmups and thirty recorded calls. There are 18 sequential workers and 540 measured samples. Batch order rotates by two cases. No GC is forced. A sample ends when the complete SDK report object returns, including internal normalization/classification and exact verification. The caller's final JSON encoding, gzip and archive writing are outside that timer. SDK import is a cold process/module import; this is not a claim about cold operating-system file caches.

`process.resourceUsage().maxRSS` is captured before caller final output encoding/gzip/archival. It is the process high-water across cold load, first call, warmups and measured calls, not the allocation or RSS of an individual call. Node documents this value in KiB: https://nodejs.org/download/release/v24.13.0/docs/api/process.html#processresourceusage . Per-batch high-water values and their median/P95/max are reported. With three processes, the RSS P95 equals their maximum and is labelled accordingly. All 90 latency observations for each case are pooled for its median/P95; all per-batch samples and statistics are retained. No across-case geometric mean or speedup is invented.

Only each worker's LAST full report is archived, as a gzip plus exact uncompressed/gzip byte counts and SHA256. This retains 18 full outputs, not 540 output copies. Every timing sample is retained. Outputs from the three batches must be exactly equal; no version/header/business-value normalization is allowed. The controller rehashes all runtime/tool bytes outside each measured child, and validates every archived output. It retains each child's stdout/stderr and any failure; it does not rerun a failed implementation until it passes.

Preparation (Root only after final integrated candidate freeze):

    node tools/freeze.mjs FINAL_DIST EXACT_RAW_BUILD_MANIFEST_SHA NEW_FROZEN_BUNDLE

This step only copies and binds the actual complete SDK runtime; it never imports that SDK. The manifest's core/capture hashes must match actual bytes. Root should review the resulting plan SHA and ensure no compiler, database, packaging, download/unpack or unrelated activity remains on the machine.

Formal execution (Root only during the approved exclusive window):

    node NEW_FROZEN_BUNDLE/tools/run.mjs --execute-root-approved-exclusive NEW_FROZEN_BUNDLE/plan.json EXACT_REVIEWED_PLAN_SHA NEW_RESULTS

No formal run has been executed by this preparer. A worker has a 300-second bound, full output an explicit 32MiB archival cap and the invocation requires at least 1GiB free. A timeout or cap rejection is an incomplete measurement, not a silently shortened sample set. Existing SDK budgets are not raised. Pure helper tests do not import any SDK or run workers.

Storage peak DESIGN estimate: six small frozen inputs (~91KiB), full runtime capped at 128MiB, eighteen retained gzip outputs each bounded by a 32MiB uncompressed report (roughly 577MiB worst case plus gzip framing), timing/log JSON capped child output at 1MiB per worker. The default 1GiB free-space guard exceeds the planned retained archive+runtime bound with margin; this is an estimate, not observed usage. The root reviews actual runtime byte count before starting. This protocol does not retain a raw duplicate of each full report on disk.

Performance targets, existing control regressions, actual database results, genuine public-package installation and competition review remain separate. These new six-model checks do more work than the old category-only API, so no old-v25 speedup is calculated. Results must name the final candidate and exact source/runtime hashes; later build changes require a new explicit freeze and measurement.
