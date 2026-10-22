# v0.1.3 ORM structural-cache candidate

This is an isolated, executable candidate. Nothing here has been applied to the main checkout, installed, published, compiled with MoonBit, or run against a database. It preserves the existing experimental ORM coverage gaps and does not promote a complete ORM history or the authentication system into stable support.

## Concrete change

The existing slice3 observer already compiles 35 exact SQLAlchemy plans for recognition. Its separate `StructuredSQLCache.match()` compiles each first executed shape again. The candidate's `prepare()` puts those constructor plans into the same bounded cache later used by `match()`. Exact original SQL still must match; every execution still independently validates the current parameters, declared UUID domain, actual rows and source cells.

The actual compiler comparison uses the existing SQLAlchemy **2.0.55** environment, all 35 shapes, and three executions per shape:

| Implementation | Actual compiler calls |
|---|---:|
| Original constructor plus separate first-use cache | 70 |
| Candidate cache enabled | 35 |
| Candidate cache disabled | 140 |

These are counted compiler calls, not measured wall time, throughput or memory improvements. The first-use duplicate work is removed; later hits in the original implementation were already cached.

## Copyable Python entry

`payload/integrations/python/moontxnwitness_capture/orm.py` provides the proposed explicit submodule. The package root `__init__.py` is unchanged. Basic imports need neither SQLAlchemy nor psycopg:

```python
from moontxnwitness_capture.orm import UserScope, SQLContext, StructuredSQLCache

scope = UserScope('mtw_orm_v3_example', 'observed_user', (
    '00000000-0000-4000-8000-000000000001',
))
cache = StructuredSQLCache(context=SQLContext(registry_epoch=1))
plan = cache.prepare(scope, 'get')  # Explicitly loads pinned SQLAlchemy here.
assert cache.match(scope, plan.original_sql, 'get') is plan
```

The optional experimental `ProvenanceObserver` and `SourceSink` are available by explicit import from the same submodule. All their imports are package-relative; no bootstrap, upstream checkout, experiments path, runtime `sys.path` mutation or file-path module loader is used. The source collector still requires an explicit compatible installation object made with this submodule's immutable `UserScope`. Installing or proving that migration is outside this cache change. Existing source observations remain component-local diagnostics.

The payload includes unchanged copies of `__init__.py`, `capture.py`, `capture_v3.py` and `journal_v3.py` so the complete directory can be copied independently. Only five new package files are in `candidate.patch`; an existing checkout already has the four unchanged dependencies. Apache-2.0 `LICENSE` is copied into the payload. No upstream business implementation is vendored into this candidate.

## Bounds and context

- Defaults: 128 entries and 1 MiB accounted retained-entry bytes. Hard configuration bounds: 1–256 entries, 4 KiB–2 MiB. Cache disabled retains zero entries. Oversized entries are returned without retention, preserving SQL semantics.
- Accounting recursively charges retained immutable entry graphs and a 512-byte entry/link allowance. Objects shared between entries are deliberately charged again. This excludes the fixed cache/lock/container header and is not an RSS limit. The pre-existing fixed 35-plan recognition map remains separate; this is not a bound on all observer memory.
- Cache keys include the complete immutable scope (schema, table and declared fixed UUID domain), immutable compiler/profile context, operation, canonical update fields and bind identity. The profile pins SQLAlchemy 2.0.55, PostgreSQL dialect/18 contract, psycopg 3.3.6 contract and the fixed payload layout. A loaded compiler-version change is rejected even on a warm hit.
- The caller must use a new `registry_epoch` or observer after installation, catalog assumptions or connection configuration change. The context is an explicit configuration contract, not automatic database metadata observation. Incompatible dialects/profile versions are rejected rather than guessed.
- No API accepts a business parameter dictionary, result object or transaction state for caching. The cache retains fixed SQL strings and immutable plan/profile identities only. Actual unrecognized SQL is compared but never retained. Active transaction/savepoint/commit logic and source decoders are unchanged.
- Known IDs must be a native immutable tuple. Constructor configuration/compiler failures occur before creating the new journal. This does not alter business SQL execution or its original driver exceptions.

## Executed checks

Final author receipt: `runs/run-20261022T111648Z-ca3e70dc/receipt.json`, **21/21 tests passed**, zero skips/errors/failures. Earlier 17/17 and 19/19 receipts are retained. This is author verification; independent review has not yet signed this candidate.

The suite executes actual compiler/template comparisons across 35 shapes and both supported update bind layouts (66 comparisons); enabled/disabled equality; real original/new compiler-call counts; actual observer constructor wiring; entry and byte eviction; oversized bypass; complete scope and profile-epoch isolation; immutable/invalid configuration; warm compiler-change rejection; one-compilation concurrency; no parameter retention; unchanged AST of the original source decoders and raw lifecycle classes; and original versus enabled/disabled DBAPI-double return, exception-identity, positive-read, negative-read and fresh-parameter behavior. The `-I -S` subprocess imports from only the copied package without site packages or either optional dependency. Database connection methods are patched to fail during the test suite.

Run without installing anything, using the already-existing pinned environment:

```powershell
& 'D:/CodexScratch/MoonTxnWitness-v011-20261020/orm-v3-draft-env-20261021/Scripts/python.exe' -B artifacts/v013-orm-candidate/run_tests.py
```

Each attempt creates a new owned directory and preserves its first log and source bindings. This command does not build or connect to a database. A new environment may run it after independently provisioning the declared existing dependencies; this candidate has not performed such provisioning.

Before integration: obtain independent review; keep the fixed SQL/source contract unchanged; run the current full regression and actual upstream ORM/PostgreSQL comparison using the copied package; verify native result/exception behavior under the pinned SQLAlchemy async adapter. Formal performance and fresh-install acceptance remain separate. Do not reuse the older real-database receipts as execution evidence for this migrated candidate.
