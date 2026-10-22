///|
fn v3_response_check(trace : Json, status : String) -> Json raise {
  let result = @json.parse(
    normalize_register_capture_v3_json(trace.stringify()),
  )
  assert_eq(capture_field(result, "status"), status.to_json())
  if status == "ready" {
    assert_eq(capture_field(result, "algorithm"), "v3-lifecycle-2".to_json())
  }
  result
}

///|
fn v3_commit_response_trace(proof : Json) -> Json {
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
    { "kind": "rollback_ok", "tx": "A", "commitResponse": proof },
  ])
}

///|
test "v3 actual COMMIT ROLLBACK tag confirms abort and reverses effects" {
  let result = v3_response_check(
    v3_commit_response_trace({ "request": 4, "commandTag": "ROLLBACK" }),
    "ready",
  )
  let transactions = v3_test_items(result, "transactions")
  assert_eq(
    object_fields_unchecked_v3(transactions[0]).at("status"),
    "aborted".to_json(),
  )
  assert_eq(
    object_fields_unchecked_v3(v3_test_items(result, "effects")[0]).at(
      "revertedBy",
    ),
    (5).to_json(),
  )
}

///|
test "v3 serialization error response can prove COMMIT rollback" {
  let _ = v3_response_check(
    v3_commit_response_trace({
      "request": 4,
      "sqlstate": "40001",
      "diagnosticSqlstate": "40001",
      "transactionStatus": "IDLE",
    }),
    "ready",
  )
}

///|
test "v3 deadlock is a confirmed abort outcome not a G2 label" {
  let _ = v3_response_check(
    v3_commit_response_trace({
      "request": 4,
      "sqlstate": "40P01",
      "diagnosticSqlstate": "40P01",
      "transactionStatus": "IDLE",
    }),
    "ready",
  )
}

///|
test "v3 COMMIT rollback proof cannot acknowledge another event" {
  let _ = v3_response_check(
    v3_commit_response_trace({ "request": 3, "commandTag": "ROLLBACK" }),
    "invalid",
  )
}

///|
test "v3 a COMMIT tag cannot be relabeled rollback" {
  let _ = v3_response_check(
    v3_commit_response_trace({ "request": 4, "commandTag": "COMMIT" }),
    "invalid",
  )
}

///|
test "v3 client-only confirmation flag is rejected" {
  let _ = v3_response_check(
    v3_commit_response_trace({ "request": 4, "serverConfirmed": true }),
    "invalid",
  )
}

///|
test "v3 mismatching server diagnostic cannot prove rollback" {
  let _ = v3_response_check(
    v3_commit_response_trace({
      "request": 4,
      "sqlstate": "40001",
      "diagnosticSqlstate": "40P01",
      "transactionStatus": "IDLE",
    }),
    "invalid",
  )
}

///|
test "v3 non-idle connection cannot prove transaction abort" {
  let _ = v3_response_check(
    v3_commit_response_trace({
      "request": 4,
      "sqlstate": "40001",
      "diagnosticSqlstate": "40001",
      "transactionStatus": "INERROR",
    }),
    "invalid",
  )
}
