# df23 profile-directed performance candidates

These are isolated drafts. The primary source, scripts and dist are unchanged. The original formal run remains authoritative: all 20 P95 guards passed, while the graph RSS, large-search speed and reduction speed targets were not all met. No candidate below has run the formal gate.

The exact baseline is source `df23e6a01c0d59420c7576eb35271b6346c500044ee24a0ea0d7ac29a951d97b`, main core `318fecd1f38f8415f7b0c65455facd119efe2c2a0035b7b7ce7535faeec329f8`, and capture core `588d1a2479565cfb6575b5f3b1b484091002b184ba69c6f609f4e84d5f546166`. All 554 baseline core tests are retained. The new owned workspace is `<external-scratch>/MoonTxnWitness-performance-df23-draft-20261021-slice2`.

## Diagnosis before changes

The protocol froze the current core, pinned v0.1.0 core, four original fixtures, and the diagnostic worker before any code change. Eight workers ran exactly once: current and v0.1.0 for search12, reduction512, dense192 and dense316. Each used five warmups and thirty full JSON-in/JSON-out operations, CPU sampling at 500μs, heap sampling at 32KiB including collected objects, and a GC observer. No forced GC or worker retry was used.

The original 48 profile/output/log files were bound before edits. Four additional workers later used the identical protocol on the genuinely changed v1 candidate. All 72 files are bound in `manifest.json`. These samples are instrumented diagnostics, not formal timing or RSS evidence. Inspector `post`/callback work is visible in raw CPU profiles and is not attributed to the analyzer.

The df23 search12 state-key builder accounted for about 70.6% of sampled allocated bytes. Its generated JS appended one scalar at a time using `StringBuilder.write_char` and `String.fromCodePoint`, creating intermediate strings. The reducer's identifier validation still allocated iterator/closure objects for repeatedly checked short identifiers. Dense graphs were dominated by complete JSON joins and host parsing; replacing graph indexes alone cannot be presented as a demonstrated 20% whole-process RSS reduction.

## v1 code changes

1. Search keeps exactly the existing key of `1 + 2*K` UTF-16 units: done mask, every current version and every declared-chain position. It reuses a private bounded integer scratch buffer and uses one JS `String.fromCharCode` call. K≤128, mask≤4095, versions≤512 and positions≤12, so all units lie below the surrogate range and there are at most 257 arguments. Non-JS uses the same complete encoding via its ordinary builder. There is no hash, truncation, missing component, traversal change, cache-policy change or budget change. Previously returned strings cannot alias the reused numeric scratch.
2. `valid_identifier` scans UTF-16 units for the same forbidden ASCII controls instead of constructing a scalar iterator and predicate closure. Length remains 1–256 UTF-16 units. Every surrogate unit exceeds the forbidden ASCII range, so this preserves the original predicate for supplementary Unicode characters as well.
3. Graph sources, targets and adjacency lists use exact capacities instead of repeatedly grown arrays. Two passes preserve every original edge and each source's original edge order. Tarjan, BFS, topology, evidence, tie order and counters are unchanged. Generated JS uses ordinary arrays here; the draft does **not** claim that MoonBit `FixedArray[Int]` has Int32Array storage.

v1 passed 562 tests on each of JS, Wasm GC and Wasm, plus all-target warning-free checking. It also passed 117 exact complete-output comparisons against the frozen df23 core: all 20 original scenarios, large-search budget/cache boundaries, reducer budget boundaries, and Unicode/control inputs. The comparison includes full fields, edge sources, budgets, counters and evidence.

The identical allocation protocol observed the following statistical totals over 35 operations:

| Workload | df23 sampled allocation | v1 sampled allocation | Ratio |
|---|---:|---:|---:|
| search12 | 112.81 MB | 56.20 MB | 0.498 |
| reduction512 | 125.51 MB | 108.71 MB | 0.866 |
| dense192 | 590.23 MB | 563.21 MB | 0.954 |
| dense316 | 1,545.29 MB | 1,463.71 MB | 0.947 |

One predeclared changed-code smoke used eight new workers, one warmup and three measured operations, comparing v1 with df23. Search12 was 21.139→7.903ms; dense192 51.555→46.460ms; dense316 152.975→126.792ms. **Reduction512 was slower: 13.175→16.967ms.** Dense192 smoke maxRSS fell, while dense316 smoke maxRSS rose. These observations, including regressions, are retained without rerunning this implementation to select favorable samples. They establish no formal target result.

## Distinct v2

v1 source, binaries and receipts are preserved under `variants/v1`. v2 additionally shares one private zero-length neighbor array for zero-outdegree vertices. Such an array has no valid writable index, holds no input state, and is never written by the nonzero-edge fill pass. This avoids allocating hundreds of empty neighbor arrays beside a small cycle or in an edgeless history. Nonempty lists retain exact capacities and original order.

v2 passes 563 tests on each target, all-target warning-free checking, and the same 117 complete-byte comparisons. The additional semantic regression verifies 512 vertices with a two-cycle and 510 isolated vertices, including component counts and stable topology. **v2 has not been timed or heap-profiled**; the owned PostgreSQL run began before another isolated timing window was available. No performance benefit is claimed for its empty-array sharing.

v1 source/core: `9250b4f71d681df14980c48a97dc529ec5bc11b33fcf9c5894aa2cabeddd3ad7` / `307ccf5c9b1fa79f007cd270b69ed12eda91ca2afc91ab2d2206ff0210cedcf3`.

v2 source/core: `b6638ee56395a14284d1440a92a0d975c4ea4073f42ccab6d8d39e359d928096` / `52d9593c8c6fd063ce26d0a37a2e43cc1a0930363de3b5f7e052f054c502569c`.

Both capture cores are `d91d5cb547d80ddaa44d35ee622f9eb789aff19444485c29693b6ac57ea15deb`. The final manifest is SHA256 `e561e9bcc30c83c4f3450331c152c42b4696114b85b4ce0d09719abb60710980`.

## Review and next gate

The reviewable final sources and baseline-relative patches are in `candidate-v2/`. Search and identifier patches can be reviewed separately from graph representation changes. The graph change also requires the matching empty GraphIndex literal change in `analyze.mbt`. No initial fact, transitive edge, output field or edge provenance is removed. The old key-boundary/cache-budget tests remain unchanged.

Independent review and the parent's full integration/packaging checks precede any new formal gate. Search allocation has a concrete reduction; reduction latency and whole-process graph RSS remain unresolved. Complete JSON joins and host parsing remain substantial dense-graph costs. Any next writer or index change must preserve the same full output range and retain this v1 regression record.

The initial preparation failure and misleading mixed-object PowerShell table interpretation are retained in `prepare-first-failure.json`. Explicit volume reads showed sufficient space; no disk was exhausted and no old evidence was deleted. The first empty failed workspace remains separate from slice2. Compiler/test setup failures are also retained in the isolated receipts directory.
