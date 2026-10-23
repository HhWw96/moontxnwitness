///| Independent handoff counterexamples: initial prefix validity is a prerequisite
/// for deriving list dependency edges, not a graph anomaly inferred from absence.
fn classification26_audit_prefix_trace(reordered : Bool, valid : Bool) -> Json raise {
  let trace = classification26_test_list_skew()
  let events = v3_test_items(trace, "events")
  let first_x : Json = { "id": "ix", "value": "initial-x" }
  let second_x : Json = { "id": "ix2", "value": "initial-x2" }
  let first_y : Json = { "id": "iy", "value": "initial-y" }
  let second_y : Json = { "id": "iy2", "value": "initial-y2" }
  object_fields_unchecked_v3(events[0])["initial"] = if reordered {
    { "x": [first_x, second_x], "y": [first_y, second_y] }
  } else { { "x": [first_x], "y": [first_y] } }
  if reordered {
    object_fields_unchecked_v3(events[3])["items"] = [second_y, first_y].to_json()
    object_fields_unchecked_v3(events[4])["items"] = [second_x, first_x].to_json()
  } else if valid {
    object_fields_unchecked_v3(events[3])["items"] = [first_y].to_json()
    object_fields_unchecked_v3(events[4])["items"] = [first_x].to_json()
  }
  trace
}

///|
test "classification26 audit missing initial prefix cannot supply a false list cycle" {
  let trace = classification26_audit_prefix_trace(false, false)
  let normalized = @json.parse(normalize_capture_v3_json(trace.stringify()))
  assert_eq(capture_field(normalized, "status"), "ready".to_json())
  let graph = classification_models_v3_list(trace.stringify(), normalized)
  assert_eq(graph.complete, false)
  assert_true(graph.edges.is_empty())
  let report = classification26_test_report(trace)
  assert_true(!v3_test_items(report, "validityGaps").is_empty())
  for category in ["G0", "G1c", "G2-item", "G-nonadjacent"] {
    assert_eq(capture_field(classification_test_rule(report, category), "status"), "unknown".to_json())
  }
  assert_eq(capture_field(report, "status"), "inconclusive".to_json())
}

///|
test "classification26 audit reordered initial prefix cannot supply a false list cycle" {
  let trace = classification26_audit_prefix_trace(true, false)
  let normalized = @json.parse(normalize_capture_v3_json(trace.stringify()))
  let graph = classification_models_v3_list(trace.stringify(), normalized)
  assert_eq(graph.complete, false)
  assert_true(graph.edges.is_empty())
  let report = classification26_test_report(trace)
  assert_true(!v3_test_items(report, "validityGaps").is_empty())
  assert_eq(capture_field(classification26_test_model(report, "adya-pl-3-v1"), "status"), "inconclusive".to_json())
}

///|
test "classification26 audit valid initial prefix preserves actual list write skew refutation" {
  let trace = classification26_audit_prefix_trace(false, true)
  let report = classification26_test_report(trace)
  assert_eq(capture_field(classification26_test_model(report, "elle-generalized-si-v1"), "status"), "checked-compatible".to_json())
  assert_eq(capture_field(classification26_test_model(report, "adya-pl-3-v1"), "status"), "refuted".to_json())
}
///|
test "classification26 audit independent valid cycle survives another invalid list read" {
  let trace = classification26_test_list([
    { "kind": "begin", "tx": "A", "connection": "a" },
    { "kind": "begin", "tx": "B", "connection": "b" },
    { "kind": "list_read", "tx": "A", "key": "y", "items": [] },
    { "kind": "list_read", "tx": "B", "key": "x", "items": [] },
    { "kind": "append", "tx": "A", "key": "x", "id": "a", "value": "same" },
    { "kind": "append", "tx": "B", "key": "y", "id": "b", "value": "same" },
    { "kind": "commit_request", "tx": "A" }, { "kind": "commit_ok", "tx": "A" },
    { "kind": "commit_request", "tx": "B" }, { "kind": "commit_ok", "tx": "B" },
    { "kind": "begin", "tx": "R", "connection": "r" },
    { "kind": "list_read", "tx": "R", "key": "z", "items": [] },
    { "kind": "commit_request", "tx": "R" }, { "kind": "commit_ok", "tx": "R" },
  ])
  object_fields_unchecked_v3(v3_test_items(trace, "events")[0])["initial"] = { "x": [], "y": [], "z": [{ "id": "iz", "value": "initial-z" }] }
  let report = classification26_test_report(trace)
  assert_eq(capture_field(report, "dependencyGraphComplete"), false.to_json())
  assert_eq(v3_test_items(report, "validityGaps").length(), 1)
  assert_eq(v3_test_items(report, "dependencies").length(), 2)
  assert_eq(capture_field(classification_test_rule(report, "G2-item"), "status"), "refuted".to_json())
  assert_eq(capture_field(classification26_test_model(report, "adya-pl-3-v1"), "status"), "refuted".to_json())
  assert_eq(capture_field(capture_field(classification26_test_model(report, "adya-pl-3-v1"), "internalValidity"), "status"), "unknown".to_json())
}