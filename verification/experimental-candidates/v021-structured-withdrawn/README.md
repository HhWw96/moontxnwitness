# Withdrawn structured v3 candidate

Both formal runs failed the unchanged tail-latency control policy. The candidate
is preserved for reproducibility and is **not active in the stable v0.2.1 default**.
This archive retains its complete fingerprinted inputs, 657 MoonBit core tests,
compiled runtime and pinned public20 benchmark inputs. No failed result is turned
into a passing stable performance claim. The candidate engine string was 0.2.1
before public release; identify it by candidateId and complete source/core SHA,
and use its own frozen runtime when reproducing intermediate invalid reports.

Extract candidate-2-source-runtime.zip into a new directory. Its dist/sdk.mjs is
standalone. The performance tool requires Node.js; rebuilding/core testing also
requires the recorded external MoonBit toolchain. The historical location-table
generator additionally needs the original release Git tags. Do not overwrite a
stable installation with this experimental snapshot. Formal receipts and the two
independent review bundles remain in the repository at their original paths.
