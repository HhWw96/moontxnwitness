# Register/list comparison with fixed Elle results

## v0.4.0 published runtime follow-up

The published v0.4.0 runtime at `0745b562` reproduced the original canonical
serializable comparison. There were 1,997 agreements, zero differences or
execution failures, and three ineligible upstream results. The run performed
2,000 classifications and 2,000 report verifications without adding inferred
order or running the Elle JVM again. The [v0.4.0 receipt](evidence/elle-common-v040.json)
binds the exact original input, frozen reference and observed runtime digests.

`node scripts/compare-fixed-elle-serializable.mjs ORIGINAL_JOB.json FROZEN_REFERENCE.json NEW_OUTPUT_DIR DIST_DIR`
reruns these checks using the original `fixed2000-job.original.json` and the
`preflight-upstream-bindings.json` reference derived from the original hosted
Elle artifact. Both file digests are checked before execution. Results and the
first example of each non-matching outcome are written to the new directory.

## v0.3.6 maintained comparison

The maintained v0.3.6 2,000-history comparison executed frozen classifier
`2c5245e` / core `c7c62b521af6068c…` and its verifier once per history,
using unchanged original observations. In the common
canonical `serializable` scope, all 1,997 eligible results agree with the fixed
Elle results: 1,000 register histories and 997 append-list histories. There are
zero boolean differences and zero current execution failures. Three upstream
unknown results remain separately classified, rather than counted as agreement.

The explicit `captured-list-original-serial/v1` route resolves all twelve list
histories that the earlier prefix-only run left unknown. It uses bounded
original-program interpretation and fresh certificate replay. On the previously
uncompared group of 858 histories, 855 now have matching comparable decisions;
the remaining three are the same upstream unknowns.

| Data model | Histories | Agreement | Upstream unknown | Difference / failure |
| --- | ---: | ---: | ---: | ---: |
| Register | 1,000 | 1,000 | 0 | 0 / 0 |
| Append list | 1,000 | 997 | 3 | 0 / 0 |

This run recomputes MoonTxnWitness results against the preserved results from
[Elle at the fixed commit](https://github.com/jepsen-io/elle/tree/4e359e597c52938b0afebb8bc42273914d68a424).
It does not rerun Elle or assert equivalence for the other thirteen model
definitions. The earlier comparison and its original inputs remain unchanged.

This is a completed maintained rerun, not a fresh independent acceptance or
a run against the final v0.4.0 core.

The [machine-readable receipt](evidence/elle-common-v036.json) records the tested
source/core identities, full input and per-item digests, counts and postflight
binding checks. See [the list policy](list-original-serial-v4.md) for its budgets
and source requirements, and use independently selected options when verifying.
