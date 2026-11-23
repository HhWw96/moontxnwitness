# Replaying a captured PostgreSQL write skew

Download and extract the GitHub portable archive. From its root, with Node.js
20.11 or newer, run the example. PostgreSQL and network access are unnecessary
for offline replay. The optional output path must be new.

```sh
node examples/point-window-replay.mjs --html witness.html
```

The example verifies the file manifest, then replays the original analysis and
reduction capsules using separately supplied SQL configuration, source policy,
target model and budgets. Open `witness.html` to trace the original SQL and
business-delivered values to row versions and the two `rw` dependencies. The
verified selection keeps two of five transactions and is single-minimal under the
selected model and source-closure rules. The three remaining transactions in the
original window are read-only observations of a committed writer.

## Same business rule, different transaction outcome

The fixture starts with two enabled rows on PostgreSQL 18.6. At least one row
must remain enabled. A transaction may disable its own row when it observes both
rows enabled. The two clients read before either writes, then each attempts its
update and they issue commit in the same order in both concurrency runs.

| Run | Actual database outcome | Offline model result |
| --- | --- | --- |
| Repeatable Read | Both updates commit. Both rows are disabled. | `serializable` refuted by a `G2-item` cycle. |
| Serializable with complete retry | PostgreSQL returns `40001` on the second commit. Its fresh retry observes the first update, skips the second update, and commits. One row remains enabled. | The original window includes the rolled-back attempt, so the model result is `unknown`. |
| Ordered Serializable control | The same rule runs in serial order. Both transactions commit and one row remains enabled. | Source-verified serial certificate, `checked-compatible`. |

The retained evidence comes from a disposable fixture. A file digest checks
bytes relative to the manifest, and semantic verification recomputes a result
under caller-supplied options. The capsule carries no database authenticity
claim. Offline replay does not rerun SQL.

## Run the database cases again

The portable archive can capture and replay the three isolation outcomes in
five independent rounds. Install the pinned psycopg and SQLGlot dependencies
from `examples/orm-requirements.txt` and
`integrations/python/requirements-configured-sql.txt`. Supply a disposable
PostgreSQL 18.6 instance through an environment variable.

```sh
node scripts/postgres-point-window-demo.mjs --runtime dist --dsn-env MTW_DISPOSABLE_DSN --output new-run
node examples/point-window-replay.mjs --fixtures new-run/round-1/fixtures --html witness.html
```

On Windows, `--bin PATH_TO_POSTGRES_BIN` starts an owned instance for each
round. Use an unused output path under `D:\CodexScratch` for the Windows
producer. Each round retains the database receipt, fixture checksums,
independent replay and HTML explanation. The command verifies all three
fresh capsules with the same runtime and records the compatible, refuted
and incomplete gate results. PostgreSQL CI also submits the first newly
captured refutation to the pinned public Action and requires exit 1.

## Run the separate FastAPI Users case

Build the runtime in a source checkout and install both the pinned ORM and
configured adapter requirements. Use PostgreSQL 18.6 binaries for the disposable
local cluster and the original FastAPI Users SQLAlchemy checkout at
`6397ace506d829a2ee12786da5d724c3f4c6b634`. On Windows set
`core.autocrlf=false` on the upstream checkout before checking out that commit
so the byte audit can compare it to the original Git blob. The application needs
`fastapi-users==14.0.2` for the upstream fixture.

```sh
npm run build
python -m pip install --require-hashes -r examples/orm-requirements.txt
python -m pip install --require-hashes -r integrations/python/requirements-configured-sql.txt
python -m pip install fastapi-users==14.0.2
node scripts/configured-business-window-demo.mjs --runtime dist --bin /path/to/postgresql/bin --upstream /path/to/fastapi-users-db-sqlalchemy --output new-run
```

The original FastAPI Users methods run with and without capture across 30
fixed CRUD input seeds. The duplicate-email case checks the actual unique
constraint error `23505`, driver rollback, and successful follow-up transaction.
Its model verdict remains `unknown`. This upstream integration is independent
of the primary write-skew fixture. [Adapter and regression details](configured-async-window-v2.md)

