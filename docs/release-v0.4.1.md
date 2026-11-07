# MoonTxnWitness v0.4.1

- Analyze actual PostgreSQL point reads and updates using sealed start/end snapshots, original client observations and confirmed commits.
- Verify complete newly visible source effects, predecessor versions and client transaction identity independently in MoonBit.
- Share the compiled core across the default SDK's configured SQL, fetch, source and session calls.
- Reduce repeated installation hashing and SHA-256 schedule allocation while preserving original evidence and replay rules.
- Build a lightweight portable SDK/CLI package with clean-directory example verification.

Install the core with `moon add HhWw96/moontxnwitness@0.4.1`.
For the SDK and CLI use the GitHub portable package with Node.js 20 or later.

Point-window analysis supports an owned PostgreSQL 18 database, synchronous
psycopg 3.3.6, one configured table, positive primary-key reads and one non-key
update per transaction/key after reading its predecessor. Limits are 32
transactions, 128 business statements and independently supplied verification
budgets. Incomplete results, unknown commit outcomes and missing source facts
remain visible in the report.

See [the executable workflow](configured-session-v4.md#analyze-a-captured-point-window),
[the support matrix](stable-scope.md) and [lightweight packaging](portable-lite.md).
