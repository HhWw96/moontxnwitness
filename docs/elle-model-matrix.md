# Actual fixed-Elle model comparison

The maintained workflow executes Elle commit `4e359e597c52938b0afebb8bc42273914d68a424` with JDK 21, Leiningen 2.11.2 and the upstream Clojure 1.12.6 dependency. It builds this checkout's SDK. Historical smoke scripts and the original 2,000-history comparison keep their original SDK and evidence bindings.

## Common facts

The case generator declares original register/list operations, confirmed outcomes, one clock domain and explicit logical clients. Physical connection names do not select clients. Initial register versions map bijectively to the upstream initial `nil`; list element identities, rather than possibly repeated business values, are upstream append values.

Most cases use client observations only. Register WW-cycle cases additionally supply predecessor facts already present on original writes. The independent converter resolves only those original committed-final writer identities and passes them through Elle's additional-graph interface, retaining the original write positions and source records. No MoonTxnWitness report, inferred order or completed search output becomes an upstream input.

Per-key linearizability, sequential consistency and writes-follow-reads inference flags are disabled. The fixed reference documents caveats for these inference options. Choosing a target model does not enable an assumption that it already holds.

## Cases and outcomes

Each of two datatypes has fourteen model targets with a required compatible case, a forbidden case and an incomplete-source case: 84 required positions and 56 required actual upstream comparisons. Forbidden families vary by target: WW, WR, write skew, single anti-dependency and explicit order violations. Additional families include nonadjacent anti-dependencies, aborted and intermediate sources, internal inconsistency and future WR cycles.

The generator currently produces 378 source/model cases and 342 eligible upstream requests. In addition to the original 84 positions, required cross-client stale reads distinguish real-time restrictions from logical-session restrictions, and required missing-client cases preserve unknown session coverage. In total there are 120 required positions and 84 required actual upstream comparisons. Missing-event and missing-client histories remain recorded as SDK `unknown` and upstream not-comparable; the converter never silently fills either gap. Additional cases may be unknown or expose differences. Every difference and raw upstream result is retained, and an unexplained determinate difference fails the comparison.

The original single-transaction positive remains as `own-only`: the actual list checker returns `empty-transaction-graph` unknown for that input. Required positive cases include an observed dependency between two committed transactions, so reference unknowns cannot masquerade as completed positive comparisons.

An early local fixture audit found list WR cycles with reads before the producers' appends returning unknown. Those exact source semantics remain a separate `future-wr-cycle` boundary family. The basic `wr-cycle` family puts both original writes before the reads and tests the intended dependency cycle without the additional future-source premise.

`compare-test.mjs` uses synthetic responses only to test accounting and fault refusal. Its success is not actual Elle execution. The Linux workflow separately retains the actual JVM results; a successful SDK preparation alone cannot establish reference parity.

Comparison binds the request digest and each result's identity, actual checker datatype and requested canonical model. A same-valued result routed to another checker or model is rejected rather than counted as a match.

The [retained actual run](evidence/elle-model-matrix-v042.json) executed 342 fixed-Elle requests: 289 matched, 53 unknown, no determinate differences, timeouts or checker failures. All 84 required actual pairs matched. The 36 incomplete-source/context positions remain separately not-comparable. The receipt binds the actual workflow commit, exact runtime, prepared inputs, raw result digest, per-model counts and downloadable artifact digest. It covers these discriminating fixtures; the earlier 2,000-history serializable comparison retains its separate scope.

The comparison also verifies the upstream runner's successful completion record, exact request/result/checker bindings, fixed-source inventory, toolchain identities and post-run source check. A checker output left behind by a subsequently failed run cannot receive a passing comparison receipt. Accounting tests inject those failure conditions independently.

## Reproduce

From the source checkout on Linux, after installing the fixed compiler and building:

```text
node scripts/elle-model-matrix/compare-test.mjs
node scripts/elle-model-matrix/prepare.mjs dist NEW_OUTPUT
python -B scripts/elle-model-matrix/run_upstream.py --requests NEW_OUTPUT/requests.edn --output NEW_OUTPUT/upstream
node scripts/elle-model-matrix/compare.mjs NEW_OUTPUT
```

Output directories must be new. The runner binds the exact EDN request bytes, source files, upstream commit, launcher/JAR, licenses and dependency tree. Raw per-case EDN, SDK report digests, inputs, execution logs and comparison rows remain available even on failure. Download/dependency failures, checker errors, timeouts and unknown model results are separate outcomes.

This workflow does not yet add relation predicate reference parity. Relation extension uses its own model definition and independent interpreter. Neither model count nor successful self-replay substitutes for actual upstream comparison.
