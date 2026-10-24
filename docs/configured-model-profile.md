# Configured list and relation driver profile (development)

This explicit profile is separate from diagnostic instrumentation and the frozen
base-user ORM profile. It installs a **new, owned PostgreSQL18 schema**, observes
one startup synchronous psycopg3.3.6 connection factory, and retains original SQL,
positional parameters, immutable native PGresults, actual business deliveries,
COMMIT responses, initialization and finalization control queries. It generates
no handwritten model history. The MoonBit model-projection entry must verify the
original package before granting mapping coverage.

The source envelope has exactly `format`, `profile`, `traceText`,
`sourceJournalText`, `lifecycleText`, `journalIndexText`. Its format is
`moontxnwitness-model-profile-source/v1`, profile `pg18-configured-models/1`.
Every source window contains one model. Raw diagnostic coverage and
`sourceClosed:false` are retained; successful independent projection is separate.
The index self-checksum and event descriptors bind original observations; the
envelope does not contain segment payloads and cannot prove their checksums.

## Supported first slice

- Append list: 1–8 installed keys, initially empty lists, point SELECT and one
  append per exact registered UPDATE. Each append has a globally unique bounded
  identity and a string business value. Repeated business values are allowed.
  Original JSONB list results preserve item order and identities.
- Relation: one table with signed int64 `id`/`balance`, boolean `active`, and text
  `region` using C collation; 1–8 installed write keys. Point SELECT and point
  INSERT/UPDATE/DELETE preserve the original four business columns. Same-statement
  hidden unique version/predecessor metadata binds actual write effects.
- Relation SELECTs may register up to eight exact AND plans, each with up to eight
  terms. Operators are eq/lt/le/gt/ge; booleans support eq. Parameter values remain
  the original DBAPI arguments. Only actual complete SELECT delivery, including
  a complete empty result, supports a predicate read. RETURNING is an affected
  write image and never a complete predicate observation.
- Explicit commit and rollback, original driver fetchone/fetchmany/fetchall, and
  repeated transactions on an observed connection. No prefetch consumes business
  results. Capture installation and source finalization consume only their own
  dedicated setup connection.

Unknown SQL, zero/multiple-row writes, unsupported types, NULL, JOIN, arbitrary
functions, aggregates, mixed models, batches, alternate cursor/row modes,
savepoints, unknown outcomes, and incomplete delivery prevent complete mapping.
Their original observations and business outcomes remain visible. No negative
SELECT or synthetic initial source is manufactured to repair a coverage gap.
The first slice covers the native synchronous factory; it does not claim ORM,
connection-pool, asynchronous, arbitrary-table or arbitrary-SQL support.

## Source proof

The producer records each controlled SQL request and its original text PGresult
beside actual decoded results. Reviewed exact DDL creates transactional source
state, unique identities/versions, immutable candidate effects and actual-effect
ledgers. Installation is acknowledged before any application connection opens.
Initial and final snapshots, ledgers, source state, function bodies, trigger
definitions and C locale are observed under an exclusive lock, with an actual
COMMIT acknowledgment. The explicit trusted scope is this owned database's
controlled writer population, not hash-based authentication of a remote server.

A source batch is published only after actual consumer delivery completes. It
binds one statement to all original rows-event sequences, original parameters,
original/executed SQL, native text-format cells/OIDs, the unchanged business
column description, command tag and affected count. The MoonBit verifier must
derive the operation from its own exact plans, decode cells independently,
require a bijection with every original statement and rows delivery, verify
actual call/transaction outcomes and reject all extra lifecycle activity.

The final committed effect ledger must match every committed observed write;
rolled-back writes must be absent. Unique predecessor/source chains and full
initial/final states close the source window. Model traces are newly derived,
retain original sequence references, and never overwrite the raw diagnostic.
The existing list/relation interpreters then enforce their unchanged exact
search limits (six committed transactions, 128 operations and explicit budgets).

## Reproduce development evidence

`experiments/model_profile_v3/driver_cases.py` runs original driver business code
and stores ten predeclared cases without semantic history input. Its owned
controller `owned_postgres.py --bin EXISTING_PG18_BIN --output NEW_DIRECTORY`
creates/stops only its own low-memory cluster and retains first failures.
Credentials and database data remain private; the public evidence selection
contains source logs, original envelopes and receipts only.

The first real producer run passed all ten database cases, including both real
Repeatable Read write-skew schedules, supported CRUD/append/rollback/results and
three deliberately unprovable paths. The new compiled MoonBit projection then
accepted seven supported original packages, rejected all three unprovable paths,
and agreed with the separately implemented Python list/relation interpreters on
all seven supported results (five consistent and two violations). Original
conservative source-binding/FK-hook refusals and compiler failures remain retained.
These are author development results; independent review and release acceptance
remain pending. No formal capture performance measurement has been run.
