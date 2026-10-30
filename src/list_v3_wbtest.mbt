///|
/// These fixtures assert model facts, scope effects and exact search boundaries.
/// They do not use the production interpreter to create expected histories.
fn l3_test_subset(actual : Json, expected : Json) -> Unit raise {
  match expected {
    Object(fields) => {
      let object = object_fields(actual, "actual test value")
      for key, value in fields {
        l3_test_subset(required(object, key, "actual test value"), value)
      }
    }
    Array(values) => {
      let actual_values = presence_capture_array(actual, "actual array")
      assert_eq(actual_values.length(), values.length())
      for index, value in values {
        l3_test_subset(actual_values[index], value)
      }
    }
    _ => assert_eq(actual, expected)
  }
}

///|
fn l3_test_case(
  text : String,
  expected_status : String,
  expected : String,
  options : String,
) -> Unit raise {
  let report = list_v3_analysis(text, options)
  assert_eq(capture_field(report, "status"), Json(expected_status))
  assert_eq(capture_field(report, "algorithm"), Json("v3-list-1"))
  assert_eq(capture_field(report, "schemaVersion"), Json(3))
  assert_eq(
    capture_field(capture_field(report, "modelDefinition"), "id"),
    Json("append-list-serializable-v1"),
  )
  let normalized = capture_field(report, "normalized")
  assert_eq(capture_field(normalized, "history"), Json::null())
  assert_eq(
    capture_field(normalized, "observations"),
    capture_field(@json.parse(text), "events"),
  )
  assert_eq(@json.parse(normalize_list_capture_v3_json(text)), normalized)
  l3_test_subset(report, @json.parse(expected))
}

///|
test "list v3 01 empty initialized capture has an empty serial witness" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0}],\"gaps\":[]}",
    "consistent", "{\"evidence\":{\"kind\":\"serial-list-replay\",\"serialOrder\":[]}}",
    "{}",
  )
}

///|
test "list v3 02 empty committed transaction consumes one candidate" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":3,\"time\":2},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":4,\"time\":3}],\"gaps\":[]}",
    "consistent", "{\"evidence\":{\"serialOrder\":[\"A\"]},\"execution\":{\"metrics\":{\"states\":1,\"operationChecks\":0}}}",
    "{}",
  )
}

///|
test "list v3 03 initial ordered values are read in their declared order" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"i\",\"value\":\"i\"},{\"id\":\"j\",\"value\":\"j\"}]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"i\",\"value\":\"i\"},{\"id\":\"j\",\"value\":\"j\"}],\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "consistent", "{}", "{}",
  )
}

///|
test "list v3 04 duplicate business values are valid distinct initial identities" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"i\",\"value\":\"same\"},{\"id\":\"j\",\"value\":\"same\"}]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"i\",\"value\":\"same\"},{\"id\":\"j\",\"value\":\"same\"}],\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "consistent", "{}", "{}",
  )
}

///|
test "list v3 05 append and own complete read have a serial witness" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"}],\"seq\":4,\"time\":3},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":5,\"time\":4},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":6,\"time\":5}],\"gaps\":[]}",
    "consistent", "{\"execution\":{\"metrics\":{\"states\":1,\"operationChecks\":3}}}",
    "{}",
  )
}

///|
test "list v3 06 equal append values keep independent identities" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\",\"seq\":3,\"time\":2},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"b\",\"value\":\"same\",\"seq\":4,\"time\":3},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"same\"},{\"id\":\"b\",\"value\":\"same\"}],\"seq\":5,\"time\":4},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":6,\"time\":5},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":7,\"time\":6}],\"gaps\":[]}",
    "consistent", "{\"normalized\":{\"transactions\":[{\"finalWrites\":[3,4]}]}}",
    "{}",
  )
}

///|
test "list v3 07 own reversed append order cannot be serially replayed" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"b\",\"value\":\"b\",\"seq\":4,\"time\":3},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"b\",\"value\":\"b\"},{\"id\":\"a\",\"value\":\"a\"}],\"seq\":5,\"time\":4},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":6,\"time\":5},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":7,\"time\":6}],\"gaps\":[]}",
    "violation", "{\"evidence\":{\"kind\":\"bounded-serial-exhaustion\"},\"execution\":{\"metrics\":{\"reason\":\"exhausted\"}}}",
    "{}",
  )
}

///|
test "list v3 08 omitting an own append from a full list is a counterexample" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":4,\"time\":3},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":5,\"time\":4},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":6,\"time\":5}],\"gaps\":[]}",
    "violation", "{\"evidence\":{\"kind\":\"bounded-serial-exhaustion\"}}", "{}",
  )
}

///|
test "list v3 09 strict prefix does not count as full list observation" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"b\",\"value\":\"b\",\"seq\":4,\"time\":3},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"}],\"seq\":5,\"time\":4},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":6,\"time\":5},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":7,\"time\":6}],\"gaps\":[]}",
    "violation", "{\"evidence\":{\"kind\":\"bounded-serial-exhaustion\"}}", "{}",
  )
}

///|
test "list v3 10 repeated complete observations need no extra identity" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"}],\"seq\":4,\"time\":3},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"}],\"seq\":5,\"time\":4},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":6,\"time\":5},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":7,\"time\":6}],\"gaps\":[]}",
    "consistent", "{}", "{}",
  )
}

///|
test "list v3 11 initial prefix survives a new append" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"i\",\"value\":\"i\"}]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"i\",\"value\":\"i\"},{\"id\":\"a\",\"value\":\"a\"}],\"seq\":4,\"time\":3},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":5,\"time\":4},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":6,\"time\":5}],\"gaps\":[]}",
    "consistent", "{}", "{}",
  )
}

