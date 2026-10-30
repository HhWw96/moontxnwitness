///|
fn v3_test_trace(body : Array[Json]) -> Json {
  let events : Array[Json] = [
    {
      "kind": "snapshot",
      "initial": { "x": "x0", "y": "y0" },
      "consistent": true,
    },
  ]
  for event in body {
    events.push(event)
  }
  for index, event in events {
    let fields = object_fields_unchecked_v3(event)
    fields["seq"] = Json(index + 1)
    fields["time"] = Json(index)
  }
  {
    "traceSchema": 3,
    "clockDomain": "v3-test",
    "scope": { "exclusiveWriters": true },
    "events": Json(events),
    "gaps": [],
  }
}

///|
fn v3_test_completed(steps : Array[Json]) -> Json {
  let body : Array[Json] = [{ "kind": "begin", "tx": "A", "connection": "c" }]
  for step in steps {
    body.push(step)
  }
  body.push({ "kind": "commit_request", "tx": "A" })
  body.push({ "kind": "commit_ok", "tx": "A" })
  v3_test_trace(body)
}

///|
fn v3_test_check(trace : Json, status : String) -> Json raise {
  let result = @json.parse(normalize_capture_v3_json(trace.stringify()))
  assert_eq(capture_field(result, "schema"), Json(3))
  assert_eq(capture_field(result, "algorithm"), Json("v3-lifecycle-1"))
  assert_eq(capture_field(result, "status"), Json(status))
  assert_eq(
    capture_field(capture_field(result, "coverage"), "complete"),
    Json(status == "ready"),
  )
  assert_eq(
    capture_field(result, "observations"),
    capture_field(trace, "events"),
  )
  if status != "ready" {
    assert_eq(capture_field(result, "history"), Json::null())
  }
  result
}

///|
fn v3_test_items(value : Json, field : String) -> Array[Json] raise {
  match capture_field(value, field) {
    Array(items) => items
    _ => fail("Bad v3 fixture array")
  }
}

///|
fn v3_test_has_gap(result : Json, code : String) -> Bool raise {
  let mut found = false
  for gap in v3_test_items(capture_field(result, "coverage"), "gaps") {
    if capture_field(gap, "code") == Json(code) {
      found = true
    }
  }
  found
}

///|
test "v3 empty commit retains transaction identity and no client realtime constraints" {
  let result = v3_test_check(v3_test_completed([]), "ready")
  let tx = v3_test_items(result, "transactions")[0]
  assert_eq(capture_field(tx, "events"), Json([2, 3, 4]))
  assert_eq(capture_field(tx, "finalWrites"), Json::array([]))
  let h = parse_history(capture_field(result, "history").stringify()).unwrap()
  assert_eq(h.transactions.length(), 1)
  assert_eq(h.transactions[0].start, None)
  assert_eq(h.transactions[0].end, None)
  assert_eq(h.version_orders.get("x"), Some(["x0"]))
}

///|
test "v3 own read is checked before eliminating it from the safe projection" {
  let trace = v3_test_completed([
    {
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "x1",
      "predecessor": "x0",
    },
    { "kind": "read", "tx": "A", "key": "x", "version": "x1" },
  ])
  let result = v3_test_check(trace, "ready")
  let h = parse_history(capture_field(result, "history").stringify()).unwrap()
  assert_true(h.transactions[0].ops == [write_op("x", "x1")])
  assert_eq(
    capture_field(v3_test_items(result, "transactions")[0], "finalWrites"),
    Json([3]),
  )
  assert_eq(
    capture_field(v3_test_items(result, "effects")[0], "revertedBy"),
    Json::null(),
  )
}

