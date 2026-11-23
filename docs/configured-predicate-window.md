# Configured PostgreSQL range windows

Use the explicit synchronous Python API on a disposable or controlled PostgreSQL 18.6 instance with psycopg 3.3.6. Install the existing V2 sources first and keep the configured writer roles exclusive to the capture scope.

```python
from moontxnwitness_capture.configured_predicate_window import ConfiguredPredicateWindow

window = ConfiguredPredicateWindow("new-range-window", config, control, policy, installed, opt_in=True)
txn = window.begin(psycopg.connect(writer_dsn, autocommit=True), isolation="repeatable read")
rows = txn.select_range(100, 200)
txn.commit()
bundle_file = window.seal()
```

Each dedicated connection starts idle. The API owns its transaction and closes the connection after commit or rollback. The first profile supports one non-null int64 primary key, complete rows in ascending key order, half-open intervals and full-row single inserts. Repeatable Read and Serializable retain the original range statement's snapshot when the capture reads it on the same connection. Fetching returns all business rows and removes the private version field. A window is bounded to 32 transactions, 128 operations and at most 128 rows per native range result. [PostgreSQL snapshot semantics](https://www.postgresql.org/docs/18/transaction-iso.html)

```js
import {readFileSync} from 'node:fs';
import {admitConfiguredPredicateWindowV1} from './dist/sdk.mjs';

const input = name => readFileSync(name, 'utf8');
const report = admitConfiguredPredicateWindowV1(input('new-range-window/predicate-window.json'), {
  config: input('config.json'), policy: input('policy.json'), maxChecks: 1_000_000,
});
console.log(report.status, report.coverageComplete);
```

MoonBit replays the installation and closing ledgers, checks native result bytes and delivered rows, then reconstructs each complete range from the original PostgreSQL snapshot and prior writes in the same transaction. An external write, unsupported statement, failed or unconfirmed transaction, missing observation or exhausted budget keeps the result unknown. Admit reports certify coverage of the supplied capture within this scope. The PostgreSQL source itself remains a caller trust boundary.

Run the real fixture with `python -B scripts/predicate-window-postgres.py --owned-database --dsn-env MTW_PREDICATE_DSN --output new-range-capture` and replay it with `node scripts/verify-predicate-window.mjs --core dist/sql-projection-v2-core.mjs --input new-range-capture --output admission.json`.

## Reproduce the reservation case

From the portable distribution, use a dedicated PostgreSQL 18.6 test database. The Python environment needs psycopg 3.3.6 and the pinned Python requirements supplied in the package. Set `MTW_PREDICATE_DSN` to the disposable database. Its admin role needs to create the fixture schemas and roles.

```sh
node scripts/postgres-predicate-window-demo.mjs --dsn-env MTW_PREDICATE_DSN --output reservation-run
```

Each of five rounds checks three independent histories. Repeatable Read commits two reservations after both transactions read the same empty interval. The source-backed witness has two predicate anti-dependencies and zero item anti-dependencies. The reducer checks a five-to-two transaction, source-closed, one-minimal reproduction. The ordered Serializable run accepts one reservation and checks compatible. Concurrent Serializable returns SQLSTATE `40001`; the retry sees the committed reservation. The original retry window returns unknown under this contract because it includes a failed transaction.

```sh
node examples/check-predicate-window.mjs --capsule reservation-run/database/round-1/before/analysis-capsule.json --config reservation-run/database/round-1/before/config.json --policy reservation-run/database/round-1/before/policy.json
```

The command replays the capsule offline and uses exits `0` for compatible, `1` for verified refutation and `2` for unknown or invalid evidence. The SDK exports `analyzeConfiguredPredicateWindowV1`, `reduceConfiguredPredicateWindowV1`, `makeConfiguredPredicateCapsuleV1` and `replayConfiguredPredicateCapsuleV1`. A reduction capsule also binds the original window and is replayed with the caller's explicit configuration, policy and chosen budgets.

## Replay in a clean directory

The portable archive contains the original PostgreSQL input from one round of
the five-round campaign. No database or external service is needed.

```sh
node examples/predicate-window-replay.mjs --output reservation-replay.json
```

The report shows the original range SQL, parameters, commit count and SQLSTATE
alongside the verified model judgment. In the RR run, both inserts committed
without a database error. Replaying the original snapshots and writes
identifies the two predicate edges, proves the refutation and checks the
minimal reduction. The same report records the compatible ordered control and
the inconclusive retry window with its original `40001`.
