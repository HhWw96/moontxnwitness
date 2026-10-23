# Full diagnostic capture cost protocol

This measures automatic raw driver diagnostics, configured provenance and
durable logs. It does not certify arbitrary SQL semantics, configured ORM
promotion, production adoption or full application model coverage. The earlier
source-only B/A study is a separate result.

## Frozen experiment

Use PostgreSQL 18, Python 3.12, psycopg/psycopg-binary 3.3.6 and the source-bound
runner. The recorded isolated producer environment is
`experiments/business/fastapi_users/requirements-lock.txt`. Stop all other local
compilation, database suites, SDK tests, packaging, downloading and extraction.
Use one otherwise idle owned PostgreSQL cluster and retain its configuration,
binary hashes and private connection file. Do not change a shared driver
environment or an existing application's database. Keep all temp/cache/data on
the declared capacity-checked volume.

A executes the original workload. B adds configured provenance and its real
database writes with no event collector. C adds automatic diagnostics, source
records, lifecycle records and durable persistence to B. No global driver
monkeypatch is used. The register-like SQL cost fixture is not a general source
schema or configured FastAPI Users proof profile.

The four workloads are 4,096 keys/one connection; 4,096 keys/four connections;
32 keys/eight connections with 90% of selected updates on four hot keys; and
4,096 keys/four connections with declared CRUD and negative reads. Every cell
warms for 15 seconds, issues for 60 seconds and permits at most 30 seconds of
transaction drain. Its throughput denominator also includes the actual durable
capture/source tail. Orders are ABC, BCA and CAB in three batches per workload:
36 fresh child-process cells for a column profile, and a separate 36 for a
sidecar profile. Seed is 20261023, with fixed batch and worker offsets recorded
in the plan. The original 100,000 attempts per worker and all raw storage caps
remain explicit; exhaustion is a failed cell, never a valid target result.

All attempted transactions, SQLSTATE outcomes, commit/rollback results, latency
samples, CPU, process peak RSS, blocking observations, database-global WAL LSN
and counter deltas, final business checks and persistence completion times are
retained. The common 100 ms capacity sampler runs for A, B and C, including
warmup. A volume free-space value below the fixed 512 MiB reserve stops the
cell and records a protocol failure. It does not delete a live source or alter
the workload to manufacture a pass. Database-global WAL/counters do not become
invented exact per-transaction attribution, and server CPU is not measured.

The formal eligibility rule requires all three matched A/B/C batches. For each
workload the geometric mean of paired C/A committed throughput must be at least
0.90 and paired all-attempt P95 must be at most 1.15. B/A remains separately
reported. `formalProtocolCompleted` and `performanceTargetsPassed` are distinct.
Strict target eligibility additionally requires zero failed attempts in every
A/B/C cell, including warmup. Registered SQLSTATE 23505/40001/40P01/55P03 errors
remain in their original all-attempt latency/SQLSTATE counts and may allow the
timed protocol to finish, but disqualify its performance evidence. Missing or
invalid measured failure counts, any protocol/capture-budget failure, or nonzero
reported SQLSTATE counts are also ineligible. Comparison recomputes eligibility
from the retained cell counters rather than trusting a supplied pass flag.
Quick runs and incomplete prefixes are ineligible, even if their ratios look
favorable. The first failure is retained; diagnose and change implementation
before any new measurement rather than repeating unchanged code until it wins.

## Commands and partial first run

From the repository with a private `MTW_PG_CONNECTION_FILE` referring to the
owned exclusive cluster, generate plans without starting any database work:

```text
python -B experiments/provenance/full_capture_cost.py --output NEW_COLUMN_PLAN --profile column --plan-only --archive-cells
python -B experiments/provenance/full_capture_cost.py --output NEW_SIDECAR_PLAN --profile sidecar --plan-only --archive-cells
```

The first capacity-constrained invocation may execute exactly the first ABC
group with the original full timing. It preserves all 36 preregistered cells:

```text
python -B experiments/provenance/full_capture_cost.py --output NEW_FIRST_GROUP --profile column --exclusive-host --exclusive-cluster --archive-cells --max-cells 3
```

Alternatively, the owned wrapper creates a new retained cluster from existing
PG18 binaries, writes its private credentials only in that new output, records
binary/source hashes, invokes the same full-timing prefix and stops only its
own verified data path:

```text
python -B experiments/provenance/owned_full_capture_cost.py --bin EXISTING_PG18_BIN --output NEW_OWNED_FIRST_GROUP --profile column --exclusive-host --max-cells 3
```

Its fixed memory/WAL settings are 32 MiB shared buffers, 24 connections, 2 MiB
work memory, 512 MiB max WAL size and 80 MiB minimum WAL size, all recorded in
the wrapper receipt. Max WAL size is a checkpoint target, not a hard storage
cap. The wrapper never downloads binaries or changes an existing cluster. It
is prepared but has not yet run an actual full-timing cost cell.

Success of those three cells gives `status=partial`, exit code 2 and
`formalProtocolCompleted=false`; it cannot pass all-workload targets. A source
or storage failure gives a failed/incomplete result. Do not use `--quick` for
this first full-timing group. Omitting `--max-cells` runs the full registered
profile; start it only with a justified storage budget. No formal run has yet
been executed by this preparation slice.

## Capacity and post-measurement archives

C permits 1 GiB of raw event segments, 1 GiB of source records and 512 MiB of
lifecycle records. The separately checked transaction SQLite index admits up
to 2 GiB, with attempt logs and small metadata in addition. A conservative
accepted-cell envelope is about 4.75 GiB before PostgreSQL, WAL and other
retained schemas. A full zip is temporarily additional to its raw files; in the
incompressible case a cell can require about 9.5 GiB plus database space. These
are conservative protocol capacity estimates, not measured production sizes.
Current roughly 5.6 GiB free space cannot guarantee that extreme single-cell
envelope or a complete 36-cell run. Keep at least the original logs on refusal.

With `--archive-cells`, compression starts only after the child has terminated,
its measured durable tail ended and its terminal original receipt exists. No
archiving overlaps a measured cell. Before starting an archive, the parent
requires space for the actual complete raw byte count again, plus 512 MiB
reserve and 16 MiB overhead. It streams every original file into a new zip,
binds each path/byte count/SHA-256 in the internal manifest, independently reads
every zipped file to verify it, and binds the zip and manifest themselves.
Only then does it recheck the unchanged complete raw set and unlink those
enumerated files inside this invocation's newly created direct `cell-N`
directory. It leaves `archive-pointer.json`; the summary points to the zip,
manifest and original receipt hashes. Failed cell states remain failed.

No previous evidence, other run, active log or PostgreSQL data file is released.
Any changed/new file, unsafe link/path, checksum mismatch, missing receipt,
capacity refusal or verification failure leaves the raw cell in place. An
interrupted partial zip is retained and is not proof that release occurred.
This archive is byte retention, not a claim of complete model coverage.

Verify or restore using a fresh base-Python process and the expected zip SHA
from its pointer (restoration refuses an existing destination):

```text
python -B experiments/provenance/cell_archive.py RUN/archives/cell-0.zip --sha256 EXPECTED_SHA256
python -B experiments/provenance/cell_archive.py RUN/archives/cell-0.zip --sha256 EXPECTED_SHA256 --restore NEW_RESTORED_CELL
```

The offline archive tests cover byte-exact restoration, original receipt and
failure-state preservation, zip/source mutation, unsafe names, duplicate
members, expansion limits and release boundaries. Windows hosts without link
creation privilege explicitly skip that one symlink case. They are not formal
database or performance results.