///|
test "v3 ordinary external initial reads stay in the replay program" {
  let result = v3_test_check(
    v3_test_completed([
      { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
    ]),
    "ready",
  )
  let h = parse_history(capture_field(result, "history").stringify()).unwrap()
  assert_true(h.transactions[0].ops == [read_op("x", "x0")])
}

///|
test "v3 nested rollback restores each original overlay and preserves delivered reads" {
  let result = v3_test_check(
    v3_test_completed([
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "x1",
        "predecessor": "x0",
      },
      { "kind": "savepoint", "tx": "A", "name": "outer", "instance": "s1" },
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "x2",
        "predecessor": "x1",
      },
      { "kind": "savepoint", "tx": "A", "name": "inner", "instance": "s2" },
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "x3",
        "predecessor": "x2",
      },
      { "kind": "rollback_to", "tx": "A", "instance": "s2" },
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "x4",
        "predecessor": "x2",
      },
      { "kind": "rollback_to", "tx": "A", "instance": "s1" },
      { "kind": "read", "tx": "A", "key": "x", "version": "x1" },
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "x5",
        "predecessor": "x1",
      },
    ]),
    "ready",
  )
  let effects = v3_test_items(result, "effects")
  assert_eq(effects.length(), 5)
  assert_eq(capture_field(effects[1], "revertedBy"), Json(10))
  assert_eq(capture_field(effects[2], "revertedBy"), Json(8))
  assert_eq(capture_field(effects[3], "revertedBy"), Json(10))
  let h = parse_history(capture_field(result, "history").stringify()).unwrap()
  assert_true(
    h.transactions[0].ops == [write_op("x", "x1"), write_op("x", "x5")],
  )
  assert_eq(h.version_orders.get("x"), Some(["x0", "x5"]))
}

///|
test "v3 release merges child writes so parent rollback still revokes them" {
  let result = v3_test_check(
    v3_test_completed([
      { "kind": "savepoint", "tx": "A", "name": "outer", "instance": "s1" },
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "x1",
        "predecessor": "x0",
      },
      { "kind": "savepoint", "tx": "A", "name": "inner", "instance": "s2" },
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "x2",
        "predecessor": "x1",
      },
      { "kind": "release", "tx": "A", "instance": "s2" },
      { "kind": "read", "tx": "A", "key": "x", "version": "x2" },
      { "kind": "rollback_to", "tx": "A", "instance": "s1" },
      { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
    ]),
    "ready",
  )
  for effect in v3_test_items(result, "effects") {
    assert_eq(capture_field(effect, "revertedBy"), Json(9))
  }
  let h = parse_history(capture_field(result, "history").stringify()).unwrap()
  assert_true(h.transactions[0].ops == [read_op("x", "x0")])
}

///|
test "v3 rollback target remains active for a second rollback" {
  let result = v3_test_check(
    v3_test_completed([
      { "kind": "savepoint", "tx": "A", "name": "s", "instance": "s1" },
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "x1",
        "predecessor": "x0",
      },
      { "kind": "rollback_to", "tx": "A", "instance": "s1" },
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "x2",
        "predecessor": "x0",
      },
      { "kind": "rollback_to", "tx": "A", "instance": "s1" },
      { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
    ]),
    "ready",
  )
  let effects = v3_test_items(result, "effects")
  assert_eq(capture_field(effects[0], "revertedBy"), Json(5))
  assert_eq(capture_field(effects[1], "revertedBy"), Json(7))
}

///|
test "v3 hidden same-name savepoint cannot be addressed by older instance ID" {
  for kind in ["rollback_to", "release"] {
    let _ = v3_test_check(
      v3_test_completed([
        { "kind": "savepoint", "tx": "A", "name": "same", "instance": "s1" },
        { "kind": "savepoint", "tx": "A", "name": "same", "instance": "s2" },
        { "kind": Json(kind), "tx": "A", "instance": "s1" },
      ]),
      "invalid",
    )
  }
}

///|
test "v3 releasing newest same-name mark exposes the old one" {
  let result = v3_test_check(
    v3_test_completed([
      { "kind": "savepoint", "tx": "A", "name": "same", "instance": "s1" },
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "x1",
        "predecessor": "x0",
      },
      { "kind": "savepoint", "tx": "A", "name": "same", "instance": "s2" },
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "x2",
        "predecessor": "x1",
      },
      { "kind": "release", "tx": "A", "instance": "s2" },
      { "kind": "rollback_to", "tx": "A", "instance": "s1" },
    ]),
    "ready",
  )
  for effect in v3_test_items(result, "effects") {
    assert_eq(capture_field(effect, "revertedBy"), Json(8))
  }
}

