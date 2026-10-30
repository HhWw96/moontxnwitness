///|
fn capture_fixture() -> Json {
  {
    "traceSchema": 1,
    "clockDomain": "test-monotonic-clock",
    "scope": { "exclusiveWriters": true },
    "gaps": [],
    "events": [
      {
        "kind": "snapshot",
        "seq": 1,
        "time": 0,
        "consistent": true,
        "initial": { "x": "x0" },
      },
      { "kind": "begin", "seq": 2, "time": 1, "tx": "A" },
      {
        "kind": "sql",
        "seq": 3,
        "time": 2,
        "tx": "A",
        "sql": "UPDATE example SET version = $1",
      },
      {
        "kind": "op",
        "seq": 4,
        "time": 3,
        "tx": "A",
        "op": { "type": "write", "key": "x", "version": "x1" },
      },
      { "kind": "end", "seq": 5, "time": 4, "tx": "A", "status": "committed" },
      { "kind": "begin", "seq": 6, "time": 5, "tx": "B" },
      {
        "kind": "op",
        "seq": 7,
        "time": 6,
        "tx": "B",
        "op": { "type": "read", "key": "x", "version": "x1" },
      },
      { "kind": "end", "seq": 8, "time": 7, "tx": "B", "status": "committed" },
    ],
  }
}

///|
fn capture_events(fixture : Json) -> Array[Json] raise {
  match capture_field(fixture, "events") {
    Array(items) => items
    _ => fail("bad capture test fixture")
  }
}

///|
fn capture_field(value : Json, key : String) -> Json raise {
  required(object_fields(value, "test object"), key, "test object")
}

///|
fn capture_event(fixture : Json, index : Int32) -> Map[String, Json] raise {
  object_fields(capture_events(fixture)[index], "test event")
}

///|
fn capture_check(fixture : Json, status : String) -> Json raise {
  let result = @json.parse(normalize_capture_json(fixture.stringify()))
  assert_eq(capture_field(result, "status"), Json(status))
  assert_eq(
    capture_field(capture_field(result, "coverage"), "complete"),
    Json(status == "ready"),
  )
  if status != "ready" {
    assert_eq(capture_field(result, "history"), Json::null())
  }
  result
}

///|
test "capture normalization preserves facts without inventing version order" {
  let result = capture_check(capture_fixture(), "ready")
  let h = parse_history(capture_field(result, "history").stringify()).unwrap()
  assert_eq(h.transactions.length(), 2)
  assert_eq(h.transactions[0].start, Some(1L))
  assert_eq(h.transactions[0].end, Some(4L))
  assert_true(h.transactions[0].ops == [write_op("x", "x1")])
  assert_true(h.transactions[1].ops == [read_op("x", "x1")])
  assert_eq(h.version_orders, Map([]))
  assert_true(analyze(h).outcome == Consistent)
}

///|
test "capture explicit gaps never expose a normal history" {
  for
    code in [
      "unsupported_sql", "incomplete_fetch", "log_failure", "autocommit", "savepoint",
    ] {
    let fixture = capture_fixture()
    object_fields(fixture, "test")["gaps"] = Json([
      capture_gap(code, "test gap"),
    ])
    let _ = capture_check(fixture, "inconclusive")
  }
}

///|
test "capture requires explicit exclusive writer scope" {
  let fixture = capture_fixture()
  object_fields(capture_field(fixture, "scope"), "test")["exclusiveWriters"] = Json(
    false,
  )
  let _ = capture_check(fixture, "inconclusive")
}

///|
test "capture inconsistent initialization is not treated as observed initial fact" {
  let fixture = capture_fixture()
  capture_event(fixture, 0)["consistent"] = Json(false)
  let _ = capture_check(fixture, "inconclusive")
}

///|
test "capture missing initial key does not manufacture an initial version" {
  let fixture = capture_fixture()
  capture_event(fixture, 0)["initial"] = ({} : Json)
  let _ = capture_check(fixture, "inconclusive")
}

