# Full capture cost: CRUD conflict-noop v2

This is a new workload protocol, `full-capture-cost/crud-conflict-noop-v2`, with generator `python-random-point-capture-cost/insert-conflict-noop-v2`. It is separate from both the original v1 workload and the optional `full-capture-cost-capacity/v2` storage-budget profile. The original runner and protocol remain unchanged. Prior failed measurements remain evidence of those original SQL semantics, not measurements of this new protocol.

The v1 fixture prefilled all 4,096 keys, then selected a random ordinary INSERT. Inserting an already present primary key produced SQLSTATE 23505. The previous recorded column/sidecar runs retained 135,075/70,286 measured and 43,234/24,221 warmup 23505 failures; see [the retained report](../../docs/performance-v0.3.0-capture.md), [column run 40383472300](https://github.com/HhWw96/moontxnwitness/actions/runs/40383472300) and [sidecar run 40383476670](https://github.com/HhWw96/moontxnwitness/actions/runs/40383476670) at source `329df5cf1a2c58f03dd9e913e0621a822c6411ef`. Those failures disqualify target comparisons and are not discarded or relabeled as successful inserts.

## Changed SQL and unchanged controls

Only CRUD's insert-if-absent action changes its business SQL:

```sql
INSERT INTO configured_items(id,value) VALUES (%s,0)
ON CONFLICT (id) DO NOTHING;
```

The runner executes one statement once and records the actual delivered DBAPI rowcount, exactly 0 or 1. Zero is a successful no-op write result, not a SELECT, negative read, proof of a unique historical absent version, or hidden retry. Unknown/failed write results are null. Read-only actions also have no write result. A zero/one delivered result followed by a failed COMMIT remains a failed transaction; observed statement effects and committed counts are reported separately.

The original RNG and its consumption, seeds, business key/negative-key domains and action choices are identical across A/B/C. The write helper has no mode parameter. The original four workloads remain 4,096 keys/1 connection, 4,096/4, 32/8 with 90% of updates on four keys, and CRUD 4,096/4. The complete plan still has 36 cells, the ABC/BCA/CAB rotations, 15-second warmup, 60-second issue window and at most 30-second drain. Existing provenance-specific observations and writes remain the explicit additional B/C work; no claim is made that those overhead statements are present in A.

The plan binds explicit business SQL templates and their SHA-256. Worker configuration must name the new generator/protocol and SQL hash. Each measured attempt retains its negative key, action, actual write result, SQLSTATE, commit status and latency. Warmup keeps actual write-result counters alongside the existing attempts/errors/SQLSTATE counters. Raw lifecycle, source and event retention remain the existing protocol's responsibility. The new runner's source and all loaded capture helpers are bound before and after every cell.

No retry was added. Any measured/warmup SQL failure, missing/incomplete evidence, storage exhaustion or protocol failure still makes the cell ineligible. Target ratios remain full C/A throughput ≥0.90 and P95 ≤1.15; B/A cannot substitute. Throughput still includes drain and durable-tail time. No source-fact, capture-window or full model-analysis completeness is promoted by this cost fixture.

## Execution

Generate the new complete plan without connecting to PostgreSQL:

```text
python -B experiments/provenance/full_capture_cost_v2.py --profile column --output NEW_V2_PLAN --plan-only --archive-cells
```

After preregistration, on a separately owned PostgreSQL 18 cluster with explicit exclusive task assertions:

```text
python -B experiments/provenance/full_capture_cost_v2.py --profile column --output NEW_V2_RUN --exclusive-host --exclusive-cluster --archive-cells
```

The existing registered `full-capture-cost.yml` workflow adds an explicit `cost_protocol` choice. Its default `legacy-v1` still invokes the original runner. Select `crud-conflict-noop-v2` and an exact source commit to execute this new runner. Source buffering and the finite storage profile remain separate explicit inputs; their default/limits are unchanged. Environment/build/setup, offline checks, Docker download and archiving occur outside the timed cell window. A GitHub-hosted job is an isolated job environment; physical host tenancy is not measured.

Before the existing persistence tests, a small preparer restores only their 2,490-byte frozen legacy workflow fixture through the existing pinned public input cache. It verifies the input-index identity, provider archive hash if opened, and final member hash. Existing or cached poison is rejected rather than overwritten. A fresh CI job may need the pinned source archive during setup; it does not materialize the full test corpus or compatibility runtimes. Local validation can reuse an already verified blob with `--offline`; no download is needed. Preparation records are retained outside timed cells.

Offline tests call the actual new SQL executor with a stateful fake DBAPI. They reproduce the old duplicate-key error, check actual zero/one/null distinctions, mode/seed equality, four-connection conflicts, no synthetic SELECT or retry, unchanged timing/targets and source binding. They are not PostgreSQL, persistence-cost or performance results. No new formal result is claimed by this protocol preparation.

Actual local preparation passed 27 new checks and the complete existing 157-test persistence/cost suite (one symlink test was explicitly skipped because this Windows host cannot create symlinks). Both full 36-cell column/sidecar plans were generated without a database; YAML, all three workflow Python blocks and new Python sources parsed successfully. The first new-test fixture omitted the positive throughput/P95 required by existing qualification rules; the original failing log and fixture are retained, and the fixture was completed without weakening those rules. A first legacy workflow-context check also retained its missing external fixture error; the exact 2,490-byte pinned fixture was then restored offline and the unchanged legacy suite passed. These are setup and functional results, not measured C/A ratios.
