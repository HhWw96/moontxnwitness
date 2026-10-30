///|
/// Additional audit regressions. The original 25 protocol tests stay unchanged.
fn orm_profile_audit_records_v3() -> Array[Json] {
  let original = orm_profile_test_window_records_v3()
  let records : Array[Json] = [
    original[0],
    original[1],
    { "kind": "engine-attached", "asynchronous": false },
    { "kind": "connect", "connection": "C" },
    { "kind": "pool-connect", "connection": "C" },
    { "kind": "pool-checkout", "connection": "C" },
    original[2],
    original[3],
    original[4],
    original[5],
    original[6],
    {
      "kind": "pool-reset",
      "connection": "C",
      "terminateOnly": false,
      "transactionWasReset": false,
      "asyncioSafe": true,
    },
    {
      "kind": "call-start",
      "callId": "cleanup",
      "method": "rollback",
      "connection": "C",
      "tx": null,
      "statementSeq": null,
      "journalEventSeqs": {},
    },
    {
      "kind": "call-end",
      "callId": "cleanup",
      "method": "rollback",
      "connection": "C",
      "tx": null,
      "statementSeq": null,
      "journalEventSeqs": {},
      "succeeded": true,
    },
    { "kind": "pool-checkin", "connection": "C" },
    original[7],
    original[8],
    { "kind": "instrumentation-detached", "borrowedConnections": 0 },
  ]
  records
}

///|
fn orm_profile_audit_window_v3(
  records : Array[Json],
) -> OrmProfileWindowV3 raise {
  for i, raw in records {
    let record = object_fields_unchecked_v3(raw)
    record["seq"] = Json(i + 1)
    if i > 0 {
      record["processMonotonicDomain"] = Json("synthetic-process")
      if !record.contains("monotonicNs") || i >= 2 {
        record["monotonicNs"] = Json((1000 + i).to_string())
      }
    }
  }
  // The copied opening timestamp is smaller than all actual worker timestamps.
  object_fields_unchecked_v3(records[1])["monotonicNs"] = Json("1001")
  orm_profile_window_v3(orm_profile_test_window_text_v3(records), Json("nonce"))
}

///|
fn orm_profile_audit_insert_v3(
  records : Array[Json],
  at : Int32,
  additions : Array[Json],
) -> Array[Json] {
  let result : Array[Json] = []
  for i, record in records {
    if i == at {
      for extra in additions {
        result.push(extra)
      }
    }
    result.push(record)
  }
  result
}

///|
test "profile promotion audit accepts balanced engine lifecycle and null transaction pool rollback" {
  let window = orm_profile_audit_window_v3(orm_profile_audit_records_v3())
  orm_profile_ownership_v3(window)
  let calls = orm_profile_calls_v3(
    window,
    orm_profile_test_events_v3(),
    orm_profile_test_transactions_v3(),
  )
  assert_eq(orm_get(calls, "pairedCalls"), Json(3))
  assert_eq(orm_get(calls, "statementCalls"), Json(1))
}

///|
test "profile promotion audit refuses missing or late engine attachment" {
  for late in [false, true] {
    let records = orm_profile_audit_records_v3()
    if late {
      let attach = records[2]
      records[2] = records[7]
      records[7] = attach
    } else {
      object_fields_unchecked_v3(records[2])["kind"] = Json("untyped-factory")
    }
    let window = orm_profile_audit_window_v3(records)
    orm2_expect_reject(() => orm_profile_ownership_v3(window))
  }
}

///|
test "profile promotion audit refuses active and idle pool invalidation" {
  for kind in ["pool-invalidate", "pool-soft-invalidate"] {
    for at in [8, 14] {
      let records = orm_profile_audit_insert_v3(
        orm_profile_audit_records_v3(),
        at,
        [{ "kind": Json(kind), "connection": "C" }],
      )
      let window = orm_profile_audit_window_v3(records)
      orm2_expect_reject(() => orm_profile_ownership_v3(window))
    }
  }
}

