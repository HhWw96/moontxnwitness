///|
fn select45_fixture() -> Json raise {
  sql_json_v1(
    "{\"check\":{\"valid\":true,\"status\":\"matched\",\"completeFetchVerified\":true,\"deliveredRows\":1,\"grammar\":{\"descriptor\":{\"table\":{\"primaryKey\":\"id\",\"columns\":[{\"name\":\"id\",\"type\":\"int64\"},{\"name\":\"balance\",\"type\":\"int64\"},{\"name\":\"active\",\"type\":\"bool\"},{\"name\":\"label\",\"type\":\"text\"},{\"name\":\"__mtw_source_version\",\"type\":\"int64\"}]},\"projections\":[{\"column\":\"id\"},{\"column\":\"balance\"},{\"column\":\"active\"},{\"column\":\"label\"},{\"column\":\"__mtw_source_version\"}],\"predicates\":[{\"column\":\"id\",\"operator\":\"eq\",\"value\":{\"kind\":\"positional\",\"value\":0,\"type\":\"int64\"},\"collation\":null}],\"ordering\":[]},\"bindings\":[{\"reference\":{\"kind\":\"positional\",\"value\":0,\"type\":\"int64\"},\"value\":{\"type\":\"int64\",\"value\":\"17\"}}]}},\"native\":{\"resultId\":\"synthetic-result\",\"statementSeq\":3,\"connection\":\"synthetic-c\",\"cursor\":\"synthetic-cur\",\"tx\":\"synthetic-tx\",\"fields\":[{\"oid\":20,\"format\":0},{\"oid\":20,\"format\":0},{\"oid\":16,\"format\":0},{\"oid\":25,\"format\":0},{\"oid\":20,\"format\":0}],\"rows\":[[\"MTc=\",\"MTAw\",\"dA==\",\"8JCAgA==\",\"MQ==\"]]}}",
    65536,
  )
}

///|
fn select45_run(f : Json, limit~ : Int32 = 1000000) -> Map[String, Json] raise {
  let r = source_object_v4(f)
  source_object_v4(
    source_select_result_constraints_v4(r.at("check"), r.at("native"), {
      limit,
      checks: 0,
    }),
  )
}

///|
fn select45_check(f : Json) -> Map[String, Json] raise {
  source_object_v4(source_object_v4(f).at("check"))
}

///|
fn select45_native(f : Json) -> Map[String, Json] raise {
  source_object_v4(source_object_v4(f).at("native"))
}

///|
fn select45_descriptor(f : Json) -> Map[String, Json] raise {
  source_object_v4(
    source_object_v4(select45_check(f).at("grammar")).at("descriptor"),
  )
}

///|
fn select45_term(f : Json) -> Map[String, Json] raise {
  source_object_v4(orm_array(select45_descriptor(f).at("predicates"))[0])
}

///|
fn select45_binding(f : Json) -> Map[String, Json] raise {
  source_object_v4(
    orm_array(source_object_v4(select45_check(f).at("grammar")).at("bindings"))[0],
  )
}

///|
fn select45_remove(f : Json, at : Int32) -> Unit raise {
  let descriptor = select45_descriptor(f)
  let projections = orm_array(descriptor.at("projections"))
  let kept_projections : Array[Json] = []
  for index, value in projections {
    if index != at {
      kept_projections.push(value)
    }
  }
  descriptor["projections"] = Json(kept_projections)
  let n = select45_native(f)
  let fields : Array[Json] = []
  for index, value in orm_array(n.at("fields")) {
    if index != at {
      fields.push(value)
    }
  }
  n["fields"] = Json(fields)
  let rows : Array[Json] = []
  for row in orm_array(n.at("rows")) {
    let values : Array[Json] = []
    for index, value in orm_array(row) {
      if index != at {
        values.push(value)
      }
    }
    rows.push(Json(values))
  }
  n["rows"] = Json(rows)
}

///|
test "select45 01 WHERE matches delivered primary key" {
  let r = select45_run(select45_fixture())
  assert_eq(r.at("valid"), Json(true))
  assert_eq(r.at("resultSetCompletenessVerified"), Json(false))
}

///|
test "select45 02 independent WHERE18 returned17 witness" {
  let f = select45_fixture()
  source_object_v4(select45_binding(f).at("value"))["value"] = Json("18")
  let r = select45_run(f)
  assert_eq(r.at("status"), Json("mismatch"))
  assert_eq(
    source_object_v4(r.at("witness")).at("rule"),
    Json("returned-row-WHERE-AND"),
  )
}

