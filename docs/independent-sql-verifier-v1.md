# Independent configured SQL grammar and binding verifier

This module independently checks configuration, original PostgreSQL SQL text and original supplied parameters against a Python candidate. It is implemented in MoonBit and does not call SQLGlot, a database driver, a subprocess or an SQL executor. It is separate from existing HistoryV4 analysis and every older profile/replay contract.

The first checked grammar is single-table SELECT/INSERT/UPDATE/DELETE with configured columns, a single primary key, point/range comparisons joined with AND, quoted identifiers, aliases and comments. It supports exact psycopg positional/named parameter references, direct scalar writes, direct SELECT/RETURNING projections, configured star expansion and simple column ordering. Unknown structures, NULL, joins, aggregates, functions, casts, complex subqueries, LIMIT/OFFSET and incomplete resource budgets remain explicit gaps.

The configuration permits unrelated schema/table/PK/column names. The current cross-check uses one handler on 2-, 4- and 6-column tables; no business-name, four-column or eight-key assumption is introduced. A model field is a target hint, never a grant of history or model coverage.

## Independent input contract

The frozen Python candidate template intentionally stores no external parameter values. A template alone cannot distinguish binding 7 from 8. The verifier therefore accepts a new binding-claim envelope:

```json
{
  "format": "moontxnwitness-sql-binding-candidate/v1",
  "descriptor": {"...": "the frozen Python plan.to_dict()"},
  "bindings": [{"reference": {"kind": "positional", "value": 0, "type": "int64"},
                "value": {"type": "int64", "value": "7"}}],
  "configSha256": "canonical normalized configuration digest",
  "sqlSha256": "exact original SQL UTF-8 digest",
  "parametersSha256": "canonical original parameter JSON digest"
}
```

The envelope is a claim to check, not a fact producer. MoonBit independently parses the configuration and SQL, resolves each identifier, reconstructs the descriptor, validates parameter positions/names/types and exact supplied values, and compares the full reconstructed envelope. Changing source, configuration, descriptor, typed binding, hashes, result flags or an unknown field cannot reuse an unchanged claim.

Consistently supplying an entirely new SQL/config/parameter claim may pass the grammar check. That does not authenticate that an observer or server executed it. Cryptographic digests detect disagreement; they do not authenticate the source.

All JSON parsing uses the compiler runtime's duplicate-key rejection, depth bound and original-number representation. int64 parameters retain their original decimal lexemes without passing through an approximate Double, and typed int64 bindings use decimal text. Host JavaScript callers must supply raw parameter JSON for integers outside the JavaScript safe range.

Configuration digests use explicit Unicode lexical key ordering. The toolchain's ordinary String Compare is shortlex (length before code units), so it is not used for canonical JSON keys. No existing string/graph/ordering contract is changed.

## Public MoonBit surface

- `parse_sql_config_v1(text)` returns an opaque `SQLConfigV1` or an error.
- `sql_verification_options_v1(...)` records independent caller caps.
- `normalize_sql_candidate_v1(config, sql, parameters, options~)` reconstructs the supported structure and binding claim.
- `verify_sql_candidate_v1(config, sql, parameters, candidate, options~)` compares the supplied claim independently.
- `sql_candidate_check_v1_json(result)` returns a detached report.

The separate foreign-library bridge exports `normalize_configured_sql_v1_json`, `verify_configured_sql_v1_json` and `normalize_sql_config_v1_json`. `compare_c_text_v1` is a mathematical text comparator helper, not database evidence.

Reports use `moontxnwitness-sql-candidate-verification/v1`, semantic contract `moonbit-independent-configured-sql/v1`, algorithm `moonbit-configured-single-table-grammar-1` and counter `configured-sql-lexer-parser-step-checks-1`.

`recognized` means independent normalization/type checks completed; `matched` additionally means the supplied claim matched. `mismatch`, `unknown` and `invalid` never claim verification. Every result separately records that driver results, source window and source authentication have not been verified. No report produces register/list/relation history facts.

## Budgets

