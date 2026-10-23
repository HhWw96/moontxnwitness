# First selected test diagnosis

The second JS source check passed. The first combined category/model run passed
36/37; all 19 prior category tests passed. One new list abort/intermediate test
panicked while accessing `rules` because classification had returned a diagnostic.

Read-only diagnosis found two wrong field references in the new model module:
existing `list_v3_finding` writes `readSeq`, while the new classifier required
`seq`. The source now uses the actual `readSeq` field in both places. No test
expected status, applicability assertion, existing parser or anomaly rule was
changed. Original first-test logs remain unchanged. This fix has not been
recompiled or rerun; the Moon token has already been returned to root.
