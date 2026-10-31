# Independent installed-source proof contract draft

The source installer is a producer of raw control observations. Its booleans and Python validators must not authorize future source facts. This draft identifies the independent core inputs and remaining joins; it is not an implemented or frozen acceptance interface.

## Required input separation

- Caller-supplied immutable original `SQLCaptureConfig` and installation policy, not policy/budgets inferred from a report.
- Exact DDL/control SQL text and parameters, paired request/result sequence identities and native transaction/status/column metadata.
- Raw native text cells, actual decoded control deliveries, initialization row identities and stream seals/digests.
- Separate original business SQL/parameters, native buffers and actual fetch delivery records from the frozen independent grammar/fetch stages.
- Later finite source-window, database/client transaction mapping and effective write/rollback records. These are currently absent.

The future MoonBit verifier should parse duplicate-sensitive bounded JSON, regenerate expected control queries/DDL/function bodies from configuration, compare raw bytes with decoded observations, check request/result/transaction sequencing and recompute catalog/initialization conclusions. Unknown inputs, missing rows/requests, truncated logs and exhausted caller budgets must remain unknown or rejected. Only a fully completed matching set can satisfy a component; a self-declared `catalogVerified` or recomputed hash is insufficient.

## Installation consistency

The stream must begin in an idle dedicated control connection, acknowledge BEGIN, acquire all expected table locks before the first SELECT, and contain the same backend/database identity throughout. Expected table OIDs/column positions/types/primary key, private schema/object ownership and grants, exact trigger identities/arguments/prosrc/settings, no-cycle version sequence and installed uniqueness must agree. Initial rows must come from the actual locked row outputs, contain exactly the configured scalar values plus installed metadata, have unique versions and satisfy every budget; neither a sentinel nor a truncated row can become an initial fact. Scope and initial effect counts must match. The final COMMIT needs its native success tag and post-response state, followed by an intact seal.

These checks establish consistency under PostgreSQL's declared semantics, not collector authenticity or an absence of privileged out-of-scope DDL. That remaining condition must be visible rather than hidden in a config boolean.

## Same-statement read source

A future projector must first verify the original SQL and original bindings against the original config. An explicit full-mode transform may derive an augmented schema containing the installed metadata, but must keep the original config/digest separate. A hidden pure-column SELECT suffix must have an exact independently checked transform, unchanged FROM/WHERE/parameters and business column ordering, and matching native metadata/result prefix. Statement/parameter differences, unsupported syntax, missing source columns or unconsumed results preserve gaps. A later SELECT cannot supply the version of a prior business read.

Standard description/fetch/rowcount behavior and errors need dedicated driver tests. Direct native `pgresult`, custom row factories, binary/server-side cursors, star/empty/sentinel transforms and writes without the necessary source return path remain outside the first transform. The current installer performs no transform.

## Finite writer window

Source sidecar AFTER effects describe actual writes and actual OLD predecessor identities. They do not describe a complete UPDATE predicate read or prove which rows were scanned/rechecked under RC. A zero-row conditional statement is a separate condition observation. Global sequence values and xids must never imply commit order.

Opening/closing barriers must drain conflicting ordinary writers and bind snapshots/effect coverage. Every observed effect must map to a captured connection/transaction/program statement, with explicit gaps for unobserved writer/read activity. Backend PID alone is insufficient across reuse; bind actual connection epochs and original lifecycle records. Additional metadata SQL must be proved not to advance the original logical snapshot; a pre-query SELECT can change RR behavior and cannot be introduced silently. COMMIT request is not confirmation. Savepoint rollback revokes writes and associated source effects but does not erase already delivered reads.

Only after catalog, initialization, writer-window, same-statement source, actual fetch and independent core checks are all satisfied should an explicitly versioned interface consider `sourceFactsProduced=true`. The present install candidate always leaves that flag false.
