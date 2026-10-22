///|
fn presence_token(index : Int) -> String {
  "10000000-0000-4000-8000-00000000000" + index.to_string()
}

///|
fn presence_fixture() -> Json {
  let v0 = presence_token(0)
  let v1 = presence_token(1)
  let v2 = presence_token(2)
  let v3 = presence_token(3)
  let v4 = presence_token(4)
  {
    "traceSchema": 2,
    "clockDomain": "presence-test",
    "scope": { "exclusiveWriters": true },
    "gaps": [],
    "events": [
      {
        "seq": 1,
        "time": 0,
        "kind": "snapshot",
        "consistent": true,
        "initial": { "x": v0.to_json() },
      },
      { "seq": 2, "time": 1, "kind": "begin", "tx": "A" },
      {
        "seq": 3,
        "time": 2,
        "kind": "op",
        "tx": "A",
        "op": { "type": "read", "key": "x", "version": v0.to_json() },
      },
      {
        "seq": 4,
        "time": 3,
        "kind": "op",
        "tx": "A",
        "op": { "type": "write", "key": "x", "version": v1.to_json() },
      },
      {
        "seq": 5,
        "time": 4,
        "kind": "op",
        "tx": "A",
        "op": { "type": "write", "key": "x", "version": v2.to_json() },
      },
      {
        "seq": 6,
        "time": 5,
        "kind": "op",
        "tx": "A",
        "op": { "type": "write", "key": "x", "version": v3.to_json() },
      },
      {
        "seq": 7,
        "time": 6,
        "kind": "op",
        "tx": "A",
        "op": { "type": "read", "key": "x", "version": v3.to_json() },
      },
      {
        "seq": 8,
        "time": 7,
        "kind": "op",
        "tx": "A",
        "op": { "type": "write", "key": "x", "version": v4.to_json() },
      },
      { "seq": 9, "time": 8, "kind": "end", "tx": "A", "status": "committed" },
    ],
    "presenceFacts": {
      "schema": 1,
      "projection": "column-presence-register-v0.1.2-experimental",
      "initial": [{ "key": "x", "version": v0.to_json(), "present": false }],
      "reads": [
        {
          "seq": 3,
          "tx": "A",
          "key": "x",
          "version": v0.to_json(),
          "present": false,
        },
        {
          "seq": 7,
          "tx": "A",
          "key": "x",
          "version": v3.to_json(),
          "present": false,
        },
      ],
      "writes": [
        {
          "seq": 4,
          "tx": "A",
          "key": "x",
          "version": v1.to_json(),
          "predecessor": v0.to_json(),
          "oldPresent": false,
          "newPresent": true,
          "action": "insert",
        },
        {
          "seq": 5,
          "tx": "A",
          "key": "x",
          "version": v2.to_json(),
          "predecessor": v1.to_json(),
          "oldPresent": true,
          "newPresent": true,
          "action": "update",
        },
        {
          "seq": 6,
          "tx": "A",
          "key": "x",
          "version": v3.to_json(),
          "predecessor": v2.to_json(),
          "oldPresent": true,
          "newPresent": false,
          "action": "delete",
        },
        {
          "seq": 8,
          "tx": "A",
          "key": "x",
          "version": v4.to_json(),
          "predecessor": v3.to_json(),
          "oldPresent": false,
          "newPresent": true,
          "action": "insert",
        },
      ],
    },
  }
}

///|
fn presence_facts(fixture : Json, field : String) -> Array[Json] raise {
  match capture_field(capture_field(fixture, "presenceFacts"), field) {
    Array(items) => items
    _ => fail("Bad presence test fixture")
  }
}

///|
fn presence_check(fixture : Json, status : String) -> Json raise {
  let result = @json.parse(normalize_presence_capture_json(fixture.stringify()))
  assert_eq(capture_field(result, "status"), status.to_json())
  assert_eq(
    capture_field(capture_field(result, "coverage"), "complete"),
    (status == "ready").to_json(),
  )
  if status != "ready" {
    assert_eq(capture_field(result, "history"), Json::null())
  }
  result
}

