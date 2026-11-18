# Configured point CRUD candidates v2

`configured_sql_v2.py` is an additive, optional structural input adapter. Its output is a candidate description, not an execution observation, successful read, effective write, source proof, model projection or complete CRUD analysis. The original `configured_sql.py` v1 protocol and existing capture/source adapters are unchanged.

## Version boundary

| Item | V2 identifier |
| --- | --- |
| Configuration | `moontxnwitness-configured-sql/v2` |
| Candidate | `moontxnwitness-sql-point-crud-candidate/v2` |
| Parser contract | `sqlglot-30.26-postgres-single-table-point-crud/v2` |
| Optional runtime parser | SQLGlot exactly 30.26.0 |

V1 and V2 configurations are rejected by the other version's constructor and JSON reader. V2 reuses V1's immutable business `ColumnConfig`, scalar reference shapes, identifier/projection checks, exact parameter-position checks and dependency validation. It does not widen the V1 scalar types or change V1 recognition.

## Configuration

```python
from moontxnwitness_capture.configured_sql_v2 import (
    ColumnConfig, PrimaryKeyConfigV2, TableConfigV2,
    SQLCaptureConfigV2, ConfiguredSQLParserV2, TEXT_COMPARISON,
)

config = SQLCaptureConfigV2(TableConfigV2(
    'identity', 'members', PrimaryKeyConfigV2('member_uuid', 'uuid'), (
        ColumnConfig('email', 'text', TEXT_COMPARISON),
        ColumnConfig('is_active', 'bool'),
    ),
))
parser = ConfiguredSQLParserV2(config)
plan = parser.recognize(
    'SELECT members.member_uuid, members.email, members.is_active '
    'FROM identity.members WHERE members.member_uuid=%(pk_1)s::UUID'
)
original_parameters = {'pk_1': 'A8098C1AF86E11DABD1A00112444BE1E'}
input_log = plan.bind(original_parameters)
assert input_log[0][1] == 'a8098c1a-f86e-11da-bd1a-00112444be1e'
assert original_parameters['pk_1'] == 'A8098C1AF86E11DABD1A00112444BE1E'
```

Exactly one configured table is permitted per proposed capture window. The key is separately declared as int64, C / UTF-8 text, or UUID, and is immutable in UPDATE candidates. There must be 1–16 distinct business columns, excluding the key. Business columns are declared non-NULL int64, boolean or C / UTF-8 text; UUID business columns are outside this contract. Configuration declarations do not prove native catalog types, nullability, key constraints, physical layout or collation.

There is no `known_ids` or key-universe list. One structural parameterized plan accepts arbitrary runtime keys within its declared scalar bounds. Binding a previously unseen key does not establish that it was absent, initialized or read. A future source path must observe a successful execution and complete zero-row delivery before it can describe an absent point read.

Frozen dataclasses and tuples hold configuration and candidate values. `to_dict()` returns detached JSON-compatible values. Configuration JSON rejects duplicate keys, unknown fields and nonfinite values. Relation identities use separate schema/table fields; quoted Unicode and punctuation use the existing 63 UTF-8-byte identifier bound and explicit ASCII unquoted folding rules.

## Recognized structural subset

All operations use one configured base table. SELECT, UPDATE and DELETE require exactly one direct primary-key equality, with no additional conditions. Text equality uses the configured C / UTF-8 declaration; an explicit `COLLATE "C"` is also recognized. Unqualified relations require an explicit configured default schema and remain dependent on later session proof.

- SELECT projects the key and every configured business field exactly once. Direct column aliases, different projection order, table aliases and configured star expansion are supported. Repeated columns/output names are refused. A real SQLAlchemy 2.0.55 entity SELECT and the mapper's primary-key refresh clause are compiled and recognized in offline tests.
- INSERT has one VALUES row, an explicit key and every business column exactly once. Every value is an original bind slot. Partial/default/generated inserts, multirow inserts and UPSERT are diagnostic refusals.
- UPDATE assigns one or more distinct business fields from original bind slots. Primary-key assignments, literals, arithmetic and column/function expressions are diagnostic refusals.
- DELETE has the same single primary-key equality boundary.
- Write RETURNING may contain direct configured columns, aliases or a configured star. It remains a write-result projection, never a predicate read or proof that any row changed.

Int64/text key equality accepts a typed literal or bind. UUID identity requires a direct original bind, optionally wrapped in `::UUID` or `CAST(... AS UUID)`. INSERT and UPDATE also accept the unquoted `::VARCHAR` spelling on a direct bind for a non-key text column, including the form emitted by SQLAlchemy's psycopg dialect. PostgreSQL treats unbounded `VARCHAR` as a variable-length string. Length-limited, schema-qualified, quoted, nested and array text casts remain coverage gaps. [PostgreSQL character types](https://www.postgresql.org/docs/18/datatype-character.html)

