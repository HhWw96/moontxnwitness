# Independent installed-source component checks (v4 candidate)

This separate namespace recomputes the configured PostgreSQL installation component from original control observations. It does not accept Python `catalogVerified` or `initialSnapshotVerified` as authority, and it does not change existing history/classification/capsule behavior. This development patch passed a single-target JS deny-warn check/build, 37 new MoonBit white-box tests, 56 SDK/boundary checks and an offline replay of the actual 260-row installation. It still requires independent review and integration; these checks do not complete the source window or driver projection.

## Caller inputs and limits

`verify_source_installation_v4(config, policy, original_log, receipt, max_checks~)` accepts the opaque configured SQL object, a caller-supplied policy, the exact newline-terminated source-control journal, and its receipt. The policy is separate from the receipt and includes an explicit namespace, distinct writer logins, initial row budget and bounded recording budget. The actual caller controls the independently counted check limit, 0–1,000,000. The report cannot raise that limit.

The text API `verify_source_installation_v4_json` accepts configuration (256 KiB), policy (8 KiB), original log (8 MiB), receipt (2 MiB), and options (8 KiB). Duplicate JSON keys, including Unicode-escaped duplicates, are rejected by MoonBit before interpretation. Options accept only `maxChecks`. Pass original JSON text for int64 values outside the JavaScript safe integer range; the SDK rejects unsafe materialized numbers rather than silently rounding them. A producer log larger than this first verifier's 8 MiB limit is an explicit unsupported case even if the producer had a larger recording budget.

`SourceInstallationCheckV4` is opaque. `source_installation_check_v4_json` returns a detached snapshot. `verify_source_installation_report_v4_json` recomputes under the caller's expected options; it never adopts options from a supplied report. Report replay confirms consistency of supplied evidence, not collector authenticity. The receipt digest in the result is explicitly a canonical JSON digest; the journal digest binds the exact original UTF8 bytes.

## What is independently recomputed

- Every original journal sequence, paired request/result, original SQL and parameters, native status/columns/raw text cells, and actual decoded delivery. Native base64 must be canonical and decode to the same UTF8 cell as the delivery; parsed JSON remains duplicate-sensitive. The final seal, record/byte counts and exact journal digest are checked.
- The fixed PostgreSQL control queries, source functions and complete DDL sequence are regenerated from the caller configuration and policy. Business identifiers, quoted names, Unicode key arguments, writer strings and the apostrophe/backslash namespace are independently bound. The fixed query texts define this versioned protocol; they are not arbitrary producer-described queries.
- BEGIN, string settings, acknowledged table locks before the first catalog SELECT, exact table OIDs, actual held lock inventory, non-privileged owner/writer admission, complete ordered column/type inventory, deterministic `pg_catalog.C` text comparison, single immediate primary key, metadata column and unique version index.
- Exact ALWAYS trigger scope/arguments/function body/owner/settings, private object ownership and ACL inventory, non-cycling bigint sequence and source scope. Unsupported RLS, inheritance, rules, event triggers, domains and generated/identity columns remain visible.
- Every locked initial row, its exact typed values, monotone unique installed version and per-table typed primary-key uniqueness. Composite index identities use structured canonical JSON, not delimiter concatenation. Oversized row sentinels, missing columns, incorrect scalar types, incomplete paging and exhausted row/check budgets cannot become accepted initialization.
- Initialization ledger command counts, final observed ledger/scope rows, initial digest, receipt catalogs/counts and actual COMMIT response with IDLE state. A COMMIT request with ROLLBACK/unknown response is insufficient.

A successful result is `matched-components`, with `catalogComponentVerified` and `initialSnapshotComponentVerified`. It always retains `sourceFactsProduced=false`, `sourceAuthenticated=false`, `writerWindowVerified=false`, `driverFetchVerified=false` and `isolationModelChecked=false`. Caller-known hashes do not prove absence of privileged writers or later DDL.

