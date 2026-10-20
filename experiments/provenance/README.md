# v0.1.2 provenance experiments

These are two independent **research prototypes**, outside the stable v0.1.1
capture adapter. They do not complete its existing-application acceptance gate,
and do not constitute a v0.1.2 release or a production-ready installer.

Both candidates start with an ordinary table that has no version column. The
experiment supports a single text primary key and one payload column. The real
database fixture uses integer payloads, repeated values, several updates in a
transaction, deletion, reinsertion, transaction rollback and savepoint rollback.
Initial keys include all rows in a locked initial state plus explicitly declared
missing keys. Other keys are outside this prototype's frozen scope.

| Candidate | Live row version | Negative-read/deletion state | Costs to measure |
| --- | --- | --- | --- |
| Column + triggers | Added UUID column, new UUID before every INSERT/UPDATE | Separate transactional metadata for initially missing/deleted keys | Table migration and lock duration; changed SELECT * layout; row width; audit writes and WAL |
| Sidecar + triggers | Existing business columns stay unchanged; UUID and presence in another table | The same transactional state table includes tombstones | Extra MVCC join and metadata writes; state-row locks; deadlocks; WAL and storage |

Each candidate has an audit table whose UUID primary key includes initial and
later versions. The table stores per-key predecessor identity and old/new payload,
with deletion represented by `present=false`. A UUID is a version identity, not a
commit timestamp or rank. Neither transaction IDs, sequences, thread return times
nor UUID sorting supply commit-order facts. Audit output is sorted only to make
the saved file stable; the independent verifier follows predecessor links.

The column candidate also needs deletion metadata: a deleted row cannot return
its former version column. Missing rows are observed using that metadata, with
an independently identified initial absence or later tombstone.

## Initialization and observation

`install()` requires a dedicated idle autocommit setup connection and an explicit
`mtw_provenance_*` schema. It opens a Read Committed transaction, acquires SHARE
table locks before reading initial data, validates the table profile, creates its
objects, assigns initial identities, and publishes the snapshot only after
commit returns. The column migration also needs PostgreSQL's stronger ALTER TABLE
lock, and initialization writes rows; SHARE is not a claim that installation
permits uninterrupted writes. Application workers start after installation.

The installer refuses existing RLS, user triggers, views/partitions or a primary
key that is not the declared single text column. It supports at most 10,000
initialized keys. All generated identifiers are quoted, and PL/pgSQL dollar
delimiters are chosen outside the complete function body. Values are bound as
parameters. No extension or object is installed outside the supplied schema.
Names are deterministic, creation never uses `OR REPLACE`, and an object-name
collision aborts the installation transaction.

`Installation.observe(connection, key)` uses **one SELECT** joining the business
table and version metadata. Positive and negative observations therefore use one
statement snapshot; the API never reads business data and then issues a second
query to infer its version. It checks that business presence and metadata presence
agree. It refuses unknown keys rather than manufacturing an initial absence from
the first missing result.

The prototypes intentionally reject inserts outside the frozen key scope and
primary-key changes. They add metadata and locks to business writes and can alter
contention or failure behavior. The generated SELECT is an explicit integration
operation, not universal automatic SQL rewriting. These limits must be removed or
made visible as coverage gaps before a broader application profile is claimed.

Metadata and audit writes belong to the business transaction, so rollback and
rollback-to-savepoint remove them together. The database fixture retains observed
pre-rollback tokens separately to check that they did not become committed facts.
This does not flatten savepoints for the core analyzer or resolve unknown commits.
A production capture design would also need original client attempts, outcomes,
coverage and unknown-result handling.

## Uninstall

`uninstall()` checks the installation nonce and current business table OID inside
a locked transaction. It drops only this installation's triggers, functions,
metadata tables and optional added column. Business keys/payloads remain. It does
not drop the caller's schema or use CASCADE. The marker is an ownership guard,
not cryptographic proof against a database owner who can modify all objects.

The standalone fixture creates one **new** explicitly named schema, refuses to
adopt an existing schema, and removes only the schema it created. `--keep-schema`
keeps the controlled business fixture tables for inspection. Candidate metadata
is still removed by the tested uninstall path.

## Run checks

The fast tests use no database:

```text
python experiments/provenance/test_prototype.py
```

To run the actual PostgreSQL 18 fixture, configure either `MTW_PG_CONNECTION_FILE`
(a private JSON object with psycopg connection arguments) or `MTW_PG_DSN`. Use a
dedicated local test database and a new controlled schema name:

```text
python experiments/provenance/postgres_test.py --schema mtw_provenance_local_run1 --output artifacts/provenance-local-run1
```

An absent optional driver/database is reported as not executed. Driver messages
and credentials are not printed; failure records preserve error class, SQLSTATE
and code-frame locations. The optional fixture uses finite connection, statement
and lock timeouts. It checks:

- Initial positive and negative facts; different identities for equal values.
- Multiple writes, tombstone identity and reinsertion in one transaction.
- Metadata restored by transaction and savepoint rollback.
- Two actual concurrent writers and independently verified predecessor links.
- Every committed observation's payload/presence against its version audit row.
- Refusal to uninstall with a mismatched marker; preserved business values;
  successful reinstall and uninstall.

`test_prototype.py` has `actualDatabaseExecution=false`. Running it is not evidence
that the PostgreSQL functions compiled or that concurrency behaved as expected.
The real suite writes a distinct receipt and retains failure records. This folder
does not install or execute any external application's setup scripts.

## Candidate selection remains pending

The real fixture records one smoke installation duration only. It is **not** a
performance comparison and cannot establish transparency or negligible overhead.
Before selecting a stable candidate, alternate baseline/candidate runs on the
same database with the same workload and data. Measure at least:

