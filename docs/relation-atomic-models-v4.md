# Atomic primary-key row model profile

`ModelRelationAtomicRows` / `captured-relation-row-slots/v1` explicitly projects complete original `relation-set-v1` programs into atomic typed primary-key slots. The existing `ModelRelationPoint` default and predicate category interfaces retain their previous contracts.

The slot identity includes relation name, primary column, primary type and the original typed key. Present row versions, confirmed tombstones and justified initial absence remain distinct. This is a persistent key-slot interpretation; equivalence to physical row incarnations is not asserted.

## Original source requirements

Projection rechecks the original complete capture window, exact transaction outcomes, savepoint effect journal, typed row identities, complete installed version orders and every delivered point query. Each query must be a complete singleton-primary-key equality query with an independently justified source. Empty results with competing absence/tombstone explanations stay unknown. Unmapped operations, sequence holes, missing sources, unconfirmed outcomes, range predicates and additional AND terms do not become complete through projection.

Original reads are retained across savepoint rollback. Only the matching own write effects are undone. Whole-row own assignments reveal their own row; they do not reveal an external prefix or manufacture a SELECT. Temporary write preconditions that are not covered by actual reads, an active own effect, a final-writer block or a closed immutable initial slot remain an explicit applicability gap.

## Per-model checks

Every validated external read contributes its own dependency source. RC can permit two external reads of different installed row versions; that formal repeatable-read INT finding does not by itself make the source window incomplete. The finding remains available to models requiring it. All other source gaps still block completion. Later reads are preserved, so mutually dependent later reads can refute RC through an actual WR cycle.

Snapshot completion requires the appropriate acyclic extended graph and source/overlay premises. Its concrete CO/VIS prefix certificate is independently replayed against the original JSON row program, including actual row values and savepoint events. Serializable completion additionally constructs and replays a complete D-topological serial order. Failure of one certificate is unknown, not a proof that a weaker model is violated. Given logical snapshot graphs remain unsupported, and BEGIN does not create a logical database snapshot fact.

The 14 fixed canonical definitions are composed from their actual required rules. Compatibility is reported only when every necessary rule completes under the chosen original-order facts and budgets. Reliable forbidden evidence remains a refutation when another obligation is unknown. Arbitrary relation predicates do not acquire generalized completion through this point-row profile.

## Interfaces and independent verification

Use `project_relation_rows_v4` for the opaque projection result, or select `relation_profile=ModelRelationAtomicRows` in `model_options_v4` and call `classify_models_v4`. JavaScript uses `classifyModelsV4` with `relationProfile: "captured-relation-row-slots/v1"`; CLI consumers pass that field through an independent options JSON file.

`verify_relation_row_projection_v4` and `verify_relation_program_replay_v4` recompute from the source with independent caller budgets. The latter also requires the caller's concrete certificate and `RelationSnapshotPrefixes` or `RelationSerialOrder` mode. `verifyModelsV4` and model capsules likewise require independently selected model/profile/budget options. Reported statuses or embedded larger budgets do not authorize verification.

The original point-row capacities remain 128 transactions and 4,096 operations. Source checks are limited to 1,000,000; graph rules retain their separate state and edge-check budgets. These are bounded checks, not exact enumeration capacity claims. Results describe the supplied formal transaction observations; PostgreSQL product isolation names are not substituted for these definitions.
