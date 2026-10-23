# Independent v0.2.1 stable-default withdrawal review

This delta selects a new stable default after the structured optimization was
withdrawn. It references original base manifest
`991bbdc9ac79b5e4495c0cba54ea4267023f7b19101f5776528ef8ca18c639b8`.
Prior candidate files, first failures, formal-performance failures and prior pass
receipts remain separate evidence. No prior result was reused for this new build.
The previous candidate delta may also be retained; it is not required to apply
this stable delta after the original base bundle.

The new default independently passes the original **unchanged** 106 strict script:
106 normalized and complete SDK outputs equal public20 after only explicit engine
headers, with zero strict differences and 106 equal judgments. The original
unchanged126 replay checks and independent152 model checks pass on this same new
runtime. Its manifest was checked stable before/after copying. The separate
runtime, input plan, runner, stdout, receipts and SHA bindings are included.

Four normalizer files are byte-for-byte identical to public commit cab3320;
all original629 test declarations are preserved, current629, with no removed or
added declarations. The active API diff is only explicit released-engine header
compatibility plus a comment. Structured fast paths and generated diagnostic
coordinate mapper are absent from the active core. Withdrawn source/runtime archive
hashes are recorded separately without adding those candidates back to the default.

This is independent AI review of a local build. It does not establish performance
improvement, a proven V8 cause, public v0.2.1 installation, human acceptance, production
adoption or organizer approval. This reviewer ran no compiler, database or formal
performance measurement. The frozen126 receipt lacks build metadata, so its equal
contents retain the prior SHA; this delta's assessment/preparation explicitly bind
this new execution to the stable runtime.

Restore the original base into a fresh directory, then apply this delta:

```text
python restore-delta.py <restored-base-directory>
cd <restored-base-directory>
node replay-regression.mjs stable-default-20261023-c reproduced-stable-126.json
node model-replay-independent.mjs stable-default-20261023-c reproduced-stable-152.json
```

To rerun the strict106 comparison without replacing the archived receipt:

```text
python prepare-strict-reproduction.py <restored-base-directory> <fresh-strict-directory>
cd <fresh-strict-directory>
node review.mjs
```

All three commands should exit0. `prepare-strict-reproduction.py` only copies
original scripts/data/runtime; it does not alter the frozen runner. Restore refuses
existing targets and verifies both compressed and original digests. No redactions
were needed. This delta is not a public-release review.
