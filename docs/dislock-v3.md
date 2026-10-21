# dislock v3 collector and full synchronous lifecycle (development)

This experiment connects the frozen MIT-licensed
`Actticus/dislock@f9946f07159054433d9071c3805e41223cb47856` component to the
independent bounded [v3 journal](capture-journal-v3.md). Original upstream files
are verified against the pinned archive and are not edited. The harness injects
a connection facade only into that already isolated module's driver reference;
it does not replace the process-global psycopg driver.

This is an owned PostgreSQL experiment, not production adoption, a discovered
upstream bug, complete SQL instrumentation, or proof of lease mutual exclusion.
It is also distinct from the earlier positive-row read/renew slice.

## Actual implementation

- `integrations/python/moontxnwitness_capture/capture_v3.py` records protocol
  observations directly to segmented disk storage. It retains no `_events`
  history. It automatically identifies transactions, reconnects/retries and
  savepoint instances; equal savepoint names do not reuse instance identities.
- `experiments/business/dislock/v3_registry.py` builds the exact SQL profiles
  from the pinned query builders. `v3_registry.json` freezes their template
  representation with explicit schema/table/version/helper placeholders.
- `v3_install.py` performs an explicit opt-in provenance migration in a fresh
  `mtw_provenance_*` schema and verifies its objects and initial snapshot under
  one lock window.
- `v3_postgres.py` exercises the original `ScheduleLock`, `LeaseLock`, heartbeat,
  ownership-loss, reconnect and cleanup methods. It also compares real aborted
  COMMIT behavior with the unwrapped driver.
- `v3_commit_postgres.py` separately targets an actual commit-time `40001`
  response, diagnostic provenance, exception identity and subsequent idle
  rollback. It does not map that fixture's SQL into register facts.

The generic protocol wrapper is synchronous. It supports the connection/cursor
surfaces needed by these original methods, including cursor contexts, iteration,
`fetchone/many/all`, `arraysize`, `description`, `rowcount`, `rownumber`,
`statusmessage`, commit, rollback and close. Named/custom/withhold cursors,
pipeline, TPC, autocommit, cursor streaming/COPY/executemany and unobserved
transaction context APIs carry explicit coverage limitations. The original
business exceptions and returns are preserved. Async dislock, arbitrary SQL,
dynamic-key migrations and command-subprocess lifecycle are separate gates.

## Supported table and deployment

The supported business table is the actual upstream shape:

```sql
CREATE TABLE key_value (
  key text PRIMARY KEY,
  value text NOT NULL,
  expire_at timestamptz NOT NULL
);
```

The migration requires PostgreSQL 18, one native text primary key, a declared
domain of 1–128 bounded text keys, and no existing keys outside that domain.
It rejects RLS, inheritance, foreign keys, rules, CHECK/EXCLUDE, generated/custom
types, expression/partial/custom-operator indexes, nondeterministic collations,
unregistered indexes or extra user triggers. The migration adds a private UUID
version column and controlled metadata tables/functions/triggers. It is not a
zero-change production observer: unknown-key writes, DELETE and primary-key
mutation are outside its installed domain and may be rejected by its trigger.
Unknown SQL is passed to the driver as written and has no verified semantic
mapping; this does not mean installation leaves arbitrary out-of-domain SQL
behavior unchanged.

The controlled deployment must route every writer through the observer, forbid
DDL/trigger disabling/replication-role changes and stop workers before sealing.
Initialization and final verification check object identities and definitions;
they do not continuously defend against a database administrator. Scope and
source closure are explicit deployment facts, not authenticated by hashes.

## UPSERT candidate versus actual effect

PostgreSQL can run `BEFORE INSERT` for an `INSERT ... ON CONFLICT` that ultimately
updates another row or returns zero rows. Advancing version state there would
invent writes on failed guards. This migration separates the two:

1. `BEFORE INSERT/UPDATE` mints a unique opaque token and records an immutable
   **candidate** with its exact predecessor. It does not advance current state.
2. Only `AFTER` an actual INSERT/UPDATE advances current state and appends the
   **actual-effect ledger**. A failed guard leaves at most an unused candidate.
3. The original `RETURNING` prefix is extended with actual PG18 OLD/NEW tokens
   and a same-statement helper for the unique NEW-token candidate predecessor.
4. At the closed window, final committed effects are cross-checked against the
   actual-effect ledger. Candidate-only rows are never modeled as writes.

