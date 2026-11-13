# Extending dependency inference

MoonTxnWitness separates **observation interpretation**, **dependency construction**, **category search** and **model obligations**. For inference over an existing validated history, use [registered modules](inference-modules-v4.md) and `classify_with_inference_v4`: the core shares one original immutable view and binds each module's policy and output. The lower-level public graph API described here also lets an adapter interpret caller-owned in-memory types and compose inferencers without converting observations to the built-in capture JSON format.

Run the complete example:

```text
moon run --target wasm-gc src/inference_demo
```

The example's `Observation` type is caller-owned. `infer_read_sources` derives WR from matching unique versions. `infer_predecessors` derives WW and RW from explicit predecessor facts. Their tagged edges and original observation references are combined into `scoped_dependency_graph_v4`, searched using `search_scoped_category_v4`, then independently checked with `verify_scoped_category_v4`. It also verifies that a zero search budget returns `unknown`.

The same source has also run from a new directory with only the public `HhWw96/moontxnwitness@0.4.1` Mooncakes dependency, producing a verified G2-item witness with Wasm GC. The [consumer receipt](evidence/inference-consumer-v041.json) binds the sample, dependency configuration and output; this does not claim database collection.

## Adapter contract

| Layer | Extension input / responsibility | Core responsibility |
| --- | --- | --- |
| Raw observations | Interpret a new datatype; preserve original operation identities, actual observations and transaction outcomes | Built-in captures revalidate their own source rules; the declared-graph interface does not authenticate a collector |
| Version inference | Derive only justified partial order and read-source relationships; retain inference premise and source references | Keep inferred constraints separate from original facts; built-in register/list adapters retain their own source checks |
| Data dependencies | Supply distinct `ScopedDataEdgeInputV4` identities, endpoints, WW/WR/RW and item/predicate scope, with nonempty `sources` | Validate graph structure, detach source JSON, bind its digest, retain parallel edges and provenance |
| Additional order | Supply `ScopedOrderEdgeInputV4` with explicit logical process or observed real-time references | Validate endpoints and references; quarantine inconsistent order components; keep process and real-time coverage independent |
| Coverage | Declare which edge families are complete and retain unresolved sources as gaps | Missing-provenance edges are excluded; absent required coverage prevents a compatible conclusion |
| Category search | Explicitly choose category, rule set, order context and budget | Search the chosen category, preserve valid witnesses, and return unknown on unfinished work |
| Full model composition | A new datatype still needs source-validity, applicability and completion obligations | `classifyModelsV4` accepts only its supported source profiles; a supplied graph does not automatically establish all model obligations |

Graph input supports 128 transactions, 50,000 edges and 4,096 coverage gaps. Search budgets are independent of construction and exact-interpreter limits. `Adya2000Mixed` and `ElleFixed4e359e5` are separate mandatory rule-set choices. `ScopedDataOnly`, `ScopedWithProcess` and `ScopedWithRealtime` select the order context. A physical pooled connection is not automatically a logical process.

This is source-level extensibility: callers write ordinary MoonBit inference functions and compose their edge outputs. There is no dynamic plug-in loader, automatic recognition of an arbitrary datatype, or acceptance of an adapter's precomputed model verdict. Coverage flags at the declared-graph boundary are caller assertions; verification recomputes the category over that declared graph. Database-source verification remains a separate operation.

## Relationship to Elle

At the fixed reference commit, Elle's `core/combine` composes analysis functions, retaining a combined graph, explanations and anomalies. Its register checker combines direct WR inference, partial-version WW/RW inference and additional graphs; list append inference uses observed element order. MoonTxnWitness exposes corresponding typed edges, original-source JSON and an explicit graph/search boundary. It separately verifies original capture programs before composing full models.

The interfaces are functionally comparable extension points, not binary-compatible plug-ins or proof of equal inference strength. The [feature matrix](feature-matrix-v4.md) lists which built-in adapters and model profiles are actually available. New adapters must add source tests, positive/negative category cases, missing-evidence cases and an independent interpreter or a reference-tool comparison before claiming full model coverage.

Reference source: [Elle core/combine and explainer protocols](https://github.com/jepsen-io/elle/blob/4e359e597c52938b0afebb8bc42273914d68a424/src/elle/core.clj), [register inference](https://github.com/jepsen-io/elle/blob/4e359e597c52938b0afebb8bc42273914d68a424/src/elle/rw_register.clj), [list append inference](https://github.com/jepsen-io/elle/blob/4e359e597c52938b0afebb8bc42273914d68a424/src/elle/list_append.clj).
