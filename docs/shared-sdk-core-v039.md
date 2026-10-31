# Shared SDK core

The default SDK binds configured-session, source-component, SQL candidate and actual-fetch diagnostics to the main `core.mjs` instance. Public functions remain synchronous and use the existing input, option, report and capsule contracts. The main bridge forwards 13 existing JSON/primitive methods; no parser, analysis, model, budget, counter or source-authority rule is changed.

The standalone `configured-v4.mjs`, SQL candidate/fetch entries, four independent compiled files, explicit `--runtime` tools and their build scripts remain available. SQL host validation is defined once in two core-free factories and used by both routes. Missing functions fail explicitly; unsupported mixed SDK/core installations are not silently accepted.

The expected default SDK graph has 41 static modules and two compiled roots (`core.mjs`, `capture-core.mjs`). The four standalone configured runtime files remain packaged and SHA-bound. Actual Node syntax inventory must verify the graph; file count is not a measured memory saving. The main binary grows when retaining additional entry points, so delivered archive size may increase.

Runtime conformance compares original primitive String/Bool/Int32 responses against every genuine standalone slot, then compares full SDK responses. All 13 forwarders must actually execute. The existing configured 14-check consumer also executes shared and standalone session routes, preserves its genuine standalone SHA and adds explicit main/standalone dispatch hashes. Package and release checks validate both roles rather than relabeling the previous receipt. Source facts, authenticated provenance, complete writer windows and isolation-ready claims remain disabled where previously disabled.

Validation commands after a real JS build:

```text
node scripts/shared-core-host-test.mjs
node scripts/configured-session-integration-test.mjs
node scripts/shared-core-runtime-test.mjs
node scripts/native-report-sdk-test.mjs dist NEW_NATIVE_RECEIPT.json
```

The portable conformance check needs Node only and the included fixtures; it does not require MoonBit sources, a database or SQLGlot. Full source validation additionally retains the independent SQLGlot corpus cross-check and existing model/relation/capsule suites.

This is a separate v0.3.9 candidate. No v0.3.9 performance improvement is claimed before functional verification and its own paired CI measurement. Earlier v0.3.8 and experimental-native measurements keep their original source/runtime identities and scope.

The local source checkpoint passed 18 core-free host checks and seven receipt-contract tests. Its attempted JS build stopped at the resource guard before starting a compiler: C had 970,399,744 bytes free against a 1 GiB minimum. Consequently the 41-module inventory, 13-forwarder runtime parity, generated bridge interface and existing runtime suites still require execution against the new CI build. An older v0.3.8 runtime does not satisfy those checks.
