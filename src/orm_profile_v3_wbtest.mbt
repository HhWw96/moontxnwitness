///|
// Synthetic protocol tests; full acceptance must consume original PG18 profile bundles.
fn orm_profile_test_gaps_v3(index~ : Bool = false) -> Array[Json] {
  let gaps = [
    capture_gap(
      "diagnostic_instrumentation_only", "No verified initial/version/predicate mapping; raw observations never grant complete analysis coverage.",
    ),
  ]
  if !index {
    gaps.push(
      capture_gap(
        "source_unsealed", "Journal and explicit source window have not both been sealed.",
      ),
    )
    gaps.push(
      capture_gap(
        "diagnostic_only", "This export is incomplete diagnostic evidence, not a complete analysis input.",
      ),
    )
  }
  gaps
}

///|
fn orm_profile_test_events_v3() -> Array[Json] {
  [
    {
      "seq": 1,
      "time": 0,
      "kind": "snapshot",
      "initial": { "x": "x0" },
      "consistent": true,
    },
    { "seq": 2, "time": 1, "kind": "begin", "tx": "T", "connection": "C" },
    {
      "seq": 3,
      "time": 2,
      "kind": "statement",
      "tx": "T",
      "sql": "SELECT business",
    },
    {
      "seq": 4,
      "time": 3,
      "kind": "rows",
      "tx": "T",
      "statement": 3,
      "rows": [],
      "complete": true,
    },
    { "seq": 5, "time": 4, "kind": "commit_request", "tx": "T" },
    { "seq": 6, "time": 5, "kind": "commit_ok", "tx": "T" },
  ]
}

///|
fn orm_profile_test_fact_v3() -> Json {
  {
    "kind": "read",
    "sourceSeq": 5,
    "statement": 3,
    "rows": 4,
    "tx": "T",
    "data": { "key": "x", "version": "x0", "present": false, "image": null },
  }
}

///|
fn orm_profile_test_index_v3(events : Array[Json]) -> Json {
  {
    "indexSchema": 1,
    "traceSchema": 3,
    "closed": true,
    "sourceClosed": false,
    "eventCount": Json(events.length()),
    "durableSeq": Json(events.length()),
    "lastTime": orm_get(events[events.length() - 1], "time") catch {
      _ => Json::null()
    },
    "activeTransactions": [],
    "commitRequests": [],
    "references": {
      "activeTransactions": [],
      "unreadResults": [],
      "versionSources": [],
    },
    "gaps": Json(orm_profile_test_gaps_v3(index=true)),
    "segments": [
      {
        "firstSeq": 1,
        "lastSeq": Json(events.length()),
        "eventCount": Json(events.length()),
      },
    ],
  }
}

///|
fn orm_profile_test_window_records_v3() -> Array[Json] {
  let records : Array[Json] = [
    {
      "kind": "header",
      "format": "moontxnwitness-instrumentation/v1",
      "diagnosticOnly": true,
      "processMonotonicDomain": "synthetic-process",
    },
    {
      "kind": "profile-window-open",
      "profile": "fastapi-users-sqlalchemy-7.0.0-pg18/1",
      "installationNonce": "nonce",
      "initialCommitSourceSeq": 100,
      "initialSnapshotSourceSeq": 99,
    },
    {
      "kind": "call-start",
      "callId": "execute1",
      "method": "execute",
      "connection": "C",
      "tx": "T",
      "statementSeq": null,
      "journalEventSeqs": { "begin": 2 },
    },
    {
      "kind": "call-end",
      "callId": "execute1",
      "method": "execute",
      "connection": "C",
      "tx": "T",
      "statementSeq": 3,
      "succeeded": true,
      "journalEventSeqs": { "begin": 2 },
    },
    {
      "kind": "call-start",
      "callId": "commit1",
      "method": "commit",
      "connection": "C",
      "tx": "T",
      "statementSeq": null,
      "journalEventSeqs": { "begin": 2 },
    },
    {
      "kind": "commit-response",
      "connection": "C",
      "request": 5,
      "commandTag": "COMMIT",
      "transactionStatus": 0,
    },
    {
      "kind": "call-end",
      "callId": "commit1",
      "method": "commit",
      "connection": "C",
      "tx": "T",
      "statementSeq": null,
      "succeeded": true,
      "nativeCommandTag": "COMMIT",
      "journalEventSeqs": { "begin": 2, "commit_request": 5, "commit_ok": 6 },
    },
    {
      "kind": "profile-window-quiesced",
      "profile": "fastapi-users-sqlalchemy-7.0.0-pg18/1",
      "installationNonce": "nonce",
    },
    {
      "kind": "profile-window-close",
      "profile": "fastapi-users-sqlalchemy-7.0.0-pg18/1",
      "installationNonce": "nonce",
      "finalCommitSourceSeq": 200,
      "finalSnapshotSourceSeq": 199,
      "finalLedgerSourceSeq": 198,
    },
  ]
  for i, raw in records {
    let record = object_fields_unchecked_v3(raw)
    record["seq"] = Json(i + 1)
    if i > 0 {
      record["processMonotonicDomain"] = Json("synthetic-process")
      record["monotonicNs"] = Json((1000 + i).to_string())
    }
  }
  records
}