///|
test "capture unknown commit and outstanding transactions stay inconclusive" {
  let fixture = capture_fixture()
  capture_event(fixture, 7)["status"] = Json("unknown")
  let _ = capture_check(fixture, "inconclusive")
  let unfinished = capture_fixture()
  let _ = capture_events(unfinished).pop()
  let _ = capture_check(unfinished, "inconclusive")
}

///|
test "capture missing snapshot is explicitly unresolved" {
  let fixture = capture_fixture()
  object_fields(fixture, "test")["events"] = Json(([] : Array[Json]))
  let _ = capture_check(fixture, "inconclusive")
}

///|
test "capture detects missing event sequence without exporting partial history" {
  let fixture = capture_fixture()
  for index, _ in capture_events(fixture) {
    capture_event(fixture, index)["seq"] = Json(index + 2)
  }
  let _ = capture_check(fixture, "inconclusive")
}

///|
test "capture duplicate sequence and backwards clock are invalid" {
  let fixture = capture_fixture()
  capture_event(fixture, 3)["seq"] = Json(3)
  let _ = capture_check(fixture, "invalid")
  let clock = capture_fixture()
  capture_event(clock, 3)["time"] = Json(1)
  let _ = capture_check(clock, "invalid")
}

///|
test "capture accepts equal clock ticks but rejects unsafe or missing timestamps" {
  let fixture = capture_fixture()
  capture_event(fixture, 3)["time"] = Json(2)
  let _ = capture_check(fixture, "ready")
  for bad in [Json::null(), Json(-1), Json(0.5), Json(9007199254740992.0)] {
    let invalid_time = capture_fixture()
    capture_event(invalid_time, 3)["time"] = bad
    let _ = capture_check(invalid_time, "invalid")
  }
}

///|
test "capture rejects duplicate JSON keys including escaped key spellings" {
  let raw = "{\"traceSchema\":1,\"traceSchema\":1}"
  let result = @json.parse(normalize_capture_json(raw))
  assert_eq(capture_field(result, "status"), Json("invalid"))
  let escaped = "{\"traceSchema\":1,\"trace\\u0053chema\":1}"
  assert_eq(
    capture_field(@json.parse(normalize_capture_json(escaped)), "status"),
    Json("invalid"),
  )
}

///|
test "capture unknown event kinds and unrecognized structured fields are invalid" {
  let fixture = capture_fixture()
  capture_event(fixture, 2)["kind"] = Json("new-unknown-event")
  let _ = capture_check(fixture, "invalid")
  let unsupported = capture_fixture()
  capture_event(unsupported, 3)["unrecognized"] = Json(true)
  let _ = capture_check(unsupported, "invalid")
}

///|
test "capture rejects operation before begin and operation after end" {
  let fixture = capture_fixture()
  capture_event(fixture, 3)["tx"] = Json("B")
  let _ = capture_check(fixture, "invalid")
  let ended = capture_fixture()
  capture_event(ended, 6)["tx"] = Json("A")
  let _ = capture_check(ended, "invalid")
}

///|
test "capture duplicate transaction and duplicate end events are invalid" {
  let fixture = capture_fixture()
  capture_event(fixture, 5)["tx"] = Json("A")
  let _ = capture_check(fixture, "invalid")
  let ended = capture_fixture()
  capture_event(ended, 7)["tx"] = Json("A")
  let _ = capture_check(ended, "invalid")
}

///|
test "capture rejects repeated write identity and reused initial identity" {
  let fixture = capture_fixture()
  object_fields(capture_event(fixture, 6).at("op"), "test")["type"] = Json(
    "write",
  )
  let _ = capture_check(fixture, "invalid")
  let reused = capture_fixture()
  object_fields(capture_event(reused, 3).at("op"), "test")["version"] = Json(
    "x0",
  )
  let _ = capture_check(reused, "invalid")
}

///|
test "capture unique snapshot must precede transaction lifecycle" {
  let fixture = capture_fixture()
  capture_events(fixture)[1] = {
    "kind": "snapshot",
    "seq": 2,
    "time": 1,
    "consistent": true,
    "initial": { "x": "x0" },
  }
  let _ = capture_check(fixture, "invalid")
  let no_initial = capture_fixture()
  capture_events(no_initial)[0] = {
    "kind": "begin",
    "seq": 1,
    "time": 0,
    "tx": "early",
  }
  let _ = capture_check(no_initial, "invalid")
}

