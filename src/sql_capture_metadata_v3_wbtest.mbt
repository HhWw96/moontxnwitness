///|
fn v3_sql_transport_trace() -> Json {
  v3_test_completed([
    {
      "kind": "statement",
      "tx": "A",
      "sql": "SELECT value FROM fixture WHERE key = %s",
      "parameters": ["x"],
      "mappingId": "fixture.read/1",
      "executedSql": "SELECT value, version FROM fixture WHERE key = %s",
    },
    {
      "kind": "rows",
      "tx": "A",
      "statement": 3,
      "rows": [["value"]],
      "complete": true,
      "serverRows": [["value", "x0"]],
      "columns": [{ "name": "value", "typeCode": 25 }],
    },
    {
      "kind": "read",
      "tx": "A",
      "key": "x",
      "version": "x0",
      "statement": 3,
      "mappingId": "fixture.read/1",
      "evidence": { "serverRow": 0 },
    },
  ])
}

///|
test "v3 named SQL mappings retain observations but cannot manufacture coverage" {
  let trace = v3_sql_transport_trace()
  let result = v3_test_check(trace, "inconclusive")
  assert_true(v3_test_has_gap(result, "unmapped_statement"))
  assert_true(v3_test_has_gap(result, "unverified_sql_mapping"))
}

///|
test "v3 source metadata cannot bind a future statement" {
  let trace = v3_sql_transport_trace()
  object_fields_unchecked_v3(v3_test_items(trace, "events")[4])["statement"] = (6).to_json()
  let _ = v3_test_check(trace, "invalid")
}

///|
test "v3 SQL fact metadata must be complete" {
  let trace = v3_sql_transport_trace()
  object_fields_unchecked_v3(v3_test_items(trace, "events")[4]).remove(
    "mappingId",
  )
  let _ = v3_test_check(trace, "invalid")
}

///|
test "v3 SQL fact evidence must be an object" {
  let trace = v3_sql_transport_trace()
  object_fields_unchecked_v3(v3_test_items(trace, "events")[4])["evidence"] = true.to_json()
  let _ = v3_test_check(trace, "invalid")
}

///|
test "v3 mapped statement cannot hide executed SQL" {
  let trace = v3_sql_transport_trace()
  object_fields_unchecked_v3(v3_test_items(trace, "events")[2]).remove(
    "executedSql",
  )
  let _ = v3_test_check(trace, "invalid")
}

///|
test "v3 server and delivered row batch lengths must agree" {
  let trace = v3_sql_transport_trace()
  object_fields_unchecked_v3(v3_test_items(trace, "events")[3])["serverRows"] = Json::array([],
  )
  let _ = v3_test_check(trace, "invalid")
}

///|
test "v3 business column count must match delivered results" {
  let trace = v3_sql_transport_trace()
  object_fields_unchecked_v3(v3_test_items(trace, "events")[3])["columns"] = Json::array([],
  )
  let _ = v3_test_check(trace, "invalid")
}

///|
test "v3 invalid PostgreSQL type OID is rejected" {
  let trace = v3_sql_transport_trace()
  object_fields_unchecked_v3(v3_test_items(trace, "events")[3])["columns"] = Json::array([
      { "name": "value", "typeCode": 4294967296.0 },
    ],
  )
  let _ = v3_test_check(trace, "invalid")
}

///|
test "v3 SQLSTATE transport rejects arbitrary error flags" {
  let trace = v3_sql_transport_trace()
  object_fields_unchecked_v3(v3_test_items(trace, "events")[3])["error"] = {
    "class": "DatabaseError",
    "sqlstate": "FAILED",
  }
  let _ = v3_test_check(trace, "invalid")
}

///|
test "v3 valid SQLSTATE remains raw failed-statement evidence" {
  let trace = v3_sql_transport_trace()
  object_fields_unchecked_v3(v3_test_items(trace, "events")[3])["error"] = {
    "class": "DeadlockDetected",
    "sqlstate": "40P01",
  }
  let _ = v3_test_check(trace, "inconclusive")
}

