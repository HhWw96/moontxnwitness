# Relation predicate model analysis

`classify_relation_models_v4` analyzes original `relation-set-v1` histories under the independent `relation-predicate-models/v1` contract. It combines full relation-query observations, row-version provenance, scoped item/predicate dependencies, declared ordering contexts and bounded original-program replay. Existing point-row model profiles and their reports keep their original semantics.

The namespace accepts the fourteen canonical `ElleModelV4` selections. Its relation extension uses Adya item/predicate rules; it is not a claim that Elle's register or append-list checkers directly support relation predicates. Formal model names describe the supplied history, rather than a PostgreSQL product isolation level.

## Core API

```moonbit
let history = @witness.parse_history_v4(trace_text).unwrap()
let facts = @witness.model_facts_v4(history).unwrap()
let options = @witness.model_options_v4(
  models=@witness.elle_core_models_v4(),
).unwrap()
let analysis = @witness.classify_relation_models_v4(facts, options).unwrap()
let report = @witness.relation_model_classification_v4_json(analysis)
assert_true(@witness.verify_relation_models_v4(facts, report, options))
```

`facts` and `options` are supplied independently when verifying. Verification reruns normalization, source checks, graph searches and original-program completion; it does not accept the report's own budgets or conclusion as authority. Reports bind the original history and caller-declared logical clients with `sourceSha256`.

The input contract is the existing versioned relation trace: a complete initial snapshot, typed relation schema, original `row_read`/`row_write` observations and transaction lifecycle events. A query records its entire actual result, explicit `complete` flag and AND predicate. Writes record their unique version, action, predecessor and full row values. Supported values are int64, bool and text with the existing declared comparison rules. Insert, update, delete, empty results, point/range predicates, own reads, intermediate own writes and savepoint rollback use their original observations. NULL, joins, aggregate results and mixed data-model transactions remain outside this contract.

## Model rules

`W` contains WW dependencies. `I` contains WW and WR. `Ai` contains item RW; predicate RW is kept separate. `D` contains all three dependency types. Each search retains the complete source references of its witness.

| Model | Required dependency rule | Additional context |
| --- | --- | --- |
| `read-uncommitted` | no W cycle / G0 | data |
| `read-committed` | no I cycle / G1c; no G1a or G1b source | data |
| `repeatable-read` | RC rules; no D cycle containing an item RW / G2-item; own-effect consistency | data |
| `snapshot-isolation` | RC and own-effect rules; acyclic `I ∪ (I;A)`; original fixed-snapshot certificate | data |
| `serializable` | RC and own-effect rules; no D cycle / G2; original serial certificate | data |
| `strict-serializable` | serializable rules with real-time context | real-time |
| `consistent-view` | RC and own-effect rules; no G-single | data |
| `strong-session-read-uncommitted` | W cycle rule with session context | declared logical client |
| `strong-read-uncommitted` | W cycle rule with real-time context | real-time |
| `strong-session-read-committed` | RC rules with session context | declared logical client |
| `strong-read-committed` | RC rules with real-time context | real-time |
| `strong-session-serializable` | serializable rules with session context | declared logical client |
| `strong-session-snapshot-isolation` | snapshot-isolation rules with session context | declared logical client |
| `strong-snapshot-isolation` | snapshot-isolation rules with real-time context | real-time |

