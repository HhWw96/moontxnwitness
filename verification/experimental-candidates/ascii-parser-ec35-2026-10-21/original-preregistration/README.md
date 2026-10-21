This is an uncompiled, untested, unmeasured parser allocation candidate. The
production parser and the original b663 writer experiments are unchanged.
`protocol.json` was hashed before either candidate source or tests existed.

The existing scanner already detects the string's closing quote and whether the
content is unescaped ASCII. At that exact successful branch, this draft returns
one of 21 immutable schema literals only after exact length/first-unit/full-unit
comparison. Unknown strings retain the original owned-substring path. Escapes,
Unicode, invalid strings and the public legacy-error fallback remain intact.
No dictionary or unbounded intern table is added.

The motivation is an older, rejected writer experiment whose parser bytes equal
the baseline parser. Its allocation percentage is not a current baseline or an
estimated performance improvement. It does not demonstrate the required graph
RSS or reduction speed target. The graph stores/edges and reducer algorithm are
unchanged by this draft.

For a later isolated build, copy only `candidate/parse_optimized.mbt` and
`candidate/performance_ascii_symbol_wbtest.mbt` into a fresh source clone at the
same src paths. Nine tests are written but have not run. Run focused/all-target
checks and the complete117 old output-byte comparisons before a separately
declared changed-code allocation smoke. Keep all errors and regressions. Do not
use the in-progress main integration as a fixed baseline or run formal timing
from this draft without a separate accepted source snapshot.
