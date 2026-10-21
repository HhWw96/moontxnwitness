# Archive reader / cold-segment prune — revision 4

This is a new **static, unexecuted** candidate. Original r2/r3 source, tests and
actual receipts remain unchanged. r3 passed 70 cases on both CI platforms, then
an independent filesystem counterexample failed three of nine safety checks on
both platforms: guard missing, live instance unpoisoned, fresh result complete
after the final directory sync failed. Those failed results are preserved.

The protocol now separates a permanent native mutex from temporary owner state.
`coordination.lock` is created during adoption, contains the installation nonce,
and is never removed or replaced by the API. Every operation acquires its native
OS lock first and holds it through owner-path inspection/deletion. The existing
`operation.lock` holds owner nonce/token, but is not an OS mutex. This prevents a
second recovery acquiring an old inode between unlock and unlink while a third
operation creates a new inode.

All source/archive/intent/manifest/marker durability work and the final store sync
occur with the permanent mutex held and the original owner guard still present.
Normal data completion requires that final sync to succeed. An exception there,
including a second marker-write failure, must retain the guard, poison the live
instance and block fresh completeness. Owner close/unlink errors preserve the
still-existing guard. Cleanup never replaces the original exception.

Here a confirmed commit means the actual file-sync and platform-supported sync
requests completed. Frozen `point.sync_directory` requests directory fsync on
POSIX, but is a controlled no-op on Windows. A Windows return or injected failure
is not evidence of physical directory persistence. Keep Linux and Windows raw
results separate; physical power-cut and Windows directory-fsync certification
remain unexecuted. The required guard behavior on source/intent/sync failures is
unchanged on either platform.

After the confirmed data commit, owner removal is temporary coordination cleanup:
its deletion is deliberately not directory-synced. A reappeared owner conservatively
requires exact explicit recovery. Native unlock/close follows owner removal; it
does not create another data durability promise. Such a coordination-only exception
poisons the live instance and attempts owner/marker persistence. If **all** those
post-commit writes fail, another process can still see valid committed data but
cannot learn that release exception. This explicit boundary does not apply to any
source data write, intent cleanup, marker cleanup or final protected sync failure.

The old independent nine-check input remains unchanged. Its premise (sync after
owner removal) is inapplicable here and must not be reported as passing. The new
independent gate must inject a real final protected-sync failure plus diagnostic
IO failure with the same three safety requirements. A first r4 static design with
the old unlock/unlink handoff race is retained in `snapshots/pre-stable-mutex/`.

Author suite: 33 retained r2 cases + 5 retained r3 cases + 13 new r4 cases = **51**;
separate original regression = **32**, total **83**. Original regression source
remains byte-identical. No local syntax, filesystem, Python subprocess or database
test has been executed for r4. These are expectations, not passing receipts.

Independent Python 3.12 stdlib calls, retaining repository layout:

```
python -B artifacts/source-window-v3-archive-r4-draft/test_gaps.py
python -B artifacts/source-window-v3-archive-r4-draft/test_managed.py
```

Use a distinct precreated scratch base for each invocation; set
`MTW_JOURNAL_SCRATCH`, `TEMP` and `TMP` to that base. Retain all actual inputs,
child crash logs and receipts. Verify every declared source/dependency SHA before
and after execution. Linux must not skip symlink checks; Windows must record the
actual outcome. Four repository dependencies remain as frozen in prior revisions.

Only point-register closure is supported. This draft does not add automatic SQL
coverage, list/relation closure, archive deletion, default-journal integration,
formal performance evidence, stable publication or organizer acceptance.
