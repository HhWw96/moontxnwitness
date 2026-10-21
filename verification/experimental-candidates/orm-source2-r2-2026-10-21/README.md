# ORM sourceSchema2 MoonBit candidate

This revision preserves the actual first remote failure from run `39584869264`
in `first-ci-39584869264/`. The fixed-template AST check passed there; `check-all`
reported 29 errors, and no model tests, build or mutation harness executed.
This revision only supplies explicit JSON type context, renames a reserved local
identifier and replaces deprecated raising callback syntax. It changes no raw
fixture, contract, assertion expectation, SQL template or mutation harness.
The original candidate manifest SHA `3cc3bab0339703acb4f1237ae833d98def66d1aa5c7772c99d5690d864164390`
and its source files remain unchanged in the original directory. This new
revision has not been compiled locally or remotely at preparation time.

This is a static experimental candidate, prepared for independent review and a temporary Linux CI build. **No new MoonBit source in this directory has been compiled or tested locally.** The template check, 24 new white-box tests and original-byte mutation harness are pending execution. Their expected behavior below is a plan, not a pass record.

The baseline is the preserved source1 diagnostic at source `5cfa00f0fbcdcb4152f819b7e332a569e15911a526cbfe3586409c5a7c5f8590`. Its old input contract, implementation, 16 missing-raw-field gaps, tests and actual output remain unchanged. This candidate adds a separate `v3-orm-source-proof-2` entry rather than widening or rewriting that old contract.

## What the candidate checks

It directly decodes original native/raw PostgreSQL text cells, then checks the exact controlled SQL workflow: pre-migration catalog, first business lock, thirteen installation DDL statements, marker and three initialization parameter groups, second business/owned lock, catalog/function/trigger/marker/snapshot queries and acknowledged COMMIT. Final catalog/functions/marker/snapshot/ledger facts stay in the terminal record and are checked against a separate real control transaction.

The raw fixture contains **one** explicitly configured Jsonb parameter, in sourceSeq 24. The two preceding state INSERTs carry `present=false` and `image=null`. All three groups are checked against actual source/state facts. No claim of three Jsonb objects is made.