///|
test "v3 rollback destroys descendants while release destroys its own mark" {
  let _ = v3_test_check(
    v3_test_completed([
      { "kind": "savepoint", "tx": "A", "name": "outer", "instance": "s1" },
      { "kind": "savepoint", "tx": "A", "name": "inner", "instance": "s2" },
      { "kind": "rollback_to", "tx": "A", "instance": "s1" },
      { "kind": "release", "tx": "A", "instance": "s2" },
    ]),
    "invalid",
  )
  let _ = v3_test_check(
    v3_test_completed([
      { "kind": "savepoint", "tx": "A", "name": "s", "instance": "s1" },
      { "kind": "release", "tx": "A", "instance": "s1" },
      { "kind": "rollback_to", "tx": "A", "instance": "s1" },
    ]),
    "invalid",
  )
}

///|
test "v3 savepoint instance identity is not reusable after release" {
  let _ = v3_test_check(
    v3_test_completed([
      { "kind": "savepoint", "tx": "A", "name": "one", "instance": "s" },
      { "kind": "release", "tx": "A", "instance": "s" },
      { "kind": "savepoint", "tx": "A", "name": "two", "instance": "s" },
    ]),
    "invalid",
  )
}

///|
test "v3 top-level rollback revokes effects but retains original own reads" {
  let result = v3_test_check(
    v3_test_trace([
      { "kind": "begin", "tx": "A", "connection": "c" },
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "x1",
        "predecessor": "x0",
      },
      { "kind": "read", "tx": "A", "key": "x", "version": "x1" },
      { "kind": "rollback_ok", "tx": "A" },
    ]),
    "ready",
  )
  assert_eq(
    capture_field(v3_test_items(result, "effects")[0], "revertedBy"),
    Json(5),
  )
  assert_eq(
    capture_field(v3_test_items(result, "transactions")[0], "status"),
    Json("aborted"),
  )
  assert_eq(
    capture_field(v3_test_items(result, "transactions")[0], "finalWrites"),
    Json::array([]),
  )
}

///|
test "v3 a connection may be reused sequentially with distinct transaction identities" {
  let result = v3_test_check(
    v3_test_trace([
      { "kind": "begin", "tx": "A", "connection": "c" },
      { "kind": "commit_request", "tx": "A" },
      { "kind": "commit_ok", "tx": "A" },
      { "kind": "begin", "tx": "B", "connection": "c" },
      { "kind": "read", "tx": "B", "key": "x", "version": "x0" },
      { "kind": "commit_request", "tx": "B" },
      { "kind": "commit_ok", "tx": "B" },
    ]),
    "ready",
  )
  assert_eq(v3_test_items(result, "transactions").length(), 2)
}

///|
test "v3 overlapping transactions on one connection are rejected" {
  let _ = v3_test_check(
    v3_test_trace([
      { "kind": "begin", "tx": "A", "connection": "c" },
      { "kind": "begin", "tx": "B", "connection": "c" },
    ]),
    "invalid",
  )
}

///|
test "v3 transaction identities cannot be reused after rollback" {
  let _ = v3_test_check(
    v3_test_trace([
      { "kind": "begin", "tx": "A", "connection": "c" },
      { "kind": "rollback_ok", "tx": "A" },
      { "kind": "begin", "tx": "A", "connection": "other" },
    ]),
    "invalid",
  )
}

///|
test "v3 commit confirmation needs a request and cannot be followed by more operations" {
  let _ = v3_test_check(
    v3_test_trace([
      { "kind": "begin", "tx": "A", "connection": "c" },
      { "kind": "commit_ok", "tx": "A" },
    ]),
    "invalid",
  )
  let _ = v3_test_check(
    v3_test_trace([
      { "kind": "begin", "tx": "A", "connection": "c" },
      { "kind": "commit_request", "tx": "A" },
      { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
    ]),
    "invalid",
  )
}

///|
test "v3 disconnect after commit request leaves permanent unknown even after connection reuse" {
  let result = v3_test_check(
    v3_test_trace([
      { "kind": "begin", "tx": "A", "connection": "c" },
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "x1",
        "predecessor": "x0",
      },
      { "kind": "commit_request", "tx": "A" },
      { "kind": "disconnect", "tx": "A" },
      { "kind": "begin", "tx": "B", "connection": "c" },
      { "kind": "commit_request", "tx": "B" },
      { "kind": "commit_ok", "tx": "B" },
    ]),
    "inconclusive",
  )
  assert_true(v3_test_has_gap(result, "unknown_commit"))
  assert_eq(
    capture_field(v3_test_items(result, "transactions")[0], "status"),
    Json("unknown"),
  )
  assert_eq(
    capture_field(v3_test_items(result, "transactions")[1], "status"),
    Json("committed"),
  )
}

