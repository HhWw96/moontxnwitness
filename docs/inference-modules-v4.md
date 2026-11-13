# Registered inference modules

The MoonBit API composes deterministic local inference functions over one validated original-history index. Modules retain their own identity, semantic contract, parameters, original edge identities, references and measured work. A module output never becomes an instruction to mark a model complete.

```moonbit
let history = @txn.parse_history_v4(source_text).unwrap()
let facts = @txn.model_facts_v4(history).unwrap()
let options = @txn.model_options_v4(
  models=[@txn.ElleSerializable],
).unwrap()
let modules = [
  @txn.builtin_inference_module_v4(@txn.InferenceReadSources),
  @txn.builtin_inference_module_v4(@txn.InferenceGivenVersions),
]
let result = @txn.classify_with_inference_v4(
  facts, modules, options=options,
).unwrap()
let report = @txn.inference_classification_v4_json(result)
let verified = @txn.verify_with_inference_v4(
  facts, report, modules, options=options,
)
```

`infer_dependencies_v4` returns the graph-and-execution record through `inference_v4_json`. `classify_with_inference_v4` returns `InferenceClassificationV4`, rendered with `inference_classification_v4_json`. Both take caller-created `ModelFactsV4`, an ordered array of registered modules, independently chosen `ModelOptionsV4`, and optional `max_inference_checks`.

## Module contract

Create a descriptor with `inference_module_v4(id, semantic_contract, callback, parameters~, algorithm~)`. The optional algorithm identity defaults to the semantic-contract identity for an initial implementation; callers can bind a distinct implementation revision without changing that semantic contract. Its callback receives an opaque `InferenceViewV4`, a detached parameter JSON value, and `InferenceBudgetV4`. It returns `Result[InferenceContributionV4, String]` containing only `data_edges`, `order_edges` and `gaps`.

The view offers detached `history_json`, `nodes`, `data_edges` and `order_edges` accessors and the original `data_model`. Every callback sees the same original index. Newly emitted constraints are merged after each callback; they are never fed into another callback as observed facts. Exact replays of an already indexed edge retain their original graph entry and module-emission identity, avoiding another physical graph copy. Distinct provenance and parallel constraints remain separate.

Registered code is caller-trusted local MoonBit code. It must be deterministic and inspect only its supplied view and bound parameters. Verification reruns the caller's actual registered implementations; a supplied report cannot register code or choose an implementation. Semantic IDs describe the expected code contract rather than authenticate arbitrary callback code.

The core snapshots the selected module array before invoking local code. Mutating a caller-owned registry during a callback cannot remove, reorder or replace modules for that invocation. Verification binds the algorithm revision as well as the semantic identity and parameters, and recomputes output rather than trusting labels alone.

Contributions are ordering constraints over the original transaction nodes. They do not introduce new read/write observations, rewrite source validity, or define a new datatype. A custom module remains responsible for sound inference and the correct item/predicate interpretation. Category witnesses from custom constraints are explicitly conditional on that trusted contract.

The initial built-ins are:

| Choice | Identity | Source scope |
| --- | --- | --- |
| `InferenceReadSources` | `original-read-sources/v1` | WR relations already established by original source checking |
| `InferenceGivenVersions` | `original-version-constraints/v1` | WW/RW relations established from the selected validated adapter |
| `InferenceListPrefixes` | `observed-list-prefixes/v1` | Existing observed/effective list graph; requires append-list input |
| `InferenceDeclaredOrders` | `declared-transaction-orders/v1` | Explicit logical-client and real-time relations established from original facts |

List and atomic-row completion still require the caller's explicit `ModelListPrefixStates` or `ModelRelationAtomicRows` source options. Choosing a module does not silently enable either policy. Logical clients come from `model_facts_v4`; physical connection reuse supplies no client membership. No per-key linearizability, sequential-consistency or writes-follow-reads assumption is enabled by these built-ins.

## Model results and source assurance

The result retains the unchanged `classify_models_v4` report as `baseClassification`. Registered module constraints are searched independently for forbidden projection cycles. A reliable base refutation survives a module error, missing evidence or exhausted work. Additional forbidden witnesses are conditional on the caller-trusted module implementations and their declared premises.

Only graph obligations forbidden by the selected model can supply these witnesses. Stronger auxiliary graphs used by base completion or absence arguments are not promoted to standalone refutations. In particular, an adjacent two-antidependency cycle can refute repeatable-read or serializable without being relabelled as an SI or consistent-view violation.

Base compatibility survives only when every module finishes without gaps and every emitted relation is already entailed by the independently validated base graph. A genuinely new constraint can invalidate the base positive certificate even when it creates no cycle. This implementation therefore reports `unknown` for that positive case until a separate additional-constraint completion certificate is implemented. Module flags cannot make the graph or a model complete; `InferenceContributionV4` has no completeness or verdict field.

