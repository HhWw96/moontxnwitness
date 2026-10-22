# First actual18 parser experiment: performance gate FAILED

This evidence concerns experimental source599906/core5b63, compared with published
actual17 source3359/cored1e4. It records the first authorized run, not a successful
retry. Original correctness=true and protocolCompleted=true; control=false and
performanceImprovementClaim=false. The candidate was rejected for default use.
A future stable18 rollback is a different build. Neither the old101 correctness
review nor this measurement accepts that future source/runtime.

Python3.11+ standard library is sufficient to read and recompute existing data:

```
python -B recompute.py --manifest-sha256 EXTERNAL_PUBLIC_MANIFEST_SHA256
```

This command only reads files, verifies hashes and recalculates samples/thresholds.
It launches no process, imports no SDK, compiles nothing and measures no duration.
The historical authorization is evidence of the old run and is not permission to
launch another run. Original38 protocol files are preserved for inspection;
do not execute their protocol launcher or worker as part of this data review.

The whole14-row original receipt,84 warm/84 cold/28 equivalence worker and parent
JSON records,196 jobs and original stdout/stderr logs are included. The84 warm
workers provide2520 original timed samples (90 per engine/input/phase). All7 fixed
inputs and38 frozen protocol files plus manifest are retained. Each equivalence
input/phase/engine has one complete native and projected output; there are no
invented or duplicated hot-output records. Self-contained17/18 cores, matching
build manifests and both exact source sets (17:81 and rejected18:82 files) are
included. This is not a full Git/toolchain/product package or a new build.

origin-to-public.json lists every copied original SHA, public SHA, byte size and
path-string substitution. Only declared private ROOT/home prefixes were replaced.
All text outside JSON string tokens, including every sample numeric literal,
budget, result flag and counter, stays exact. Nonpath string tokens and complete
analysis/typed outputs remain unchanged. Original private files and raw authority
records are preserved outside this closure. The original private receipt SHA is
d0dcafc4e9589c18adb4bb81de19d01a899dd1194eba4a4e2630bd1dff58289c.
Mapped authority/binding/receipt files are derivatives, not original authority
bytes; their original and public hashes are explicitly distinguished.

Original control rule: current minus baseline <=max(10% baseline,2ms), applied to
warm pooled median/P95 and3-process cold median for the3 fixed control inputs.
Two of18 control metrics fail:

* dense parse cold process median257.4113 ->283.3188ms; delta25.9075ms,
  allowance25.74113ms, excess0.16637ms. The narrow excess remains a failure.
* dense full pooled-P95 24.6684 ->27.9992ms; delta3.3308ms,
  allowance2.46684ms, excess0.86396ms.

Custom-ASCII full median11.4021 ->13.69255ms (+20.09%) is an additional
parser-heavy observation, not an invented post-run control rule. Its paired batch
medians all increase (+9.98%,+3.76%,+22.19%) while each batch P95 decreases.
Dense full batch P95 changes are mixed; the largest tail increase occurs in the
third batch. All raw samples remain available; no batch is removed.

Some parse-only warm medians improve (known/custom ASCII about10.8%), while full
analysis and cold process outcomes differ. Full mode times the actual complete
analysis/encoding call; output validation occurs between samples, outside that
timer. Cold external wall time includes process start, import, first call,
validation/serialization and exit. It is not isolated parser latency. RSS is the
whole worker lifetime, including input/hash/import/validation/serialization, not
parser allocation-only, and had no registered pass threshold.

There are3 independent process batches; the90 within-process calls are not90
independent machines or trials. AB/BA/AB and original file times are consistent;
file times do not cryptographically prove execution order. Exclusivity and agent
shutdown were root attestations, not independently observed OS isolation.
The data supports the original failed gate and workload-specific observations;
it does not establish a universal speedup, code-level cause or a new release.

The read-only auditor initially compared a worker JSON with a parent-enriched
rawWarm row and raised a checker AssertionError. That checker error and correction
are retained separately; it did not alter measurements or the original failure.
No performance rerun, database, network, compilation or SDK execution occurred
while preparing this closure.
