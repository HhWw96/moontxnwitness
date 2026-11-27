# Point-window release verification

The [v0.7.0 public download run](https://github.com/HhWw96/moontxnwitness/actions/runs/45167011049) verifies the release digests and installs from Mooncakes. The [Windows and Linux consumer run](https://github.com/HhWw96/moontxnwitness/actions/runs/45167018539) compares the normalized history and model judgment from both consumers.

Starting with v0.7.1, the version's [release page](https://github.com/HhWw96/moontxnwitness/releases) lists the portable and point-gate ZIPs in its checksum manifest. The release workflow binds both archives to a successful source build. All six point-window fixtures run through both extracted gates. The public consumer uploads the resulting verdict comparison, archive sizes, transfer times and cold-start timings.

The [database campaign](point-window-replay.md) separately exercises PostgreSQL write skew, reduction, the ordered Serializable control and an observed rollback and retry. The [capture cost protocol](configured-window-performance.md) compares the original workload, source-only configuration and complete durable capture.

## Reproduce point and predicate evidence

Start with the [v0.7.6 portable archive and checksums](https://github.com/HhWw96/moontxnwitness/releases/tag/v0.7.6). From a new extraction directory, run:

```sh
node examples/point-window-replay.mjs --html point-witness.html
node examples/predicate-window-replay.mjs --output predicate-witness.json
node scripts/point-window-ci-test.mjs
node scripts/verify-point-window-moon-consumer.mjs --runtime dist --module-version 0.7.6 --output new-moon-consumer
```

The two replays work offline. The final command installs the public package
from Mooncakes and compares the point-window verdict against JavaScript. For
a database-backed reproduction, the [reservation guide](configured-predicate-window.md)
runs five independent rounds against a disposable PostgreSQL 18.6 database.
The [fixed Elle comparison](elle-model-matrix.md) covers register and append-list
histories in the common scope. Predicate evidence uses its own source contract,
and its replay is checked against the original PostgreSQL input.

The [v0.7.4 capture-cost results](https://github.com/HhWw96/moontxnwitness/releases/tag/v0.7.4)
compare boundary paging with v0.7.0 across four workloads. The profiling command,
limits and evidence checks are available in the [capture cost protocol](configured-window-performance.md#paired-comparison-for-larger-boundary-pages).

When reproducing a result, keep the tested version, its portable digest,
operating system and command output together. These identify which input and
runtime produced the verdict.
