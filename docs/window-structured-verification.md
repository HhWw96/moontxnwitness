# Explicit structured verification profile

The profile uses the same independently reconstructed window and relation-model
reducer, while retaining the internal report as structured MoonBit data during
verification. It removes serialization followed by parsing of its own report and
reuses canonical bytes for comparison and hashing. External reports still pass
strict parsing, independent configuration and budget checks.

```js
import {
  analyzeConfiguredWindowV4, verifyConfiguredWindowV4,
  reduceConfiguredWindowV4, verifyConfiguredWindowReductionV4,
  explainConfiguredWindowV4,
} from './dist/configured-window-v2-structured.mjs';
```

Arguments and successful report semantics match the
[configured-window APIs](configured-window-v2-sdk.md). Select the profile through
this explicit module. The default SDK and CLI keep their original verification
implementation and do not import its additional core. The optional profile is
listed separately in capability metadata and bound by the two-file
`structuredWindowRuntimeSha256` inventory; its shared host is bound by the
original window inventory.

Complete successful reports, counters and source mappings are compared across
profiles on original PostgreSQL windows. Unknown outcomes preserve their safety
flags; diagnostic source locations can differ. Both verifiers retain the
64-container self-report limit, including empty containers, while scalar leaves
do not consume a container level. The explicit profile also bounds oversized
malformed-input failure text to the same 32/64 MiB output contracts.

## Measurement protocol

The first attempt applied structured verification to the default implementation.
Its five target verification workloads improved 1.314× geometrically and their
peak RSS ratio was 0.842. A common model control's P95 was 55.801 ms against
45.133 ms, exceeding the `max(10%, 2 ms)` limit. That attempt was withdrawn from
the default path; all 1,260 samples and the exact failed runtime were retained.

The explicit module is a separate configuration. Its measurements include the
cost of loading its smaller dedicated runtime, so those memory/cold-start
results describe the complete selected profile. Common controls use the default
SDK. Measurements retain complete output and compare its canonical digest,
including all evidence and counters; no source or edge output is trimmed.

Create inputs from an original successful PostgreSQL campaign:

```text
node scripts/window-verification-performance-inputs.mjs --baseline <baseline-sdk> --candidate <default-sdk> --candidate-structured <explicit-profile> --receipt <original-receipt> --output <new-input-directory> --baseline-commit <commit> --candidate-commit <commit>
```

After all local compilation, database and packaging jobs stop, set the generated
configuration's `exclusiveExecution` to true and run:

```text
node scripts/window-verification-performance.mjs --config <config.json> --output <new-measurement-directory>
```

Formal timing uses five warmups, thirty samples and three batches of independent
processes. Separate memory and cold-start workers record peak RSS, full output
size and process import/first-call cost. Baseline/candidate order alternates;
common controls retain the original P95 threshold. `--smoke` is explicitly
nonformal. The harness, inputs, runtimes and raw samples are digest-bound.

The baseline is the locally frozen source-closed-window implementation at
`1b8868695`, not an earlier public release without these APIs. Reference results
from older model-analysis benchmarks remain separate.
