# Capability discovery

After building the runtime, run:

```powershell
node dist/moontxnwitness.mjs capabilities
node dist/moontxnwitness.mjs capabilities --format json
```

The default format is `text`. `--format json` returns `moontxnwitness-capabilities/v1`: the loaded core version, actual SDK function exports, availability of the two JavaScript native model-report exports, runtime model names, and the complete [feature declaration](feature-matrix-v4.json) with its SHA-256 digest. Declared SDK API availability is checked against loaded functions. The command does not invoke a history checker or turn declaration fields into a model verdict.

The build copies `capabilities.mjs` and the exact declaration to `dist/`, beside the CLI. Both files are bound by `runtimeAssetSha256` in `dist/build-manifest.json`; the portable package includes them. Asset lookup is relative to the module and works from another working directory without the source checkout. The digest identifies bytes; it does not authenticate a publisher or captured observations.

General SQL/ORM instrumentation and configured-session diagnosis report executed operations and coverage gaps. Model analysis separately requires the selected source profile, original observations, confirmed outcomes, a source-closed window and model-specific facts. Missing facts and incomplete budgets retain `unknown`. Fourteen selectable definitions do not establish arbitrary SQL support or complete Elle equivalence. Native object-report availability changes report transport only. See the [functional scope](feature-matrix-v4.md) and [current roadmap](ROADMAP.md).

Discovery reads local declaration bytes and loaded exports. It does not connect to a database, access the network, execute migrations, write files or reexecute the referenced comparison evidence. Exit code `0` means discovery succeeded. Invalid, duplicate, missing or unsupported options, positional inputs and unreadable/invalid declaration assets produce exit code `2`, a diagnostic on stderr and no report on stdout. This command supports only `--format json|text`; use shell redirection if a saved copy is needed.

`node scripts/capabilities-test.mjs` checks strict CLI parsing, loaded-export/version agreement, declaration bytes and manifest digests, both output formats, and execution from a relocated portable runtime. This test is included after the build in `npm test`; it does not execute a database workload or establish model equivalence.

The native model output exports return freshly allocated plain objects for the same core computations. They retain the original 32 MiB pretty-report UTF-8 limit and 64-level JSON container limit; inability to use that transport requests the original text route. Capsule creation still binds the original pretty report text, and report verification still parses untrusted input and recomputes under independent caller options. The maintained `scripts/native-model-report-test.mjs` checks complete field/counter equality, fallback when an export is absent or unavailable, capsule text, tamper rejection and source nesting that becomes deeper inside a report.
