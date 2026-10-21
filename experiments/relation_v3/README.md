# Controlled relational PG fixture

This is a controlled, fixed SQL workload; it
does not demonstrate arbitrary SQL instrumentation, ORM coverage or production
acceptance. The relational model consumes explicit semantic fixture facts.
`raw-sql.jsonl` separately retains every actual SQL request, complete delivered
result, column metadata, affected count, command acknowledgment and server error.
No raw unmapped statement is silently removed from an automatic capture claim.

`plan.json` freezes all eight input sets/schedules/expected outcomes before the
runner opens its database connection. Each scenario runs 20 times; each round
has its own fresh schema. There is no formal performance measurement.

The base relation has bigint PK/balance, boolean active, `text COLLATE "C"`
region, and an opaque server-generated UUID for every actual write. Initial
rows and all metadata are installed in one transaction, the full table is
snapshotted under ACCESS EXCLUSIVE, and workers begin only after COMMIT ACK.
The trusted deployment scope is this fresh owned database and its controlled
fixture writers; hashes do not authenticate that scope.

The BEFORE trigger assigns candidate tokens; AFTER records only actual effects
and advances state. Same-statement DELETE RETURNING calls the owned VOLATILE
helper for the unique immutable candidate matching its actual OLD token. A
delete produces a new tombstone, never the OLD live version. A reinsertion
returns its actual candidate predecessor. All candidate/state/ledger writes
roll back with the statement/transaction/savepoint. Actual committed ledger is
compared with all committed unreverted semantic writes, including intermediate
versions. No predecessor metadata becomes a fabricated SELECT.

Complete reads are SELECTs without LIMIT, with `fetchall()` completed before
publication. UPDATE/DELETE/INSERT RETURNING are affected rows, never complete
predicate reads. SQL text predicates explicitly use C collation; C/UTF8 implies
code point order for supported scalar text. U+0000 is rejected by the adapter
because PostgreSQL text cannot represent it. Int64 values are canonical decimal
strings in semantic JSON. Neither UUIDs nor reply time infer version ordering.

The SSI scenario records actual server 40001/40P01 aborts and a new retry
identity. It does not classify the execution abort as an isolation violation.
The known empty-query/membership and write-skew schedules have preregistered
relational serializability expectations. Model validation is a separate
offline receipt, not part of the actual database execution receipt.

Run `test_fixture.py` with the pinned psycopg environment for light unit checks.
`run_postgres.py --output NEW_DIRECTORY [--schema mtw_relation_v3_<12hex>]`
accepts `MTW_PG_CONNECTION_FILE` or `MTW_PG_DSN` (in that priority order).
Missing optional driver or explicit database configuration produces a retained
`database-receipt.json` with `notExecuted`, `actualDatabaseExecution:false`, and
exit code 3. Never interpret that result as a passed database test.
`local_postgres.py --python <pinned-python> --work-root <new-dedicated-D-root>`
creates/stops only its own PostgreSQL18.6 instance, retains logs/data/failures,
and never prints connection credentials. The local scheduler is Windows-only;
the direct producer works with an explicitly controlled PostgreSQL18.6 server.
Each output binds original producer
bytes before/after execution, the frozen plan, raw SQL and semantic facts.

`e2e.mjs RETAINED_DATABASE_OUTPUT NEW_OFFLINE_OUTPUT` validates every retained
file, SQL/predicate parameter binding, actual query rows, committed unreverted
effects and state, then checks the frozen independent Python oracle, current
SDK and self-contained replay capsules. It opens no database and writes a
separate `actualDatabaseExecution:false` model receipt. This source audit is
performed by the fixture author and is not independent human/GPT acceptance.

The promoted producer was executed in a separate new owned PostgreSQL18.6
instance on 2026-10-21: all 8 scenarios × 20 rounds passed database checks;
every round then passed raw binding checks, the independently authored Python
oracle, the current SDK, report verification and capsule replay. The
100 consistent and 60 violation results agree with the preregistered plan.
The 20 SSI rounds each retain one actual server abort and a fresh retry identity;
an execution abort itself is not an isolation classification or model violation.
The dedicated instance was stopped and its temporary drive alias removed.

Public evidence is in `verification/relation-v3/postgres-2026-10-21/`:
`database/` holds the 160 raw SQL logs, full SELECTs, semantic fixture facts,
installations and final actual effect/state observations; `model/` holds separate
offline results and 160 replay capsules. Database and offline receipts deliberately
distinguish actual database execution from read-only model verification. Each
raw SQL log encodes server integer values and counters as canonical decimal
strings, retaining PostgreSQL column type OIDs; boolean/text stay their JSON
types. This diagnostic file is not itself a v3 statement/rows transport.

The earlier ignored prototype and its initial PL/pgSQL installation syntax
failure remain unchanged in external task scratch. A small public failure receipt
binds the original failed log/raw evidence/source digests; the failed run never
reached model validation. Success is bound to the promoted source bytes and a
new owned run, rather than rewriting the old receipt's source path.

Seven lightweight producer tests passed, including absent optional driver or
database, canonical int64/Unicode projection and savepoint effect filtering.

Remaining gates: independent source audit, non-fixture automatic SQL coverage, public packaging,
independent clean-environment technical acceptance, and formal capture cost.
