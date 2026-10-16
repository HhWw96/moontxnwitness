# Actual PostgreSQL 18 capture and regression

This optional demonstration executes SQL against PostgreSQL 18. The analyzer,
shortest cycle, bounded completion, reduction and semantic replay remain MoonBit.
Python only collects observations through two independent backend connections.

## Run the complete workflow

Use Python 3.12 on Windows x86_64 or Linux x86_64 for the frozen driver wheels.
Run these commands from the downloaded portable or built source directory:

```powershell
python -m venv .venv-pg
.venv-pg/Scripts/python -m pip install --require-hashes -r examples/postgres-requirements.txt
$env:MTW_PYTHON = (Resolve-Path .venv-pg/Scripts/python.exe).Path
$env:MTW_PG_DSN = 'host=127.0.0.1 port=5432 dbname=YOUR_TEST_DATABASE user=YOUR_TEST_USER password=YOUR_PASSWORD'
node dist/postgres-demo.mjs
```

On Linux use `python3`, `.venv-pg/bin/python`, and `export MTW_PYTHON=...` /
`export MTW_PG_DSN=...`. A JSON connection file may replace the DSN:
`node dist/postgres-demo.mjs --connection-file PATH`. Keep credentials outside
source control. The account needs CREATE permission on the selected test database.
Each invocation creates and drops only its own random `mtw_*` schema.

Every invocation creates a new `moontxnwitness-postgres-*` output directory.
Missing Python, the optional driver or database configuration produces
`not-executed`, `passed:false`, `actualDatabaseExecution:false`, and exit code 3.
A failed actual connection or scenario is a failed run, never a synthetic pass.
The completed suite exits 0. Recheck its portable evidence independently:

```powershell
node dist/moontxnwitness.mjs replay moontxnwitness-postgres-EXAMPLE/rr.capsule.json
node dist/moontxnwitness.mjs replay moontxnwitness-postgres-EXAMPLE/serial.capsule.json
node dist/moontxnwitness.mjs replay moontxnwitness-postgres-EXAMPLE/mini.capsule.json
```

Source developers can run `npm run postgres:verify` to additionally save a
versioned receipt under `verification/releases/VERSION/postgres/`. Each failed or
unexecuted attempt keeps a separate receipt. The independent `postgres.yml`
workflow runs the same 20 + 20 scenarios on an official PostgreSQL 18 container,
separately from Windows/Linux core tests and Linux Native execution.

## Start a disposable local cluster from existing binaries

The source helper starts and stops a project-owned cluster without a system
service. Provide a complete PostgreSQL 18 installation tree, not just copied exe
files. It preserves logs and data after stopping. On Windows choose an ASCII
temporary directory:

```powershell
.venv-pg/Scripts/python scripts/local-postgres.py --bin C:/PostgreSQL/18/bin --work-root C:/temp
```

On Linux choose a writable work directory and run as a regular non-root user.
The helper uses loopback, a random available port and generated credentials.
Its cleanup verifies the cluster data directory before stopping that cluster.

## What actually happens

Two workers point-read two duty registers before a barrier releases either
write. Each tries to clear a different register if both remain on duty. Values
are business data; every write carries a separate unique version identity.

For 20 Repeatable Read rounds both distinct-row writes commit, leaving zero on
duty. MoonTxnWitness explains the read/write dependency cycle and reduces the
combined history to a verified, transaction-one-minimal two-transaction case.
For 20 Serializable rounds the database rejects one initial transaction with
SQLSTATE 40001. That transaction is rolled back, then the whole operation is
retried as a fresh transaction after the concurrent pair has finished. The final
count stays one. These expectations follow the official
[PostgreSQL 18 isolation documentation](https://www.postgresql.org/docs/18/transaction-iso.html).
The anomaly at Repeatable Read is expected isolation behavior, not a database bug.

The evidence includes point-read results, acknowledged updates and commits,
server-reported aborts, rollback acknowledgment, unique versions, backend IDs,
single-process monotonic intervals, raw JSONL observations, histories, full
reports, the reduced case, three schema-2 replay capsules and file SHA-256 values.
JSONL is flushed after each event, so failed captures retain partial observations.
The server's own logs are retained by the local helper or CI service.

No sequence counter or worker return order supplies a commit order. Each fixture
key has at most one committed writer; single-writer order is an inference, not a
collected total order. A passing controlled fixture establishes this captured
execution and the replayed register model; it does not certify every database
execution, implement predicate/range-query analysis or authenticate a collector.