SQLGlot parsing is not PostgreSQL syntax validation. JOIN, unknown tables/columns, extra predicates, OR, ranges, IN, subqueries, functions, NULL, ordering, limits, locks and unsupported clauses are rejected with `RecognitionError.code`. Refusal does not call, rewrite, retry or alter the business operation; this module has no execution/cursor integration.

## Original bindings and UUID identity

Only exact psycopg `%s` and `%(name)s` slots are recognized, with original lexical order retained. Mixed styles, positional arity mismatch, extra/missing named keys and nonmaterialized iterators are refused. A repeated named slot is retained at each original position and validated against each referenced scalar type.

`bind()` returns immutable typed input-log pairs. It does not retain supplied parameters in the plan/cache. UUID values may be exact `uuid.UUID` objects, 32 hexadecimal digits, or the standard 36-character hyphenated spelling, with either letter case. The returned log contains lowercase hyphenated UUID identity; the caller's dict, list, tuple and contained arguments remain unchanged. Other UUID spellings are diagnostic refusals in this bounded contract. Text remains case-sensitive and is not UUID-normalized.

Non-NULL scalar validation rejects bool-as-int64, int64 overflow, bool-as-int, invalid Unicode, NUL, oversized text and unsupported UUID values. No driver or catalog claim follows from this input validation. The original SQL string is preserved, including comments and whitespace; no SQL template is generated from a table layout. Existing percent-format ambiguity checks remain active.

## Bounds and cache

Defaults are 65,536 SQL UTF-8 bytes, 8,192 tokens, 4,096 AST nodes, nesting 64 and 65,536 bytes per text value. Limits have finite validated maxima. The local structural cache defaults to 256 entries and 4 MiB of accounted serialized key/plan bytes. It stores no supplied values, result rows, transaction facts or key universe. Accounted bytes do not claim total process memory. A new catalog/installation context must select a new config/parser rather than keep a stale cache across DDL.

Importing V2 does not import SQLGlot, a driver or an ORM. Only the first recognition needs the optional, exact-version SQLGlot parser. SQLAlchemy is used solely by one compiler test and is not an adapter runtime dependency. The existing hash-pinned SQLGlot requirements/license remain applicable; this change installs nothing.

## Independent MoonBit candidate verification

The additive `configured_sql_config_v2.mbt`, `configured_sql_grammar_v2.mbt` and `configured_sql_verify_v2.mbt` implement a separate V2 config reader and independent point-CRUD grammar. `SQLConfigV2`, `SQLVerificationOptionsV2` and `SQLCandidateCheckV2` are distinct public types. The optional `sql_projection_v2_bridge` exports only V2 JSON entry points; no V1 wire format or V1 descriptor builder is used to manufacture a V2 result.

The core entry points are `parse_sql_config_v2`, `normalize_sql_candidate_v2`, `verify_sql_candidate_v2` and `sql_candidate_check_v2_json`. The JSON entry points are `normalize_sql_config_v2_json`, `normalize_configured_sql_v2_json` and `verify_configured_sql_v2_json`. Verification takes independent caller-supplied config text, original SQL, original parameter JSON, the raw Python `plan.to_dict()` descriptor, and caller verification options. It does not accept config, budgets or completeness claims from the candidate as authority.

The verifier independently rebuilds the exact V2 descriptor and validates original parameter references/types. Status is `recognized` without a candidate, `matched` for an equal candidate, `mismatch` for differing descriptors or invalid bindings, `unknown` for unsupported grammar or exhausted budgets, and `invalid` for malformed configuration/input/options. A descriptor is structural and reusable: different well-typed runtime parameter values can match the same descriptor, while each invocation returns its own typed bindings and original-parameter hash. Matching does not authenticate the claimed observer or parameter provenance.

`originalParameters` is a detached copy of the supplied JSON observation and `originalParametersSha256` hashes its canonical exact-number representation. Separate `bindings` normalize UUID identities to lowercase hyphenated text and int64 values to decimal text. For example, upper/lower/32-hex UUID spellings have the same typed identity but distinct original observation hashes. Python UUID objects must be represented by the observer's JSON serialization boundary; this wire verifier receives original JSON values, not driver objects. Neither path changes business call parameters.

The implementation shares private identifier/relation/projection helpers and tokenizer state. The V1 tokenizer wrapper always passes an explicit false for the private UUID-cast token switch. V1's public interfaces, configuration scalar acceptance and descriptor/wire protocols remain unchanged. The V2 parser has its own scalar/binding and CRUD rules; UUID key identity does not widen V1 or business-column types.

