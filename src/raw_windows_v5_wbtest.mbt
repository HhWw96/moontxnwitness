///|
fn raw5_trace(
  model : DataModelV4,
  body : Array[Json],
  missing~ : Array[Int32] = [],
  explicit_gap~ : Bool = false,
) -> HistoryV4 {
  let initial : Json = if model == RegisterV4 {
    { "x": "x0" }
  } else {
    { "x": [] }
  }
  let events : Array[Json] = [
    { "kind": "snapshot", "initial": initial, "consistent": true },
  ]
  events.append(body)
  for i, e in events {
    let f = object_fields_unchecked_v3(e)
    f["seq"] = Json(i + 1)
    f["time"] = Json(i)
  }
  let raw : Json = {
    "traceSchema": 3,
    "dataModel": Json(v4_model_name(model)),
    "clockDomain": "raw-window-v5",
    "scope": { "exclusiveWriters": true },
    "events": Json(
      events.filter(e => {
        !missing.contains(rcl_number(relation_classification_at_v4(e, ["seq"])))
      }),
    ),
    "gaps": if explicit_gap {
      Json([({ "code": "lost-window", "message": "unknown location" } : Json)])
    } else {
      Json(([] : Array[Json]))
    },
  }
  parse_history_v4(raw.stringify()).unwrap()
}

///|
fn raw5_begin(tx : String) -> Json {
  { "kind": "begin", "tx": Json(tx), "connection": Json(tx) }
}

///|
fn raw5_write(tx : String, v : String, p : String) -> Json {
  {
    "kind": "write",
    "tx": Json(tx),
    "key": "x",
    "version": Json(v),
    "predecessor": Json(p),
  }
}

///|
fn raw5_read(tx : String, v : String) -> Json {
  { "kind": "read", "tx": Json(tx), "key": "x", "version": Json(v) }
}

///|
fn raw5_mark(tx : String) -> Json {
  { "kind": "savepoint", "tx": Json(tx), "name": "s", "instance": "s1" }
}

///|
fn raw5_undo(tx : String) -> Json {
  { "kind": "rollback_to", "tx": Json(tx), "instance": "s1" }
}

///|
fn raw5_commit(events : Array[Json], tx : String) -> Unit {
  events.push({ "kind": "commit_request", "tx": Json(tx) })
  events.push({ "kind": "commit_ok", "tx": Json(tx) })
}

///|
fn raw5_producer() -> Array[Json] {
  let body = [
    raw5_begin("P"),
    raw5_write("P", "p1", "x0"),
    raw5_mark("P"),
    raw5_write("P", "p2", "p1"),
    raw5_undo("P"),
  ]
  raw5_commit(body, "P")
  body.push(raw5_begin("R"))
  body.push(raw5_read("R", "p1"))
  raw5_commit(body, "R")
  body
}

///|
fn raw5_report(history : HistoryV4) -> Json {
  capture_anomalies_v4_json(inspect_capture_anomalies_v4(history))
}

///|
test "raw window v5 01 missing rollback cannot assert intermediate register source" {
  let body = raw5_producer()
  assert_eq(
    cap034_find(raw5_report(raw5_trace(RegisterV4, body)), "G1b").length(),
    0,
  )
  let gap = raw5_report(raw5_trace(RegisterV4, body, missing=[6]))
  assert_eq(v4_test_at(gap, ["status"]), Json("unknown"))
  assert_eq(cap034_find(gap, "G1b").length(), 0)
}

///|
test "raw window v5 02 unmapped rollback SQL cannot be silently ignored for finality" {
  let body = raw5_producer()
  body[4] = { "kind": "statement", "tx": "P", "sql": "ROLLBACK TO SAVEPOINT s" }
  let report = raw5_report(raw5_trace(RegisterV4, body))
  assert_eq(v4_test_at(report, ["status"]), Json("unknown"))
  assert_eq(cap034_find(report, "G1b").length(), 0)
}

