# v3 segmented capture journal (development)

`integrations/python/moontxnwitness_capture/journal_v3.py` is a Python standard
library storage component for the [v3 event contract](v3-contract.md). It is
independent of the stable v1/v2 in-memory capture adapter. It does not yet wrap
psycopg, prove SQL predicate semantics, or establish a database deployment's
exclusive-writer scope. Its IO tests are not PostgreSQL or application tests.

## Durable storage and bounds

```python
from moontxnwitness_capture.journal_v3 import SegmentedJournal, JournalReader

journal = SegmentedJournal("new-journal-directory")
journal.append({"seq": 1, "time": 0, "kind": "snapshot",
                "initial": {"lease:key": "initial-token"}, "consistent": True})
# Append real observed lifecycle/statement/row facts, using the v3 contract.
journal.flush()  # waits for the data and bound index to be synchronized
result = journal.close(source_closed=True)
assert result.complete
for event in JournalReader("new-journal-directory").iter_events():
    consume(event)
```

`append()` returns `AppendResult(accepted, durable_seq, blocked_ns, gap)`.
Acceptance means that the bounded writer queue owns a copied record; it does not
mean that the record is durable. `flush()`, `checkpoint()` and `close()` wait for
the relevant tail and its index. `append()` rejects invalid/budget-exhausted
records with an explicit gap rather than silently dropping them. The caller must
propagate any rejection to its coverage result and must not mutate an input
event concurrently with `append()`.

| Resource | Default / bound |
| --- | --- |
| Encoded queue, including the in-flight record and reserved encoding slot | 4 MiB |
| One encoded NDJSON record, including newline | 512 KiB; configurable, hard maximum 4 MiB |
| One bounded JSON copy | 65,536 nodes, depth 16, aggregate record byte budget |
| Segment | 16 MiB; a record never spans two segments |
| Sync trigger | 256 KiB pending bytes or 100 ms dirty interval |
| Raw NDJSON bytes in one journal | 1 GiB; configurable, explicit rejection on exhaustion |
| Segment index | 4,096 segments; at most 2 MiB index JSON |
| In-memory active transactions / pending COMMIT requests | At most 4,096 bounded identities; index JSON limit also applies |
| Caller-provided active/read/version reference labels | At most 4,096 per category, 256 characters each, 256 KiB aggregate |
| Coverage gaps | 64 distinct gaps plus one truncation gap |
| Historical transaction identities | SQLite disk index, not an in-memory history set |
| Reader disk identity index | At most 2 GiB; rebuilt temporary disk index used for comparison |

The queue limit is an encoded-buffer budget, not a claim about total process RSS.
The temporary container copy, JSON encoder, current read record, bounded index,
active-reference metadata, SQLite page cache and interpreter also use memory.
No complete event-history list is retained by the writer or reader. Waiting
appenders do not each pre-encode another record. `stats` reports actual queue
high water, backpressure count/nanoseconds, accepted/durable counts, fsync count
and bytes written. Backpressure time covers queue-capacity waiting, not all IO or
CPU time. The timed trigger is a writer scheduling target: slow storage or thread
scheduling can delay an fsync, and successful explicit sync remains the durability
boundary.

Events use contiguous positive safe-integer `seq`, nonnegative safe-integer
nondecreasing `time`, and the v3 kind vocabulary. The storage reader does not
replace the stricter MoonBit event/predicate/savepoint validator. Generic storage
completeness must not be described as a database consistency verdict.

## Indexes, sync and failure

The directory contains:

- `segment-000001.jsonl`, etc.: canonical UTF-8 NDJSON containing original events.
- `journal-index.json`: SHA-256 self-check, segment byte sizes/hashes, first/last
  sequence and counts, durable tail/time, limits, lifecycle state and coverage.
- `transactions.sqlite3`: rebuildable uniqueness index of `tx` and its observed
  begin sequence. SQLite uses `synchronous=FULL` and `journal_mode=DELETE`; a
  transaction-index commit precedes acknowledgement of the corresponding index.
- `writer.lock` while the owned writer is live, and best-effort
  `journal-failure.json` after a storage failure.
