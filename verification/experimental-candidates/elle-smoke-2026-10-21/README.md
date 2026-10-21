# Actual fixed Elle smoke candidate — not executed

This draft calls upstream `elle.rw-register/check` and
`elle.list-append/check` from commit
`4e359e597c52938b0afebb8bc42273914d68a424`. It does not reproduce their rules in
our own code and does not treat a graph-kernel oracle as an Elle execution.
The contract was frozen before the adapter and checker runner existed.

Fifteen raw cases are frozen: eight eligible (two positive, four negative and
two explicitly expected edgeless-graph unknowns), five outside the common
range, and two malformed inputs. All original expectations are pending actual
execution. No local adapter tests, Java/Clojure/Node, compiler or model runtime
has run. Only bounded official source downloads and static file authoring have
occurred. The earlier network failures remain recorded separately.

First shared range: all committed, no SQL or savepoints, one write per register
key, empty initial lists. Initial register identities are renamed to per-key
Elle nil without inventing an initialization transaction. List append IDs remain
distinct even when business values repeat; payload source mismatches are not
silently erased. Unsupported observations and missing source facts do not get
fed to the checker. The raw-to-invoke/ok correspondence is retained separately.

Explicit `[:serializable]` options are necessary: default strict serializability
automatically adds real-time graphs even when `:additional-graphs` is empty.
The runner checks that no such graph was selected and disables all optional
register version-order inference. It never supplies `:transaction-order`.
That upstream option is a total transaction order, not arbitrary per-key facts.

## Exact remote-only execution

Use a new task-owned Linux scratch, JDK21 and a new `LEIN_HOME`. Restore this
draft at its original repository path; do not overlay production src. Resolve
the absolute draft/output paths before entering the upstream checkout.

```text
python -B <draft>/prepare.py --input <draft>/smoke-inputs-v1.json --output <new-output>/prepared
git clone --filter=blob:none --no-checkout https://github.com/jepsen-io/elle <new-output>/elle
git -C <new-output>/elle fetch --depth 1 origin 4e359e597c52938b0afebb8bc42273914d68a424
git -C <new-output>/elle checkout --detach 4e359e597c52938b0afebb8bc42273914d68a424
git -C <new-output>/elle rev-parse HEAD
```

Before executing it, verify upstream `project.clj` SHA256
`d4608919c02b20de53cb017467e54c4b8267c4f146619a612a1a585f42f7c89f`,
LICENSE SHA256 `721c2da257578bace3332b14d8ea06643d7d26753e7ef25a837b4e904edc0bf5`
and the fixed checker/source hashes in `source-pins.json`.
The complete official license is retained under `primary-references/` and must
remain separate from our production Apache license. The project declares the
EPL/GPL-with-classpath alternatives; no legal equivalence is inferred here.

Use the included, unmodified official `primary-references/lein` launcher:
Leiningen2.11.2, commit `795c3a5d68de7a2465582da4184c42d7bd065c76`,
script SHA256 `f83e3de252cb09d301f18f1912acffa807b54c1c9a96772ae63847a946032bd4`.
The launcher pins its standalone JAR SHA256 to
`7d31ae23ae769e927438b0cd55d15a93e7dabab09fd4fc15877979161e108774`.
Do not disable this check or TLS verification. Upstream targets Java21 and
Clojure1.12.6. In the fixed upstream directory, with `LEIN_HOME` pointing to a
new owned directory:

```text
bash <draft>/primary-references/lein version
bash <draft>/primary-references/lein with-profile -dev deps :tree
bash <draft>/primary-references/lein with-profile -dev run -m clojure.main <draft>/elle_smoke.clj <new-output>/prepared/requests.edn <new-output>/elle-result.json <new-output>/elle-raw-results
```

Save every command's real stdout/stderr, exit code and exact runtime versions.
Bound the JVM process to 300 seconds and use a bounded heap. Record all resolved
JAR/POM SHA256 values and the dependency tree. Dependency-download/bootstrap
failures are setup failures, not valid checker outcomes. No transitive runtime
hash has been observed or claimed yet.

From a separately built, fingerprint-bound MoonTxnWitness checkout:

```text
node <draft>/compare-tool.mjs <built-dist>/sdk.mjs <draft>/smoke-inputs-v1.json <new-output>/prepared/adapter-receipt.json <new-output>/elle-result.json <new-output>/comparison-first.json
```

The comparison saves full MoonBit reports, verification and real Elle result
bindings. Raw upstream results stay unmodified as individual EDN files. The two
edgeless unknowns are named coverage differences, not false agreement. The
five excluded and two invalid adapter cases are not counted as checker passes.
All mismatches must remain failures; do not modify inputs or expectations after
seeing results. Do not reuse an output directory or replace a first receipt.

The first smoke is not complete. Only after actual independent acceptance will
the next separately preregistered stage expand to 1000 distinct register and
1000 append histories. It will preserve unknown/outside counts and original
facts. This draft makes no six-model parity, real database or performance claim.