This contract is identified by `registered-inference-and-model-refutations/v1`, independently of product version. Existing `classify_models_v4`, source profiles, default options and model capsules retain their existing meaning. This module API does not claim arbitrary new-datatype model completion or database-observer authentication.

## Limits and verification

- At most 16 modules; identities must be distinct nonempty scalar strings of at most 256 UTF-16 units. Parameters are detached and bounded to 8,192 UTF-8 bytes.
- `max_inference_checks` defaults to 1,000,000 and accepts 0..1,000,000. The shared counter charges module invocation, cooperating callback work and each returned constraint. Exactly using the limit is legal; attempting more work marks exhaustion.
- Metering controls kernel output work and cooperating trusted callbacks. It is not a wall-clock or memory sandbox for arbitrary registered code.
- Module graph input retains the existing 128-node, 50,000-edge boundary. Output identities are validated before fixed-length module namespacing. Original IDs and all retained provenance remain in the execution record.
- Invalid or over-budget output is atomic: none of that module's candidate constraints are installed. Missing edge references remain gaps and cannot form witnesses.
- Source, graph and model budgets remain independent. Actual source/order counts and per-module counts are recorded separately.
- `verify_with_inference_v4` requires the caller's facts, module implementations/order/parameters, source options and inference budget, then reproduces the complete record. Changing a verdict, policy, module selection, semantic ID or budget cannot authorize verification.

The maintained tests cover three source data models, composition and removal, changed order/parameters, detached source containers, conditional refutations, unproved positive completions, exact/zero budgets, module errors, missing provenance, duplicate identities and atomic invalid output. JS, Wasm GC and Wasm runs are independent from Linux Native and public-package installation validation.

## Compiled-module JSON boundary

`infer_dependencies_v4_json(source, options)` and `classify_with_inference_v4_json(source, options)` expose the compiled built-ins. `verify_inference_v4_json` and `verify_with_inference_v4_json` take original source text, supplied report text and independently supplied expected options.

```json
{
  "modules": ["original-read-sources/v1", "original-version-constraints/v1"],
  "modelOptions": {"models": ["serializable"]},
  "maxInferenceChecks": 1000000
}
```

`modules` is required and may be an empty array. It accepts only the four compiled identities above. The envelope permits exactly `modules`, `modelOptions` and `maxInferenceChecks`; nested model options use the existing canonical model parser, including independent client declarations and source/graph budgets. Decoded duplicate keys, duplicate/unknown modules, code objects, unknown options and out-of-range budgets fail.

The complete options envelope is bounded to 16 KiB, the original history to 8 MiB and the supplied combined report to 64 MiB. `inference_options_v4_content_json` provides canonical options for transport, and `inference_report_v4_content_json` validates the report's transport identity. The latter does not establish semantic validity: use the verification functions to recompute original source and caller policy. Portable callers do not receive an automatic dynamic module registry.

## JavaScript and CLI

```javascript
import {classifyWithInferenceV4, verifyWithInferenceV4,
  makeInferenceCapsuleV4, replayInferenceCapsuleV4} from './dist/sdk.mjs';
const options = {
  modules: ['original-read-sources/v1', 'original-version-constraints/v1'],
  modelOptions: {models: ['serializable']},
  maxInferenceChecks: 1000000
};
const report = classifyWithInferenceV4(originalHistory, options);
const verified = verifyWithInferenceV4(originalHistory, report, options);
const capsule = makeInferenceCapsuleV4(originalHistory, options);
const replay = replayInferenceCapsuleV4(capsule, options);
```

Use `inferDependenciesV4` and `verifyInferenceV4` for the separately bound module-execution record. `parseInferenceOptionsV4` validates duplicate keys and produces a detached canonical policy. SDK and CLI select only compiled built-ins; custom callbacks are registered by a MoonBit program.

```text
node dist/moontxnwitness.mjs infer-dependencies-v4 source.json --options modules.json --output graph.json
node dist/moontxnwitness.mjs classify-with-inference-v4 source.json --options modules.json --output report.json --capsule case.json
node dist/moontxnwitness.mjs verify-with-inference-v4 source.json report.json --options modules.json
node dist/moontxnwitness.mjs replay-inference-v4 case.json --options modules.json
```

Verification and replay require an independently selected options file. The capsule binds exact source, normalized options and complete report bytes with SHA-256; changed modules, budgets, evidence or recomputed digests do not bypass semantic reanalysis. Its envelope uses canonical compact JSON to reject duplicate decoded fields; preserve the emitted bytes rather than reformatting the capsule. Producer version is descriptive metadata, while semantic, algorithm and counter identities select the supported behavior. Existing model capsules use their original format and verifier.
