# Preserve typed Elle results and returned raw evidence

This development slice fixes two result-transport defects without changing any
of the 2,000 frozen histories or computing new consistency conclusions.

The original boolean or `:unknown` judgement is retained independently of the
cycle-search-timeout flag. A proven false result remains false even when another
search timed out. Unexpected result types remain execution errors. Raw EDN is
saved before summary generation. Preparation failures, checker exceptions,
returned-result storage failures and summary failures have separate stages;
they preserve whether the checker was invoked, returned and had its raw result
retained. Failure to store a diagnostic does not overwrite the primary error.

The typed helper passed five tests with 16 assertions. The next transport
revision passed six tests with 27 assertions using explicitly synthetic callback
results and real small-file storage failures. Both used the actual Clojure
1.12.6 runtime on Java 25.0.1 with a 128 MiB heap cap. Three runtime JARs were
downloaded once from Maven Central and rehashed against the original fixed Elle
execution's dependency metadata. They are not redistributed here.

The full wrapper's eight forms were read by the actual Clojure reader without
evaluation. Neither the complete wrapper nor any actual Elle checker was
compiled/executed in these tests. This is not the fixed Java 21 integration gate
or the 2,000-input comparison. The remote process-group, output/time budgets,
missing-ID accounting, dependency locks and full SDK/evidence comparison remain
required before that run.

The independently rejected previous wrapper remains under `previous-r2`; it
computed its summary before preserving the raw result. Its pure helper pass is
preserved, and is not promoted into a full wrapper acceptance. The current
revision and first execution records are under `current-r3`. One extra closing
delimiter in a draft test was caught before freezing/running tests; the original
draft and static-failure record are retained. Any local-path redaction is a
marked derivative with both original and public hashes in `publication-index.json`.
Synthetic evidence is never labelled as an actual upstream result.

Independent read-only review receipts are retained separately. They do not
reexecute JVM, change frozen inputs or sign six-model parity, performance or a
stable release. Archived runners retain their original artifacts layout;
restore that layout before reexecuting them.
