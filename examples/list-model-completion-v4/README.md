# Captured list model example

This MoonBit consumer maps a complete original append-list capture, including an own read followed by rollback, into explicit prefix constraints. It checks generalized SI, replays every original list operation against the constructed visibility certificate, verifies the complete result and confirms source immutability.

Use the current source checkout with moonc 0.10.16 or newer:

```powershell
# From examples/list-model-completion-v4
Set-Content -LiteralPath moon.work -Value 'members = [".", "../.."]'
moon run --target js . --deny-warn --jobs 1
```

The local workspace selects this source checkout. These prototype APIs are not claimed to be present in the currently published package. Remove the local workspace override when validating a future published package. The example needs no database or Python adapter.

Expected output:

```text
captured list: foreign prefix inferred from delivered own read; revoked append retained as observation; original program and SI evidence verified
```

The prefix interpretation is explicitly selected through `ModelListPrefixStates`; native list model behavior remains the default. This is conditional evidence from the supplied capture, not database authenticity or a PostgreSQL isolation-level assertion. See [the projection contract](../../docs/list-prefix-state-projection-v4.md) for supported sources, model-specific rules and counterexamples.