- `journal-invalidated.json` if the closed observer later sees unrecorded activity.
  It is separate from the sealed data/index/cache and does not rewrite them.

Each sync flushes and `fsync`s raw data, commits the SQLite cache and flushes and
`fsync`s a new index before atomically replacing its name. Final sealing occurs
after the data/cache handles close successfully. On POSIX the directory is also
`fsync`ed. Python's Windows standard library does not provide this directory
operation; the index explicitly records that limitation. This implementation
does not claim power-loss durability beyond the operating system/filesystem's
flush, replacement and persistence guarantees.

The SQLite cache is not trusted as evidence: the reader streams raw segments,
rebuilds transaction identities into a separate temporary SQLite file, and
compares every stored identity/sequence row. It also independently recomputes
lifecycle state. A non-DELETE SQLite header/mode or any WAL/SHM/rollback-journal
sidecar is refused; required rows cannot hide in an unarchived sidecar.
The raw segments and their hash/size/sequence bindings remain
authoritative. Set `MTW_JOURNAL_SCRATCH` to an existing disk directory for this
temporary verification work, particularly for large captures.

A failed write, failed index replacement/sync, missing/duplicate sequence,
missing segment, partial last line, changed bytes, unexpected segment, altered
index, corrupted/missing cache, unresolved transaction or absent source closure
cannot produce a complete result. Every writer error retains the existing
writer lock, even if a sealed-index replacement succeeded just before a sync
failure and the disk also refused the failure marker. Readers and reopening
therefore refuse completeness without relying on an additional error write.
No hardware-independent audit authentication or recovery guarantee is asserted.
Preserve the directory after a failure. There is no automatic crash recovery.

`JournalReader.verify().as_dict()` reports `valid` separately from `complete`.
For example, a sealed journal with an explicit skipped-sequence gap can be valid
stored evidence while remaining incomplete. The result always records
`actualDatabaseExecution: false`: it is a storage verification receipt.

`iter_events()` first verifies all bindings, then uses bounded per-segment
verification and streaming iteration. A concurrent mutation can still raise
during iteration. A consumer must exhaust the iterator successfully before
claiming that it processed a complete history. Atomic export below enforces that
rule before publishing its final filename. Iteration also rechecks newly
appearing writer/failure markers at the end, including the reopen-before-index
replacement window. Marker inspection uses `lstat`, so a dangling symbolic link
is still a marker and inspection errors cannot silently restore completeness.

## Closed sources, checkpoints and retention

`source_closed=True` is the caller's assertion that the capture window has no
unrecorded writers or open observation sources. It is not proved by a file hash.
`close()` defaults to `False`; ordinary context-manager exit does not infer
source closure. The journal independently tracks active transactions and COMMIT
requests, and the adapter must supply all additional unread-result and source
references with `set_references(active_transactions=..., unread_results=...,
version_sources=...)`. That method replaces all three bounded reference sets.

An active transaction or unread result refuses source sealing. A lost COMMIT
acknowledgement followed by an idle `rollback_ok` remains unknown. A disconnect
leaves a permanent coverage gap; a later message cannot erase it. No outcome is
inferred from timestamps, tokens, connection idleness or a subsequent write.
A `rollback_ok.commitResponse` can instead identify the actual matching COMMIT
response: either its server `ROLLBACK` command tag, or a real `40001`/`40P01`
response with matching diagnostic SQLSTATE and IDLE status. Only that strict
request-bound evidence resolves a known aborted COMMIT; ordinary later rollback
does not.

Appending after close rejects the event, permanently invalidates the live
writer and attempts to create the separate invalidation marker. The v3 observer
also invalidates on later business execute/fetch/commit/rollback or facade
connection activity, while preserving its business behavior. Fresh verification
can still report integrity-valid stored data, but it reports incomplete when the
marker is present; strict export, reopening and archiving refuse it. Diagnostic
iteration/export of a post-close-invalidated observer is conservatively refused.
No original sealed bytes are changed. If the disk refuses every marker write,
the live instance still refuses completeness/export, but a new process cannot
learn about unrecorded later activity from unchanged bytes. An already exported
old window does not cover that later activity.

