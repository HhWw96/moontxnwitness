# Bounded ordinary-table capture draft

This ignored experiment is a functional step toward full-capture cost measurement. It is not a stable profile, an automatic arbitrary-SQL adapter, or a completed C/A benchmark. `coreProofImplemented` and `formalEligible` remain **false**, including when the raw journal is structurally complete.

## Supported input

Use Python 3.12.5, psycopg 3.3.6 and PostgreSQL 18 in a new, explicitly owned `mtw_provenance_*` schema. Before installation the table must have exactly `id text PRIMARY KEY, value integer NOT NULL`. Declare every existing key, from 1 to 64 distinct strings, each at most 512 UTF-8 bytes. There are three generated business statements: point SELECT, point UPDATE without RETURNING, and point UPDATE RETURNING value. Business connections use explicit transactions and the actual standard tuple row factory.

Unsupported SQL, parameters and factories run their original query and produce a coverage gap. The installed provenance triggers themselves restrict some out-of-scope writes, so this is not a claim that installing the experiment leaves every possible query unchanged. Dynamic keys, INSERT/DELETE/UPSERT, reliable negative reads, custom business cursors, async/ORM and arbitrary SQL proof are excluded.

The installer obtains ACCESS EXCLUSIVE before inspecting or changing the business table, runs the frozen column prototype's DDL, verifies owned definitions, reads actual key/value/token rows, acknowledges COMMIT, and only then publishes the initial snapshot. Start no business worker before `initialize()` returns. All writers must use the observer, and no actor may change DDL, triggers, replication role or owned metadata during the window. These are explicit deployment assumptions; comparing two catalogs does not prove that no change occurred between them.

## Reused schema boundary

`profile.py` imports `ddl`, `Installation` and SQL/catalog helpers from `experiments/provenance/prototype.py`, plus the frozen `verify_installation` from `capture_profile.py`. It does **not** instantiate or inherit the old `ColumnCapture`/`CaptureSession` observer. The fixed metadata tables still use JSONB payloads; the integer business value is converted by the existing `to_jsonb(value)` trigger expression. The UUID/version column, marker and two trigger definitions are unchanged. Initialization adds stricter checks for the original two business columns and native primary index. The new combination still needs its own actual-PG execution; earlier prototype receipts cannot establish that this integer-table profile worked.

## Storage and observations

The primary observer inherits `CaptureV3Session` and its segmented disk journal. It has no `_events` list or growing in-memory fact history. There are at most 512 retained unread-result identities. Crossing that limit adds a gap and blocks closure eligibility rather than growing the set. A discarded unread cursor remains represented by its retained identity; it does not become a completed result.

For a positive SELECT, read facts are emitted only after the original business row was actually delivered. Repeated EOF does not duplicate facts, and `fetchmany(0)` is not treated as EOF while the driver's result position still precedes its row count. UPDATE obtains PG18 OLD/NEW tokens in the same statement. A predecessor is metadata, not an invented SELECT read. Intermediate writes, including equal business values, remain distinct versions.

For an original command UPDATE without RETURNING, the proxy consumes only the added internal token result. It exposes the original no-result description/rownumber, rowcount and command tag. Its no-result fetch error is reconstructed from the pinned driver's class/message. Actual execute/fetch/transaction exceptions are rethrown by identity. Native UPDATE RETURNING value keeps the original business row prefix and hides the two token columns.

Command tokens are stored separately in `sources/records.jsonl`, bound to the actual statement and business rows event sequence. This source log is **not** an accepted extension to traceSchema3. It retains a bounded record at a time (64 KiB, 4096 nodes), with an 8 MiB/8192-record aggregate cap, sequence/hash chain and a sealed byte/hash index. Budget or I/O failure adds gaps; a valid byte prefix is not complete source proof. Reader verification iterates the file instead of building a full-log list. Hashes are integrity bindings, not source authentication.