///|
test "profile promotion audit refuses a physical close during an active transaction" {
  for kind in ["pool-close", "connection-close"] {
    let records = orm_profile_audit_insert_v3(
      orm_profile_audit_records_v3(),
      8,
      [{ "kind": Json(kind), "connection": "C" }],
    )
    let window = orm_profile_audit_window_v3(records)
    orm2_expect_reject(() => orm_profile_ownership_v3(window))
  }
}

///|
test "profile promotion audit refuses borrowed detach and a missing checkin" {
  let records = orm_profile_audit_records_v3()
  object_fields_unchecked_v3(records[17])["borrowedConnections"] = Json(1)
  let window = orm_profile_audit_window_v3(records)
  orm2_expect_reject(() => orm_profile_ownership_v3(window))
  let records = orm_profile_audit_records_v3()
  object_fields_unchecked_v3(records[14])["kind"] = Json("pool-reset")
  let window = orm_profile_audit_window_v3(records)
  orm2_expect_reject(() => orm_profile_ownership_v3(window))
}

///|
test "profile promotion audit refuses double checkout and checkin before transaction completion" {
  for
    (at, kind) in [
      (8, "pool-checkout"),
      (8, "pool-checkin"),
      (6, "pool-checkin"),
    ] {
    let records = orm_profile_audit_insert_v3(
      orm_profile_audit_records_v3(),
      at,
      [{ "kind": Json(kind), "connection": "C" }],
    )
    let window = orm_profile_audit_window_v3(records)
    orm2_expect_reject(() => orm_profile_ownership_v3(window))
  }
}

///|
test "profile promotion audit refuses work after quiescence and early detach" {
  let records = orm_profile_audit_insert_v3(
    orm_profile_audit_records_v3(),
    16,
    [{ "kind": "pool-checkout", "connection": "C" }],
  )
  let window = orm_profile_audit_window_v3(records)
  orm2_expect_reject(() => orm_profile_ownership_v3(window))
  let records = orm_profile_audit_records_v3()
  let detach = records[17]
  records[17] = records[14]
  records[14] = detach
  let window = orm_profile_audit_window_v3(records)
  orm2_expect_reject(() => orm_profile_ownership_v3(window))
}

///|
test "profile promotion audit refuses unknown lifecycle SQL observations" {
  let records = orm_profile_audit_insert_v3(orm_profile_audit_records_v3(), 8, [
    { "kind": "future-sql-observation", "connection": "C" },
  ])
  let window = orm_profile_audit_window_v3(records)
  orm2_expect_reject(() => orm_profile_ownership_v3(window))
}