///|
test "capture SQL metadata is ordered and transaction scoped" {
  let fixture = capture_fixture()
  capture_event(fixture, 2)["tx"] = Json::null()
  let _ = capture_check(fixture, "ready")
  let bad = capture_fixture()
  capture_event(bad, 2)["tx"] = Json("not-started")
  let _ = capture_check(bad, "invalid")
}

///|
test "capture schema and clock domain are mandatory and bounded" {
  let fixture = capture_fixture()
  object_fields(fixture, "test")["clockDomain"] = Json("")
  let _ = capture_check(fixture, "invalid")
  let unsupported = capture_fixture()
  object_fields(unsupported, "test")["traceSchema"] = Json(2)
  let _ = capture_check(unsupported, "invalid")
}

///|
test "capture retains a real aborted source for the existing anomaly checker" {
  let fixture = capture_fixture()
  capture_event(fixture, 4)["status"] = Json("aborted")
  let result = capture_check(fixture, "ready")
  let h = parse_history(capture_field(result, "history").stringify()).unwrap()
  assert_true(analyze(h).outcome == Violation)
}

///|
test "capture readiness does not manufacture a source for an unexplained read" {
  let fixture = capture_fixture()
  object_fields(capture_event(fixture, 6).at("op"), "test")["version"] = Json(
    "never-captured",
  )
  let result = capture_check(fixture, "ready")
  let h = parse_history(capture_field(result, "history").stringify()).unwrap()
  assert_true(analyze(h).outcome == Inconclusive)
  assert_eq(h.initial, Map([("x", "x0")]))
}

///|
test "capture malformed scope and gap declarations cannot silently disappear" {
  let fixture = capture_fixture()
  object_fields(capture_field(fixture, "scope"), "test")["exclusiveWriters"] = Json(
    "true",
  )
  let _ = capture_check(fixture, "invalid")
  let malformed = capture_fixture()
  object_fields(malformed, "test")["gaps"] = Json([{ "code": "failure" }])
  let _ = capture_check(malformed, "invalid")
}

///|
test "capture SQL metadata cannot hide new semantic fields or unmapped operations" {
  let fixture = capture_fixture()
  capture_event(fixture, 2)["versionOrders"] = ({} : Json)
  let _ = capture_check(fixture, "invalid")
  let unmapped = capture_fixture()
  capture_event(unmapped, 2)["mapped"] = Json(false)
  let _ = capture_check(unmapped, "inconclusive")
}

///|
test "capture preserves transport payload types without treating SQL rows as operations" {
  let fixture = capture_fixture()
  let sql = capture_event(fixture, 2)
  sql["phase"] = Json("execute-ack")
  sql["mapped"] = Json(true)
  sql["parameters"] = ["x1", 1, Json::null()]
  sql["rows"] = [["x1", 1]]
  sql["affectedRows"] = Json(-1)
  sql["returnedRows"] = Json(1)
  sql["exhausted"] = Json(true)
  let result = capture_check(fixture, "ready")
  let h = parse_history(capture_field(result, "history").stringify()).unwrap()
  assert_eq(h.transactions[0].ops.length(), 1)
  let malformed = capture_fixture()
  capture_event(malformed, 2)["rows"] = Json("not-an-array")
  let _ = capture_check(malformed, "invalid")
}

///|
test "capture event resource limits are explicit before event traversal" {
  let fixture = capture_fixture()
  object_fields(fixture, "test")["events"] = Json(
    Array::make(65537, Json::null()),
  )
  let _ = capture_check(fixture, "invalid")
}

///|
fn column_capture_key() -> String {
  "[\"mtw_provenance_profile.items\",\"text\",\"a\"]"
}

