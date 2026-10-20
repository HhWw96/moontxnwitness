# 0.1.1 — development

- Encode the complete bounded search cache state in fixed-width numeric
  characters after CPU diagnostics. Preserve every current version, declared
  position, traversal, budget and counter; add collision and exact-limit tests.

- Batch JS JSON fragments after CPU/GC diagnostics, removing the final copy of
  all fragments. Wasm/Native retain their existing output path; complete evidence
  and analysis counters remain unchanged.
- Add an opt-in PostgreSQL 18 existing-row SQL profile that captures the actual
  server-assigned UUID with the SELECT/UPDATE statement and hides metadata from
  supported business cursor results. It remains experimental and does not cover
  arbitrary SQL, new keys, insert/delete or an existing external application.
- Reject foreign-key, rewrite-rule and inherited-table side effects during
  stable capture initialization. The experimental installer also verifies the
  exact PostgreSQL 18 NOT NULL constraints and rolls back failed setup.
- Preserve performance observations with immutable snapshots, atomic pointers
  and bounded filesystem-only retries; fault injection never retries analysis.

- Split automatic capture from the existing CLI analysis module and share the
  reduction JSON writer without omitting evidence or changing budgets/counters.
  Same-version compatibility fixtures retain byte-identical full outputs.
- Bound raw-value trees and retained capture evidence by aggregate nodes/JSON
  bytes. Exhaustion records a coverage gap while business calls keep their
  original result or exception.
- Add experimental column/sidecar provenance fixtures for ordinary tables and a
  three-batch cost study. Both candidates currently regress throughput/latency;
  they remain outside the stable adapter and do not complete v0.1.2.

- Add opt-in synchronous/asynchronous psycopg capture with generated point SQL templates, explicit custom mappings, a locked initial snapshot, raw JSONL and coverage gaps.
- Normalize capture traces in MoonBit; gaps, unknown outcomes and unfinished transactions cannot expose a complete history. Add SDK `normalizeCapture` and CLI `ingest`.
- Preserve legacy analysis and schema-2 replay, explicitly accepting the new engine header without changing its algorithm.
- Freeze a hash-verified public v0.1.0 baseline with 20 full scenarios, 15 phases and complete formal samples; retain historical measurements separately.
- Add controlled real-PostgreSQL capture checks and driver-interface tests. Independent existing-business adoption remains an uncompleted release gate.

# 0.1.0

- Post-publication main fix: select the requested release inside multi-version CI evidence; retain original assets, failed verification and successful retry.

- Repair PostgreSQL CI port-context placement; preserve its failed first run and attest the original v0.0.11 source independently from the repaired workflow commit.
- Freeze the documented v2 analysis/replay and effective-budget contract; recommend balanced entry points while preserving legacy defaults.
- Make the portable one-command demonstration exercise balanced analysis, reduction and schema-2 replay.
- Include fixed benchmark inputs, automatic pinned public v0.0.6 baseline preparation, complete performance comparisons and current verification instructions.
- Deliver actual PostgreSQL anomaly/fix evidence, an explainable project brief, AI provenance and a separate human acceptance checklist.

# 0.0.11

- Capture actual PostgreSQL 18 point-read/write transactions through two independent connections and a bounded synchronization barrier.
- Execute 20 RR write-skew rounds and 20 Serializable server-abort/fresh-retry rounds, then analyze, reduce and replay three v2 capsules.
- Ship the complete workflow in the portable runtime, preserve partial SQL observations and explicitly label missing database prerequisites as not executed.
- Add independent Linux PostgreSQL CI, frozen optional driver hashes and an owned temporary-cluster helper.

# 0.0.10

- Add opt-in 512-transaction reduction with witness/source seeds, remapped immutable writer indexes and rejected-subset caching.
- Revalidate candidate semantics, retain original input facts and prove singleton minimality only after a completed pass.
- Stream complete reduced histories/reports and add a schema-directed valid-input parser with legacy fallback.
- Differentially test parser behavior and prepared subset reports against the reference paths.
- Reject stale compiled cores before performance measurements using source/core fingerprints.
- Share immutable integer adjacency across SCC/BFS and topological ordering; generate unique RT pairs without redundant hash-set entries.
- Recheck singleton candidates on their active keys internally, restore every initial fact in delivered histories, and flatten the complete JSON output once.

