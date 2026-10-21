# Archive reader / cold-segment prune — revision 3

This new ignored candidate fixes the actual recovery regression from independent
run `39582277986`, commit `405588d0…`. Both Linux and Windows executed all 33 r2
gap cases successfully, but both failed original regression `test_32`; neither
platform skipped the dangling-symlink tests. The original r2 index `7a014774…`,
all original inputs and all actual failure receipts remain unchanged.

The failure was a production state transition: an invalid abandoned-lock token
was not checked against the prepared intent until after `dirty=True`. Refusing
that unmodified recovery then wrote an owner marker bearing the wrong token.
Restoring the true lock token could no longer recover. This revision validates
intent/token/roots before dirty and repeats `_finish` checks before mutation.
It does not weaken either wrong-token refusal or the old test expectation.

Five new cases explicitly check byte-preserving refusals, same-instance valid
retry after restoring exact authority, genuine existing-marker retention, and
failure after real recovery publication. The gap suite now selects the retained
33 `test_r2_` cases and five `test_r3_` cases: **38 expected**. Run the original
32-test regression separately against this new source: **70 expected total**.
All r3 Python syntax, runtime, filesystem and subprocess tests are **unexecuted**
locally. No prior pass or skip is an r3 result.

Independent Python 3.12 stdlib invocation, in the preserved repository layout:

```
python -B artifacts/source-window-v3-archive-r3-draft/test_gaps.py
python -B artifacts/source-window-v3-archive-r3-draft/test_managed.py
```

Use separate new scratch bases for the two invocations, with
`MTW_JOURNAL_SCRATCH`, `TEMP` and `TMP` set to the respective existing base.
Keep every raw input, child crash log and receipt. Linux must not skip tests;
Windows permissions determine actual symlink execution and any skip must remain
explicit. The same four frozen repository dependencies as r2 are required.

The source remains an experimental point-register archive/prune layer. No
default journal, SDK, business collector, list/relation closure, archive deletion,
database run, formal performance result or organizer acceptance is claimed.
