# Category-specific register evidence

The new MoonBit entry points are `classify_v3_json(trace, options)`,
`reduce_classification_v3_json(trace, options)` and
`verify_classification_v3_json(trace, report)`. The existing serial analyzer and
selected-cycle explanation keep their original meaning. SDK/CLI wiring is a
separate integration step.

Classification options are `categories` (a nonempty unique subset of `G0`,
`G1c`, `G2-item`), `maxStates` (0–100,000), and `maxEdgeChecks`
(0–1,000,000). Defaults request all three categories at those maximum budgets.
Each category has its own counters and budget. Structure is limited to 128
transactions, 4,096 operations, and 50,000 dependencies. The input is at most
8 MiB UTF-8 and the report at most 32 MiB UTF-8. These limits do not guarantee
that every search finishes.

`G0` searches WW-only cycles; `G1c` searches every WW/WR cycle, including WW-only cycles implied by G0;
`G2-item` searches WW/WR/item-RW cycles with at least one item RW. Searches are
independent: a shorter cycle of another category cannot hide the requested
category. A witness is simple, but has no category-shortest claim. The report
retains every dependency, the full normalized observations/effects/history,
exact original trace text, and every matching original observation sequence
for witness endpoints. Captured predecessor chains are retained as facts; no
version-order completion is performed. Assertions are not authenticated SQL.

A rule is `refuted`, `checked-compatible`, or `unknown`; unsupported data models
remain `unsupported`. Here `checked-compatible` concerns only the requested
cycle category, not a full isolation model. Any source-verified refutation
remains valid when another category runs out of budget. G0 implies G1c and G1;
G1c implies G1; G2-item implies G2. These logical implications do not change the
most-specific witness label, recorded separately as `specificCategory`. An independent G1c request therefore still detects a pure G0 cycle.

Reduction options require `category`, and optionally accept `maxChecks`
(0–256, default 256) and `classificationOptions`. Only candidates which still
prove that exact category can be accepted. Every candidate is normalized and
searched again. Source gaps are not repaired by inventing writes or orders.
The result retains original sequence mapping and the exact reduced trace text.
`oneMinimal` requires a complete remaining single-delete pass; an otherwise
complete candidate whose search exhausts cannot establish minimality.

Verification recomputes every report field from the exact trace text and
recorded options. Host-side capsules separately bind raw trace, report and
options with SHA-256. The core does not introduce a new hash implementation.

The new tests include raw-capture cases, provenance, budgets, tampering,
category-preserving reduction, hidden longer cycles, and all 4,096 typed
three-node graphs against a separate simple-cycle enumerator. The 18 selected JS tests passed, including all 4,096 typed graphs (three
category comparisons per graph). The complete suite, other targets, database
integration, production bridge runtime and performance measurements were not
executed in this development slice. See `verification/classification-v3/v025/`.


The first development receipt at `v025/` used Elle's most-specific G1c search
label (requiring WR), while the public request semantics promised G0 -> G1c.
That mismatch was found in review. The correction at `v025-g1c-closure/`
freezes an independent G1c request over a WW-only history and changes the
independent enumerator to the logical closure definition. The original
18-test receipt and source hashes are retained unchanged; they do not certify
this semantic correction. New-model code and performance are outside this fix.
