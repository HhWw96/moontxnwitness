# Original native result and actual delivery consistency v2

This is an internal, independent consistency checker for supplied observations of the original, unmodified point-CRUD SQL. It does not wrap a driver, fetch a row, execute SQL, construct a source projection, or accept capture/source/model/commit facts. It is separate from the projected-SQL constructor and from all V1 wire formats and source-admission paths.

## Interfaces and caller authority

`verify_configured_result_v2(config, execution, native, deliveries, options~)` takes an independent `SQLConfigV2` and `ConfiguredResultOptionsV2`. It returns `ConfiguredResultCheckV2`; `configured_result_check_v2_json` returns a detached report. `verify_configured_result_v2_json` exposes the same bounded check through five JSON text arguments. The existing isolated `sql_projection_v2_bridge` exports that V2 function for testing, without changing any V1 entry.

Options are independent caller inputs: `maxChecks` (default/maximum 1,000,000), `maxCellBytes` (65,536/65,536), `maxTotalBytes` (262,144/1,048,576), `maxDeliveryRecords` (1,024/1,024), and separate `grammarOptions`. Zero budgets are permitted and cannot be overridden by a candidate. Byte accounting covers decoded native field names, command tag and cells, getter decimal text and delivered scalar text; check accounting covers grammar-independent result work. Native rows are limited to one and native columns to 17. Wire JSON byte/depth limits apply separately.

The checker internally reruns `verify_sql_candidate_v2` against the execution's original SQL, supplied JSON parameter values and raw candidate descriptor. It takes the descriptor, typed bindings and key reference from that independently rebuilt result. Candidate hashes, key fields, completeness flags and execution `success` cannot authorize a successful result check.

## Execution observation

Exact format: `moontxnwitness-configured-execution/v2`.

| Field | Meaning |
| --- | --- |
| `connection`, `cursor`, `tx` | Bounded observer identity claims; never authentication |
| `statementSeq`, `executionNoteSeq` | Positive bounded observation indices |
| `sql`, `parameters`, `candidate` | Original SQL, JSON parameter serialization and raw V2 descriptor |
| `sqlRewritten` | Must be false |
| `success` | Must be true and agree with the expected native success status/tag |
| `decoderContract` | Must be `psycopg-default-text-scalars/v2` |

The grammar report preserves the supplied JSON parameters and hashes them independently of UUID normalization. A JSON UUID string is not proof that the business argument was a string or a `uuid.UUID` object. A replay that serializes a previously observed Python UUID object must preserve its original type-tagged observation separately and state that the JSON value is a semantic serialization. No call arguments are changed by this checker.

## Native observation

Exact format: `moontxnwitness-native-result/v2`.

The native record contains `resultId`, the execution identity fields, `executionNoteSeq`, a strictly later `nativeNoteSeq`, original `sqlSha256` and `originalParametersSha256`, `status`, `clientEncodingBase64`, `commandStatusBase64`, `commandTuples`, `fields` and `rows`. `clientEncodingBase64` preserves the actual libpq `ParameterStatus(client_encoding)` bytes; they must strictly decode to `UTF8`. Missing encoding observations are not filled from assumptions or defaults.

`commandStatusBase64` represents the actual `pgresult.command_status` bytes. The operation and canonical nonnegative count are parsed from that original command tag. Supported point tags are `SELECT n`, `INSERT 0 n`, `UPDATE n` and `DELETE n`, where n is 0 or 1. Larger counts cannot complete this point contract.

Psycopg 3.3.6's `pgresult.command_tuples` getter returns an integer or None. It is **not a raw byte observation**. V2 therefore records it as `{"pythonType":"builtins.int","value":"1"}` (typed decimal integer observation), or preserves a None observation as `{"pythonType":"builtins.NoneType","value":null}`. The integer getter must agree with the independently parsed command-tag count. None is retained diagnostically and cannot complete this contract. Encoding `str(getter)` into base64 does not produce original libpq bytes and is not accepted as such.

