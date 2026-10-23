# Explicit experimental storage capacity candidate

Base: bf28179a40aa2d1325f4f1484acb30362eea4f18 plus the separately reviewed one-line duplicate-test flush barrier. This isolated tree does not modify the release workspace.

The explicit `full-capture-cost-capacity/v2` profile permits higher configured ceilings while every default and legacy rejection remains unchanged. A single shared observer/source/lifecycle remains per measured cell. Proposed active settings: source 2 GiB / 6M records; lifecycle 6 GiB / 16M records; journal 4 GiB; transaction SQLite 1 GiB (page cap before growth); attempt logs 1 GiB. Queues stay 4 MiB. No analysis/export limit is raised; 8 MiB analysis diagnostic export remains bounded.

Writers mark experimental storage. Readers require the same explicit opt-in and validate actual declared limits against the finite profile, never self-authorizing from disk. Legacy storage retains its old format/default path. SQLite reconstruction is also page capped. New lifecycle verification is streaming and storage-only.

Evidence: first hosted environment df reports `/dev/root 145G total / 62G used / 84G available`, and first cell minimum free was 89,333,989,376 bytes. New hosts must be checked live, not assumed equivalent. Before each cell, use a 14 GiB raw envelope twice (raw + worst-case ZIP), 1 GiB reconstruction index, 8 GiB PostgreSQL/WAL budget and 4 GiB reserve (~41 GiB). Already completed archives consume observed free space automatically. A free-space or DB budget refusal remains failed/ineligible and preserves evidence. Full 36-cell completion is not guaranteed for worst-case incompressible outputs.

Frozen 15-second warmup, 60-second issue, 30-second drain and all raw observations remain. Candidate attempt ceiling is 1M per worker and a separately recorded warmup bound; neither turns any prior exhausted cell into a pass. No second formal run, database or local performance measurement is authorized here. Small real-file fault tests only.

## Execution and refusal contract

`--experimental-budget full-capture-cost-capacity/v2` is required to select the new finite plan; workflow choice defaults to `legacy`. All three modes retain the same 15/60/30 windows, seeds, operations and shared observer topology. Warmup is additionally bounded at 250,000 attempts per worker; measured attempts at 1,000,000 per worker. Exhaustion always makes the cell ineligible. The fixed all-mode attempt log reserves bytes before issuing each operation, so budget refusal cannot execute an unrecordable next attempt.

The raw envelope is 14 GiB plus 64 MiB metadata, rather than a promise about typical output. Every new cell checks actual free bytes (and already retained archives) against raw + worst-case ZIP + 1 GiB reconstruction + 8 GiB database/WAL + 4 GiB reserve. The runtime monitor protects an archive/reconstruction reserve and samples database/WAL size once per ten lock samples; that database guard is sampled protection, not a hard database quota. SQLite uses a hard page count at both writer creation and verification reconstruction. Default source/lifecycle bounds and legacy archive 8 GiB behavior remain. Experimental archives allow at most 16 GiB only with the same explicit reader profile.

Large declaration tests use small real files; they do not demonstrate GiB-scale speed. Journal/source/lifecycle verification streams records. Attempt quantile aggregation still retains Python latency lists, and the final RSS must be reported honestly. Analysis and diagnostic export limits remain 8 MiB; this capacity profile is storage/verification support, not large-history analysis coverage. The child deadline remains bounded; any deadline, disk or storage refusal stays failed. Full 36-cell completion is not guaranteed in the worst case.

No formal experiment has been run on this candidate. Both original failed remote runs and their 100,000-attempt plan remain immutable external evidence.

## Compatibility and receipt field boundaries

The legacy journal's 1 GiB default was not a hard `totalBytes` ceiling: valid existing custom legacy journals retain their original reading rules. The new experiment marker requires the matching explicit opt-in for its unchanged marked representation; it is a capacity declaration, not authentication. Source/lifecycle experimental limits remain finite, and a reader never increases them from an index declaration alone.

`captureBudgetExhausted` retains its earlier limited meaning. Attempt/warmup/attempt-log, sampled database/WAL and storage-reserve refusals remain visible in `protocolFailures`; any such failure prevents formal completion and target eligibility. `JournalIOError` is not automatically relabelled as a page-budget failure because it may have a different IO cause. Read actual failure codes and original logs rather than treating one summary flag as exhaustive.

Verification reconstruction also checks its actual temporary filesystem, which may differ from the output volume. The workflow selects an owned runner scratch directory and records byte-based output/scratch filesystem observations and memory metadata. Neither a human-readable old df snapshot nor a candidate plan is proof about a new VM.
