# Fixed base-user CRUD promotion protocol

The independent `orm_profile_source_v3_json(envelopeText, analysisOptionsText)`
entry is a candidate integration for an explicitly configured PostgreSQL18 test
or preproduction window. The existing `orm_sql_source2_v3_proof_json` entry keeps
its diagnostic behavior, `history:null` and `analysisCoverageAccepted:false`.
The new entry is not yet a database acceptance claim: the original automatic
profile bundle must pass the same core checks before this capability is released.

## Input and observed source

The envelope contains exactly these fields:

| Field | Required content |
|---|---|
| `format` | `moontxnwitness-orm-profile-source/v1` |
| `profile` | `fastapi-users-sqlalchemy-7.0.0-pg18/1` |
| `traceText` | Original diagnostic v3 export, unchanged |
| `sourceJournalText` | Original sealed `orm-source-draft/2` JSONL, unchanged |
| `lifecycleText` | Original sealed scoped instrumentation JSONL, unchanged |
| `journalIndexText` | Original synchronized journal index text, unchanged |

The fixed profile uses the already verified SQL and eight-column same-statement
source transport. It preserves the business's six result columns and actual
result delivery. Both a present point lookup and a proven absent point lookup
are reads of the observed version. Creates, updates and deletes retain their
actual predecessor, row image, presence, new version and native command result.
A zero-row conditional command is not synthesized into a SELECT or a write.

Initialization and finalization are separately recorded real control
transactions. Their original raw PGresult fields, installation nonce, table and
owned catalogs, trigger/function definitions, snapshot, complete effect ledger,
source chain and native COMMIT acknowledgements are checked by MoonBit.
The sidecar's opening and closing records refer to those actual source query
sequences. Its quiescence marker alone does not establish completeness.

## Promotion checks

The new entry recomputes the old source proof from the raw texts. It then checks:

- Every original statement and delivered rows event has exactly one proven
  same-statement fact. No hand-authored register facts enter the raw SQL window.
- Actual execute calls refer to the original transaction and statement. All
  original transactions have paired driver calls and confirmed completion.
  A COMMIT request requires the actual native response inside its matching call;
  the request, connection, transaction, command tag and terminal event agree.
- Exactly one engine attachment precedes every observed connection, pool lease and
  driver call. Checkouts/checkins are balanced; active calls and transactions may
  not survive quiescence or detach. Unknown lifecycle records, invalidation,
  implicit reset outcomes and unreturned leases remain inconclusive. A local
  connection factory without a typed attachment proof remains diagnostic.
- Each execute has exactly one original statement. Null-transaction pool rollback
  is allowed only as an administrative call with no SQL or transaction facts;
  an unmapped execute is never treated as an implicit SAVEPOINT.
- Decimal monotonic observations independently bind each driver call and the
  opening/quiescence/closing/detach interval. They do not establish database
  snapshots or transaction real-time order.
- Worker calls stay after initialized opening and before recorded quiescence.
  The final controls bind the actual same installation, snapshot and ledger.
- The generic journal is closed and its durable tail, event count, segment
  descriptor ranges and active/unread references match the original export. Its
  self-checksum is recomputed from the original index bytes with only the
  top-level digest member elided, preserving numeric spelling and Unicode.
- Unknown SQL, errors, batches, missing observations, unproven source versions,
  uncertain outcomes and additional coverage gaps prevent complete promotion.

From these checked facts, MoonBit derives a separate point-register history,
validates it using the existing normalizer and parser, then applies the existing
bounded analysis. Original observations and gaps are not overwritten. Derived
sequence numbers retain their original event references in `retainedOriginalSeq`.

## Result and boundaries

`originalDiagnosticCoverage` and `originalSourceProof` remain diagnostic, including
the original `sourceClosed:false` state and diagnostic gaps. `mappingCoverage`
records the separate profile proof. `analysisCoverageAccepted:true` means this
supported source mapping has completed; the analysis can still be inconclusive
because of its existing size or computation budget.

The result binds all four original texts by SHA-256 and includes the derived
history, normalized facts, analysis, exact analysis options and execution counts.
Hashes provide integrity and reproducibility; they do not authenticate a database
or collector. Without original segment payloads, the core checks the index's
semantic bindings and raw-text digest, not the underlying segment byte hashes.
The export path's separate storage verifier remains necessary for those bytes.

The configured scope is FastAPI Users SQLAlchemy v7.0.0 base-user lookup by ID,
create, supported field update and delete, with SQLAlchemy2.0.55 and psycopg3.3.6.
`get_by_email()` with `lower()`, OAuth JOINs, arbitrary SQL, batch execution,
range/predicate queries, automatic schema changes and a complete authentication
system are outside this contract. No database snapshot or real-time relation is
inferred from client BEGIN timestamps.
