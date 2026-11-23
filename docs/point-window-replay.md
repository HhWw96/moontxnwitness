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

Build the runtime in a source checkout and install both the pinned ORM and
configured adapter requirements. Use PostgreSQL 18.6 binaries for the disposable
local cluster and the original FastAPI Users SQLAlchemy checkout at
`6397ace506d829a2ee12786da5d724c3f4c6b634`. The application needs
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
checks. To stage the same small offline fixture set from that new receipt, run
`node scripts/stage-point-window-replay.mjs --receipt new-run/database/receipt.json --runtime dist --output new-fixtures`.
For exact offline replay of the new capture, use `new-fixtures` as the
`examples/point-window-replay-data` directory in a disposable copy of the example.

## Use the verification step in your CI

Start with a verified portable archive. Have your capture job write an analysis
capsule and keep the configuration, policy and budget under CI control. In this
example, the archive was extracted into `vendor/moontxnwitness`.

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
node scripts/verify-point-window-moon-consumer.mjs --runtime dist --module-version 0.6.4 --output new-moon-consumer
```

The consumer compares the normalized history digest, `serializable` decision
and full model judgment for the counterexample and ordered control. The SQL and
writer evidence are first verified by the capsule runtime. The separate core
comparison begins at the normalized relation-history boundary.