For a conflicting successful UPSERT, the preliminary INSERT candidate is unused
and the actual UPDATE has its own new token and actual OLD predecessor. These
tokens do not encode an ordering. Savepoint-reverted and aborted metadata writes
roll back with PostgreSQL; their earlier delivered observations remain in the
immutable journal. The final ledger contains all surviving committed effects,
including intermediate same-transaction versions, rather than only final rows.

## Fixed SQL profiles and evidence

There are **six** original SQL families:

| Mapping ID | Original behavior | Actual server row layout |
| --- | --- | --- |
| `dislock.acquire-schedule/1` | Explicit-expiry UPSERT, expired-row guard | key, newExpire, oldToken, newToken, oldOwner, oldExpire, serverNow, actualPredecessor, action |
| `dislock.acquire-run/1` | NOW + TTL UPSERT, expired-row guard | Same layout |
| `dislock.read-current/1` | Point SELECT expiry + owner | expireAt, owner, token |
| `dislock.renew/1` | Owner-guarded TTL UPDATE | newExpire, oldToken, newToken, oldOwner, oldExpire, serverNow |
| `dislock.expire/1` | Owner-guarded UPDATE to NOW | key, oldToken, newToken, oldOwner, oldExpire, serverNow |
| `dislock.server-now/1` | Original SELECT NOW() | serverNow |

Only projections are extended. WHERE clauses, owner comparisons, ON CONFLICT,
NOW(), interval multiplication, parameter ordering and original RETURNING
prefixes are retained. Hidden columns are removed from business rows and
description. The wrapper does not prefetch application result rows. Actual
default-client cursor count/position can confirm that the delivered prefix
exhausted the result; repeated EOF does not manufacture another result or false
guard. Result chunks have a cumulative statement ordinal for source references.

`statement.sql` is original SQL, `executedSql` is the actual rewritten SQL and
`mappingId` identifies a declared fixed profile. `rows.rows` contains business
rows actually delivered; `serverRows` preserves the corresponding hidden source
columns. `rows.columns` uses `{name,typeCode}` for the business prefix.
`read/write/condition` reference the original statement sequence and mapping ID.
Predecessors produce write-source facts, never fabricated SELECT reads.

A zero-row UPSERT/owner UPDATE, or absent point SELECT, lacks a same-statement
source in this slice. It records the negative condition without inventing
`sourceVersion`; a later SELECT or final ledger cannot retroactively supply that
guard's read source. These cases must remain inconclusive until independently
proved. Unknown mappings or predicates remain incomplete. A `mappingId`, hash,
registered text or collector declaration alone does not waive those gaps.

Timestamps are actual returned aware datetimes, encoded as
`{captureType:"datetime",value:str(datetime)}` with offset/microseconds retained.
NOW is the actual server transaction constant returned in that statement.
No client wall time, elapsed time, sequence number or UUID order substitutes for
it. Naive timestamps or unsupported interval-number semantics require a gap.

The root `sqlProfiles` declaration binds the schema/table/known keys and retains:

- `initialState` with exact key/version/present/owner/expireAt and snapshot tokens.
- Metadata nonce, server version, table OID and actual marker row.
- Both trigger/function OIDs, definitions, flags/arguments, raw function source,
  source SHA and the actual nine-column function catalog row.
- Business and owned-table catalog rows, constraints, complete user-trigger OID
  sets, index counts and explicit unsafe-feature counts.
- Successful initialization ACK sequence: BEGIN → ACCESS EXCLUSIVE lock →
  catalog verification → locked snapshot → COMMIT.
- Final actual-effect ledger, never treated as a model SELECT.

The core must independently check these facts and exact templates. This wire
contains no self-declared `verified:true` escape hatch.

## COMMIT responses and diagnostics

The commit observer temporarily wraps only a pinned psycopg **3.3.6** connection
instance's original `_exec_command` generator. It yields from the original
without extra SQL, observes the actual returned COMMIT response tag and restores
the previous instance method in `finally`. Concurrent/repeated unexpected
commands or unsupported pipeline/TPC modes create coverage gaps.

`commit_request` alone is not success. A real `ROLLBACK` response is tied to its
request in `rollback_ok.commitResponse`. A server `40001`/`40P01` abort additionally
requires a real `psycopg.Error.pgresult`, matching diagnostic SQLSTATE and IDLE
status. A client-constructed SQLSTATE exception is not that evidence. A lost
response remains unknown; later idle rollback, retry, write or reconnect cannot
resolve its original outcome. Reconnect/retry uses fresh identities.

