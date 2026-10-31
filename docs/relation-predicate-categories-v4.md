# Relation predicate category analysis

The MoonBit library connects complete relation query observations to separately scoped item and predicate dependencies. It checks G0, G1c, G2-item, G2, G-single-item, G-single and G-nonadjacent using the selected formal rule definition, retaining original query and row-version provenance.

```moonbit
let history = @txn.parse_history_v4(source_text).unwrap()
let result = @txn.classify_relation_predicate_v4(
  history,
  @txn.ScopedG2,
  rule_set=@txn.Adya2000Mixed,
).unwrap()
let evidence = @txn.relation_predicate_classification_v4_json(result)
let valid = @txn.verify_relation_predicate_classification_v4(
  history,
  evidence,
  @txn.ScopedG2,
  rule_set=@txn.Adya2000Mixed,
)
```

Run the direct library example without restoring historical runtime payloads:

```text
node scripts/moon.mjs run --target js src/predicate_demo
```

Two transactions each observe the complete empty matching set and insert a different matching row. The example verifies a predicate G2 witness while the item G2 check completes without a witness. Empty results remain actual query observations; candidate source constraints do not become invented negative-version reads.

`Adya2000Mixed` and `ElleFixed4e359e5` are explicit choices because their scoped category definitions differ. The result concerns one selected dependency category. It keeps the existing point-classification and global-shortest-cycle meanings intact. Formal isolation-model composition is a separate API.

The adapter uses persistent typed primary-key slots, original write-effect journals and complete predicate membership changes. The initial supported values are int64, Boolean and explicitly ordered text with primary-key, equality/range and AND predicates. Complete-query coverage, source closure and version-order evidence remain part of the result. Physical entity-incarnation equivalence across deletion and reinsertion is not inferred.

Construction, predicate evaluations, candidate visits and category search have separate recorded budgets. An unfinished search returns `unknown`; a valid discovered witness remains a refutation. Verification recomputes from the original source and the caller's selected category, rule definition and budgets. Hashes bind supplied observations, rather than authenticate a database observer.

The report transport also reuses the encoded complete report instead of building a second report object tree. JSON, text, Markdown and DOT presentations retain their original bytes and standard JSON escaping. New timing and memory claims require measurements of the final integrated build.

The SDK exposes the same explicit selectors:

```js
import {classifyRelationPredicateV4, makeRelationPredicateClassificationCapsuleV4,
  replayRelationCapsuleV4} from './dist/sdk.mjs';
const options = {category: 'G2', ruleSet: 'adya-2000-scoped-categories-v1'};
const report = classifyRelationPredicateV4(sourceText, options);
const capsule = makeRelationPredicateClassificationCapsuleV4(sourceText, options);
const replay = replayRelationCapsuleV4(capsule, options);
```

```text
node examples/relation-predicate-categories.mjs
node dist/moontxnwitness.mjs classify-relation-predicate-v4 examples/relation-predicate-categories.json --options options.json --output report.json --capsule evidence.json
node dist/moontxnwitness.mjs verify-relation-predicate-v4 examples/relation-predicate-categories.json report.json --options options.json
node dist/moontxnwitness.mjs replay-relation-v4 evidence.json --options options.json
```

Save the following as `options.json` for the commands above:

```json
{"category":"G2","ruleSet":"adya-2000-scoped-categories-v1"}
```

Both `category` and `ruleSet` are mandatory. Optional limits are `maxGraphChecks`, `maxPredicateChecks`, `maxCandidateVisits`, `maxStates` and `maxEdgeChecks`. Verification and capsule replay require independently supplied expected options. The CLI returns 1 for a refutation, 0 for a completed compatible check, 3 for an unfinished check and 2 for invalid input or failed verification.

Multiple unobserved versions that exclude a row are retained as candidate constraints. When every candidate induces the same predicate dependencies, the graph check can complete without selecting a fictitious negative read version. Candidates separated by a membership change remain ambiguous. The predicate graph algorithm identifies this behavior as `relation-predicate-must-edges-3`.
