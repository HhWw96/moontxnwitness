# First configured base-user profile evidence

This is a producer development slice, not a complete application acceptance or
performance pass. `manifest.json` binds the exact producer sources, original raw
packets and the retained first independent failures.

Two actual PostgreSQL 18.6 runs used psycopg 3.3.6, SQLAlchemy 2.0.55 and the
unmodified FastAPI Users SQLAlchemy adapter at fixed commit
`6397ace506d829a2ee12786da5d724c3f4c6b634`. Each executed six real base-user checks:
existing/absent get, create/commit/refresh, update/commit/refresh, updated get and
delete/negative get. Both owned clusters were stopped; source hashes before and
after each actual run agree. Their source packages contain no handwritten
history and the producer explicitly declines to grant analysis coverage.

The first public one-click wrapper failed on a startup `NameError` before any
database action. Its exact failed script and a receipt copied from the original
tool output remain under `wrapper-first-failure`; that receipt is not presented
as a wrapper-generated database execution receipt. The corrected one-click
run's actual source and native receipt are `producer-second`.

The first independent adversarial review of the initial MoonBit promotion
candidate failed: it incorrectly promoted several resealed lifecycle/attachment
and index mutations to complete coverage. The original failed receipts and
reproducible mutation scripts are in `independent-first-failures`. No original
trace gap, source record or failed result has been removed. These failures must
be repaired and independently rerun before complete promotion is released.
The author's first unmodified-packet promotion success does not supersede this
failed review. This evidence does not claim that arbitrary tables, direct
factories, zero-row conditional writes, email functions or OAuth joins have
complete model coverage.

`producer-first` and `producer-second` preserve exact original text bytes for
the envelope, trace, lifecycle, source journal and index. Original event segment
payloads are also retained. The promotion envelope itself passes only the index
text and therefore does not constitute an independent proof of segment storage
integrity. Password files, connection files, database data directories, virtual
environments and package caches are excluded. The test business data is newly
generated fixture data.

The 11/13/18-test development logs are retained in order; the final expanded
18-case unit suite passed. Those fake-driver checks do not replace either the
actual PostgreSQL runs or independent core review. `upstream-LICENSE` is the
original upstream license. The dependency version lock records the actual
isolated environment; transitive packages came from its configured Tsinghua
PyPI mirror and are not called official PyPI downloads.