Each native field has exactly `nameBase64`, `oid`, `format`, `typmod`, `tableOid` and `tableColumn`. Name bytes are strictly decoded as UTF-8 and compared with the original projection's output name at that exact position. `format` must be text (0), including when no rows were returned. OID compatibility is checked before reading cells, so an empty buffer does not bypass type/format checks:

| Declared scalar | Native OIDs | Default delivered Python type |
| --- | --- | --- |
| int64 | 20, 21, 23 | `builtins.int`, canonical decimal observation |
| boolean | 16 | `builtins.bool`, JSON boolean |
| C / UTF-8 text | 25, 1043 | `builtins.str`, exact text |
| UUID key | 2950 | `uuid.UUID`, canonical `str(UUID)` observation |

Native cells are original bytes encoded as canonical base64. NULL, binary formats, invalid UTF-8, NUL, incompatible OIDs and noncanonical integer/boolean/UUID representations cannot complete the check. OID 21/23 integer widths are checked in addition to the configured int64 bound. UUID native text must use PostgreSQL's canonical lowercase hyphenated identity. Text remains exact; no case folding or Unicode normalization occurs.

Physical table/column metadata is retained and checked for bounded numeric shape. It is not linked to catalog/source identities. `sourceColumnMappingVerified` is always false. Native fields and raw rows remain separate from any later source mapping.

## Actual delivery observation

Deliveries are an ordered array of `moontxnwitness-actual-delivery/v2` records. Every record contains matching result/execution identities, the exact `nativeNoteSeq`, a strictly increasing later `deliveryNoteSeq`, `method`, `resultPythonType`, `requestedSize`, `effectiveSize`, `start`, `rows` and `exhaustedObserved`. The actual result type is `builtins.list` for fetchall/fetchmany, `builtins.tuple` for a returned fetchone/iterator row, `builtins.NoneType` for an empty fetchone, or the observed `builtins.StopIteration` outcome for iterator-stop. An unrecorded collection/row type cannot be supplied from a default-driver assumption.

A row is `{"pythonType":"builtins.tuple","cells":[...]}`. A scalar is `{"pythonType":"uuid.UUID","value":"a8098c1a-f86e-11da-bd1a-00112444be1e"}`, or the corresponding int/bool/str observation in the table above. Custom row factories and scalar decoders are outside the contract. The original type tags and values are retained in `deliveryObservations`; the separately returned typed identities do not erase them. In particular, a delivered string with the same characters as a UUID object cannot impersonate `uuid.UUID`.

Supported methods are `fetchone`, `fetchmany`, `fetchall`, `iterator-next` and `iterator-stop`. For `fetchmany`, `requestedSize` preserves an explicit size or null for an omitted argument, and `effectiveSize` records the resolved size including an observed arraysize default. Pinned psycopg 3.3.6 resolves an omitted or zero request using the cursor's actual `arraysize`; a positive explicit request must equal the resolved size. Other methods require both sizes to be null. Positions must be continuous and values/types must match native cells at those exact positions. Claims of observed exhaustion before the known native rows were delivered are inconsistent.

A nonempty point result is fully delivered once the verified native row count and continuous actual delivery reach the same total. One `fetchone` row can therefore complete a one-row result without an extra fetch returning None. `exhaustedObserved: false` does not prove that more rows remain. For native row count zero, at least one meaningful actual fetch is required: `fetchone`, `fetchall`, a `fetchmany` with positive resolved size, or an equivalent iterator-stop observation. No fetch, or a fetch with resolved size zero, cannot manufacture a negative read. An exhaustion flag attached only to a zero resolved size cannot grant completion; its original claim remains in the raw observation.