///|
test "select45 03 independent duplicate native PK witness" {
  let f = select45_fixture()
  let rows = orm_array(select45_native(f).at("rows"))
  rows.push(v4_json_copy(rows[0]))
  select45_check(f)["deliveredRows"] = Json(2)
  let r = select45_run(f)
  assert_eq(r.at("status"), Json("mismatch"))
  assert_eq(
    source_object_v4(r.at("witness")).at("rule"),
    Json("single-table-primary-key-result-uniqueness"),
  )
}

///|
test "select45 04 missing conditional field is unknown" {
  let f = select45_fixture()
  select45_remove(f, 0)
  let r = select45_run(f)
  assert_eq(r.at("status"), Json("unknown"))
  assert_eq(r.at("valid"), Json(false))
}

///|
test "select45 05 partial business projection does not fill sidecar values" {
  let f = select45_fixture()
  select45_remove(f, 1)
  let r = select45_run(f)
  assert_eq(r.at("valid"), Json(true))
  assert_eq(r.at("sourceFactsProduced"), Json(false))
}

///|
test "select45 06 legal complete empty result remains no negative source proof" {
  let f = select45_fixture()
  select45_native(f)["rows"] = Json::array([])
  select45_check(f)["deliveredRows"] = Json(0)
  let r = select45_run(f)
  assert_eq(r.at("valid"), Json(true))
  assert_eq(r.at("negativeReadSourceVerified"), Json(false))
}

///|
test "select45 07 incomplete prefix has a gap" {
  let f = select45_fixture()
  select45_check(f)["completeFetchVerified"] = Json(false)
  let r = select45_run(f)
  assert_eq(r.at("status"), Json("unknown"))
}

///|
test "select45 08 WHERE mismatch wins over incomplete prefix" {
  let f = select45_fixture()
  select45_check(f)["completeFetchVerified"] = Json(false)
  source_object_v4(select45_binding(f).at("value"))["value"] = Json("18")
  assert_eq(select45_run(f).at("status"), Json("mismatch"))
}

///|
test "select45 09 unknown native delivery is not SELECT verification" {
  let f = select45_fixture()
  select45_check(f)["valid"] = Json(false)
  select45_check(f)["status"] = Json("unknown")
  assert_eq(select45_run(f).at("valid"), Json(false))
}

///|
test "select45 10 repeated consumption rejected by native gate stays rejected" {
  let f = select45_fixture()
  select45_check(f)["valid"] = Json(false)
  select45_check(f)["status"] = Json("mismatch")
  assert_eq(select45_run(f).at("status"), Json("mismatch"))
}

///|
test "select45 11 ORDER BY outside this profile is visible" {
  let f = select45_fixture()
  select45_descriptor(f)["ordering"] = [{ "column": "id", "direction": "desc" }]
  assert_eq(select45_run(f).at("status"), Json("unknown"))
}

///|
test "select45 12 zero caller checks remains unknown" {
  let r = select45_run(select45_fixture(), limit=0)
  assert_eq(r.at("valid"), Json(false))
  assert_eq(source_object_v4(r.at("execution")).at("limited"), Json(true))
}

///|
test "select45 13 exact versus one-short checks" {
  let f = select45_fixture()
  let full = select45_run(f)
  let count = fetch_number_v1(
    source_object_v4(full.at("execution")).at("checks"),
    1000000,
  )
  assert_eq(select45_run(f, limit=count).at("valid"), Json(true))
  assert_eq(select45_run(f, limit=count - 1).at("valid"), Json(false))
}

///|
test "select45 14 int64 comparison uses exact signed lexemes" {
  assert_eq(
    source_select_integer_compare_v4(
      "9223372036854775807", "9223372036854775806",
    ),
    1,
  )
  assert_eq(
    source_select_integer_compare_v4(
      "-9223372036854775808", "-9223372036854775807",
    ),
    -1,
  )
  assert_eq(source_select_integer_compare_v4("-10", "-9"), -1)
  assert_eq(source_select_integer_compare_v4("0", "-1"), 1)
}

///|
test "select45 15 C text order handles astral versus BMP" {
  assert_eq(
    source_select_compare_v4({ "type": "text", "value": "𐀀" }, {
      "type": "text",
      "value": "",
    }),
    1,
  )
}

///|
test "select45 16 operator eq actual equal values" {
  let f = select45_fixture()
  select45_term(f)["operator"] = Json("eq")
  assert_eq(select45_run(f).at("valid"), Json(true))
}

///|
test "select45 17 operator le actual equal values" {
  let f = select45_fixture()
  select45_term(f)["operator"] = Json("le")
  assert_eq(select45_run(f).at("valid"), Json(true))
}

///|
test "select45 18 operator ge actual equal values" {
  let f = select45_fixture()
  select45_term(f)["operator"] = Json("ge")
  assert_eq(select45_run(f).at("valid"), Json(true))
}

