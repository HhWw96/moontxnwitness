# Independent point projection descriptor recomputation v2

The MoonBit verifier independently rebuilds the frozen Python `moontxnwitness-sql-point-projection/v2` descriptor from original caller inputs. It does not invoke the Python constructor, execute generated SQL, accept native results, install metadata, wrap a driver or construct model history. A match establishes descriptor reproduction only.

## Caller inputs and interfaces

The typed API is:

```text
point_projection_options_v2(config, version_column?, version_type?, star_contract?, business_star_columns?, max_projected_sql_bytes?, max_descriptor_bytes?)
point_projection_verification_options_v2(max_checks?, grammar_options?)
verify_point_projection_v2(config, original_sql, original_typed_parameters, independent_options, supplied_descriptor, budget?)
point_projection_check_v2_json(result)
```

The options constructor returns `Result[PointProjectionOptionsV2, String]`. The config is an independent `SQLConfigV2`; a config carried by independently supplied options must equal it after strict V2 normalization. Neither config nor options is selected from the supplied descriptor. Options JSON may omit its redundant config, in which case the independent config argument is used; a conflicting redundant config is invalid. Options reject unknown fields, version/business collisions, non-int64 version types and invalid star policy.

`verify_point_projection_v2_json(config_text, original_sql, typed_parameters_text, independent_options_text, supplied_descriptor_text, budget_text)` is the separate V2 JSON entry in the small existing V2 bridge. It accepts no V1 wire or source-admission result. Private tokenizer, identifier and canonical JSON helpers are shared with the independent grammar; the V1 wrapper and its acceptance remain unchanged.

Projection options normalize to the exact frozen Python fields: `config`, `versionColumn`, `versionType`, `starContract`, `businessStarColumns`, `maxProjectedSqlBytes` and `maxDescriptorBytes`. SQL bytes default to 131,072 with maximum 2 MiB; descriptor bytes default to 16 MiB with maximum 64 MiB. Independent verification budget JSON has `maxChecks` (default/maximum 1,000,000) and separate `grammarOptions`. Zero check/grammar budgets return unknown. JSON byte/depth caps apply before construction. The V2 step counter includes parameter/field/construction work and its private star-token scan; grammar has its own separately supplied budget. These bounds do not claim total process RSS.

## Original typed parameter observations

The input follows the frozen Python serialization exactly:

```json
{"container":"none","items":[]}
{"container":"tuple","items":[{"pythonType":"int","decimal":"7"}]}
{"container":"list","items":[{"pythonType":"uuid.UUID","value":"a8098c1a-f86e-11da-bd1a-00112444be1e"}]}
{"container":"dict","items":[{"name":"same","value":{"pythonType":"int","decimal":"12"}},{"name":"Name","value":{"pythonType":"str","value":"100% raw"}}]}
```

These are four separate observations, including empty tuple/list/dict versus None. Dict items are an ordered array; duplicate names cannot impersonate a Python dict. Scalar tags are exactly `bool` with a JSON boolean, `int` with canonical exact int64 decimal text, `str` with original text, or `uuid.UUID` with canonical `str(UUID)` text. An uppercase/32-hex string remains a string observation; it is not relabeled as a UUID object.

The verifier derives semantic JSON solely for independent V2 grammar/binding/identity checks. It preserves the original typed record separately and takes snapshots of mutable caller atoms. `typedInputBindings` comes from the independently bound canonical values: UUID identity is always recorded there as `pythonType="str"` with lowercase hyphenated text. `parameterMap.value` instead retains the original atom, including UUID object type or original string spelling. Occurrence order creates the new positional mapping; original dict item order remains intact. Literal values also become new typed positional parameters and are never interpolated into generated SQL.

## Exact deterministic construction

The rebuilt descriptor includes the original candidate, original SQL and hash, typed observations, independently normalized options and hash, generated SQL and hash, parameter occurrence map, business/native ordinals, hidden image roles, OLD/NEW aliases and required proofs. The entire descriptor is compared, including fixed false flags and proof arrays.

Generated identifiers are always quoted, embedded quotes are doubled and literal percent signs in identifiers are doubled for positional psycopg formatting. Values retain their original spellings and percent signs in parameter observations. UUID slots use `CAST(%s AS UUID)`. Fresh private aliases follow the frozen deterministic collision rules.

