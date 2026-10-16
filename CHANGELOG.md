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