///|
test "list v3 12 independent list keys do not merge their values" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"y\",\"id\":\"b\",\"value\":\"b\",\"seq\":4,\"time\":3},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"}],\"seq\":5,\"time\":4},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"y\",\"items\":[{\"id\":\"b\",\"value\":\"b\"}],\"seq\":6,\"time\":5},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":7,\"time\":6},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":8,\"time\":7}],\"gaps\":[]}",
    "consistent", "{}", "{}",
  )
}

///|
test "list v3 13 writer acknowledgement may be logged after reader" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"begin\",\"tx\":\"B\",\"connection\":\"B\",\"seq\":5,\"time\":4},{\"kind\":\"list_read\",\"tx\":\"B\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"}],\"seq\":6,\"time\":5},{\"kind\":\"commit_request\",\"tx\":\"B\",\"seq\":7,\"time\":6},{\"kind\":\"commit_ok\",\"tx\":\"B\",\"seq\":8,\"time\":7},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":9,\"time\":8}],\"gaps\":[]}",
    "consistent", "{\"evidence\":{\"serialOrder\":[\"A\",\"B\"]}}", "{}",
  )
}

///|
test "list v3 14 serial order may reverse client append event order" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"begin\",\"tx\":\"B\",\"connection\":\"B\",\"seq\":3,\"time\":2},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":4,\"time\":3},{\"kind\":\"append\",\"tx\":\"B\",\"key\":\"x\",\"id\":\"b\",\"value\":\"b\",\"seq\":5,\"time\":4},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":6,\"time\":5},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":7,\"time\":6},{\"kind\":\"commit_request\",\"tx\":\"B\",\"seq\":8,\"time\":7},{\"kind\":\"commit_ok\",\"tx\":\"B\",\"seq\":9,\"time\":8},{\"kind\":\"begin\",\"tx\":\"C\",\"connection\":\"C\",\"seq\":10,\"time\":9},{\"kind\":\"list_read\",\"tx\":\"C\",\"key\":\"x\",\"items\":[{\"id\":\"b\",\"value\":\"b\"},{\"id\":\"a\",\"value\":\"a\"}],\"seq\":11,\"time\":10},{\"kind\":\"commit_request\",\"tx\":\"C\",\"seq\":12,\"time\":11},{\"kind\":\"commit_ok\",\"tx\":\"C\",\"seq\":13,\"time\":12}],\"gaps\":[]}",
    "consistent", "{\"evidence\":{\"serialOrder\":[\"B\",\"A\",\"C\"]}}", "{}",
  )
}

///|
test "list v3 15 two incompatible complete orders have no common serialization" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4},{\"kind\":\"begin\",\"tx\":\"B\",\"connection\":\"B\",\"seq\":6,\"time\":5},{\"kind\":\"append\",\"tx\":\"B\",\"key\":\"x\",\"id\":\"b\",\"value\":\"b\",\"seq\":7,\"time\":6},{\"kind\":\"commit_request\",\"tx\":\"B\",\"seq\":8,\"time\":7},{\"kind\":\"commit_ok\",\"tx\":\"B\",\"seq\":9,\"time\":8},{\"kind\":\"begin\",\"tx\":\"C\",\"connection\":\"C\",\"seq\":10,\"time\":9},{\"kind\":\"list_read\",\"tx\":\"C\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"},{\"id\":\"b\",\"value\":\"b\"}],\"seq\":11,\"time\":10},{\"kind\":\"commit_request\",\"tx\":\"C\",\"seq\":12,\"time\":11},{\"kind\":\"commit_ok\",\"tx\":\"C\",\"seq\":13,\"time\":12},{\"kind\":\"begin\",\"tx\":\"D\",\"connection\":\"D\",\"seq\":14,\"time\":13},{\"kind\":\"list_read\",\"tx\":\"D\",\"key\":\"x\",\"items\":[{\"id\":\"b\",\"value\":\"b\"},{\"id\":\"a\",\"value\":\"a\"}],\"seq\":15,\"time\":14},{\"kind\":\"commit_request\",\"tx\":\"D\",\"seq\":16,\"time\":15},{\"kind\":\"commit_ok\",\"tx\":\"D\",\"seq\":17,\"time\":16}],\"gaps\":[]}",
    "violation", "{\"evidence\":{\"kind\":\"bounded-serial-exhaustion\"}}", "{}",
  )
}

///|
test "list v3 16 empty read write skew on two keys is rejected" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"begin\",\"tx\":\"B\",\"connection\":\"B\",\"seq\":3,\"time\":2},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"y\",\"items\":[],\"seq\":4,\"time\":3},{\"kind\":\"list_read\",\"tx\":\"B\",\"key\":\"x\",\"items\":[],\"seq\":5,\"time\":4},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":6,\"time\":5},{\"kind\":\"append\",\"tx\":\"B\",\"key\":\"y\",\"id\":\"b\",\"value\":\"b\",\"seq\":7,\"time\":6},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":8,\"time\":7},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":9,\"time\":8},{\"kind\":\"commit_request\",\"tx\":\"B\",\"seq\":10,\"time\":9},{\"kind\":\"commit_ok\",\"tx\":\"B\",\"seq\":11,\"time\":10}],\"gaps\":[]}",
    "violation", "{\"evidence\":{\"kind\":\"bounded-serial-exhaustion\"}}", "{}",
  )
}

///|
test "list v3 17 all unreverted appends remain final effects for one key" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"b\",\"value\":\"b\",\"seq\":4,\"time\":3},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":5,\"time\":4},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":6,\"time\":5}],\"gaps\":[]}",
    "consistent", "{\"normalized\":{\"effects\":[{\"id\":\"a\",\"revertedBy\":null},{\"id\":\"b\",\"revertedBy\":null}],\"transactions\":[{\"finalWrites\":[3,4]}]}}",
    "{}",
  )
}

