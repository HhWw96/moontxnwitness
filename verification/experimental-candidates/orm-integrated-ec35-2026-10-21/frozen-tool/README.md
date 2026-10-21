# Independent24 replay of the integrated local build

This candidate is frozen before invoking the new module. It preserves the original independent r2 driver (6f2bf2fe...) and the original24-case contract (2e30dccc...) byte-for-byte. The two raw inputs and24 full baseline reports come from independently downloaded successful run39595025070; all input hashes/expected statuses remain unchanged.

The target is explicitly a current local build: source ec35d4a61267af9c5600baf6e62197219aa979fdc1f36ca17a9a4bc40f1d9787, main95c96abb..., capture82294d92.... It is not represented as the old public3b536b runtime, and no old public signature is extended to it. SDK/CLI bytes are bound and copied, but this command executes only the original independent24 direct-core probes; root's new12 SDK/CLI checks and later fresh public-wrapper acceptance are separate evidence.

Do not start until root grants a Node execution window. From the repository:

    python -B artifacts/orm-integrated-independent-replay-v1/replay.py --runtime-dir dist --work artifacts/orm-integrated-independent-run-NEW

The work directory must be new; use --node for an explicitly selected executable if necessary. No GitHub token is permitted in the parent; sensitive environment variables are removed before the bounded child runs. Actual Node version/platform are retained in the original driver's result, not silently represented as the prior Linux environment. No database, compilation or performance measurement runs here.

Before copying or executing, the wrapper recomputes the complete current MoonBit source fingerprint and actual build/core/capture/SDK/CLI/evidence hashes against target-profile.json. The fresh directory receives only those new actual build bytes, the unchanged independent driver/contract, and frozen original raw inputs. The profile given to the unchanged driver contains the new module binding and explicitly says current local build rather than borrowing the old artifact's origin.

The final immutable receipt separates semantic24Passed, all24InputsAndExpectationsUnchanged, valid4OutputBytesPassed, invalid20OutputBytesPassed and strict24OutputBytesPassed. Full bytes are required for overall passed. Compiler error location changes remain recorded differences and are not normalized or treated as passed; all failed original reports/inputs remain intact. A separate compatibility decision can inspect these differences later without rewriting this strict result.

Six lightweight checks passed: Python syntax, exact readonly source/build preflight, fixed driver/contract, credential removal, wrong-binding refusal and retention of exact diagnostic differences. No new-module Node execution has occurred at candidate freeze. This evidence cannot establish full application capture, model coverage, public publication or stable release.
