# Frozen two-epoch source handoff experiment

This archive preserves the unchanged `plain-v3-epoch-r1` candidate, its first
static and subsequent 40/45/47-test snapshots, and the exact original R2 runtime
dependency bindings. The local final suite passed 47 checks with no skips;
those database responses were synthetic. Real PostgreSQL results must come from
the separately dispatched manual workflow and its retained first-run artifact.

The experiment admits two epochs, 1-64 existing text keys with integer values,
128 live connections, 1,024 audit rows and an 8 MiB source ledger. The four
prepared database scenarios check equal-value version identities, rollback and
savepoint effects, unsupported SQL refusal, and an injected discarded setup
COMMIT acknowledgement. The latter executes real COMMIT then throws; it is not
a network-disconnection test. There is no automatic retry of a failed run.

`scripts/experimental_plain_epoch_ci.py` restores all 62 original R2 files and
the 35 new candidate files into a fresh Linux directory. It verifies the nine
runtime dependencies, runs the 47 checks before the four database scenarios,
then binds the exact executed sources, receipts and raw chain files. The manual
workflow uses a digest-pinned disposable PostgreSQL 18.6 image and optional
psycopg 3.3.6 driver. It retains partial output, server logs and first failures.

Raw observation continuity does not establish the SQL proof or a complete
analysis source closure: `coreProofImplemented`, `sourceClosureVerified` and
`formalEligible` remain false. Pruning is refused; recovery is inspect-only.
This experiment is not a 4,096-key cost result, general SQL support or a release
acceptance gate.

Independent static review identified a future admission hardening task:
`create()` currently materializes an iterable before applying the 64-key limit.
The frozen real-database fixture supplies a finite two-key tuple. R1 is retained
unchanged for this experiment; arbitrary iterable admission needs a separately
frozen bounded-consumption revision before promotion.

The inherited R2 first initialization records the setup COMMIT tag without
requiring the same explicit COMMIT/idle checks used by the handoff boundary.
The unit suite replaces that initial setup with mock data. A separate revision
must validate first-initialization acknowledgement and test failures before any
promotion of this experiment to supported source-closure behavior.

The [recorded actual run and independent review](actual-ci-39620317399/README.md)
now retain 47 passing checks, four real PostgreSQL cases and 2,832 independent
read-only checks. The initial archive failure remains under
`first-ci-39619434773`. The two admission/initialization limitations are addressed
in the [separate R2 candidate](../plain-epoch-r2-2026-10-21/README.md); neither
frozen R1 source nor its historical receipts were rewritten.
