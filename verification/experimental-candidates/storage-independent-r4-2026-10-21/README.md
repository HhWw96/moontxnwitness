# Independent r4 protected-final-sync failure probes

The two input/safety cases were frozen before independent implementation and before reading the r4 source: original contractSHA66e3b568…; the later additive stable-mutex amendmentSHA3d801be3… does not replace it. The exact final callsites are separately bound to candidate223e61bc… and managed.py290913bd….

This runner is unexecuted locally. Only Python syntax was checked. Its purpose is to exercise actual filesystem/native-lock failure behavior on a separate approved CI runner; it never runs Node, MoonBit builds, PostgreSQL or performance sampling.

## Actual fault evidence

Each case starts from its own actual sealed18-event journal and archive. A real child enters prune, independently records actual intent/manifest/owner/permanent-mutex bytes and native contention, then exits73 at the prepared manifest point. The stage callback merely triggers a crash; its name is not accepted as evidence of preparation.

Recovery injects OSError only when the **actual bound callsite** `_release_operation:331` invokes `point.sync_directory(store)`. At that point the runner must independently observe manifest.pending=null, matching completedPlan, no remaining intent, the exact original owner nonce/token and native lock contention on the permanent coordination.lock. A separate native probe process implements fcntl/msvcrt locking directly; it does not call the author's lock helper or trust an ownership flag.

The second case also injects diagnostic persistence OSError at the actual `_failure_marker:357` Path.open(operation-failed.json, xb) request. It requires the same source/owner/mutex evidence. The exact primary data-sync exception must survive this additional failure. An ordinary source sync or a diagnostic sync is never silently substituted for the registered target.

Required results remain: an owner-bound persistent guard, a poisoned live instance with incomplete public verification, and an incomplete fresh verifier. The second case specifically requires the original owner authority to survive failed marker IO. Original source index, SQLite cache, source fence and archive bytes, plus the permanent coordination inode/content, must stay unchanged. Both cases and all24 checks must actually execute successfully for passed=true.

## Frozen revision and remote invocation

Restore frozen author candidate223e61bcb41b64f2d47f0d96e8c8e99e88a1a9c1fed856467a7b01a45c920124 into the original repository layout `artifacts/source-window-v3-archive-r4-draft`, including its19 bound files and4 root dependencies. Publish/copy this independent directory separately; do not import or run the author tests to determine these expectations.

```sh
python -B /path/to/independent/counterexample.py --candidate /repo/artifacts/source-window-v3-archive-r4-draft --work /new/runner-temp/independent-r4
```

The work path must not exist. Use each platform's Python3.12 and existing exact dependency snapshot; no external SQL driver/database is needed. The two cases run sequentially in fresh subdirectories. Every child/native probe is bounded; a setup/resource/placement error is preserved and stops further scenarios. No retries or cleanup repair a failed source.

Outputs include `independent-r4-receipt.json`, both case-receipt.json files, actual child logs/prepared bytes, native-probe results, exceptions and before/after file bindings. Stdout gives passed/complete/cases/checks/receiptSha256. Upload the entire new small scenario directory even on failure, together with original candidate index/dependency hashes. The runner's success requires two completed scenarios,23 case checks and one final source-immutability check.

## Separate boundaries and history

The old r3 counterexample targeted a normal sync after owner lock deletion. Its three-of-nine safety failures per platform remain intact. That old premise is inapplicable/not-executed in this protocol, never counted as a passing test. The earlier pre-stable r4 unlock/unlink race and its exact source snapshot also remain archived; the final source uses a permanent OS coordination inode and removes temporary owner authority while holding it.

A purely native unlock/close exception **after successful data commit and owner cleanup**, followed by failure of every diagnostic write, may be unobservable to another process. That stated boundary is not executed or accepted by these cases and never waives a data/source/intent synchronization failure. POSIX directory-sync attempts and process faults are not a physical power-cut proof; Windows standard-library directory durability remains limited.

The author83-case results are separate evidence, not a substitute for these two independent cases, and neither evidence alone is stable API, full capture/application or organizer acceptance.
