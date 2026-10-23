# Structured v3 candidate: second formal run and withdrawal

**Overall performance acceptance failed. Default optimization withdrawn.** These are unpublished candidate measurements, not stable v0.2.1 speed claims.

The dedicated counter replaced the generic integer-array counter after a bounded V8 diagnostic. The source build was 69b9113246b48c2a5e142063f724446bee9cedf9aa430531db31763a1c6493a5. Inputs, complete outputs, 5 warmups, 30 samples, 3 independent batches, and the 10% or 2 ms P95 policy were unchanged.

| Group | Median speedup geometric mean | Peak RSS ratio | Failed batch comparisons |
|---|---:|---:|---:|
| full-v3 | 1.855x | 0.865 | 0 |
| normalization | 1.223x | 0.985 | 2 |
| reduction-v3 | 2.652x | 0.966 | 0 |
| control | 1.000x | 0.994 | 6 |

All 123 complete-output comparisons agreed. Full analysis and reduction passed their P95 checks, but normalization and legacy-control failures keep the overall result false. The legacy analysis functions were unchanged; their failure mechanism has not been established, so environment noise is not asserted as the cause.

| Batch | Workload | Phase | Baseline P95/ms | Candidate P95/ms |
|---:|---|---|---:|---:|
| 1 | relation-source-cycle | normalize | 5.312 | 7.495 |
| 1 | legacy-dense-rt-316 | legacy | 117.229 | 134.521 |
| 1 | legacy-sparse-512 | legacy | 10.625 | 15.861 |
| 1 | legacy-reduction-512 | legacy-reduce | 11.165 | 13.512 |
| 2 | legacy-completion-impossible-11 | legacy | 4.614 | 7.158 |
| 2 | legacy-completion-impossible-12 | legacy | 7.668 | 12.274 |
| 3 | list-chain | normalize | 58.282 | 64.794 |
| 3 | legacy-completion-impossible-9 | legacy | 2.578 | 5.891 |

[Original second-run receipt and raw samples](../verification/performance-v020/run-2026-10-23T04-20-10-798Z-c96838bf/receipt.json). The [first run](performance-v0.2.1-first.md) is retained unchanged.

The [complete candidate archive](../verification/experimental-candidates/v021-structured-withdrawn/manifest.json) binds source, runtime and all 657 candidate core tests. The stable default restores the public20 paths and does not enable this candidate. Further optimization moves to a later bounded iteration.
