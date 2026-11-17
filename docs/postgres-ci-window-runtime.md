# Source-bound PostgreSQL CI window runtimes

The PostgreSQL evidence importer checks the source commit, MoonBit source digest,
compiler, executed input inventory, original database packet and actual compiled
bytes. A Windows consumer can import a matching Linux database run without
asserting that their generated JavaScript files are byte-identical.

The recorded `ff61f96a8` Windows failure isolated exactly two additional compiled
outputs: `sql-projection-v2-core.mjs` and
`structured-window-verification-core.mjs`. All other executable inputs outside
the already bound platform outputs matched. The original failure and archive
digests remain retained; the small regression fixture records a projection of
those observed facts, rather than replacing the original run.

## Independent two-output binding

The `moontxnwitness-window-compiled-slots/v1` binding checks:

1. The actual build script declares exactly the two supported output-to-bridge
   mappings and uses the checked copy loop.
2. The build declaration and each bridge's `moon.pkg` and `bridge.mbt` have the
   same executed-input digests in both runs. The complete MoonBit source digest
   and compiler are checked separately.
3. Both build manifests have the exact existing window/profile inventories.
   Wrapper digests still match across platforms; wrappers are not exceptions.
4. The current outputs are read from the consumer's filesystem. The PostgreSQL
   outputs are read from the original downloaded packet. Their bytes match their
   respective manifests and executed-input inventories.
5. The imported reproduction retains the actual PostgreSQL outputs and manifest.
   Installation and later reproduction validation recheck these retained bytes.

Only these two independently bound compiled outputs receive the additional
platform allowance. The original four configured-core slots and algorithm keep
their existing contract. Missing outputs, changed bridges, an unused mapping,
rehashed wrappers, incomplete inventories and changed retained bytes are errors.
There is no general exclusion for `dist/` or other executable files.

## Checks

```text
python -B -m unittest discover -s scripts -p 'test_postgres_ci_*.py' -v
```

The new tests preserve the original import/reproduction tests and add platform
differences, source/copy-loop tampering, missing raw output, inventory and retained
reproduction checks. CI uploads the actual complete `dist/` alongside database
observations. A successful import establishes this source/runtime/evidence
binding; model judgments still require their independent semantic checks.
