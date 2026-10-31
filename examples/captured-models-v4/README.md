# Captured register model example

This development-checkpoint consumer calls only public MoonBit APIs. It checks all 14 fixed Elle model definitions from an original register capture, including a legal own read followed by savepoint rollback, and verifies the complete result under independently supplied options. It does not claim database authenticity or validate a given logical snapshot graph.

Use the current source checkout (moonc 0.10.16 or newer):

```powershell
# From examples/captured-models-v4
Set-Content -LiteralPath moon.work -Value 'members = [".", "../.."]'
moon run --target js . --deny-warn --jobs 1
```

The local workspace selects the checked-out module. These prototype APIs are not claimed to be present in the currently published package. The workspace override is local and should be removed when validating a future published package. No database, Python, or Node wrapper is required by the example itself.

Expected output:

```text
captured register: 14 model obligations completed; original rollback observations retained; evidence verified
```