///|
test "select45 19 operator lt actual equal values" {
  let f = select45_fixture()
  select45_term(f)["operator"] = Json("lt")
  assert_eq(select45_run(f).at("valid"), Json(false))
}

///|
test "select45 20 operator gt actual equal values" {
  let f = select45_fixture()
  select45_term(f)["operator"] = Json("gt")
  assert_eq(select45_run(f).at("valid"), Json(false))
}

///|
test "select45 21 literal parameter is independently resolved" {
  let f = select45_fixture()
  select45_term(f)["value"] = {
    "kind": "literal",
    "type": "int64",
    "value": "17",
  }
  assert_eq(select45_run(f).at("valid"), Json(true))
}

///|
test "select45 22 named binding is resolved without guessing" {
  let f = select45_fixture()
  let reference : Json = { "kind": "named", "type": "int64", "value": "who" }
  select45_term(f)["value"] = reference
  select45_binding(f)["reference"] = reference
  assert_eq(select45_run(f).at("valid"), Json(true))
}

///|
test "select45 23 missing binding is a mismatch" {
  let f = select45_fixture()
  source_object_v4(select45_check(f).at("grammar"))["bindings"] = Json::array([])
  assert_eq(select45_run(f).at("valid"), Json(false))
}

///|
test "select45 24 AND known false survives another missing condition" {
  let f = select45_fixture()
  let terms = orm_array(select45_descriptor(f).at("predicates"))
  terms.push({
    "column": "balance",
    "operator": "ge",
    "value": { "kind": "literal", "type": "int64", "value": "0" },
    "collation": Json::null(),
  })
  select45_remove(f, 1)
  source_object_v4(select45_binding(f).at("value"))["value"] = Json("18")
  assert_eq(select45_run(f).at("status"), Json("mismatch"))
}

///|
test "select45 25 duplicate primary key survives unknown condition" {
  let f = select45_fixture()
  let rows = orm_array(select45_native(f).at("rows"))
  rows.push(v4_json_copy(rows[0]))
  select45_check(f)["deliveredRows"] = Json(2)
  orm_array(select45_descriptor(f).at("predicates")).push({
    "column": "balance",
    "operator": "ge",
    "value": { "kind": "literal", "type": "int64", "value": "0" },
    "collation": Json::null(),
  })
  select45_remove(f, 1)
  assert_eq(select45_run(f).at("status"), Json("mismatch"))
}

///|
test "select45 26 boolean equality true" {
  let f = select45_fixture()
  select45_descriptor(f)["predicates"] = [
    {
      "column": "active",
      "operator": "eq",
      "value": { "kind": "literal", "type": "bool", "value": true },
      "collation": Json::null(),
    },
  ]
  assert_eq(select45_run(f).at("valid"), Json(true))
}

///|
test "select45 27 boolean equality false witness" {
  let f = select45_fixture()
  select45_descriptor(f)["predicates"] = [
    {
      "column": "active",
      "operator": "eq",
      "value": { "kind": "literal", "type": "bool", "value": false },
      "collation": Json::null(),
    },
  ]
  assert_eq(select45_run(f).at("status"), Json("mismatch"))
}

///|
test "select45 28 missing PK despite nonkey condition remains unknown" {
  let f = select45_fixture()
  select45_descriptor(f)["predicates"] = [
    {
      "column": "balance",
      "operator": "eq",
      "value": { "kind": "literal", "type": "int64", "value": "100" },
      "collation": Json::null(),
    },
  ]
  select45_remove(f, 0)
  assert_eq(select45_run(f).at("status"), Json("unknown"))
}

///|
test "select45 29 full result with no WHERE still needs PK uniqueness" {
  let f = select45_fixture()
  select45_descriptor(f)["predicates"] = Json::array([])
  let rows = orm_array(select45_native(f).at("rows"))
  rows.push(v4_json_copy(rows[0]))
  select45_check(f)["deliveredRows"] = Json(2)
  assert_eq(select45_run(f).at("status"), Json("mismatch"))
}

///|
test "select45 30 comparison kind mismatch is rejected" {
  let rejected = try {
    let _ = source_select_compare_v4({ "type": "int64", "value": "1" }, {
      "type": "text",
      "value": "1",
    })
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "select45 31 invalid int64 lexical input does not pass" {
  let rejected = try {
    let _ = source_select_integer_compare_v4("01", "1")
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "select45 32 result evidence retains original identity" {
  let r = select45_run(select45_fixture())
  assert_eq(
    source_object_v4(r.at("resultReference")).at("resultId"),
    Json("synthetic-result"),
  )
  assert_eq(
    source_object_v4(r.at("resultReference")).at("statementSeq"),
    Json(3),
  )
}
