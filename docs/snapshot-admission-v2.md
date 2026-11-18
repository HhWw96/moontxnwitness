# Independent source-snapshot admission v2

`verify_snapshot_admission_v2` replays a single original PostgreSQL boundary
snapshot against an independently verified `SourceAdmissionV2`. It accepts the
original snapshot log, its receipt and caller-selected check/row/effect budgets.
It executes no SQL and performs no network or driver operation.

The separate semantic contract is
`postgres18-original-readonly-snapshot-complete-ledger/v2`. The result reports
`snapshotVerified: true` only after every required original observation agrees.
Installation and snapshot verification remain components of complete capture
admission; source authenticity, writer-window closure and model conclusions are
separate. Their flags remain false in this component.

## Original controls

The verifier independently parses the V2 control-request/native/delivery triples,
including exact sequence references, native text bytes, actual decoded control
deliveries, command-status bytes, count getter, transaction states and sealed-log
digests. Receipt flags and rehashed claims cannot authorize a query or its result.
Expected SQL and bound parameters are rebuilt from independent configuration.

Required controls include:

- acknowledged `BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY` and safe search
  path, original PostgreSQL snapshot identity and server peer;
- original environment, unchanged installed table catalog, owner/writer scopes,
  source sidecar catalog and complete configured source scope;
- exhaustive current-row enumeration and complete retained-ledger enumeration,
  both starting at zero independently in each snapshot;
- acknowledged read-only `ROLLBACK`, with no omitted or extra controls.

Native observations must use the declared PostgreSQL scalar types, including
canonical UUID identities. Visible rows are unique by primary-key identity and
version. Every visible row must equal its complete retained effect. Conversely,
every unconsumed live effect must be present in the complete current row set;
a consumed version cannot still be current.

Ledger entries retain INITIAL, INSERT, UPDATE and DELETE. INITIAL observations
are bound to the original installation ledger, including writer identity.
Updates/deletes require an existing, same-key live predecessor and cannot consume
it twice. DELETE event identities are preserved as ledger events and never
become live row versions. Writer identities must remain stable for each native
transaction ID, and committed entries must be visible in the recorded snapshot.

Version allocation order is used only for complete pagination. It does not
establish commit order or a cross-snapshot watermark. In particular a lower
allocated version can become visible after a higher allocated one. INSERT and
DELETE of the same key are not globally ordered by those allocation identities.

## Budgets and interfaces

The typed API defaults to `max_checks = 1_000_000`, `max_rows = 4_096` and
`max_effects = 4_096`. Their maximums are 1,000,000 / 16,384 / 16,384. Zero is valid;
an exhausted independent budget returns `unknown`, never a completed snapshot.
Producer limits remain observations and cannot increase the caller's budget.
Malformed input and inconsistent evidence are reported separately as `invalid`
and `mismatch`. Returned partial observations do not grant snapshot completion.

`snapshot_admission_v2_json` returns a detached report. Verified `rows` are keyed
by the original positive version string, with the complete original row and
control `requestSeq` / `resultSeq`. Verified `effects` retain their original
payload fields plus those control references. Peer, mode and log digests remain
available for later window admission. These locations do not authenticate the
collector or infer a transaction's client lifecycle.

`verify_snapshot_admission_v2_json` takes seven text arguments: independent
configuration, policy, original installation log/receipt, original snapshot
log/receipt and caller options. It independently repeats installation admission
before checking the snapshot. Options are `maxInstallationChecks`, `maxChecks`,
`maxRows` and `maxEffects`; their default budgets are independent. Reports and
embedded receipts do not supply the caller's authority or select executable code.

## Validation

White-box tests freeze original PostgreSQL 18.6 installation and snapshot logs
for int64, C-text and UUID primary keys. They replay the original installation
and complete end snapshot, plus an intermediate snapshot that contains version 6
but not the earlier allocated version 5. The end snapshot correctly includes
both. Tests also exercise independent budgets, rehashed row/ledger/SQL tampering,
initial writer identities, impossible writer visibility, source closure and
receipt self-authorization. Running these replay tests does not start a database
or claim a new database execution.
