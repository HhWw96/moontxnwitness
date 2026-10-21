# Controlled MLflow cross-batch deadlock rehearsal

Experimental execution-fault evidence for [MLflow PR #24941](https://github.com/mlflow/mlflow/pull/24941).
This executes the unchanged affected `_update_latest_metrics_if_necessary`
method and `SqlLatestMetric` class from before commit
`c2dcdb96c62c75f35af3f28b5d493c0cf139a856` and repair commit
`40c146a23518813e8488e55fc9752e08c3a8bad5` on an actual PostgreSQL server.
The immutable upstream files, their licenses and byte/AST bindings are retained.
The runs table, managed session wiring and scheduler are controlled fixtures;
this does not start the full MLflow server or execute its HTTP `log_batch` API.

## Run

Use a new isolated Python 3.12 environment and PostgreSQL 18. Install optional
test dependencies with their frozen hashes:

```text
python -m pip install --require-hashes -r experiments/faults/mlflow/requirements.txt
python -B experiments/faults/mlflow/run_postgres.py --connection-file PRIVATE_CONNECTION.json --output NEW_DIRECTORY
```

The connection file contains the normal psycopg connection fields. Alternatively
set `MTW_PG_CONNECTION_FILE` or `MTW_PG_DSN`; connection secrets are not printed.
Missing drivers or connection configuration are `not-executed`, exit code 3.
Use a dedicated disposable database: this creates new uniquely named schemas
and retains them. It never resets or deletes an existing schema or directory.

The existing owned-cluster helper can run this fixture using the same environment:

```text
python -B scripts/capture-local-postgres.py --suite mlflow-fault --work-root NEW_CLUSTER_PARENT
```

## What the comparison establishes

Two workers each supply 1,000 metric keys. The original 500-key batch size stays
unchanged. Their first unsorted batches are disjoint and their second batches
request the opposite locks. Both reach the first locking statement together.
The controller releases successful first batches only after observing both
completed, or one completed and the other actually waiting on a database lock.
This allows the repaired global sort to serialize naturally instead of placing
a barrier after a lock that the second worker cannot acquire.

The before case must produce one native `40P01` victim and one committed
transaction; the repaired case must commit both and retain the correct latest
step for all 1,000 keys. Native SQL/parameters, actual command rowcounts, errors,
final rows and the v3 raw observation journal are saved. The SQL observation
stream is bounded and synchronized before success. Actual server logs are
retained by the owned cluster and CI.

`40P01` is an execution deadlock. It is not G2 or an isolation-level violation.
The raw SQL is deliberately unmapped and the initial relation snapshot is not
proved, so `analyzeV3` remains `inconclusive`. The separate MoonBit
`inspectExecutionFailuresV3` / CLI `failures-v3` describes recorded errors without
claiming model violation or database authenticity. Zero observed faults does
not certify absence of every failure.

Each case retains nine actual SQL executions in the fixture SQL log and eight
statement observations in generic v3 capture. The original ORM update uses
`executemany`, which that capture adapter does not yet support. The separate
fixture log does not remove this coverage gap. `failures-v3` exit code 0 means
only that the diagnostic input is valid, even when a recorded deadlock exists.

This first component comparison does not complete the v0.1.7 gate. Real-fault
predicate reduction, registered concurrent seeds, retry-path coverage and
independent clean-environment acceptance remain required. No synthetic
deadlock exception is injected and no input history is handwritten.