For full-row SELECT, an actually returned key must equal the original independent WHERE key. For INSERT/UPDATE/DELETE RETURNING, this comparison is performed only if the original RETURNING actually includes the key. Int64, exact C text identity and canonical UUID identity are compared using the independently rebuilt descriptor/bindings. A wrong key is a mismatch even if native bytes and delivered values agree with each other. Missing RETURNING keys are never fabricated; `returnedKeyObserved` and `returnedKeyConsistencyVerified` remain false when no key was returned. These checks establish only consistency of supplied observations, never conditional facts or source provenance.

## Command-only DML and result reports

SELECT and original RETURNING require TUPLES_OK (2), the original field shape, native rows and meaningful actual delivery. DML without RETURNING requires COMMAND_OK (1), zero fields/rows, no delivery records, and an original tag/count consistent with the integer getter. A 0-row command is an admissible raw command observation; it is not an empty SELECT, absence proof, failed-condition fact or effective committed write.

The report format is `moontxnwitness-configured-result-verification/v2`. `matched` means this bounded supplied-observation consistency check completed; `partial` means delivery was incomplete; unsupported/missing observations and budget exhaustion produce `unknown`; inconsistent claims produce `mismatch`; malformed wire/options produce `invalid`. Only `matched` has `valid: true`. `completeFetchVerified` is reserved for row results; command-only success uses `commandObservationVerified`. Raw `nativeObservation` and `deliveryObservations` are preserved separately from decoded identity arrays.

`captureFactsProduced`, `sourceFactsProduced`, `sourceAuthenticated`, `catalogVerified`, `sourceWindowVerified`, `sourceColumnMappingVerified`, `modelCoverageAccepted`, `commitVerified`, `committedWriteEffectVerified` and `moonbitProjectionVerified` always remain false. No successful command or delivery observation establishes commit, installed unique versions, observed read-version identity, initialized absence, complete writer windows or any isolation-model conclusion.

## Bounded validation

Run the new result file and, when needed, the affected old fetch regression file; do not substitute a full-suite run for this scope:

```text
moon test src/configured_result_v2_wbtest.mbt --target js --deny-warn --jobs 1 --target-dir <isolated-build-dir>
moon test src/configured_fetch_v1_wbtest.mbt --target js --deny-warn --jobs 1 --target-dir <isolated-build-dir>
moon build src/sql_projection_v2_bridge --target js --release --deny-warn --jobs 1 --target-dir <isolated-build-dir>
```

Unit fixtures are synthetic supplied observations and do not claim actual database execution. Replaying previously recorded real buffers must preserve the original receipt, raw byte payloads, getter values and actual scalar type tags; event/position annotations derived for the fixture and missing original metadata must be identified explicitly. Such a replay cannot prove the actual lifecycle, observer authentication or metadata that the original receipt did not record.

The read-only recorded-payload runner requires a receipt containing actual fetch method, collection/row/scalar type observations and raw client-encoding ParameterStatus bytes. It verifies the recorded observer-source hash, uses independent fixture configs/options, preserves original typed Python parameter observations separately from semantic JSON serialization, and never imports a driver/ORM or starts a database:

```text
python -B scripts/configured-result-v2-replay-inputs.py --receipt <recorded-receipt.json> --observer-source <recorded-observer-source.py> --output <isolated-log-dir>/result-replay-inputs.json
node scripts/configured-result-v2-replay-test.mjs --core <isolated-build-dir>/js/release/build/sql_projection_v2_bridge/sql_projection_v2_bridge.js --inputs <isolated-log-dir>/result-replay-inputs.json --output <isolated-log-dir>/result-replay-validation.json
```

Development validation passed 23 new result unit tests, 32 unchanged V1 fetch regressions and 10 V2 grammar regressions. A separate replay passed 33 recorded original-SQL payload cases from an existing PostgreSQL 18.6 receipt and 20 explicitly synthetic fault cases. The replay itself executed no database operations. Actual payloads came from the original receipt; event identities/note positions and semantic-JSON digest links were fixture-derived, with no actual driver-wrapper lifecycle, source authentication, committed effect or model claim. Missing metadata in older receipts was not filled from assumptions, and the original receipts remained unchanged.