///|
test "profile promotion audit refuses null transaction execute despite complete original source" {
  let records = orm_profile_audit_records_v3()
  for at in [12, 13] {
    object_fields_unchecked_v3(records[at])["method"] = Json("execute")
  }
  let window = orm_profile_audit_window_v3(records)
  orm2_expect_reject(() => orm_profile_ownership_v3(window))
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
test "profile promotion audit refuses duplicate successful execute references" {
  let records = orm_profile_audit_records_v3()
  let start = object_fields_unchecked_v3(guarded_json(records[6].stringify()))
  let end = object_fields_unchecked_v3(guarded_json(records[7].stringify()))
  start["callId"] = Json("duplicate-execute")
  end["callId"] = Json("duplicate-execute")
  let window = orm_profile_audit_window_v3(
    orm_profile_audit_insert_v3(records, 8, [Json(start), Json(end)]),
  )
  orm_profile_ownership_v3(window)
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
test "profile promotion audit refuses existing transaction execute without an original statement" {
  let records = orm_profile_audit_records_v3()
  object_fields_unchecked_v3(records[7])["statementSeq"] = Json::null()
  let window = orm_profile_audit_window_v3(records)
  orm_profile_ownership_v3(window)
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
test "profile promotion audit refuses overlapping physical driver calls" {
  let records = orm_profile_audit_records_v3()
  let start = object_fields_unchecked_v3(guarded_json(records[6].stringify()))
  start["callId"] = Json("overlapping")
  let window = orm_profile_audit_window_v3(
    orm_profile_audit_insert_v3(records, 7, [Json(start)]),
  )
  orm2_expect_reject(() => orm_profile_ownership_v3(window))
}

///|
test "profile promotion audit refuses administrative calls with hidden transaction facts" {
  let records = orm_profile_audit_records_v3()
  object_fields_unchecked_v3(records[13])["journalEventSeqs"] = { "begin": 2 }
  let window = orm_profile_audit_window_v3(records)
  orm2_expect_reject(() => orm_profile_ownership_v3(window))
}

///|
test "profile promotion audit refuses open worker and close clock contradictions" {
  let window = orm_profile_audit_window_v3(orm_profile_audit_records_v3())
  object_fields_unchecked_v3(window.records[window.opened])["monotonicNs"] = Json(
    "999999",
  )
  orm2_expect_reject(() => orm_profile_ownership_v3(window))
  let window = orm_profile_audit_window_v3(orm_profile_audit_records_v3())
  object_fields_unchecked_v3(window.records[7])["monotonicNs"] = Json("1000")
  orm2_expect_reject(() => orm_profile_ownership_v3(window))
  let window = orm_profile_audit_window_v3(orm_profile_audit_records_v3())
  object_fields_unchecked_v3(window.records[window.closed])["monotonicNs"] = Json(
    "1000",
  )
  orm2_expect_reject(() => orm_profile_ownership_v3(window))
}

///|
test "profile promotion audit compares decimal clocks without integer overflow" {
  assert_true(
    orm_profile_ns_le_v3("9999999999999999999", "10000000000000000000"),
  )
  assert_true(
    !orm_profile_ns_le_v3("18446744073709551615", "9999999999999999999"),
  )
  let window = orm_profile_audit_window_v3(orm_profile_audit_records_v3())
  object_fields_unchecked_v3(window.records[7])["monotonicNs"] = Json("01007")
  orm2_expect_reject(() => orm_profile_ownership_v3(window))
}

///|
fn orm_profile_audit_index_text_v3(position : Int32) -> String {
  let payload = "{\"first\":0.10,\"nested\":{\"indexSha256\":\"literal\"},\"text\":\"吴🙂\"}"
  let digest_field = "\"indexSha256\":\"" + v3_dislock_sha256(payload) + "\""
  if position == 0 {
    "{" +
    digest_field +
    ",\"first\":0.10,\"nested\":{\"indexSha256\":\"literal\"},\"text\":\"吴🙂\"}\n"
  } else if position == 1 {
    "{\"first\":0.10," +
    digest_field +
    ",\"nested\":{\"indexSha256\":\"literal\"},\"text\":\"吴🙂\"}\n"
  } else {
    "{\"first\":0.10,\"nested\":{\"indexSha256\":\"literal\"},\"text\":\"吴🙂\"," +
    digest_field +
    "}\n"
  }
}

///|
test "profile promotion audit verifies raw index checksum at every member position" {
  for position in [0, 1, 2] {
    let text = orm_profile_audit_index_text_v3(position)
    orm_profile_index_digest_v3(
      text,
      object_fields(guarded_json(text), "index"),
    )
  }
}

///|
test "profile promotion audit rejects corrupt index checksum and raw numeric lexical changes" {
  let text = orm_profile_audit_index_text_v3(1)
  let index = object_fields(guarded_json(text), "index")
  index["indexSha256"] = Json(
    "0000000000000000000000000000000000000000000000000000000000000000",
  )
  orm2_expect_reject(() => orm_profile_index_digest_v3(text, index))
  let changed = text.replace(old="0.10", new="0.1")
  orm2_expect_reject(() => {
    orm_profile_index_digest_v3(
      changed,
      object_fields(guarded_json(changed), "index"),
    )
  })
}

///|
test "profile promotion audit does not accept a nested digest as the index checksum" {
  let text = "{\"nested\":{\"indexSha256\":\"0000000000000000000000000000000000000000000000000000000000000000\"}}"
  orm2_expect_reject(() => {
    orm_profile_index_digest_v3(
      text,
      object_fields(guarded_json(text), "index"),
    )
  })
}
