# Grouped source persistence and full capture cost

`GroupedSourceSink` is an optional source-record writer. The legacy
`_orm_source_sink.SourceSink` keeps its per-record synchronization and limits.
Existing v1 capture and presence entry points are unchanged.

```python
from moontxnwitness_capture.source_sink import GroupedSourceSink

sources = GroupedSourceSink("new-sources.jsonl")
accepted = sources.append({"kind": "source-batch", "observation": original_source})
if not accepted.accepted:
    # Preserve the reported gap; this capture cannot establish full coverage.
    record_gap(accepted.gap)
sources.flush()  # waits for the accepted prefix and its index to be durable
status = sources.close()  # seals, drains, synchronizes, then releases writer lock
```

`accepted` acknowledges queue admission, not durable storage. `durable_seq`
reports the synchronized prefix. Default limits are a 4 MiB memory queue,
128 KiB record, 16 MiB source file, and 16,384 records. A dirty tail synchronizes
at 256 KiB or 100 ms, whichever occurs first. Queue admission reserves the maximum
record size before encoding, so blocked producers cannot accumulate encoded
records outside the stated queue. Backpressure count and time are measurable.
Close synchronizes both the data and index before dropping the writer guard.

The source file keeps the existing `orm-source-draft/2` header and JSONL framing.
Its companion `.index.json` binds actual durable bytes, SHA-256, sequence,
configuration and counters. A truncated seal, altered data/index, lingering
writer/failure guard, rejected record or post-close append prevents a sealed
storage result. `verify_grouped_source` reads bounded lines and streams the file;
it does not load the entire source into memory. A valid sealed file still has
`completeCapture=false` and `coreProofAccepted=false`. Storage integrity cannot
supply missing SQL sources, model semantics or an isolation verdict.

The v3 segmented journal and this writer share `_durable_policy.CapacityQueue`
and sync/flush scheduling, including explicit target-watermark handling.
Record validation, file framing, segment/index management and failure handling
remain separate because source and event records have different semantics.
This is shared queue and sync policy, not a second copy of the event writer.

Raw collection may explicitly raise source limits up to 1 GiB/1,000,000 records
and queue size to 64 MiB. Instrumentation may explicitly raise lifecycle limits
to 1 GiB/2,000,000 records. The cost runner uses larger bounded raw limits; it does
not raise default export/analysis limits or certify that a large file can be
loaded as one analysis window. Any exhausted budget invalidates that cost cell.

## A/B/C cost protocol

`experiments/provenance/full_capture_cost.py` compares:

- A: the original point/CRUD business SQL and client attempt log.
- B: the same workload with the existing column or sidecar provenance profile.
- C: B plus automatic raw diagnostic capture, grouped source persistence and
  lifecycle storage. Initial and read sources, then actual final audit rows,
  are retained without hand-written transaction histories.

This measures the implemented diagnostic-plus-provenance profile. It does not
claim complete arbitrary SQL/ORM model coverage. B/A is reported separately;
only C/A is used as the complete capture cost of this declared profile.

Use a new output directory and an explicitly owned PostgreSQL 18 instance.
`MTW_PG_CONNECTION_FILE` is a private JSON file of psycopg connection arguments;
connection credentials are not copied into public receipts. No server, package
or archive is downloaded. Each cell creates and retains a fresh fixture schema.

```text
python -B experiments/provenance/full_capture_cost.py --output NEW_PLAN --plan-only
python -B experiments/provenance/full_capture_cost.py --output NEW_SMOKE --quick
python -B experiments/provenance/full_capture_cost.py --output NEW_FORMAL --profile column --exclusive-host --exclusive-cluster
```

Run `--profile sidecar` separately for the other supported profile. The caller
must actually stop compilers, other database suites, packaging and downloads
before the formal command. The two flags are explicit assertions, not an
automatic proof that the host is idle. `--quick` is development smoke only.

There are four fixed workloads: 4,096 keys/one connection; 4,096 keys/four
connections; 32 keys/eight connections with 90% updates on four hot keys; and
4,096 keys/four connections with known-key CRUD and negative reads. Each uses
15 seconds warmup, 60 seconds issuing, at most 30 seconds transaction drain,
with three `ABC/BCA/CAB` batches. Each cell is a fresh child process, and every
worker's deterministic seed and generator version are retained.

All measured attempts, commits and failures are logged without hidden retries.
Throughput includes transaction drain and durable capture/source tail; P50/P95
include failed attempts, with committed-only P95 also available. Receipts keep
client CPU, process peak RSS, WAL deltas, actual server lock-wait samples,
database-global counter scope, source budgets and gaps, final business checks,
source hashes before/after execution and raw per-worker logs. Server CPU is
explicitly unmeasured. SQL failures, exhausted budgets, missing logs, source
changes, timeouts and missing cells make the comparison ineligible. A failed
run is retained and stops; the runner does not retry an unchanged cell until it
passes. A plan-only or unconfigured database is recorded as not executed.

No formal cost results are included with the protocol unit tests. Run the full
protocol in an exclusive window before claiming the throughput or P95 targets.
## Dedicated hosted measurement

The manually dispatched `full-capture-cost.yml` workflow pins an exact source
commit and runs one controlled profile on a dedicated Linux job. It records the
36-cell plan before measurement, installs dependencies and starts its owned
PostgreSQL 18.6 container before timing, then preserves complete raw archives,
server logs, machine metadata and the byte-identical plan. Dispatch `column`
and `sidecar` separately. A successful workflow does not imply the numeric
targets passed; read `hosted-receipt.json` and all workload qualifications.
Underlying physical-host tenancy is not measured, and absolute times from
different hosted jobs are not a same-machine comparison.

Lifecycle sidecars retain their original buffered-file append and close-time
flush/fsync guarantee. They have total byte/record limits; they do not use the
4 MiB shared queue or promise its 100 ms durability interval. The grouped event
journal and optional source writer are the objects using that policy.

Full sealed-journal export and archival preserve the original records. Selecting an
arbitrary analysis subwindow with its complete transitive source closure remains
unimplemented in this release; a stored or exported window is not automatically
a complete model history.
