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
- The JS backend uses small host primitives to join string fragments and to
  materialize an already encoded search key from at most 257 exact UTF-16 units.
  Search state, cache membership, traversal and budget decisions remain in MoonBit;
  other targets use the equivalent MoonBit string builder.
- Python standard-library `sqlite3` supplies the actual SQLite baseline and
  `zipfile` creates archives. Python/SQLite binaries are not redistributed.
- No external npm packages or Mooncakes packages are required by the analyzer.
- Optional PostgreSQL collection uses [psycopg 3.3.6](https://pypi.org/project/psycopg/3.3.6/), LGPL-3.0-only, installed separately using frozen PyPI hashes. Its wheels and PostgreSQL binaries are not redistributed. Driver dependencies keep their upstream licenses.
- The experimental existing-lease integration vendors unmodified
  [Actticus/dislock](https://github.com/Actticus/dislock/tree/f9946f07159054433d9071c3805e41223cb47856)
  at commit `f9946f07159054433d9071c3805e41223cb47856`, under its MIT license.
  The original license, selected original files, source archive and byte hashes
  remain in `experiments/business/dislock/upstream/`. The fixture calls the
  existing business functions; it does not turn this third-party component into
  MoonBit-authored code or imply upstream adoption of MoonTxnWitness.

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

## Experimental MLflow component

The experimental MLflow execution-fault rehearsal bundles gzip-compressed,
unmodified source files from MLflow commits
`c2dcdb96c62c75f35af3f28b5d493c0cf139a856` and
`40c146a23518813e8488e55fc9752e08c3a8bad5` under the Apache-2.0 license.
Each copy retains the upstream LICENSE.txt and SHA-256 provenance in
`experiments/faults/mlflow/upstream/`. Only the original affected method and
SqlLatestMetric class are compiled; the runs table/session scheduler are
controlled fixtures. This is not a complete MLflow server integration, an
isolation-level proof or a port of MLflow into MoonBit.

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
PostgreSQL controlled fixtures also retain real SQL results, server-reported rollbacks and fresh retries; expectations follow the [PostgreSQL 18 isolation documentation](https://www.postgresql.org/docs/18/transaction-iso.html). No claim of a prize or organizer acceptance is made.
