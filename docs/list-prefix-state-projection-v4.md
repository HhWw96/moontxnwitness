# Explicit list prefix-state projection

`project_list_prefix_v4` reconstructs a derived state program from original `append-list-v1` observations. Each append, delivered read and savepoint effect stays linked to its original sequence. Derived prefix states, external-prefix components and writer-block constraints are stored separately from captured facts. The original history is not rewritten and no SELECT is created.

Model composition selects this interpretation with `model_options_v4(list_profile=ModelListPrefixStates, ...)`. `ModelListNative` remains the default with its original results. Verification requires independently supplied policy and budgets; a report cannot enable the additional premise itself. The prototype profile is `captured-list-prefix-state/v2`, with distinct projection, composition and counter identifiers.

## Applicable source programs

The mapping requires a complete capture window, confirmed outcomes, unique item identities and matching business values, complete producer prefixes, and a proved order of final writer blocks. Different items may have identical business values. Missing producers, incomplete or interleaved external prefixes and unproved writer order remain unknown. Writer identifiers are sorted only to visit candidates; the algorithm does not select an order from their names.

Every original append and delivered read is retained. Rollback removes effects while preserving already delivered reads. A delivered final own prefix supplies a positive writer-order constraint only when active own items exactly match that key's final surviving group. Provisional or revoked groups cannot manufacture such an order.

For an own read, the validated active own suffix is removed from the complete returned list to obtain an external-prefix component. That component must identify a complete initial or installed terminal prefix. It is an inference from the actual delivered value, not an additional operation. WR and immediate-successor RW constraints preserve that actual read, source appends and derivation. An own immediate installed successor stops RW; the adapter does not jump over it to a later transaction.

A revoked own append still constrains the snapshot of the original program. In W(x=[w], y=[y1]), A(read y=[y1]; savepoint; append x=a; read x=[a]; rollback; commit), the x component is the initial prefix. Together with the y source it yields an actual SI refutation. Changing the delivered x read to [w,a] permits a valid snapshot. Neither case needs an invented earlier SELECT.

## Model-specific obligations

| Fixed model family | Graph obligation | Full same-transaction single-snapshot INT required? |
| --- | --- | --- |
| Read uncommitted | W (WW) | No |
| Read committed | I (WW/WR), plus its fixed source/literal obligations | No |
| Repeatable read | I plus item RW and fixed literal coverage | No universal SI replay requirement |
| Consistent view | I and single-RW absence, plus independently replayed per-key ranks | No universal SI replay requirement |
| Generalized snapshot isolation | Ext(I,A), complete internal/source premises and a constructive original-program CO/VIS replay | Yes, for this completion certificate |
| Serializable variants | D with the selected order context and fixed literal/source premises | As required by the fixed definition and completion certificate |

The standalone list INT inspector deliberately has a separate result. For example, read [] then read [a] in one transaction can refute standalone INT and SI while satisfying the fixed RC model. A snapshot interpreter is not used to reject RC or RU. Logical clients and real-time observations retain their original independent applicability requirements; a pooled connection is not a logical session.

After constructing an SI CO/VIS certificate, production code executes the original typed list append/read/savepoint interpreter against every emitted visibility prefix and verifies same-key write conflicts. An invalid or incomplete replay leaves that completion unknown. This validates one certificate; it does not increase the existing exact-search transaction limits. CV rank certificates also check the external components of own reads, including observations preceding rollback.

## Reproduction and bounded checks

Run the public MoonBit consumer in `examples/list-model-completion-v4`. Its valid foreign-prefix case has no earlier external x read and retains a subsequently revoked own observation. It verifies the entire model result under explicit caller options and confirms that the source history stays unchanged.

The developer oracle reads original capture JSON directly, without importing normalized programs, inferred order, model statuses or graph edges. It enumerates commit orders and visible prefixes for at most three committed transactions and replays every actual append/read/savepoint. The deterministic 1,000-history corpus has 750 compatible and 250 incompatible programs. Each accepted model certificate is replayed by this separate implementation. Unsupported input and exhausted oracle budgets are distinct from unsatisfiability.

The earlier guarded v1 checkpoint and the pre-correction false certificate are preserved in local technical artifacts. V1 needed an actual prior base read or other restrictive base guarantee; v2 replaces that conservative restriction with a sourced external-prefix component and mandatory original-program certificate replay. The failure was not removed from the record.

These are local JS developer checks, not a database run, a full Clojure differential, an independent reviewer sign-off, or a performance measurement.

## Fixed references

The fixed Elle commit is `4e359e597c52938b0afebb8bc42273914d68a424`.

- [consistency_model.clj](https://github.com/jepsen-io/elle/blob/4e359e597c52938b0afebb8bc42273914d68a424/src/elle/consistency_model.clj): canonical RC/RU aliases at lines 204–208 and forbidden-phenomenon definitions at lines 432–448. Local reference SHA-256: `f909f517351081001054bef461fcdec709f6bd2d2c058955777e68033d4fb10b`.
- [txn.clj](https://github.com/jepsen-io/elle/blob/4e359e597c52938b0afebb8bc42273914d68a424/src/elle/txn.clj): W/I/item-RW/Ext projections at lines 307–324. SHA-256: `8c3c87062d518cc7ba9cee49408fe552e8057a59e5b2068f4f8aa0bf6421a5a6`.
- [list_append.clj](https://github.com/jepsen-io/elle/blob/4e359e597c52938b0afebb8bc42273914d68a424/src/elle/list_append.clj): per-operation internal checks at lines 145–185 and separate future-read checks at lines 187–235. SHA-256: `f4bfeee8afef994e662a4f5e2d36219ddd714254a9590f6bc36ca0b52bf3d2e7`.
- [Cerone and Gotsman 2016](https://software.imdea.org/~gotsman/papers/si-podc16.pdf), Definition 6 and Theorems 9/10: existential SI completion under the documented source premises, without a supplied logical snapshot graph.
