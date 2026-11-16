# Explicit point-source installation components v2

`install_configured_source_v2(connection, output, config, policy, opt_in=True)`
installs a new, private row-version source for one `SQLCaptureConfigV2` table.
The V2 contract supports int64, explicitly declared C-text and UUID primary keys
without constructing or relabeling a V1 configuration or receipt.

Use a dedicated idle autocommit control connection acting as a non-login,
non-privileged owner. That owner needs permission to create the private source
schema. Declare separate non-privileged writer login roles through the existing
immutable `SourceInstallPolicy`; grant only the required business DML and schema
usage. Installation rejects unsafe ownership/membership, writer trigger/truncate
privileges, unexpected triggers, rules, RLS, inheritance and unsupported types.
It does not grant application privileges or create writer credentials.

The installer obtains an acknowledged exclusive table lock, retains native
catalog observations, adds the fresh bigint version column, installs reviewed
triggers and creates the private initial/effect ledger. It checks all configured
columns by name, preserving actual physical order. Every supported column is
non-NULL; a UUID identity requires the native `pg_catalog.uuid` OID. Changing the
primary key is outside this source contract and is rejected by its write guard.

Before/after catalogs record exactly the added metadata and unchanged business
columns. A star view is applicable only when its independent declared business
order matches the actual preinstallation physical order. Explicit column
projection works when the primary key appears elsewhere physically.

Initial rows and their initial ledger entries are compared individually and by
complete bounded inventory/count. Success requires the actual native COMMIT
response and sealed raw log; requests and decoded control returns alone do not
establish a confirmed installation. Original SQL, native bytes, decoded results,
failures and sealing status use separate V2 records. Failure retains the
original exception; an uncertain COMMIT or failed final seal requires inspection
of the owned schema before any retry.

`catalogComponentsChecked` and the initial component checks describe this Python
installation check. Source authenticity, independent MoonBit installation
verification, complete writer-window closure and model-history admission remain
separate obligations. Their flags stay false. DELETE ledger identifiers are
event identities; they do not assert a new deleted-row version.

## Validation

The unit suite has 30 checks and 70 subtests, including native catalog types,
permissions, physical order, bounded raw logging, incomplete acknowledgements,
seal failures and original exception identity. Run with a fresh
`MTW_SOURCE_V2_TEST_ROOT` using unittest discovery for
`test_configured_source_v2.py` under `integrations/python`.

The real PostgreSQL 18.6 campaign runs all three primary-key types using separate
owner/writer roles. Each installs one initial row, then executes committed
INSERT, UPDATE and DELETE through the V2 wrapper. It compares the actual return
values, writer login/PID checkpoints, unique ledger identities and predecessor
links, verifies the final table, and checks the primary-key guard. It uses an
explicit physical order with the primary key last. All three layouts passed.

`scripts/configured-source-v2-postgres.py --help` documents the owned-cluster
runner. Raw database files and original receipts remain outside the repository.
The earlier setup-permission and test-exception failures are retained separately;
the successful campaign does not count as complete window/model acceptance or a
performance measurement.
