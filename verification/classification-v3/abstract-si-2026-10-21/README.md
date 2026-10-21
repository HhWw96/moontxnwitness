# Independent bounded abstract SI cross-check evidence

This bundle publishes the frozen reference, inputs, existing results, independent review and graph correspondence checks. The files copied under `payload/artifacts/` retain their original bytes and sibling directory layout. Historical plans, errors and later additive corrections remain distinguishable. No oracle, Node program, compiler, database or performance workload was rerun during publication.

## Definitions and scope

The independent reference implements the contract `cerone-no-session-si-register-v1`: INT, EXT, PREFIX and NoConflict, with an empty session order. Its serial control requires the full earlier visibility prefix. It assumes committed transactions, explicit initialization, unique per-key version identities and complete factual final-write orders, within six transactions/128 operations/128 keys. Those factual orders are input assumptions, not inferred from array order, transaction identifiers, acknowledgements, clocks or a returned witness.

This is an experimental small-model reference and graph correspondence check. It is not an Elle run or a complete six-model isolation classifier. It does not establish collector authenticity, scoped rollback semantics, predicate/list/relation coverage, real-time order, stable public API, full application integration, human acceptance or organizer acceptance.

## What was retained and checked

- **52 hand-written boundaries:** the exact inputs and manual SI/serial expectations, plus the author's self-test summary. Full per-case output certificates were not retained for these52. The independent review checked their applicable expectations/source rules, and does not claim to have replayed52 full certificates.
- **1,000 generated histories:** all1,000 input SHA values are distinct; one original JSONL and one original complete result JSONL retain2,000 SI/serial reports. SI outcomes are551 admissible,349 refuted,100 inconclusive; serial outcomes are463 admissible,437 refuted,100 inconclusive.
- **1,014 positive certificates:** independently checked literal arbitration/visibility, INT/EXT/PREFIX/NoConflict and serial-control obligations. The check did not trust the author's `witnessVerified` field or use graph cycle absence to accept a positive witness.
- **1,052 input records accounted for:** independent conversion froze683 common complete graphs,295 direct semantic obligations and74 coverage/structure/capacity exclusions. No out-of-domain or unknown case was silently counted as absence of a cycle.
- **683 common graphs:** independently checked against the fixed experimental MoonBit kernel;683 node/edge order reversals and3 budget checks are retained. Existing graph receipts record1,088 cycle witness checks and7,108 absence checks. These are distinct from the1,014 abstract-execution positive certificates.
- **Cross-check results:**1,220 generated common-range model comparisons,580 direct refutations and200 unknown reports are retained with zero unexplained differences. Unknown source and zero-budget cases remain inconclusive. The52 manual boundary comparisons have their separate, narrower scope in `comparison-receipt-v1.json`.

The graph comparison constructs WW/WR/item-RW edges only from original complete version/source facts and reversible identity indexing. Generalized SI uses cycles in D union (D;RW), with D=WW union WR; the serial control uses D union RW. INT, external intermediate reads and own-future sources remain separate semantic obligations. No array/ACK/search ordering is added as a fact.

## Runtime and source provenance

`runtime/graph-only-capture-core.mjs` is the actual frozen experimental module:1,150,860 bytes, SHA256 `af606ccd40106ae9a5b46d12d550f0a3002b404c60018ca4512544c66295f1d1`. Its source fingerprint is `217388d9be420c2b881f32e57ccf1e71f598d929ed5e4f745924be71d65e58ca`.

Matching source overlays and original graph-kernel failure/review receipts are published in the sibling `../graph-kernel-2026-10-21/`, including `src/classification_graph_v3.mbt`, its white-box tests and the capture-bridge export. They target the public8f5d51a878ef7872f76e02fa745888523df6436a base, whose MoonBit source fingerprint is `df23e6a01c0d59420c7576eb35271b6346c500044ee24a0ea0d7ac29a951d97b`. This draft runtime is not the stable runtime downloaded from checkpoint7863550 or the package's default classification API.

The original `check-kernel.mjs` contained a private absolute checkout path and is intentionally omitted. Its exact original byte count/SHA remain in `portable-change-record.json`. The published `check-kernel-portable.mjs` changes only that location to an explicit first CLI runtime argument and retains the immutable runtime SHA pin. **This portable variant has not been executed.** Its distinct digest does not replace the original executed-checker digest inside frozen receipts.

The existing payload includes immutable outputs whose writers use exclusive creation. Do not run generators/checkers directly over the archived payload and overwrite or delete records. Any future reproduction must copy the code and required frozen inputs into a separately identified clean output layout, preserve the two sibling directories, supply the published runtime explicitly and write new receipts. No reproduction claim is made for this publication step.

## Preserved corrections

The first generation plan wrote a target1100 while its nine quotas summed to1000. The explicit first-inconsistency record and amendment correct that plan sentence without changing the seed, quotas,1,000 frozen inputs or expected/results bytes.

The original general counter sentence omitted the empty-execution direct-proof exception. The original zero-budget empty-history boundary and code already agreed. `contract-erratum-empty-execution-v1.json` clarifies zero states/zero semantic checks without changing the original contract, implementation, inputs, expectations or measured results.

Original author notes predate the later independent static review; they are preserved as historical artifacts. `static-review-v1.json` records the subsequent review and its limits. `publication-index.json` binds every copied file and the separately published runtime; it does not turn any of these experimental checks into stable or official acceptance.