The wrapper retains the raw receipt and runs analysis, reduction, and capsule
checks. It stages `orm-gate/ordered.capsule.json`, `duplicate.capsule.json`,
`config.json` and `policy.json` for the Action. The PostgreSQL workflow
rechecks both windows with a pinned public verifier. The ordered CRUD
window exits 0. The duplicate-email window retains a real rollback and a
new committed transaction, and exits 2 with a reproduced `unknown`.

To stage the separate write-skew offline fixture set from that new receipt, run
`node scripts/stage-point-window-replay.mjs --receipt new-run/database/receipt.json --runtime dist --output new-fixtures`.
For exact offline replay of the new capture, use `new-fixtures` as the
`examples/point-window-replay-data` directory in a disposable copy of the example.

## Use the verification step in your CI

Have your capture job write an analysis capsule and keep the configuration,
policy, budget and expected archive digest under CI control. The GitHub Action
runs with Python 3.12 and Node.js 24 in the calling job. Pin the Action to the
reviewed release. Record the SHA-256 for the selected ZIP from that release's
checksum manifest in your repository variable before running the job.

```yaml
- name: Verify the captured window
  uses: HhWw96/moontxnwitness/.github/actions/check-point-window@v0.7.1
  with:
    release-version: '0.7.1'
    archive-profile: point-gate
    point-gate-sha256: ${{ vars.MTW_POINT_GATE_SHA256 }}
    config: ci/point-window-config.json
    policy: ci/point-window-policy.json
    capsule: artifacts/database-window.capsule.json
    max-point-checks: '1000000'
```

The Action checks the selected archive's exact SHA-256 before loading the verifier.
The default `portable` profile continues to use `portable-sha256`. The
`point-gate` profile uses `point-gate-sha256` and runs the same verifier bytes.
Its `exit-code` and `verdict` outputs retain the gate result for subsequent
steps. The calling job fails for exit codes 1 and 2. The verifier also runs
directly from an archive previously extracted to `vendor/moontxnwitness`.

The stable inputs are `release-version`, `portable-sha256`, `capsule`,
`config`, `policy` and optional `max-point-checks`. The default budget is
1,000,000 and the caller may lower it. Use a controlled single-table
PostgreSQL point window with configured int64, C-collated text or UUID
primary keys, complete native results, confirmed transaction outcomes and
source installation evidence. Capture gaps remain visible as incomplete
results. The package includes one compatible capture, one verified
refutation, and one rollback and retry for a fresh consumer to replay.

```yaml
- name: Recompute the point-window Serializable result
  run: >-
    node vendor/moontxnwitness/examples/check-point-window.mjs
    --config ci/point-window-config.json
    --policy ci/point-window-policy.json
    --max-point-checks 1000000
    artifacts/database-window.capsule.json
```

Exit code `0` means the source-bound model report recomputed and established a
compatible result for this window. Code `1` indicates a verified model
refutation. Code `2` covers incomplete evidence, verification or input errors.
The gate treats the entire captured window with a rolled-back attempt according
to its actual coverage. Run `node scripts/point-window-ci-test.mjs` to exercise
the passing result, the actual counterexample, coverage and source gaps, a
tampered report with recalculated digests, and a caller-budget mismatch.

A separate consumer can verify the shared normalized inputs using the public
MoonBit library. This creates a new MoonBit project and installs only the
requested registry version. The JavaScript runtime comes from an extracted
portable archive. Set `--module-version` to the matching version.

```sh
node scripts/verify-point-window-moon-consumer.mjs --runtime dist --module-version 0.7.1 --output new-moon-consumer
```

The consumer compares the normalized history digest, `serializable` decision
and full model judgment for the counterexample and ordered control. The SQL and
writer evidence are first verified by the capsule runtime. The separate core
comparison begins at the normalized relation-history boundary.
