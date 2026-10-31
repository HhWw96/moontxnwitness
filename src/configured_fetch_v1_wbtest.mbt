///|
fn fetch37_fixture() -> Json raise {
  sql_json_v1(
    "{\"config\":{\"format\":\"moontxnwitness-configured-sql/v1\",\"tables\":[{\"schema\":\"biz\",\"table\":\"orders\",\"primaryKey\":\"id\",\"columns\":[{\"name\":\"id\",\"type\":\"int64\",\"comparison\":null},{\"name\":\"enabled\",\"type\":\"bool\",\"comparison\":null},{\"name\":\"version\",\"type\":\"text\",\"comparison\":\"postgres-c-utf8-v1\"}],\"model\":\"relation-set-v1\"}],\"defaultSchema\":\"biz\",\"limits\":{\"max_sql_bytes\":65536,\"max_tokens\":8192,\"max_ast_nodes\":4096,\"max_nesting\":64,\"max_terms\":128,\"max_insert_rows\":128,\"max_text_bytes\":65536}},\"execution\":{\"candidate\":{\"bindings\":[{\"reference\":{\"kind\":\"positional\",\"type\":\"int64\",\"value\":0},\"value\":{\"type\":\"int64\",\"value\":\"1\"}}],\"configSha256\":\"bb90f296b2a0292a49f05f419456f7a6286eb571b6feeeb4936453defc20ec0f\",\"descriptor\":{\"assignments\":[],\"captureFactsProduced\":false,\"configSha256\":\"bb90f296b2a0292a49f05f419456f7a6286eb571b6feeeb4936453defc20ec0f\",\"databaseSyntaxValidated\":false,\"format\":\"moontxnwitness-sql-ast-candidate/v1\",\"insertColumns\":[],\"insertRows\":[],\"moonbitProjectionVerified\":false,\"operation\":\"select\",\"ordering\":[],\"originalSql\":\"SELECT id,enabled,version FROM biz.orders WHERE id=%s\",\"parameters\":[{\"kind\":\"positional\",\"type\":\"int64\",\"value\":0}],\"parserContract\":\"sqlglot-30.26-postgres-single-table/v1\",\"predicates\":[{\"collation\":null,\"column\":\"id\",\"operator\":\"eq\",\"value\":{\"kind\":\"positional\",\"type\":\"int64\",\"value\":0}}],\"projections\":[{\"column\":\"id\",\"outputName\":\"id\"},{\"column\":\"enabled\",\"outputName\":\"enabled\"},{\"column\":\"version\",\"outputName\":\"version\"}],\"requiredProofs\":[\"catalog-types-primary-key-and-text-collation\",\"session-schema-resolution\",\"server-encoding-and-string-literal-rules\",\"actual-execution-and-delivered-result-shape\",\"complete-fetch-for-predicate-read\",\"installed-unique-version-sources-and-effective-write-ledger\",\"same-statement-or-native-observed-read-version-identity\",\"complete-source-window-and-writer-scope\",\"independent-MoonBit-original-SQL-parameters-source-projection\"],\"requiresNoParameterArgument\":false,\"returning\":[],\"returningIsPredicateRead\":false,\"schemaResolution\":\"explicit-schema\",\"sourceAuthenticated\":false,\"sqlSha256\":\"c3579d7482ef0cc6517de6a08ff37f40c38fdb4dd0f380d4d2d7161b473421c3\",\"sqlglotVersion\":\"30.26.0\",\"table\":{\"columns\":[{\"comparison\":null,\"name\":\"id\",\"type\":\"int64\"},{\"comparison\":null,\"name\":\"enabled\",\"type\":\"bool\"},{\"comparison\":\"postgres-c-utf8-v1\",\"name\":\"version\",\"type\":\"text\"}],\"model\":\"relation-set-v1\",\"primaryKey\":\"id\",\"schema\":\"biz\",\"table\":\"orders\"}},\"format\":\"moontxnwitness-sql-binding-candidate/v1\",\"parametersSha256\":\"080a9ed428559ef602668b4c00f114f1a11c3f6b02a435f0bdc154578e4d7f22\",\"sqlSha256\":\"c3579d7482ef0cc6517de6a08ff37f40c38fdb4dd0f380d4d2d7161b473421c3\"},\"connection\":\"connection-e360f56bf5bc4e46ba82da4a82cd3f5b\",\"cursor\":\"cursor-8e3fac48e824462393447350394dc761\",\"format\":\"moontxnwitness-configured-execution/v1\",\"parameters\":[1],\"sourceFactsProduced\":false,\"sql\":\"SELECT id,enabled,version FROM biz.orders WHERE id=%s\",\"statementSeq\":3,\"tx\":\"transaction-31d9f246a62445d094749826482ea767\"},\"native\":{\"connection\":\"connection-e360f56bf5bc4e46ba82da4a82cd3f5b\",\"cursor\":\"cursor-8e3fac48e824462393447350394dc761\",\"executionNoteSeq\":5,\"fields\":[{\"format\":0,\"name\":\"id\",\"oid\":20,\"tableColumn\":1,\"tableOid\":17000,\"typmod\":-1},{\"format\":0,\"name\":\"enabled\",\"oid\":16,\"tableColumn\":2,\"tableOid\":17000,\"typmod\":-1},{\"format\":0,\"name\":\"version\",\"oid\":25,\"tableColumn\":3,\"tableOid\":17000,\"typmod\":-1}],\"format\":\"moontxnwitness-native-result/v1\",\"parametersSha256\":\"080a9ed428559ef602668b4c00f114f1a11c3f6b02a435f0bdc154578e4d7f22\",\"resultId\":\"result-4da4e9abc44f4a789fecd8ec8f521af2\",\"rows\":[[\"MQ==\",\"dA==\",\"5Yid8J+Zgg==\"],[\"Mg==\",\"Zg==\",\"djI=\"]],\"sourceFactsProduced\":false,\"sqlSha256\":\"c3579d7482ef0cc6517de6a08ff37f40c38fdb4dd0f380d4d2d7161b473421c3\",\"statementSeq\":3,\"status\":2,\"storedColumnDeclarations\":[],\"tx\":\"transaction-31d9f246a62445d094749826482ea767\"},\"deliveries\":[{\"complete\":false,\"connection\":\"connection-e360f56bf5bc4e46ba82da4a82cd3f5b\",\"cursor\":\"cursor-8e3fac48e824462393447350394dc761\",\"format\":\"moontxnwitness-actual-delivery/v1\",\"method\":\"fetchone\",\"nativeNoteSeq\":6,\"resultId\":\"result-4da4e9abc44f4a789fecd8ec8f521af2\",\"rows\":[[{\"type\":\"int64\",\"value\":\"1\"},{\"type\":\"bool\",\"value\":true},{\"type\":\"text\",\"value\":\"初🙂\"}]],\"sourceFactsProduced\":false,\"start\":0,\"statementSeq\":3,\"tx\":\"transaction-31d9f246a62445d094749826482ea767\"},{\"complete\":true,\"connection\":\"connection-e360f56bf5bc4e46ba82da4a82cd3f5b\",\"cursor\":\"cursor-8e3fac48e824462393447350394dc761\",\"format\":\"moontxnwitness-actual-delivery/v1\",\"method\":\"fetchone\",\"nativeNoteSeq\":6,\"resultId\":\"result-4da4e9abc44f4a789fecd8ec8f521af2\",\"rows\":[[{\"type\":\"int64\",\"value\":\"2\"},{\"type\":\"bool\",\"value\":false},{\"type\":\"text\",\"value\":\"v2\"}]],\"sourceFactsProduced\":false,\"start\":1,\"statementSeq\":3,\"tx\":\"transaction-31d9f246a62445d094749826482ea767\"},{\"complete\":true,\"connection\":\"connection-e360f56bf5bc4e46ba82da4a82cd3f5b\",\"cursor\":\"cursor-8e3fac48e824462393447350394dc761\",\"format\":\"moontxnwitness-actual-delivery/v1\",\"method\":\"fetchone\",\"nativeNoteSeq\":6,\"resultId\":\"result-4da4e9abc44f4a789fecd8ec8f521af2\",\"rows\":[],\"sourceFactsProduced\":false,\"start\":2,\"statementSeq\":3,\"tx\":\"transaction-31d9f246a62445d094749826482ea767\"}]}",
    1048576,
  )
}

