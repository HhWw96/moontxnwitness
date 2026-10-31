# Configured startup and same-connection diagnostics

`startup.py` installs a local observer on a supplied psycopg factory or SQLAlchemy
engine before first use. It neither creates a connection nor changes database
schema. The application keeps its original SQL, fetch calls and connection
ownership. After workers stop, `session.seal()` returns the original input bundle.
Unsupported SQL, missing rows/columns and incomplete native delivery stay visible.

The optional source example uses the same three configured tables with 4, 3 and
6 business columns. `initial-queries.json` explicitly selects the installed
metadata column in addition to the actual business columns. No code rewrites a
business query. This is an explicit read-only demonstration consumer.

First provide an owned PostgreSQL 18 database, these configured tables and rows,
a non-login source owner role, and the login writer named in the policy. The owner
must own each table; the writer cannot be privileged, inherit ownership or change
triggers. The existing installer independently records and checks its catalog and
permissions. Do not run this example against an unprepared production database.

Install the hash-pinned optional requirements from
`integrations/python/requirements-configured-sql.txt` into the chosen environment,
or supply an existing trusted target with `--dependency-root PATH`. The controller
never installs or downloads a dependency.

Planning makes no database connection:

```powershell
python scripts/configured-session-postgres.py --config examples/configured-session/config.json --policy examples/configured-session/source-policy.json --queries examples/configured-session/initial-queries.json --output artifacts/new-owned-session
```

After building the applied patch's self-contained `configured_session_bridge`,
compute its SHA-256 independently. Execution needs an explicit DSN environment
variable and the exact runtime pin:

```powershell
python scripts/configured-session-postgres.py --config examples/configured-session/config.json --policy examples/configured-session/source-policy.json --queries examples/configured-session/initial-queries.json --output artifacts/new-owned-session --execute --dsn-env MTW_OWNED_PG_DSN --owner-role mtw_source_owner --runtime _build/js/release/build/configured_session_bridge/configured_session_bridge.js --runtime-sha256 CALLER_VERIFIED_SHA
```

The controller installs using the caller-owned physical connection, confirms
COMMIT, reuses that connection for the original SELECTs and actual `fetchall`,
rolls back the read-only transaction, seals original logs, then invokes MoonBit
replay with a caller-pinned runtime. Partial installation/failure receipts remain;
there is no automatic retry. Credentials are not written into artifacts or passed
to the diagnostic child environment.

Same-object connection reuse is a producer observation. It does not authenticate
the server or observer, close a complete writer window or provide post-initial
write effects. All source-fact, authentication, window and isolation-analysis
authority flags remain false. A model hint in table configuration is not a model
history. Run and review the diagnostic report before adding any fact projection.