///|
fn v3_sql_profile_trace(keys : Json) -> Json {
  let trace = v3_test_completed([])
  object_fields_unchecked_v3(trace)["sqlProfiles"] = Json::array([
    {
      "profile": "fixture/1",
      "schema": "public",
      "table": "fixture",
      "knownKeys": keys,
      "metadata": { "verified": true },
      "effectLedger": [],
    },
  ])
  trace
}

///|
test "v3 self-declared installation verification does not establish coverage" {
  let result = v3_test_check(
    v3_sql_profile_trace(["x"].to_json()),
    "inconclusive",
  )
  assert_true(v3_test_has_gap(result, "unverified_sql_profile"))
}

///|
test "v3 duplicate profile keys are rejected" {
  let _ = v3_test_check(v3_sql_profile_trace(["x", "x"].to_json()), "invalid")
}

///|
test "v3 duplicate installations are rejected" {
  let trace = v3_sql_profile_trace(["x"].to_json())
  let profile = v3_test_items(trace, "sqlProfiles")[0]
  object_fields_unchecked_v3(trace)["sqlProfiles"] = [profile, profile].to_json()
  let _ = v3_test_check(trace, "invalid")
}

///|
test "v3 SQL profile evidence cannot be a scalar" {
  let trace = v3_sql_profile_trace(["x"].to_json())
  object_fields_unchecked_v3(v3_test_items(trace, "sqlProfiles")[0])["effectLedger"] = [
    true,
  ].to_json()
  let _ = v3_test_check(trace, "invalid")
}

///|
test "v3 deletion remaps confirmed COMMIT response references" {
  let trace = v3_test_trace([
    { "kind": "begin", "tx": "N", "connection": "n" },
    { "kind": "commit_request", "tx": "N" },
    { "kind": "commit_ok", "tx": "N" },
    { "kind": "begin", "tx": "A", "connection": "a" },
    { "kind": "commit_request", "tx": "A" },
    {
      "kind": "rollback_ok",
      "tx": "A",
      "commitResponse": { "request": 6, "commandTag": "ROLLBACK" },
    },
  ])
  let (reduced, origins) = v3_without_transaction(trace, "N")
  let _ = v3_response_check(reduced, "ready")
  assert_eq(origins, [1, 5, 6, 7].map(n => n.to_json()))
  let response = capture_field(
    v3_test_items(reduced, "events")[3],
    "commitResponse",
  )
  assert_eq(capture_field(response, "request"), (3).to_json())
}

///|
test "v3 deletion remaps every fact statement binding" {
  let trace = v3_test_trace([
    { "kind": "begin", "tx": "N", "connection": "n" },
    { "kind": "commit_request", "tx": "N" },
    { "kind": "commit_ok", "tx": "N" },
    { "kind": "begin", "tx": "A", "connection": "a" },
    {
      "kind": "statement",
      "tx": "A",
      "sql": "SELECT 1",
      "parameters": [],
      "mappingId": "fixture/1",
      "executedSql": "SELECT 1",
    },
    {
      "kind": "rows",
      "tx": "A",
      "statement": 6,
      "rows": [[1]],
      "complete": true,
    },
    {
      "kind": "read",
      "tx": "A",
      "key": "x",
      "version": "x0",
      "statement": 6,
      "mappingId": "fixture/1",
      "evidence": {},
    },
    { "kind": "commit_request", "tx": "A" },
    { "kind": "commit_ok", "tx": "A" },
  ])
  let (reduced, _) = v3_without_transaction(trace, "N")
  let _ = v3_test_check(reduced, "inconclusive")
  assert_eq(
    capture_field(v3_test_items(reduced, "events")[3], "statement"),
    (3).to_json(),
  )
  assert_eq(
    capture_field(v3_test_items(reduced, "events")[4], "statement"),
    (3).to_json(),
  )
}
