# Configured PostgreSQL SQL recognition

This is an optional input-adapter foundation. It recognizes a bounded PostgreSQL SQL subset against immutable table configuration. It preserves the original SQL and outputs a structural candidate. It does not execute SQL, wrap a cursor, install triggers, create transaction facts, or declare a capture complete.

The optional dependency is exactly SQLGlot 30.26.0. SQLGlot documents its parser as deliberately lenient: successfully parsing a statement does not validate that PostgreSQL will execute it. The candidate therefore always records `databaseSyntaxValidated: false`, `captureFactsProduced: false`, and `moonbitProjectionVerified: false`. See the [official parser FAQ](https://sqlglot.com/sqlglot.html#faq).

## Current source boundary

Existing input paths retain their protocols:

- `instrumentation.py` observes only explicitly selected engine/factory objects. The actual result-consumption path supplies delivered rows and errors; hooks do not prefetch business results.
- `profiles/orm_cursor.py` and `profiles/orm_install.py` implement the fixed FastAPI Users base-user layout and its separately verified source metadata.
- `profiles/model_sql.py` generates its existing `business` table plans for four relation columns, at most eight keys and configured predicates, or its one-item list append templates.
- MoonBit `model_profile_*`, `orm_sql_v3.mbt`, `orm_source2_v3.mbt` and `orm_profile_v3.mbt` independently verify those exact protocols, catalog observations, initialization and source windows.

The new `configured_sql.py` is separate. Its table registry has no `business` name, four-column or eight-key assumption. Removing assumptions in this candidate parser does not widen an existing profile's provenance contract. No old source checker or business adapter is changed.

## Configuration

```python
from moontxnwitness_capture.configured_sql import (
    ColumnConfig, TableConfig, SQLCaptureConfig, ConfiguredSQLParser,
    TEXT_COMPARISON,
)

config = SQLCaptureConfig((
    TableConfig('ledger', 'accounts', 'account_no', (
        ColumnConfig('account_no', 'int64'),
        ColumnConfig('balance', 'int64'),
        ColumnConfig('active', 'bool'),
        ColumnConfig('label', 'text', TEXT_COMPARISON),
    )),
    TableConfig('app', 'flags', 'feature_key', (
        ColumnConfig('feature_key', 'text', TEXT_COMPARISON),
        ColumnConfig('enabled', 'bool'),
    )),
), default_schema=None)

parser = ConfiguredSQLParser(config)
plan = parser.recognize(
    'UPDATE ledger.accounts SET balance=%s WHERE account_no=%s RETURNING account_no'
)
bindings = plan.bind((500, 72))
print(plan.to_dict())
```

All configuration and returned plans use frozen dataclasses and immutable tuples. Dictionaries returned by `to_dict()` are detached copies. Configuration JSON uses format `moontxnwitness-configured-sql/v1`; `SQLCaptureConfig.from_json()` rejects unknown fields and duplicate keys, including escaped duplicates.

Tables specify schema, table, one primary-key column, ordered columns and a target-model hint. Names may use legal quoted Unicode and punctuation, up to PostgreSQL's standard 63 UTF-8-byte identifier bound. Unquoted SQL identifiers use an explicit ASCII folding rule; non-ASCII names must be quoted. A relation identity is a `(schema, table)` pair, not a separator-concatenated string.

Supported scalar declarations are signed int64, boolean and text. Text requires the explicit `postgres-c-utf8-v1` comparison declaration. This declaration is a requested configuration, not proof of the actual database's type or collation. NULL, UUID, JSON payload semantics and custom types are not stable scalar bindings in this first candidate layer.

`model` is a configuration hint for future register/list/relation projection. It does not convert SQL into that model or make list-append/unique-version facts available. Existing model-specific source proofs remain necessary.

No key universe is enumerated. A parsed parameterized plan may bind more than eight distinct runtime keys without changing its structure. The configuration supports 1–128 tables and 1–128 columns per table, with a single configured primary key.

## Recognized subset

- One configured table per statement, with explicit schema or an explicitly configured default schema.
- SELECT direct columns, optional column/table aliases, configured-column star expansion, equality/range comparisons joined with AND, and ordering by direct configured columns.
- INSERT with explicit columns including the primary key, bounded VALUES rows and direct RETURNING columns.
- UPDATE with direct literal/parameter assignments, equality/range/AND conditions and direct RETURNING columns.
- DELETE with the same conditions and direct RETURNING columns.
- Exact psycopg `%s` or `%(name)s` parameter references. Named parameters are case-sensitive. Mixed styles are rejected. Parameter binding requires a materialized tuple/list or exact dictionary and never consumes a generator.

Predicates retain column identity, operator, typed literal or original parameter reference, and supported explicit `COLLATE "C"`. Parameter positions follow their original lexical order, including assignment parameters before WHERE parameters and multirow INSERT order. int64 literals serialize as tagged decimal text to avoid precision loss in JavaScript consumers.

Unknown columns/tables, JOIN, multiple tables, CTE, subqueries, UNION, aggregates, arbitrary functions, casts, NULL, OR, IN, BETWEEN, primary-key mutation, UPSERT, arithmetic updates, LIMIT/OFFSET and unsupported clauses are rejected with an explicit `RecognitionError.code`. The original SQL remains unchanged. These exclusions are candidate boundaries, not statements about PostgreSQL validity.

`RETURNING` is represented only as a returned projection of the executed write. It is never relabeled as a complete predicate read. A WHERE descriptor is not a SELECT fact, and a zero-row conditional write is not evidence of a complete empty query result.

Configuration-based star expansion and unqualified-table resolution need later catalog/session proof. They do not establish the actual physical columns or search path.

Psycopg percent formatting can affect SQL strings and comments before PostgreSQL parses them. This layer rejects percent text/escapes combined with external bind slots unless a later independent driver-format contract is available. A no-bind statement containing literal percent text requires `parameters=None`; it cannot silently reinterpret a supplied parameter argument.

## Resource and cache contract

Default bounds are 65,536 SQL UTF-8 bytes, 8,192 tokens, 4,096 AST nodes, nesting 64, 128 AND terms, 128 INSERT rows and 65,536 bytes per text value. Configurable maxima remain finite. SQL byte/Unicode checks happen before cache lookup. Token and nesting checks precede AST construction; excessive ASTs and unsupported constructs are rejected.

Each parser owns a local structural cache, defaulting to 256 entries and 4 MiB of accounted serialized plan/key bytes. Both limits apply; no global cache is installed. Accounted bytes are not a claim about total Python RSS. Cached plans contain no mutable AST, supplied parameter values, database result rows or transaction state. A new installation/catalog context must select a new immutable configuration and parser rather than reusing a context after DDL.

## Required MoonBit projection contract

A later source package must bind configuration, original statement/event identity, parameters, actual result delivery and source evidence. The adapter's AST is untrusted input to that verifier. A proposed independent verifier must:

1. Parse the supported original SQL subset independently in MoonBit, preserving quoted identifiers, comments, literal/parameter boundaries and lexical bind order. Reject a descriptor that differs from the raw SQL; a SQLGlot parse or checksum cannot authorize semantic facts.
2. Prove actual relation identity, native column types, one primary key, text collation, server/session encoding and string-literal rules. Verify session schema resolution for unqualified tables and physical layout for stars. Include catalog/DDL epoch and reject unproved RLS, rules, generated expressions or additional writers/effects.
3. Tie each statement to actual DBAPI execution, delivery/error and complete-fetch state without prefetching. Verify returned columns/positions against the actual native result. No row is claimed delivered before the business consumes it.
4. Bind reads to same-statement or native-observed unique version identities. Business-value equality or a later SELECT cannot establish which version the earlier read observed.
5. Verify explicit provenance installation, initialized snapshot, complete window, unique writers, effective final writes and rollback/savepoint journals. SQL configuration alone establishes none of these facts.
6. Separate complete predicate result sets, empty query results, conditional facts and actual write effects. PostgreSQL RC target rechecks/waits cannot be reconstructed from a RETURNING collection.
7. Apply register, append-list or relation projection only after the required model-specific observations are available. SQL scalar recognition does not create append identities or register versions.
8. Preserve every coverage gap and use new versioned source/projection identifiers. Do not upgrade older incomplete profile traces or replay contracts by changing names.

Until that verifier and actual driver/source integration exist, candidate descriptors remain diagnostics. They are not accepted `HistoryV4` observations and must not be fed to the classifier as if source verification had completed.

## Optional installation and offline checks

The optional adapter requires Python 3.10 or later. Install explicitly from the hash-pinned requirements; nothing installs at module import:

```text
python -m pip install --require-hashes --no-deps -r integrations/python/requirements-configured-sql.txt
python scripts/configured-sql-unit-test.py
```

An isolated dependency directory is supported without modifying a shared environment:

```text
python -m pip install --require-hashes --no-deps --target artifacts/sqlglot-deps -r integrations/python/requirements-configured-sql.txt
python scripts/configured-sql-unit-test.py --dependency-root artifacts/sqlglot-deps
```

The first development validation passed 86 unit tests, including three table structures using the same parser for CRUD, more than eight runtime keys, Unicode names, strict parameter types, refusal paths and bounded-cache checks. A separate `-I -S` interpreter verified missing-dependency refusal, explicit local dependency loading and no driver/ORM import. The initial four failures exposed SQLGlot's `And`/`Collate` inheritance from `Func`; only those exact supported structural nodes were exempted, with all original function-rejection expectations retained. These are adapter checks, not database or MoonBit source-projection validation.

Run the three-configuration example with:

```text
python examples/configured-sql-recognition.py --dependency-root artifacts/sqlglot-deps
```

The runner uses offline configured statements and parameter values. It does not connect to PostgreSQL, install DDL, wrap a cursor or run performance measurements. Its receipt records actual outcomes and hashes; tests are not assumed to have passed merely because this document exists.

## Dependency provenance

SQLGlot 30.26.0 pure wheel: 800,802 bytes, SHA-256 `58fe0d44cc5ae2947a08d16c4e1affb8716e6ddb47154674e3b6180a2f2b315c`. The installed wheel's METADATA states `License-Expression: MIT`; its actual LICENSE states `Copyright (c) 2026 Toby Mao`. The full original license is retained in `integrations/python/licenses/SQLGlot-30.26.0-MIT.txt`. No SQLGlot implementation source is copied into this repository.

Primary sources: [PyPI release](https://pypi.org/project/sqlglot/30.26.0/), [upstream repository](https://github.com/tobymao/sqlglot), and [official parser documentation](https://sqlglot.com/sqlglot.html).