///|
fn fetch37_run(
  f : Json,
  max_checks~ : Int32 = 1000000,
  grammar_checks~ : Int32 = 1000000,
) -> Json raise {
  let fields = object_fields(f, "fixture")
  let config = parse_sql_config_v1(fields.at("config").stringify()).unwrap()
  configured_fetch_check_v1_json(
    verify_configured_fetch_v1(
      config,
      fields.at("execution"),
      fields.at("native"),
      fields.at("deliveries"),
      max_checks~,
      grammar_options=sql_verification_options_v1(max_checks=grammar_checks),
    ),
  )
}

///|
fn fetch37_field(f : Json, name : String) -> Map[String, Json] raise {
  object_fields(object_fields(f, "fixture").at(name), name)
}

///|
fn fetch37_batch(f : Json, index : Int32) -> Map[String, Json] raise {
  object_fields(
    orm_array(object_fields(f, "fixture").at("deliveries"))[index],
    "batch",
  )
}

///|
fn fetch37_native_field(f : Json, index : Int32) -> Map[String, Json] raise {
  object_fields(
    orm_array(fetch37_field(f, "native").at("fields"))[index],
    "native field",
  )
}

///|
test "fetch37 01 roundtrip" {
  let f = fetch37_fixture()
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("matched"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 02 wrong source SQL" {
  let f = fetch37_fixture()
  fetch37_field(f, "execution").set(
    "sql",
    Json("SELECT id FROM biz.orders WHERE id=%s"),
  )
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("mismatch"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 03 wrong binding" {
  let f = fetch37_fixture()
  fetch37_field(f, "execution").set("parameters", [2])
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("mismatch"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 04 wrong native source hash" {
  let f = fetch37_fixture()
  fetch37_field(f, "native").set("sqlSha256", Json("wrong"))
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("mismatch"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 05 wrong native parameters hash" {
  let f = fetch37_fixture()
  fetch37_field(f, "native").set("parametersSha256", Json("wrong"))
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("mismatch"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 06 native tx identity" {
  let f = fetch37_fixture()
  fetch37_field(f, "native").set("tx", Json("other"))
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("mismatch"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 07 delivery tx identity" {
  let f = fetch37_fixture()
  fetch37_batch(f, 0).set("tx", Json("other"))
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("mismatch"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 08 delivery result identity" {
  let f = fetch37_fixture()
  fetch37_batch(f, 0).set("resultId", Json("other"))
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("mismatch"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 09 delivery start skipped" {
  let f = fetch37_fixture()
  fetch37_batch(f, 0).set("start", Json(1))
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("mismatch"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 10 native output name" {
  let f = fetch37_fixture()
  fetch37_native_field(f, 0).set("name", Json("other"))
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("mismatch"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 11 native OID" {
  let f = fetch37_fixture()
  fetch37_native_field(f, 0).set("oid", Json(2950))
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("unknown"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 12 native binary format" {
  let f = fetch37_fixture()
  fetch37_native_field(f, 0).set("format", Json(1))
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("unknown"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 13 native empty result shape" {
  let f = fetch37_fixture()
  fetch37_field(f, "native").set("fields", [])
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("unknown"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 14 unknown execution field" {
  let f = fetch37_fixture()
  fetch37_field(f, "execution").set("trusted", Json(true))
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("unknown"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 15 source facts grant rejected" {
  let f = fetch37_fixture()
  fetch37_field(f, "execution").set("sourceFactsProduced", Json(true))
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("mismatch"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 16 native source grant rejected" {
  let f = fetch37_fixture()
  fetch37_field(f, "native").set("sourceFactsProduced", Json(true))
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("mismatch"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 17 delivery source grant rejected" {
  let f = fetch37_fixture()
  fetch37_batch(f, 0).set("sourceFactsProduced", Json(true))
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("mismatch"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 18 unknown native format" {
  let f = fetch37_fixture()
  fetch37_field(f, "native").set("format", Json("next"))
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("mismatch"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 19 unconfigured version declaration" {
  let f = fetch37_fixture()
  fetch37_field(f, "native").set("storedColumnDeclarations", ["missing"])
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("mismatch"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 20 duplicate version declaration" {
  let f = fetch37_fixture()
  fetch37_field(f, "native").set("storedColumnDeclarations", [
    "version", "version",
  ])
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("mismatch"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 21 no fetch stays partial" {
  let f = fetch37_fixture()
  object_fields(f, "fixture").set("deliveries", [])
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("partial"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 22 wrong delivery method" {
  let f = fetch37_fixture()
  fetch37_batch(f, 0).set("method", Json("execute-prefetch"))
  let report = object_fields(fetch37_run(f), "report")
  assert_eq(report.at("status"), Json("unknown"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 23 budget zero" {
  let f = fetch37_fixture()
  let report = object_fields(fetch37_run(f, max_checks=0), "report")
  assert_eq(report.at("status"), Json("unknown"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 24 grammar budget zero" {
  let f = fetch37_fixture()
  let report = object_fields(fetch37_run(f, grammar_checks=0), "report")
  assert_eq(report.at("status"), Json("unknown"))
  assert_eq(report.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 exact budget succeeds and one fewer stays unknown" {
  let f = fetch37_fixture()
  let report = object_fields(fetch37_run(f), "report")
  let count = fetch_number_v1(
    object_fields(report.at("execution"), "execution").at("checks"),
    1000000,
  )
  assert_eq(
    object_fields(fetch37_run(f, max_checks=count), "report").at("status"),
    Json("matched"),
  )
  assert_eq(
    object_fields(fetch37_run(f, max_checks=count - 1), "report").at("status"),
    Json("unknown"),
  )
}

///|
test "fetch37 raw duplicate and unknown caller options refused" {
  let f = object_fields(fetch37_fixture(), "fixture")
  for
    options in [
      "{\"maxChecks\":0,\"max\u0043hecks\":100}", "{\"unknown\":true}", "{\"maxChecks\":1000001}",
    ] {
    let report = object_fields(
      sql_json_v1(
        verify_configured_fetch_v1_json(
          f.at("config").stringify(),
          f.at("execution").stringify(),
          f.at("native").stringify(),
          f.at("deliveries").stringify(),
          options,
        ),
        1048576,
      ),
      "report",
    )
    assert_eq(report.at("valid"), Json(false))
  }
}

///|
test "fetch37 full fetch still does not authenticate catalogue or writer window" {
  let report = object_fields(fetch37_run(fetch37_fixture()), "report")
  assert_eq(report.at("completeFetchVerified"), Json(true))
  for
    key in [
      "sourceAuthenticated", "catalogVerified", "sourceWindowVerified", "isolationModelChecked",
    ] {
    assert_eq(report.at(key), Json(false))
  }
}

///|
test "fetch37 result getter returns independent JSON" {
  let f = object_fields(fetch37_fixture(), "fixture")
  let config = parse_sql_config_v1(f.at("config").stringify()).unwrap()
  let checked = verify_configured_fetch_v1(
    config,
    f.at("execution"),
    f.at("native"),
    f.at("deliveries"),
  )
  object_fields(configured_fetch_check_v1_json(checked), "report").set(
    "sourceFactsProduced",
    Json(true),
  )
  assert_eq(
    object_fields(configured_fetch_check_v1_json(checked), "report").at(
      "sourceFactsProduced",
    ),
    Json(false),
  )
}

///|
test "fetch37 native row tamper is detected independently" {
  let f = fetch37_fixture()
  let rows = orm_array(fetch37_field(f, "native").at("rows"))
  orm_array(rows[0])[0] = Json("OTk=")
  assert_eq(
    object_fields(fetch37_run(f), "report").at("status"),
    Json("mismatch"),
  )
}

///|
test "fetch37 actual delivered value tamper is detected" {
  let f = fetch37_fixture()
  let rows = orm_array(fetch37_batch(f, 0).at("rows"))
  orm_array(rows[0])[0] = { "type": "int64", "value": "99" }
  assert_eq(
    object_fields(fetch37_run(f), "report").at("status"),
    Json("mismatch"),
  )
}

///|
test "fetch37 empty result requires actual exhaustion delivery" {
  let f = fetch37_fixture()
  fetch37_field(f, "native").set("rows", [])
  let batch = fetch37_batch(f, 0)
  batch.set("rows", [])
  batch.set("complete", Json(true))
  batch.set("method", Json("fetchall"))
  object_fields(f, "fixture").set("deliveries", [Json(batch)])
  let r = object_fields(fetch37_run(f), "report")
  assert_eq(r.at("status"), Json("matched"))
  assert_eq(r.at("nativeRows"), Json(0))
  assert_eq(r.at("sourceFactsProduced"), Json(false))
}

///|
test "fetch37 physical metadata without source installation stays observations only" {
  let f = fetch37_fixture()
  fetch37_field(f, "native").set("storedColumnDeclarations", ["version"])
  let r = object_fields(fetch37_run(f), "report")
  assert_eq(r.at("storedColumnObservations"), Json(2))
  assert_eq(r.at("sourceWindowVerified"), Json(false))
  fetch37_native_field(f, 2).set("tableOid", Json(0))
  assert_eq(
    object_fields(fetch37_run(f), "report").at("storedColumnObservations"),
    Json(0),
  )
}