SELECT preserves original business column/alias order and appends the configured same-row version column. DML uses PostgreSQL 18 `RETURNING WITH`, with original business RETURNING columns first: NEW for INSERT/UPDATE and OLD for DELETE. Hidden INSERT NEW, UPDATE OLD/NEW and DELETE OLD complete images follow in their exact native positions with fixed int64 versions. Hidden write images are write-effect observations, not SELECT/predicate-read facts. DELETE sets `producesDeletionVersion=false` and does not create a deletion/tombstone identity. No-original-RETURNING DML remains `businessResult.mode="no-result"`; hidden outputs cannot be delivered directly as business results.

The frozen descriptor's construction contract and driver-format strings retain their original `/v1` suffixes. They are compared as literal construction identifiers; this does not invoke V1 wire verification or authorize V1 source formats as V2.

## Star policy remains an unproved declaration

Star result expressions are refused by default. An independent `preinstallation-business-schema/v1` policy must list the key and business columns in exactly configured order, excluding version metadata. A symbol star is found only after independent grammar validation; quoted identifier/literal/comment stars do not trigger wildcard policy.

For actual star expressions the expected descriptor retains the unverified business view and all four additional obligations:

- `preinstallation-physical-columns-and-order-equal-declared-business-star-view`
- `version-column-newly-installed-and-not-an-original-business-column`
- `postinstallation-only-declared-version-column-added-to-original-table-schema`
- `independent-MoonBit-catalog-installation-and-business-star-projection-recomputation`

Recomputation does not prove any of these catalog/installation facts. Embedded policy, catalog/installation booleans or current-native-star equivalence claims cannot authorize a star or remove obligations.

## Results and remaining boundaries

The result format is `moontxnwitness-point-projection-verification/v2`: `matched` means full reproduction, `mismatch` means a changed descriptor or original binding claim, `unknown` means unsupported grammar/policy or exhausted independent budgets, and `invalid` means malformed independent inputs/options/typed observations. Only matched is valid. `expectedDescriptor` is a bounded diagnostic reconstruction, not an executable capture object.

`databaseExecuted`, `databaseSyntaxValidated`, `sourceAuthenticated`, `captureFactsProduced`, `sourceFactsProduced`, `completeWindow`, `modelCoverageAccepted`, `moonbitProjectionVerified` and `commitVerified` remain false. No result establishes actual statement success, native result adaptation, source DDL, maintained unique versions, negative-read sources, closed writer windows, commit effects or an isolation-model conclusion.

## Narrow offline checks

```text
moon test src/point_projection_v2_wbtest.mbt --target js --deny-warn --jobs 1 --target-dir <isolated-build-dir>
moon build src/sql_projection_v2_bridge --target js --release --deny-warn --jobs 1 --target-dir <isolated-build-dir>
python -B scripts/point-projection-v2-cross-inputs.py --projection-root <frozen-Python-worktree> --dependency-root <existing-pinned-deps> --recorded-receipt <r3-receipt.json> --output <isolated-log-dir>/projection-cross-inputs.json
node scripts/point-projection-v2-cross-test.mjs --core <isolated-build-dir>/js/release/build/sql_projection_v2_bridge/sql_projection_v2_bridge.js --inputs <isolated-log-dir>/projection-cross-inputs.json --output <isolated-log-dir>/projection-cross-validation.json
```

The fixture producer reads frozen Python source/docs and the unchanged r3 receipt, records their hashes, uses independent configs/options, and constructs additional real Python descriptors using the existing pinned SQLGlot dependency. It imports no database driver/ORM and performs no DB calls. Reusing 33 descriptions that were executed in a separate prior run establishes only current descriptor reproduction; this verifier does not repeat or authenticate that execution lifecycle. Cross checks also cover collisions, percent escaping, literal int64 bounds, all parameter containers, repeated named parameters, UUID object/string spellings, embedded authorization, options conflicts, star obligations, OLD/NEW aliases and metadata-index tampering.

Development validation passed 13 new MoonBit tests (including 20 complete frozen Python descriptor hashes), plus 10 V2 grammar and 23 V2 result regressions. Separate compiled cross-validation passed 101 checks: 33 recorded r3 descriptions, 25 newly constructed frozen Python descriptions and 43 explicit tamper cases. The frozen worktree files and r3 receipt remained unchanged. These counts are bounded development checks, not a full-suite run, new DB execution or acceptance of any remaining source/model obligation.
