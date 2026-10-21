# Two quiescent point epochs, experimental R1

This is an ignored, opt-in candidate. It does not modify the stable collector,
the frozen R2 point profile, the MoonBit core, or any old evidence. It is limited
to at most two epochs over the same 1..64 existing text keys and integer values.
The new `contract-r1.json` is the implementation contract; `execution-plan.json`
preserves the preregistration and the additions made before each new execution.

The implementation preserves all raw SQL and source records. It has no SQL
dependency-graph proof and always returns `sourceClosureVerified=false`,
`coreProofImplemented=false`, and `formalEligible=false`. `prune()` always
refuses and deletes nothing. Two epochs are not 4096-key or 60-second C/A
acceptance, automatic SQL coverage, archive GC, or a production release.

## Actual versus prepared verification

The first 40-case Windows small-file/mock run and the next 45-case run passed,
with zero skips and identical before/after runtime source bytes. Their source
snapshots and original receipts are in `history/first-40-passed/` and
`history/second-45-passed/`. The final suite contains 47 cases, adding bounded
tree traversal and bounded directory validation. Its actual result and exact
source hashes are recorded separately in `unit-test-receipt.json`.

These tests exercise real files, file sync requests, SQLite, actual native lock
competition, real child-process crashes, and real threads. All database
responses in them are explicitly synthetic. The production installer and
catalog verifier are monkeypatched only inside the test fixture. This is not
actual PostgreSQL execution or independent acceptance.

`postgres_epoch.py` is prepared for four new controlled PostgreSQL 18.6 cases:

1. Two epochs, repeated equal-value updates, own intermediate read, distinct
   real server tokens, and token continuity into the next actual snapshot.
2. Rolled-back and savepoint-reverted writes retained in raw events but absent
   from the actual final audit ledger.
3. Unknown SQL runs unchanged and creates a coverage gap; no complete handoff.
4. A deliberately discarded actual setup COMMIT response retains failure
   authority. This is an injected response-loss test, not a real network fault.

No local PostgreSQL, Node, JVM, compiler, or formal performance run was executed
for this candidate. Actual PostgreSQL results must be recorded in a new output
directory by the separate isolated CI; they must not be filled from mock tests.

## Lifecycle

```python
from epoch_coordinator import EpochCoordinator

chain = EpochCoordinator.create(
    new_store, dedicated_idle_autocommit_setup,
    schema="mtw_provenance_my_owned_fixture", keys=("k", "other"),
    exclusive_writers=True,
)
old = chain.current
business = old.wrap(new_raw_connection)
business.execute(old.profile.write_sql, (5, "k"))
assert business.execute(old.profile.read_sql, ("k",)).fetchone() == (5,)
business.commit()
business.close()

# Stop and join all business workers. Close every wrapper through the observer.
barrier = chain.quiesce(expected_generation=0)
new = chain.handoff(dedicated_idle_autocommit_setup,
                    caller=barrier, expected_generation=0)
# Only new, freshly wrapped connections may now be used.

# Stop workers and close all new wrappers before finalization too.
last_barrier = chain.quiesce(expected_generation=1)
result = chain.finish(dedicated_idle_autocommit_setup,
                      caller=last_barrier, expected_generation=1)
```

Only the three existing R2 SQL forms are rewritten: its generated point SELECT,
generated point UPDATE, and that UPDATE with its original one-column RETURNING.
No tokens are reinstalled or renumbered at handoff. Business result delivery and
EOF remain on the original business cursor lifecycle; hidden write metadata is
the R2 same-statement PG18 OLD/NEW mechanism. Original business exceptions are
re-raised, and original SQL still runs on unsupported paths with explicit gaps.

The strong live registry prevents a dropped wrapper from disappearing through
garbage collection. It is capped at 128 identities at once. A close acknowledgement
means the original driver's `close()` returned and `raw.closed` became true; it
is not a PostgreSQL COMMIT-equivalent server acknowledgement. Externally closing
the raw connection does not count. Active/unknown transactions, discarded unread
results, previous gaps, and missing persisted close acknowledgements block the
transition before a new intent or owner marker is written.

`quiesce()` stops wrapper admission. Any subsequent execute/fetch/commit/rollback
activity invalidates that stopped-worker barrier. Pure repeated connection close
is cleanup and does not invalidate a normally completed chain. Raw connection
bypass, external writers, DDL, trigger disabling and metadata changes are excluded
by explicit deployment assumptions; initial/final observations do not prove no
administrator changed the database in between.

## Boundary and commit protocol

One permanent `coordination.lock` inode carries the native OS mutex. It is never
deleted or replaced. All cooperating transitions and readers acquire it. The
process-local lock serializes `quiesce()` and transition calls; after native lock
acquisition, a fresh preflight checks the caller token, generation, observer,
manifest, and admissions before writing new authority. A stale competing thread
does not poison or mutate the valid transition.