## Initial-source fetch consistency

`verify_source_fetch_mapping_v4` accepts an opaque installation check, original execution, native result, actual fetch deliveries, and a separate `caller-asserted-installation-epoch/v1` context with installation journal digest and database OID. This context only identifies the supplied installation; it does not authenticate a server or observer. OIDs may be reused across databases or server lifetimes.

The mapper independently runs the existing SQL/binding/native/fetch verifier. It accepts only the original business configuration or its deterministically derived installed-column configuration; candidate configuration headers select between two independently verified contracts and never authorize an arbitrary descriptor. No SQL is rewritten or executed. It then binds actual result table OIDs, physical column numbers and types to the independently checked installed catalog.

A first mapping requires the original SELECT to return the stored `__mtw_source_version` column and every modeled business column, with an actual initial version whose row values match those delivered. Sidecar data never fills unreturned business values. A result that omits the stored version, is empty, omits business columns, is not exhausted, or references an unobserved post-initial version stays unknown. No SELECT is invented for zero-row condition writes, and RETURNING does not become a complete predicate read.

The result `matched-initial-components` establishes only supplied initial-row/native-delivery consistency. It still has no completed writer window or authenticated provenance and cannot produce isolation-model facts. The full source stage needs separately verified barriers, observed writer/read coverage, transaction/connection epoch mapping, effective writes and source closure. Those are not implemented by this patch.

## SDK and offline replay

The separate bridge exports `verify_source_installation_v4_json`, `verify_source_installation_report_v4_json`, `verify_source_fetch_mapping_v4_json`, and `verify_source_fetch_mapping_report_v4_json`. The small `createSourceComponentsV4(core)` SDK wraps these as `verifySourceInstallationV4`, `verifySourceInstallationReportV4`, `mapInitialSourceFetchV4` and `verifyInitialSourceFetchReportV4`. It starts no driver, compatibility worker or database.

```text
node scripts/replay-source-components-v4.mjs --runtime <compiled-source-components-bridge.mjs>
node scripts/source-components-v4-test.mjs --runtime <compiled-source-components-bridge.mjs>
```

The patch includes 37 MoonBit white-box tests plus a 56-check SDK suite for raw/decoded disagreement, SQL/config/trigger/receipt tampering, original row values, unknown/duplicate options, exact budget boundaries, source-context mismatch, missing sources and independently budgeted report replay. The stated JS suites have been executed and passed. No other target, historical full suite, new database run, formal performance measurement or publication is claimed for this patch. The first SDK run stopped 33 of 56 checks at an omitted legal `CREATE TRIGGER` acknowledgement; its original failure report is retained. The implementation was corrected and a specific white-box regression added without altering the original 56 SDK assertions.

## Fixture origins and exclusions

`fixtures/source-components-v4/control.jsonl` and `receipt.json` are exact copies of the completed 24-check owned PostgreSQL installation over three unrelated 4/3/6-column tables with 260 initial rows. They contain generated test data. The source cluster is stopped; the offline verifier starts none. Private credentials/connection files and all PostgreSQL data files are excluded. `origin.json` records actual source hashes and this exclusion boundary.

`actual-fetch-other-installation.json` contains three actual full-column fetches from a different stopped owned cluster. They independently exercise SQL/native/fetch consistency but do not contain the new private metadata version. They cannot be relabeled as this installation's source mapping.

`SYNTHETIC-fetch-inputs.json` is explicitly synthetic: it uses real initial row/catalog values but constructs new execution/native/delivery frames without executing SQL. Its SQLGlot 30.26.0 candidates are actually generated by the optional parser. These are algorithm unit inputs, not evidence of a completed database source/fetch integration. Their positive mapping results must never be counted as a real driver source closure.

No database, migration, full build, performance experiment or publication is performed by this patch's offline scripts. The existing six source-installer files and earlier SQL/fetch freezes remain unchanged.
