# Sparse temporary-map draft

collect_writes detects a transaction's single-key write case before allocating a last-write map; the general multi-key path preserves all original write indices and is_final flags. Existing nested write maps are retrieved without allocating unused defaults. Validated two-version orders compute the known 0/1 rank directly; longer orders keep the original rank table.

Per-transaction own-write and first-read Maps become shared epoch-stamped parallel arrays. Scratch indices are allocated only when an operation in a non-skipped committed transaction first touches a key. No slot is allocated for a merely unused initial key. Epoch ti+1 keeps skipped/aborted/unknown transactions from leaking scratch, and first-read/latest-own-write indices retain the same diagnostics. This change does not reorder transaction, operation, edge, finding or version-order iteration.

Six new semantic tests cover cross-TX own state, the first read's diagnostic position, interleaved multi-key finals, latest-own-write diagnostics, two-version WR/RW order, and 1,024 unused initial keys with skipped TX before/after live operations. JS: 404/404; all-target deny-warn check passes.

The initially validated eager-initial-key variant is retained under receipts/initial-scratch-snapshot with its original receipts. Final code is the lazy variant. The change avoids a known allocation on wide initial/small reduced histories; overall speed/RSS remains unmeasured. Minimal eventual loads: sparse512, noise64, reduction512, wide initial/tiny TX, interleaved multi-key and aborted/intermediate reads.

These are isolated functional drafts on the exact f33c8675 baseline, not transferred into the primary source tree. No benchmark, P95, RSS or database execution was run. A passing byte comparison proves the checked complete outputs and counters match; it does not establish a speed or memory improvement. Native code was checked by --target all but not executed.
