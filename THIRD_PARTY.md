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
  of the difficulties of inferring version order. The analyzer implements its
  own MoonBit algorithms. A separate experimental CI comparison calls the fixed
  upstream checkers; they are not linked into the compiled MoonBit runtime.
  The comparison is limited to its declared common raw-history range.
- [Adya, Liskov and O'Neil, Generalized Isolation Level Definitions](https://pmg.csail.mit.edu/papers/icde00.pdf):
  conceptual reference for dependency graph terminology. This release does not
  claim to implement every anomaly/isolation class in that work.

## Fixed upstream comparison references

`verification/experimental-candidates/elle-smoke*/primary-references/` contains
unmodified selected Elle sources, tests, project metadata and their original
complete LICENSE at commit `4e359e597c52938b0afebb8bc42273914d68a424`.
The upstream project declares `EPL-2.0 OR GPL-2.0-or-later WITH
Classpath-exception-2.0`; these files retain their upstream terms and attribution.
The frozen Leiningen 2.11.2 launcher retains its separate
`LEININGEN-COPYING` in the revised candidate. Root Apache licensing does not
relicense these reference files. Java/Lein/Maven dependencies are resolved in an
isolated test environment, recorded by actual hashes and not bundled as analyzer
runtime dependencies. Original setup failures and exact resolved dependency
records remain separate from successful checker results.

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

## Development assistance

AI assisted the implementation, documentation and tests.

## Verification

The production algorithms are in MoonBit. The test oracle replays
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

## Fixed cycle-rule reference materials

The unmodified Elle `txn.clj`, `project.clj` and `LICENSE` in `fixtures/register-cycle-v3/elle-reference/primary-references/` are pinned to commit `4e359e597c52938b0afebb8bc42273914d68a424`. Their original source, notices and license text are retained byte-for-byte; `reference-attribution.json` binds their source hashes. The upstream project declares `EPL-2.0 OR GPL-2.0-or-later WITH Classpath-exception-2.0`; the retained LICENSE is the original EPL-2.0 text. These reference materials keep their upstream terms and are not relabeled as this project's Apache-2.0 code. The SDK independently implements the selected ww/wr/item-rw mathematical conditions; it does not copy the Clojure implementation or load an Elle checker runtime.

## Recorded execution diagnostic fixtures

The two capture/receipt pairs in `fixtures/execution-v3/mlflow/` are unmodified recorded component-fixture observations from the existing MLflow rehearsal. `source-origin.json` binds their original paths and exact bytes, the fixed upstream commits and the historical unbound capture.py dependency. The original MLflow Apache-2.0 LICENSE.txt is retained for each fixed revision; no upstream application code is copied into these fixture files. Offline diagnostic replay does not execute MLflow or authenticate the original database.


## SQLGlot 30.26.0 (optional Python adapter)

SQLGlot is an optional dependency for structural PostgreSQL SQL recognition. Its implementation is installed separately and is not copied into the source tree or required by the MoonBit core. The exact pure wheel is pinned by SHA-256 in `integrations/python/requirements-configured-sql.txt`.

The actual wheel METADATA declares `License-Expression: MIT`; its LICENSE is Copyright (c) 2026 Toby Mao. The complete original license is retained at [SQLGlot MIT license](integrations/python/licenses/SQLGlot-30.26.0-MIT.txt). Upstream: https://github.com/tobymao/sqlglot ; release: https://pypi.org/project/sqlglot/30.26.0/ .
