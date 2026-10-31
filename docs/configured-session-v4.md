# Unified configured session diagnostics

The configured session namespace composes existing optional SQLGlot 30.26.0
PostgreSQL recognition, independent MoonBit SQL/parameter verification, native
libpq-to-actual-fetch comparison, returned-row WHERE/PK constraints, source
installation verification and initial-source mapping. Existing namespaces and
legacy analysis/capsule semantics remain unchanged.

## Interfaces

MoonBit exposes `ConfiguredSessionOptionsV4`, `ConfiguredSessionDiagnosticV4`,
`configured_session_options_v4`, `diagnose_configured_session_v4`,
`configured_session_diagnostic_v4_json` and
`verify_configured_session_diagnostic_v4`. Getters return detached JSON. Verification
recomputes the entire diagnostic record under independently supplied caller
options, rather than accepting budgets/status from that record.

The separate `configured_session_bridge` exports these JSON methods and the
underlying configuration, SQL, fetch and source-component methods. The JS factory
`createConfiguredSessionV4(core)` returns `diagnoseConfiguredSessionTextV4`,
`diagnoseConfiguredSessionV4`, `verifyConfiguredSessionV4` and
`normalizeConfiguredSessionOptionsV4`. Prefer original JSON text for exact int64
parameters and complete proof replay. Passing materialized unsafe JS integers is
rejected; the returned original frame texts retain precise native observations.

Python `ConfiguredDiagnosticSession` wraps only a supplied factory, connection or
engine. Default construction does not install source columns, execute SQL, fetch
results or patch a global driver. Install before the first connection borrow;
late borrowed connections cannot be retrospectively treated as covered. Stop
workers, then call `seal()`. Actual fetch ownership stays with the application.

## Original inputs and identity

The input envelope is `moontxnwitness-configured-session-input/v1` with four text
fields: `configText`, `lifecycleText`, `diagnosticTraceText`, `sourceInputsText`.
The last two may contain literal `null`. Optional source inputs retain exact
`policyText`, `logText`, `receiptText` and `sourceContextText`. The context still
states `caller-asserted-installation-epoch/v1`; it cannot authenticate a server.

The verifier checks original lifecycle sequence and seal, clock-domain binding,
unique structural `[connection,cursor,tx,statementSeq]` identities, actual outer
execution/native note references and result identities. It checks optional trace
statement SQL/transaction/connection bindings without renumbering producer events.
It does not infer commit order or logical sessions from observation sequence.
Unknown statements remain unprojected diagnostics; an encoded payload is not an
executed SELECT merely because a producer claims it is one.

Reports distinguish `resultConsistency`, `initialSourceStatus`, original producer
gaps, source/journal verification scope, unprojected statements and unmatched
executions. WHERE witnesses and initial mapping mismatches are diagnostic
contradictions, not isolation anomalies. Original execution/native/delivery texts
are retained alongside independent component evidence.

## Bounded work and reuse

Defaults are 1,000,000 journal checks, 32 results (maximum 128), 1,000,000 source
installation checks, and independent per-result fetch, returned-row and source
mapping limits of 1,000,000 each. All zero budgets remain valid caller requests.
The source installation is recomputed once into an opaque typed result and reused
across the batch. The mapping helper retains its own fetch and row checks; no
claim is made that all component work is deduplicated. Further cross-component
reuse needs a separate counter and evidence contract.

Input bounds are configuration 256 KiB, lifecycle and optional trace 8 MiB each,
source envelope 12 MiB, total bundle 32 MiB and report 64 MiB. Bounded details of
unprojected statements include a total count and a truncation indicator. Original
files remain intact if the producer cannot form a bounded inline bundle. Queue,
source-log or filesystem errors cannot silently make a complete input.

## Current result boundary

Every report explicitly keeps `sourceFactsProduced`, `writerWindowVerified`,
`sourceAuthenticated`, `serverInstanceIdentityAuthenticated`,
`isolationModelChecked`, and `isolationAnalysisReady` false. This namespace gives
a useful diagnostic workflow; it does not yet produce a complete model history.

Supported returned-row checks require actual business/predicate/PK columns and
ordinary supported native int64/bool/text values. Missing columns, NULL, unsupported
functions/JOINs, ambiguous/partial result consumption and unsupported ORDER BY
remain gaps. RETURNING is a write effect, not a complete predicate SELECT. Sidecar
lookups cannot fill business columns absent from actual delivery. Three arbitrary
table shapes use the same configuration and parser, without business templates.

Remaining source closure work is explicit: collect all writer/connection epochs
and outcomes across a complete window; exclude privileged/DDL changes with actual
before/after proofs; retain rollback/intermediate effects and original observations;
map post-initial effects; preserve source closure when exporting a window; and
prove negative/tombstone sources without choosing an arbitrary missing-row
version. Private transactional effect rows alone do not prove this closure.
Authentication is a separate protocol. None of these obligations is satisfied by
flipping a producer Boolean, reusing a backend PID, or querying a source later.

## Replay and preparation validation

Use `scripts/diagnose-configured-session-v4.mjs` with explicit runtime path and
SHA-256. It imports the exact hashed self-contained bytes, independently supplies
options, and refuses to overwrite existing report files. `--report` verifies a
whole supplied report. No runtime or source material is downloaded.

Prepared checks cover tuple collisions, interleaved connections, original trace
binding, WHERE/PK contradictions, unsupported native types, torn/missing logs,
zero/exact budgets, source-context tampering, cross-cluster inputs, and attempted
report authority upgrades. The inherited original installation observations,
other-cluster actual native fetches and synthetic mapping inputs retain distinct
origins. Re-grouped lifecycle test envelopes are explicitly synthetic.

See the patch preparation receipt for checks actually executed. The new MoonBit
module and consolidated SDK must be compiled/run in an integration checkout before
being described as validated or shipped. The same-connection PostgreSQL controller
is prepared, but no database run is implied by its presence or by mock tests.

## Installed SDK and diagnostic evidence

The standard build includes configured-session-core.mjs and the independent SQL/fetch bridges. The main SDK exports diagnoseConfiguredSessionV4, verifyConfiguredSessionV4, makeConfiguredSessionCapsuleV4 and replayConfiguredSessionCapsuleV4. The source-component and configured SQL/fetch functions remain separately callable through the same SDK.

The CLI commands diagnose-configured-session-v4, verify-configured-session-v4 and replay-configured-session-v4 use the same original session bundle. Caller options are supplied independently for verification and replay. A capsule binds exact original input/report strings and their SHA-256 values; its envelope cannot authorize larger budgets or claim source authentication. Successful replay means that the diagnostic recomputed identically.

CLI diagnostic exit 0 means the supported observation check executed. A returned-result mismatch exits 1, invalid verification exits 2, and input-unverified diagnostics exit 3. These statuses do not report isolation compatibility.

The owned PostgreSQL CI controller uses a fresh limited owner, writer and three configured table layouts, then performs explicit installation followed by actual initial SELECT/fetch on the same physical connection. It retains installation, lifecycle, input, result and execution records. This controller is prepared for CI and is not a claim that a complete business writer window has been observed.
