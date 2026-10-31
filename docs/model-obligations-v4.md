# Source-bound canonical model API

The independent model namespace composes actual source rules, category-specific graph work and applicable completion certificates for 14 fixed Elle definitions. It does not replace `classifyV4`, the six older model definitions or relation-category APIs. Relation predicates currently expose seven graph categories; that is not a completed fourteen-model relation checker.

```js
import {classifyModelsV4, verifyModelsV4, makeModelsCapsuleV4,
  replayModelsCapsuleV4} from './dist/sdk.mjs';
const options = {models: 'elle-core'};
const report = classifyModelsV4(originalCapture, options);
const verified = verifyModelsV4(originalCapture, report, options);
const capsule = makeModelsCapsuleV4(originalCapture, options);
const replay = replayModelsCapsuleV4(capsule, options);
```

`models` accepts `elle-core` for the 14 exact canonical names or a nonempty array of distinct names. Without it, the default remains six models. Aliases are not counted as additional models.

| Canonical names | Necessary graph context |
| --- | --- |
| read-uncommitted / read-committed | W / I, data only |
| repeatable-read / consistent-view | I+item RW / G-single, data only, plus literal coverage |
| serializable / strict-serializable | D / D with proven real-time order |
| snapshot-isolation | Ext(I,A) with checked original-program completion premises |
| strong-session-read-uncommitted / strong-read-uncommitted | W with explicit logical-process / real-time context |
| strong-session-read-committed / strong-read-committed | I with explicit logical-process / real-time context |
| strong-session-serializable | D with explicit logical-process context |
| strong-session-snapshot-isolation / strong-snapshot-isolation | Ext(I,A) with explicit logical-process / real-time context |

These are fixed Elle transaction-observation definitions, not database product isolation labels. Reports enumerate each necessary rule and preserve checked, refuted, unknown and pending work. A reliable forbidden witness survives unrelated missing facts or budget exhaustion. Compatibility requires every necessary source and model rule to finish. RC and RU are not forced through full snapshot INT: changing external reads can be legal under RC even when the independent INT inspector or SI reports a violation.

Options are strict: `maxSourceChecks` (0..1,000,000 per source module), `maxStates` (0..100,000 per graph rule), `maxEdgeChecks` (0..1,000,000 per graph rule), `clients`, `clientsComplete`, `listProfile`, `relationProfile` and `completionPolicy`. Unknown fields, duplicate decoded JSON keys, aliases, duplicate model names and invalid limits fail. Source text is limited to 8 MiB, options to 8 KiB, a report to 32 MiB and a capsule to 64 MiB. Exact-search transaction limits remain unchanged; these are graph/certificate budgets.

Logical clients use `{id, transactions}` records tied to original identities. They are caller-declared source facts, never inferred from a pooled connection. Missing session or real-time evidence remains unknown where required. BEGIN time does not assert a logical snapshot. `completionPolicy: 'given-logical-snapshot-assertions/unsupported'` keeps applicable snapshot completion unavailable.

Complete captured point-register programs use `captured-register-full-program/v2`. Lists retain native behavior by default. Explicit `listProfile: 'captured-list-prefix-state/v2'` adds proved writer blocks, external-prefix components and original-program completion replay within its documented source scope. Incomplete windows, unproved prefixes or missing producers cannot be repaired by renumbering or inventing operations. The original capture is immutable; derived states and constraints are recorded separately.

Relation point/source checks retain their current bounded applicability, and higher relation completion remains pending. `relationProfile: 'adya-2000-predicate-on-keyslots-v1'` does not silently turn Adya predicate edges into a completed fixed-Elle model graph.

Verification always reanalyses the original history under independent caller options, clients, source profile and limits. The model-specific capsule binds exact source/options/report texts, SHA-256 digests and semantic/algorithm/counter identifiers. Embedded limits and statuses cannot grant authority. Producer version is descriptive metadata and does not select a verifier. Hashes and semantic replay do not authenticate the original observer.

CLI equivalents:

```text
node dist/moontxnwitness.mjs classify-models-v4 SOURCE.json --models elle-core --output REPORT.json --capsule CAPSULE.json
node dist/moontxnwitness.mjs verify-models-v4 SOURCE.json REPORT.json --models elle-core
node dist/moontxnwitness.mjs replay-models-v4 CAPSULE.json --models elle-core
```

Pass the same independently selected `--options EXPECTED.json` for logical clients, explicit list mapping and nondefault budgets. `--list-profile captured-list-prefix-state/v2` is also available. Options cannot be specified twice. Output files must not exist. Exit codes are 0 for all requested models checked-compatible, 1 for a refutation, 2 for invalid input/evidence and 3 for unknown/pending; successful verification/replay means semantic reproduction.

The raw-register and list MoonBit consumers are in `examples/captured-models-v4` and `examples/list-model-completion-v4`. The offline JavaScript roundtrip is `node examples/models-v4-roundtrip.mjs` after a current build. Local development checks are not public-package installation, database or performance evidence.

The opt-in [atomic row profile](relation-atomic-models-v4.md) has a separate [JavaScript roundtrip](../examples/relation-atomic-models-roundtrip.mjs). [Candidate verification](v0.3.6-validation.md) distinguishes maintained SDK tests, previous fixed Elle results and pending checks of the final compiled runtime.