The flat array decoder follows [PostgreSQL 18 array I/O](https://www.postgresql.org/docs/18/arrays.html#ARRAYS-IO): it distinguishes null and quoted `NULL`, handles quoted delimiters and escaped characters, and declines nested or nondefault-bound arrays outside this profile. Numeric cells require exact canonical integers; unsupported OID/format/typmod or native/raw disagreement fails closed. Record/cell/node/byte bounds remain explicit.

The old strict business batch, original/executed SQL, parameters, business result prefix/EOF, actual internal PGresult, effects and scope/ledger routines are reused. Local `provenStatements`/`provenFacts` do not grant coverage exemptions. Every result has `analysisCoverageAccepted:false`, `history:null` and empty `verifiedProfiles`. Original lifecycle, zero-result, unsupported and other missing-source gaps remain visible.

## Exact overlay files

Apply this overlay only in a fresh experimental clone of the intended frozen root baseline. Do not copy over the default checkout or published dist. The producer's controlled raw input is not fetched or run as a database application.

Copy these unchanged legacy helper files from this directory's `legacy/` subdirectory into the temporary clone's `src/`. The manifest binds each copy to the unchanged original `artifacts/orm-v3-moonbit-draft/` file:

- `orm_sql_v3.mbt`
- `orm_proof_v3.mbt`
- `orm_catalog_v3.mbt`
- `orm_templates_v3.mbt`
- `orm_sql_v3_wbtest.mbt` (the existing 28 source1 units)

Copy these new files from this directory into that same `src/`:

- `orm_control_source2.mbt`
- `orm_control_queries2.mbt`
- `orm_control_templates2.mbt`
- `orm_control_catalog2.mbt`
- `orm_control_profile2.mbt`
- `orm_source2_v3.mbt`
- `orm_control_source2_wbtest.mbt`

Copy `capture_bridge_source2.mbt` to the temporary clone's `src/capture_bridge/orm_source2.mbt`. Its only bridge dependency is the existing `@txn` import of `HhWw96/moontxnwitness`. The library requires the existing imports of `moonbitlang/core/json`, `moonbitlang/core/encoding/base64` and `moonbitlang/core/encoding/utf8`. No Python database driver or SQLAlchemy install is required for the MoonBit build or mutation harness.

The two bridge exports are `orm_sql_source2_v3_proof_json` and the preserved `orm_sql_v3_proof_json`. No stable SDK or CLI file is changed. The new independent entry accepts:

```json
{"schema":2,"profile":"fastapi-users-sqlalchemy-7.0.0-pg18/1","traceText":"<original trace JSON text>","sourceJournalText":"<original source JSONL text>"}
```

The original raw fixtures are copied byte-for-byte under `fixtures/`. `fixtures/bindings.json` records source/destination SHA256 and lengths. `check-source2.mjs` validates those fixed hashes before assembling the envelope in memory; it never rewrites the original files.

## Pending CI commands

Use the already pinned MoonBit `v0.10.14+7d59c7ec9` toolchain. From the temporary clone, the intended sequence is:

```text
node scripts/moon.mjs check --target all --deny-warn --jobs 1
node scripts/moon.mjs test --target js src/orm_control_source2_wbtest.mbt --deny-warn --jobs 1
node scripts/moon.mjs test --target wasm-gc src/orm_control_source2_wbtest.mbt --deny-warn --jobs 1
node scripts/moon.mjs test --target wasm src/orm_control_source2_wbtest.mbt --deny-warn --jobs 1
node scripts/moon.mjs test --target js src/orm_sql_v3_wbtest.mbt --deny-warn --jobs 1
node scripts/moon.mjs build --target js --release --deny-warn --jobs 1
```

Then use the generated ESM module at `_build/js/release/build/capture_bridge/capture_bridge.js` directly:

```text
node <candidate>/check-source2.mjs _build/js/release/build/capture_bridge/capture_bridge.js <candidate>/fixtures <new-output>/source2-functional-first.json
```

MoonBit may generate a native executable rather than an ESM extension in another layout; inspect the compiler output and preserve any path/build failure instead of silently using an old dist. The existing JS bridge is configured for ESM. A failed first receipt must be retained; the harness refuses to overwrite it.

`python <candidate>/generate_control_templates.py --check` is a source-template consistency check, not a database script. It reads the two frozen producer files included under `producer-templates/` and checks their embedded SHA256 values before comparing all twelve SQL constants by AST. It does not import or run the producer. If the frozen producer files are staged elsewhere in CI, pass `--producer-dir <frozen-producer-dir>`. Do not use the generator's write mode during frozen-source verification.

The functional harness preregisters the original 121-query/21-batch/8-effect/7-ledger baseline and resealed semantic mutations. These include altered raw/native cells, OIDs/format/status, commands, parameters, each DDL, both lock windows, setup Jsonb, query references, initial/final source and ledger facts, and safe failures. It preserves whole-trace false boundaries even when local evidence succeeds. All are **unexecuted candidate assertions** until a new CI receipt exists.

## Runtime and acceptance boundary

An isolated D preparation directory was created from the old source1 source only, with no `_build`/`dist` copy, but the new overlay is staged here and has not been compiled there. Local compilation is intentionally paused for host memory constraints. The experimental clone may instead use a newer root baseline; its own actual source/runtime hashes must be recorded after the overlay and cannot be borrowed from either old manifest.

Passing these checks would establish consistency of this bounded supplied source profile under controlled writers, pinned adapters and no unobserved DDL/metadata mutation. It would not authenticate the collector, prove arbitrary ORM/SQL coverage, accept the entire original trace, or complete the competition roadmap.
