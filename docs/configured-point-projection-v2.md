# Same-statement point CRUD projection construction

`configured_point_projection_v2.py` constructs a SQL statement, a new positional
parameter tuple and a detached projection descriptor. It does not execute SQL,
inspect result rows, install metadata or accept source/model facts. The separate
`configured_sql_v2.py` recognizer and all existing v1 code retain their interfaces.

```python
from moontxnwitness_capture.configured_sql import ColumnConfig
from moontxnwitness_capture.configured_sql_v2 import (
    PrimaryKeyConfigV2, TableConfigV2, SQLCaptureConfigV2, ConfiguredSQLParserV2,
)
from moontxnwitness_capture.configured_point_projection_v2 import (
    PointProjectionOptionsV2, build_point_projection, verify_point_projection,
)

config = SQLCaptureConfigV2(TableConfigV2(
    'ledger', 'accounts', PrimaryKeyConfigV2('id', 'int64'),
    (ColumnConfig('balance', 'int64'),),
))
plan = ConfiguredSQLParserV2(config).recognize(
    'UPDATE ledger.accounts SET balance=%s WHERE id=%s RETURNING balance'
)
options = PointProjectionOptionsV2(config, version_column='__mtw_source_version')
original_parameters = [30, 7]
projection = build_point_projection(plan, original_parameters, options)
description = projection.to_dict()
assert verify_point_projection(description, plan, original_parameters, options)['valid']
```

This example constructs data only. A successful descriptor verification means
that independently supplied original inputs and options reproduce it. It does
not mean that PostgreSQL accepted the statement or that source/model coverage
was established.

## Inputs and parameter mapping

The constructor requires an exact `RecognizedSQLV2`, materialized original
parameters and independent immutable `PointProjectionOptionsV2`. It recognizes
the original SQL again using the independent configuration and compares the
complete candidate. Changing a dataclass field, fingerprint or embedded option
cannot authorize another rewrite.

The output SQL uses fully quoted identifiers and positional `%s` bindings. A
parameter-map entry identifies each original named key, positional index or
literal and its projected index. Repeated named slots become separate positional
occurrences. UUID primary-key bindings use `CAST(%s AS UUID)`; UUID objects and
original UUID text spelling remain unchanged in the new call arguments. Exact
int64 values are represented by decimal strings in JSON logs. Original SQL is
retained verbatim, and original parameter-container kind, mapping order and raw
scalar values are logged separately from normalized typed input bindings.

Values are never inserted into generated SQL. Literal values also become new
bindings. Literal percent characters in generated quoted identifiers are doubled
for psycopg's parameter format; percent characters in parameter values remain
unchanged. Original input lists and mappings are never modified.

## Result description

The version column is an independent name with fixed `int64` / PostgreSQL `bigint`
type and must be distinct from the configured key and business columns. It is a
declaration requiring later catalog and installation proof. Transaction IDs,
timestamps and `xmin` are not substituted for a unique version per change.

An explicit complete point SELECT retains its original business-column order
and aliases, then appends the same row's version column. Empty results retain
`diagnostic-only-no-absence-source`; this module constructs no negative-read or
absence source.

Star expressions require a separate, explicit **pre-install business view**:

```python
options = PointProjectionOptionsV2(
    config,
    star_contract='preinstallation-business-schema/v1',
    business_star_columns=tuple(column.name for column in config.table.columns),
)
```

Without these independent options, `SELECT *`, qualified `table.*` and DML
`RETURNING *` are rejected. The supplied order must exactly match the declared
key followed by business columns and exclude the added version column. An
accepted star is expanded as this declared pre-install business view, not as a
claim of equivalence to the current physical table's native star result.

The descriptor retains this view and keeps catalog/installation verification
false. It requires proof that original physical columns and order matched the
view before installation, the version column was newly added rather than an
original business column, and it was the only column added afterward. Independent
MoonBit catalog/installation/projection recomputation remains required. Only a
later complete installation proof can authorize hiding the added metadata from
business star results. Explicit complete column lists require no star options.

DML uses PostgreSQL 18 `RETURNING WITH` and separate private OLD/NEW aliases.
UPDATE appends hidden complete OLD and NEW rows, each with its version; INSERT
appends NEW; DELETE appends OLD. The grammar and row-image meanings follow the
official [UPDATE](https://www.postgresql.org/docs/18/sql-update.html),
[INSERT](https://www.postgresql.org/docs/18/sql-insert.html) and
[DELETE](https://www.postgresql.org/docs/18/sql-delete.html) documentation.

Original business RETURNING expressions remain first: NEW for INSERT/UPDATE,
OLD for DELETE. Hidden images are write-effect observations, never SELECT or
predicate-read facts. DELETE retains the existing deleted-row version and sets
`producesDeletionVersion=false`; it produces no tombstone or deletion identity.

Statements without original RETURNING have `businessResult.mode="no-result"`.
Their newly returned hidden rows cannot be delivered directly to the application.
The descriptor provides ordinal mappings but no cursor/result adapter; a future
executor must separately preserve business results, command tags and errors.

## Verification and remaining obligations

`moontxnwitness-sql-point-projection/v2` binds the original candidate, SQL and typed
input log; independent options and digest; generated SQL and digest; occurrence
parameter mapping; business/native ordinals; OLD/NEW aliases; and hidden row/version
roles. The verifier reconstructs from independent arguments and compares the
entire descriptor. Duplicate JSON keys, added authorization fields, changed SQL,
changed parameters and embedded options differing from caller policy are rejected.

The constructor has explicit generated-SQL and descriptor byte bounds. It does
not grant `sourceFactsProduced`, `captureFactsProduced`, `sourceAuthenticated`,
`completeWindow`, `modelCoverageAccepted` or `moonbitProjectionVerified`.
Database execution and syntax-validation flags also remain false. Required
proofs include independent MoonBit recomputation, catalog types/order and text
comparison, maintained unique non-NULL version metadata, session/DDL policy,
actual successful execution, complete fetch and a separate closed source window.
Triggers, rewrite rules and permissions can affect native observations and must
be checked by a later execution integration.

No negative-read helper, sidecar, DDL, driver wrapper or business API is added.
The unit module `moontxnwitness_capture.test_configured_point_projection_v2`
checks construction and descriptor rejection without a database. It does not
establish server syntax acceptance or actual query effectiveness.
