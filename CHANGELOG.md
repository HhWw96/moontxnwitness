# Changelog

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

Scope: unique versioned registers with supplied final-write orders. No SQL range
reads, automatic database instrumentation, complete isolation taxonomy, unbounded
performance claims, native executable, public publication or contest submission.