///|
fn orm_profile_test_window_text_v3(records : Array[Json]) -> String {
  let prefix = StringBuilder()
  for record in records {
    prefix.write_string(record.stringify())
    prefix.write_string("\n")
  }
  let seal : Json = {
    "seq": Json(records.length() + 1),
    "kind": "seal",
    "records": Json(records.length()),
    "prefixSha256": Json(v3_dislock_sha256(prefix.to_string())),
  }
  prefix.write_string(seal.stringify())
  prefix.write_string("\n")
  prefix.to_string()
}

///|
fn orm_profile_test_window_v3() -> OrmProfileWindowV3 raise {
  orm_profile_window_v3(
    orm_profile_test_window_text_v3(orm_profile_test_window_records_v3()),
    Json("nonce"),
  )
}

///|
fn orm_profile_test_transactions_v3() -> Array[Json] {
  [
    {
      "id": "T",
      "connection": "C",
      "status": "committed",
      "beginSeq": 2,
      "endSeq": 6,
    },
  ]
}

///|
test "profile promotion keeps the exact three original diagnostic gaps" {
  let gaps = orm_profile_test_gaps_v3()
  let before = Json(gaps).stringify()
  orm_profile_diagnostic_gaps_v3(gaps)
  assert_eq(Json(gaps).stringify(), before)
}

///|
test "profile promotion refuses additional raw coverage loss" {
  let gaps = orm_profile_test_gaps_v3()
  gaps.push(capture_gap("capture_event_not_retained", "event missing"))
  orm2_expect_reject(() => orm_profile_diagnostic_gaps_v3(gaps))
}

///|
test "profile promotion cannot relabel a raw diagnostic gap" {
  let gaps = orm_profile_test_gaps_v3()
  gaps[0] = capture_gap(
    "diagnostic_instrumentation_only", "different unresolved condition",
  )
  orm2_expect_reject(() => orm_profile_diagnostic_gaps_v3(gaps))
}

///|
test "profile promotion refuses duplicate or missing original boundary gaps" {
  let gaps = orm_profile_test_gaps_v3()
  gaps.push(gaps[0])
  orm2_expect_reject(() => orm_profile_diagnostic_gaps_v3(gaps))
  orm2_expect_reject(() => {
    orm_profile_diagnostic_gaps_v3(orm_profile_test_gaps_v3(index=true))
  })
}

///|
test "profile promotion binds the original closed diagnostic index semantically" {
  let events = orm_profile_test_events_v3()
  let index = orm_profile_test_index_v3(events)
  let before = index.stringify()
  orm_profile_index_v3(object_fields(index, "index"), events)
  assert_eq(index.stringify(), before)
  assert_eq(orm_get(index, "sourceClosed"), Json(false))
}

///|
test "profile promotion refuses unsynchronized or rewritten sourceClosed indexes" {
  for (field, value) in [("closed", Json(false)), ("sourceClosed", Json(true))] {
    let events = orm_profile_test_events_v3()
    let index = object_fields(orm_profile_test_index_v3(events), "index")
    index[field] = value
    orm2_expect_reject(() => orm_profile_index_v3(index, events))
  }
}

///|
test "profile promotion refuses index missing events or unread sources" {
  let events = orm_profile_test_events_v3()
  let index = object_fields(orm_profile_test_index_v3(events), "index")
  index["eventCount"] = Json(5)
  orm2_expect_reject(() => orm_profile_index_v3(index, events))
  index["eventCount"] = Json(6)
  object_fields(orm_get(Json(index), "references"), "refs")["unreadResults"] = Json([
      "result",
    ],
  )
  orm2_expect_reject(() => orm_profile_index_v3(index, events))
}

