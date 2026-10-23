# Cost protocol and post-cell retention preparation

This receipt records no PostgreSQL execution and no formal performance result.
The full column and sidecar plans each retain 36 cells, all four workloads,
15-second warmup, 60-second submission, 30-second bounded drain and the three
rotations ABC/BCA/CAB. Targets stay C/A throughput at least 0.90 and all-attempt
P95 at most 1.15. The default owned-runner prefix is three full-timing cells;
completion is explicitly partial and cannot pass complete protocol targets.

The first archive test run failed nine cases because Windows cannot fsync a
read-only descriptor. Its exact first source and output remain here. The
corrected writable-descriptor implementation passed the original checks; the
expanded suite additionally restores bytes through the public CLI in a fresh
Python process. Final archive result: 12 passed and one explicit Windows
symlink-privilege skip out of 13 cases. Final cost protocol result: 17 passed,
including unchanged original workload/rotation/eligibility checks, both fixed
targets, full source-helper binding and refusal to start an owned cluster
without a host exclusivity assertion or with an invalid prefix.

Compression is optional and happens only after the timed child, tail and native
receipt finish. Every original file and receipt is SHA-bound inside the zip;
the complete archive is independently streamed and checked before the complete
unchanged original cell set is released. Previous evidence, active sources and
database files are outside this tool's release scope. Any capacity or binding
refusal retains the raw files. Reports retain explicit zip/manifest/original
receipt pointers and hashes; independent restoration refuses an existing path.

The new owned PostgreSQL runner has only offline startup guards tested here.
Its actual database startup and full-timing execution remain not executed.
The manifest's 4.75 GiB raw / 9.5 GiB raw-plus-zip single-cell estimate is a
conservative protocol envelope, not a measured size. Additional database, WAL
and previous cells are not bounded by that estimate. Available D space does not
guarantee the worst envelope or the full protocol. The fixed 512 MiB common
capacity sampler fails a cell instead of dropping evidence. Archive creation
has another actual-byte-count capacity preflight.

Use the executable commands in
`experiments/provenance/full_capture_cost_protocol.md` only when the host is
otherwise idle and the declared storage budget is justified. These offline
tests do not certify the cost runner's semantic source records as arbitrary
SQL/ORM facts or grant complete application model coverage.
