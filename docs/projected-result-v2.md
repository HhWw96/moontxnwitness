# Projected native result and business delivery consistency v2

This MoonBit component checks supplied observations from the synchronous V2
point producer. It independently reconstructs the SQL projection, then checks
the actual projected native buffer, hidden row images and business deliveries.
It does not turn the projected buffer into an original, unmodified SQL result.
It performs no driver call, database operation or history/model admission.

## Independent inputs

`verify_projected_result_v2(config, original_sql, original_typed_parameters,
independent_projection_options, supplied_descriptor, native_frame, deliveries,
options~)` returns `ProjectedResultCheckV2`. Obtain a detached Json with
`projected_result_check_v2_json`. Configuration and projection options are chosen
by the caller; embedded descriptor options cannot grant their own authority.

`verify_projected_result_v2_json` takes the same eight arguments as text, with
the original SQL as its second argument. `options_text` accepts only
`maxChecks`, `maxCellBytes`, `maxTotalBytes`, `maxDeliveryRecords` and
`projectionBudget`. Defaults are 1,000,000 checks, 65,536 cell bytes, 262,144 total
decoded payload bytes and 1,024 delivery records. Maximum total bytes is 1 MiB;
other maxima equal their defaults. Zero budgets are valid and yield unknown
when they prevent a required check. Invalid option fields/ranges are refused.

The independent `projectionBudget` retains its own `maxChecks` and
`grammarOptions` fields. These control descriptor reconstruction separately from
native-field, image and delivery checks. No grammar assumptions are selected
from the report. `projected_result_options_v2` exposes the corresponding typed
labelled arguments. Native-frame wire bytes are limited to 2 MiB and delivery
wire bytes to 4 MiB. Limits describe bounded verification work, not total RSS.

## Existing producer frames

The native argument is the original `configured-point-native` frame payload:
`resultId`, `projectionNoteSeq`, `connection`, `cursor`, `tx`, `statementSeq`,
`native` and `sourceFactsProduced`. Its nested native format is
`moontxnwitness-projected-native-result/v2`. The checker accepts the existing
payloads directly; it does not invent `nativeNoteSeq` or `deliveryNoteSeq`.

`projectionNoteSeq` must be present and positive. It remains an observation
reference in a different journal from `statementSeq`; numerical equality or
relative order between those domains is not inferred. Result/connection/cursor/
transaction/statement identities are preserved and compared with every actual
delivery payload. This checks consistency of those references; independent
validation of the sealed lifecycle and original frame positions is still needed.

## Checks

- Rebuild the entire descriptor with the existing independent MoonBit V2
  projection verifier, including original typed arguments, SQL, parameter map,
  aliases, hidden field positions, options, proof obligations and fixed flags.
- Require successful text TUPLES_OK in an active transaction, UTF8 native
  encoding, a positive backend PID, and a zero-or-one-row command count agreeing
  with both the original command-status bytes and the typed integer getter.
- Match field names, order, scalar OIDs and text formats even for empty results.
  Check bounded table/column/typmod metadata, canonical base64 and exact decoded
  int64/boolean/text/UUID values. Version fields must be positive native bigint
  values. Physical catalog provenance remains a separate obligation.
- Decode complete SELECT/read, INSERT/NEW, UPDATE/OLD+NEW or DELETE/OLD images.
  All observed keys must equal the independently bound original point key.
  INSERT values must match every original assignment. UPDATE values must match
  assigned arguments and preserve each unassigned column; its two version
  identities must differ. Business RETURNING must agree with the appropriate
  hidden image. DELETE never supplies a new deleted-row version.
- Compare actual fetch collection/row/scalar types and values with business
  columns at their exact native positions. Hidden columns cannot be delivered as
  business rows. Positions must be continuous; rewinds/repeated delivery cannot
  establish completion. Omitted/zero fetchmany requests use the producer's
  observed resolved size, matching pinned psycopg behavior.
- One delivered row completes a one-row point result without an extra EOF fetch.
  An empty read requires a meaningful actual fetch; a zero resolved size or no
  fetch remains partial. No-original-RETURNING DML instead checks the complete
  hidden native observation and requires no business-delivery records.

The existing V2 grammar still requires bound UUID identities and bound write
assignments. Supported literal point keys retain their exact typed values;
unsupported UUID literals or literal write assignments remain unknown.

## Results and evidence

`matched` means this bounded consistency check completed; `partial` means an
actual row result was not completely delivered; `mismatch` means supplied claims
conflict; `unknown` covers missing/unsupported observations or exhausted work;
`invalid` covers malformed independent options and wire structure. Only matched
is valid. The report retains decoded rows, complete image observations, verified
business deliveries, the projection check and bounded original observations.

All database-execution, source/authentication, catalog/mapping, complete-window,
absence, commit/effective-write and model-admission flags remain false. An
image-consistency check is not a source fact, a zero-row command is not an
absence source, and a reported backend/transaction identity is not authentication.

The narrow white-box suite freezes 12 unchanged native/delivery frame pairs from
an existing PostgreSQL 18.6 producer campaign: three primary-key layouts times
SELECT/INSERT/UPDATE/DELETE. Its original receipt SHA-256 is recorded alongside
the fixture payloads. Additional cases are explicitly synthetic tamper/boundary
inputs. These tests replay existing observations and execute no database. Run
only `src/projected_result_v2_wbtest.mbt` to reproduce the narrow check; broader
cross-target and complete-window validation is reported separately.