///|
test "profile promotion refuses descriptor gaps even with a matching tail count" {
  let events = orm_profile_test_events_v3()
  let index = object_fields(orm_profile_test_index_v3(events), "index")
  index["segments"] = Json([{ "firstSeq": 2, "lastSeq": 6, "eventCount": 5 }])
  orm2_expect_reject(() => orm_profile_index_v3(index, events))
}

///|
test "profile promotion validates an original sealed lifecycle window" {
  let window = orm_profile_test_window_v3()
  assert_eq(window.opened, 1)
  assert_eq(window.quiesced, 7)
  assert_eq(window.closed, 8)
}

///|
test "profile promotion rejects an unsealed or wrong-prefix lifecycle" {
  let records = orm_profile_test_window_records_v3()
  orm2_expect_reject(() => {
    ignore(orm_profile_window_v3(Json(records).stringify(), Json("nonce")))
  })
  let text = orm_profile_test_window_text_v3(records)
  let changed = text.replace(old="execute1", new="execute2")
  orm2_expect_reject(() => ignore(orm_profile_window_v3(changed, Json("nonce"))))
}

///|
test "profile promotion rejects wrong initialization nonce or window order" {
  let records = orm_profile_test_window_records_v3()
  orm2_expect_reject(() => {
    ignore(
      orm_profile_window_v3(
        orm_profile_test_window_text_v3(records),
        Json("other"),
      ),
    )
  })
  let a = records[1]
  records[1] = records[7]
  records[7] = a
  for i, record in records {
    object_fields_unchecked_v3(record)["seq"] = Json(i + 1)
  }
  orm2_expect_reject(() => {
    ignore(
      orm_profile_window_v3(
        orm_profile_test_window_text_v3(records),
        Json("nonce"),
      ),
    )
  })
}

///|
test "profile promotion rejects raw batch and driver failure lifecycle" {
  for kind in ["executemany-begin", "driver-error"] {
    let records = orm_profile_test_window_records_v3()
    object_fields_unchecked_v3(records[3])["kind"] = Json(kind)
    orm2_expect_reject(() => {
      ignore(
        orm_profile_window_v3(
          orm_profile_test_window_text_v3(records),
          Json("nonce"),
        ),
      )
    })
  }
}

///|
test "profile promotion requires actual paired execute and confirmed native commit" {
  let result = orm_profile_calls_v3(
    orm_profile_test_window_v3(),
    orm_profile_test_events_v3(),
    orm_profile_test_transactions_v3(),
  )
  assert_eq(orm_get(result, "pairedCalls"), Json(2))
  assert_eq(orm_get(result, "confirmedTransactions"), Json(1))
}

///|
test "profile promotion rejects a native commit response with no actual command" {
  let window = orm_profile_test_window_v3()
  object_fields_unchecked_v3(window.records[5])["commandTag"] = Json::null()
  orm2_expect_reject(() => {
    ignore(
      orm_profile_calls_v3(
        window,
        orm_profile_test_events_v3(),
        orm_profile_test_transactions_v3(),
      ),
    )
  })
}

///|
test "profile promotion rejects commit request with missing native response" {
  let window = orm_profile_test_window_v3()
  object_fields_unchecked_v3(window.records[5])["kind"] = Json("unrelated")
  orm2_expect_reject(() => {
    ignore(
      orm_profile_calls_v3(
        window,
        orm_profile_test_events_v3(),
        orm_profile_test_transactions_v3(),
      ),
    )
  })
}

///|
test "profile promotion rejects mismatched call connection and unfinished driver call" {
  let window = orm_profile_test_window_v3()
  object_fields_unchecked_v3(window.records[3])["connection"] = Json("other")
  orm2_expect_reject(() => {
    ignore(
      orm_profile_calls_v3(
        window,
        orm_profile_test_events_v3(),
        orm_profile_test_transactions_v3(),
      ),
    )
  })
  let window = orm_profile_test_window_v3()
  object_fields_unchecked_v3(window.records[3])["kind"] = Json("unrelated")
  orm2_expect_reject(() => {
    ignore(
      orm_profile_calls_v3(
        window,
        orm_profile_test_events_v3(),
        orm_profile_test_transactions_v3(),
      ),
    )
  })
}

