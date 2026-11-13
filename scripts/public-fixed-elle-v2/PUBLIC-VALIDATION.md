# Public SDK validation against the original fixed-Elle corpus

This directory supplies a read-only, manually dispatched verifier for the v0.5.0
public portable distribution and separately published sealed v2 reference data.
It is validation tooling, not an additional library version or a change to the
library's existing evidence contracts.

The library tag must resolve to
`6fd3410b6eae0efd399ba23f459c37ce29e6c46a`. The validation-data tag points to
the tools commit and is not required to be the library commit. Both HTTP archive
downloads use fixed URLs, sizes and independently pinned SHA-256 values. No
token, cookie, original large campaign ZIP, dependency JAR or author SDK is used.

The manual workflow checks out its own immutable commit, runs boundary tests,
checks all archive members and the public runtime/build manifest, reconstructs
the original upstream reference, then calls classification and independent-option
verification for every one of the 2,000 original captures. The fixed upstream
eligibility denominator is 1,997. Differences, SDK unknowns, timeouts and failures
remain separate; the three original upstream unknowns remain not comparable.

Run with Node.js 24 and Python 3.12 from a clean directory:

```text
python -I -B hosted_public_validation.py --tools ABSOLUTE_PATH_TO_THIS_DIRECTORY --workflow-sha IMMUTABLE_40_HEX_TOOLS_COMMIT --output NEW_EXTERNAL_DIRECTORY
```

`--workflow-sha` records caller-supplied identity in local use; the hosted workflow
also verifies its actual checkout HEAD against `github.workflow_sha`. New output
directories are required. Complete reports, result rows, actual public runtime,
file hashes and logs are retained under `results/`, including on failure.

The upstream results are reconstructed from retained original evidence. This does
not rerun Elle/JVM, establish fourteen-model differential parity or cover relation
predicates. The maintained fourteen-model live Elle comparison and independent
relation interpreter have separate workflows and receipts in the library.
