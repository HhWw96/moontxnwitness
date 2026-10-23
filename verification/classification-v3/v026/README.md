# v0.2.6 draft verification record

This directory preserves development evidence, including failures. It does not
claim publication, database execution, performance acceptance or independent
six-model acceptance.

- The original first source check and selected test run failed. Their complete
  diagnostics, pre-change assertions, approval rejection record and semantic
  decision are retained unchanged.
- `compat-handoff-first/` freezes the inherited draft and the unchanged 38-test
  selection after the `readSeq` field correction. Its model test file SHA-256 is
  `27f4429892105528e706b078d0dd085658112529e5ad20282c1b55442f60e119`.
- `prefix-audit-before/` contains exact raw list captures and SDK reports showing
  false G2-item refutations when immutable initial prefixes were omitted or
  reordered. The first three-test semantic run passed only the valid control;
  both negative cases failed before the source repair.
- `prefix-audit-after/` records the strict JS check, 42/42 selected tests and the
  same raw-capture replay after repair. Four audit tests were added separately;
  no inherited expectation was edited. Invalid reads supply no edges or direct
  anomaly proof. A valid independent cycle remains a refutation even alongside
  another invalid read.

`prefix-audit-before/core.mjs.gz` is the exact pre-fix compiled runtime in gzip
form. `runtime-archive.json` binds compressed and original SHA-256 values;
`build-manifest.json` binds its source and toolchain. Decompress it to `core.mjs`
in a fresh copy before using the preserved counterexample generator. Its
exclusive-create outputs must not overwrite the original evidence files.

The runtime version field remains the frozen v0.2.0 development baseline. These
artifacts are unreleased candidates, not publicly released v0.2.6 binaries.
Cross-target regression, independently checked model semantics, real collector
sidecars, full Elle comparison, database cases and installation remain separate.
Raw receipts and compiler logs intentionally retain their original CRLF and
compiler alignment whitespace. They are evidence bytes, not reformatted source.
The product-source whitespace check covers `src/` and `docs/`; raw evidence is
preserved exactly rather than edited to satisfy a formatting check.
## Direct list G1b follow-up

`g1b-source-audit-before/` freezes d18's complete runtime, nine raw independent
inputs, the pre-edit semantic decision and original first/addon expectations.
The frozen pre-fix runtime fails seven of the nine documented checks: three false
G1b labels and four producer-prefix coverage gaps. Those failed outputs remain.

`g1b-source-audit-after/` binds the repaired core and the same raw inputs. Actual
last-version G1b labels, preserved same-key aborted-item G1a, explicit malformed
external-prefix gaps and report self-verification pass all nine author checks.
The original 42 assertions remain byte-identical; ten new direct-source tests
bring the strict JS target selection to 52/52. Original compiler diagnostics for
a reserved test parameter are preserved; only that local name was corrected.

Both candidate compiled cores are stored losslessly as `core.mjs.gz` with full
compressed/uncompressed digests. This does not replace independent review or
claim database execution, external adoption, cross-target or performance results.
