///|
/// New fixed-expectation direct-list regressions. The original 42 tests and
/// independent first/addon expectations remain unchanged in their own files.
fn classification26_source_interleaved(
  own : Bool,
  aborted : Bool,
  read_final : Bool,
) -> Json {
  let body : Array[Json] = [{ "kind": "begin", "tx": "W", "connection": "w" }]
  if !own {
    body.push({ "kind": "begin", "tx": "C", "connection": "c" })
  }
  body.push({ "kind": "begin", "tx": "R", "connection": "r" })
  body.push({
    "kind": "append",
    "tx": "W",
    "key": "x",
    "id": "a",
    "value": "same",
  })
  body.push({
    "kind": "append",
    "tx": Json(if own { "R" } else { "C" }),
    "key": "x",
    "id": "c",
    "value": "same",
  })
  if read_final {
    body.push({
      "kind": "append",
      "tx": "W",
      "key": "x",
      "id": "b",
      "value": "same",
    })
  }
  let items : Array[Json] = [
    { "id": "a", "value": "same" },
    { "id": "c", "value": "same" },
  ]
  if read_final {
    items.push({ "id": "b", "value": "same" })
  }
  body.push({ "kind": "list_read", "tx": "R", "key": "x", "items": Json(items) })
  if !read_final {
    body.push({
      "kind": "append",
      "tx": "W",
      "key": "x",
      "id": "b",
      "value": "same",
    })
  }
  body.push({ "kind": "commit_request", "tx": "W" })
  body.push({ "kind": "commit_ok", "tx": "W" })
  if !own {
    if aborted {
      body.push({ "kind": "rollback_ok", "tx": "C" })
    } else {
      body.push({ "kind": "commit_request", "tx": "C" })
      body.push({ "kind": "commit_ok", "tx": "C" })
    }
  }
  body.push({ "kind": "commit_request", "tx": "R" })
  body.push({ "kind": "commit_ok", "tx": "R" })
  classification26_test_list(body)
}

///|
fn classification26_source_prefix(aborted : Bool, observed : String) -> Json {
  let body : Array[Json] = [
    { "kind": "begin", "tx": "W", "connection": "w" },
    { "kind": "append", "tx": "W", "key": "x", "id": "a", "value": "same" },
    { "kind": "append", "tx": "W", "key": "x", "id": "b", "value": "same" },
  ]
  if aborted {
    body.push({ "kind": "rollback_ok", "tx": "W" })
  } else {
    body.push({ "kind": "commit_request", "tx": "W" })
    body.push({ "kind": "commit_ok", "tx": "W" })
  }
  let items : Array[Json] = []
  for item in observed.iter() {
    items.push({ "id": Json(item.to_string()), "value": "same" })
  }
  body.push({ "kind": "begin", "tx": "R", "connection": "r" })
  body.push({ "kind": "list_read", "tx": "R", "key": "x", "items": Json(items) })
  body.push({ "kind": "commit_request", "tx": "R" })
  body.push({ "kind": "commit_ok", "tx": "R" })
  classification26_test_list(body)
}

///|
test "classification26 source final external last append does not read an earlier writer intermediate version" {
  let report = classification26_test_report(
    classification26_source_interleaved(false, false, false),
  )
  assert_eq(
    capture_field(classification_test_rule(report, "G1b"), "status"),
    Json("checked-compatible"),
  )
  assert_true(v3_test_items(report, "validityGaps").is_empty())
}

///|
test "classification26 source own last append does not create external G1b" {
  let report = classification26_test_report(
    classification26_source_interleaved(true, false, false),
  )
  assert_eq(
    capture_field(classification_test_rule(report, "G1b"), "status"),
    Json("checked-compatible"),
  )
  assert_eq(
    capture_field(classification_test_rule(report, "INT"), "status"),
    Json("checked-compatible"),
  )
}

///|
test "classification26 source aborted final last append preserves G1a without adding false G1b" {
  let report = classification26_test_report(
    classification26_source_interleaved(false, true, false),
  )
  assert_eq(
    capture_field(classification_test_rule(report, "G1a"), "status"),
    Json("refuted"),
  )
  assert_true(
    capture_field(classification_test_rule(report, "G1b"), "status") !=
    Json("refuted"),
  )
  let proof = capture_field(classification_test_rule(report, "G1a"), "evidence")
  assert_eq(capture_field(capture_field(proof, "source"), "id"), Json("c"))
}