///|
test "list v3 18 aborted append is retained but imposes no committed order" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"rollback_ok\",\"tx\":\"A\",\"seq\":4,\"time\":3}],\"gaps\":[]}",
    "consistent", "{\"evidence\":{\"serialOrder\":[]},\"normalized\":{\"effects\":[{\"id\":\"a\",\"revertedBy\":4}],\"transactions\":[{\"status\":\"aborted\",\"finalWrites\":[]}]}}",
    "{}",
  )
}

///|
test "list v3 19 aborted wrong value observation is outside serializability" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"i\",\"value\":\"i\"}]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"i\",\"value\":\"wrong\"}],\"seq\":3,\"time\":2},{\"kind\":\"rollback_ok\",\"tx\":\"A\",\"seq\":4,\"time\":3}],\"gaps\":[]}",
    "consistent", "{}", "{}",
  )
}

///|
test "list v3 20 aborted wrong key observation is outside serializability" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"i\",\"value\":\"i\"}],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"y\",\"items\":[{\"id\":\"i\",\"value\":\"i\"}],\"seq\":3,\"time\":2},{\"kind\":\"rollback_ok\",\"tx\":\"A\",\"seq\":4,\"time\":3}],\"gaps\":[]}",
    "consistent", "{}", "{}",
  )
}

///|
test "list v3 21 aborted duplicate observation does not claim opacity" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"i\",\"value\":\"i\"}]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"i\",\"value\":\"i\"},{\"id\":\"i\",\"value\":\"i\"}],\"seq\":3,\"time\":2},{\"kind\":\"rollback_ok\",\"tx\":\"A\",\"seq\":4,\"time\":3}],\"gaps\":[]}",
    "consistent", "{}", "{}",
  )
}

///|
test "list v3 22 aborted unknown identity still lacks capture coverage" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"unknown\",\"value\":\"unknown\"}],\"seq\":3,\"time\":2},{\"kind\":\"rollback_ok\",\"tx\":\"A\",\"seq\":4,\"time\":3}],\"gaps\":[]}",
    "inconclusive", "{\"normalized\":{\"coverage\":{\"gaps\":[{\"code\":\"missing_item_source\"}]}},\"evidence\":null}",
    "{}",
  )
}

///|
test "list v3 23 committed reader of aborted append has source proof" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"rollback_ok\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"begin\",\"tx\":\"B\",\"connection\":\"B\",\"seq\":5,\"time\":4},{\"kind\":\"list_read\",\"tx\":\"B\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"}],\"seq\":6,\"time\":5},{\"kind\":\"commit_request\",\"tx\":\"B\",\"seq\":7,\"time\":6},{\"kind\":\"commit_ok\",\"tx\":\"B\",\"seq\":8,\"time\":7}],\"gaps\":[]}",
    "violation", "{\"evidence\":{\"kind\":\"source-proven-list-anomaly\",\"findings\":[{\"code\":\"read_from_aborted_append\"},{\"code\":\"read_from_reverted_append\"}]}}",
    "{}",
  )
}

///|
test "list v3 24 committed reader of a reverted external append has source proof" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"s1\",\"instance\":\"s1\",\"seq\":3,\"time\":2},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":4,\"time\":3},{\"kind\":\"rollback_to\",\"tx\":\"A\",\"instance\":\"s1\",\"seq\":5,\"time\":4},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":6,\"time\":5},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":7,\"time\":6},{\"kind\":\"begin\",\"tx\":\"B\",\"connection\":\"B\",\"seq\":8,\"time\":7},{\"kind\":\"list_read\",\"tx\":\"B\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"}],\"seq\":9,\"time\":8},{\"kind\":\"commit_request\",\"tx\":\"B\",\"seq\":10,\"time\":9},{\"kind\":\"commit_ok\",\"tx\":\"B\",\"seq\":11,\"time\":10}],\"gaps\":[]}",
    "violation", "{\"evidence\":{\"kind\":\"source-proven-list-anomaly\",\"findings\":[{\"code\":\"read_from_reverted_append\"}]}}",
    "{}",
  )
}

///|
test "list v3 25 own read before later rollback remains a real valid observation" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"s1\",\"instance\":\"s1\",\"seq\":3,\"time\":2},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":4,\"time\":3},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"}],\"seq\":5,\"time\":4},{\"kind\":\"rollback_to\",\"tx\":\"A\",\"instance\":\"s1\",\"seq\":6,\"time\":5},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":7,\"time\":6},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":8,\"time\":7}],\"gaps\":[]}",
    "consistent", "{\"normalized\":{\"effects\":[{\"revertedBy\":6}],\"transactions\":[{\"finalWrites\":[]}]},\"evidence\":{\"serialOrder\":[\"A\"]}}",
    "{}",
  )
}

///|
test "list v3 26 own read after rollback cannot resurrect reverted identity" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"s1\",\"instance\":\"s1\",\"seq\":3,\"time\":2},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":4,\"time\":3},{\"kind\":\"rollback_to\",\"tx\":\"A\",\"instance\":\"s1\",\"seq\":5,\"time\":4},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"}],\"seq\":6,\"time\":5},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":7,\"time\":6},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":8,\"time\":7}],\"gaps\":[]}",
    "violation", "{\"evidence\":{\"kind\":\"source-proven-list-anomaly\",\"findings\":[{\"code\":\"read_from_reverted_append\"}]}}",
    "{}",
  )
}