Default independent caps are 1,000,000 lexer/parser steps, 8,192 tokens and 65,536 SQL UTF-8 bytes. Hard ceilings are 1,000,000 steps, 32,768 tokens and 1 MiB SQL. Caller caps are not taken from a producer descriptor. A zero/exhausted cap yields unknown instead of a successful absence/consistency conclusion.

The configuration's bounds also apply. The independent parser conservatively accounts two structural units per lexical token plus root units against `max_ast_nodes`; it does not claim identical counters to SQLGlot's AST. A very tight producer AST cap can therefore yield unknown even when SQLGlot recognized the input. EOF is not charged as a business SQL token. JSON/type/hash input-size bounds remain separate from the lexer/parser step count.

Transport maxima are 256 KiB config, 1 MiB raw SQL, 1 MiB parameters, 8 MiB candidate, 8 KiB options and 32 MiB report. The SDK rejects malformed host Unicode, unsafe host numeric parameter values and invalid independent options.

## Running the minimal bridge

With MOON_HOME pointing at moonc 0.10.16 or a verified compatible toolchain:

```text
node scripts/build-sql-candidate-v1.mjs
node scripts/verify-sql-candidate-v1.mjs CONFIG.json SQL.txt PARAMS.json CANDIDATE.json
```

The build creates only `dist/sql-projection-core.mjs` and its small SDK. It does not restore legacy inputs or build a public package. The CLI reads bounded UTF-8 files and writes only to stdout; it does not mutate inputs. Exit codes are 0 for matched, 3 for unknown and 2 for rejected/invalid.

SDK usage:

```javascript
import {verifySQLCandidateV1} from './dist/sql-candidate-v1.mjs';
const report = verifySQLCandidateV1(configText, originalSql, parameterJsonText, claimText,
  {maxChecks: 1000000, maxTokens: 8192, maxSqlBytes: 65536});
```

`SQLConfigV1`/descriptors are immutable or detached. Original inline SQL and inline literal values necessarily remain in the candidate/cache inherited from the Python recognizer. Only supplied external bind values, result rows and mutable ASTs are excluded from that recognizer cache; it is not a cache without business data.

## Validation and limits of evidence

The current suite includes 36 tests on JS, Wasm GC and Wasm. Twenty-one expected candidate hashes come from actually running the frozen SQLGlot parser and `plan.bind` on three table layouts, rather than from the MoonBit normalizer. The separate Node suite exercises those 21 real candidates plus source/config/descriptor/binding tampering, duplicate keys, unknown types/flags, independent budget boundaries, Unicode and the minimal CLI.

The initial configuration-digest mismatch was preserved and fixed by using explicit lexical key comparison. A later real counterexample showed a named bind `%(where)s` could impersonate a keyword, and a quoted string `'='` could impersonate an operator; the original failure remains recorded, and strict token-kind checks now reject both. Expected results were retained.

The C-text helper reuses the existing surrogate-aware Unicode codepoint comparator. Astral U+10000 versus BMP U+E000, prefix/length cases and 512 randomized valid Unicode pairs are checked against independent UTF-8 byte ordering. This is not a real PostgreSQL execution or proof of a database column's encoding/collation; actual catalog/server and PG comparison evidence is still required before predicate facts can use it.

Native is typechecked only in this first stage. No database execution, DDL, driver wrapping, provenance migration, formal performance measurement, package acceptance or public release is performed by these tests.

## Remaining source closure

Grammar matching does not solve the read-version simultaneity problem. A complete source path still needs actual execution/fetch, same-statement/native version identity, initialized provenance state, exclusive writer/window closure and rollback-aware write effects. An ordinary SELECT returning only repeated business values cannot be assigned a version using a later SELECT.

FastAPI Users' UUID primary-key parameters and `%(pk)s::UUID` remain an explicit gap between its existing fixed profile and this generic scalar grammar. Supporting them would require a separately versioned canonical UUID identity/cast rule and dedicated tests; arbitrary casts are not accepted.

See `same-statement-source-projection-draft.md` for the proposed transformation boundary. Existing incomplete captures are never renamed into complete histories.
