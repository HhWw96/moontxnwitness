# Configured FastAPI Users source profile

This separate opt-in profile records the real pinned base-user CRUD methods
without hand-written histories. Two actual PostgreSQL producer runs have passed
the six base-user checks. Independent mutation review found false complete
promotion in the first MoonBit candidate; that core gate is being repaired.
The profile remains a candidate until the corrected independent review passes.
The existing general diagnostic entry and old ORM source diagnostic keep their
original partial-coverage behavior.

The first configured scope is PostgreSQL 18, psycopg 3.3.6, SQLAlchemy 2.0.55 and
FastAPI Users SQLAlchemy v7.0.0 at commit
`6397ace506d829a2ee12786da5d724c3f4c6b634`. It covers the exact six-column base-user
table, known UUID point gets (including absence), create, update of declared
non-PK fields and delete. Original SQL templates and same-statement metadata
use the existing independently checked sourceSchema2 contract.

## Explicit setup and application entry

```python
from moontxnwitness_capture.orm import UserScope
from moontxnwitness_capture.profiles.fastapi_users import install_user_profile

scope = UserScope(controlled_schema, "observed_user", tuple(known_uuid_strings))
capture, control = install_user_profile(setup_connection, scope, "new-profile")
capture.attach_engine(engine)  # unused pool; normal sync/async psycopg engine

# Run the original application's base-user methods with its original engine.
# Stop its workers, finish transactions and return borrowed connections.
capture.finalize(control)
capture.export_profile("new-profile/profile-source.json")
```

The first promotion contract is limited to one `instrument_engine` attachment
before its first observed connection/checkout and maintained through finalization.
All leases must be returned before quiescence. Invalidations, missing or late
attachment, and detached outstanding leases must prevent complete promotion.
Direct connection factories retain diagnostic status in this first contract.
An idle connection may remain in the pool after check-in; disposing the pool
after capture finalization does not supply a missing transaction observation.

`setup_connection` is a native synchronous idle/autocommit psycopg connection
on the explicitly owned database. Installation is a transactional migration:
it adds a unique version column, state/candidate/effect tables, an installation
marker and checked triggers/functions. It verifies the actual native catalog,
locks the controlled relations, reads the initial state and observes the real
COMMIT acknowledgement. It never installs itself from `instrument_engine`.
Keep the output of a failed attempt and create a new capture after repairing
the cause. Closing without finalization remains an incomplete window.

This is a bounded controlled pilot. Declare 1–128 UUIDs before installation;
its triggers reject new IDs outside that domain. The schema uses the explicit
`mtw_orm_v3_...` namespace and the first catalog contract requires C/C database
locale, native six-column types, the original UUID primary index and unique
email index, and no unobserved DDL or extra trigger behavior. At most 512
surviving effects are admitted by the current final ledger. The migration and
metadata remain installed afterward; this entry performs no automatic removal.
An arbitrary production table or unrestricted dynamically generated IDs do not
meet this first profile's contract.

## What is preserved and independently checked

- Fixed recognition uses `UserScope` and `StructuredSQLCache`. It does not parse
  arbitrary SQL. The original SQL/parameters and the exact executed projection
  are both retained. No global driver function is replaced.
- Read versions and absence come from metadata joined in the same SQL snapshot.
  A source is published only when the original six columns or EOF are delivered
  to the DBAPI consumer. The async driver's existing adapter prefetch does not
  itself publish a read. There is no additional business fetch.
- Writes retain original native RETURNING metadata, predecessor, effect and
  command. The ORM sees the original command surface and six business columns.
  A zero-row UPDATE/DELETE has a source gap and never becomes an invented read.
- The original diagnostic has one directly observed initialized snapshot,
  keeps its diagnostic gaps and has `sourceClosed=false`. Initialization,
  controls, native raw cells, business rows and the final locked ledger are a
  separate sealed source journal. Original call/COMMIT observations stay in the
  lifecycle sidecar. No existing raw event or gap is removed during export.
- The new envelope contains original trace, source journal, lifecycle and index
  texts. Only the new independent MoonBit promotion may derive a history after
  verifying their bindings, whole statement/row coverage, actual transaction
  outcomes and both source windows. A producer receipt cannot grant coverage.
  Index binding alone does not revalidate event segment payloads not supplied
  to that verifier.

Unsupported SQL, `lower(email)`, OAuth JOIN, out-of-domain parameters, batch
writes, custom adapters/cursors, unknown outcomes or missing sources retain
visible gaps. This scope is base-user CRUD, not a complete authentication
system. Direct custom PGresult consumers and arbitrary native-driver behavior
are outside the new profile's stable surface. The original diagnostic entry is
available for those observations.

## Actual upstream example and verification

`experiments/business/fastapi_users/profile_demo.py` requires an existing checkout
of the exact upstream commit and an owned `MTW_PG_CONNECTION_FILE`. It checks the
runtime Python source bytes against Git, uses the real `SQLAlchemyUserDatabase`
methods for existing/absent get, create/commit/refresh, update/commit/refresh,
delete and a final absent get, and retains the generated source package.
Fixture schema creation and catalog startup precede the profile window; the
installer then rechecks the actual catalog. No startup SQL recorded inside the
window is silently dropped. A missing dependency or configuration is recorded
as not executed.

```text
python -B experiments/business/fastapi_users/fetch_upstream.py --output NEW_UPSTREAM
python -B experiments/business/fastapi_users/owned_postgres.py --bin EXISTING_PG18_BIN --upstream-root NEW_UPSTREAM/source --output NEW_OWNED_RUN
python -B experiments/business/fastapi_users/profile_demo.py --upstream-root PINNED_CHECKOUT --output NEW_DIRECTORY
python -B integrations/python/moontxnwitness_capture/test_user_profile.py
```

The optional first command fetches only the declared public Git commit and
retains its original license and source hashes. Its checkout is
`NEW_UPSTREAM/source`; it refuses an existing output directory and preserves
first failures. It does not install or alter the application's dependencies.

The second command starts and stops a new retained owned PostgreSQL cluster and
invokes the real producer. It never borrows or changes an existing cluster.
The third uses an already configured private connection file. The last command
uses fake native results to check cursor/source contracts; it does not replace
the real database run. Install the optional dependencies into an isolated Python
3.12 environment using `requirements-lock.txt`; its recorded first environment
used four retained wheels and a configured Tsinghua PyPI mirror for transitive
dependencies. They are not represented as official PyPI downloads.

The retained evidence distinguishes the first one-click wrapper's startup
NameError, its corrected actual run, and the independent promotion failures.
No raw event or first failed result is edited to obtain acceptance. The new
profile has not established complete application acceptance, multi-seed
concurrency coverage or performance targets. Its complete cost must be measured
separately from the diagnostic-plus-provenance A/B/C experiment.
