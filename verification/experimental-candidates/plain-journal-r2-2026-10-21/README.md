# Manual CI candidate for bounded ordinary-table capture

This directory is ignored, static CI preparation. No workflow, wrapper test, PostgreSQL test or performance measurement has been executed from this directory. Only source copying/hash binding and Python AST parsing are allowed locally for this handoff. The underlying revised profile has a separate actual local 31/31 FS/mock receipt; that is not a CI or actual-PG result.

## Frozen input

The original `486c42e0968bc0d195cb36845ce933a38bd9291afd04b09ad153added89f23dc` candidate remains unchanged. Independent static review found its unbounded source-index read. The new profile revision is:

`artifacts/plain-v3-journal-r2-draft/candidate-index.json`

SHA256 `3a13b37fdf4324ceb8c899b3616d86c92e75aa256eca9d87668ddfcde46ee50a` (11181 bytes).

The R2 first 30-test run exposed three Windows ctime API differences and remains preserved, including its source snapshot and a public summary bound to the unmodified private raw receipt. After the same-API file-descriptor identity repair, the preregistered growth and Windows-ctime cases passed with all original inputs unchanged: 31/31, zero skips. The old 29-case receipt is historical evidence only. New actual-PG execution is still missing.

`bundle/repository/` contains exact copies of the 54 R2 candidate files, its candidate index, six runtime Python dependencies and the original hash-locked optional driver requirements: 62 files in their **original repository-relative layout**. `bundle/bundle-index.json` binds every byte. The original 486 candidate and older receipts are inside the R2 history; they are retained as data and are not executed as current source.

## Parent review and publication boundary

Proposed public root: `verification/experimental-candidates/plain-journal-r2-2026-10-21/`.

The parent can copy this entire directory into that public root after review, then copy `manual-workflow.yml` to a new manually dispatched workflow under `.github/workflows/`. Preserve bundle bytes with a matching `-text` Git attribute; the existing `verification/experimental-candidates/** -text` rule already covers the proposed root. Do not normalize CRLF in a hash-bound snapshot. Do not replace root default observer APIs or any previous candidate/evidence. `freeze_bundle.py` is the author-time source copier and is retained for provenance; it is not the public workflow entry point and should not be run from the relocated public directory.

The wrapper's candidate hash and repository prefix are fixed constants. Its `verify` mode checks every manifest file, the exact protected candidate index, all candidate/dependency/requirements bindings, no missing or extra source, and read/copy budgets. The bundle is not an authentication protocol; the reviewed Git commit and downloaded artifact bindings remain separate evidence.

## Isolated execution

The proposed workflow permits only `workflow_dispatch` with an immutable lowercase 40-character source commit. It records the checked-out source separately from the workflow commit. Actions are SHA-pinned. PostgreSQL is the exact existing workflow image:

`postgres:18.6-bookworm@sha256:afc7e2d441324c0388fa80c3d24f733b4194a4eb7f47dd8ee2b08eb1a24a647c`.

It uses an ephemeral CI service database `mtw_plain_test`, fixture-only user/password, a dynamically allocated local port and the original `examples/postgres-requirements.txt` installed with `--require-hashes --only-binary=:all:`. No arbitrary endpoint, production credential, untrusted install script, Node, MoonBit build or benchmark is required.

After bundle verification and driver installation, the wrapper creates a new `--work` directory and restores all source files to `restored-repository/`; it never executes the normal checkout's changing observer files. It runs the 31 FS/mock cases first. Only the exact passing count, zero skips, actual filesystem marker and unchanged protected source allow the seven actual-PG scenarios to start. The PostgreSQL receipt must report actual server version 180006, all seven preregistered names in order, unchanged source bindings, the expected complete/incomplete diagnostic windows and every raw-file digest. `coreProofImplemented` and `formalEligible` must remain false.

Example parent-controlled calls after copying the bundle:

```text
python -B verification/experimental-candidates/plain-journal-r2-2026-10-21/restore_and_run.py verify
python -B verification/experimental-candidates/plain-journal-r2-2026-10-21/restore_and_run.py run --work NEW_WORK_DIRECTORY --fixture-port ISOLATED_SERVICE_PORT
```

The fixture endpoint is constructed only from that local service port and the fixed fixture credentials. Inherited DB endpoints, secrets, Python paths and adapter configuration are excluded from child environments. The caller must supply the owned ephemeral service; the wrapper does not create, stop or access any other database. Missing driver, failed unit setup, missing database, timeout or incomplete receipts remain failed/not-executed states, never a pass.

## Evidence

Each child has an unmodified combined stdout/stderr log. The work directory retains the actual raw source journals, SQLite indexes, separate source logs, all test scratch folders, scenario receipts, source-before/after and byte bindings. An always-uploaded context directory retains checkout metadata, bundle verification, hash-locked driver installation output, wrapper stdout, Docker server logs and actual image ID. Failure outputs are uploaded as well. The execution receipt reports which child actually started and whether actual PostgreSQL scenarios occurred.

Do not call a passing CI result SQL-core proof, full-application capture, safe live-window handoff, 4096-key/60-second support, formal C/A, physical power-cut durability, human acceptance or organizer approval. Those gates remain independent.