///|
test "profile promotion refuses unknown transaction outcome" {
  let transactions = orm_profile_test_transactions_v3()
  object_fields_unchecked_v3(transactions[0])["status"] = Json("unknown")
  orm2_expect_reject(() => {
    ignore(
      orm_profile_calls_v3(
        orm_profile_test_window_v3(),
        orm_profile_test_events_v3(),
        transactions,
      ),
    )
  })
}

///|
test "profile promotion derives point reads from original SQL EOF facts" {
  let events = orm_profile_test_events_v3()
  let before = Json(events).stringify()
  let (projection, origins) = orm_profile_derived_v3(
    events,
    [orm_profile_test_fact_v3()],
    Json("synthetic-profile"),
  )
  assert_eq(orm_get(projection.normalized, "status"), Json("ready"))
  assert_eq(projection.history.transactions.length(), 1)
  assert_eq(origins, [Json(1), Json(2), Json(4), Json(5), Json(6)])
  assert_eq(Json(events).stringify(), before)
}

///|
test "profile promotion refuses missing original SQL or result binding" {
  orm2_expect_reject(() => {
    ignore(
      orm_profile_derived_v3(
        orm_profile_test_events_v3(),
        [],
        Json("synthetic-profile"),
      ),
    )
  })
  let fact = orm_profile_test_fact_v3()
  object_fields_unchecked_v3(fact)["rows"] = Json(5)
  orm2_expect_reject(() => {
    ignore(
      orm_profile_derived_v3(
        orm_profile_test_events_v3(),
        [fact],
        Json("synthetic-profile"),
      ),
    )
  })
}

///|
test "profile promotion refuses source missing from the original closed version set" {
  let fact = orm_profile_test_fact_v3()
  object_fields_unchecked_v3(orm_get(fact, "data"))["version"] = Json("missing")
  orm2_expect_reject(() => {
    ignore(
      orm_profile_derived_v3(
        orm_profile_test_events_v3(),
        [fact],
        Json("synthetic-profile"),
      ),
    )
  })
}

///|
test "profile promotion refuses handwritten point facts in the raw SQL capture" {
  let events = orm_profile_test_events_v3()
  events[3] = {
    "seq": 4,
    "time": 3,
    "kind": "read",
    "tx": "T",
    "key": "x",
    "version": "x0",
  }
  orm2_expect_reject(() => {
    ignore(
      orm_profile_derived_v3(
        events,
        [orm_profile_test_fact_v3()],
        Json("synthetic-profile"),
      ),
    )
  })
}

///|
test "profile promotion malformed envelope remains inconclusive without a history" {
  let result = object_fields(
    guarded_json(orm_profile_source_v3_json("{}", "{}"), limit=65536),
    "result",
  )
  assert_eq(required(result, "status", "result"), Json("inconclusive"))
  assert_eq(required(result, "analysisCoverageAccepted", "result"), Json(false))
  assert_eq(required(result, "history", "result"), Json::null())
  assert_eq(required(result, "analysis", "result"), Json::null())
}

///|
test "profile promotion rejects native response tag contradicting the actual COMMIT call" {
  let window = orm_profile_test_window_v3()
  object_fields_unchecked_v3(window.records[5])["commandTag"] = Json("ROLLBACK")
  orm2_expect_reject(() => {
    ignore(
      orm_profile_calls_v3(
        window,
        orm_profile_test_events_v3(),
        orm_profile_test_transactions_v3(),
      ),
    )
  })
}

///|
test "profile promotion rejects response outside the paired COMMIT call" {
  let window = orm_profile_test_window_v3()
  object_fields_unchecked_v3(window.records[5])["seq"] = Json(7)
  orm2_expect_reject(() => {
    ignore(
      orm_profile_calls_v3(
        window,
        orm_profile_test_events_v3(),
        orm_profile_test_transactions_v3(),
      ),
    )
  })
}

///|
test "profile promotion refuses an extra fact whose statement or result was never observed" {
  let extra = orm_profile_test_fact_v3()
  let fields = object_fields_unchecked_v3(extra)
  fields["statement"] = Json(5)
  fields["rows"] = Json(6)
  orm2_expect_reject(() => {
    ignore(
      orm_profile_derived_v3(
        orm_profile_test_events_v3(),
        [orm_profile_test_fact_v3(), extra],
        Json("synthetic-profile"),
      ),
    )
  })
}