The source log has no reopen/recovery writer API. Its temporary writer guard remains throughout data/index sync; after successful sync it is removed without a promise that guard deletion itself is durable. A surviving guard conservatively blocks reading. Post-close use invalidates the live observer and attempts an independent persistent marker. If every marker write fails, the live instance still refuses completeness; an independent process cannot discover later activity from unchanged bytes. Windows directory-sync behavior is the imported controlled API and is not physical directory durability or power-cut certification.

## Ledger and handoff

`stream_final_ledger(setup)` first requires no prior gaps, no unresolved transaction, no pending result identity and all business connections actually closed. It holds the business lock, verifies installation again, and reads the actual audit ledger through a server cursor in batches of 32. Every row is written to bounded source storage. More than 1024 rows, missing provenance or any failed query/sync remains incomplete. UUID order in the query is a stable presentation order, not a version or commit order.

`quiescence_report()` is an admission check. It does **not** implement a safe multi-window handoff. The next protocol must persist an intent linking the old raw journal/source hashes, a locked final snapshot and ledger, and a fresh epoch's actual initial snapshot. It must not release business workers between those facts; old wrappers must remain closed, and uncertain sealing/commit/marker state must block continuous-capture completeness. See the frozen future protocol in `contract-v1.json`. Dynamic window roots, ledger warmup filtering, archive-backed lineage and safe metadata pruning are still missing. Consequently neither 4096-key nor 60-second cost eligibility is claimed.

## Evidence and invocation

`contract-v1.json`, `test-plan.json` and `preregistration-before-implementation.json` preceded implementation. The initial 25 FS/mock cases passed; the original source bytes and receipt are under `history/first-25-unit/`. `review-amendment.json` records four additional cases and the new external-dependency binding requirement before the next run. The revised 29-case run then passed with zero skips; its original receipt is `evidence/unit-29.json`, and all declared local/external source bindings matched before and after that run. Python AST parsing also passed for all four executable draft files. These tests do not execute PostgreSQL or establish SQL proof. The actual-PG producer is prepared but was not executed when this README was written.

Use an existing pinned interpreter; do not run an install script:

```powershell
$env:MTW_JOURNAL_SCRATCH = 'D:/CodexScratch/MoonTxnWitness-v011-20261020/plain-v3-journal-draft-tests'
$env:TEMP = $env:MTW_JOURNAL_SCRATCH
$env:TMP = $env:MTW_JOURNAL_SCRATCH
$env:PYTHONDONTWRITEBYTECODE = '1'
& artifacts/pg-driver/Scripts/python.exe -B artifacts/plain-v3-journal-draft/test_profile.py
```

The test scratch parent must already exist. Each invocation creates a unique child and retains its receipt and FS fixtures. `sourceBindingsBefore/After` bind the actual code used in that invocation. A later source change does not revise a prior receipt.

For isolated CI or a parent-owned new PostgreSQL instance, set `MTW_PG_CONNECTION_FILE` to a controlled JSON connection dictionary or `MTW_PG_DSN`, then run:

```powershell
& artifacts/pg-driver/Scripts/python.exe -B artifacts/plain-v3-journal-draft/postgres.py --output NEW_OUTPUT_DIRECTORY
```

This producer does not start or stop a database. Its caller must own lifecycle cleanup and must never point it at another application's data. Seven cases cover original result/command surfaces, equal-value intermediate writes, rollback source retention, native RETURNING, real NOT NULL error identity, unsupported SQL and ledger overflow. Output directories cannot be overwritten. Missing driver/database returns `not-executed` with exit 3; observed failures preserve output and return nonzero. No benchmark duration, throughput or RSS result is generated.

Full C/A remains a later independent gate: equal original business input and output scope, plain A/provenance B/full capture C, column plus sidecar, all four planned contention/CRUD loads, and original raw latency/error/CPU/RSS/WAL/lock/durable-tail samples. This bounded positive-point draft cannot stand in for those measurements.
