# Configured source installation candidate

This stage implements an explicit PostgreSQL row-version/sidecar installation layer. It uses the same immutable `SQLCaptureConfig` table, column, single-primary-key and scalar-type definitions as configured SQL recognition. Business schema/table/column names and row keys are not hardcoded. The default diagnostic factory and the previously frozen SQL/fetch verifiers are unchanged.

This is currently a development candidate with pure contract/control-driver tests. The owned PostgreSQL regression script is prepared but has not been executed for this candidate. `moonbitCatalogVerified`, `writerWindowVerified`, `driverFetchVerified` and `sourceFactsProduced` remain false. No installation receipt is accepted as a transaction history or isolation-model conclusion.

## Offline plan

```text
python -B examples/configured-source-plan.py
python -B examples/configured-source-plan.py --show-ddl
```

The example uses one handler/configuration interface for three unrelated 4/2/6-column schemas and prints a plan only. It connects to no database and executes no SQL. SQLGlot is not imported by the source installer; the optional recognizer and independent MoonBit SQL/fetch checks remain separate stages.

## Explicit installation API

```python
from moontxnwitness_capture.configured_source import (
    SourceInstallPolicy, install_configured_source,
)
policy = SourceInstallPolicy('mtw_source_owned_test', ('application_login',))
# A dedicated idle autocommit control connection must already use the
# non-login, non-superuser owner role of all configured tables.
installation = install_configured_source(
    owner_control, 'new-source-evidence-directory', config, policy,
    opt_in=True,
)
print(installation.to_dict())
```

`opt_in=True` is required before filesystem or database access. The API owns one explicit installation transaction on its dedicated control connection. It does not use a business connection/cursor, rewrite application SQL, install a global driver patch or register old fixed business SQL templates. The application login roles are distinct from the non-login source/table owner. The namespace must be a new, explicit `mtw_source_*` name; existing installation objects are not silently adopted.

The initial scope is 1–16 arbitrary configured ordinary tables, each with a complete ordered column configuration and one immediate valid single-column primary key. Supported native scalar families are integer, boolean and explicit deterministic `pg_catalog.C` text/varchar in UTF8. Domains, arrays, generated/identity columns, RLS, inheritance, rewrite rules, existing user row triggers and active database DDL event triggers need separate semantics and are rejected by this first installer.

## Components checked

1. The control transaction takes an acknowledged `ACCESS EXCLUSIVE ... NOWAIT` lock over the configured tables before the first catalog/data SELECT. It records actual backend/database identity and the granted `pg_locks` inventory.
2. Catalog output binds actual table OIDs, owner, ordered columns/types/collations and primary-key shape. OID-valued JSON fields are explicitly cast to bigint rather than relying on their default JSON string representation.
3. Installation adds one private non-null bigint version column and unique index, a private no-cycle bigint sequence, a configured relation scope and transactional effect ledger. A BEFORE trigger allocates versions; only the AFTER trigger inserts actual INSERT/UPDATE/DELETE effects. Aborted operations and rolled-back savepoint effects therefore belong to the transaction that changes them; allocation gaps are not interpreted as missing operations or commit order.
4. Both row triggers are `ALWAYS`, have exact relation/key arguments and expected function bodies, and execute as the private owner with fixed `search_path` and string-literal settings. Source writers cannot own/control the tables, assume privileged roles, set replication mode or gain TRIGGER/TRUNCATE privileges. Private objects admit no non-owner ACL entries or non-superuser owner-role memberships.
5. Initialization records every row and its installed version under the same lock, verifies unique identities, configured values and exact source-scope/initial-ledger counts, and enforces explicit row/log budgets. Source data is never truncated into an accepted snapshot. Initial JSON is emitted in bounded single-row cells; oversized data produces a failure marker and the migration is rolled back.
6. Successful component installation requires native `COMMIT`/`COMMAND_OK`, no result columns, and an IDLE control connection. A COMMIT request, a ROLLBACK response, an unknown acknowledgement or missing durable evidence cannot confirm installation.

The existing bounded lifecycle sink records source control requests, native status/column metadata/raw bytes, actual decoded control results, errors and a final seal. Control-row decoding must match native UTF8 bytes. It does not retain an unbounded `_events` list. The source-control cursor eagerly consumes only installer-owned catalog/snapshot queries and must never wrap a business cursor.

A local `catalogVerified`/`initialSnapshotVerified` component result describes the installer's checks of its supplied native observations. It is not independent MoonBit verification, authenticated provenance, complete writer coverage or a database-history proof. Privileged administrators and later DDL remain an explicit scope gap. The source ledger currently has no completed window/retention protocol; keep this candidate in owned test environments until those stages are verified.

## Next required joins

The driver stage must independently bind actual original SQL/parameters, real delivered results and observed row versions to these installed sources. Any hidden SELECT suffix needs a separately verified same-statement transform, supported standard DBAPI result-prefix preservation and catalog/permission proof. Native `pgresult` extensions cannot be called transparent after adding columns. Empty results, zero-row conditional writes, no-RETURNING writes and RC target-scan/wait-recheck uncertainty cannot be converted into invented SELECT facts.

A finite writer window must establish barriers, effective write/read coverage, client/database transaction mapping, rollback effects and final source closure. Backend PID and writer xid in sidecar effects are identity observations, not transaction order. Source facts remain disabled if catalog, initial state, source lookup, actual fetch, writer scope or independent core verification is incomplete.

## Tests and references

Pure tests: `python -B -m unittest moontxnwitness_capture.test_configured_source` with `integrations/python` on the import path. They include field/ACL/function tampering, native/decoded disagreement, 300-row initialization, budget rollback, unconfirmed COMMIT and post-commit log failure. They do not execute PostgreSQL or establish server-DDL validity.

`scripts/configured-source-postgres.py --bin <existing-PG18-bin> --output <new-owned-directory>` is prepared for a later enabled database window. It creates only a new localhost cluster, uses the frozen three-table configuration, checks actual CRUD/zero-row/UPSERT/savepoint/rollback/source permissions, and stops only its verified owned cluster. Its private connection/password files must not enter public artifacts. No real database execution is claimed here until its actual receipt exists.

The intended server semantics are based on PostgreSQL 18 [CREATE TRIGGER](https://www.postgresql.org/docs/18/sql-createtrigger.html), [pg_trigger](https://www.postgresql.org/docs/18/catalog-pg-trigger.html), [LOCK](https://www.postgresql.org/docs/18/sql-lock.html) and [CREATE FUNCTION](https://www.postgresql.org/docs/18/sql-createfunction.html). The explicit OID-to-integer conversion follows the built-in JSON type classification in [PostgreSQL's JSON implementation](https://github.com/postgres/postgres/blob/REL_18_STABLE/src/backend/utils/adt/jsonfuncs.c).
