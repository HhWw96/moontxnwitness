# Full capture capacity v2: original experiment evidence

Experimental source: `6935d180b078d00386225d50314a964cb2ab6a0a`; opt-in `full-capture-cost-capacity/v2`. This is an experimental branch, not a published v25 performance result. Each profile was dispatched once to its own hosted VM. A/B/C comparisons pair batches within that VM; absolute throughput is not compared across VMs.

Both workflows completed all 36 planned cells. The unchanged protocol uses 15 s warmup, 60 s issue, 30 s drain, ABC/BCA/CAB orders and one shared observer per cell. Workflow success and original cell `status:passed` mean protocol completion, not performance acceptance. No target passed. The earlier formal budget/test-race failures remain preserved separately.

| profile | workload | B/A TPS | C/B TPS | C/A TPS | B/A P95 | C/B P95 | C/A P95 | eligible |
|---|---|---:|---:|---:|---:|---:|---:|---|
| column | serial | 0.824869 | 0.268847 | 0.221763 | 1.233033 | 3.014948 | 3.717529 | true |
| column | parallel | 0.794059 | 0.141011 | 0.111971 | 1.246573 | 5.754982 | 7.174003 | true |
| column | hot | 0.849392 | 0.203707 | 0.173027 | 1.175890 | 3.508435 | 4.125536 | true |
| column | crud | 0.798351 | 0.156750 | 0.125141 | 1.255726 | 4.907058 | 6.161921 | false |
| sidecar | serial | 0.814491 | 0.276835 | 0.225480 | 1.261562 | 3.024099 | 3.815088 | true |
| sidecar | parallel | 0.783531 | 0.141677 | 0.111008 | 1.264580 | 5.797612 | 7.331542 | true |
| sidecar | hot | 0.853484 | 0.206045 | 0.175857 | 1.169758 | 3.503718 | 4.098502 | true |
| sidecar | crud | 0.823487 | 0.155550 | 0.128093 | 1.213799 | 5.048746 | 6.128161 | false |

Targets: end-to-end committed throughput C/A >=0.90; all-attempt P95 C/A <=1.15. Ratios aggregate the three paired batches by geometric mean. CRUD ratios are descriptive only: all nine CRUD cells per profile are ineligible because measured and warmup requests returned SQLSTATE 23505 (database unique-key conflicts, not timeouts). No requests or expectations were changed to eliminate those failures.

B/A describes adding provenance; C/B describes adding collection/persistence to that provenance-enabled baseline. Their measured ratios help localize cost but do not establish CPU/IO causality. A separate profile is needed for causal diagnosis. No performance improvement is claimed.

All 24 C cells report sealed source/lifecycle storage, no storage gap or capture-budget exhaustion. C persistence tails are included in end-to-end throughput: column 7.537056 to9.251595 s; sidecar 7.564883 to9.905132 s. These are producer receipt statements: complete raw logs were not downloaded or independently replayed locally. Every cell keeps sourceSemanticsCertified:false; diagnostic capture does not prove complete model/ORM coverage.

## Verified scope and limits

Selected original outer members were read by bounded HTTPS Range with immutable ETag and strict Content-Range, then checked against ZIP CRC. All 72 nested receipt/manifest pairs passed CRC and SHA binding to the original outer summary. The 21 small source files match sourceBindings in every cell. Registered and measured plan bytes match. Original receipts preserve SQLSTATE, qualification, costs, storage and tails; summary.json recomputes comparisons from those exact bytes.

Complete original artifacts total692,626,333 bytes. They were NOT downloaded or fully hashed locally: wholeArtifactDigestVerifiedLocally:false; wholeCellArchiveShasVerifiedLocally:false. GitHub digests in original/artifact-metadata.json are declared metadata. Exact IDs, digests, expiry and run URLs remain there. Remote retention is finite. This compact package is selected metadata, not every request, raw SQL or capture stream; raw logs remain in original remote cell archives.

Extract into a new directory and run `python verify.py`. This checks manifested bytes, selected outer CRC/SHA, nested receipt/manifest/outer-summary bindings, 72 configurations, source hashes and recomputed ratios. It performs no database execution, performance rerun or network download. The partial source snapshot is for inspection, not full source-build reproduction.

Original readable files are unchanged. Private host homes, credentials and signed URLs are absent; public GitHub runner paths can occur in original CI metadata. No Git ancestry or credential responses are included.
