# Registered inference modules

This independent MoonBit consumer registers two local functions over the same immutable original-history view, alongside two compiled built-ins. One function replays original WR sources; the other selects original WW/RW constraints using a bound parameter. Their output is merged without feeding one module's results into the next.

The input contains two committed transactions, explicit unique versions and confirmed client outcomes. The example classifies `serializable`, verifies the complete report, and rejects changed parameters, removed modules and a different independently supplied work budget.

From this directory in the source checkout, use MoonBit 0.10.16 or newer:

```powershell
moon run --target wasm-gc . --deny-warn
```

The included `moon.work` selects the checkout as a local dependency. The `moon.mod` dependency targets version 0.4.3, which introduces these APIs. After that version is published, a registry-only consumer can copy this directory into a new location, omit `moon.work`, run `moon update`, and run the same command.

Expected output:

```text
registered modules: serializable checked-compatible; two independent modules and builtins verified
verification policy: changed module, removed modules and changed budget rejected
```

Registered code is caller-trusted and deterministic; reports cannot load callback code. This example replays constraints already entailed by original source checks, so the base positive certificate remains applicable. Genuinely new constraints may provide conditional refutations, but do not automatically authorize model compatibility. See [the module contract](../../docs/inference-modules-v4.md).