///|
fn presence_append_external(
  fixture : Json,
  op : Json,
  fact : Json,
  field : String,
) -> Unit raise {
  let events = capture_events(fixture)
  events.push({ "seq": 10, "time": 9, "kind": "begin", "tx": "B" })
  events.push({ "seq": 11, "time": 10, "kind": "op", "tx": "B", "op": op })
  events.push({
    "seq": 12,
    "time": 11,
    "kind": "end",
    "tx": "B",
    "status": "committed",
  })
  presence_facts(fixture, field).push(fact)
}

///|
test "presence external writes require a committed final predecessor while abnormal reads stay observed" {
  for source in [3, 4] {
    let fixture = presence_fixture()
    if source == 4 {
      capture_event(fixture, 8)["status"] = "aborted".to_json()
    }
    presence_append_external(
      fixture,
      { "type": "write", "key": "x", "version": presence_token(5).to_json() },
      {
        "seq": 11,
        "tx": "B",
        "key": "x",
        "version": presence_token(5).to_json(),
        "predecessor": presence_token(source).to_json(),
        "oldPresent": (source == 4).to_json(),
        "newPresent": (source == 3).to_json(),
        "action": (if source == 4 { "delete" } else { "insert" }).to_json(),
      },
      "writes",
    )
    let _ = presence_check(fixture, "inconclusive")
  }
  for status in ["committed", "aborted"] {
    let fixture = presence_fixture()
    capture_event(fixture, 8)["status"] = status.to_json()
    presence_append_external(
      fixture,
      { "type": "read", "key": "x", "version": presence_token(3).to_json() },
      {
        "seq": 11,
        "tx": "B",
        "key": "x",
        "version": presence_token(3).to_json(),
        "present": false,
      },
      "reads",
    )
    let result = presence_check(fixture, "ready")
    let history = parse_history(capture_field(result, "history").stringify()).unwrap()
    assert_true(
      history.transactions[1].ops == [read_op("x", presence_token(3))],
    )
    assert_true(analyze(history).outcome == Violation)
  }
}

///|
test "presence folds same-transaction tombstones and intermediate writes without inventing reads" {
  let fixture = presence_fixture()
  let result = presence_check(fixture, "ready")
  let history = parse_history(capture_field(result, "history").stringify()).unwrap()
  assert_eq(history.transactions.length(), 1)
  assert_true(
    history.transactions[0].ops ==
    [
      read_op("x", presence_token(0)),
      write_op("x", presence_token(1)),
      write_op("x", presence_token(2)),
      write_op("x", presence_token(3)),
      read_op("x", presence_token(3)),
      write_op("x", presence_token(4)),
    ],
  )
  assert_eq(
    history.version_orders.get("x"),
    Some([presence_token(0), presence_token(4)]),
  )
  assert_true(analyze(history).outcome == Consistent)
  assert_eq(
    capture_field(result, "sourceFacts"),
    capture_field(fixture, "presenceFacts"),
  )
  assert_eq(
    capture_field(capture_field(result, "projection"), "version"),
    "column-presence-register-v0.1.2-experimental".to_json(),
  )
  let _ = capture_check(fixture, "invalid")
}

///|
test "presence aborted writes remain observed operations but never enter committed version facts" {
  let fixture = presence_fixture()
  capture_event(fixture, 8)["status"] = "aborted".to_json()
  let result = presence_check(fixture, "ready")
  let history = parse_history(capture_field(result, "history").stringify()).unwrap()
  assert_true(history.transactions[0].status == Aborted)
  assert_eq(history.transactions[0].ops.length(), 6)
  assert_eq(history.version_orders.get("x"), Some([presence_token(0)]))
}

///|
test "presence rejects missing duplicate and wrongly bound read or write facts" {
  for field in ["reads", "writes"] {
    let fixture = presence_fixture()
    let _ = presence_facts(fixture, field).pop()
    let _ = presence_check(fixture, "invalid")
    let duplicate = presence_fixture()
    let facts = presence_facts(duplicate, field)
    facts.push(facts[0])
    let _ = presence_check(duplicate, "invalid")
    for attribute in ["tx", "key", "version"] {
      let wrong = presence_fixture()
      object_fields(presence_facts(wrong, field)[0], "test")[attribute] = "wrong".to_json()
      let _ = presence_check(wrong, "invalid")
    }
    let wrong_seq = presence_fixture()
    object_fields(presence_facts(wrong_seq, field)[0], "test")["seq"] = (2).to_json()
    let _ = presence_check(wrong_seq, "invalid")
  }
}

