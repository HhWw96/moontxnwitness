# G1c public logical-closure correction

The prior v025 implementation searched the most-specific Elle G1c label, requiring
at least one WR edge. Its public independent G1c request also promised the logical
G0 -> G1c implication. The frozen WW-only history exposes that mismatch.

`old-artifact-regression.json` records an actual pre-fix `checked-compatible`
result. It was obtained from the exact previously compiled white-box JS artifact
whose SHA-256 is recorded there. `freeze-old-artifact.cjs` removes only the terminal
whole-suite driver invocation and exports the existing classify function in a VM;
it does not modify the original artifact or compile a new production bridge.
The original 18-test receipt at `../v025/` remains byte-for-byte unchanged.

The corrected G1c rule searches all WW/WR cycles using its own budget. A pure WW
witness reports `specificCategory: G0` and derives G0, G1c, G1. The independent
three-node enumerator now checks that logical public rule; its old WR requirement
is documented explicitly rather than silently changing previous receipts.

The corrected source has now passed official format/info, the full JS source check with warnings denied, and all 19 selected classification tests. New-model drafts were excluded during these checks. Other targets, real databases, formal performance and release acceptance are outside this correction and were not executed.


The first post-fix JS source check passed, and the first selected run passed
17/19. Its two failures exposed old fixture assumptions that G1c excluded G0:
the long-cycle test called a WW cycle irrelevant to G1c, and the budget test
expected G1c to be unknown despite its complete WW witness. The revised long-WR
fixture uses a genuinely irrelevant short RW-only cycle; its original length
assertion is retained. The budget test checks independent G2-item exhaustion;
its original `unknown` assertion is retained. The frozen G1c-only regression and
the corrected independent graph oracle passed on their first post-fix run.
The initial failure logs are retained, not overwritten.
