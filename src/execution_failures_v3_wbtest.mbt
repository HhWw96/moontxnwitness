///|
fn execution_failure_trace_v3(state : Json) -> Json {
  v3_test_trace([
    { "kind": "begin", "tx": "A", "connection": "c" },
    { "kind": "statement", "tx": "A", "sql": "SELECT 1" },
    {
      "kind": "rows",
      "tx": "A",
      "statement": 3,
      "rows": [],
      "complete": false,
      "error": { "class": "RecordedDriverError", "sqlstate": state },
    },
    { "kind": "rollback_ok", "tx": "A" },
  ])
}

///|
fn execution_failure_expect_v3(state : Json, kind : String) -> Unit raise {
  let trace = execution_failure_trace_v3(state)
  let result = @json.parse(
    inspect_execution_failures_v3_json(trace.stringify()),
  )
  assert_eq(capture_field(result, "valid"), Json(true))
  assert_eq(capture_field(result, "modelViolationClaim"), Json(false))
  assert_eq(capture_field(result, "databaseAuthenticityVerified"), Json(false))
  assert_eq(capture_field(result, "certifiesFailureAbsence"), Json(false))
  assert_eq(capture_field(result, "observedFaultCount"), Json(1))
  let fault = v3_test_items(result, "faults")[0]
  assert_eq(capture_field(fault, "kind"), Json(kind))
  assert_eq(capture_field(fault, "sqlstate"), state)
  assert_eq(capture_field(fault, "seq"), Json(4))
  assert_eq(capture_field(fault, "statement"), Json(3))
  assert_eq(capture_field(fault, "origin"), Json("rows.error"))
}

///|
test "execution failures keep actual deadlock observations outside G2" {
  execution_failure_expect_v3(Json("40P01"), "deadlock")
}

///|
test "execution failures identify a serialization abort without isolation violation" {
  execution_failure_expect_v3(Json("40001"), "serialization_abort")
}

///|
test "execution failures preserve lock unavailable rather than claim deadlock" {
  execution_failure_expect_v3(Json("55P03"), "lock_not_available")
}

///|
test "execution failures do not infer timeout from query canceled" {
  execution_failure_expect_v3(Json("57014"), "query_canceled")
}

///|
test "execution failures retain other SQLSTATE as unclassified statement error" {
  execution_failure_expect_v3(Json("23505"), "statement_error")
}

///|
test "execution failures retain missing SQLSTATE without inventing classification" {
  execution_failure_expect_v3(Json::null(), "statement_error")
}

///|
test "execution failures empty observations do not certify absence of faults" {
  let trace = v3_test_completed([])
  let result = @json.parse(
    inspect_execution_failures_v3_json(trace.stringify()),
  )
  assert_eq(capture_field(result, "valid"), Json(true))
  assert_eq(capture_field(result, "captureStatus"), Json("ready"))
  assert_eq(capture_field(result, "observedFaultCount"), Json(0))
  assert_eq(capture_field(result, "certifiesFailureAbsence"), Json(false))
}

///|
test "execution failures malformed JSON fails validation" {
  let result = @json.parse(inspect_execution_failures_v3_json("{"))
  assert_eq(capture_field(result, "valid"), Json(false))
  assert_eq(capture_field(result, "status"), Json("invalid"))
}

///|
test "execution failures statement reference cannot be forged" {
  let trace = execution_failure_trace_v3(Json("40P01"))
  let events = v3_test_items(trace, "events")
  object_fields_unchecked_v3(events[3])["statement"] = Json(99)
  let result = @json.parse(
    inspect_execution_failures_v3_json(trace.stringify()),
  )
  assert_eq(capture_field(result, "valid"), Json(false))
}

///|
test "execution failures reused event identity is rejected" {
  let trace = execution_failure_trace_v3(Json("40P01"))
  let events = v3_test_items(trace, "events")
  object_fields_unchecked_v3(events[3])["seq"] = Json(3)
  let result = @json.parse(
    inspect_execution_failures_v3_json(trace.stringify()),
  )
  assert_eq(capture_field(result, "valid"), Json(false))
}

///|
fn execution_commit_failure_trace_v3(response : Json) -> Json {
  v3_test_trace([
    { "kind": "begin", "tx": "A", "connection": "c" },
    { "kind": "commit_request", "tx": "A" },
    { "kind": "rollback_ok", "tx": "A", "commitResponse": response },
  ])
}

///|
test "execution failures bind actual COMMIT ROLLBACK response" {
  let trace = execution_commit_failure_trace_v3({
    "request": 3,
    "commandTag": "ROLLBACK",
  })
  let result = @json.parse(
    inspect_execution_failures_v3_json(trace.stringify()),
  )
  assert_eq(capture_field(result, "valid"), Json(true))
  let fault = v3_test_items(result, "faults")[0]
  assert_eq(capture_field(fault, "kind"), Json("commit_rolled_back"))
  assert_eq(capture_field(fault, "request"), Json(3))
  assert_eq(capture_field(fault, "sqlstate"), Json::null())
}

///|
test "execution failures bind confirmed commit-time deadlock independently" {
  let trace = execution_commit_failure_trace_v3({
    "request": 3,
    "sqlstate": "40P01",
    "diagnosticSqlstate": "40P01",
    "transactionStatus": "IDLE",
  })
  let result = @json.parse(
    inspect_execution_failures_v3_json(trace.stringify()),
  )
  assert_eq(capture_field(result, "valid"), Json(true))
  let fault = v3_test_items(result, "faults")[0]
  assert_eq(capture_field(fault, "kind"), Json("deadlock"))
  assert_eq(capture_field(fault, "origin"), Json("rollback_ok.commitResponse"))
  assert_eq(capture_field(result, "modelViolationClaim"), Json(false))
}

///|
test "execution failures mismatched commit diagnostics are not accepted" {
  let trace = execution_commit_failure_trace_v3({
    "request": 3,
    "sqlstate": "40P01",
    "diagnosticSqlstate": "40001",
    "transactionStatus": "IDLE",
  })
  let result = @json.parse(
    inspect_execution_failures_v3_json(trace.stringify()),
  )
  assert_eq(capture_field(result, "valid"), Json(false))
}

///|
test "execution failures unknown commit remains unknown with no fabricated fault" {
  let trace = v3_test_trace([
    { "kind": "begin", "tx": "A", "connection": "c" },
    { "kind": "commit_request", "tx": "A" },
    { "kind": "disconnect", "tx": "A" },
  ])
  let result = @json.parse(
    inspect_execution_failures_v3_json(trace.stringify()),
  )
  assert_eq(capture_field(result, "valid"), Json(true))
  assert_eq(capture_field(result, "observedFaultCount"), Json(0))
  assert_eq(capture_field(result, "captureStatus"), Json("inconclusive"))
  let outcome = v3_test_items(result, "transactionOutcomes")[0]
  assert_eq(capture_field(outcome, "status"), Json("unknown"))
}
