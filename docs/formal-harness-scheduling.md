# Formal capture-cost harness corrections

This is a follow-up to the frozen v0.2.3 tooling. The original protocol remains
byte-identical (SHA-256 `37de5f6e79df8a4089439f6ac5df27cb748f6daaaabece4ba339285763a90418`).
No original measurement, SQL failure, expected test result or release package is
rewritten. These changes do not establish a performance gain.

A complete three-batch timing result can have zero committed C throughput when
all attempts fail. Such a result keeps its zero ratio and failed-attempt counts
and remains ineligible. Missing/zero A baselines, unavailable P95 samples and
nonfinite or invalid numbers yield unavailable ratios and ineligible results,
without aborting the aggregate receipt. Ordinary positive comparisons retain the
same ratios and geometric means. All matched A/B/C cells must qualify.

Worker native connections and configured wrappers now reach a bounded readiness
barrier before the full 15-second warmup deadline starts. A connection or wrapper
failure aborts the barrier, retains its original worker failure class in the
failed receipt and closes any acquired raw connection. No transaction issue
window begins after a broken barrier. The existing 30-second readiness bound,
15/60/30-second formal schedule, seed, workloads, budgets and ABC/BCA/CAB rotations
remain explicit. The 30-second transaction drain is separate from the durable
tail already included in throughput.

The all-attempt P95 is the latency until a transaction API call completes,
including its observed error/rollback and collector enqueue/backpressure cost.
It is not a per-transaction durable-acknowledgement P95. C's end-of-window
source/event/lifecycle close and synchronization tail remains included in the
end-to-end throughput denominator and is reported separately. Lifecycle retains
buffered append with close flush/fsync; it is not described as a periodic
4-MiB group-sync queue.

The workflow has an independent 180-minute measurement-step deadline within a
270-minute job, bounded setup steps, 10 minutes for cleanup/receipt and 30 minutes
for artifact upload. The maximum sum of declared step deadlines is 247 minutes,
leaving job headroom. Timeout or incomplete execution cannot qualify performance;
raw partial logs are still retained by the subsequent always-run steps. This is
failure-budget isolation, not a guarantee of runner storage or physical-host
exclusivity. Actual environment and completion remain recorded per run.

The original strict SQL-failure rule remains: ordinary duplicate INSERT or any
registered SQLSTATE failure, including warmup, disqualifies target evidence.
A green workflow does not imply C/A targets passed. The original zero-throughput
counterexample, pre-fix test failures and the first implementation syntax error
are retained under `verification/formal-harness-fix`.

Validation uses synthetic metric records and fake driver connections plus the
existing local file/queue/protocol unit tests. No formal measurement, real
database, compiler or public package verification was performed for this fix.

The first runner-local path step uses the shell's `$RUNNER_TEMP` and writes the
subsequent-step values to `$GITHUB_ENV`. Job-level env expressions only use
contexts allowed by the [official GitHub context availability table](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts).
The original invalid `runner.temp` job-env configuration and failing local check are retained; the matching
path-only correction is a separate preceding commit, already applied to v0.2.3.
The later changes here remain isolated follow-up tooling.