///|
test "list v3 27 rollback restores earlier appended prefix" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"s1\",\"instance\":\"s1\",\"seq\":4,\"time\":3},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"b\",\"value\":\"b\",\"seq\":5,\"time\":4},{\"kind\":\"rollback_to\",\"tx\":\"A\",\"instance\":\"s1\",\"seq\":6,\"time\":5},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"}],\"seq\":7,\"time\":6},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":8,\"time\":7},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":9,\"time\":8}],\"gaps\":[]}",
    "consistent", "{\"normalized\":{\"transactions\":[{\"finalWrites\":[3]}],\"effects\":[{\"id\":\"a\",\"revertedBy\":null},{\"id\":\"b\",\"revertedBy\":6}]}}",
    "{}",
  )
}

///|
test "list v3 28 nested rollback first restores child then parent prefix" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"p\",\"instance\":\"p\",\"seq\":4,\"time\":3},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"b\",\"value\":\"b\",\"seq\":5,\"time\":4},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"c\",\"instance\":\"c\",\"seq\":6,\"time\":5},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"c\",\"value\":\"c\",\"seq\":7,\"time\":6},{\"kind\":\"rollback_to\",\"tx\":\"A\",\"instance\":\"c\",\"seq\":8,\"time\":7},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"},{\"id\":\"b\",\"value\":\"b\"}],\"seq\":9,\"time\":8},{\"kind\":\"rollback_to\",\"tx\":\"A\",\"instance\":\"p\",\"seq\":10,\"time\":9},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"}],\"seq\":11,\"time\":10},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":12,\"time\":11},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":13,\"time\":12}],\"gaps\":[]}",
    "consistent", "{}", "{}",
  )
}

///|
test "list v3 29 released child append stays live until its parent rolls back" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"p\",\"instance\":\"p\",\"seq\":3,\"time\":2},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"c\",\"instance\":\"c\",\"seq\":4,\"time\":3},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":5,\"time\":4},{\"kind\":\"release\",\"tx\":\"A\",\"instance\":\"c\",\"seq\":6,\"time\":5},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"}],\"seq\":7,\"time\":6},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":8,\"time\":7},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":9,\"time\":8}],\"gaps\":[]}",
    "consistent", "{\"normalized\":{\"transactions\":[{\"finalWrites\":[5]}]}}",
    "{}",
  )
}

///|
test "list v3 30 parent rollback revokes a released child append" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"p\",\"instance\":\"p\",\"seq\":3,\"time\":2},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"c\",\"instance\":\"c\",\"seq\":4,\"time\":3},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":5,\"time\":4},{\"kind\":\"release\",\"tx\":\"A\",\"instance\":\"c\",\"seq\":6,\"time\":5},{\"kind\":\"rollback_to\",\"tx\":\"A\",\"instance\":\"p\",\"seq\":7,\"time\":6},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":8,\"time\":7},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":9,\"time\":8},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":10,\"time\":9}],\"gaps\":[]}",
    "consistent", "{\"normalized\":{\"effects\":[{\"revertedBy\":7}],\"transactions\":[{\"finalWrites\":[]}]}}",
    "{}",
  )
}

///|
test "list v3 31 rollback target can be used repeatedly" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"s1\",\"instance\":\"s1\",\"seq\":3,\"time\":2},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":4,\"time\":3},{\"kind\":\"rollback_to\",\"tx\":\"A\",\"instance\":\"s1\",\"seq\":5,\"time\":4},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"b\",\"value\":\"b\",\"seq\":6,\"time\":5},{\"kind\":\"rollback_to\",\"tx\":\"A\",\"instance\":\"s1\",\"seq\":7,\"time\":6},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":8,\"time\":7},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":9,\"time\":8},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":10,\"time\":9}],\"gaps\":[]}",
    "consistent", "{\"normalized\":{\"effects\":[{\"revertedBy\":5},{\"revertedBy\":7}]}}",
    "{}",
  )
}

///|
test "list v3 32 hidden same name old instance is not addressable" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"same\",\"instance\":\"old\",\"seq\":3,\"time\":2},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"same\",\"instance\":\"new\",\"seq\":4,\"time\":3},{\"kind\":\"rollback_to\",\"tx\":\"A\",\"instance\":\"old\",\"seq\":5,\"time\":4},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":6,\"time\":5},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":7,\"time\":6}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 33 releasing newest duplicate name restores older instance" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"same\",\"instance\":\"old\",\"seq\":3,\"time\":2},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":4,\"time\":3},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"same\",\"instance\":\"new\",\"seq\":5,\"time\":4},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"b\",\"value\":\"b\",\"seq\":6,\"time\":5},{\"kind\":\"release\",\"tx\":\"A\",\"instance\":\"new\",\"seq\":7,\"time\":6},{\"kind\":\"rollback_to\",\"tx\":\"A\",\"instance\":\"old\",\"seq\":8,\"time\":7},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":9,\"time\":8},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":10,\"time\":9},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":11,\"time\":10}],\"gaps\":[]}",
    "consistent", "{}", "{}",
  )
}

