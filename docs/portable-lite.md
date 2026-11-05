# Lightweight portable bundle

Build the current runtime, then create the ZIP in a new directory.

```text
npm run build
python -B scripts/package_lite.py artifacts/lite-build
```

Unzip and run with Node.js. No database is needed for these examples.

```text
node dist/moontxnwitness.mjs --version
node examples/models-v4-roundtrip.mjs
node examples/relation-predicate-categories.mjs
```

The bundle includes the current SDK and CLI, their compiled runtimes, licenses,
and minimal examples. It supports current evidence creation and replay. Use
the full portable bundle when replay needs a historical runtime or when running
the included database and compatibility suites. The build receipt records the
archive digest and the checks executed after extracting it to a new directory.
