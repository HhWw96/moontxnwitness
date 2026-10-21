# Archive recovery revision 3

The preceding independent Linux and Windows run found a real recovery failure in
revision 2. All 33 new cases passed, but the unchanged older recovery case failed
on both platforms. Its actual downloaded ZIPs, hashes, receipts and logs remain
under `../storage-r2-2026-10-21/first-ci-39582277986/`.

Revision 3 checks the prepared intent, operation token and retained roots before
marking recovery as mutating. An invalid request must not persist a marker that
prevents a later valid recovery. The original checks also remain at the mutation
boundary. Five additional cases cover rejected requests and real recovery faults.

This bundle freezes candidate `f312fc6d…b933962`. The manual storage workflow runs
38 incremental cases and 32 unchanged regression cases against the new source on
each platform. Results are pending until actual execution. All limits and the
point-register-only scope of the original contract remain in effect. Passing this
suite would not establish full capture integration or stable API acceptance.

```
python -B scripts/experimental_storage_ci.py --candidate r3 --work /path/to/new/mtw-storage-r3
```