///|
test "list v3 34 released savepoint instance cannot be rolled back" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"s1\",\"instance\":\"s1\",\"seq\":3,\"time\":2},{\"kind\":\"release\",\"tx\":\"A\",\"instance\":\"s1\",\"seq\":4,\"time\":3},{\"kind\":\"rollback_to\",\"tx\":\"A\",\"instance\":\"s1\",\"seq\":5,\"time\":4},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":6,\"time\":5},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":7,\"time\":6}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 35 invalidated child cannot be released" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"p\",\"instance\":\"p\",\"seq\":3,\"time\":2},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"c\",\"instance\":\"c\",\"seq\":4,\"time\":3},{\"kind\":\"rollback_to\",\"tx\":\"A\",\"instance\":\"p\",\"seq\":5,\"time\":4},{\"kind\":\"release\",\"tx\":\"A\",\"instance\":\"c\",\"seq\":6,\"time\":5},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":7,\"time\":6},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":8,\"time\":7}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 36 savepoint instance identities cannot be reused" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"s1\",\"instance\":\"s1\",\"seq\":3,\"time\":2},{\"kind\":\"release\",\"tx\":\"A\",\"instance\":\"s1\",\"seq\":4,\"time\":3},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"s1\",\"instance\":\"s1\",\"seq\":5,\"time\":4},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":6,\"time\":5},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":7,\"time\":6}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 37 another transaction cannot address a savepoint instance" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"s1\",\"instance\":\"s1\",\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4},{\"kind\":\"begin\",\"tx\":\"B\",\"connection\":\"B\",\"seq\":6,\"time\":5},{\"kind\":\"rollback_to\",\"tx\":\"B\",\"instance\":\"s1\",\"seq\":7,\"time\":6},{\"kind\":\"commit_request\",\"tx\":\"B\",\"seq\":8,\"time\":7},{\"kind\":\"commit_ok\",\"tx\":\"B\",\"seq\":9,\"time\":8}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 38 connection can be reused sequentially" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"c\",\"seq\":2,\"time\":1},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":3,\"time\":2},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"begin\",\"tx\":\"B\",\"connection\":\"c\",\"seq\":5,\"time\":4},{\"kind\":\"commit_request\",\"tx\":\"B\",\"seq\":6,\"time\":5},{\"kind\":\"commit_ok\",\"tx\":\"B\",\"seq\":7,\"time\":6}],\"gaps\":[]}",
    "consistent", "{\"normalized\":{\"transactions\":[{\"connection\":\"c\",\"status\":\"committed\"},{\"connection\":\"c\",\"status\":\"committed\"}]}}",
    "{}",
  )
}

///|
test "list v3 39 connection cannot hold simultaneous transaction identities" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"c\",\"seq\":2,\"time\":1},{\"kind\":\"begin\",\"tx\":\"B\",\"connection\":\"c\",\"seq\":3,\"time\":2}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 40 completed transaction identity cannot be reused" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":3,\"time\":2},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":5,\"time\":4},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":6,\"time\":5},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":7,\"time\":6}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 41 disconnect after commit request is unknown" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"disconnect\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "inconclusive", "{\"evidence\":null,\"normalized\":{\"transactions\":[{\"status\":\"unknown\"}]}}",
    "{}",
  )
}

///|
test "list v3 42 later rollback acknowledgement does not settle requested commit" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"rollback_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "inconclusive", "{\"normalized\":{\"transactions\":[{\"status\":\"unknown\"}]}}",
    "{}",
  )
}

///|
test "list v3 43 original COMMIT response ROLLBACK confirms aborted append" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"rollback_ok\",\"tx\":\"A\",\"commitResponse\":{\"request\":4,\"commandTag\":\"ROLLBACK\"},\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "consistent", "{\"normalized\":{\"effects\":[{\"revertedBy\":5}],\"transactions\":[{\"status\":\"aborted\",\"finalWrites\":[]}]}}",
    "{}",
  )
}

///|
test "list v3 44 commit acknowledgement without request is malformed" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":3,\"time\":2}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 45 two append operations cannot share an identity" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":4,\"time\":3},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":5,\"time\":4},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":6,\"time\":5}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 46 append cannot reuse initialized identity" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"i\",\"value\":\"i\"}]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"i\",\"value\":\"i\",\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 47 initial identity cannot belong to two keys" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"i\",\"value\":\"i\"}],\"y\":[{\"id\":\"i\",\"value\":\"i\"}]},\"consistent\":true,\"seq\":1,\"time\":0}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 48 initial list cannot repeat an identity" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"i\",\"value\":\"i\"},{\"id\":\"i\",\"value\":\"i\"}]},\"consistent\":true,\"seq\":1,\"time\":0}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 49 repeated returned identity is a semantic source finding" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"i\",\"value\":\"i\"}]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"i\",\"value\":\"i\"},{\"id\":\"i\",\"value\":\"i\"}],\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "violation", "{\"evidence\":{\"kind\":\"source-proven-list-anomaly\",\"findings\":[{\"code\":\"duplicate_list_item\"}]}}",
    "{}",
  )
}

///|
test "list v3 50 known identity with modified value is a semantic finding" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"i\",\"value\":\"i\"}]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"i\",\"value\":\"wrong\"}],\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "violation", "{\"evidence\":{\"kind\":\"source-proven-list-anomaly\",\"findings\":[{\"code\":\"item_value_mismatch\"}]}}",
    "{}",
  )
}

///|
test "list v3 51 known identity returned under another key is a semantic finding" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"i\",\"value\":\"i\"}],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"y\",\"items\":[{\"id\":\"i\",\"value\":\"i\"}],\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "violation", "{\"evidence\":{\"kind\":\"source-proven-list-anomaly\",\"findings\":[{\"code\":\"item_key_mismatch\"}]}}",
    "{}",
  )
}

///|
test "list v3 52 future observed append does not repair an earlier missing source" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"B\",\"connection\":\"B\",\"seq\":2,\"time\":1},{\"kind\":\"list_read\",\"tx\":\"B\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"}],\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"B\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"B\",\"seq\":5,\"time\":4},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":6,\"time\":5},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":7,\"time\":6},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":8,\"time\":7},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":9,\"time\":8}],\"gaps\":[]}",
    "inconclusive", "{\"evidence\":null}", "{}",
  )
}

///|
test "list v3 53 unknown item does not become a proven anomaly" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"unknown\",\"value\":\"unknown\"}],\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "inconclusive", "{\"evidence\":null}", "{}",
  )
}

///|
test "list v3 54 append on an uninitialized key is incomplete" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"z\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "inconclusive", "{\"evidence\":null}", "{}",
  )
}

