# RT complete-field writer draft

The standard null-provenance RT edge writes the exact existing JSON field shell in one fragment. From/to IDs use the existing escaped-string cache. The predicate requires the original reason and every nullable field to be null; a custom Edge falls through to the unchanged generic writer. Every edge and all null fields/reason/order remain present. No graph traversal or analysis changes.

Four new semantic tests cover exact complete bytes, Unicode/quote/newline escaping, unusual provenance fields and a custom reason. JS: 402/402; all-target deny-warn check passes. Dense RT fixtures in the complete-output comparison are unchanged byte for byte.

Expected mechanism: fewer JsonText fragments per normal RT edge. No measured speed/RSS conclusion. Minimal eventual measured loads: dense RT 96/192/316, long-cycle full provenance, and the custom-Edge fallback correctness cases.

These are isolated functional drafts on the exact f33c8675 baseline, not transferred into the primary source tree. No benchmark, P95, RSS or database execution was run. A passing byte comparison proves the checked complete outputs and counters match; it does not establish a speed or memory improvement. Native code was checked by --target all but not executed.