///|
test "v3 rollback ack after a commit request cannot prove original commit was aborted" {
  let result = v3_test_check(
    v3_test_trace([
      { "kind": "begin", "tx": "A", "connection": "c" },
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "x1",
        "predecessor": "x0",
      },
      { "kind": "commit_request", "tx": "A" },
      { "kind": "rollback_ok", "tx": "A" },
    ]),
    "inconclusive",
  )
  assert_eq(
    capture_field(v3_test_items(result, "transactions")[0], "status"),
    Json("unknown"),
  )
  assert_eq(
    capture_field(v3_test_items(result, "effects")[0], "revertedBy"),
    Json::null(),
  )
}

///|
test "v3 an outstanding transaction has unknown outcome and no terminal sequence" {
  let result = v3_test_check(
    v3_test_trace([{ "kind": "begin", "tx": "A", "connection": "c" }]),
    "inconclusive",
  )
  assert_true(v3_test_has_gap(result, "outstanding_transaction"))
  assert_eq(
    capture_field(v3_test_items(result, "transactions")[0], "endSeq"),
    Json::null(),
  )
}

///|
test "v3 delayed commit acknowledgement is not an artificial dependency" {
  let result = v3_test_check(
    v3_test_trace([
      { "kind": "begin", "tx": "W", "connection": "cw" },
      {
        "kind": "write",
        "tx": "W",
        "key": "x",
        "version": "x1",
        "predecessor": "x0",
      },
      { "kind": "commit_request", "tx": "W" },
      { "kind": "begin", "tx": "R", "connection": "cr" },
      { "kind": "read", "tx": "R", "key": "x", "version": "x1" },
      { "kind": "commit_request", "tx": "R" },
      { "kind": "commit_ok", "tx": "R" },
      { "kind": "commit_ok", "tx": "W" },
    ]),
    "ready",
  )
  let h = parse_history(capture_field(result, "history").stringify()).unwrap()
  assert_eq(h.version_orders.get("x"), Some(["x0", "x1"]))
  assert_true(analyze(h).outcome == Consistent)
}

///|
test "v3 a future source does not repair a missing-source observation retroactively" {
  let result = v3_test_check(
    v3_test_trace([
      { "kind": "begin", "tx": "R", "connection": "cr" },
      { "kind": "read", "tx": "R", "key": "x", "version": "x1" },
      { "kind": "commit_request", "tx": "R" },
      { "kind": "commit_ok", "tx": "R" },
      { "kind": "begin", "tx": "W", "connection": "cw" },
      {
        "kind": "write",
        "tx": "W",
        "key": "x",
        "version": "x1",
        "predecessor": "x0",
      },
      { "kind": "commit_request", "tx": "W" },
      { "kind": "commit_ok", "tx": "W" },
    ]),
    "inconclusive",
  )
  assert_true(v3_test_has_gap(result, "missing_version_source"))
}

