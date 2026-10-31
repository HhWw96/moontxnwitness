# Native JavaScript report transport

The 0.3.8 candidate enables a JS-only opaque-object return path for `analyze` and `analyzeWithOptions`. MoonBit still validates the same original history and options, runs the same analysis once, and retains all dependency fields, coverage, version orders, witnesses, search counters and caller budgets. The SDK feature-detects each explicit native export and uses its existing text path when that export is absent. Text APIs, capsule routes and other target implementations keep their original behavior.

The native edge constructor accepts only an opaque host report plus String, Bool and Int32 primitives. Presence flags distinguish null from an empty string or operation index 0. Each result and edge is fresh. Metadata still uses the original report encoder and JSON parser, including balanced extras; no general assumption that metadata is small is made.

## Recorded paired experiment

[Run 41200680274](https://github.com/HhWw96/moontxnwitness/actions/runs/41200680274) completed on a recorded hosted Linux job. Its fixed harness is `fbba24b470ce7b3775de41354302a006eb02eb7c`; the measured candidate is `988faceefdec4e7a97c6bcb3151255453bc1fa2a`. The candidate version string was 0.3.6. Actual public 0.3.1 SDK modules and the same compiler version form the baseline. See the [digest-bound evidence reference](native-report-performance.json).

| Metric | Independently recomputed result | Registered goal |
| --- | ---: | ---: |
| Five-target geometric-mean speedup |2.231533648006153|at least1.3|
| Five-target geometric-mean peak-RSS ratio |0.7778597015960469|at most0.8|
| Three control scenarios |passed|median and P95 within baseline+max(10%,2ms)|

The eight unchanged inputs include five targets: dense316 legacy, dense316 balanced, dense192 legacy report from text input, ring64 legacy and sparse256 balanced. The three controls are dense316 standalone, small balanced and serial32 transport. Each subject/scenario has three fresh workers, each with one cold call, five warmups and 30 samples: 90 raw timings per subject/scenario, 48 formal workers and 1,440 raw timings. Both subjects use Node 24.13.0 with `--max-old-space-size=768`; this old-space flag does not cap total RSS.

All 16 saved complete preflight reports were decompressed and compared after replacing only the root product version. Dense reports retain all 49,770 edges. All 48 formal-worker final returned-report hashes match those saved reports. Six original metadata negative controls passed. Whole-archive SHA, 262 member CRCs and original bytes, 234 candidate source files, complete 25/36 static module closures and every reported statistic were checked. Individual intermediate timed-call reports were not separately archived. The source and runtime digest bindings distinguish the dispatch harness from the measured candidate.

The result covers complete calls to the two stated SDK methods. v4 classification, configured-source collection, relational models, database execution and every other SDK method require their own evidence. Hosted hardware is recorded; a dedicated physical host is not asserted. Earlier unoptimized and RT-cache paired runs remain retained with unmet goals; their measurements are not merged with this run.

## Integrated candidate boundary

The 0.3.8 tree combines this transport with the later configured-source interfaces. Its new source fingerprint and compiled runtime are recorded by local integration checks and future CI. The above result remains attached to candidate988 and its actual Linux bytecode; it is not transferred to a different integrated runtime. Final publication, installation and integrated performance are separate recorded checks.

Local integration compiled all six current JS bridges and executed 1,853 JS unit tests, including the 12 JS-only DTO cases and the original 8 transport cases. The 39 native SDK, 73 v4, 117 configured-session, 38 atomic-row and 90 canonical-model checks passed against the integrated runtime. The current ordinary SDK static import closure has 44 modules and also imports successfully from an isolated directory without a build manifest. No WasmGC, Wasm, Native, database execution, complete portable archive or new formal measurement was executed in this local round. The per-target summary contract records actual Moon output: the 12 JS-only cases must not be attributed to non-JS targets; older receipts retain their single-field fallback.
