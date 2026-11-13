# Functional scope and reference comparison

MoonTxnWitness is an embeddable MoonBit transaction-consistency analysis library. Its reusable layers are original-history validation, dependency inference, category search, model obligations, counterexample reduction and evidence verification. SQL/ORM collection is an optional input adapter. This page describes the maintained v4 namespaces; each referenced receipt identifies the source/runtime version actually checked. Historical public-package results do not establish publication or equivalence for a later source tree.

The reference is [Elle commit `4e359e5`](https://github.com/jepsen-io/elle/tree/4e359e597c52938b0afebb8bc42273914d68a424). A named interface, a passing example and a differential comparison are different evidence. Each table states which is available. Model compatibility always concerns supplied observations under the selected source profile and budgets.

## Architecture and functional comparison

| Layer | Fixed Elle design | MoonTxnWitness implementation and boundary | Reproduction / evidence |
| --- | --- | --- | --- |
| Embeddable core | History analyzers and checker functions, used without a Jepsen deployment | MoonBit library, JS SDK and CLI; JS, Wasm GC, Wasm and Linux Native builds | [Core consumer](../examples/core-v4), cross-target CI |
| Extensible inference | `core/combine`, graph explainers and `additional-graphs`; datatype-specific version inference | Registered deterministic MoonBit modules over one original index, explicit parameters/provenance/budgets, plus the public typed scoped graph; compiled module choices in SDK/CLI | [Registered modules](inference-modules-v4.md), [caller-module example](../examples/inference-modules-v4), [graph adapter](dependency-inference-v4.md) |
| Registers | WR from unique writes, WW/RW from justified partial version order and additional order assumptions | Unique version identities, source and predecessor checks, direct and inferred constraints stored separately; missing order can remain unknown | `classifyV4`, `inspectAnomaliesV4`, `classifyModelsV4`; [register comparison](evidence/elle-common-v041.json) |
| Append lists | Append identities and observed list order constrain dependencies | Effective append journals, delivered prefixes, multiple own appends, savepoint rollback and independent original-program replay | Explicit `effective-v1`, prefix-state and original-serial profiles; [list comparison scope](elle-common-comparison-v036.md) |
| Relations | The selected register/list reference checker does not provide our SQL predicate adapter | Atomic primary-key row profile; separate complete-query predicate graph with item/predicate scopes and membership transitions | [Row profile](relation-atomic-models-v4.md), [predicate categories](relation-predicate-categories-v4.md) |
| Categories | Tagged dependency-cycle searches plus source anomaly checks | Independent category searches and source inspectors; requested rule, order context and budgets bound into evidence | Category and source rows below; existing exhaustive/small-graph and oracle tests |
| Models | Forbidden anomalies, implication closure and additional order relations | Fourteen canonical definitions with explicit required rules, profile applicability and completion certificates | [Model obligations](model-obligations-v4.md), executable profile/model matrix |
| Explanation | Edge explainers, cycles and graph rendering | Original operations → versions → dependencies → witness; JSON/text/Markdown/DOT and point-window offline HTML | `verify*` recomputes using independent caller options |
| Reduction / replay | Anomaly explanations remain the reference-tool output | Category- and model-preserving relation reduction, source-closure rechecks, original-event mapping and conditional transaction one-minimality; source-bound capsules | [Model reduction](relation-models-reduction-v4.md), [v4 API](v4-api.md), [point-window flow](configured-session-v4.md) |

Graph provenance is not source authentication. A custom adapter can compose dependency categories immediately, but a new datatype must supply its validity and completion obligations before using full model compatibility. This is the distinction between the public graph extension API and the built-in original-history model adapters.

## Recommended entry points

| Input / operation | SDK | MoonBit | Independent verification |
| --- | --- | --- | --- |
| Existing register/list/atomic-row source profiles | `classifyModelsV4` | `classify_models_v4` | Original facts and separately selected `ModelOptionsV4` |
| Registered inference over original history | `classifyWithInferenceV4` | `classify_with_inference_v4` | Actual caller-registered code, module order/parameters/algorithm and independent budgets |
| Complete relation queries and predicate dependencies | `classifyRelationModelsV4` | `classify_relation_models_v4` | Original relation facts, selected model options and explicit real-time policy |
| Preserve one relation model refutation | `reduceRelationModelsV4` | `reduce_relation_models_v4` | Original facts, target model, source policy and candidate/model budgets |

The [registered-module example](../examples/inference-modules-v4), [relation model round trip](../examples/relation-models-v4-roundtrip.mjs) and [relation reduction round trip](../examples/relation-model-reduction-v4-roundtrip.mjs) exercise these boundaries. The older category, exact-interpreter and capsule APIs continue to use their original contracts. A model report is not interchangeable with a category report.

Registered modules receive the same original immutable view, not preceding modules' outputs. Additional constraints are searched only for obligations forbidden by the selected model; a stronger auxiliary absence graph cannot independently refute a weaker model. Base compatibility is retained only for constraints already entailed by validated original facts. Genuinely new constraints without a forbidden witness remain `unknown` until an appropriate independent completion proof exists.

## Data-model and anomaly matrix

`Direct` means a category/inspector produces its own source-bound result. `Composed` means a necessary rule is evaluated inside a selected model profile; it is not an additional standalone detector. `Separate` denotes an independent API and rule definition. Missing required facts or exhausted work produces `unknown`/`pending`, rather than an accepted model.

| Rule family | Point register | Append list | Atomic primary-key rows | General relation predicates |
| --- | --- | --- | --- | --- |
| G0, G1c, G2-item | Direct `classifyV4` | Direct; opt into effective graph for multiple appends | Direct `classifyRelationV4` | Separate scoped-category API |
| G-single | Direct explicit category | Direct explicit category with applicable list graph | Composed in model namespace | Separate G-single / G-single-item categories |
| G-nonadjacent | Composed, category-specific graph rule | Composed under selected source profile | Composed under atomic-row profile | Separate category; cyclic first/last adjacency checked |
| G1a / G1b | Original delivered reads vs aborted/intermediate writes | Source/prefix checks; producer and own-overlay applicability remains explicit | Original row source / projection checks | Composed from original complete-query sources in `relation-predicate-models/v1` |
| Internal consistency | Original program and own-write checks | Own append overlay and observed prefixes | Original row program / savepoint effect checks | Original complete queries, active own effects and savepoint rollback |
| Future read, lost update, dirty update | Source inspectors under their explicit premises | Applicable source diagnostics / model obligations; no blanket register-label parity | Row source and model obligations; no blanket register-label parity | Not claimed as complete named-detector coverage |
| Missing source / conflicting version facts | Explicit gap / order-conflict diagnostics | Explicit missing producer / incompatible-prefix diagnostics | Explicit missing writer / predecessor / row-value gaps | Incomplete result or ambiguous membership remains a gap |
| Item vs predicate anti-dependency | Item scope | Item scope | Item point profile | Both scopes retained; seven selected categories |
| Logical session / real-time | Explicit source facts and separate contexts | Same, subject to profile applicability | Same, subject to row projection | Separate model namespace with caller-declared clients and confirmed order facts |

Relations support typed int64, Boolean and explicitly compared text, primary-key/equality/range/AND predicates and distinct write effects. Full-query coverage is required for negative/predicate evidence. An UPDATE RETURNING result is not a complete predicate read. Atomic row-slot semantics do not assert equivalence to physical entity incarnations. Mixed-model transactions, NULL, JOIN, aggregates and arbitrary SQL functions are outside this stable scope.

## Canonical model matrix

All entries below are **conditional model checks** for captured registers, explicitly selected list prefix programs and explicitly selected atomic row programs. The default native list and relation interpretations have a narrower completion scope. General relation predicates now have the separate [relation-model namespace](relation-models-v4.md): six default selections and fourteen explicitly selectable definitions, original query/source checks and bounded constructive certificates. Its literal Adya mixed-item RR rule is declared separately from the existing fixed-Elle point/list projection. The original seven predicate-category APIs retain their semantics.

| Canonical model | Main graph projection | Additional order / premises |
| --- | --- | --- |
| `read-uncommitted` | W | Source rules and required literal coverage |
| `read-committed` | I | Source rules including forbidden G1; RC is not forced through snapshot INT |
| `repeatable-read` | I + item anti-dependency | Required item/source rules |
| `serializable` | D | Original-program serial completion where applicable |
| `strict-serializable` | D | Proven real-time order and applicable original-program completion |
| `snapshot-isolation` | Ext(I,A) | Checked prefix/completion premises; not a database product label |
| `consistent-view` | G-single | Required literal and source rules |
| `strong-session-read-uncommitted` | W | Declared complete logical-client context |
| `strong-read-uncommitted` | W | Proven real-time context and required order rules |
| `strong-session-read-committed` | I | Declared complete logical-client context |
| `strong-read-committed` | I | Proven real-time context and required order rules |
| `strong-session-serializable` | D | Declared logical-client context and applicable completion |
| `strong-session-snapshot-isolation` | Ext(I,A) | Declared logical-client context and checked completion |
| `strong-snapshot-isolation` | Ext(I,A) | Proven real-time context and checked completion |

W is the write-dependency projection; I includes write-read dependencies; D also includes anti-dependencies. These summaries are not the entire obligation list: each report enumerates the actual required source, graph, applicability and completion rules, including implication coverage. Missing necessary rules prevent compatibility; an independently valid forbidden witness remains a refutation when another check is unfinished. G0→G1c→G1 implication is separate from the most specific witness label.

**Fourteen definitions are available; complete cross-tool equivalence is not established.** Applicable positive histories, source-bound refutations and explicit unknown cases are implemented and tested per namespace. The fixed Elle register/list comparison and the independent relation reference each cover their stated inputs and rules. Neither turns the selectable definition count into a completeness theorem for arbitrary histories, new datatypes or database product isolation levels.

## Executable declaration and interoperability evidence

The [machine-readable declaration](feature-matrix-v4.json) enumerates profile IDs, required facts, categories, exact canonical model names and reference-comparison scope. Execute it after building:

```text
npm run build
npm run features:verify
# Or explicitly test an extracted distribution:
node scripts/feature-matrix-v4.mjs --runtime PATH_TO_DIST --output NEW_RESULT_DIRECTORY
```

The runner uses nine fixed original histories: compatible, WW-refuted and incomplete cases for each of three profiles. It checks **126 profile/model/case results**, every required rule on compatible cases, forbidden evidence on refutations, changed verdicts, independent budgets, unknown handling and capsule replay. The [public v0.4.1 matrix receipt](evidence/feature-matrix-v041.json) records 287 passing checks and binds the runner, declaration, fixtures and public runtime. A failed list/row projection can return its narrower source profile; this is allowed only for an expected unknown case and is recorded in each row. CI uploads both the per-row results and checksummed summary on Windows and Linux. These are interface/semantic regression checks, not fourteen-model Elle differential results.

The separate public-v0.4.1 [Elle comparison receipt](evidence/elle-common-v041.json) covers **2,000 original register/list histories for serializable**: 1,997 matched, zero differences, three upstream unknown cases not comparable, and zero execution failures. It recomputes and verifies MoonTxnWitness using the public package against retained results of the fixed Elle run. It does not reexecute Elle, compare all fourteen models, or include relations. List comparison uses `captured-list-original-serial/v1`; that evidence is not silently reassigned to every prefix-state model.

The maintained [actual fourteen-model comparison](elle-model-matrix.md) now runs fixed Elle with this checkout's SDK. Its [receipt](evidence/elle-model-matrix-v042.json) records 342 actual requests over discriminating register/list fixtures: 289 matched, 53 unknown, zero determinate differences, timeouts or checker failures, with all 84 required actual pairs matched. Missing-event and logical-client cases remain separately not-comparable. Cross-client stale reads distinguish session order from real-time order; aborted/intermediate reads, internal inconsistency, WW/WR and adjacent/nonadjacent anti-dependencies retain their own families. This reference run and the 2,000-history serializable corpus are distinct evidence sets. Predicate relations require an independent multiversion/predicate interpreter because the selected register/list checkers do not provide that oracle.

The [relation reference receipt](evidence/relation-models-v044.json) records 1,000 frozen histories and 14,000 model judgment positions: 10,800 determinate agreements, 800 conservative SDK unknowns, 1,800 reference-undecided positions and 600 positions undecided on both sides. Certificate replays and premise-only checks are separately recorded. Its reference supplies exact bounded serial decisions, direct aborted/intermediate-source findings and sufficient RC/SI certificates; nonserial RR/CV premise checks are not complete RR/CV parity. `fullFourteenModelParity` remains false, and that receipt does not claim public-package or formal performance verification.

## Full-output performance status

The current candidate shares the original source/order index between inference and base model analysis, and shares the full relation scoped graph before per-rule projection. It preserves original facts, source references, report fields, independent budgets and logical counters. Three formal batches retain 3,420 samples with complete report-byte equality and four passing P95 controls. Relation model calls measured 1.081× and model-preserving reduction 1.044×; the overall target-case ratio was 1.020× with essentially unchanged peak RSS. The larger speed/memory goals were not met. [The full-call report and raw samples](model-performance-v050.md) retain independent baselines, per-case P95, fresh-process memory, cold-start and output-size measurements.

Reference implementations: [core composition](https://github.com/jepsen-io/elle/blob/4e359e597c52938b0afebb8bc42273914d68a424/src/elle/core.clj), [transaction anomaly rules](https://github.com/jepsen-io/elle/blob/4e359e597c52938b0afebb8bc42273914d68a424/src/elle/txn.clj), [consistency model definitions](https://github.com/jepsen-io/elle/blob/4e359e597c52938b0afebb8bc42273914d68a424/src/elle/consistency_model.clj).
