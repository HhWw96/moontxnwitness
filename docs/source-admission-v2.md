# Independent source-installation admission v2

MoonBit independently replays successful explicit V2 source installations before
their catalogs and initialization facts can be used by a window verifier. It
does not trust the Python component-check booleans or infer installation from a
matching report digest.

`verify_source_admission_v2(config, policy_value, original_log, receipt,
max_checks~)` accepts a caller-selected `SQLConfigV2` and source policy, the
original V2 log and its receipt. `source_admission_v2_json` returns a detached
report. `verify_source_admission_v2_json` exposes five text arguments, with the
last argument containing independent `{ "maxChecks": ... }` options. The default
and maximum are 1,000,000 checks; zero is valid and prevents a positive result.
Unknown option fields and out-of-range values are invalid.

## Original protocol and checks

The verifier reads `moontxnwitness-source-installation-log/v2` directly. Each
control operation has separate request, native-buffer and actual-delivery
records. It checks their exact sequences and references, original UTF-8/base64
text, scalar/row collection types, status/command tags and typed command-count
getters. It then checks the complete command order against independently
constructed SQL and parameters, including BEGIN, safe string/search-path
settings, exclusive initialization locks, catalog queries, DDL, row/ledger scans
and the actual COMMIT acknowledgement.

Catalog checking covers the dedicated owner and declared writer roles,
privileges, table identity, non-NULL scalar types, native UUID OID, primary key,
version uniqueness, the private sidecar inventory and exact trigger functions.
The V2 function includes its explicit immutable-primary-key guard. Business
columns are resolved by name while retaining their actual physical order.
Before/after attributes must be unchanged except for the appended version
column; star-view compatibility is separately recomputed.

Every initial visible row is compared with its complete initial-ledger entry,
including key, values, version, writer identity and original backend. Complete
inventory counts and the original initialization digest are checked in addition
to row content. Recomputed outer hashes cannot conceal weakened source guards,
changed row values, mismatched native delivery or ROLLBACK in place of COMMIT.

The independent log limit is the selected source policy (at most 64 MiB), with
at most 65,536 records, 512 KiB per record, one native text row per query and
128 KiB per native cell. The input schema and algorithm remain separate from V1;
only pure query/DDL and scalar helpers are reused internally.

## Outcomes and later admission

`installationVerified: true` requires all required checks and the acknowledged
installation to complete. Budget exhaustion and unsupported/incomplete semantic
premises return `unknown`; inconsistent observations return `mismatch`; malformed
wire inputs/options return `invalid`. Older installation logs without an
observed safe search path remain unknown under this V2 admission rule.

The report retains the verified catalog, environment, original complete initial
rows and initial effects for independent snapshot replay. It records actual
`execution.checks` and `execution.limit`. Collector authentication, full writer
window closure and model-history admission are separate: `sourceAuthenticated`,
`sourceFactsProduced`, `completeWindow`, `writerWindowVerified` and
`modelCoverageAccepted` stay false here. Existing V1 source and evidence replay
rules are unchanged.

## Validation

The scoped test suite has 13 tests, including three frozen, original PostgreSQL
18.6 installations with int64, C-text and UUID identities. It checks caller
budgets/policy, receipt tampering, weakened owner/trigger privileges, changed
UUID types and initial ledger values, native-delivery mismatch, command getter
disagreement, failed COMMIT acknowledgement and older missing-search-path logs.
Tamper cases recompute the outer log seal and receipt hashes before verification.
The scoped verifier run replays retained inputs and does not execute a database.