///|
test "raw window v5 03 explicit unlocated gaps prevent finality claims" {
  let body = [
    raw5_begin("P"),
    raw5_write("P", "p1", "x0"),
    raw5_write("P", "p2", "p1"),
  ]
  raw5_commit(body, "P")
  body.push(raw5_begin("R"))
  body.push(raw5_read("R", "p1"))
  raw5_commit(body, "R")
  assert_eq(
    cap034_find(raw5_report(raw5_trace(RegisterV4, body)), "G1b").length(),
    1,
  )
  assert_eq(
    cap034_find(
      raw5_report(raw5_trace(RegisterV4, body, explicit_gap=true)),
      "G1b",
    ).length(),
    0,
  )
}

///|
test "raw window v5 04 confirmed abort survives producer hole without trusting ledger" {
  let body = [
    raw5_begin("P"),
    raw5_read("P", "x0"),
    raw5_write("P", "p1", "x0"),
    ({ "kind": "rollback_ok", "tx": "P" } : Json),
    raw5_begin("R"),
    raw5_read("R", "p1"),
  ]
  raw5_commit(body, "R")
  let report = raw5_report(raw5_trace(RegisterV4, body, missing=[3]))
  let findings = cap034_find(report, "G1a")
  assert_eq(findings.length(), 1)
  assert_eq(
    v4_test_at(findings[0], ["evidence", "sourceEffect", "writeJournalComplete"]),
    Json(false),
  )
  assert_eq(
    v4_test_at(findings[0], ["evidence", "sourceEffect", "outcome"]),
    Json("aborted"),
  )
}

///|
test "raw window v5 05 confirmed abort survives unlocated gap for immutable actual read" {
  let body = [
    raw5_begin("P"),
    raw5_write("P", "p1", "x0"),
    ({ "kind": "rollback_ok", "tx": "P" } : Json),
    raw5_begin("R"),
    raw5_read("R", "p1"),
  ]
  raw5_commit(body, "R")
  assert_eq(
    cap034_find(
      raw5_report(raw5_trace(RegisterV4, body, explicit_gap=true)),
      "G1a",
    ).length(),
    1,
  )
}

///|
test "raw window v5 06 actual dirty write requires its own survival window" {
  let body = [
    raw5_begin("P"),
    raw5_write("P", "p1", "x0"),
    ({ "kind": "rollback_ok", "tx": "P" } : Json),
    raw5_begin("W"),
    raw5_mark("W"),
    raw5_write("W", "w1", "p1"),
    raw5_undo("W"),
  ]
  raw5_commit(body, "W")
  assert_eq(
    cap034_find(raw5_report(raw5_trace(RegisterV4, body)), "dirty-update").length(),
    0,
  )
  assert_eq(
    cap034_find(
      raw5_report(raw5_trace(RegisterV4, body, missing=[8])),
      "dirty-update",
    ).length(),
    0,
  )
}

///|
test "raw window v5 07 confirmed abort and closed observer still proves actual dirty input" {
  let body = [
    raw5_begin("P"),
    raw5_read("P", "x0"),
    raw5_write("P", "p1", "x0"),
    ({ "kind": "rollback_ok", "tx": "P" } : Json),
    raw5_begin("W"),
    raw5_write("W", "w1", "p1"),
  ]
  raw5_commit(body, "W")
  assert_eq(
    cap034_find(
      raw5_report(raw5_trace(RegisterV4, body, missing=[3])),
      "dirty-update",
    ).length(),
    1,
  )
}

///|
test "raw window v5 08 revocation after unknown SQL is not an original confirmed abort" {
  let body = raw5_producer()
  body.insert(
    4,
    (
      { "kind": "statement", "tx": "P", "sql": "SELECT unknown_scope_change()" } :
      Json),
  )
  let report = raw5_report(raw5_trace(RegisterV4, body))
  assert_eq(cap034_find(report, "G1a").length(), 0)
  assert_eq(cap034_find(report, "G1b").length(), 0)
}

///|
test "raw window v5 09 closed producer G1b is not erased by later unrelated hole" {
  let body = [
    raw5_begin("P"),
    raw5_write("P", "p1", "x0"),
    raw5_write("P", "p2", "p1"),
  ]
  raw5_commit(body, "P")
  body.push(raw5_begin("N"))
  body.push(raw5_read("N", "x0"))
  raw5_commit(body, "N")
  body.push(raw5_begin("R"))
  body.push(raw5_read("R", "p1"))
  raw5_commit(body, "R")
  let report = raw5_report(raw5_trace(RegisterV4, body, missing=[8]))
  assert_eq(cap034_find(report, "G1b").length(), 1)
}

