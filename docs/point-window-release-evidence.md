# Point-window release verification

The [v0.7.0 public download run](https://github.com/HhWw96/moontxnwitness/actions/runs/45167011049) verifies the release digests and installs from Mooncakes. The [Windows and Linux consumer run](https://github.com/HhWw96/moontxnwitness/actions/runs/45167018539) compares the normalized history and model judgment from both consumers.

Starting with v0.7.1, the version's [release page](https://github.com/HhWw96/moontxnwitness/releases) lists the portable and point-gate ZIPs in its checksum manifest. The release workflow binds both archives to a successful source build. All six point-window fixtures run through both extracted gates. The public consumer uploads the resulting verdict comparison, archive sizes, transfer times and cold-start timings.

The [database campaign](point-window-replay.md) separately exercises PostgreSQL write skew, reduction, the ordered Serializable control and an observed rollback and retry. The [capture cost protocol](configured-window-performance.md) compares the original workload, source-only configuration and complete durable capture.
