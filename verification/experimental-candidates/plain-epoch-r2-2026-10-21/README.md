# Separately frozen initialization hardening

This revision keeps R1 and its original ordinary-table dependencies unchanged.
Key admission consumes at most 65 iterable items before admitting at most 64
distinct UTF-8 keys, and rejects invalid declarations before filesystem or
database effects. The initial setup COMMIT must return COMMAND_OK, the COMMIT
tag, no rowset and idle connection status before publishing the first snapshot.
Unknown or failed initialization cannot retry on the same observer. Primary
driver errors remain the original objects if diagnostics or rollback also fail.

The first isolated local run passed the original 47 cases plus 26 new admission,
acknowledgement and failure cases: 73 total, no skips. It uses explicitly
synthetic catalog/business results and the real unchanged initializer, ACK gate,
files, native child processes and publication barrier. All 27 restored source
bindings were unchanged. The original receipt is retained under `first-local`;
the local log is a marked path-redacted derivative with both byte bindings.
Archived author descriptions retain their original pre-execution status.

A separate manual Linux workflow restores only the exact 18 frozen candidate
files and 62 original dependency files. It reruns the 73 checks before four
controlled PostgreSQL 18.6 cases. Its actual database results and independent
acceptance must be recorded separately. It does not borrow R1's database pass.

ACK records are appended before snapshot publication; the source ledger is
synchronized at close. This is not a claim of per-record fsync or crash-durable
initialization. Active/failed ledgers cannot be verified complete.
`coreProofImplemented`, `sourceClosureVerified` and `formalEligible` remain
false. Pruning, automatic recovery and general SQL support remain unavailable.
No formal performance measurement or stable release acceptance is claimed.

The scripts in `first-local` are archived in their original artifacts layout;
restore that layout before executing them. The dedicated CI runner is
`scripts/experimental_plain_epoch_r2_ci.py`.
