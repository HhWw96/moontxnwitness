# Register/list comparison with fixed Elle results

The maintained 2,000-history comparison executes the current classifier and
verifier once per history, using unchanged original observations. In the common
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

The [machine-readable receipt](evidence/elle-common-v036.json) records the tested
source/core identities, full input and per-item digests, counts and postflight
binding checks. See [the list policy](list-original-serial-v4.md) for its budgets
and source requirements, and use independently selected options when verifying.
