# Independent abstract SI reference draft

The private Python reference implements `INT`, `EXT`, `PREFIX` and `NoConflict` directly over register operations. It imports no graph kernel and does not use dependency cycles as its decision rule. Both its contract and semantic input categories were hashed before `oracle.py` existed. The 52 concrete input/expectation pairs were frozen before the first oracle test.

The reference is an independent implementation relative to the production graph algorithm. Its author also wrote its self-tests. Another reviewer has not yet approved it, and it has not yet validated a production source adapter or any complete isolation classification. No database, MoonBit build or performance benchmark was run for this draft.

## Supported question

The input declares all transactions committed, unique version identities, explicit initialization and complete per-key orders of **final** committed writes. The oracle asks whether a finite abstract execution can realize these facts. It does not certify that a database or collector supplied truthful facts. A found arbitration order is an existential witness and is kept separate from the input's factual version orders.

Only a point-register model is accepted. Aborted/unknown outcomes, savepoint journals, missing sources or orders, list/relation/predicate models and over-capacity inputs return `inconclusive`. Ill-formed input returns `invalid`. Limits are six transactions, 128 original operations, 128 keys, 8 MiB JSON, depth 16 and 4,096 nodes. Unicode scalar identities allow NUL and supplementary characters within 256 UTF-16 units.

## Why the search is complete for this range

The oracle enumerates every total transaction arbitration order that extends the supplied final-write orders. A transaction can see any prefix strictly before itself, with initialization always visible. For one fixed arbitration order, each transaction's allowed cuts depend only on that order, fixed writes and its own operations. They do not depend on other transactions' selected cuts. The code therefore checks the cuts separately instead of building their Cartesian product.

For each candidate cut it checks that every earlier writer sharing a key is visible, constructs the snapshot, and replays the entire transaction. This implements `NoConflict`, `EXT` and operation-order consistency without a graph. A separate literal relation checker constructs `CO`/`VIS`, evaluates prefix closure and shared-writer visibility, and checks first external reads and subsequent same-key operations. It does not call the search helpers. The serial control requires the full earlier prefix (`TOTALVIS`).

This reasoning follows [Cerone and Gotsman's author-hosted paper](https://software.imdea.org/~gotsman/papers/si-podc16.pdf), Definitions 1–4 and Figure 1. The paper's session order is empty here. Its graph theorem is a future comparison target, not the oracle's implementation. Original Adya PL-SI, real-time order and inferred session order are outside this definition.

## Evidence and budgets

The first run passed 11 unittest methods, including the 52 frozen inputs under both SI and serial controls. It covers valid own intermediate reads, external intermediate-source refutation, nonrepeatable reads, fractured visibility, write skew, lost update, long fork, cross-key factual order cycles, identity/structure/capacity bounds, low budgets, witness tampering and identity/array-order metamorphisms. The log is retained in `first-selftest-output.txt`.

The single initial read is hand-counted at two states and five semantic visits. A budget one below either requirement returns `inconclusive` with no witness. All counters charge before the declared semantic visit. Input validation, permutation bookkeeping and report encoding are bounded but excluded, as explicitly specified in the frozen contract. Counters are not wall-time measurements.

`INT` and external-intermediate-source evidence have separate original transaction/operation locations. The latter is not automatically called G1b. A valid own intermediate read is not discarded or retrospectively invalidated merely because a later write overwrites it. Scope rollback is declined rather than flattened.

## Next gates

1. A second reviewer must audit the prefix-factorization argument, source completeness and exact counters.
2. Independently review the new frozen generated finite-history corpus and reference results below before using it for production comparison.
3. Independently derive the supported register graph/source ledger, then compare the full graph classifier against this abstract reference without changing frozen expectations to match production.
4. Design and review scoped, list and partial-order extensions separately. Do not broaden the current model ID silently.

All files remain in this ignored draft directory. Stable APIs and old failures are untouched.

## Frozen generated corpus and first evaluation

The fixed seed is `1397313861`. Nine quotas cover constructed SI/serial executions, known-source read mutations (including own future writes), internal inconsistency, lost updates, write-skew rings, external intermediate reads, unknown sources and zero budgets. All inputs retain complete factual final-write orders. Every third input has an explicit sidecar showing repeated business payloads with distinct state-version identities; the payload sidecar is not an extra accepted field of the register oracle input.

The first plan accidentally wrote a target of 1,100 while its nine quotas sum to 1,000. This was detected before any generated oracle result was observed. The original plan, generator output and failed consistency record are preserved. A separate amendment corrects only the arithmetic target to 1,000, matching the assigned minimum; no input, expected decision, seed or quota was replaced and no data was regenerated.

The frozen corpus has 1,000 different input hashes and 1,000 different identity-normalized program-shape hashes. The shape metric records producer positions and operation/key structure after removing literal identity renaming. It is not a claim of 1,000 nonisomorphic graphs. Generation took 1,001 attempts: one lacked an eligible requested own-future read mutation and was retried before evaluation; no input was selected or rejected using an oracle result.

The first complete run retained 2,000 SI/TOTALVIS decisions:

| Reference mode | Satisfiable | Unsatisfiable | Inconclusive |
|---|---:|---:|---:|
| SI | 551 | 349 | 100 |
| Serial (`TOTALVIS`) | 463 | 437 | 100 |

For each mode, the 100 inconclusive results are the 50 deliberately missing-source inputs and 50 deliberately exhausted zero-budget inputs. There were no unexpected invalid inputs, expectation mismatches or unreported budget unknowns. The separate literal relation checker accepted all 1,014 returned witnesses and all 600 stored construction witnesses. These are same-author reference checks, not an external review of the reference or the production model.

The corpus contains intermediate writes in 938 histories, own-future read sources in 65, repeated reads in 991 and repeated-payload sidecars in 334. Actual maximum generated dimensions are six transactions, 59 operations and seven keys; the earlier hand-written boundaries cover the 128-operation and 128-key limits. All statuses, source/semantic findings, budgets and original output records are saved in `generated-evaluation-v1.jsonl` and bound by `generated-evaluation-v1-receipt.json`.

No Elle process, database, production graph classifier or benchmark was run in this evaluation. Production comparison and independent peer review remain separate gates.