///|
fn column_capture_trace(body : Array[Json]) -> Json raise {
  let initial : Map[String, String] = Map([
    (column_capture_key(), "50000000-0000-4000-8000-000000000000"),
  ])
  let events : Array[Json] = [
    {
      "kind": "snapshot",
      "seq": 1,
      "time": 0,
      "consistent": true,
      "initial": Json(initial),
    },
  ]
  for index, event in body {
    let fields = object_fields(event, "column capture test event")
    fields["seq"] = Json(index + 2)
    fields["time"] = Json(index + 1)
    events.push(event)
  }
  {
    "traceSchema": 1,
    "clockDomain": "column-profile-monotonic-test",
    "scope": { "exclusiveWriters": true },
    "gaps": [],
    "events": Json(events),
  }
}

///|
test "server tokens preserve repeated-value writes and internal intermediate reads" {
  let key = column_capture_key()
  let first = "f0000000-0000-4000-8000-000000000001"
  let final_token = "10000000-0000-4000-8000-000000000002"
  let trace = column_capture_trace([
    { "kind": "begin", "tx": "W" },
    {
      "kind": "sql",
      "tx": "W",
      "phase": "execute-request",
      "mapped": true,
      "sql": "UPDATE items SET value=%s WHERE id=%s",
      "parameters": [7, "a"],
    },
    {
      "kind": "sql",
      "tx": "W",
      "phase": "execute-ack",
      "mapped": true,
      "sql": "UPDATE items SET value=%s WHERE id=%s RETURNING private_version",
      "affectedRows": 1,
      "rows": [[Json(first)]],
    },
    {
      "kind": "op",
      "tx": "W",
      "op": { "type": "write", "key": Json(key), "version": Json(first) },
    },
    {
      "kind": "sql",
      "tx": "W",
      "phase": "fetch",
      "returnedRows": 1,
      "exhausted": true,
      "rows": [[7, Json(first)]],
    },
    {
      "kind": "op",
      "tx": "W",
      "op": { "type": "read", "key": Json(key), "version": Json(first) },
    },
    {
      "kind": "sql",
      "tx": "W",
      "phase": "execute-request",
      "mapped": true,
      "sql": "UPDATE items SET value=%s WHERE id=%s",
      "parameters": [7, "a"],
    },
    {
      "kind": "sql",
      "tx": "W",
      "phase": "execute-ack",
      "mapped": true,
      "sql": "UPDATE items SET value=%s WHERE id=%s RETURNING private_version",
      "affectedRows": 1,
      "rows": [[Json(final_token)]],
    },
    {
      "kind": "op",
      "tx": "W",
      "op": { "type": "write", "key": Json(key), "version": Json(final_token) },
    },
    {
      "kind": "op",
      "tx": "W",
      "op": { "type": "read", "key": Json(key), "version": Json(final_token) },
    },
    { "kind": "end", "tx": "W", "status": "committed" },
    { "kind": "begin", "tx": "R" },
    {
      "kind": "op",
      "tx": "R",
      "op": { "type": "read", "key": Json(key), "version": Json(final_token) },
    },
    { "kind": "end", "tx": "R", "status": "committed" },
  ])
  let normalized = capture_check(trace, "ready")
  let h = parse_history(capture_field(normalized, "history").stringify()).unwrap()
  assert_eq(h.transactions[0].ops.length(), 4)
  assert_eq(h.transactions[0].ops[0].version, first)
  assert_eq(h.transactions[0].ops[1].version, first)
  assert_eq(h.transactions[0].ops[2].version, final_token)
  let report = analyze(h)
  assert_true(report.outcome == Consistent)
  assert_eq(report.inferred_orders.at(key), [
    "50000000-0000-4000-8000-000000000000", final_token,
  ])
  assert_true(
    report.edges.any(edge => {
      edge.kind == WR &&
      edge.from == "W" &&
      edge.to == "R" &&
      edge.from_op == Some(2)
    }),
  )
  assert_true(h.version_orders.is_empty())
}

