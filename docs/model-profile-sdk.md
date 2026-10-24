# Configured model source analysis and complete-package replay

Use `install_model_profile()` with an immutable `ModelScope`, one new controlled
PostgreSQL18 schema and a startup synchronous psycopg factory. Original business
SQL executes through that factory and fetches the original business columns.
Stop/close business connections, finalize the observed source window, and export
the original package. The exact supported SQL/types and operational boundaries
are in [configured-model-profile.md](configured-model-profile.md).

The producer accepts no handwritten model history. The new MoonBit
`model_profile_source_v3_json` independently checks source controls, SQL and
parameters, native results, actual delivery, lifecycle and committed effect
closure before deriving a separate list or relation trace. Raw diagnostic gaps
and unconfirmed sources remain visible. The complete model query/write trace is
then interpreted using the existing six-transaction, 128-operation bounded
models; search budget exhaustion returns inconclusive.

The JS SDK exposes explicit new methods:

```js
const report = analyzeModelProfileV3(originalSourceText, {
  maxStates: 100000,
  maxOperationChecks: 1000000,
});
const checked = verifyModelProfileV3(originalSourceText, report);
const capsule = makeModelProfileCapsuleV3(originalSourceText);
const replayed = replayModelProfileCapsuleV3(capsule);
```

The capsule format is `moontxnwitness-model-profile/v1`. It retains the **entire
original source envelope**, its four original raw texts, all source SHA256
values, exact options/report text, declared budgets and exact current compiled
core/host identities. Replay recomputes every projection and report. Extra,
missing, duplicate or changed fields, unknown algorithms/engines and re-signed
changed conclusions fail exact replay. Inconclusive results can still be
faithfully packaged and replayed without turning them into complete findings.
This binds observations and conclusions; it does not authenticate a server or
an exclusive-writer declaration.

The command line supports:

```text
node dist/moontxnwitness.mjs model-profile-v3 MODEL_SOURCE.json --output REPORT.json --capsule PROOF.json
node dist/moontxnwitness.mjs verify-model-profile-v3 MODEL_SOURCE.json REPORT.json
node dist/moontxnwitness.mjs replay-model-profile-v3 PROOF.json
```

`--options OPTIONS.json` is available for analysis and verification. Outputs
cannot overwrite original inputs. All inputs/options/reports have explicit byte
bounds. `examples/model-profile-roundtrip.mjs --out-root NEW_PARENT` replays two
actual captured Repeatable Read anomalies, a CRUD result and an inconclusive
zero-row write without opening a database.

This first host slice supports analysis and **complete original-package replay**.
It does not claim source-closed model-profile reduction. A negative relation
query can depend on an earlier delete or a write crossing its predicate. A
future source-preserving reducer must retain those writers and revalidate the
remaining source closure; the older generic semantic reducer is unchanged and
does not silently acquire this stronger profile claim.
