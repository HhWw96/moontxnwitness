# Dependencies, references and development provenance

MoonTxnWitness is licensed under Apache-2.0. The license text is the standard
Apache license, not transaction-analysis code copied from another project.

## Runtime and dependencies

- [moonbitlang/core](https://github.com/moonbitlang/core): MoonBit standard library,
  Apache-2.0. `core/json` is used for JSON parsing and serialization; runtime
  portions are included in compiled JavaScript. `dist/THIRD_PARTY_NOTICES.txt`
  includes attribution and license text.
- Node.js provides local command-line I/O; it is a user-installed prerequisite,
  not redistributed in the portable ZIP.
- Python standard-library `sqlite3` supplies the actual SQLite baseline and
  `zipfile` creates archives. Python/SQLite binaries are not redistributed.
- No external npm packages or Mooncakes packages are required.

## Conceptual references

- [Jepsen Elle](https://github.com/jepsen-io/elle): primary reference for
  transaction-history dependency inference, WR/WW/RW terminology and explanation
  of the difficulties of inferring version order. This project does not embed,
  call or port Elle code. It implements a smaller, explicitly versioned register
  model with supplied final-write orders or bounded exact serial completion for
  small histories whose only uncertainty is missing order.
- [Adya, Liskov and O'Neil, Generalized Isolation Level Definitions](https://pmg.csail.mit.edu/papers/icde00.pdf):
  conceptual reference for dependency graph terminology. This release does not
  claim to implement every anomaly/isolation class in that work.

## AI assistance and evidence

The implementation, documentation and tests were created with AI
assistance. The production algorithms are in MoonBit. The test oracle replays
every possible serial permutation of small whole transactions and does not use
the production dependency inference rules. Certificate verification shares
inference rules and separately checks a supplied cycle without searching for one.

Synthetic anomalous histories are labeled as such. SQLite samples include an
actually executed sequential baseline and a two-thread/two-connection WAL race
with aborted attempts and fresh retries. They do not reproduce a SQLite
vulnerability or certify all database executions. See the official
[SQLite isolation](https://www.sqlite.org/isolation.html) and
[WAL](https://www.sqlite.org/wal.html) documentation for the underlying behavior.
Public release verification is recorded separately in verification/publication.json.
No claim of a prize or organizer acceptance is made for v0.0.6.
