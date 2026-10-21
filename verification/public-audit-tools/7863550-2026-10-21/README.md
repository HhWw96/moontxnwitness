# Fixed public-checkpoint independent audit candidate

This is a new explicit GitHub Actions mode. The preserved local 8f audit and its personal-account authentication remain unchanged. The candidate has not downloaded or executed checkpoint 7863550 on this host. Its local checks use Python syntax, AST, mocked transport/child pipes and small filesystem faults only.

## Frozen target and review

- Repository: `HhWw96/moontxnwitness`.
- Commit: `78635505e4c189c402ba70600632aeaef71ef206`.
- Core run: `39577549262`; PostgreSQL run: `39577549263`.
- Fixed profile requires 563 tests per target/platform and Linux Native563; 347 tested-file bindings (339 non-dist), 76 packaging consumers, and 332 fresh runtime plus 24 MLflow checks for each downloaded artifact origin.
- Profile bytes are checked against a hardcoded SHA256. Neither runtime metadata nor an input parameter can lower these expectations.
- The independently read local summary confirms these counts; the remote audit must still download and verify the actual new public summary and all runtime bytes.

## Exact execution interface

Requires Ubuntu/Linux, Python 3.12 or later and Node 24.13.0. The three executable files must be installed together in a new audit-tool directory: `audit-public-ci.py`, `transport.py`, `profile-7863550.json`. The parent workflow pins the candidate source commit and reviewed file hashes. It must not supply a product checkout/dist/cache as a test input. Setup actions must be reviewed and commit-pinned by the workflow owner.

Fetch step (the only step with `GITHUB_TOKEN`; workflow permissions `contents: read`, `actions: read`):

```sh
python -B "$AUDIT_TOOL/audit-public-ci.py" --mode github-actions --phase fetch --profile "$AUDIT_TOOL/profile-7863550.json" --work "$RUNNER_TEMP/public-audit-7863550"
```

A separate audit step has no `GITHUB_TOKEN`, `GH_TOKEN` or other secret environment variable. GitHub provides `GITHUB_ACTIONS=true` and the exact `GITHUB_REPOSITORY=HhWw96/moontxnwitness` for both steps. Run:

```sh
python -B "$AUDIT_TOOL/audit-public-ci.py" --mode github-actions --phase audit --profile "$AUDIT_TOOL/profile-7863550.json" --work "$RUNNER_TEMP/public-audit-7863550" --output "$RUNNER_TEMP/public-audit-7863550/independent-public-7863550.json"
```

The work directory must not exist before fetch. All accepted files and receipts are exclusive new writes. Do not rerun a failed target in the same directory. Preserve the failed run and create a separately identified directory only for an authorized retry or changed implementation. The first run remains evidence.

Both modes require the exact Actions environment. Audit rejects a nonempty `GITHUB_TOKEN`. No `/user` lookup is made: a repository workflow token is not a personal user token. Child environments remove token/secret/password variables. Requests use HTTPS with ordinary certificate validation. Authorization is sent only to the exact repository's GitHub API paths and never forwarded to a signed blob URL. URL query strings, Location headers, tokens and signed URLs are not recorded.

No Python third-party driver is needed for these fresh read/replay checks. The source journal import and independent raw chain tools use standard-library paths here; the audit does not connect to a database, compile the project or run performance sampling.

## What actually runs

1. Download the two exact completed-success run records, three successful job logs, three actual artifacts and a fresh fixed-commit source ZIP. Artifact digests and sizes must match GitHub metadata and the fixed commit.
2. Safely extract four archives, recompute the MoonBit source fingerprint, check all 347/339 bindings and actual core/capture/wrapper bytes against each build manifest and public source.
3. Check the original platform/Native counts and original database receipts/raw bindings, including the full relation and failure evidence.
4. Execute the same independent runtime checks in two new source directories, using one downloaded artifact dist per origin. A Linux host executes both JS origins; Windows and Native execution are validated from their original CI logs, not claimed as newly executed locally.
5. Run the independent raw-chain and MLflow receipt checks, including actual returned counts and generated receipt digests. Failure of any fresh check marks that stage failed and the final result incomplete.

All five stages have not-executed/running/passed/failed states. A failed early stage leaves later checks not-executed. The final receipt never claims completeness from a successful download alone. The frozen performance receipt is rechecked; this audit does not rerun it. Its graph speed and large search targets pass, while RSS and reduction targets remain false. Stable release, full application integration, participant human acceptance and organizer acceptance remain false.

## Bounds and preserved failures

Reads/hashes/downloads use 64 KiB chunks. Metadata reads are at most 32 MiB (API metadata 4 MiB, profile8KiB); artifact ZIPs128MiB, source ZIP180MiB, job logs4MiB. Fetch has a1200s global deadline, at most3 attempts per download and20s socket timeout. A digest/length disagreement is not retried as a new candidate. Partial bytes and exclusive failure JSON retain the original failure. Metadata is published as accepted JSON only after complete parsing.

ZIP limits: 20,000 distinct entries, 1GiB total expanded, 64MiB/file, 512-character paths, 300s extraction deadline. Traversal, absolute/drive paths and symlinks fail. Runtime child stdout/stderr are drained with a declared8MiB per-stream limit and60/120s timeout; failure preserves the retained prefix and an explicit incomplete-output marker. No large host-local product execution was used to validate this candidate.

## Output and safe upload paths

Use `if: always()` for the evidence upload. Include the paths below relative to `public-audit-7863550`; do not upload the source tree, downloaded ZIPs/parts, copied business database directories or the full fresh source trees a second time:

```text
*.json
*.log
*.stdout
*.stderr
fresh-*/*-process.json
fresh-*/*-output.stdout
fresh-*/*-output.stderr
fresh-*/*-output.failure.json
fresh-*/audit-output/**
fresh-*/dist/core.mjs
fresh-*/dist/capture-core.mjs
fresh-*/dist/build-manifest.json
fresh-*/dist/sdk.mjs
fresh-*/dist/evidence.mjs
fresh-*/dist/moontxnwitness.mjs
fresh-*/verification/faults/mlflow/independent-*/**
source/*/verification/relation-v3/raw-chain-independent-*.json
```

Top-level JSON includes transport/run/job/artifact metadata, accepted-file SHA/byte bindings, member bindings, stage snapshots, copied-input bindings and the final result or fetch failure. The logs are the three public CI job logs. Actual runtime modules are included so a public receipt does not cite hashes alone. Partial transfer bytes stay in the runner work directory; their byte counts/SHA and first-failure JSON are retained in the uploaded evidence. A successful audit prints a final JSON summary with `passed`, `complete`, receipt SHA and all stage states; any failure returns nonzero. Fetch success explicitly reports the audit next phase as not-executed.

## Candidate correction and local tests

The initial driver-literal rewrite was semantically wrong despite compiling. Its exact bytes, first12-test receipt and correction are preserved in `candidate-history`/`unit-artifacts`. The revised tests assert separate literal assignments, Node assert import, absence of journal top-level execution, rejection of that preserved malformed candidate, no half-JSON publication, bounded child failure behavior and failed-stage completeness. Local test receipts are separate from the as-yet unexecuted remote audit.
