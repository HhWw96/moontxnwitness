///|
/// Synthetic protocol units only; the separate harness consumes original PG18 bytes.
fn orm2_expect_reject(action : () -> Unit raise) -> Unit raise {
  let mut rejected = false
  try { action() } catch { _ => rejected = true }
  assert_true(rejected)
}

///|
fn orm2_test_raw(text : String) -> Json {
  let bytes = @utf8.encode(text[:])
  { "captureType": "bytes", "base64": @base64.encode(bytes[:]).to_json() }
}

///|
fn orm2_test_select(oid : Int, native : Json, wire : String) -> Json {
  {
    "sourceSeq": 2, "kind": "control-query", "connection": "setup-A", "backendPid": 7,
    "transaction": "setup-A-tx1", "sql": "SELECT metadata", "parameters": Json::null(),
    "transactionStatusBefore": "INTRANS", "transactionStatusAfter": "INTRANS",
    "result": { "status": 2, "commandTag": "SELECT 1", "rowcount": 1,
      "columns": [{ "name": "value", "typeCode": oid.to_json() }], "rows": [[native]], "complete": true,
      "actualPGresult": { "status": 2, "commandTag": orm2_test_raw("SELECT 1"), "commandTuples": 1,
        "ntuples": 1, "nfields": 1, "fields": [{ "oid": oid.to_json(), "format": 0, "typmod": -1 }],
        "rawRows": [[orm2_test_raw(wire)]] } },
  }
}

///|
fn orm2_test_cursor(records : Array[Json]) -> OrmControlCursor2 raise {
  let controls : Array[OrmControl2] = []
  for value in records { controls.push(orm2_control(value)) }
  { controls, at: 0, verified: [] }
}

///|
fn orm2_test_command() -> Json {
  { "sourceSeq": 2, "kind": "control-query", "connection": "setup-A", "backendPid": 7,
    "transaction": "setup-A-tx1", "sql": "INSERT setup", "parameters": Json::null(),
    "transactionStatusBefore": "INTRANS", "transactionStatusAfter": "INTRANS",
    "result": { "status": 1, "commandTag": "INSERT 0 1", "rowcount": 1,
      "columns": Json::null(), "rows": [], "complete": true,
      "actualPGresult": { "status": 1, "commandTag": orm2_test_raw("INSERT 0 1"), "commandTuples": 1,
        "ntuples": 0, "nfields": 0, "fields": [], "rawRows": [] } },
  }
}

///|
test "source2 flat array retains quoted comma quote backslash and Unicode" {
  assert_eq(orm2_array_cell("{\"a,b\",\"q\\\"r\",\"b\\\\c\",\"月🚀\"}", 25), ["a,b", "q\"r", "b\\c", "月🚀"].to_json())
}

///|
test "source2 array distinguishes NULL from quoted or escaped NULL" {
  assert_eq(orm2_array_cell("{NULL,\"NULL\",N\\ULL,\"\"}", 25), [Json::null(), "NULL".to_json(), "NULL".to_json(), "".to_json()].to_json())
}

///|
test "source2 empty arrays do not create one null item" {
  assert_eq(orm2_array_cell("{}", 25), orm_empty())
}

///|
test "source2 smallint array checks endpoints" {
  assert_eq(orm2_array_cell("{-32768,0,32767}", 21), [-32768, 0, 32767].to_json())
  orm2_expect_reject(() => { ignore(orm2_array_cell("{32768}", 21)) })
}

///|
test "source2 boolean array uses actual PostgreSQL text values" {
  assert_eq(orm2_array_cell("{t,f,NULL}", 16), [true.to_json(), false.to_json(), Json::null()].to_json())
  orm2_expect_reject(() => { ignore(orm2_array_cell("{true}", 16)) })
}

///|
test "source2 malformed array closure or delimiter cannot complete proof" {
  for input in ["{\"abc}", "{a,}", "{,a}", "{\"a\"x}"] {
    orm2_expect_reject(() => { ignore(orm2_array_cell(input, 25)) })
  }
}

///|
test "source2 nested and nondefault-bound arrays are declined" {
  for input in ["{{a}}", "[0:1]={a,b}"] {
    orm2_expect_reject(() => { ignore(orm2_array_cell(input, 25)) })
  }
}

