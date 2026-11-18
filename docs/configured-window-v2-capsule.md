# Offline capsules for source-bound configured windows

`configured-window-v2-capsule.mjs` packages one original source-bound V2 window
and its analysis or reduction report for offline replay. The runtime is installed
separately: capsules contain data and do not select, download or load code.

This is a separate module. It does not change the main SDK, CLI, existing point
window capsule formats, or the optional structured verification profile.

## Analysis

```js
import {readFileSync, writeFileSync} from 'node:fs';
import {
  makeConfiguredWindowCapsuleV4,
  replayConfiguredWindowCapsuleV4,
} from './dist/configured-window-v2-capsule.mjs';

const bundleText = readFileSync('configured-window-input.json', 'utf8');
const options = {
  config: readFileSync('configured-sql.json', 'utf8'),
  policy: readFileSync('source-policy.json', 'utf8'),
  maxPointChecks: 1_000_000,
};
const capsuleText = makeConfiguredWindowCapsuleV4(bundleText, options);
writeFileSync('window-capsule.json', capsuleText);

// A verifier obtains its configuration, policy and budgets independently.
const replay = replayConfiguredWindowCapsuleV4(capsuleText, options);
console.log(replay.valid, replay.reportMatches, replay.status);
```

`make` analyzes the original bundle and invokes the existing verifier with the
same caller options before packaging. `replay` passes the retained original
bundle and report text to `verifyConfiguredWindowV4`, which reconstructs the
source-bound history and report under the verifier's independent options.

The capsule contains no options that can authorize a replay. The caller must
provide `config` and `policy` every time; omitted numeric budgets retain the
existing SDK defaults. Different effective input or budget evidence can cause
the report comparison to fail.

## Reduction

```js
import {
  makeConfiguredWindowReductionCapsuleV4,
  replayConfiguredWindowReductionCapsuleV4,
} from './dist/configured-window-v2-capsule.mjs';

const target = {
  config: options.config,
  policy: options.policy,
  preserveModel: 'serializable',
  // Window budgets belong in windowOptions for reduction calls.
  windowOptions: {maxPointChecks: 1_000_000},
  reductionOptions: {maxChecks: 256},
};
const reducedCapsule = makeConfiguredWindowReductionCapsuleV4(bundleText, target);
const reducedReplay = replayConfiguredWindowReductionCapsuleV4(reducedCapsule, target);
console.log(reducedReplay.valid, reducedReplay.refutationVerified,
  reducedReplay.oneMinimalVerified);
```

The reduction capsule keeps the complete original window. Its reduction changes
only the analysis transaction selection; it does not present a pruned raw log as
an independently captured window. Replay invokes
`verifyConfiguredWindowReductionV4`, including source closure, the selected model,
the final report, and the original one-deletion checks and budgets.

Only `serializable` is accepted as the independently selected preservation model
by this source-bound window entry. The existing relation-predicate reduction and
the original atomic-row window report keep their separate semantic contracts.

## Results and trust

Replay reports separate:

- `envelopeVerified`: strict capsule schema, canonical encoding and digests match.
- `reportMatches`: the existing verifier independently reproduced the report.
- `valid`: core verification succeeded and the report is neither `unknown` nor
  `invalid`. For analysis, a valid report can contain a model refutation or a
  compatible result; inspect `status` and the retained report.
- `refutationVerified` and `oneMinimalVerified`: reduction-only evidence flags
  taken from the independent reduction verifier. A verified capsule does not
  automatically imply a refutation or transaction single-minimality.

Matching `unknown` or `invalid` diagnostics can be archived and reproduced, but
their capsule result always has `valid: false`. A report mismatch exposes no
verified report or refutation flags. `sourceAuthenticated` is always `false`.
This is an additional capsule gate: the underlying SDK's report verification
can succeed for a complete source window whose model result is still unknown.
The capsule does not change that SDK result or its original meaning.
Digest checks detect changes relative to the packaged data; they do not prove
that supplied observations came from a particular database or machine.

Changing a report and recomputing all outer digests still requires the core to
reproduce that report from the original bundle and independently supplied
configuration and budgets. Neither an outer digest nor a capsule-supplied field
can replace that step. Callers must separately decide whether to trust the
origin of the original observations.

A failure diagnostic need not bind every byte of a rejected input: for example,
adding JSON whitespace can reproduce the same `unknown` diagnostic. Such a replay
can have `reportMatches: true`, while its `valid` and evidence flags remain false.

## Encoding and limits

The two operation domains use separate formats:

| Operation | Format |
| --- | --- |
| Analysis | `moontxnwitness-configured-source-window-capsule/v1` |
| Reduction | `moontxnwitness-configured-source-window-reduction-capsule/v1` |

Both have exactly these ordered fields: `format`, `operation`, `bundleText`,
`bundleSha256`, `reportText`, `reportSha256`, `capsuleSha256`. The final digest is
SHA-256 of the compact JSON object containing the preceding six fields in this
order. Each text digest hashes the original UTF-8 text. The capsule is compact
`JSON.stringify` output plus one final newline.

Replay accepts only this generator's exact canonical encoding. It rejects extra
fields, duplicate keys (including escaped duplicate keys), reordered fields,
alternate string escapes and whitespace. The original inner texts keep their
bytes: they go directly to MoonBit's strict parser rather than through a host
parse/serialize cycle. The capsule cannot specify modules or code paths.

| Boundary | UTF-8 limit |
| --- | ---: |
| Original bundle text | 32 MiB |
| Analysis report text | 32 MiB |
| Reduction report text | 64 MiB |
| Analysis capsule, including escaped inner texts | 136 MiB |
| Reduction capsule, including escaped inner texts | 264 MiB |

The inner raw text limits are checked first, and the final escaped capsule is
bounded separately. Some heavily escaped inputs within the inner limits can
still exceed the capsule limit and are rejected. These transport limits do not
raise any transaction, operation, source-check, search or reduction budgets.

Applications that deliberately select another already installed SDK can use
`createConfiguredWindowCapsulesV4(sdk)`. The factory requires the four existing
analysis, reduction and verification functions. This is an explicit trusted
application choice; the capsule cannot choose that SDK.

## Reproduction checks

```powershell
node scripts/configured-window-v2-capsule-test.mjs --runtime dist `
  --receipt D:/CodexScratch/mtw053-reduction-postgres-1117/receipt.json `
  --output D:/CodexScratch/window-capsule-consumer.json
```

The receipt option replays retained actual PostgreSQL observations across int64,
text and UUID primary keys: CRUD, RR write skew, noisy counterexamples, ordered
Serializable execution, and zero-row-write diagnostics. The script checks both
capsule domains, independent configuration and budgets, source text preservation,
outer-digest recomputation attacks, unknown results and reduction flags. It does
not execute the database or measure performance. Omitting the receipt runs only
the local transport and invalid-diagnostic checks.