///|
test "list v3 55 empty read still needs a captured initial key" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"z\",\"items\":[],\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "inconclusive", "{\"evidence\":null}", "{}",
  )
}

///|
test "list v3 56 register read cannot be mixed into append list" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"read\",\"tx\":\"A\",\"key\":\"x\",\"version\":\"x0\",\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 57 register write cannot be mixed into append list" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"write\",\"tx\":\"A\",\"key\":\"x\",\"version\":\"x1\",\"predecessor\":\"x0\",\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 58 numeric append payload is outside string model" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":1,\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 59 object read payload is outside string model" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"i\",\"value\":\"i\"}]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"i\",\"value\":{}}],\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 60 item fields cannot silently add unsupported semantics" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"i\",\"value\":\"i\"}]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"i\",\"value\":\"i\",\"extra\":true}],\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 61 append fields cannot silently add unsupported semantics" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"position\":1,\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 62 data model must identify append list" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":3,\"time\":2},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":4,\"time\":3}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 63 complete SQL rows do not erase unmapped statement gap" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"statement\",\"tx\":\"A\",\"sql\":\"select 1\",\"seq\":3,\"time\":2},{\"kind\":\"rows\",\"tx\":\"A\",\"statement\":3,\"rows\":[[1]],\"complete\":true,\"seq\":4,\"time\":3},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":5,\"time\":4},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":6,\"time\":5}],\"gaps\":[]}",
    "inconclusive", "{\"evidence\":null}", "{}",
  )
}

///|
test "list v3 64 predicate observations stay preserved but unsupported" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"i\",\"value\":\"i\"}]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"condition\",\"tx\":\"A\",\"predicate\":{\"id\":\"i\"},\"matched\":true,\"sourceVersion\":\"i\",\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "inconclusive", "{\"evidence\":null}", "{}",
  )
}

///|
test "list v3 65 rows cannot reference a missing statement" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"rows\",\"tx\":\"A\",\"statement\":1,\"rows\":[],\"complete\":true,\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 66 sequence gap makes capture incomplete" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":2},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":3}],\"gaps\":[]}",
    "inconclusive", "{\"evidence\":null}", "{}",
  )
}

///|
test "list v3 67 clock reversal is malformed" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":3,\"time\":0},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":4,\"time\":3}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 68 open writer scope cannot prove complete capture" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":false},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":3,\"time\":2},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":4,\"time\":3}],\"gaps\":[]}",
    "inconclusive", "{\"evidence\":null}", "{}",
  )
}

///|
test "list v3 69 explicit input gap cannot be ignored" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":3,\"time\":2},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":4,\"time\":3}],\"gaps\":[{\"code\":\"lost_event\",\"message\":\"test\"}]}",
    "inconclusive", "{\"evidence\":null}", "{}",
  )
}

///|
test "list v3 70 inconsistent initial snapshot cannot become ready" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":false,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":3,\"time\":2},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":4,\"time\":3}],\"gaps\":[]}",
    "inconclusive", "{\"evidence\":null}", "{}",
  )
}

///|
test "list v3 71 zero state budget cannot report exhaustive failure" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "inconclusive", "{\"execution\":{\"metrics\":{\"reason\":\"state_budget\"}}}",
    "{\"maxStates\":0}",
  )
}

///|
test "list v3 72 one state permits a single committed append" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "consistent", "{\"execution\":{\"metrics\":{\"states\":1,\"operationChecks\":1,\"complete\":true}}}",
    "{\"maxStates\":1,\"maxOperationChecks\":1}",
  )
}

///|
test "list v3 73 zero operation budget interrupts before any mutation" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "inconclusive", "{\"execution\":{\"metrics\":{\"reason\":\"operation_budget\",\"operationChecks\":0,\"complete\":false}}}",
    "{\"maxOperationChecks\":0}",
  )
}

///|
test "list v3 74 exact final comparison may consume final allowed operation" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"}],\"seq\":4,\"time\":3},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":5,\"time\":4},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":6,\"time\":5}],\"gaps\":[]}",
    "consistent", "{\"execution\":{\"metrics\":{\"operationChecks\":3}}}", "{\"maxStates\":1,\"maxOperationChecks\":3}",
  )
}

///|
test "list v3 75 one missing comparison unit cannot be called exhausted" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"}],\"seq\":4,\"time\":3},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":5,\"time\":4},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":6,\"time\":5}],\"gaps\":[]}",
    "inconclusive", "{\"execution\":{\"metrics\":{\"reason\":\"operation_budget\"}}}",
    "{\"maxOperationChecks\":2}",
  )
}

///|
test "list v3 76 seven committed transactions exceed exact capacity" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":3,\"time\":2},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"begin\",\"tx\":\"B\",\"connection\":\"B\",\"seq\":5,\"time\":4},{\"kind\":\"commit_request\",\"tx\":\"B\",\"seq\":6,\"time\":5},{\"kind\":\"commit_ok\",\"tx\":\"B\",\"seq\":7,\"time\":6},{\"kind\":\"begin\",\"tx\":\"C\",\"connection\":\"C\",\"seq\":8,\"time\":7},{\"kind\":\"commit_request\",\"tx\":\"C\",\"seq\":9,\"time\":8},{\"kind\":\"commit_ok\",\"tx\":\"C\",\"seq\":10,\"time\":9},{\"kind\":\"begin\",\"tx\":\"D\",\"connection\":\"D\",\"seq\":11,\"time\":10},{\"kind\":\"commit_request\",\"tx\":\"D\",\"seq\":12,\"time\":11},{\"kind\":\"commit_ok\",\"tx\":\"D\",\"seq\":13,\"time\":12},{\"kind\":\"begin\",\"tx\":\"E\",\"connection\":\"E\",\"seq\":14,\"time\":13},{\"kind\":\"commit_request\",\"tx\":\"E\",\"seq\":15,\"time\":14},{\"kind\":\"commit_ok\",\"tx\":\"E\",\"seq\":16,\"time\":15},{\"kind\":\"begin\",\"tx\":\"F\",\"connection\":\"F\",\"seq\":17,\"time\":16},{\"kind\":\"commit_request\",\"tx\":\"F\",\"seq\":18,\"time\":17},{\"kind\":\"commit_ok\",\"tx\":\"F\",\"seq\":19,\"time\":18},{\"kind\":\"begin\",\"tx\":\"G\",\"connection\":\"G\",\"seq\":20,\"time\":19},{\"kind\":\"commit_request\",\"tx\":\"G\",\"seq\":21,\"time\":20},{\"kind\":\"commit_ok\",\"tx\":\"G\",\"seq\":22,\"time\":21}],\"gaps\":[]}",
    "inconclusive", "{\"execution\":{\"metrics\":{\"reason\":\"exact_capacity\"}}}",
    "{}",
  )
}