RR uses the explicitly selected literal Adya mixed-dependency rule: a forbidden cycle must contain at least one item RW edge and may also contain predicate RW edges. The report identifies this projection as `D-item-mixed`. A cycle made solely of predicate RW edges can refute serializability while remaining compatible with RR. This differs from the item-only anti-dependency interpretation discussed in the [Jepsen G2-item reference](https://jepsen.io/consistency/phenomena/g2-item); it does not alter the existing fixed-Elle model API. RC can observe changing external query results; it is not checked by forcing all statements through one transaction snapshot.

G1a proves that an actual delivered row names a foreign aborted or rolled-back source. G1b proves that it names a foreign intermediate source. Own-effect checking compares an actual complete result with the currently active own writes. Savepoint rollback restores the own-write overlay while preserving earlier delivered reads. A write predecessor is a write effect and is never invented as a SELECT observation.

Session contexts require the caller's complete logical client membership and nonoverlapping original boundaries. Connection-pool identity does not create a session. Real-time contexts use confirmed response-before-invocation relations in the supplied clock domain. A client BEGIN timestamp is not treated as a database snapshot.

The new relation namespace separately accepts `realtime_known=false` in the typed APIs, or `realtimeKnown: false` in its SDK/wire model options. The default is true and is explicitly recorded in `sourcePolicy`. False removes all real-time edges, marks real-time coverage incomplete and prevents real-time completion certificates. It preserves data dependencies and separately declared logical session facts, so a genuine data refutation remains refuted while an RT-only stale-read violation becomes unknown. Verification must independently supply the same policy. The mandatory `clockDomain` input syntax and all existing generic model parsers keep their original rules.

## Constructive completion

The report separates every graph/source rule from the original-program completion rule. A positive certificate supplies a commit order and replays the original full predicate queries, actual row versions/values, write predecessors, own overlay and savepoint controls.

Three independent completion modes are available internally:

* `original-serial`: every transaction executes at its position in the candidate serial order.
* `original-fixed-snapshot`: each transaction replays on one committed prefix plus its own writes. A committed key changed after that snapshot cannot enter its surviving write set.
* `original-committed-query-prefixes`: statements may use monotonically advancing committed prefixes plus active own effects. The earliest matching prefix is retained; a rollback does not erase already observed progress.

Write effects are also validated when installing each transaction in the candidate commit order. The selected session/real-time predecessor must precede that transaction's query/snapshot prefix. The resulting certificates are sufficient constructive compatibility evidence; they do not promote an inferred prefix into an original observation.

The exact completion scope is **6 committed transactions, 128 original actions, 100,000 states and 1,000,000 semantic checks**. Original actions include reads, writes and savepoint controls, including actions of aborted transactions retained in the source. State and semantic budgets can be reduced using the existing model options. Counters are reported separately for source inspection, each graph rule and each completion mode/context. Predicate graph capacity remains **128 transactions, 4,096 semantic read/write operations and 50,000 edges**; these graph limits do not enlarge exact enumeration.

`checked-compatible` means either all required rules and the model-specific constructive completion succeeded, or a concrete stronger serial certificate succeeded in the same ordering context. This stronger route can discharge an ambiguous predicate dependency graph by directly replaying all original complete queries.

`refuted` requires an actual forbidden source finding or scoped cycle, with its original sources. A reliable finding remains refuted even if another search is incomplete. `unknown` covers missing sources/contexts, unconfirmed outcomes, incomplete query delivery, unsupported input scope, exhausted budgets and unsuccessful completion. A failure to find a serial schedule is never used as an RC, RR or SI refutation. This release does not claim that its bounded positive search is complete for every weak-model history.

## Report and replay

The report format is `moontxnwitness-relation-model-composition/v4`, with:

* `semanticContract: relation-predicate-models/v1` and independently identified algorithm/counter contracts;
* original `observations`, source digest and independently supplied options;
* per-model `requiredGraph`, `orderContext`, `status` and per-rule findings/completion;
* predicate graph/source evidence, order completeness, executed limits and actual counts.

Completion IDs have the shape `completion/original-serial/data-only`, `completion/original-fixed-snapshot/realtime` or `completion/original-committed-query-prefixes/process`. Certificates include `commitOrder` and per-transaction `snapshotPrefix` or per-action `statementPrefixes`. A verifier reconstructs these from the original input instead of trusting a certificate in isolation.

The focused suite exercises all fourteen selections on a fully replayed history, predicate-only write skew, RC changing reads, aborted/intermediate producers, real-time stale reads, savepoints, source ambiguity, unknown commits, capacity/budget boundaries and source/report/budget tampering. The independent relation interpreter is a separate comparison implementation; production classification never calls it.

## SDK and CLI

```javascript
import {classifyRelationModelsV4, verifyRelationModelsV4,
  makeRelationModelsCapsuleV4, replayRelationModelsCapsuleV4} from './dist/sdk.mjs';
const options = {models: 'elle-core'};
const report = classifyRelationModelsV4(originalRelationHistory, options);
const verified = verifyRelationModelsV4(originalRelationHistory, report, options);
const capsule = makeRelationModelsCapsuleV4(originalRelationHistory, options);
const replay = replayRelationModelsCapsuleV4(capsule, options);
```

Omit `models` for the six basic model selections. `models: 'elle-core'` selects fourteen. Existing model options bind source, state and edge budgets and independently declared logical clients. Run `node examples/relation-models-v4-roundtrip.mjs` to distinguish predicate write skew under Serializable, RR and SI and replay its original evidence.

```text
node dist/moontxnwitness.mjs classify-relation-models-v4 source.json --models elle-core --output report.json --capsule case.json
node dist/moontxnwitness.mjs verify-relation-models-v4 source.json report.json --models elle-core
node dist/moontxnwitness.mjs replay-relation-models-v4 case.json --models elle-core
```

Use `--options` for independently selected client declarations and budgets. Capsule hashes bind complete source, options and report; replay reruns the model checks. Unknown source, model or budget fields and decoded duplicate JSON keys are rejected. The product version does not choose an algorithm or authorize embedded policy.

## References

* [Adya, Weak Consistency: A Generalized Theory and Optimistic Implementations for Distributed Transactions (2000)](https://pmg.csail.mit.edu/papers/adya-phd.pdf)
* [Fixed Elle reference](https://github.com/jepsen-io/elle/tree/4e359e597c52938b0afebb8bc42273914d68a424)
* [Elle consistency phenomena and model descriptions](https://jepsen.io/consistency)
* [PostgreSQL 18 transaction isolation](https://www.postgresql.org/docs/18/transaction-iso.html)