///|
test "v3 external aborted and intermediate sources remain facts with a coverage gap" {
  for outcome in ["rollback_ok", "commit_ok"] {
    let body : Array[Json] = [
      { "kind": "begin", "tx": "W", "connection": "cw" },
      {
        "kind": "write",
        "tx": "W",
        "key": "x",
        "version": "x1",
        "predecessor": "x0",
      },
    ]
    if outcome == "commit_ok" {
      body.push({
        "kind": "write",
        "tx": "W",
        "key": "x",
        "version": "x2",
        "predecessor": "x1",
      })
      body.push({ "kind": "commit_request", "tx": "W" })
    }
    body.push({ "kind": Json(outcome), "tx": "W" })
    body.push({ "kind": "begin", "tx": "R", "connection": "cr" })
    body.push({ "kind": "read", "tx": "R", "key": "x", "version": "x1" })
    body.push({ "kind": "commit_request", "tx": "R" })
    body.push({ "kind": "commit_ok", "tx": "R" })
    let result = v3_test_check(v3_test_trace(body), "inconclusive")
    assert_true(v3_test_has_gap(result, "unsafe_read_source"))
  }
}

///|
test "v3 own read inconsistency is retained rather than declared a malformed trace" {
  let result = v3_test_check(
    v3_test_completed([
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "x1",
        "predecessor": "x0",
      },
      { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
    ]),
    "inconclusive",
  )
  assert_true(v3_test_has_gap(result, "own_read_mismatch"))
}

///|
test "v3 own revoked version cannot be read after restoring the prior state" {
  let result = v3_test_check(
    v3_test_completed([
      { "kind": "savepoint", "tx": "A", "name": "s", "instance": "s1" },
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "x1",
        "predecessor": "x0",
      },
      { "kind": "rollback_to", "tx": "A", "instance": "s1" },
      { "kind": "read", "tx": "A", "key": "x", "version": "x1" },
    ]),
    "inconclusive",
  )
  assert_true(v3_test_has_gap(result, "own_read_mismatch"))
}

///|
test "v3 globally reused versions and cross-key predecessor claims are invalid" {
  let _ = v3_test_check(
    v3_test_completed([
      {
        "kind": "write",
        "tx": "A",
        "key": "y",
        "version": "x0",
        "predecessor": "y0",
      },
    ]),
    "invalid",
  )
  let _ = v3_test_check(
    v3_test_completed([
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "x1",
        "predecessor": "y0",
      },
    ]),
    "invalid",
  )
}

///|
test "v3 committed predecessor forks are not sorted by client event order" {
  let result = v3_test_check(
    v3_test_trace([
      { "kind": "begin", "tx": "A", "connection": "ca" },
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "x1",
        "predecessor": "x0",
      },
      { "kind": "commit_request", "tx": "A" },
      { "kind": "commit_ok", "tx": "A" },
      { "kind": "begin", "tx": "B", "connection": "cb" },
      {
        "kind": "write",
        "tx": "B",
        "key": "x",
        "version": "x2",
        "predecessor": "x0",
      },
      { "kind": "commit_request", "tx": "B" },
      { "kind": "commit_ok", "tx": "B" },
    ]),
    "inconclusive",
  )
  assert_true(v3_test_has_gap(result, "version_order_gap"))
}

///|
test "v3 missing initialized keys and version sources remain incomplete" {
  let result = v3_test_check(
    v3_test_completed([
      { "kind": "read", "tx": "A", "key": "z", "version": "z0" },
    ]),
    "inconclusive",
  )
  assert_true(v3_test_has_gap(result, "missing_initial"))
  assert_true(v3_test_has_gap(result, "missing_version_source"))
}

///|
test "v3 conditions are preserved separately and never fabricated into read operations" {
  let result = v3_test_check(
    v3_test_completed([
      {
        "kind": "condition",
        "tx": "A",
        "predicate": { "eq": ["owner", "a"] },
        "matched": false,
        "sourceVersion": "x0",
      },
    ]),
    "inconclusive",
  )
  assert_true(v3_test_has_gap(result, "unsupported_condition"))
  assert_eq(v3_test_items(result, "effects").length(), 0)
}

///|
test "v3 complete raw rows do not prove a SQL semantic mapping" {
  let result = v3_test_check(
    v3_test_completed([
      { "kind": "statement", "tx": "A", "sql": "SELECT 1", "parameters": [] },
      {
        "kind": "rows",
        "tx": "A",
        "statement": 3,
        "rows": [[1]],
        "complete": true,
      },
    ]),
    "inconclusive",
  )
  assert_true(v3_test_has_gap(result, "unmapped_statement"))
}