Caller options are independently bounded `maxChecks`, `maxTokens` and `maxSqlBytes`; zero is a valid exhausted budget and returns `unknown`. Configuration limits remain separate. JSON byte/depth limits apply before grammar work; the parser uses the documented conservative structure budget rather than claiming SQLGlot AST counter equivalence. Successful structural verification still returns all capture/source/model flags as false, including `moonbitProjectionVerified`, which remains reserved for the later source/model projection boundary.

Targeted checks use an isolated build directory, without building the full SDK, running the whole test suite or contacting a database:

```text
moon test src/configured_sql_v2_wbtest.mbt --target js --deny-warn --jobs 1 --target-dir <isolated-build-dir>
moon test src/configured_sql_v1_wbtest.mbt --target js --deny-warn --jobs 1 --target-dir <isolated-build-dir>
moon build src/sql_projection_v2_bridge --target js --release --deny-warn --jobs 1 --target-dir <isolated-build-dir>
python -B scripts/configured-sql-v2-cross-inputs.py --dependency-root <existing-pinned-deps> --output <isolated-log-dir>/cross-inputs.json
node scripts/configured-sql-v2-cross-test.mjs --core <isolated-build-dir>/js/release/build/sql_projection_v2_bridge/sql_projection_v2_bridge.js --inputs <isolated-log-dir>/cross-inputs.json --output <isolated-log-dir>/cross-validation.json
```

The Python fixture producer generates three unrelated table/key layouts and compiles mapper refresh and INSERT SQL with SQLAlchemy 2.0.55. The compiled MoonBit cross-check compares descriptor hashes, config hashes, typed bindings, preserved original UUID observations, int64 bounds, unenumerated dynamic keys, refused SQL, candidate self-authorization attempts and independent zero budgets. Receipts bind the compiled core, inputs and source hashes for the grammar and input consistency checks.

## Required source work

The separate [original native-result/delivery checker](configured-result-v2.md) verifies only bounded consistency of supplied observations, with distinct V2 formats and budgets. It does not authorize any source/model claims listed below or couple the candidate parser to a projected-SQL constructor.

The separate [point-projection descriptor verifier](point-projection-verifier-v2.md) independently rebuilds deterministic SQL, typed parameter maps and result ordinals from caller config/options. Matching reproduces the frozen construction claim and preserves all execution/source/window/model flags as false.

Every candidate explicitly records `databaseSyntaxValidated`, `sourceAuthenticated`, `captureFactsProduced`, `sourceFactsProduced`, `modelCoverageAccepted`, and `moonbitProjectionVerified` as false. Independent work must bind the V2 config, original SQL/event identity and original parameters to:

1. Bind the implemented independent MoonBit V2 grammar/input check to the actual observer and source event. Its success alone cannot authorize source/model projection. V1 source formats must not be relabeled as V2.
2. Native catalog types, non-NULL constraints, primary-key identity, C / UTF-8 collation, physical star expansion, schema/encoding/session state and catalog/DDL epoch; unsupported RLS, rules, generated effects and additional writers need refusal or explicit proof.
3. Actual execution success/error, native returned column positions, business-delivered rows and complete-fetch state. Empty delivery and RETURNING cannot substitute for a successful complete point SELECT.
4. Same-statement or native-observed unique read-version identity. Equal business values or a later read do not establish which version was observed.
5. An initialized snapshot, dynamic absence semantics, complete source/writer window, installed unique-version sources, effective writes and rollback/savepoint journals.
6. Model-specific projection and coverage checks after all required observations exist.

Until these steps are implemented and checked, V2 candidates remain diagnostics and cannot be accepted as classifier history facts.

## Offline validation

Use a previously provisioned read-only dependency root with SQLGlot 30.26.0 and SQLAlchemy 2.0.55:

```text
python -B scripts/configured-sql-v2-unit-test.py --dependency-root D:\CodexScratch\mtw041-pydeps
```

The runner writes `artifacts/configured-sql-v2/validation.json` and `tests.txt`, including individual outcomes, source hashes, untouched V1 hashes, dependency versions/origins and explicit false DB/source/performance/release claims. Its output directory can be selected with `--output-dir`. A prior failed receipt/log is retained once before replacement.

The development run passed 159 checks: 73 V2 candidate tests and 86 unchanged V1 tests. Coverage includes three unrelated schema/table/key/business layouts through the same parser implementation, 40 dynamic keys per layout, real ORM UUID entity/refresh compilation, canonical UUID input logs with untouched business args, cold optional-dependency import/refusal, unsupported SQL, strict non-NULL scalar/arity checks, resource limits and bounded cache behavior. It performed no database execution, DDL, full build, performance measurement, source-fact acceptance or public release. Actual run receipts, rather than this document, establish the observed test outcomes.