///|
test "presence rejects source loops missing predecessors forks and cross-key UUID aliases" {
  for predecessor in [presence_token(1), presence_token(4)] {
    let fixture = presence_fixture()
    object_fields(presence_facts(fixture, "writes")[0], "test")["predecessor"] = predecessor.to_json()
    let _ = presence_check(fixture, "invalid")
  }
  let missing_source = presence_fixture()
  object_fields(presence_facts(missing_source, "writes")[0], "test")["predecessor"] = presence_token(
    9,
  ).to_json()
  let _ = presence_check(missing_source, "inconclusive")
  let fork = presence_fixture()
  object_fields(presence_facts(fork, "writes")[1], "test")["predecessor"] = presence_token(
    0,
  ).to_json()
  let _ = presence_check(fork, "invalid")
  let duplicate_initial = presence_fixture()
  presence_facts(duplicate_initial, "initial").push({
    "key": "y",
    "version": presence_token(0).to_json(),
    "present": false,
  })
  object_fields(capture_event(duplicate_initial, 0).at("initial"), "test")["y"] = presence_token(
    0,
  ).to_json()
  let _ = presence_check(duplicate_initial, "invalid")
}

///|
test "presence rejects altered presence actions and initial-snapshot bindings" {
  let initial = presence_fixture()
  object_fields(presence_facts(initial, "initial")[0], "test")["present"] = true.to_json()
  let _ = presence_check(initial, "invalid")
  let read = presence_fixture()
  object_fields(presence_facts(read, "reads")[1], "test")["present"] = true.to_json()
  let _ = presence_check(read, "invalid")
  for field in ["oldPresent", "newPresent"] {
    let fixture = presence_fixture()
    object_fields(presence_facts(fixture, "writes")[0], "test")[field] = false.to_json()
    if field == "oldPresent" {
      object_fields(presence_facts(fixture, "writes")[0], "test")[field] = true.to_json()
    }
    let _ = presence_check(fixture, "invalid")
  }
  let action = presence_fixture()
  object_fields(presence_facts(action, "writes")[0], "test")["action"] = "update".to_json()
  let _ = presence_check(action, "invalid")
  let missing_initial = presence_fixture()
  let _ = presence_facts(missing_initial, "initial").pop()
  let _ = presence_check(missing_initial, "invalid")
}

///|
test "presence valid gaps unknown outcomes and open scope cannot export complete histories" {
  let gap = presence_fixture()
  object_fields(gap, "test")["gaps"] = [
    capture_gap("missing-event", "Controlled evidence gap"),
  ].to_json()
  let _ = presence_check(gap, "inconclusive")
  let unknown = presence_fixture()
  capture_event(unknown, 8)["status"] = "unknown".to_json()
  let _ = presence_check(unknown, "inconclusive")
  let open = presence_fixture()
  object_fields(capture_field(open, "scope"), "test")["exclusiveWriters"] = false.to_json()
  let _ = presence_check(open, "inconclusive")
}

///|
test "presence rejects noncanonical UUIDs duplicate fields and unknown fact schema" {
  let fixture = presence_fixture()
  object_fields(presence_facts(fixture, "initial")[0], "test")["version"] = "not-a-uuid".to_json()
  let _ = presence_check(fixture, "invalid")
  let schema = presence_fixture()
  object_fields(capture_field(schema, "presenceFacts"), "test")["schema"] = (2).to_json()
  let _ = presence_check(schema, "invalid")
  let duplicate = presence_fixture()
    .stringify()
    .replace(old="\"traceSchema\":2", new="\"traceSchema\":2,\"traceSchema\":2")
  let outcome = @json.parse(normalize_presence_capture_json(duplicate))
  assert_eq(capture_field(outcome, "status"), "invalid".to_json())
}