`checkpoint(source_closed=True)` synchronizes the recorded tail and records a
source assertion if references allow it, but leaves the writer open: it does
not itself produce a complete exportable journal. A final explicit `close()` is
still required. `SegmentedJournal.reopen(path,
exclusive_continuation=True)` supports only a previously complete sealed journal;
the caller must assert uninterrupted exclusive-source coverage between windows.
It preserves earlier raw files and starts a new segment. Reopening interrupted,
unknown or incomplete storage is refused rather than inventing a missing tail.

`prune(before_seq=...)` currently always returns `implemented: false` and an empty
deletion list. Active transactions, unread rows and version-chain sources never
lose their records. Deriving arbitrary source-closed subwindows and proving safe
garbage collection are unfinished. Retaining all evidence is intentional for
this slice and must not be advertised as completed retention management.

`archive(outside_new_zip_path)` verifies a complete sealed source, creates a new
archive containing the index, transaction cache and every raw segment, verifies
their archived bytes, reconstructs the complete storage from bounded extracted
members and reruns semantic storage verification, and retains all source files.
It rejects a destination
inside the journal or an existing target. A failed archive can leave its partial
new ZIP for inspection; it never returns a successful receipt for that file.
Archiving an incomplete source is refused in this implementation.

## Standalone verification and bounded export

```text
python -B integrations/python/moontxnwitness_capture/journal_v3.py verify JOURNAL_DIRECTORY
python -B integrations/python/moontxnwitness_capture/journal_v3.py export JOURNAL_DIRECTORY --output NEW.json --clock-domain ACTUAL_DOMAIN --exclusive-writers
```

`verify` exits `0` for complete, `3` for valid but incomplete and `2` for invalid
storage. `export` requires a complete verified source and streams a v3 envelope
with the caller's actual clock domain and explicit scope assertion. It defaults
to **8 MiB including envelope bytes**; `--max-bytes` changes that bound. An
oversized capture is refused; it is never silently truncated. Exporting selected
closed subwindows is future work. A false exclusive-writer assertion cannot be
detected by hashing and must not be substituted for deployment verification.
The Python export API additionally accepts an optional bounded `sql_profiles`
declaration (at most 16 entries and 8 MiB of bounded JSON); the default export
behavior is unchanged. Declaring a profile does not prove its SQL semantics.

Export writes and synchronizes a uniquely named temporary file outside the
journal, then publishes its final name with an atomic no-overwrite hard link.
An existing final file is preserved. Filesystems without hard-link support fail
explicitly. An over-budget or failed export publishes no partial final JSON and
removes only its own temporary file. Original evidence is retained throughout.

## IO verification (2026-10-21)

The first suite passed 43 tests. An expanded 50-test run preceded independent
audit, which found two real gaps: a final sync plus failure-marker failure could
lose the writer lock, and a foreign WAL cache could produce an incomplete
archive. Original failed receipts and raw files were preserved. After fixes,
the current suite ran **64 tests: 62 passed and two Windows symlink tests were
skipped** because this account could not create symbolic links.
These tests exercised real segment-creation/index-replacement
failures, injected device-sync/final-close failures, short writes, timed/size
sync, queue backpressure, truncation, same-size tampering, SQLite cache tampering,
reopening and interrupted-process rejection, bounded export, archive
reconstruction, actual foreign WAL/SHM state, combined sync/marker failure and
the lock appearing during streaming iteration. Later tests also cover strict
COMMIT-response evidence, bounded profile export, post-close append invalidation,
unchanged sealed bytes, marker-write failure with permanent live refusal and
marker-inspection failure. Separate collector tests cover post-close wrapper and
facade activity while preserving business return/exception behavior and allowing
ordinary cleanup.
The historical-identity case recorded and verified **4,100 completed
transactions**, beyond the former in-memory identity cap. All IO artifacts and
receipts were retained in the dedicated D-drive scratch directory; no PostgreSQL
or formal performance measurement was run by this suite.

This storage component alone does not complete v0.1.1/v0.1.2 joint acceptance,
full dislock lifecycle capture, SQLAlchemy integration, source-closed-window
reduction, performance gates or a public release.