///|
test "source2 canonical raw integer is exact not coercive" {
  assert_eq(orm2_text_integer("4294967295"), (4294967295.0).to_json())
  for input in ["01", "+1", "1.0", "1e0", "9007199254740992"] {
    orm2_expect_reject(() => { ignore(orm2_text_integer(input)) })
  }
}

///|
test "source2 raw jsonb independently reconstructs complete nested image" {
  assert_eq(orm2_decode_cell(orm2_test_raw("{\"id\":\"x\",\"v\":[true,null,\"月\"]}"), 3802), { "id": "x", "v": [true, Json::null(), "月".to_json()] })
  orm2_expect_reject(() => { ignore(orm2_decode_cell(orm2_test_raw("{\"x\":1,\"x\":2}"), 3802)) })
}

///|
test "source2 invalid UTF8 and noncanonical base64 are rejected" {
  orm2_expect_reject(() => { ignore(orm2_decode_cell({ "captureType": "bytes", "base64": "/w==" }, 25)) })
  orm2_expect_reject(() => { ignore(orm2_decode_cell({ "captureType": "bytes", "base64": "YQ==\n" }, 25)) })
}

///|
test "source2 native boolean cannot disagree with raw boolean" {
  orm2_expect_reject(() => { ignore(orm2_control(orm2_test_select(16, false.to_json(), "t"))) })
}

///|
test "source2 native catalog array cannot disagree with raw array" {
  orm2_expect_reject(() => { ignore(orm2_control(orm2_test_select(1005, [1, 2], "{1,3}"))) })
}

///|
test "source2 null native cell cannot replace nonnull raw cell" {
  orm2_expect_reject(() => { ignore(orm2_control(orm2_test_select(25, Json::null(), "x"))) })
}

///|
test "source2 descriptor OID cannot be changed independently of wire type" {
  let doc = orm2_test_select(25, "x".to_json(), "x")
  let result = object_fields(orm_get(doc, "result"), "result")
  let changed_columns : Json = [{ "name": "value", "typeCode": 16 }]
  result["columns"] = changed_columns
  let root = object_fields(doc, "control")
  root["result"] = result.to_json()
  orm2_expect_reject(() => { ignore(orm2_control(root.to_json())) })
}

///|
test "source2 binary format is not treated as text" {
  let doc = orm2_test_select(25, "x".to_json(), "x")
  let result = object_fields(orm_get(doc, "result"), "result")
  let raw = object_fields(required(result, "actualPGresult", "result"), "raw")
  raw["fields"] = [{ "oid": 25, "format": 1, "typmod": -1 }].to_json()
  result["actualPGresult"] = raw.to_json()
  let root = object_fields(doc, "control")
  root["result"] = result.to_json()
  orm2_expect_reject(() => { ignore(orm2_control(root.to_json())) })
}

///|
test "source2 control source aggregate bytes are bounded before acceptance" {
  let text = "x".repeat(32769)
  orm2_expect_reject(() => { ignore(orm2_control(orm2_test_select(25, text.to_json(), text))) })
}

///|
test "source2 INSERT one affected row has zero result tuples" {
  let cursor = orm2_test_cursor([orm2_test_command()])
  ignore(orm2_command(cursor, "INSERT setup", Json::null(), "INSERT 0 1", Some(1)))
  assert_eq(cursor.at, 1)
}

///|
test "source2 wrong command count cannot masquerade as INSERT ACK" {
  let cursor = orm2_test_cursor([orm2_test_command()])
  orm2_expect_reject(() => { ignore(orm2_command(cursor, "INSERT setup", Json::null(), "INSERT 0 1", None)) })
}

///|
test "source2 incomplete source result cannot supply catalog proof" {
  let doc = orm2_test_select(25, "x".to_json(), "x")
  let result = object_fields(orm_get(doc, "result"), "result")
  result["complete"] = false.to_json()
  let root = object_fields(doc, "control")
  root["result"] = result.to_json()
  orm2_expect_reject(() => { ignore(orm2_control(root.to_json())) })
}

