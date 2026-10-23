# Independent local v0.2.1 review evidence

This is an independent AI review of a local build candidate. It does not establish
publication of v0.2.1, public-package installation, human acceptance, production
adoption, or organizer approval. No compiler, database suite or formal performance
measurement was executed by this reviewer.

The original strict comparison remains **failed**: 106 equal judgments, 88 equal
complete outputs after only explicit engine headers, and 18 generated invalid
compiler-coordinate differences. The original public20 engine itself verifies and
packages all 18 invalid reports; the first candidate could replay none. Those
receipts and runtime bytes are retained unchanged. Exact expected-side source
location compatibility was then implemented by the author. The frozen pre-fix
126 checks now pass, and an additional independently written 152 checks across
8 list/relation public20 capsules pass. The latter separately reconfirms producer
reports and capsule bytes, specialized wrappers, each of the four digests, and
rehashed semantic tampering. This is a replay result, not a rewritten assertion
that all strict original outputs match.

`manifest.json` records both the original and compressed SHA-256 for every file.
Files are losslessly compressed and content-deduplicated. No evidence was redacted.
All original scripts are byte-for-byte retained, including the frozen 126 runner.
The 31 exact mapping source/hash bindings, 71 generated locations, all 18 capsules,
the 106 input generator and original inputs, differential outputs, two 0.2.1 runtime
snapshots, public20 runtime, and post-fix receipts are included. The public20 runtime
also matches the existing published-package provider path recorded in the manifest.

## Reproduce old capsule checks in a fresh directory

Requires Python 3 and Node.js with ESM support. Restore first (destination must not
exist), then enter that directory:

```text
python restore-evidence.py <fresh-review-directory>
cd <fresh-review-directory>
node replay-regression.mjs candidate-fixed-20261023-a reproduced-126.json
node model-replay-independent.mjs candidate-fixed-20261023-a reproduced-152.json
```

Both commands should exit 0. New receipt names avoid overwriting archived results.
`replay-fixed-first.json`, `model-fixed-first.json`, `assessment-fixed-first.json`
and `static-source-binding-checks.json` are the completed local review receipts.

## Reproduce the original failure separately

```text
python restore-evidence.py <another-fresh-directory> --mode strict106
cd <another-fresh-directory>
node review.mjs
node assess.mjs
```

`review.mjs` is expected to exit 1 and record 18 strict output differences;
`assess.mjs` records the coordinate-only assessment and public20 capsule capability.
Use a separate fresh directory because the original scripts deliberately refuse
to replace existing receipts and output folders. Historical comments in the frozen
106 generator are retained: its seeded chains contain 1-5 transactions, and its
literal escaped surrogate spellings do not establish a true-unpaired-surrogate test.

All reproduced outputs must be assessed on their own. Do not change expectations
or replace a failed first receipt to obtain a pass.
