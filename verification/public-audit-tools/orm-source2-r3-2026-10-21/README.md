# Independent ORM r3 downloaded-runtime audit candidate

This is a separate fixed profile. It does not modify or lower the earlier563/public-786 acceptance profile. Its24 cases and expected outcomes were frozen in `contract-v1.json` before independent runtime execution. No local Node/MoonBit/database/performance run has occurred.

## Target

- Commit `ca4a81d4eddfb4d3c4f92cb0bcac86ef05320a10`, run39588309646/job119182636633.
- Actual artifact12340977721,225908bytes, SHA256 `a6afd8bacf5e1504f8e3fc3b7aabab288550962344c2af912995e3b5ea432a85`.
- Actual module1573469bytes, SHA256 `3b536b3ba28d912d04fe1ef6225c187bc4aca8dae2cf557d9e50a134a3c8945d`.
- Frozen original raw input hashes3ee5a826…/88cbaaee…; candidate manifestda4d4d06…; source baselineb663…/isolated overlaya036….

The original four-target616 and74 author checks are checked only as pipeline prerequisites. Independent signing comes from the new driver, which never imports the author check-source2.mjs and independently reconstructs SQL/source pointers, facts, native wire images, savepoint revocation and predecessor-ledger closure from the frozen raw inputs before invoking the actual module.

The24 registered cases include four component-local positive probes: original raw, pretty-printed trace, exact8MiB trace input and exact128KiB source-record input. Twenty negative cases cover one byte over each limit, scope/ACK uncertainty, non-schema2 envelopes, a bad seal, and semantic/raw/query/ledger mutations whose JSONL seal is deliberately recomputed. Complete input and output hashes are retained. A failing case writes the exact failed envelope and report; no rerun or expected-value edit is performed.

## Remote execution

Ubuntu24.04, Python3.12+, **Node24.13.0**. Publish the five executable-input files together: `audit.py`, `runtime.mjs`, `transport.py`, `profile.json`, `contract-v1.json`. Pin their manifest hashes in the manual workflow. The transport is a byte-identical copy of the already reviewed bounded read-only transport; no local personal-account auth mode is replaced.

Only the fetch step receives `GITHUB_TOKEN`, with permissions `contents: read` and `actions: read`:

```sh
python -B "$AUDIT_TOOL/audit.py" --phase fetch --work "$RUNNER_TEMP/orm-r3-independent"
```

In a **separate step without token/secret environment variables**, run:

```sh
python -B "$AUDIT_TOOL/audit.py" --phase audit --work "$RUNNER_TEMP/orm-r3-independent"
```

The work directory must be new and absolute. Both modes enforce `GITHUB_ACTIONS=true` and exact repository `HhWw96/moontxnwitness`; audit refuses a nonempty GITHUB_TOKEN. Children receive a sanitized environment. The fetch downloads only the actual225KB module artifact, fixed candidate manifest and two original raw inputs from the exact commit. It verifies GitHub artifact size/digest, actual module SHA, fixed input SHA and Git blob identity. No product checkout/dist/cache, build, database or benchmark is used.

Successful fetch explicitly leaves runtime checks not-executed. Audit binds all source/input/runtime metadata again, invokes the new independent driver in the fresh directory with bounded stdout/stderr and a240s timeout, then saves `independent-audit.json`. A failed original prerequisite, process or case remains failed/incomplete; first raw evidence and failed envelopes remain in the new work directory.

Upload with `if: always()`:

```text
${runner.temp}/orm-r3-independent/*.json
${runner.temp}/orm-r3-independent/*.stdout
${runner.temp}/orm-r3-independent/*.stderr
${runner.temp}/orm-r3-independent/artifact/**
${runner.temp}/orm-r3-independent/inputs/**
${runner.temp}/orm-r3-independent/result/**
```

This includes actual runtime bytes, original stage logs and original74 receipt, the two fixed raw inputs, all independent results and exact first failed envelopes if any. Exclude the downloaded ZIP duplicate. Transport records no token or signed URL. Public inputs use only controlled fixture identities and example.invalid addresses.

## Interpretation

The required positive result is a **local component source profile**:121control queries/21statement batches/8observed effects/7committed surviving ledger entries/1savepoint-reverted effect/1explicitJsonb parameter. All global analysisCoverageAccepted flags must remain false, history null and complete-trace verifiedStatements/Facts/Profiles empty. Unknown outcomes, unsupported scope and other original gaps do not become complete capture facts. This is not database authentication, full ORM application integration, general SQL acceptance, stable release or human/organizer acceptance.

The5 local tests cover only Python syntax, fixed profile/contract declarations, credential refusal and static driver independence. JavaScript syntax and actual24 runtime cases remain unexecuted until the separate Linux workflow. Original r1/r2 failures and their expected raw inputs are untouched.
