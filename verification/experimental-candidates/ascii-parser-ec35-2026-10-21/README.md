# Isolated ASCII parser allocation experiment

The candidate reuses 21 exact ASCII literals after the original string scanner
has validated the closing quote. Unknown, escaped, Unicode and empty strings
keep the original decoding paths. The current main parser is unchanged.

Applied to the ec35 source, the isolated candidate passes 625 core tests on each
of JS, Wasm GC and Wasm, warning-free all-target checking, 2,542 parser comparisons
and 117 exact complete-output comparisons. Native execution and independent
candidate acceptance are still pending. The baseline parser is byte-identical
to the earlier b663 preregistration; the additive ec35 integration scope is
recorded before execution.

One new fixed diagnostic used five warmups, 30 full operations, 32-KiB heap
sampling including collected objects, and 500-us CPU sampling. Sampled allocation
ratios were 0.903909 for reduction-512 and 0.983525 for dense-rt-192. These are
statistical diagnostics, not formal speed, P95 or peak-memory acceptance.
No unchanged-code measurement was repeated to obtain a favorable result.

The original preparation failure and later missing output-directory failure are
retained. The latter happened while persisting the parser receipt after all
three core targets passed. Creating that empty output directory allowed only
the parser comparisons and previously unexecuted complete-output comparisons
to continue; source and expectations were unchanged.

Original profiles and failure logs remain in the ignored local experiment.
Public files explicitly marked as derived redact local paths and bind both
their original and derived hashes. They are not described as original bytes.
Actual isolated modules and source hashes are retained. The next gates are
independent review, regression limits and formal performance before promotion.