///|
test "classification26 source actual intermediate last append retains specific G1b witness" {
  let trace = classification26_source_prefix(false, "a")
  let report = classification26_test_report(trace)
  assert_eq(
    capture_field(classification_test_rule(report, "G1b"), "status"),
    Json("refuted"),
  )
  let proof = capture_field(classification_test_rule(report, "G1b"), "evidence")
  assert_eq(capture_field(proof, "lastObservedItem"), Json("a"))
  assert_eq(capture_field(capture_field(proof, "source"), "id"), Json("a"))
  assert_eq(
    capture_field(
      @json.parse(
        verify_classification_v3_json(trace.stringify(), report.stringify()),
      ),
      "valid",
    ),
    Json(true),
  )
}

///|
test "classification26 source final complete list value does not become intermediate read" {
  let report = classification26_test_report(
    classification26_source_prefix(false, "ab"),
  )
  assert_eq(
    capture_field(classification_test_rule(report, "G1b"), "status"),
    Json("checked-compatible"),
  )
  assert_true(v3_test_items(report, "validityGaps").is_empty())
}

///|
test "classification26 source incomplete or reversed external producer prefix is explicit unknown" {
  for observed in ["b", "ba"] {
    let report = classification26_test_report(
      classification26_source_prefix(false, observed),
    )
    assert_true(!v3_test_items(report, "validityGaps").is_empty())
    for rule in ["G1a", "G1b", "INT"] {
      assert_eq(
        capture_field(classification_test_rule(report, rule), "status"),
        Json("unknown"),
      )
    }
    assert_eq(capture_field(report, "dependencyGraphComplete"), Json(false))
  }
}

///|
test "classification26 source malformed producer prefix does not erase matching aborted item G1a" {
  for observed in ["b", "ba"] {
    let trace = classification26_source_prefix(true, observed)
    let report = classification26_test_report(trace)
    assert_true(!v3_test_items(report, "validityGaps").is_empty())
    assert_eq(
      capture_field(classification_test_rule(report, "G1a"), "status"),
      Json("refuted"),
    )
    for rule in ["G1b", "INT"] {
      assert_eq(
        capture_field(classification_test_rule(report, rule), "status"),
        Json("unknown"),
      )
    }
    assert_eq(
      capture_field(
        classification26_test_model(report, "adya-pl-2-v1"),
        "status",
      ),
      Json("refuted"),
    )
    assert_eq(
      capture_field(
        @json.parse(
          verify_classification_v3_json(trace.stringify(), report.stringify()),
        ),
        "valid",
      ),
      Json(true),
    )
  }
}

///|
test "classification26 source initial prefix gap also cannot erase independent aborted item proof" {
  let trace = classification26_source_prefix(true, "b")
  object_fields_unchecked_v3(v3_test_items(trace, "events")[0])["initial"] = {
    "x": [{ "id": "ix", "value": "initial" }],
    "y": [],
  }
  let report = classification26_test_report(trace)
  assert_true(!v3_test_items(report, "validityGaps").is_empty())
  assert_eq(
    capture_field(classification_test_rule(report, "G1a"), "status"),
    Json("refuted"),
  )
  assert_eq(
    capture_field(classification_test_rule(report, "G1b"), "status"),
    Json("unknown"),
  )
}

///|
test "classification26 source wrong key or wrong business value cannot prove aborted item read" {
  for mismatch in ["key", "value"] {
    let trace = classification26_source_prefix(true, "a")
    for raw in v3_test_items(trace, "events") {
      let event = object_fields_unchecked_v3(raw)
      if event.get("kind") != Some(Json("list_read")) {
        continue
      }
      if mismatch == "key" {
        event["key"] = Json("y")
      } else {
        object_fields_unchecked_v3(v3_test_items(raw, "items")[0])["value"] = Json(
          "forged",
        )
      }
    }
    let report = classification26_test_report(trace)
    assert_true(
      capture_field(classification_test_rule(report, "G1a"), "status") !=
      Json("refuted"),
    )
  }
}

///|
test "classification26 source unrelated mismatching item does not erase a matching aborted item" {
  let trace = classification26_source_interleaved(false, true, false)
  for raw in v3_test_items(trace, "events") {
    if capture_field(raw, "kind") == Json("list_read") {
      object_fields_unchecked_v3(v3_test_items(raw, "items")[0])["value"] = Json(
        "forged",
      )
    }
  }
  let report = classification26_test_report(trace)
  assert_eq(
    capture_field(classification_test_rule(report, "G1a"), "status"),
    Json("refuted"),
  )
  assert_true(
    capture_field(classification_test_rule(report, "G1b"), "status") !=
    Json("refuted"),
  )
}
