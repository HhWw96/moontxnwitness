# Original SQL and actual result delivery

This optional PostgreSQL adapter observes an unchanged SQL call and its real DBAPI result deliveries. A separate MoonBit verifier checks the supplied SQL, configuration, parameter binding, native result buffer and delivered row sequence. It does not install source tables, execute a later provenance query or produce transaction-history facts.

## Python entry points

```python
from moontxnwitness_capture.configured_fetch import (
    ConfiguredInstrumentation, StoredColumnObservation,
    instrument_configured_psycopg, instrument_configured_engine,
)
# config is the immutable SQLCaptureConfig used by the configured SQL adapter.
observer, connect = instrument_configured_psycopg(
    psycopg.connect, "new-output-directory", config,
    stored_columns=(StoredColumnObservation("ledger", "accounts", "version"),),
)
connection = connect(**database_parameters)
cursor = connection.cursor()
cursor.execute(original_sql, original_parameters)
rows = cursor.fetchall()       # unchanged business return value
connection.rollback()
connection.close()
observer.close()               # synchronize journal and lifecycle tail
```

Use `asynchronous=True` with an async connection factory and await the usual connection/cursor methods. Installation is local to this observer/factory. `observer.wrap(raw)` and `wrap_async(raw)` reuse an existing live wrapper for the same raw object. The weak registry retains no connection by itself. Objects already owned by another observer are left in that observer and produce a coverage gap. Register engine hooks before its first connection is borrowed; duplicate installation is rejected without installing duplicate hooks. Existing late-attachment/pool/savepoint/unknown-commit diagnostics remain in effect.

The adapter passes the original SQL and parameter objects to the original driver. Recognition failure records a gap and the original business call still executes. It never fetches during `execute()`. After a successful ordinary text result, it reads the driver's existing libpq PGresult metadata and bytes without advancing the cursor. Only real `fetchone`, `fetchmany`, `fetchall` or iteration deliveries are recorded as delivered rows. Async SQLAlchemy internal prefetch does not count as business delivery; its adapter boundary records actual consumption separately.

The default tuple rows and int64, boolean and UTF-8 text decoders are covered. Native limits are 256 rows, 128 columns, 2,048 cells and 32 KiB cell bytes. A record must fit the 60 KiB UTF-8 frame budget. Larger/unsupported results still reach the business unchanged and produce gaps. Only one native result is referenced per live cursor; replacement or close clears it. No complete result or parameter tree is accumulated in an `_events` array.

Lifecycle frames use the existing bounded lifecycle sink, alongside the existing bounded v3 journal. Queue/sink exhaustion, encoding failure and unsealed output remain visible. These diagnostic frames are separate from trace-schema semantic facts. Closing seals and synchronizes the tail; enqueue/write success alone is not a durability receipt. Configuration and statement-plan caches retain SQL text and inline literals, which can contain business data. External bind values, native rows and business results are written to the configured diagnostic output and are not stored in the plan cache. Treat this output according to the application's data-retention policy.

## Independent core verification

MoonBit exports `verify_configured_fetch_v1(SQLConfigV1, execution, native, deliveries, max_checks~, grammar_options~)` and the detached JSON getter `configured_fetch_check_v1_json`. `verify_configured_fetch_v1_json` and the independent `src/sql_fetch_bridge` provide the JSON boundary. The new SDK is separate from the existing v4 analysis namespace:

```js
import { verifyConfiguredFetchV1 } from "./dist/sql-fetch-v1.mjs";
const report = verifyConfiguredFetchV1(configText, executionText, nativeText,
                                     deliveriesText, {maxChecks: 1000000});
```

For values outside JavaScript's safe integer range, pass the original JSON text. Structured SDK inputs reject unsafe numeric values. Raw JSON rejects duplicate keys, including Unicode-escaped duplicate option names. Unknown options are rejected. Caller `maxChecks` bounds native/delivery work independently of the grammar's `grammarOptions` budget; neither is taken from a report. Both permit zero and are capped at 1,000,000 checks. The existing grammar counter and the new `native-field-cell-delivery-step-checks-1` counter are separate contracts.

The verifier reconstructs the SQL/binding descriptor rather than trusting Python status/type fields. It checks execution/native/delivery identities, source and parameter digests, projected output names, ordinary PostgreSQL scalar OIDs/text formats, canonical base64, exact native scalar decoding and contiguous delivery positions. Row values must equal the same native result in order. It requires actual exhaustion before `completeFetchVerified=true`. An empty SELECT requires an actual empty delivery/exhaustion and does not prove a missing row's version.

Result statuses are `matched`, `partial`, `mismatch`, `unknown` and `invalid`. `partial` means the supplied prefix can be consistent while complete-fetch evidence is absent; its `completeFetchVerified` remains false. Unknown SQL, unsupported native formats/NULL/custom scalar decoding, caller-budget exhaustion and incomplete observations never become a complete result claim. These statuses concern supplied-observation consistency, not database isolation acceptance.

`StoredColumnObservation` only identifies an originally projected configured column. A positive physical native field can contribute to `storedColumnObservations`; even that does not prove uniqueness, installation, catalogue identity or writer completeness. Every report keeps `sourceFactsProduced`, `sourceAuthenticated`, `catalogVerified`, `sourceWindowVerified` and `isolationModelChecked` false, and retains `read_version_unproven` plus installation/writer-window gaps. Configuration booleans cannot upgrade these conditions. Digests bind supplied bytes; they do not authenticate the collector.

## Scope and reproducibility

`NULL`, JOIN, aggregate/function expressions, UUID casts, arbitrary adapters/decoders, server-side cursors, binary results, multiple result sets and generic `executemany` fact mapping remain outside this verifier. Writes are observed but are not converted into SELECT reads; RETURNING is not a full predicate read. The existing fixed profiles remain separate. Engine hook registration and adapter delivery have simulation tests; the actual database runs here exercise native synchronous/asynchronous psycopg, not an entire ORM application.

Run wrapper simulations and regenerate the fake-driver fixture with `python -B scripts/configured-fetch-unit-test.py --dependency-root <existing-sqlglot-30.26.0-target>`. The dependency remains optional and is not installed into a shared environment. Build with `node scripts/build-sql-fetch-v1.mjs`. The standalone read-only CLI accepts CONFIG, EXECUTION, NATIVE, DELIVERIES and optional OPTIONS JSON files:

```text
node scripts/verify-configured-fetch-v1.mjs CONFIG.json EXECUTION.json NATIVE.json DELIVERIES.json OPTIONS.json
```

It prints one report and returns 0 for matched, 3 for partial/unknown, or 2 for invalid/mismatch. It does not overwrite any input.

`scripts/configured-fetch-postgres.py --bin <existing-PG18-bin> --output <new-owned-directory>` creates a private UTF8/C cluster bound only to 127.0.0.1 on a private port. It validates three arbitrary schema/table/primary-key layouts with 4/3/6 columns, real sync/async fetch paths, omitted version columns and empty results. It also checks the U+10000 versus U+E000 C-collation ordering. The script stops only that verified owned cluster and keeps all inputs/logs. Its connection/password files are private runtime configuration and must not be published. `scripts/configured-fetch-cross-test.mjs <owned-output>` sends the actual records to MoonBit and runs independent supplied-input tamper checks. No formal performance measurement is performed by these scripts.

Hidden projection, source installation/catalogue validation and complete writer-window closure require additional explicit contracts and real verification. This delivery does not implement a hidden SELECT suffix or promote observations into source facts.