# 0.0.9

- Add opt-in 12-transaction compiled completion with predecessor masks, undo trails and complete-failure caching.
- Keep legacy search and exact v1 replay counts; v2 records effective budgets and separates runtime counters from semantic evidence.
- Add balanced MoonBit/JS/CLI entry points, independent oracle comparisons and 9-12 transaction proof fixtures.

# 0.0.8

- Deduplicate complete edges with typed structural hashes, preserving collision-safe provenance.
- Use integer graph endpoints, shared BFS buffers, version-rank indexes and reusable writer/coverage data.
- Stream full dependency JSON with cached escaping; avoid temporary whitespace/token arrays in the duplicate-key guard.
- Preserve schema-v1 search traversal, evidence and all dependency edges.

# Changelog

## 0.0.6 — 2026-10-10

- Decompose dependency graphs into SCCs before shortest-cycle search; skip acyclic regions while preserving globally shortest constructed-graph witnesses.
- Add per-key coverage, explicit observed/searched version-order provenance and Chinese collection guidance.
- Keep historical cycle certificates and core semantic replay compatible.
- Add a one-command demo exporting a reduced history, model comparison and verified replay capsule.
- Validate 71 tests on JS / Wasm GC / Wasm, 10,320 independent histories and 69 CLI checks; retain honest end-to-end benchmark observations.
- Update v0.0.6 documentation, qualified ecosystem comparison and source/runtime fresh-consumer packaging.
- Publish under HhWw96/moontxnwitness with public Windows/Linux CI and package installation verification.

## 0.0.5 — 2026-10-10

- Actual two-thread, two-connection SQLite WAL race capture with aborted snapshots and fresh retries.
- Derive writer order from an audit table committed with each real write.
- Validate audit/committed-operation agreement and observed final database versions.
- Execute three independent captures and check both models and semantic replay.

## 0.0.4 — 2026-10-10

- Self-contained replay capsules bind stored history and report text with SHA-256.
- Recompute semantic results, including cycle, direct-read and exact-search verdicts.
- Compare the same history under serializable and strict-serializable models.
- Reject tampering even when an attacker updates content hashes to match forged verdicts.
- Keep v0.0.1 cycle certificates verifiable; hash checks do not authenticate source identity.

## 0.0.3 — 2026-10-10

- Transaction delta debugging with bounded checks and honest one-minimality status.
- Export reduced histories for independent analysis without inventing writer orders.
- Cover cycle, direct-read and exact-search counterexamples.
- Fix timestamp JSON export: Int64 values must be safe JSON numbers, not strings.
- Independently replay reduced generated histories and test every singleton deletion.

## 0.0.2 — 2026-10-10

- Bounded exact serial replay search for small histories with missing writer orders.
- Clearly label searched orders as possible completions, not observed facts.
- Prove exhaustive failure separately from budget exhaustion; preserve unknown outcomes.
- Add mixed atomic-writer observation example and extend independent oracle to 10,320 histories.

## 0.0.1 — 2026-10-10

First local release of MoonTxnWitness.

- MoonBit analysis of multi-key versioned point-read/write transactions.
- Explicit serializable and strict-serializable models; WR/WW/RW/RT dependencies.
- Shortest cycle witnesses in the constructed graph and feasible serial orders.
- Separate dependency-cycle certificate verification without cycle search.
- Direct read/write anomaly checks; explicit invalid and inconclusive outcomes.
- Local Node.js CLI and SDK; text, JSON, Markdown and DOT exports.
- Bounded parsing, duplicate-key rejection and non-overwriting artifact exports.
- Synthetic examples, actual sequential SQLite baseline, independent replay oracle.
- Reproducible source/portable ZIP packaging and fresh-consumer checks.

Scope: unique versioned registers with supplied or bounded-searched final-write orders. No SQL range
reads, automatic database instrumentation, complete isolation taxonomy, unbounded
performance claims, native executable, public publication or contest submission.
# 0.0.7

- Add deterministic full-report graph/search/reduction performance workloads, phase timers, cold load, P95 and independent-process peak RSS measurements.
- Freeze comparison against v0.0.6; preserve raw samples and distinguish correctness from performance-target attainment.
- Resolve public CI by exact release-tag commit instead of a historical run ID.
