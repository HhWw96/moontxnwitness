# Changelog

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
