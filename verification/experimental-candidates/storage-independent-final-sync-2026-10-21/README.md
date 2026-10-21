# Independent r3 final-lock synchronization counterexample

This is a preregistered **unexecuted** filesystem fault case. No local Python,
Node, compiler, database or performance run has been performed. The frozen
expectation requires a real recovery failure to retain an original-owner guard,
poison the live instance, and prevent a fresh `verify()` from declaring complete.
That expectation is never inverted to turn the suspected r3 bug into a pass.

`preregistration-before-implementation.json` records contract SHA
`331697054f37bf8e26fc4f7a5be00d2706cc05bdb27db21156154f173be3ae33`
and `implementationExists:false` before this runner was written.

The program creates the frozen 18-event raw journal through the stable writer,
seals it, adopts it and creates an actual full archive. A separate process calls
the unmodified candidate's `prune()` and exits at `after-manifest`. The real
prepared intent, manifest and lock are copied byte-for-byte into
`prepared-original-bytes/`; no prepared record is constructed or edited by the
test. The crash log and full original archive remain available.

The only injected fault is an `OSError` at the candidate's own store directory
synchronization call once `operation.lock` no longer exists. Every earlier
directory synchronization invokes the actual function. The original plan/token
are passed unchanged to recovery. The fresh verification is then observed with
the fault patch removed. The test neither fabricates `complete` nor changes any
candidate guard, source fact, method return, or expected result.

## Remote execution

Restore these four independent files plus this README under their original
repository path `artifacts/storage-r3-independent-draft/`. Restore the author's
r3 candidate and all four frozen repository dependencies exactly as the main
storage experimental runner already does. No third-party package is needed.

From that restored repository, with a new owned work path:

```text
python -B artifacts/storage-r3-independent-draft/counterexample.py --candidate artifacts/source-window-v3-archive-r3-draft --expected-candidate-index f312fc6d0b6adc6b146954e6b19d0c94ce09d0b5098f5869690d457f8b933962 --work <runner-temp>/storage-r3-independent-first
```

Set `TEMP`, `TMP` and `MTW_JOURNAL_SCRATCH` to an existing task-owned scratch
parent, and `PYTHONDONTWRITEBYTECODE=1`. Do not reuse an existing `--work` path.
The command creates its work directory exclusively and writes exactly one new
`<work>/test-receipt.json`, with one scenario and **nine safety/setup checks**.
Keep the exit code and upload the entire work directory even when nonzero.
Its original inputs, failed expectations and after-state must be retained.

For a CI subprocess, invoke the same argument list with a 180-second timeout,
redirect stdout/stderr to a new log, and inspect the actual receipt only after
the process exits. Record `passed`, `actualFilesystemExecution`, `checks`,
`failures`, `faultInjections`, `afterFailureFreshVerify`, source bindings and the
nonzero exit code independently; do not mark a failing safety assertion passed
because the failure was anticipated. An error before the fault is reached is a
setup failure, not confirmation of the predicted counterexample.

The default author index is r3. A later independently frozen author candidate
can be supplied only with an explicit new `--candidate` and
`--expected-candidate-index`; the original independent contract, input and r3
failure receipt remain unchanged.

The program never deletes the resulting evidence, retries recovery after the
observation, or changes stable code. This process-fault test provides no physical
power-cut guarantee and makes no database or performance claim.
