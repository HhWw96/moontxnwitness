# Three isolated performance drafts

These are isolated functional drafts on the exact f33c8675 baseline, not transferred into the primary source tree. No benchmark, P95, RSS or database execution was run. A passing byte comparison proves the checked complete outputs and counters match; it does not establish a speed or memory improvement. Native code was checked by --target all but not executed.

Baseline source: f33c8675a69a0681bb7865e32f2ace5aed21b03fb2d03dc16265dee2dbe6d57b

| Slice | Core source / tests | JS | Source SHA256 | Core SHA256 |
|---|---|---:|---|---|
| 01-rt-writer | src/serialize.mbt, src/perf_rt_draft_wbtest.mbt | 402 | 0204f74e113166eab000aea713e0ab846c8495c98eb0b41c9d69fec82b3343ea | 7100042e1287fbefccae5fab7be278f6e8e03cbdd96218c029ff8cb8711f3a0e |
| 02-sparse-scratch | src/analyze.mbt, src/perf_sparse_draft_wbtest.mbt | 404 | 98a5a67f94d8cfc98db493e5aeeb6c52a03176fbc8552bfa2343255833511972 | ef1b97bee6afb4e218c4c41ebc7a151b21053c1509c66096333b00456c415a24 |
| 03-search-trail | src/search_optimized.mbt, src/perf_search_draft_wbtest.mbt | 403 | 5f52424517132af9c8dafa79e2b21caf72083821a40a87b44d0d33771cd6002f | 0c04c99f3c5dd998ce7a31113122a97e01a174b152764792f5b011cadd18af43 |
| combined | src/serialize.mbt, src/perf_rt_draft_wbtest.mbt, src/analyze.mbt, src/perf_sparse_draft_wbtest.mbt, src/search_optimized.mbt, src/perf_search_draft_wbtest.mbt | 413 | 6206dbbf4978c722883fe3e263c31dad2d32f41bb286db30d6e67d2e3bbf7edd | edf4ced84361481c7112a2922eba68120ca37dbccc18d99e9da08c763b7e57b9 |

Combined also passes 413 Wasm GC and 413 Wasm tests. All four drafts pass all-target deny-warn checks. The exact f33c baseline rebuilt to identical source/core/capture-core digests. Forty frozen full-output cases, including dense RT, sparse/reduction, cache saturation, exact budget edges, Unicode and 512-operation boundaries, compare across all four drafts: 160 comparisons, zero byte/value differences. The combined core additionally agrees with 10,320 independent serial replays and verifies 6,373 cycle certificates.

Review each receipts/01-rt-writer.patch, 02-sparse-scratch.patch, 03-search-trail.patch separately. The combined.patch is a convenience union. Transfer only reviewed src changes/tests after the parent's source freeze ends; never copy draft scripts or dist into the primary tree. Source and generated interfaces are separate. All byte comparisons use the same engine version and unchanged output scope; no fields/counters/evidence are ignored. Any later primary integration requires a new source binding and its own full acceptance.

The initial sparse scratch version reserved storage for every initial key. It passed initial functional checks, then was refined to allocate only for actually touched non-skipped operations to avoid the wide-initial/small-counterexample allocation. Its initial source/core and receipts remain retained. The only check failure was a deprecated unparenthesized MoonBit match-in-for syntax; it was fixed before semantic tests. No frozen oracle expectations or test thresholds were changed.

Final proof records: receipts/final-functional-manifest.json; receipts/lazy-key-refinement/functional-core-summary.json; complete-output-comparison.json; oracle.json. Initial records remain in receipts/ and initial-scratch-snapshot/. Compilation was isolated on D scratch with the fixed compiler from the primary toolchain, no formal timings or peak RSS samples.
