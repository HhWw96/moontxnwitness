# Atomic row model consumer

This local MoonBit consumer selects `ModelRelationAtomicRows`. It retains actual singleton-primary-key queries, whole-row effects and savepoint observations, verifies the requested canonical model obligations, and separately replays a concrete original row program certificate.

From this example directory, create a local `moon.work` containing:

```toml
members = [".", "../.."]
```

Then run:

```text
moon run --target js --release . --deny-warn --jobs 1
```

The workspace selects this integrated source implementation. The current published package is not assumed to contain this opt-in interface.

The input must have a complete source window and a complete initial table snapshot. Only complete single-primary-key equality queries are projected. Ambiguous empty results, broader predicates and unproved temporary-write inputs stay unknown. A pooled physical connection does not supply logical-client facts.

See [the row model contract](../../docs/relation-atomic-models-v4.md) for source, proof and budget boundaries.