///|
test "list v3 77 one hundred twenty nine operations exceed exact capacity" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":3,\"time\":2},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":4,\"time\":3},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":5,\"time\":4},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":6,\"time\":5},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":7,\"time\":6},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":8,\"time\":7},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":9,\"time\":8},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":10,\"time\":9},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":11,\"time\":10},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":12,\"time\":11},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":13,\"time\":12},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":14,\"time\":13},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":15,\"time\":14},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":16,\"time\":15},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":17,\"time\":16},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":18,\"time\":17},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":19,\"time\":18},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":20,\"time\":19},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":21,\"time\":20},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":22,\"time\":21},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":23,\"time\":22},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":24,\"time\":23},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":25,\"time\":24},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":26,\"time\":25},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":27,\"time\":26},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":28,\"time\":27},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":29,\"time\":28},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":30,\"time\":29},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":31,\"time\":30},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":32,\"time\":31},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":33,\"time\":32},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":34,\"time\":33},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":35,\"time\":34},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":36,\"time\":35},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":37,\"time\":36},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":38,\"time\":37},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":39,\"time\":38},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":40,\"time\":39},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":41,\"time\":40},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":42,\"time\":41},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":43,\"time\":42},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":44,\"time\":43},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":45,\"time\":44},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":46,\"time\":45},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":47,\"time\":46},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":48,\"time\":47},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":49,\"time\":48},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":50,\"time\":49},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":51,\"time\":50},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":52,\"time\":51},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":53,\"time\":52},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":54,\"time\":53},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":55,\"time\":54},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":56,\"time\":55},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":57,\"time\":56},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":58,\"time\":57},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":59,\"time\":58},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":60,\"time\":59},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":61,\"time\":60},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":62,\"time\":61},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":63,\"time\":62},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":64,\"time\":63},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":65,\"time\":64},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":66,\"time\":65},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":67,\"time\":66},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":68,\"time\":67},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":69,\"time\":68},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":70,\"time\":69},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":71,\"time\":70},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":72,\"time\":71},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":73,\"time\":72},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":74,\"time\":73},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":75,\"time\":74},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":76,\"time\":75},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":77,\"time\":76},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":78,\"time\":77},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":79,\"time\":78},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":80,\"time\":79},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":81,\"time\":80},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":82,\"time\":81},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":83,\"time\":82},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":84,\"time\":83},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":85,\"time\":84},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":86,\"time\":85},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":87,\"time\":86},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":88,\"time\":87},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":89,\"time\":88},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":90,\"time\":89},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":91,\"time\":90},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":92,\"time\":91},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":93,\"time\":92},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":94,\"time\":93},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":95,\"time\":94},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":96,\"time\":95},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":97,\"time\":96},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":98,\"time\":97},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":99,\"time\":98},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":100,\"time\":99},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":101,\"time\":100},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":102,\"time\":101},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":103,\"time\":102},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":104,\"time\":103},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":105,\"time\":104},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":106,\"time\":105},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":107,\"time\":106},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":108,\"time\":107},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":109,\"time\":108},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":110,\"time\":109},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":111,\"time\":110},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":112,\"time\":111},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":113,\"time\":112},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":114,\"time\":113},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":115,\"time\":114},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":116,\"time\":115},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":117,\"time\":116},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":118,\"time\":117},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":119,\"time\":118},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":120,\"time\":119},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":121,\"time\":120},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":122,\"time\":121},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":123,\"time\":122},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":124,\"time\":123},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":125,\"time\":124},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":126,\"time\":125},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":127,\"time\":126},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":128,\"time\":127},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":129,\"time\":128},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":130,\"time\":129},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[],\"seq\":131,\"time\":130},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":132,\"time\":131},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":133,\"time\":132}],\"gaps\":[]}",
    "inconclusive", "{\"execution\":{\"metrics\":{\"reason\":\"exact_capacity\"}}}",
    "{}",
  )
}

///|
test "list v3 78 Unicode quotes and newlines remain exact business strings" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"月亮🙂\\\"\\\\\\n\",\"seq\":3,\"time\":2},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"月亮🙂\\\"\\\\\\n\"}],\"seq\":4,\"time\":3},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":5,\"time\":4},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":6,\"time\":5}],\"gaps\":[]}",
    "consistent", "{\"evidence\":{\"sourceEvidence\":[{\"id\":\"a\",\"value\":\"月亮🙂\\\"\\\\\\n\",\"key\":\"x\",\"writer\":\"A\",\"sourceSeq\":3,\"revertedBy\":null}]}}",
    "{}",
  )
}

