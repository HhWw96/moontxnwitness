# Verify a point window in a downstream repository

1. Copy `point-window.yml` to `.github/workflows/point-window.yml` in the
   consuming repository.
2. Supply the capture capsule and the independent configuration and policy at
   the three `ci/` paths in the workflow. To try the passing path, take
   `config.json`, `policy.json` and the decompressed `ordered.json.gz` from
   `examples/point-window-replay-data/` in the pinned portable archive.
3. Run the workflow. The job passes for a complete compatible result and
   fails for a verified refutation or incomplete evidence. The packaged
   `before.json.gz` and `retry.json.gz` exercise the two failing paths.

When upgrading, review the Action commit, portable release and SHA-256 pin
together. Keep the capture policy and analysis budget under your own CI's
control.

The portable archive also contains the MoonBit registry consumer. With
`moon` on PATH, run the following from the extracted v0.6.4 archive.

```sh
node scripts/verify-point-window-moon-consumer.mjs --runtime dist --module-version 0.6.4 --output new-consumer
```

The command creates a project, installs the requested Mooncakes version and
compares the normalized histories and full verdicts with the downloaded
JavaScript SDK. The repository's clean consumer workflow runs six gate cases
on Windows and Linux, and retains stage timings and both package sizes.
