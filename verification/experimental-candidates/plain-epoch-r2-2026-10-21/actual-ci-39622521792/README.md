# Actual R2 execution and independent limited acceptance

The immutable source is `e63df4b815f130674bc0f10939d8513e534679a8`.
[Run 39622521792](https://github.com/HhWw96/moontxnwitness/actions/runs/39622521792)
retains actual output for 73 checks and four controlled PostgreSQL 18.6 cases.
The original artifact is 931,937 bytes with SHA-256
`bd569323de9a3d8fef27a68692c9f97a140dd1006182362d09a9b05da16aaaed`.

A separate AI reviewer passed 2,760 checks with no failures, rehashed all 791
archive members and the executed source against immutable Git objects, checked
all 73 exact test identities and the four actual database histories. Every case
has a real initial COMMIT/COMMAND_OK/idle ACK at source record 1, followed by the
installation record. The snapshot barrier and executed focused test establish
the code ordering; separate files do not supply a common timestamp or prove
per-record fsync. The 26 focused initialization faults use synthetic responses;
the actual fault scenario discards a boundary COMMIT response after it executed,
and is explicitly not a real network-disconnection test.

The official run endpoint reports completed/success, while the independently
fetched job listing and direct job endpoint still report in_progress/null.
All responses are retained. The reviewer accepts the exact retained execution
evidence and explicitly leaves `overallJobCompletionMetadataVerified=false`.
It does not infer job completion from a null field or keep polling for a pass.

This is limited independent AI evidence acceptance. SQL-core proof, analysis
source closure, crash durability, formal performance, overall job completion
metadata and release acceptance remain outside the result. See
`independent/receipt-first.json` and its immutable public index.
