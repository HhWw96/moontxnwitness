# First configured list/relation driver source evidence

Ten cases executed original SQL through the newly installed synchronous driver
factory in a new owned PostgreSQL18.6 cluster. Its actual execution receipt and
all source envelopes, original SQL/native results, deliveries, control queries,
lifecycle journals and journal indexes are retained in `database/`. The owned
cluster was stopped. Private connection/password files and database data are
excluded from this selection. No formal performance experiment occurred.

`actual-first/` preserves the original conservative refusal caused by a verifier
field-name mismatch; `actual-source-fields-fixed/` retains the subsequent list
refusal of PostgreSQL-generated internal FK hooks. Neither failure was changed
to a pass. Their exact compiled runtimes and source fingerprints remain present.
`actual-internal-fk-fixed/` contains the final compiled original-input check:
seven complete supported projections (five consistent, two actual Repeatable
Read write-skew violations), three deliberately incomplete cases refused, and
agreement with both existing separately implemented Python model interpreters.
The original database inputs were not rerun or rewritten between these checks.

Sixteen new MoonBit contract tests and twenty-two Python profile/SQL contract
tests passed. Original compiler/test syntax failures and before-fix source
snapshots are retained. These are author development results; an independent
reviewer has not yet accepted this source mapper.

`original-producer/` preserves all 32 exact files used at runtime or in the
pre-run source inventory except the earlier bytes of `test_model_profile.py`,
which was not imported by the database producer and was subsequently extended
from 20 to 22 tests. Its original SHA256 is still retained in the unchanged
database receipt; no replacement bytes are claimed to match it. Every original
runtime source file matches its pre-run digest. The manifest states this
nonruntime snapshot limitation explicitly.