///|
test "server-token projection retains external intermediate-version evidence" {
  let key = column_capture_key()
  let first = "f0000000-0000-4000-8000-000000000001"
  let final_token = "10000000-0000-4000-8000-000000000002"
  let trace = column_capture_trace([
    { "kind": "begin", "tx": "W" },
    {
      "kind": "op",
      "tx": "W",
      "op": { "type": "write", "key": Json(key), "version": Json(first) },
    },
    {
      "kind": "op",
      "tx": "W",
      "op": { "type": "write", "key": Json(key), "version": Json(final_token) },
    },
    { "kind": "end", "tx": "W", "status": "committed" },
    { "kind": "begin", "tx": "R" },
    {
      "kind": "op",
      "tx": "R",
      "op": { "type": "read", "key": Json(key), "version": Json(first) },
    },
    { "kind": "end", "tx": "R", "status": "committed" },
  ])
  let normalized = capture_check(trace, "ready")
  let h = parse_history(capture_field(normalized, "history").stringify()).unwrap()
  let report = analyze(h)
  assert_true(report.outcome == Violation)
  assert_true(has_code(report, "intermediate_read"))
  assert_eq(h.transactions[0].ops.length(), 2)
  assert_eq(h.transactions[1].ops[0].version, first)
}

///|
test "server-token rollback facts survive while unknown outcomes cannot expose history" {
  let key = column_capture_key()
  let token = "70000000-0000-4000-8000-000000000003"
  let trace = column_capture_trace([
    { "kind": "begin", "tx": "W" },
    {
      "kind": "op",
      "tx": "W",
      "op": { "type": "write", "key": Json(key), "version": Json(token) },
    },
    {
      "kind": "op",
      "tx": "W",
      "op": { "type": "read", "key": Json(key), "version": Json(token) },
    },
    { "kind": "end", "tx": "W", "status": "aborted" },
    { "kind": "begin", "tx": "R" },
    {
      "kind": "op",
      "tx": "R",
      "op": {
        "type": "read",
        "key": Json(key),
        "version": "50000000-0000-4000-8000-000000000000",
      },
    },
    { "kind": "end", "tx": "R", "status": "committed" },
  ])
  let normalized = capture_check(trace, "ready")
  let h = parse_history(capture_field(normalized, "history").stringify()).unwrap()
  assert_true(h.transactions[0].status == Aborted)
  assert_eq(h.transactions[0].ops.length(), 2)
  assert_eq(h.transactions[0].ops[0].version, token)
  assert_true(analyze(h).outcome == Consistent)
  capture_event(trace, 4)["status"] = Json("unknown")
  let _ = capture_check(trace, "inconclusive")
}

///|
test "server UUID and acknowledgement order do not become collected version order" {
  let key = column_capture_key()
  let early = "f0000000-0000-4000-8000-000000000001"
  let later = "10000000-0000-4000-8000-000000000002"
  let trace = column_capture_trace([
    { "kind": "begin", "tx": "A" },
    {
      "kind": "op",
      "tx": "A",
      "op": { "type": "write", "key": Json(key), "version": Json(early) },
    },
    { "kind": "end", "tx": "A", "status": "committed" },
    { "kind": "begin", "tx": "B" },
    {
      "kind": "op",
      "tx": "B",
      "op": { "type": "write", "key": Json(key), "version": Json(later) },
    },
    { "kind": "end", "tx": "B", "status": "committed" },
  ])
  let normalized = capture_check(trace, "ready")
  let h = parse_history(capture_field(normalized, "history").stringify()).unwrap()
  assert_true(h.version_orders.is_empty())
  assert_eq(h.transactions[0].ops[0].version, early)
  assert_eq(h.transactions[1].ops[0].version, later)
  let result = analyze_with_options(h)
  assert_true(result.report.outcome == Consistent)
  assert_eq(result.report.order_sources.at(key), "searched")
  assert_true(h.version_orders.is_empty())
  capture_events(trace)[2] = {
    "kind": "sql",
    "seq": 3,
    "time": 2,
    "tx": "A",
    "phase": "execute-request",
    "sql": "SELECT count(*) FROM items",
    "mapped": false,
  }
  let _ = capture_check(trace, "inconclusive")
}