///|
fn raw5_internal_body(model : DataModelV4) -> Array[Json] {
  let body = [raw5_begin("A"), raw5_mark("A")]
  if model == RegisterV4 {
    body.push(raw5_write("A", "a", "x0"))
    body.push(raw5_read("A", "a"))
  } else {
    body.push({
      "kind": "append",
      "tx": "A",
      "key": "x",
      "id": "a",
      "value": "same",
    })
    body.push({
      "kind": "list_read",
      "tx": "A",
      "key": "x",
      "items": [{ "id": "a", "value": "same" }],
    })
  }
  body.push(raw5_undo("A"))
  if model == RegisterV4 {
    body.push(raw5_read("A", "x0"))
  } else {
    body.push({ "kind": "list_read", "tx": "A", "key": "x", "items": [] })
  }
  raw5_commit(body, "A")
  body
}

///|
test "raw window v5 10 register missing rollback does not invent INT" {
  let body = raw5_internal_body(RegisterV4)
  let control = internal_consistency_v4_json(
    inspect_internal_consistency_v4(raw5_trace(RegisterV4, body)),
  )
  let gapped = internal_consistency_v4_json(
    inspect_internal_consistency_v4(raw5_trace(RegisterV4, body, missing=[6])),
  )
  assert_eq(v4_test_at(control, ["status"]), Json("checked"))
  assert_eq(v4_test_at(gapped, ["status"]), Json("unknown"))
}

///|
test "raw window v5 11 list missing rollback does not invent own-suffix INT" {
  let body = raw5_internal_body(AppendListV4)
  let control = internal_consistency_v4_json(
    inspect_internal_consistency_v4(raw5_trace(AppendListV4, body)),
  )
  let gapped = internal_consistency_v4_json(
    inspect_internal_consistency_v4(raw5_trace(AppendListV4, body, missing=[6])),
  )
  assert_eq(v4_test_at(control, ["status"]), Json("checked"))
  assert_eq(v4_test_at(gapped, ["status"]), Json("unknown"))
}

///|
test "raw window v5 12 earlier raw INT survives later sequence loss" {
  let body = [
    raw5_begin("A"),
    raw5_write("A", "a", "x0"),
    raw5_read("A", "x0"),
    raw5_read("A", "x0"),
  ]
  raw5_commit(body, "A")
  let report = internal_consistency_v4_json(
    inspect_internal_consistency_v4(raw5_trace(RegisterV4, body, missing=[5])),
  )
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
}

///|
fn raw5_list_producer() -> Array[Json] {
  let body = [
    raw5_begin("P"),
    (
      { "kind": "append", "tx": "P", "key": "x", "id": "p1", "value": "same" } :
      Json),
    raw5_mark("P"),
    (
      { "kind": "append", "tx": "P", "key": "x", "id": "p2", "value": "same" } :
      Json),
    raw5_undo("P"),
  ]
  raw5_commit(body, "P")
  body.push(raw5_begin("R"))
  body.push({
    "kind": "list_read",
    "tx": "R",
    "key": "x",
    "items": [{ "id": "p1", "value": "same" }],
  })
  raw5_commit(body, "R")
  body
}

///|
test "raw window v5 13 list missing rollback cannot assert intermediate append source" {
  let body = raw5_list_producer()
  assert_eq(
    cap034_find(raw5_report(raw5_trace(AppendListV4, body)), "G1b").length(),
    0,
  )
  let gap = raw5_report(raw5_trace(AppendListV4, body, missing=[6]))
  assert_eq(v4_test_at(gap, ["status"]), Json("unknown"))
  assert_eq(cap034_find(gap, "G1b").length(), 0)
  body[4] = { "kind": "statement", "tx": "P", "sql": "ROLLBACK TO SAVEPOINT s" }
  assert_eq(
    cap034_find(raw5_report(raw5_trace(AppendListV4, body)), "G1b").length(),
    0,
  )
}

