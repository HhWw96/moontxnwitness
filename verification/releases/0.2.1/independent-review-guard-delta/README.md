# Independent local v0.2.1 guard follow-up delta

Apply this to the original independent adoption bundle with manifest SHA-256
`991bbdc9ac79b5e4495c0cba54ea4267023f7b19101f5776528ef8ca18c639b8`.
The original 106 strict failure, 18 diagnostic assessment, immutable 126 runner,
previous runtime and receipts remain intact. This delta adds a distinct runtime
snapshot and new receipts; no previous file is replaced.

The unchanged 126 checks and independent 152 checks both pass on the new candidate.
31 exact diagnostic-map source/hash bindings also pass. Candidate source/core/capture
hashes are bound in `preparation-fixed-20261023-b.json` and
`assessment-fixed-second.json`. The 126 receipt format lacks a runtime field, so
its identical result has the same digest as the prior successful run; this delta
explicitly binds the new execution to its new snapshot. The 152 receipt includes
its candidate build. Runtime files and manifest were checked stable before/after
copying.

The private JSON byte-budget counter changes representation, preserving the existing
bounds and fallback. No independent V8 root-cause or performance claim is made.
The source packaging review found retained existing assert statements and added
public20 baseline/control closure checks. Tests only force-add known synthetic
`fixture.json` paths before private test files exist. This reviewer did not execute
packaging tests, a compiler, databases, formal timing or a public v0.2.1 download.

Restore the original bundle into a fresh directory, then apply this delta:

```text
python restore-delta.py <restored-base-directory>
cd <restored-base-directory>
node replay-regression.mjs candidate-fixed-20261023-b reproduced-second-126.json
node model-replay-independent.mjs candidate-fixed-20261023-b reproduced-second-152.json
```

Delta restore refuses existing target files. Manifest binds original and compressed
bytes; no redaction was needed. Prior failed formal performance results are outside
this independent review and must remain separately visible in the main release.
