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
fn capture_event(fixture : Json, index : Int) -> Map[String, Json] raise {
  object_fields(capture_events(fixture)[index], "test event")
}

///|
fn capture_check(fixture : Json, status : String) -> Json raise {
  let result = @json.parse(normalize_capture_json(fixture.stringify()))
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
    object_fields(fixture, "test")["gaps"] = [capture_gap(code, "test gap")].to_json()
    let _ = capture_check(fixture, "inconclusive")
  }
}

///|
test "capture requires explicit exclusive writer scope" {
  let fixture = capture_fixture()
  object_fields(capture_field(fixture, "scope"), "test")["exclusiveWriters"] = false.to_json()
  let _ = capture_check(fixture, "inconclusive")
}

///|
test "capture inconsistent initialization is not treated as observed initial fact" {
  let fixture = capture_fixture()
  capture_event(fixture, 0)["consistent"] = false.to_json()
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
  capture_event(fixture, 7)["status"] = "unknown".to_json()
  let _ = capture_check(fixture, "inconclusive")
  let unfinished = capture_fixture()
  let _ = capture_events(unfinished).pop()
  let _ = capture_check(unfinished, "inconclusive")
}

///|
test "capture missing snapshot is explicitly unresolved" {
  let fixture = capture_fixture()
  object_fields(fixture, "test")["events"] = ([] : Array[Json]).to_json()
  let _ = capture_check(fixture, "inconclusive")
}

///|
test "capture detects missing event sequence without exporting partial history" {
  let fixture = capture_fixture()
  for index, _ in capture_events(fixture) {
    capture_event(fixture, index)["seq"] = (index + 2).to_json()
  }
  let _ = capture_check(fixture, "inconclusive")
}

///|
test "capture duplicate sequence and backwards clock are invalid" {
  let fixture = capture_fixture()
  capture_event(fixture, 3)["seq"] = (3).to_json()
  let _ = capture_check(fixture, "invalid")
  let clock = capture_fixture()
  capture_event(clock, 3)["time"] = (1).to_json()
  let _ = capture_check(clock, "invalid")
}

///|
test "capture accepts equal clock ticks but rejects unsafe or missing timestamps" {
  let fixture = capture_fixture()
  capture_event(fixture, 3)["time"] = (2).to_json()
  let _ = capture_check(fixture, "ready")
  for
    bad in [
      Json::null(),
      (-1).to_json(),
      0.5.to_json(),
      9007199254740992.0.to_json(),
    ] {
    let invalid_time = capture_fixture()
    capture_event(invalid_time, 3)["time"] = bad
    let _ = capture_check(invalid_time, "invalid")
  }
}

///|
test "capture rejects duplicate JSON keys including escaped key spellings" {
  let raw = "{\"traceSchema\":1,\"traceSchema\":1}"
  let result = @json.parse(normalize_capture_json(raw))
  assert_eq(capture_field(result, "status"), "invalid".to_json())
  let escaped = "{\"traceSchema\":1,\"trace\\u0053chema\":1}"
  assert_eq(
    capture_field(@json.parse(normalize_capture_json(escaped)), "status"),
    "invalid".to_json(),
  )
}

///|
test "capture unknown event kinds and unrecognized structured fields are invalid" {
  let fixture = capture_fixture()
  capture_event(fixture, 2)["kind"] = "new-unknown-event".to_json()
  let _ = capture_check(fixture, "invalid")
  let unsupported = capture_fixture()
  capture_event(unsupported, 3)["unrecognized"] = true.to_json()
  let _ = capture_check(unsupported, "invalid")
}

///|
test "capture rejects operation before begin and operation after end" {
  let fixture = capture_fixture()
  capture_event(fixture, 3)["tx"] = "B".to_json()
  let _ = capture_check(fixture, "invalid")
  let ended = capture_fixture()
  capture_event(ended, 6)["tx"] = "A".to_json()
  let _ = capture_check(ended, "invalid")
}