///|
test "raw window v5 14 untrusted derived revocation cannot assert aborted read or dirty update" {
  let body = raw5_producer()
  // The hidden operation may change savepoint identity before the observed undo.
  body.insert(4, raw5_read("P", "p2"))
  body[9] = raw5_read("R", "p2")
  let read_gap = raw5_report(raw5_trace(RegisterV4, body, missing=[6]))
  assert_eq(cap034_find(read_gap, "G1a").length(), 0)
  body[9] = raw5_write("R", "r1", "p2")
  let write_gap = raw5_report(raw5_trace(RegisterV4, body, missing=[6]))
  assert_eq(cap034_find(write_gap, "dirty-update").length(), 0)
}

///|
test "raw window v5 15 known rollback prefix remains evidence before later unknown producer end" {
  let body = [
    raw5_begin("P"),
    raw5_mark("P"),
    raw5_write("P", "p1", "x0"),
    raw5_undo("P"),
    raw5_read("P", "x0"),
    ({ "kind": "disconnect", "tx": "P" } : Json),
    raw5_begin("R"),
    raw5_read("R", "p1"),
  ]
  raw5_commit(body, "R")
  let report = raw5_report(raw5_trace(RegisterV4, body, missing=[6]))
  assert_eq(cap034_find(report, "G1a").length(), 1)
  assert_eq(
    v4_test_at(cap034_find(report, "G1a")[0], [
      "evidence", "sourceEffect", "writeJournalComplete",
    ]),
    Json(false),
  )
  assert_eq(
    v4_test_at(cap034_find(report, "G1a")[0], [
      "evidence", "sourceEffect", "revocationKnown",
    ]),
    Json(true),
  )
}

///|
test "raw window v5 16 unmapped SQL and unlocated gaps block standalone register and list INT" {
  for model in [RegisterV4, AppendListV4] {
    let body = raw5_internal_body(model)
    body[4] = {
      "kind": "statement",
      "tx": "A",
      "sql": "ROLLBACK TO SAVEPOINT s",
    }
    let unproved = internal_consistency_v4_json(
      inspect_internal_consistency_v4(raw5_trace(model, body)),
    )
    assert_eq(v4_test_at(unproved, ["status"]), Json("unknown"))
    assert_eq(v4_test_at(unproved, ["findings"]), Json(([] : Array[Json])))
    let root_gap = internal_consistency_v4_json(
      inspect_internal_consistency_v4(
        raw5_trace(model, raw5_internal_body(model), explicit_gap=true),
      ),
    )
    assert_eq(v4_test_at(root_gap, ["status"]), Json("unknown"))
    assert_eq(v4_test_at(root_gap, ["findings"]), Json(([] : Array[Json])))
  }
}

///|
test "raw window v5 17 zero budget cannot invent a reliable aborted source proof" {
  let body = [
    raw5_begin("P"),
    raw5_write("P", "p1", "x0"),
    ({ "kind": "rollback_ok", "tx": "P" } : Json),
    raw5_begin("R"),
    raw5_read("R", "p1"),
  ]
  raw5_commit(body, "R")
  let history = raw5_trace(RegisterV4, body)
  let zero = capture_anomalies_v4_json(
    inspect_capture_anomalies_v4(history, max_checks=0),
  )
  assert_eq(v4_test_at(zero, ["status"]), Json("unknown"))
  assert_eq(cap034_find(zero, "G1a").length(), 0)
  assert_eq(v4_test_at(zero, ["execution", "checks"]), Json(0))
}

///|
test "raw window v5 18 reliable proof survives later source budget exhaustion" {
  let body = [
    raw5_begin("P"),
    raw5_write("P", "p1", "x0"),
    ({ "kind": "rollback_ok", "tx": "P" } : Json),
    raw5_begin("R"),
    raw5_read("R", "p1"),
  ]
  raw5_commit(body, "R")
  body.push(raw5_begin("N"))
  body.push(raw5_read("N", "x0"))
  raw5_commit(body, "N")
  let history = raw5_trace(RegisterV4, body)
  let full = raw5_report(history)
  let total = rcl_number(v4_test_at(full, ["execution", "checks"]))
  let mut retained = false
  for budget in 1..<total {
    let report = capture_anomalies_v4_json(
      inspect_capture_anomalies_v4(history, max_checks=budget),
    )
    if !cap034_find(report, "G1a").is_empty() &&
      v4_test_at(report, ["coverage", "complete"]) == Json(false) {
      assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
      retained = true
      break
    }
  }
  assert_true(retained)
}