An owner-bound `operation.lock` and durable `intent.json` protect the boundary.
The dedicated setup connection executes one BEGIN and an actual backend PID /
opaque transaction identity query, then locks business, installation, audit, and
state tables in ACCESS EXCLUSIVE mode. The setup records fixed catalog queries,
final snapshot, bounded server-cursor audit batches, a second catalog inspection,
and next snapshot under that same transaction. The two snapshots must be equal.
The identity is never used to order commits.

Only an actual COMMIT tag plus idle status permits old ledger completion, old
journal/source sealing, and new consistent snapshot publication. A COMMIT error,
missing response or ROLLBACK tag is incomplete even if a later rollback is idle.
The old and new snapshot source bindings retain exact SHA256/byte counts. A new
observer replays the fixed verifier against recorded SQL, parameters, native rows
and PGresult status; it does not trust a generic `verified` flag. The final chain
reader repeats this replay and checks generation, directory count, boundary
footers, snapshot token continuity, hashes, and late-use markers.

The owner marker remains present through manifest publication, intent cleanup,
and the final protected synchronization request. It is removed only after that
commit point. Its deletion has no later persistence promise, and a reappearing
owner remains a conservative recovery refusal. A failure before or at this point
retains the owner and poisons the live coordinator, including when the diagnostic
marker cannot be written. A confirmed post-data-commit native release error has
best-effort persistent reporting and unconditional live poison; if every later
write fails, another process cannot universally detect that coordination error.
This limitation does not relax source/intent/manifest/sync failure handling.

Linux directory fsync requests and the existing Windows controlled no-op directory
API are distinct. Neither these tests nor the protocol certify disk power-loss
durability. File-content fsync requests and actual platform calls are preserved.

## Bounds and source retention

Snapshots use an explicit SQL LIMIT 65 and batches of 32, rejecting incomplete
or excess scopes. Audit export uses a real server cursor and batches of 32,
rejecting more than 1024 cumulative audit rows without writing a complete footer.
Each side source has an 8 MiB/8192-record limit; individual records have 64 KiB /
4096-node limits. Native control encoding has shared approximate 60,000-byte /
4096-node/depth-32 limits. Raw catalog queries retain the original controlled
verifier and its driver PGresult buffering; this is not a hostile-database
query-memory firewall.

Metadata reads use bounded file descriptors and before/after metadata checks,
then a separately opened path handle compared with the same fstat API. This
avoids treating the Windows path/fd ctime API difference as same-file evidence.
Unknown identity, a same-size rewrite, extra children, or any exception refuses.
Hash traversal stops after 256 nodes, 128 files, 16 MiB per file and 32 MiB per
tree. It does not sort an unbounded directory listing first.

`references.sqlite3` is a rebuildable disk cache of close acknowledgements,
raw versions/reads/outcomes and cross-epoch boundary token origins. It is not
the authoritative source or a proven SQL graph. Original journals and side
sources stay intact, including aborted/reverted writes and intermediate versions.
Metadata predecessors never generate synthetic SELECT reads. No source is
deleted, and original R2/archive candidates are not modified.

Crash `recover(owner=exact_owner)` is deliberately inspect-only. It keeps owner,
intent and raw evidence and cannot resume capture or clear a failed operation.
Automatic recovery, extra epochs, source-graph closure, archive-backed pruning,
database metadata GC, CRUD/absence, ORM/async and formal full-capture cost are
separate unfinished gates.

## Isolated commands

Use the frozen repository-relative layout; `epoch_sources.py` checks the frozen
R2 profile digest. Restore the dependency paths listed in `candidate-index.json`.
Use Python 3.12.5 and the hash-pinned psycopg 3.3.6 requirements from
`examples/postgres-requirements.txt`. Run one small suite at a time:

```powershell
$env:MTW_JOURNAL_SCRATCH = '<new-owned-scratch>'
& artifacts/pg-driver/Scripts/python.exe -B artifacts/plain-v3-epoch-r1/test_epoch.py
```

For the later isolated actual-PG fixture, supply `MTW_PG_CONNECTION_FILE` or
`MTW_PG_DSN` for a disposable, explicitly owned PostgreSQL 18.6 database:

```powershell
& artifacts/pg-driver/Scripts/python.exe -B artifacts/plain-v3-epoch-r1/postgres_epoch.py `
  --output '<new-nonexistent-output>' --schema mtw_provenance_epoch_owned_test
```

The producer does not start a server, install external code, delete old outputs
or print connection credentials. It preserves source before/after bindings and
per-case raw files. The owning CI must stop only its own database in `finally`.
The fixture is controlled generated SQL, not an existing application's adoption.
