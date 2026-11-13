# Pure-data evidence and SDK comparison

The sealed `r5` evidence directory can be published as one compressed **data and
source-only attachment**. Keep its `bundle-manifest.json` and directory contents
unchanged. Distribute these supplemental tools alongside it in a separate
directory, with the attachment SHA-256 and tool hashes in the release notes.
The 106 MB original campaign ZIP and its JARs do not need to be mirrored for this
offline data verification mode.

## Offline data verification

Python 3.11+ and the standard library suffice. No MoonBit toolchain, Java,
Leiningen, JAR download or SDK is loaded.

```powershell
python -B verify_offline_bundle.py `
  --bundle PATH/sealed-r5-directory `
  --expected-manifest-sha f3a46e697c74a1ef03e33d2803adbc495040e274f3a315a00cf2002dd3d8b89d `
  --output PATH/new-offline-receipt.json
```

The caller must obtain the manifest hash from an independently verified release
checksum, not merely trust a sidecar delivered beside unknown data. The tool
checks every file against that manifest, verifies the fixed auditor source
before importing it, and reconstructs all 2,000 original captures into all forty
retained prepared EDN batches. It rechecks control identities, ledger chains,
actual raw/summary bindings, typed upstream judgments, and equality with the
sealed cases and old `bb5` cases. Source excerpts, options and the retained
runtime manifest are checked without evaluating Clojure.

This verifies retained evidence and conversion, **not a new Elle execution**.
The receipt explicitly says that Java dependencies were not rehashed and the
original large ZIP was not reverified when absent. To additionally check that
original archive's immutable SHA-256, append:

```powershell
--original-artifact PATH/artifact-12578114941.original.zip
```

That optional archive hash check does not execute Elle or claim a new runtime
dependency audit. The existing full-audit receipt remains identified as
historical evidence. Missing data or a mismatched file is an error, not a skipped
check. Do not add the supplemental tools inside the sealed evidence directory;
the offline verifier rejects unindexed files there.

## SDK comparison after the reference has been sealed

The comparator fixes the original job hash, new upstream reference hash and
`serializable` model. It never creates or repairs a reference from SDK results.
Node's built-in modules suffice. Run mock tests first:

```powershell
node --test test_compare_sdk_v2.mjs
node compare_sdk_v2.mjs `
  --job PATH/fixed2000-job.original.json `
  --reference PATH/sealed-r5-directory/upstream-reference-v2.json `
  --runtime PATH/dist `
  --expected-version 0.5.0 `
  --expected-core-sha 723d405f31a052fd71178ac53f657a1e6fdf7ff83649db42b6f967fc0d4a1847 `
  --output PATH/new-sdk-comparison
```

The core hash above identifies the frozen local build. A later public-package
comparison must independently verify the public download, supply its actual
core hash and use `--runtime-origin public-download`; the label alone is not
proof of package transport or publication.

Each case receives independently authored model/budget options for both
classification and verification. Lists request
`captured-list-original-serial/v1`. SDK source-profile changes, unknowns and
errors do not remove a case from the fixed 1,997 eligible positions. A separate
worker enforces a 30-second wall-clock limit per case, records actual classify
and verify phases, and permits subsequent cases to continue after a worker
failure. The runtime and version are bound before and after comparison.

All inputs, actual upstream raw/summary results, complete available SDK reports
and verification results are retained in `reports.jsonl.gz`.
`items.jsonl` and `summary.json` distinguish matches, differences, SDK unknowns,
upstream-not-comparable results, timeouts and failures. Summary counters also
retain SDK disposition and the immutable eligible denominator independently.
There is no claim that an upstream unknown is a successful Boolean comparison.