///|
test "capture duplicate transaction and duplicate end events are invalid" {
  let fixture = capture_fixture()
  capture_event(fixture, 5)["tx"] = "A".to_json()
  let _ = capture_check(fixture, "invalid")
  let ended = capture_fixture()
  capture_event(ended, 7)["tx"] = "A".to_json()
  let _ = capture_check(ended, "invalid")
}

///|
test "capture rejects repeated write identity and reused initial identity" {
  let fixture = capture_fixture()
  object_fields(capture_event(fixture, 6).at("op"), "test")["type"] = "write".to_json()
  let _ = capture_check(fixture, "invalid")
  let reused = capture_fixture()
  object_fields(capture_event(reused, 3).at("op"), "test")["version"] = "x0".to_json()
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
  capture_event(bad, 2)["tx"] = "not-started".to_json()
  let _ = capture_check(bad, "invalid")
}

///|
test "capture schema and clock domain are mandatory and bounded" {
  let fixture = capture_fixture()
  object_fields(fixture, "test")["clockDomain"] = "".to_json()
  let _ = capture_check(fixture, "invalid")
  let unsupported = capture_fixture()
  object_fields(unsupported, "test")["traceSchema"] = (2).to_json()
  let _ = capture_check(unsupported, "invalid")
}

///|
test "capture retains a real aborted source for the existing anomaly checker" {
  let fixture = capture_fixture()
  capture_event(fixture, 4)["status"] = "aborted".to_json()
  let result = capture_check(fixture, "ready")
  let h = parse_history(capture_field(result, "history").stringify()).unwrap()
  assert_true(analyze(h).outcome == Violation)
}

///|
test "capture readiness does not manufacture a source for an unexplained read" {
  let fixture = capture_fixture()
  object_fields(capture_event(fixture, 6).at("op"), "test")["version"] = "never-captured".to_json()
  let result = capture_check(fixture, "ready")
  let h = parse_history(capture_field(result, "history").stringify()).unwrap()
  assert_true(analyze(h).outcome == Inconclusive)
  assert_eq(h.initial, Map([("x", "x0")]))
}

///|
test "capture malformed scope and gap declarations cannot silently disappear" {
  let fixture = capture_fixture()
  object_fields(capture_field(fixture, "scope"), "test")["exclusiveWriters"] = "true".to_json()
  let _ = capture_check(fixture, "invalid")
  let malformed = capture_fixture()
  object_fields(malformed, "test")["gaps"] = [{ "code": "failure" }].to_json()
  let _ = capture_check(malformed, "invalid")
}

///|
test "capture SQL metadata cannot hide new semantic fields or unmapped operations" {
  let fixture = capture_fixture()
  capture_event(fixture, 2)["versionOrders"] = ({} : Json)
  let _ = capture_check(fixture, "invalid")
  let unmapped = capture_fixture()
  capture_event(unmapped, 2)["mapped"] = false.to_json()
  let _ = capture_check(unmapped, "inconclusive")
}

///|
test "capture preserves transport payload types without treating SQL rows as operations" {
  let fixture = capture_fixture()
  let sql = capture_event(fixture, 2)
  sql["phase"] = "execute-ack".to_json()
  sql["mapped"] = true.to_json()
  sql["parameters"] = ["x1", 1, Json::null()]
  sql["rows"] = [["x1", 1]]
  sql["affectedRows"] = (-1).to_json()
  sql["returnedRows"] = (1).to_json()
  sql["exhausted"] = true.to_json()
  let result = capture_check(fixture, "ready")
  let h = parse_history(capture_field(result, "history").stringify()).unwrap()
  assert_eq(h.transactions[0].ops.length(), 1)
  let malformed = capture_fixture()
  capture_event(malformed, 2)["rows"] = "not-an-array".to_json()
  let _ = capture_check(malformed, "invalid")
}

///|
test "capture event resource limits are explicit before event traversal" {
  let fixture = capture_fixture()
  object_fields(fixture, "test")["events"] = Array::make(65537, Json::null()).to_json()
  let _ = capture_check(fixture, "invalid")
}
