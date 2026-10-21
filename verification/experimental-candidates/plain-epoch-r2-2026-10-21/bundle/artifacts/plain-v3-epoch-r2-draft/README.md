# Epoch R2 initialization hardening candidate

Separately frozen author candidate, not executed or promoted. Original R1 and
ordinary-table R2 files remain unchanged; exact R1 source and contract are copied
under `baseline-r1`. Dependencies are byte-bound in the static index.

Key admission consumes at most 65 items before accepting at most 64 distinct
UTF-8 text keys. Rejected declarations touch neither files nor database. The
first setup COMMIT must return the exact command tag, COMMAND_OK, no rowset and
an idle connection; its observed ACK is retained before snapshot publication.
Driver exceptions remain the same objects even if diagnostics or rollback fail.
A failed or unknown initialization cannot be retried on the same capture.

`test_hardening.py` prepares the original 47 cases plus 26 focused cases. The
new tests use synthetic catalog/business responses while exercising the unchanged
initializer, new proxy and publication barrier. They have not run. The included
`postgres_epoch.py` is copied unchanged from R1 and has not run against R2.

No SQL-core proof, source-closure proof, independent acceptance, real database
validation or performance measurement is claimed. Pruning remains refused.

Restore the declared repo-relative layout and exact dependencies before running.
Use a new owned MTW_JOURNAL_SCRATCH directory; preserve the first receipt and
source snapshot before any correction. The author must not sign independent
acceptance of this revision.
