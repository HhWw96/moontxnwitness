# Source-closed configured-window reduction

The adapter composes independently verified PostgreSQL windows with the existing
relation-predicate model reducer. It preserves a caller-selected `serializable`
refutation. It leaves the window's original atomic-row graph, complete serial
certificate and raw input contract unchanged.

```js
const target = {
  config, policy,
  preserveModel: 'serializable',
  windowOptions: {maxSourceChecks: 1_000_000, maxPointChecks: 1_000_000},
  reductionOptions: {
    maxChecks: 256,
    modelOptions: {maxSourceChecks: 1_000_000, maxStates: 100_000,
      maxEdgeChecks: 1_000_000},
  },
};
const reduced = reduceConfiguredWindowV4(originalBundleText, target);
const checked = verifyConfiguredWindowReductionV4(originalBundleText, reduced, target);
const html = explainConfiguredWindowV4(originalBundleText, originalReport,
  {config, policy}, {reduction: reduced, reductionOptions: target});
```

The SDK exports these functions from its shared core and standalone entry. See
the [CLI and SDK reference](configured-window-v2-sdk.md) for commands. The input
bundle must be original UTF-8 text. Supply configuration, policy and all options
independently; fields inside a report do not authorize its own replay.

## Selection and proof

The core first recomputes the complete source window. It then classifies the
derived full history under `relation-predicate-models/v1` and reduces under
`relation-predicate-model-reduction/v1`. The adapter has its own
`verified-configured-window-model-selection/v1` contract. If a complete original
serial certificate conflicts with a new refutation, the composition is invalid
and both reports are retained.

Candidates select transactions for analysis. They do not remove original SQL,
snapshots or source records, create initial versions, or turn inferred order
into captured facts. `originalEventSequence` and `selectedOriginalEvents` bind
the dense analysis view to the original verified history. Every deletion checks
original facts, sources and the selected model again. Deleting a writer read by
a retained transaction leaves a source gap and cannot be silently accepted.

`oneMinimal` requires a final source-closed refutation and complete single-delete
checks of every remaining transaction. Unknown candidates, incomplete model
checks or exhausted candidate budgets prevent this flag. It does not claim an
operation minimum, global minimum or preservation of a particular anomaly label.

Verification reports three separate results:

- `valid`: the complete-window report and reduction faithfully recompute.
- `refutationVerified`: the selected model refutation is preserved.
- `oneMinimalVerified`: the remaining transaction single-delete checks complete.

A compatible input can have a faithful `not-refuted` report while both latter
flags are false. An unknown source window cannot enter reduction. A zero
candidate budget can retain an already established refutation but cannot prove
minimality. `maxChecks` counts deletion candidates, while initial/final model
classification has its separately declared budgets. No real-time or session
facts are inferred; the adapter fixes `realtimeKnown` to false.

## Explanation and reproduction

The offline HTML renderer verifies the original window before reading display
fields, and independently verifies any optional reduction. It links explicit
`historySeq` references to original statement, projection, native result,
business deliveries and row versions. Reduced witnesses link through the checked
original-event mapping. Text is escaped, external execution is disabled by CSP,
and output is bounded to 64 MiB. Report text remains the complete evidence input.

Run the isolated PostgreSQL 18.6 campaign with `--with-window --with-analysis
--with-reduction`, then run:

```text
node scripts/configured-window-reduction-v2-check.mjs --core dist/sql-projection-v2-core.mjs --receipt <original-campaign-receipt.json> --output <new-directory>/checks.json
```

For int64, C-text and UUID identities, the campaign captures five real committed
transactions and reduces the RR anomaly to two. Three read-only noise
transactions read a committed anomaly writer, so their source dependency is
checked during deletion. Normal CRUD/ordered controls and zero-row-write
unknown cases run through the same adapter. The runner records actual sizes,
independent budgets, tamper rejection and unchanged original input digests.