///|
test "list v3 79 initial ordering follows arrays rather than identifier sorting" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"z\",\"value\":\"z\"},{\"id\":\"a\",\"value\":\"a\"}]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"z\",\"value\":\"z\"},{\"id\":\"a\",\"value\":\"a\"}],\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "consistent", "{}", "{}",
  )
}

///|
test "list v3 80 external read of committed writer prefix is nonserializable" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"b\",\"value\":\"b\",\"seq\":4,\"time\":3},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":5,\"time\":4},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":6,\"time\":5},{\"kind\":\"begin\",\"tx\":\"B\",\"connection\":\"B\",\"seq\":7,\"time\":6},{\"kind\":\"list_read\",\"tx\":\"B\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"}],\"seq\":8,\"time\":7},{\"kind\":\"commit_request\",\"tx\":\"B\",\"seq\":9,\"time\":8},{\"kind\":\"commit_ok\",\"tx\":\"B\",\"seq\":10,\"time\":9}],\"gaps\":[]}",
    "violation", "{\"evidence\":{\"kind\":\"bounded-serial-exhaustion\"}}", "{}",
  )
}

///|
test "list v3 81 empty capture can succeed with both search budgets zero" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0}],\"gaps\":[]}",
    "consistent", "{\"execution\":{\"metrics\":{\"states\":0,\"operationChecks\":0}}}",
    "{\"maxStates\":0,\"maxOperationChecks\":0}",
  )
}

///|
test "list v3 82 aborted and committed same-key effects never share identity" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"rollback_ok\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"begin\",\"tx\":\"B\",\"connection\":\"B\",\"seq\":5,\"time\":4},{\"kind\":\"append\",\"tx\":\"B\",\"key\":\"x\",\"id\":\"b\",\"value\":\"b\",\"seq\":6,\"time\":5},{\"kind\":\"list_read\",\"tx\":\"B\",\"key\":\"x\",\"items\":[{\"id\":\"b\",\"value\":\"b\"}],\"seq\":7,\"time\":6},{\"kind\":\"commit_request\",\"tx\":\"B\",\"seq\":8,\"time\":7},{\"kind\":\"commit_ok\",\"tx\":\"B\",\"seq\":9,\"time\":8}],\"gaps\":[]}",
    "consistent", "{\"normalized\":{\"transactions\":[{\"status\":\"aborted\",\"finalWrites\":[]},{\"status\":\"committed\",\"finalWrites\":[6]}]}}",
    "{}",
  )
}

///|
test "list v3 83 unknown writer keeps a known item read inconclusive" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"a\",\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"disconnect\",\"tx\":\"A\",\"seq\":5,\"time\":4},{\"kind\":\"begin\",\"tx\":\"B\",\"connection\":\"B\",\"seq\":6,\"time\":5},{\"kind\":\"list_read\",\"tx\":\"B\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"a\"}],\"seq\":7,\"time\":6},{\"kind\":\"commit_request\",\"tx\":\"B\",\"seq\":8,\"time\":7},{\"kind\":\"commit_ok\",\"tx\":\"B\",\"seq\":9,\"time\":8}],\"gaps\":[]}",
    "inconclusive", "{\"evidence\":null}", "{}",
  )
}

///|
test "list v3 84 non string initialized payload is malformed" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"i\",\"value\":false}]},\"consistent\":true,\"seq\":1,\"time\":0}],\"gaps\":[]}",
    "invalid", "{}", "{}",
  )
}

///|
test "list v3 85 read duplication and source mismatch remain raw observations" {
  l3_test_case(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"list-unit\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"i\",\"value\":\"i\"}]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":2,\"time\":1},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"i\",\"value\":\"i\"},{\"id\":\"i\",\"value\":\"i\"}],\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":5,\"time\":4}],\"gaps\":[]}",
    "violation", "{\"evidence\":{\"kind\":\"source-proven-list-anomaly\",\"findings\":[{\"code\":\"duplicate_list_item\"}]}}",
    "{}",
  )
}

///|
test "list v3 initial source points to the original snapshot event" {
  let text = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"initial-source\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"seq\":1,\"time\":0,\"initial\":{\"x\":[{\"id\":\"i\",\"value\":\"same\"}]},\"consistent\":true}],\"gaps\":[]}"
  let report = list_v3_analysis(text, "{}")
  let sources = v3_test_items(
    capture_field(report, "evidence"),
    "sourceEvidence",
  )
  assert_eq(capture_field(sources[0], "sourceSeq"), Json(1))
  let changed = text.replace(old="\"seq\":1", new="\"seq\":7")
  let parsed = list_v3_parse(changed)
  assert_eq(capture_field(parsed.normalized, "status"), Json("inconclusive"))
  assert_eq(capture_field(parsed.source_evidence[0], "sourceSeq"), Json(7))
  assert_true(v3_test_has_gap(parsed.normalized, "sequence_gap"))
}

///|
test "list v3 duplicate JSON root fields cannot be normalized away" {
  let text = "{\"traceSchema\":3,\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"x\",\"scope\":{\"exclusiveWriters\":true},\"events\":[],\"gaps\":[]}"
  let result = @json.parse(normalize_list_capture_v3_json(text))
  assert_eq(capture_field(result, "status"), Json("invalid"))
  assert_eq(capture_field(result, "history"), Json::null())
}

///|
test "list v3 malformed options and unsupported budget widening are rejected" {
  for
    options in [
      "{\"maxStates\":-1}", "{\"maxStates\":100001}", "{\"maxStates\":0.5}", "{\"maxOperationChecks\":1000001}",
      "{\"maxOperationChecks\":false}", "{\"unknown\":1}", "{\"maxStates\":1,\"maxStates\":1}",
    ] {
    let rejected = try {
      let _ = list_v3_options(options)
      false
    } catch {
      _ => true
    }
    assert_true(rejected)
  }
}
