# Actual controlled two-epoch execution and independent review

[Run 39620317399](https://github.com/HhWw96/moontxnwitness/actions/runs/39620317399)
used immutable source `bee9e3dbdb6e9306a249fddfcd462a48a8ebc08b` and passed
47 checks plus four actual PostgreSQL 18.6 scenarios. The original 939,621-byte
artifact has SHA-256
`36f860426993b416ddc62f45a57ebd892d69d7799991818b6a33b7f890399232`.
It preserves all 740 original members, including actual sources, journal/source
bytes, reference indexes and partial/failed observation records.

A separate AI reviewer passed 2,832 checks with no failures in
`independent/receipt-r3.json`: rehashed all members and 101 immutable Git objects,
checked actual unit outputs, independently reconstructed source chains and
boundary observations, and checked each database case. Equal-value writes have
distinct UUIDs and preserve the final version across epochs. Aborted and
savepoint-reverted writes remain in observations while the actual committed
audit retains only the surviving write. Unsupported SQL preserves the business
result and a gap. Discarding a real COMMIT response retains an unknown boundary
and its guard; it does not demonstrate a real network disconnection.

The first two reviewer receipts remain failed. One compared unspecified tied
catalog row order; the next assumed an empty directory would be uploaded in a
ZIP. The final reader checks the full metadata-row multiset with the actual
contype ordering, and checks the ZIP namespace for absent boundary records.
Candidate code, input observations and expected scenario outcomes were unchanged.
One failed receipt contains a local path: its public derivative and both hashes
are explicitly bound by `independent/public-index.json`; original bytes remain
local. The original audit index refers to those original bytes.

This is independent AI acceptance of the stated controlled evidence obligations.
No database or candidate tests were reexecuted during the read-only audit.
SQL-core proof, analysis source closure, live pruning, crash durability, formal
performance, stable publication, human adoption and organizer acceptance remain
outside this result. R2 initialization hardening has its own separate evidence.
