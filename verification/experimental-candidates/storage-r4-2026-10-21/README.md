# Frozen stable-mutex storage revision 4

The prototype now separates a permanent `coordination.lock` native mutex from
the removable owner record `operation.lock`. Every cooperative operation,
including recovery and reading, acquires the same permanent inode. The permanent
mutex is never unlinked. This closes the reviewed unlock/check/unlink handoff
race; checking a removable pathname alone could not do so.

Data and supported directory synchronization requests complete while the owner
guard and permanent mutex are still held. Owner cleanup occurs under that stable
mutex; there is no new data synchronization after owner removal. If the temporary
owner record reappears after a crash, later work conservatively requires recovery.
The contract separately records limits on observing native coordination release
failures after data commit when every subsequent persistence attempt also fails.
Windows does not acquire a physical directory-fsync guarantee from these tests.

Candidate index `223e61bc…c920124` binds the revised source, original dependencies,
prior actual failures and the rejected pre-stable design snapshot. The manual
workflow executes 51 incremental cases plus 32 unchanged regression cases on both
platforms. These results are pending until actual execution.

The old independent revision-3 counterexample and its failed safety expectations
are preserved. Its post-owner-removal sync premise is inapplicable to this
protocol and is **not counted as a pass**. A separately preregistered independent
audit targets the new protected final barrier and redundant-marker IO failure.

```
python -B scripts/experimental_storage_ci.py --candidate r4 --work /path/to/new/mtw-storage-r4
```

This remains an experimental sealed point-register storage protocol. Full capture
integration, list/relation closure, physical power-loss testing, throughput gates
and stable API acceptance remain separate work.
