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
  assert_eq(capture_field(result, "valid"), true.to_json())
  assert_eq(capture_field(result, "modelViolationClaim"), false.to_json())
  assert_eq(
    capture_field(result, "databaseAuthenticityVerified"),
    false.to_json(),
  )
  assert_eq(capture_field(result, "certifiesFailureAbsence"), false.to_json())
  assert_eq(capture_field(result, "observedFaultCount"), (1).to_json())
  let fault = v3_test_items(result, "faults")[0]
  assert_eq(capture_field(fault, "kind"), kind.to_json())
  assert_eq(capture_field(fault, "sqlstate"), state)
  assert_eq(capture_field(fault, "seq"), (4).to_json())
  assert_eq(capture_field(fault, "statement"), (3).to_json())
  assert_eq(capture_field(fault, "origin"), "rows.error".to_json())
}

///|
test "execution failures keep actual deadlock observations outside G2" {
  execution_failure_expect_v3("40P01".to_json(), "deadlock")
}

///|
test "execution failures identify a serialization abort without isolation violation" {
  execution_failure_expect_v3("40001".to_json(), "serialization_abort")
}

///|
test "execution failures preserve lock unavailable rather than claim deadlock" {
  execution_failure_expect_v3("55P03".to_json(), "lock_not_available")
}

///|
test "execution failures do not infer timeout from query canceled" {
  execution_failure_expect_v3("57014".to_json(), "query_canceled")
}

///|
test "execution failures retain other SQLSTATE as unclassified statement error" {
  execution_failure_expect_v3("23505".to_json(), "statement_error")
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
  assert_eq(capture_field(result, "valid"), true.to_json())
  assert_eq(capture_field(result, "captureStatus"), "ready".to_json())
  assert_eq(capture_field(result, "observedFaultCount"), (0).to_json())
  assert_eq(capture_field(result, "certifiesFailureAbsence"), false.to_json())
}

///|
test "execution failures malformed JSON fails validation" {
  let result = @json.parse(inspect_execution_failures_v3_json("{"))
  assert_eq(capture_field(result, "valid"), false.to_json())
  assert_eq(capture_field(result, "status"), "invalid".to_json())
}

///|
test "execution failures statement reference cannot be forged" {
  let trace = execution_failure_trace_v3("40P01".to_json())
  let events = v3_test_items(trace, "events")
  object_fields_unchecked_v3(events[3])["statement"] = (99).to_json()
  let result = @json.parse(
    inspect_execution_failures_v3_json(trace.stringify()),
  )
  assert_eq(capture_field(result, "valid"), false.to_json())
}

///|
test "execution failures reused event identity is rejected" {
  let trace = execution_failure_trace_v3("40P01".to_json())
  let events = v3_test_items(trace, "events")
  object_fields_unchecked_v3(events[3])["seq"] = (3).to_json()
  let result = @json.parse(
    inspect_execution_failures_v3_json(trace.stringify()),
  )
  assert_eq(capture_field(result, "valid"), false.to_json())
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
  assert_eq(capture_field(result, "valid"), true.to_json())
  let fault = v3_test_items(result, "faults")[0]
  assert_eq(capture_field(fault, "kind"), "commit_rolled_back".to_json())
  assert_eq(capture_field(fault, "request"), (3).to_json())
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
  assert_eq(capture_field(result, "valid"), true.to_json())
  let fault = v3_test_items(result, "faults")[0]
  assert_eq(capture_field(fault, "kind"), "deadlock".to_json())
  assert_eq(
    capture_field(fault, "origin"),
    "rollback_ok.commitResponse".to_json(),
  )
  assert_eq(capture_field(result, "modelViolationClaim"), false.to_json())
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
  assert_eq(capture_field(result, "valid"), false.to_json())
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
  assert_eq(capture_field(result, "valid"), true.to_json())
  assert_eq(capture_field(result, "observedFaultCount"), (0).to_json())
  assert_eq(capture_field(result, "captureStatus"), "inconclusive".to_json())
  let outcome = v3_test_items(result, "transactionOutcomes")[0]
  assert_eq(capture_field(outcome, "status"), "unknown".to_json())
}