Strict `session.export()` requires a complete journal. Separate
`export_diagnostic()` streams only integrity-valid partial evidence, retains all
reader/index gaps and adds a mandatory diagnostic gap. It always returns
`complete:false`; it does not weaken strict export. Both use new atomic
no-overwrite output names and bounded 8 MiB envelopes. Diagnostic budget refusal
retains a separate reason receipt and never silently truncates the raw journal.

Sealing ends the observed window. If an existing wrapper later executes, fetches,
commits or rolls back, or its facade opens another connection, the business
operation still runs but that observer is permanently invalidated. Strict and
diagnostic exports from that session are refused. A separate
`journal-invalidated.json` marker makes fresh readers, reopening and archiving
refuse completeness without changing the sealed segments, index or cache.
Marker inspection includes dangling links and fails closed on inspection errors.
Pure cursor/connection cleanup and repeated `close()` do not invalidate a window.
If every marker write fails, the live instance still refuses export; a new process
cannot infer later activity from unchanged disk bytes. Previously exported
evidence describes only its original ended window, never subsequent activity.

## Verification state

The current fake-driver protocol suite passes **35 tests**. These are simulated
driver tests, not database evidence. The journal suite has **64 tests: 62 passed
and two Windows symlink-permission skips** after its required wire additions and
post-close invalidation fixes.

The first actual seven-scenario PG18 run completed its SQL/lifecycle assertions
but its six mapped traces were rejected by the core because the producer used
`type` instead of agreed `typeCode`. That producer bug was corrected and an exact
column-metadata assertion added; the original raw/model failure receipts were
retained. The corrected collector subsequently passed a fresh
[seven-case real database run](../verification/business/dislock/v3-647afacfcbe14586b46714bac34c8f30/database-receipt.json).
A separate [real commit-time 40001 run](../verification/business/dislock/v3-commit-50d53504847d42f6ba5009b7c3b3ec91/commit-receipt.json)
confirmed a real PGresult and matching diagnostic/IDLE state, original exception
identity and zero added events from a later idle rollback. Those receipts bind
the code before the post-close invalidation fix; the changed collector/journal
must receive a new combined database run before their bytes are claimed tested.
Source receipts bind collector, journal, bounded encoder, loader, fixed registry,
installer and frozen upstream bytes before and after each run and reject drift.

The changed bytes subsequently passed the [combined seven-scenario run](../verification/business/dislock/v3-db5f87c5620c4f8e955172340023482c/database-receipt.json)
and [default/explicit-policy semantic replay](../verification/business/dislock/v3-db5f87c5620c4f8e955172340023482c/model-receipt.json).
The explicit fixed SQL policy establishes consistency for schedule/server-clock,
acquire/heartbeat/cleanup and body-exception cleanup. Busy, ownership-lost,
reconnect and the failed unmapped-statement case remain inconclusive.
The [fresh commit-time 40001 run](../verification/business/dislock/v3-commit-fb56573a35ef415b872509cf1004ee90/commit-receipt.json)
and [semantic replay](../verification/business/dislock/v3-commit-fb56573a35ef415b872509cf1004ee90/model-receipt.json)
also passed. These are controlled functional tests, not a formal performance run.

The seven-case entry point is:

```text
python -B experiments/business/dislock/v3_postgres.py --schema mtw_provenance_dislock_v3_RUN --output NEW_DIRECTORY
python -B experiments/business/dislock/v3_commit_postgres.py --schema mtw_provenance_dislock_commit_RUN --output ANOTHER_NEW_DIRECTORY
```

Supply the owned `MTW_PG_CONNECTION_FILE`; no server is started by these scripts.
Use D-drive scratch for large journals/clusters and set `MTW_JOURNAL_SCRATCH`.
The harness retains original methods' actual SQL/results, business exception
identity, worker shutdown and reconnect evidence. It separately records raw
capture, storage status, initialization/catalog facts and final effect ledger.

Full joint acceptance, validated fixed SQL/condition proofs, real network loss
of a COMMIT acknowledgement, 30 registered application seeds, independent clean
installation, full C/A overhead measurement, automatic source-closed windows,
safe retention and public release remain separate completion gates. No missing
gate is satisfied by a fake-driver test, final business value or captured hash.