- Actual application/configuration/DDL changes and installation/uninstallation time.
- Setup lock duration and blockers; permissions; schema and SELECT * compatibility.
- TPS, P50/P95/P99, CPU and memory, including repeated and hot-key writes.
- WAL, audit/state growth, retention, index and vacuum cost.
- Row/state lock waits, deadlocks, retries, failures and anomaly-rate changes.
- Recovery after interrupted setup, business rollback, logging failure and unknown
  commit; relevant initial-snapshot coverage and ordinary-business integration.

Until the source and cost gates pass, neither prototype should be described as
fully transparent, zero modification, low overhead, or production ready.

## Controlled cost protocol

`cost_study.py` compares **B/A: the provenance prototypes and their single-statement
read paths against plain business SQL**. It does not enable the v0.1.1 capture
adapter, serialize raw capture events or call the MoonBit analyzer. It is not a
full capture C/A measurement and must not be presented as one.

The default formal protocol runs all three modes (`plain`, `column`, `sidecar`),
1,000 transactions per mode per batch, 100 warmup transactions, and three batches
with rotated order: plain/column/sidecar, column/sidecar/plain, sidecar/plain/column.
Each candidate occupies each execution position once. Within a batch, all modes
start with identical 32-key integer data and receive identical frozen generated
operations and warmups. The seed is 20261020 plus the batch index, the generator is
named/versioned, and full inputs plus source hashes are saved.

One serial client performs two positive primary-key reads, one initialized
negative read, one update and one commit per transaction. The plain mode uses
ordinary point SELECT; candidates use `Installation.observe()`'s single SELECT
joining business and metadata. Every read's existence/value is checked against
the workload state. Final business values are independently replayed from the
frozen inputs and checked before and after uninstall. Candidate version chains
are also independently checked after timing. This protocol does not measure
contended multi-client workloads or infer deadlock rates.

Per-transaction latency covers the first point read through commit acknowledgement,
including the matching read/value checks. TPS additionally includes the common
client loop bookkeeping between transactions. Setup, warmup, post-run source
verification, output serialization and uninstall are outside the timed window.
The same lightweight measurement harness is used for all candidates. Raw completed
latency arrays are kept for every batch, including valid prefixes of failed runs;
no mode or slow sample is selected away. P50 uses the median; P95 uses nearest rank.

WAL is the recorded before/after `pg_current_wal_insert_lsn()` position difference.
It is a cluster-wide address delta, including padding and possible background
activity, rather than a per-table record-byte counter. Run on an otherwise idle,
dedicated test cluster and explicitly assert that scope with `--exclusive-cluster`.
Without that assertion, attribution is marked unverified. CPU, RSS, lock waits,
contended deadlocks, real application integration and vacuum/retention costs remain
unmeasured and have no fabricated numeric values.

Run only after other benchmarks stop:

```text
python experiments/provenance/cost_study.py --schema mtw_provenance_cost_run1 --output artifacts/provenance-cost-run1 --exclusive-cluster
```

The same private connection configuration as the PostgreSQL prototype test is
used. A new explicit schema and output directory are required; previous receipts
are never overwritten. Only that newly created fixture schema is cleaned up.

For pipeline smoke validation, `--quick` defaults to 20 transactions and three
warmups per mode per batch, retaining all three batches. Quick receipts say
`smoke-passed` and `formalProtocolCompleted=false`, irrespective of timing values.
The default formal protocol refuses fewer than 1,000 transactions per mode/batch.
`formalProtocolCompleted` means that this measurement protocol completed with
declared dedicated-cluster scope; it does not mean a performance target, release,
business integration or competition acceptance passed.

Output contains `workload.json`, nine batch JSON files with raw transaction
latencies/TPS/P50/P95/WAL/final business values, and `study.json` with all candidate
summaries and matched-batch B/A ratios. Lower TPS or higher latency must be
reported as regressions. Install/uninstall durations are three smoke observations
per candidate, not a controlled migration benchmark. Failed and partial runs stay
in their own output directories. The pure protocol helper checks are:

```text
python experiments/provenance/test_cost_study.py
```

These helper tests execute no database or performance measurements.

Sources: [PostgreSQL table locks](https://www.postgresql.org/docs/18/explicit-locking.html),
[trigger transaction behavior](https://www.postgresql.org/docs/18/trigger-definition.html),
[statement snapshots](https://www.postgresql.org/docs/18/transaction-iso.html),
[savepoint rollback](https://www.postgresql.org/docs/18/sql-rollback-to.html).

## First measured result (2026-10-20)

The complete local Windows PostgreSQL 18.6 protocol ran 9,000 measured
transactions and 900 warmup transactions. All nine mode/batch executions passed
the independent business-value checks and candidate predecessor checks. Raw
inputs, all latency samples, failures (if any) and environment are in
`verification/provenance-prototypes/run-fff81b8ea9134993a1c3a2cebb8ebac5/`.

| B/A candidate | Matched-batch TPS ratio (geomean) | Matched-batch P95 ratio (geomean) | WAL LSN delta ratio (approximately) |
| --- | ---: | ---: | ---: |
| Added column | 0.707 | 1.438 | 4.15 |
| Sidecar | 0.688 | 1.457 | 5.29 |

Both candidates regressed throughput and latency on this workload. These results
do not meet the future full-capture performance goals; the full capture C/A path
was not measured. They do not establish a winner for production or a stable
v0.1.2 implementation. CPU/RSS, multi-client contention, lock waits, deadlocks,
retention and real application integration are still unmeasured. WAL numbers are
cluster-wide position differences with the limitations stated above.
