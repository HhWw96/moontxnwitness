# Frozen v0.1.0 direct baseline

This directory records an **absolute baseline**, not a claim that the next
version is faster. The earlier v0.0.6 comparison and its failed runs are retained
unchanged in `verification/releases/`.

From a Git checkout with the `v0.1.0` tag, Node.js and Python installed:

```text
node scripts/baseline-v010.mjs
node scripts/baseline-v010.mjs --quick
node scripts/baseline-v010.mjs --refresh-download
```

The default command performs five warmups and 30 timed observations per
scenario/phase in each of three independent processes. `--quick` performs only
one warmup and three observations in one process, records `smokeOnly: true`, and
cannot establish formal acceptance. Avoid builds, other benchmarks, database
load and archive extraction while collecting formal measurements.

## Engine provenance

The engine is extracted from the published v0.1.0 portable ZIP, never from the
current working tree or `dist/core.mjs`. A local copy of the exact published ZIP
may be reused; `--refresh-download` forces an anonymous public download. All
three digests below are pinned in the script and verified before a measurement:

- Published ZIP SHA-256:
  `d7495482b8267f327edf40e95111acbd2502290fc97e5f1e5e1203e7bc59488c`.
- Compiled engine SHA-256:
  `6c76b3be6c45ff633232568b3ffed3c1393ade3b4d012ee5c21c49cbb8dcf97b`.
- Published source fingerprint:
  `dcc8653278a9f98dc6056d23c8b7d7d9db3fc6b8406b22987fc9ff03997dd830`.

The published build manifest identifies compiler `v0.10.14+7d59c7ec9` and Moon
`0.1.20260920`. The local immutable tag must resolve to
`540a9e390ed54f8b5e6d3b87aba3367c971c18b3`; the script independently computes
its source fingerprint with the same source-file rules as the release build.
This verifies the source identity associated with the pinned published build;
it is not a new compiler rebuild or a proof of compiler correctness.

## Frozen workload and full outputs

`verification/fixtures/v010-comparison/manifest.json` fixes input hashes,
generator hashes, transaction/operation counts and seeds before optimization:

- All 15 original v0.1.0 workloads, including the seven old graph workloads,
  6–8 transaction search, controls and small reductions.
- Four 9–12 transaction unsatisfiable search workloads, using registered
  xorshift32 seeds for transaction order. An independent register interpreter
  checks that none of the six serial orders of the A/B/R projection works;
  remaining transactions only read disjoint initial `z0`.
- The 512 transaction reduction workload: 510 disjoint read-only transactions
  plus a two-transaction write-skew witness. Expected output is two retained
  transactions with a completed transaction-singleton minimality check.

The new search family is a controlled difficult family, not representative of
all possible 9–12 transaction searches. Input files are checked for exact
equality on each invocation; changing a workload cannot silently update its
baseline. `legacy-fixtures-v010.mjs` is taken from the immutable release tag.

`outputs/*.json.gz` contains each complete JSON output, losslessly compressed;
the uncompressed SHA-256 and byte count are in every receipt. No dependency or
provenance is omitted and no summary is substituted. Every process checks the
status/witness/minimality expectations and the frozen full-output digest.

## Measurement interpretation

Full measurements include MoonBit JSON input, complete JSON output and client
JSON decoding, as in the existing performance worker. Input-object preparation
is outside the timed section. Independent phase hooks measure parse, inference,
SCC/shortest cycle, exact search, reduction and report rendering with prepared
input; those isolated numbers do not add up to an end-to-end analysis. Raw-event
capture and normalization are new capabilities and are measured separately by
their own business on/off experiments, not attributed to this old core.

Receipts retain every sample, per-process median/P95, cold module loading,
first analysis, process peak RSS and complete-output size. Summary values are
medians of the corresponding three process statistics. RSS is captured before
hashing or writing the stored output. Formal receipts include all 20 full
scenarios and 15 representative phase measurements.

`manifest.json` points to the latest successful formal and smoke records.
Timestamped records are never overwritten. A failed attempt remains
`passed: false` with the completed observations and error. Larger artifacts
(downloaded ZIP/core and child outputs) are in the recorded `artifacts/` folder;
tracked receipts retain the raw timing samples and compressed expected reports.

A future comparison must rerun both engines on the same machine and toolchain
in alternating processes, with the same inputs, budgets, model and full output
scope. The old v2-compatible path and a new v3 classification path are distinct
comparison scopes. Do not compare a new summary with this complete-output
baseline or turn a historical machine observation into a general speed claim.
