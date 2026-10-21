# Parallel-integer search trail draft

Two mutable arrays of (key, oldValue) tuples become four preallocated FixedArray[Int] buffers plus two logical sizes. The push point, undo order and marks are identical. Selected prefix plus its next distinct transaction cannot contain more than the admitted 512 raw operations, so the live state trail fits 512. Per-key final writes are a subset of the same writes, so the position trail also fits 512. The existing >512 admission check is unchanged.

Cache keys/policy, candidate traversal, blocker collection, attempts/operation checks, exhaustion status and budget tests are untouched. Five new tests cover 512 live writes, 512 final-write positions, undo after a 502-operation failed branch, exact 1,004/1,005 operation budget separation, and rejection of 513 operations. JS: 403/403; all-target deny-warn check passes.

Expected mechanism: remove hot tuple allocation/push/pop. Four 512-element integer buffers are a one-time per-search allocation; this tradeoff must be measured, especially on tiny successful or zero-budget searches. No measured speed or memory claim. Minimal eventual loads: completion-impossible-9/10/11/12, long failed prefix, 512-write boundaries, and tiny/zero-budget cache on/off controls.

These are isolated functional drafts on the exact f33c8675 baseline, not transferred into the primary source tree. No benchmark, P95, RSS or database execution was run. A passing byte comparison proves the checked complete outputs and counters match; it does not establish a speed or memory improvement. Native code was checked by --target all but not executed.
