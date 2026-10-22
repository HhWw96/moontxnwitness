# Isolated actual ORM database acceptance harness

Prepared only; no database has been started by this preparation. The original 20-file cache candidate remains frozen and untouched. This supplemental harness has its own `execution-inputs.json` and first-attempt unit receipts.

## What will execute

`frozen_run_postgres.py` is the exact existing slice3 fixture source. The runner extracts its original `RecordingCursor`, `models`, `work`, `surface` and `IDS` ASTs unchanged, retaining every assertion. Actual `SQLAlchemyUserDatabase` methods import from the already-present, fully byte-checked upstream v7.0.0 commit `6397ace506d829a2ee12786da5d724c3f4c6b634`; no download or replacement business implementation is used. The copied original setup installer, relation contract and control-query recorder change import paths only; a preflight checks their complete class/function ASTs against their sources.

The collector imports **only** the candidate payload `moontxnwitness_capture.orm` and its relative modules. Startup checks actual module paths and records their byte hashes. It does not load the older `async_adapter.py`, bootstrap the older package, or substitute a mainline collector.

The existing workload runs in plain and observed tables, then repeats in another new schema with the cache setting changed. It retains real base-user get/create/update/delete, commit-triggered refresh/new transaction, duplicate-email `23505`, NULL-password `23502`, exact original exception identity, nested rollback, same-value update, delete/reinsert, pool checkout/reset/dispose/reconnect, original no-result fetch exception identity, point reads and negative reads. Cache-on/off compares business outputs/errors/surfaces, actual surviving ledger semantics, and final state. It records actual compiler/hit/miss/retained-entry counts without interpreting them as formal performance.

Setup/finalization retain original native control-query records and acknowledged COMMIT tags. A fixture-only `RecordingConnection` delegates the original psycopg generator and independently records native COMMIT/ROLLBACK result status, tag and transaction status from SQLAlchemy physical connections. Recording failure cannot replace an original exception. Missing replies remain unknown even if the connection is idle. These fixture ACK observations are not injected into the capture, source journal or inference facts. Existing collector gaps and `completeCapture:false` / `coreProofAccepted:false` stay visible.

## Root execution command

Use the already-installed, pinned environment (Python 3.12.5, SQLAlchemy 2.0.55, psycopg 3.3.6). Do not install packages or use the default system SQLAlchemy 2.0.45 environment:

```powershell
& 'D:/CodexScratch/MoonTxnWitness-v011-20261020/orm-v3-draft-env-20261021/Scripts/python.exe' -B artifacts/v013-orm-candidate/database-harness/run_owned.py --bin artifacts/postgres18-tools/pgsql/bin
```

Root may need the same process permissions that successfully ran earlier owned PostgreSQL clusters. Do not alter ACLs or reuse a previous cluster. This command creates a fresh `executions/run-…` directory under this harness; all outputs stay there. On Windows it uses a fresh ASCII drive alias and a junction to the existing tools, starts PostgreSQL only on loopback, and stops **only** its own newly created cluster in `finally`. Existing runs are never reset or deleted. The first child/control logs, source bindings, partial outputs and failure receipt are retained. Successful execution requires successful owned-cluster shutdown.

Private `private/` contains cluster data, connection/password files and server logs. It must not be uploaded wholesale or read into public reports. Public review should select the top-level `execution-receipt.json`, `control.log`, `first.log`, and the database result directory after checking its disclosure scope. Never publish the private connection or password files.

No Node analyzer or MoonBit compiler runs in this harness. A separate invocation of the already-built `inspect-orm-source-v3` can later validate the new raw inputs, bound to the actual runtime used. Existing database/core receipts are not acceptance evidence for this migrated collector.

## Output and acceptance boundary

- `execution-receipt.json`: owned lifecycle, exact source bindings, child result digest, actual execution and shutdown.
- `database/comparison-receipt.json`: actual upstream binding, original workload AST hashes, candidate collector bindings, mode comparisons and per-mode receipt digests.
- `database/cache-{disabled,enabled}/`: original control records and same-statement source JSONL, raw diagnostic trace/journal, installation/catalog, surviving ledger, DBAPI behavior, native replies and explicit gaps.

This first database gate concerns the preserved bounded base-user source profile and cache semantics. It does not test lost-COMMIT network replies, arbitrary connection configuration transitions, OAuth joins, `lower(email)`, arbitrary ORM SQL, whole-trace core proof, production use, throughput or tail latency. These are separate work. Real failure must remain failed; do not change the frozen business assertions or substitute old outputs.

Lightweight preflight, without starting PostgreSQL:

```powershell
& 'D:/CodexScratch/MoonTxnWitness-v011-20261020/orm-v3-draft-env-20261021/Scripts/python.exe' -B artifacts/v013-orm-candidate/database-harness/test_harness.py
```