///|
test "source2 same window must retain physical connection and transaction" {
  for field in ["connection", "transaction"] {
    let first = orm2_test_select(25, "x".to_json(), "x")
    let second = object_fields(orm2_test_select(25, "x".to_json(), "x"), "second")
    second[field] = "another-identity".to_json()
    let cursor = orm2_test_cursor([first, second.to_json()])
    ignore(orm2_take(cursor, "SELECT metadata", Json::null()))
    orm2_expect_reject(() => { ignore(orm2_take(cursor, "SELECT metadata", Json::null())) })
  }
}

///|
test "source2 same window must retain backend PID" {
  let first = orm2_test_select(25, "x".to_json(), "x")
  let second = object_fields(orm2_test_select(25, "x".to_json(), "x"), "second")
  second["backendPid"] = (8).to_json()
  let cursor = orm2_test_cursor([first, second.to_json()])
  ignore(orm2_take(cursor, "SELECT metadata", Json::null()))
  orm2_expect_reject(() => { ignore(orm2_take(cursor, "SELECT metadata", Json::null())) })
}

///|
test "source2 mapping label is not exact SQL or parameter proof" {
  let cursor = orm2_test_cursor([orm2_test_select(25, "x".to_json(), "x")])
  orm2_expect_reject(() => { ignore(orm2_take(cursor, "SELECT other", Json::null())) })
  let cursor = orm2_test_cursor([orm2_test_select(25, "x".to_json(), "x")])
  orm2_expect_reject(() => { ignore(orm2_take(cursor, "SELECT metadata", ["invented"].to_json())) })
}

///|
test "source2 joins preserve actual six-null absent payload" {
  let key = "00000000-0000-4000-8000-000000000001"
  let token = "00000000-0000-4000-8000-000000000002"
  let absent : Json = { "id": Json::null(), "email": Json::null(), "hashed_password": Json::null(), "is_active": Json::null(), "is_superuser": Json::null(), "is_verified": Json::null() }
  let state : Map[String, Json] = Map([(key, { "version": token.to_json(), "present": false, "image": Json::null() })])
  let known = Map([(key, true)])
  orm2_snapshot_rows([[key.to_json(), token.to_json(), false.to_json(), Json::null(), Json::null(), Json::null(), absent].to_json()], state, known)
  orm2_expect_reject(() => { orm2_snapshot_rows([[key.to_json(), token.to_json(), false.to_json(), Json::null(), Json::null(), Json::null(), Json::null()].to_json()], state, known) })
}

///|
test "source2 installer JSONB columns cannot reuse business text transport" {
  assert_eq(orm2_control_payload("t"), "jsonb_build_object('id',t.\"id\"::text,'email',t.\"email\",'hashed_password',t.\"hashed_password\",'is_active',t.\"is_active\",'is_superuser',t.\"is_superuser\",'is_verified',t.\"is_verified\")")
  assert_eq(orm2_control_payload("\"s\".\"u\""), "jsonb_build_object('id',\"s\".\"u\".\"id\"::text,'email',\"s\".\"u\".\"email\",'hashed_password',\"s\".\"u\".\"hashed_password\",'is_active',\"s\".\"u\".\"is_active\",'is_superuser',\"s\".\"u\".\"is_superuser\",'is_verified',\"s\".\"u\".\"is_verified\")")
  assert_eq(orm2_snapshot_sql("s", "u"), "SELECT s.key,s.token::text,s.present,s.image,t.id::text,t.\"_mtw_orm_version\"::text,jsonb_build_object('id',t.\"id\"::text,'email',t.\"email\",'hashed_password',t.\"hashed_password\",'is_active',t.\"is_active\",'is_superuser',t.\"is_superuser\",'is_verified',t.\"is_verified\") FROM \"s\".\"_mtw_orm_state\" s LEFT JOIN \"s\".\"u\" t ON t.id=s.key::uuid ORDER BY s.key LIMIT 129")
  assert_true(orm_payload("t").has_suffix("::text::varchar(12288)"))
}

///|
test "source2 errors never export history or coverage exemptions" {
  let output = object_fields(guarded_json(orm_sql_source2_v3_proof_json("{}"), limit=65536), "diagnostic")
  assert_eq(required(output, "analysisCoverageAccepted", "output"), false.to_json())
  assert_eq(required(output, "history", "output"), Json::null())
  assert_eq(required(output, "controlProfileComplete", "output"), false.to_json())
  assert_eq(required(output, "provenStatements", "output"), orm_empty())
}