///|
test "v3 row chunks require a preceding statement of the same transaction" {
  let _ = v3_test_check(
    v3_test_completed([
      {
        "kind": "rows",
        "tx": "A",
        "statement": 1,
        "rows": [],
        "complete": true,
      },
    ]),
    "invalid",
  )
  let _ = v3_test_check(
    v3_test_trace([
      { "kind": "begin", "tx": "A", "connection": "ca" },
      { "kind": "statement", "tx": "A", "sql": "SELECT 1" },
      { "kind": "begin", "tx": "B", "connection": "cb" },
      {
        "kind": "rows",
        "tx": "B",
        "statement": 3,
        "rows": [],
        "complete": true,
      },
    ]),
    "invalid",
  )
}

///|
test "v3 unconsumed rows and rows after exhaustion cannot become complete histories" {
  let result = v3_test_check(
    v3_test_completed([
      { "kind": "statement", "tx": "A", "sql": "SELECT 1" },
      {
        "kind": "rows",
        "tx": "A",
        "statement": 3,
        "rows": [[1]],
        "complete": false,
      },
    ]),
    "inconclusive",
  )
  assert_true(v3_test_has_gap(result, "incomplete_rows"))
  let _ = v3_test_check(
    v3_test_completed([
      { "kind": "statement", "tx": "A", "sql": "SELECT 1" },
      {
        "kind": "rows",
        "tx": "A",
        "statement": 3,
        "rows": [[1]],
        "complete": true,
      },
      {
        "kind": "rows",
        "tx": "A",
        "statement": 3,
        "rows": [[2]],
        "complete": true,
      },
    ]),
    "invalid",
  )
}

///|
test "v3 sequence gaps preserve observations while reversed clocks and unknown kinds are invalid" {
  let gap = v3_test_completed([])
  object_fields_unchecked_v3(v3_test_items(gap, "events")[3])["seq"] = Json(5)
  let _ = v3_test_check(gap, "inconclusive")
  let clock = v3_test_completed([])
  object_fields_unchecked_v3(v3_test_items(clock, "events")[3])["time"] = Json(
    0,
  )
  let _ = v3_test_check(clock, "invalid")
  let _ = v3_test_check(
    v3_test_completed([{ "kind": "magic", "tx": "A" }]),
    "invalid",
  )
}

///|
test "v3 inconsistent snapshots open writer scope and explicit gaps forbid projection" {
  let snapshot = v3_test_completed([])
  object_fields_unchecked_v3(v3_test_items(snapshot, "events")[0])["consistent"] = Json(
    false,
  )
  let _ = v3_test_check(snapshot, "inconclusive")
  let scope = v3_test_completed([])
  object_fields_unchecked_v3(capture_field(scope, "scope"))["exclusiveWriters"] = Json(
    false,
  )
  let _ = v3_test_check(scope, "inconclusive")
  let explicit = v3_test_completed([])
  object_fields_unchecked_v3(explicit)["gaps"] = Json([
    capture_gap("test", "Missing source segment"),
  ])
  let _ = v3_test_check(explicit, "inconclusive")
}

///|
test "v3 rejects duplicate JSON keys and unsupported event fields without using legacy parser acceptance" {
  let fixture = v3_test_completed([])
  let duplicate = fixture
    .stringify()
    .replace(old="\"traceSchema\":3", new="\"traceSchema\":3,\"traceSchema\":3")
  let result = @json.parse(normalize_capture_v3_json(duplicate))
  assert_eq(capture_field(result, "status"), Json("invalid"))
  let wrong = v3_test_completed([])
  object_fields_unchecked_v3(v3_test_items(wrong, "events")[1])["extra"] = Json(
    true,
  )
  let _ = v3_test_check(wrong, "invalid")
}

///|
test "v3 savepoint nesting has an explicit resource bound" {
  let body : Array[Json] = []
  for index in 0..<65 {
    body.push({
      "kind": "savepoint",
      "tx": "A",
      "name": Json("name" + index.to_string()),
      "instance": Json("s" + index.to_string()),
    })
  }
  let _ = v3_test_check(v3_test_completed(body), "invalid")
}
