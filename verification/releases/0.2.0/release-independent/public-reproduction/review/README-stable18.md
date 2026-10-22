# New stable18 independent review

This is a new preparation and new full101 semantic run, not reuse of old
experimental5999/core5b63 acceptance. It requires source81b221/core d6cf18 and
capture60da31, plus root's stable-specific freeze kind/signal and external SHA.
The production parse_optimized source must exactly match frozen published17.
All original2542/117/81 diagnostics/287 capsules/132 derived expectations remain
unchanged. The known287 manifest locator was corrected before this preparation;
old wrong source/first failure remain preserved in the experimental audit.
No performance measurement is authorized or performed by this entry.
Only packages=[] is accepted for semantic review; package consumers and main
regression/PG/publication remain root's separate phases.

Run only after root gives the new stable freeze SHA:

```
python -B run-review.py --freeze STABLE_ROOT_FREEZE --freeze-sha256 ROOT_SHA --preparation-sha256 PREPARATION_SHA
```

Missing identity guards reject before any SDK import. The old generic README and
old manifests are provenance; this stable identity requirement takes precedence.
