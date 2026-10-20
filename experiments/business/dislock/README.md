# Frozen dislock lease component integration

This experiment executes an existing upstream component's real lease helpers,
with controlled data and an explicit capture profile. It is not a new lock
implementation, a claim of an upstream defect, a production deployment, full
application instrumentation, full v0.1.7 acceptance or organizer approval.

## Frozen upstream and license

Upstream: [Actticus/dislock](https://github.com/Actticus/dislock), fixed commit
[`f9946f07159054433d9071c3805e41223cb47856`](https://github.com/Actticus/dislock/commit/f9946f07159054433d9071c3805e41223cb47856).
It is an existing PostgreSQL-backed cron/lease locking component, not a general
database tutorial. The upstream code is MIT licensed; the full original license
is retained in [upstream/source/LICENSE](upstream/source/LICENSE).

The retained fixed tar archive is 56,046 bytes, SHA-256:

```text
78f9be44f0bf0095b64e8c767f933d155d85092c8328afdf5b9749e97c9922d0
```

[upstream/lock.json](upstream/lock.json) records its URL/commit, archive digest
and 11 untouched package/document/license files' individual digests. The archive
is retained alongside the extracted sources. `fetch_upstream.py` only downloads
and extracts a bounded selection into a new directory owned by this experiment;
it never runs an upstream installer/script. `business.verify_sources()` compares
the extracted files directly against the archive with the fixed embedded digest,
so changing both a file and its manifest entry does not pass verification.
`load_upstream()` imports the original package into a dedicated namespace,
without silently selecting an installed version. No original source is patched.

The executed slice needs the already optional psycopg 3 driver and Python's
standard library. Upstream lists croniter as a project dependency, but this
slice never imports/runs its CLI where croniter is used. It does not start a
subprocess, scheduler, heartbeat thread or background cleanup service.

## Actual business path and SQL boundary

The original schema is one text primary key, text owner and timestamp expiry:

```sql
CREATE TABLE key_value (
    key text PRIMARY KEY,
    value text NOT NULL,
    expire_at timestamptz NOT NULL
);
```

The fixture qualifies this same shape into a new caller-owned
`mtw_provenance_*` schema. Before capture starts it calls the **original**
`core.try_acquire_run_lock()` and commits to create the declared existing leases.
Capture then installs/checks its provenance objects and obtains a locked actual
initial snapshot using the [existing profile contract](../../provenance/CAPTURE_PROFILE.md).
It does not invent an initial version or skip the user-trigger validator.

`LeaseClient.read_current()` delegates query generation to the untouched
`_queries.read_current_query()` and returns its `(expire_at, owner)` tuple.
`LeaseClient.renew()` delegates to the untouched `core.renew_lease()` function:
it opens a cursor, executes the original conditional update, consumes the
original one-column RETURNING row and returns the upstream True/False result.
Commit/rollback remain the caller's responsibility, matching the helper API.

The reviewed SQL is taken directly from those original Composed query builders
with `as_string(setup)`. The observation profile changes only the known literal
projection positions: one version token appended to the SELECT, and
`OLD.version::text, NEW.version::text` appended after the original UPDATE
RETURNING column. Unit checks reverse those edits and require byte-identical
original SQL. This is not regex inference or arbitrary SQL parsing.

The original owner predicate, key predicate, parameter positions, database
`NOW()` expression, interval calculation, semicolons and business RETURNING are
preserved. Root's `ReturningPointProfile` restores two business read columns and
one business update-returning column; hidden metadata is not a business result.
Successful updates supply an actual OLD-version read and NEW-version write
from that same statement. Failed owner predicates preserve False/empty result,
emit no fabricated operation, and produce a coverage gap because this profile
does not know the version read by an unsuccessful predicate.

Only synchronous, fixed existing keys and standard tuple cursors are covered.
The full acquire/upsert path runs only as initialization before capture; first
acquisition, absence, expiry cleanup, CLI, heartbeat, reconnect, full LeaseLock
and multithreaded/multi-process operation are not covered by this slice.
`exclusive_writers=True`, no DDL/trigger disabling and all relevant captured
writers remain explicit controlled-window assumptions.

## Usage and verification

Use the fixed existing schema/key set and a dedicated idle autocommit setup
connection. For example, after creating leases through the upstream API:

```python
from business import make_capture

capture, client = make_capture(setup, "mtw_provenance_owned", keys=existing_keys,
                               exclusive_writers=True)
capture.initialize(setup)
with capture.connect(private_connection_string) as conn:
    previous = client.read_current(conn, existing_keys[0])
    renewed = client.renew(conn, existing_keys[0], 120.5, previous[1])
capture.close()
trace = capture.document()
```

Database-free checks execute the real frozen helper against fake cursors; they
do not contact PostgreSQL or prove actual database behavior:

```text
python experiments/business/dislock/test_business.py
```

Actual PostgreSQL 18 verification uses a NEW explicit schema/output directory:

```text
node experiments/business/dislock/e2e.mjs --schema mtw_provenance_dislock_run1 --output artifacts/dislock-business-run1
```

Configure `MTW_PG_CONNECTION_FILE` to a private JSON connection file, or set
`MTW_PG_DSN`. `MTW_PYTHON` selects the Python environment with psycopg. The
existing SDK must already be built. The fixture never adopts an existing schema;
only its newly created controlled schema is removed, unless `--keep-schema` is
specified. Credentials and driver error messages are excluded from receipts.

Seven prepared traces cover:

1. The real renewal helper twice with identical TTL in one transaction, its own
   intermediate reads, distinct tokens and identical repeated business expiry.
2. The real renewal followed by rollback, restoring original owner/expiry and
   removing aborted token metadata from committed audit state.
3. The original owner guard failing, returning False without a write and with
   history:null after coverage normalization.
4. A separate same-transaction plain-table comparison of original and observed
   query results, business description, rowcount/status/position, remaining
   fetches, and closed-cursor errors. Both updates share the server's NOW clock;
   the independent verifier checks expiry minus transaction timestamp equals
   TTL. Extra mirror/verifier SQL deliberately makes this comparison trace
   incomplete. No cross-transaction absolute datetime equality is claimed and
   verifier facts are not inserted into the normalized history.
5. An adversarial unconsumed original RETURNING result, which must remain a gap.
6. A real NOT NULL failure from the unchanged SQL, rollback, no invented failed
   write and an unchanged business row.
7. A real two-connection READ COMMITTED row wait. Connection two first completes
   a separate read transaction; connection one then renews without committing.
   A thread uses the original renewal helper on connection two. Independent
   `pg_blocking_pids` and lock-wait observations must identify connection one as
   its blocker before the controller releases the first commit. Only then may
   the second renewal return; its actual UPDATE OLD token must be the first
   writer's NEW token, not the initial or earlier SELECT token. The controller
   checks that fact before allowing the second commit. A bounded protocol log
   retains polling observations, errors/timeouts and thread/connection cleanup.
   Poll delays are pacing, not evidence of blocking. Both connections' RC driver
   settings are assigned while idle before wrapping; no hidden business read or
   redundant explicit BEGIN is introduced.

Python writes `business-database.json` as driver-passed/core-pending, plus actual
traces. Node requires the declared coverage statuses, exports no history on
gaps, analyzes complete histories and creates/replays capsules. Only its final
`business-receipt.json` says passed. The expected complete traces are consistent;
this test does not manufacture an upstream anomaly or claim one was discovered.
Receipts include fixed upstream provenance, adapter/profile/core/build digests
and scope limitations. Each scenario binds its exact trace/coverage files with
SHA-256 and byte counts; complete scenarios additionally bind separate projected
history, report and capsule files. The RC protocol log is also bound. Projection
version is `column-old-new-register-v0.1.2-experimental`. These bindings detect
artifact/receipt mismatches; they neither authenticate real-world collection nor
claim the later evidence-v3 gate is complete. Failed/partial runs retain their own failure files and
trace prefixes; old receipts are never overwritten.

Actual database execution and any C/A performance measurement remain pending
when this integration is first introduced. CPU/RSS, contended workers,
thread/reconnect/cleanup coverage, deployment, historical defect replay and
external adoption are separate gates. This bounded component test cannot mark
the entire v0.1.1 or v0.1.7 roadmap complete.

Sources: fixed upstream [queries](https://github.com/Actticus/dislock/blob/f9946f07159054433d9071c3805e41223cb47856/dislock/_queries.py#L57),
[real renewal helper](https://github.com/Actticus/dislock/blob/f9946f07159054433d9071c3805e41223cb47856/dislock/core.py#L223),
[MIT license](https://github.com/Actticus/dislock/blob/f9946f07159054433d9071c3805e41223cb47856/LICENSE),
[PostgreSQL 18 OLD/NEW RETURNING](https://www.postgresql.org/docs/18/dml-returning.html).

## First actual controlled result (2026-10-20)

Windows PostgreSQL 18.6 / psycopg 3.3.6 passed all seven scenarios, four complete histories and four capsule replays. The result is retained at `verification/business/dislock/run-c65e07733d4e4c12a84a420f7e79f12e/business-receipt.json`. Its independent audit verified 27 file bindings, the original source archive, replay inputs/reports and the real lock-wait protocol. Three incomplete traces exported no history. The owned instance was stopped and business rows were preserved on uninstall. This controlled component slice does not complete whole-application, C/A cost or human acceptance. Independent Linux CI for this new source is recorded separately when available.
