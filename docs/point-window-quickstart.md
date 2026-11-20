# PostgreSQL point-window quickstart

## Choose an installation

| Use | Install and run |
| --- | --- |
| MoonBit core | In a clean MoonBit project, run `moon add HhWw96/moontxnwitness@0.6.0`. [Independent consumer example](../examples/core-v4/README.md) |
| Offline JavaScript or CLI | Extract the portable ZIP from [GitHub Releases](https://github.com/HhWw96/moontxnwitness/releases). With Node.js 20 or newer, run `node dist/moontxnwitness.mjs capabilities --format json` and `node dist/demo.mjs`. |
| PostgreSQL capture | Use the matching source release, PostgreSQL 18, and an isolated Python environment with [the database and ORM dependencies](../examples/orm-requirements.txt) and [SQL recognition](../integrations/python/requirements-configured-sql.txt). Install [source components](configured-source-v2.md) explicitly on a controlled test table before recording. |

## Capture and check a window

| Business access | Capture recipe |
| --- | --- |
| Synchronous psycopg | [Owned connection factory](configured-window-v2.md) |
| Synchronous SQLAlchemy | [Scoped NullPool recipe](configured-factory-v2.md) |
| Asynchronous psycopg or SQLAlchemy | [Owned asynchronous connection or engine](configured-async-window-v2.md) |
| Asynchronous SQLAlchemy with connection reuse | [Opt-in bounded pool](configured-async-window-v2.md#reusing-the-physical-connections) |

Configure one table with an int64, C-collated text or UUID primary key. Use full-row point reads and supported single-row INSERT, UPDATE and DELETE operations. Complete business result delivery, finish the transactions, and return or close every enrolled connection before sealing. The writer and source-owner roles are configured independently.

Use the original sealed bundle with caller-supplied configuration, source policy and budgets. The [SDK and CLI reference](configured-window-v2-sdk.md) shows analysis, verification, model-preserving reduction and offline explanation. The [capsule guide](configured-window-v2-capsule.md) shows how to replay the evidence without a database.

The window admits up to 32 transactions and 128 business statements. Analysis checks the formal `serializable` model under atomic full-row point semantics. The optional [paged snapshot reader](configured-window-v2.md#paged-source-snapshots) still verifies the complete retained inventory. Partial fetches, lost coverage, unsupported SQL and uncertain outcomes stay visible as `unknown`. The [source and model matrix](feature-matrix-v4.md) lists the separate offline model capabilities.

## Run the real database fixture

From the source checkout, build once and run the fixture against a fresh owned PostgreSQL 18.6 cluster. The argument to `--bin` points to the directory containing PostgreSQL binaries, and the output directory must be new.

```sh
npm run build
python -B scripts/configured-source-v2-postgres.py --bin PG_BIN --output NEW_RUN --with-window --with-analysis --with-reduction --with-async --with-sqlalchemy --with-paged
node scripts/configured-window-v2-check.mjs --core dist/sql-projection-v2-core.mjs --receipt NEW_RUN/receipt.json --output NEW_RUN/analysis-checks.json
node scripts/configured-window-reduction-v2-check.mjs --core dist/sql-projection-v2-core.mjs --receipt NEW_RUN/receipt.json --output NEW_RUN/reduction-checks.json
node scripts/configured-window-v2-capsule-test.mjs --runtime dist --receipt NEW_RUN/receipt.json --output NEW_RUN/capsule-checks.json
```

The fixture records PostgreSQL execution separately from MoonBit verification and offline replay. For a standalone core example within the source tree, run `moon run --target wasm-gc src/demo`.
