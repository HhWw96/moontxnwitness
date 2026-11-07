# Configured-window SDK baseline

The baseline uses v0.4.1 source commit
`b7008ce2eb404bd85eedc3bd5e0b5b9bfdadcb48`, MoonBit
`0.10.16+b1a0e846e` and Node.js `24.13.0` on Windows. It measures complete
`verifyConfiguredWriterWindowV4` and `analyzeConfiguredPointWindowV4` calls
with original input texts already in memory. Filesystem input loading is outside
the timed call; parsing, source verification and complete report production are
inside it. No output fields or source evidence are removed.

| Input | Median ms | P95 ms | Peak RSS MiB | Output bytes |
| --- | ---: | ---: | ---: | ---: |
| Complete writer delta | 207.191 | 231.059 | 123.46 | 1,988 |
| Incomplete writer delta | 207.864 | 225.625 | 123.30 | 2,563 |
| Repeatable Read write skew | 109.274 | 119.321 | 100.08 | 804,320 |
| Ordered Serializable | 92.514 | 109.686 | 87.80 | 558,834 |

Each timing case has five warmups and thirty samples in each of three fresh
processes. RSS comes from three additional fresh single-call processes, rather
than the warmed timing loop. SDK cold import and first-call times are retained
separately. These memory results use this protocol and should be compared with
future measurements using the same protocol. This is a baseline, not an
optimization comparison or an A/B/C database capture-cost result.

The separate `MoonTxnWitness-v0.4.1-configured-baseline.zip` attachment contains
the original controlled observations, raw samples, runtime/input digests and
reproduction scripts. It was extracted beside an unmodified lightweight runtime
in a new directory; all static runtime digests and a complete call's output
digest matched. The reproduction plan uses portable paths; the measured plan
digest remains recorded independently.

From the extracted baseline directory, with the matching lightweight runtime
beside it:

```text
node --experimental-vm-modules scripts/bench/configured-window-baseline.mjs plan.json new-measurement
```

The VM flag is used only by setup to inventory static dependencies. Timed and
memory child processes import the ordinary SDK. A different runtime, altered
input, changed output, unexpected status or an existing output directory stops
the run. Preserve the first failure before changing the implementation.
