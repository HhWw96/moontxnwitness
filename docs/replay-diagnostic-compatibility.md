# v3 diagnostic replay compatibility

Stable v0.2.1 retains the four public v0.2.0 normalizer source files byte for byte.
Their generated compiler coordinates therefore remain unchanged. Verification
recomputes the complete report and translates only explicit supported engine
headers. It does not remove diagnostics, coordinates, observations or budgets.
The public20 model/execution/invalid capsules and semantic/digest tamper cases
remain part of the active regression and fresh-consumer checks.

The withdrawn structured candidate moved 71 guard locations. Its precise
expected-side mapping and 28 additional core tests are preserved inside
verification/experimental-candidates/v021-structured-withdrawn/candidate-2-source-runtime.zip,
alongside the original independent failures and post-fix review bundles. That
mapping is not called by the stable default; using its old table with restored
sources could rewrite a coincident location and would be unsafe.

The candidate was withdrawn because formal tail-latency controls failed. Its
657-test results remain experiment results; the stable default retains all 629
published core tests and adds actual public20 capsule checks. No baseline test
was removed and no failed performance receipt was changed to pass.
