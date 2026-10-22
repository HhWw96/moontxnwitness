# Actual18 independent semantic review preparation

Status: preparation only. No actual18 SDK/core import, product test, build,
database, network download or performance measurement has run here.

Prerequisites: Python 3.11+ and Node 24; standard libraries only. Root must supply
an actual18 root-freeze JSON and its SHA256, with executeReview=true and
actual-0.1.8-frozen-by-root. The included template is deliberately disabled.
The same JSON must supply frozen17 source/runtime locations. Their 87 original
file bindings are fixed in baseline17-binding.json (source3359/core d1e419).
Actual18 source/runtime bindings remain externally supplied and unknown.

From the review directory, after root authorization:

```
python run-review.py --freeze ROOT_FREEZE_JSON --freeze-sha256 ROOT_SUPPLIED_SHA256 --preparation-sha256 PREPARATION_MANIFEST_SHA256
```

All prepared files, complete MoonBit compilation source sets, package versions,
build metadata, runtime files and declared local import dependencies are checked
before either actual engine is copied or imported. Source/runtime preservation is
checked afterward. New run directories preserve the first failure, raw outputs,
child logs and private preflight. No automatic product retry changes expectations.
Source/runtime roots can be relative to the working directory for public replay.
No full source mirror, toolchain, binaries other than the frozen parser oracle,
or third-party service dependencies are included in this preparation.

The original81 execution behavior assertions are copied byte for byte from the
actual17 preparation. The previous85-check worker is retained as provenance.
Its new native engine-header assertions explicitly expect18; the original
business values15/16 and all original diagnostics/budgets/risks stay fixed.
An added business17/18 input is separate from those old inputs.

Original2542 parser inputs and seed/order are regenerated exactly. A product-free
preparation check verified every input SHA and JS code-unit length against the
old sealed receipt. At authorized execution the frozen15 legacy interpreter must
reproduce every original complete typed/error output hash, flags and size first.
Actual17 and18 then compare every public History/Transaction/Operation field,
Map logical contents and exact Int64/None values. Private randomized Map buckets
are excluded as in the original frozen checker. Invalid reports allow only the
explicit schema1 invalid-report root /version string span to differ.

Original117 inputs, options, names and order were likewise checked against the
unchanged old receipt. The frozen15 core must reproduce all117 original raw
output SHA/byte expectations. Native17 and18 complete analyze/shrink output
strings are retained and compared. Only known engine metadata spans are projected:

* analyze_options_json: root /version, after tool=MoonTxnWitness, schemaVersion=2,
  algorithm=bounded-register-v2.1 and native core.version/header version checks.
* shrink_options_json: /version and /report/version; root tool/schema2 and nested
  report tool/schema2/algorithm are checked first. The shrink root has no invented
  algorithm field. Every other original character, including reducedHistory
  business versions, budgets, counts, provenance and whitespace, must match.
* v3 register reports used by the132 derived checks: /version and, only when an
  existing schema2 bounded-register evidence object is present, /evidence/version.

The scanner rejects duplicate decoded JSON keys at every depth and noncanonical
engine-header key/value spans. It does not reserialize, sort, replace substrings
or erase arbitrary version fields. Helpers have a separate product-free selfcheck.

Two independently generated actual17 before/fixed execution capsules and their
original85-review receipt are immutable inputs. Native18 must replay their exact
bytes and reproduce the complete old replay results, keeping recordedEngine17.
Unknown/future/wildcard/unsupported old engines, wrong format/algorithm, resealed
budgets/diagnostics/SQLSTATE, duplicate and unknown fields remain rejected.
A real archived native17 register model capsule and four older v1/v2/v3 capsule
formats are also preserved. An additional287 frozen capsules cover v2 register3,
capture4, append-list120 and relation160. Their fixed original statuses and whole
replay results are compared against17; only the explicit currentEngine header of
v2 replay transport is allowed to advance17 to18 after exact checks.

The original132 derived histories and frozen expectations are retained. The old
independent verifier and five substantive coverage/tamper/budget/source-mapping
blocks remain verbatim. The full original16 suite and old Elle/example execution
are not claimed here; author/root runs the full product suite and regression
input comparisons separately. No new Elle execution, database run, full MLflow
business repair, every-isolation-level classification or failure-absence proof
is inferred. Both real historical MLflow captures stay inconclusive;40P01 is an
observed deadlock and never renamed G2. Valid capsules mean observations were
recomputed, without source authenticity or fault-absence certification.

packages=[] means packagesExecuted=false and packageReviewPending=true. Formal
source/portable package validation and anonymous download acceptance remain a
separate stage. This preparation does not create a package/acceptance dependency
cycle and does not sign any download or release outcome.

Private preparation journal and later raw absolute-path preflight stay outside
the selected public preparation. Public replay requires only relative roots and
bound files; private records are represented by hashes. Root LICENSE, dependency
notices and provenance remain included. No private private home-directory path is needed.

One preparation-only Python syntax failure (duplicate raw-prefix in generated
regex literals) and its original guard bytes are retained under
provenance/preparation-first-failure. It was corrected before any product import;
no product code, frozen input or original expectation changed.

The existing performance-v3-final preparation is unchanged and unexecuted. This
semantic entry contains no timing, memory benchmark or speedup conclusion.
