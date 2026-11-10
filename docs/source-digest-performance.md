# Source digest acceleration

The JavaScript build can use Node's built-in SHA-256 primitive for source
digests. Verification, JSON handling, source attribution, budgets and reports
remain in MoonBit. The original MoonBit SHA implementation is retained for
Wasm, Native, browsers, hosts without `process.getBuiltinModule`, malformed
UTF-16, or an unavailable native primitive. No optional package is required.

This changes the digest implementation, not its bytes or evidence semantics.
The original digest implementation's file and line layout are preserved for
compatibility with previously recorded diagnostics. Standard UTF-8 vectors,
combining characters, supplementary code points, embedded NUL/CRLF and SHA
padding boundaries are tested independently of configured-window fixtures.

## Complete-call comparison

Baseline: public v0.4.1, commit
`b7008ce2eb404bd85eedc3bd5e0b5b9bfdadcb48`.
Candidate: `02cf31abdd6b1bdaa98dacd5edaf98832aa107ed`.
Both use MoonBit `0.10.16+b1a0e846e`, Node `24.13.0`, and the same Windows
machine. The candidate replaces all six current compiled components in the
public lightweight runtime; wrappers and frozen compatibility components are
unchanged. The staging receipt binds the source fingerprint and every replaced
component. It is a source-built candidate, not a claim that a new package was
published.

| Complete SDK call | Baseline median ms | Candidate median ms | Speedup | Baseline P95 ms | Candidate P95 ms | Candidate / baseline peak RSS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Complete writer delta | 202.576 | 120.650 | 1.679x | 220.161 | 140.415 | 0.895 |
| Incomplete writer delta | 204.563 | 119.666 | 1.709x | 231.198 | 138.648 | 0.892 |
| RR write skew | 108.500 | 86.622 | 1.253x | 121.021 | 125.220 | 1.083 |
| Ordered Serializable | 94.817 | 69.115 | 1.372x | 112.797 | 98.288 | 0.988 |

The geometric mean speedup is **1.490x** for these four complete calls.
The complete report bytes, source references, execution counts and output
digests match in every timing and memory process. Memory improves mainly on
the writer-delta calls; these results do not establish a 20% overall RSS
reduction. This is not a database A/B/C capture-cost measurement.

Each call uses five warmups followed by thirty measurements in each of three
fresh processes. Three additional fresh single-call processes measure peak
RSS. Cold import, cold call and raw samples are retained. Baseline and
candidate groups ran consecutively without local compilation, packaging or
database workloads. Parsing, source checks and full report production are
inside the timed call; loading original input files is outside.

## Common-path controls

Register analysis, append-list analysis, relation classification and
model-preserving reduction use unchanged public examples. Each result is
independently verified, and baseline/candidate full output digests must agree.
The three batches alternate `AB`, `BA`, `AB`. All four P95 comparisons pass
the allowance `max(2 ms, baseline P95 * 0.10)`; raw values are retained,
including the relation classification increase from 3.762 to 4.938 ms.

Run the controls from a source checkout with two built runtime directories:

```text
node scripts/bench/source-digest-controls.mjs BASELINE_DIST CANDIDATE_DIST NEW_OUTPUT_DIR
```

The controlled source inputs and complete-call runner are in the public
[v0.4.1 baseline attachment](https://github.com/HhWw96/moontxnwitness/releases/download/v0.4.1/MoonTxnWitness-v0.4.1-configured-baseline.zip).
Its SHA-256 is
`227c22dfff232a33b571617f206f783f993c541c94cab2721305a5c3232da915`.
Extract it, point two copies of its plan at the corresponding runtime
directories, set each plan's source commit, and use distinct output directories:

```text
node --experimental-vm-modules scripts/bench/configured-window-baseline.mjs PLAN.json NEW_OUTPUT_DIR
```

The VM flag is used only to inventory runtime dependencies before measurement.
The recorded measurements and runtime staging bindings are under
`verification/performance/source-digests/`. Preserve failures; an existing
output directory, different source input, invalid report or output mismatch
must stop reproduction.
