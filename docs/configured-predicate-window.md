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
