# Report RT quotation cache candidate

This candidate caches already encoded endpoint strings for standard realtime
edges during one report write. The JS cache uses a private external type and
String/Unit FFI values. Misses still call the original quoted_cached function,
whose default path uses cached_quote and the standard Json string encoder.
No ASCII-specific encoding or Option representation is introduced. The type and
scalar boundary follows the [official MoonBit FFI contract](https://docs.moonbitlang.com/en/latest/language/ffi.html).

The original write_edge entry and MoonBit string Map remain available. Only
edges matching the exact existing standard RT field shell use the JS cache;
custom reasons, provenance fields and non-RT dependencies keep the original
writer. Both paths share one unchanged shell literal. Other targets keep the
original edge loop without an additional cache allocation. Graph construction,
sources, ordering, limits, counters and serial orders are unchanged.

Actual JS functional checks passed: 14 new cases, four original RT-shell cases,
eight original transport cases and the original streamed-report comparison.
The new cases cover Unicode, combining characters, quotes, backslashes, controls,
all optional-field combinations, fallback edges, report separation and the full
49,770-edge report. The public MoonBit interface is unchanged.

The functional SDK/wire comparison uses eight fixed inputs and six unchanged
metadata negative controls. Its 16 SDK calls and 16 raw core calls matched the
fixed public031 results, normalizing only the product version header. Actual
Node module parsing checks all 25 baseline and 36 candidate static modules with
byte hashes before and after execution. Lazy dynamic imports are outside that
inventory. The old regex-based 18/27 declarations are not reused as complete
closures.

These local checks use a bounded 512 MiB functional-test heap and produce no
performance samples. There is no speedup or RSS claim. The independent paired
performance CI must build this exact candidate and retain its existing eight
scenarios, six controls, 768 MiB heap, five warmups, 30 samples and three batches.
