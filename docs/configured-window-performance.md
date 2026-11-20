# Configured-window SDK baseline

## Complete PostgreSQL capture cost

Run on a separately owned PostgreSQL 18.6 test database. The selected DSN
environment variable is read by the collector. Use a new output directory.

```sh
python -B scripts/configured-window-cost-pilot.py --dsn-env MTW_TEST_DSN --owned-database --formal --exclusive-host --output NEW_COST_RUN
node scripts/configured-window-cost-pilot-verify.mjs --core dist/sql-projection-v2-core.mjs --receipt NEW_COST_RUN/receipt.json --output NEW_COST_RUN/verified.json
```

The formal protocol rotates ABC, BCA and CAB across three fresh batches per
workload. Each phase warms up on five windows and measures thirty windows of
24 transactions. Workloads use 24 keys with one connection, 1,024 keys with
four connections, and 32 keys with eight connections. In the last workload,
22 of 24 writes use four hot keys. Workers update and read their own result
within each transaction, with identical business values and final state across
all three phases. Each matched set starts from freshly initialized tables.

A runs the business operations, B enables the source installation, and C
also opens and durably seals the configured point window. Setup and subsequent
analysis are outside the measured window. Receipts retain window opening,
business and seal time, per-transaction samples, output size, and collector
peak process RSS for the run. The verifier replays the complete C evidence and
recomputes the throughput and P95 ratios. Use `--formal-smoke` instead of
`--formal --exclusive-host` for a single rehearsal per phase and order.

To compare two verified formal runs on the same host, use the same harness
and MoonBit verifier for both versions. Give each run a new directory and
retain its `receipt.json` and `verified.json`, then run:

```sh
node scripts/compare-configured-window-cost.mjs --baseline BASELINE_RUN --candidate CANDIDATE_RUN --output comparison.json
```

## Historical SDK baseline

The baseline uses v0.4.1 source commit
`b7008ce2eb404bd85eedc3bd5e0b5b9bfdadcb48`, MoonBit
`0.10.16+b1a0e846e` and Node.js `24.13.0` on Windows. It measures complete
`verifyConfiguredWriterWindowV4` and `analyzeConfiguredPointWindowV4` calls
with original input texts already in memory. Filesystem input loading is outside
the timed call; parsing, source verification and complete report production are
inside it. No output fields or source evidence are removed.

| Input | Median ms | P95 ms | Peak RSS MiB | Output bytes |
| --- | ---: | ---: | ---: | ---: |
| Complete writer delta | 207.191 | 231.059 | 123.46 | 1,988 |
| Incomplete writer delta | 207.864 | 225.625 | 123.30 | 2,563 |
| Repeatable Read write skew | 109.274 | 119.321 | 100.08 | 804,320 |
| Ordered Serializable | 92.514 | 109.686 | 87.80 | 558,834 |

Each timing case has five warmups and thirty samples in each of three fresh
processes. RSS comes from three additional fresh single-call processes, rather
than the warmed timing loop. SDK cold import and first-call times are retained
separately. These memory results use this protocol and should be compared with
future measurements using the same protocol. This is a baseline, not an
optimization comparison or an A/B/C database capture-cost result.

The separate `MoonTxnWitness-v0.4.1-configured-baseline.zip` attachment contains
the original controlled observations, raw samples, runtime/input digests and
reproduction scripts. It was extracted beside an unmodified lightweight runtime
in a new directory; all static runtime digests and a complete call's output
digest matched. The reproduction plan uses portable paths; the measured plan
digest remains recorded independently.

From the extracted baseline directory, with the matching lightweight runtime
beside it:

```text
node --experimental-vm-modules scripts/bench/configured-window-baseline.mjs plan.json new-measurement
```

The VM flag is used only by setup to inventory static dependencies. Timed and
memory child processes import the ordinary SDK. A different runtime, altered
input, changed output, unexpected status or an existing output directory stops
the run. Preserve the first failure before changing the implementation.
