# Same-statement source projection: proposed contract

This is a design boundary for the next driver/source step. It is not enabled by the independent SQL grammar checker. No SQL transformation, migration or complete-source claim is implemented here.

## Facts a diagnostic adapter can already establish

An original SQL/parameter candidate can be independently parsed by MoonBit. Existing local instrumentation can record actual execution, commit/rollback responses and fetch deliveries without consuming a business result early. Neither result business-value equality nor configuration alone identifies the version a read observed.

If the original SELECT returns no version identity, a later query of a version column or sidecar is not evidence of the earlier read's source. Concurrent commits can change that second query. This path must retain `read_version_unproven`; an AST match cannot remove it.

An ordinary `RETURNING` result gives affected writes, not a complete read of the WHERE predicate. Zero affected rows do not become an empty SELECT. The generic UUID/cast gap remains separate from the fixed FastAPI Users profile.

## First proof-capable subpath: version already in the original result

A future explicit source policy can identify a pre-existing or explicitly installed stored version column. If the original business SELECT already returns it, the same native result supplies business values and version identity. No SQL rewrite or later SELECT is needed.

The source policy must bind table/column identity, version type/encoding, actual native result position and installed-source proof. It cannot simply label a business value as a version. Unique historical identities and a new identity on every effective write require a verified source mechanism, initialized state, complete writer window and rollback-aware effect ledger.

This subpath still has an explicit negative-read gap when the original empty result carries no uniquely justified absence/tombstone source. It can verify individual delivered positive rows; it cannot declare all range/negative paths complete.

## Candidate hidden-column subpath

For a controlled explicit full-source mode, a narrow transformation could append a stored same-row managed version column:

```text
Original: SELECT business_columns FROM configured_table alias WHERE P ORDER BY O
Observed: SELECT business_columns, alias.managed_version AS hidden_alias
          FROM configured_table alias WHERE P ORDER BY O
```

Conditions before execution:

- Original SQL is the independently verified single-table subset. No DISTINCT, joins, grouping, arbitrary functions, LIMIT/OFFSET, row locking, named/server cursors, binary/custom row decoding or unsupported semantics.
- The managed version is a stored, side-effect-free column. Catalog/source proof binds the actual relation OID, business column order/types/collations, native version type, permissions, functions/triggers, source ownership and DDL epoch. Unknown rules, RLS, inheritance/partition effects and additional unverified writers remain gaps.
- Original business projections are explicit direct columns. Original `*` cannot silently include a newly installed version column. Star behavior needs its own schema/physical-layout contract or remains diagnostic.
- Reading the additional column is explicitly permitted before business begins. An original success must not be changed into a permissions failure by trying a rewrite and recovering later; no implicit retry/savepoint is introduced.
- PostgreSQL encoding/string-literal and C-collation assumptions are proved for that source window. A configuration name is not proof.

For this narrow pure projection, the transformation changes the select list only. It must retain the same original FROM/WHERE/ORDER structure, parameter references/order, snapshot command and business row-lock behavior. It adds a native result column; performance/timing may change and requires later measurement. It must not claim universal behavioral equivalence outside the stated conditions.

MoonBit must independently recognize both SQL texts and prove the observed text equals precisely the allowed transformation, including the configured version-column identity and hidden index. It must not trust Python ASTs, generated SQL text, a transformation name or a claimed `verified` flag.

No business SQL is rewritten in diagnostic mode. An unknown/failed recognition records a gap and executes the original business operation unchanged.

## Native result and fetch preservation

The proposed wrapper would expose exactly the business prefix of each native row, with original column names, OIDs, type modifiers, formats and table/column identities. Status message, row count, row number, result state, exceptions and connection/transaction lifecycle must match the original operation. This needs explicit sync/async/pool and result API tests, not just tuple slicing.

The raw execute response may make a buffered PGresult available, but it does not prove business delivery. No fetch is performed during execution or a hook. Only an actual business `fetchone`, `fetchmany`, `fetchall` or iterator advance may create a delivery observation. Row indices must bind both returned business cells and hidden version cell in the same native result. An unread/replaced/closed result leaves a gap. A complete predicate read requires its actual complete-fetch boundary; a partially consumed result is not complete.

A future independent source checker must match original SQL, parameters, allowed transformed SQL, native result metadata/cells, delivery method/order/indices and normalized row facts. Missing native evidence cannot be replaced by a later query.

## Writes and conditional outcomes

The simplest first write subpath uses an original RETURNING list that already contains a verified final version source. Adding RETURNING to a command with no original result changes its DBAPI result state; this is not covered by the SELECT hidden-column contract. A separately verified command-result facade and exact exception/rowcount behavior would be required.

A source mechanism must prove actual effects, not merely attempted writes. Installed triggers must bind final row versions and predecessor facts, avoid hidden business mutations, retain tombstones and roll back atomically with business writes/savepoints. PostgreSQL RC waits/rechecks and zero-row conditional writes require separate condition/source evidence. The WHERE AST and RETURNING collection do not supply that missing read evidence.

## Sidecar alternative and remaining gaps

A same-statement sidecar join could avoid adding a business column, but it introduces another relation, join/cardinality, locking and metadata conditions. It would require unique sidecar key/type constraints, atomic business/sidecar effects visible under the same snapshot, ownership/catalog proof and independent qualification of every original column.

A positive-row LEFT JOIN does not deliver source metadata when the original business result is empty. Sentinel/UNION/aggregate approaches also change row/result metadata or buffering and need new transformation/facade contracts. None is silently accepted by the initial grammar checker or hidden-column proposal.

The next safe runnable step is therefore actual fetch/native-result binding with explicit missing-version gaps, followed by the direct-version-result subpath when a valid source policy exists. Wider hidden projection, empty results, arbitrary write commands, general sidecars and canonical UUID primary-key support remain separately reviewable work.
