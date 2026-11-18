///|
fn sql52_config_text(index : Int32) -> String {
  [
    "{\"defaultSchema\":null,\"format\":\"moontxnwitness-configured-sql/v2\",\"limits\":{\"max_ast_nodes\":4096,\"max_nesting\":64,\"max_sql_bytes\":65536,\"max_text_bytes\":65536,\"max_tokens\":8192},\"table\":{\"businessColumns\":[{\"comparison\":null,\"name\":\"balance\",\"type\":\"int64\"},{\"comparison\":null,\"name\":\"active\",\"type\":\"bool\"},{\"comparison\":\"postgres-c-utf8-v1\",\"name\":\"label\",\"type\":\"text\"}],\"primaryKey\":{\"comparison\":null,\"name\":\"account_no\",\"type\":\"int64\"},\"schema\":\"ledger\",\"table\":\"accounts\"}}",
    "{\"defaultSchema\":null,\"format\":\"moontxnwitness-configured-sql/v2\",\"limits\":{\"max_ast_nodes\":4096,\"max_nesting\":64,\"max_sql_bytes\":65536,\"max_text_bytes\":65536,\"max_tokens\":8192},\"table\":{\"businessColumns\":[{\"comparison\":null,\"name\":\"quota\",\"type\":\"int64\"},{\"comparison\":null,\"name\":\"live\",\"type\":\"bool\"},{\"comparison\":\"postgres-c-utf8-v1\",\"name\":\"zone\",\"type\":\"text\"},{\"comparison\":null,\"name\":\"score\",\"type\":\"int64\"},{\"comparison\":\"postgres-c-utf8-v1\",\"name\":\"note\",\"type\":\"text\"}],\"primaryKey\":{\"comparison\":\"postgres-c-utf8-v1\",\"name\":\"User ID\",\"type\":\"text\"},\"schema\":\"App-X\",\"table\":\"Customer.Space\"}}",
    "{\"defaultSchema\":null,\"format\":\"moontxnwitness-configured-sql/v2\",\"limits\":{\"max_ast_nodes\":4096,\"max_nesting\":64,\"max_sql_bytes\":65536,\"max_text_bytes\":65536,\"max_tokens\":8192},\"table\":{\"businessColumns\":[{\"comparison\":\"postgres-c-utf8-v1\",\"name\":\"email\",\"type\":\"text\"},{\"comparison\":null,\"name\":\"is_active\",\"type\":\"bool\"}],\"primaryKey\":{\"comparison\":null,\"name\":\"member_uuid\",\"type\":\"uuid\"},\"schema\":\"identity\",\"table\":\"members\"}}",
  ][index]
}

///|
fn sql52_report(
  index : Int32,
  source : String,
  parameters : String,
  options~ : String = "{}",
) -> Json raise {
  sql_json_v1(
    normalize_configured_sql_v2_json(
      sql52_config_text(index),
      source,
      parameters,
      options,
    ),
    8388608,
  )
}

///|
test "sql52 three real Python layouts match all CRUD descriptor hashes" {
  for
    (layout, source, parameters, digest) in [
      (
        0, "SELECT \"account_no\",\"balance\",\"active\",\"label\" FROM \"ledger\".\"accounts\" WHERE \"account_no\"=%s",
        "[17]", "8c125bdd5c54f7f39c652381f6c1bbc1b74c3bb97fddf7c098473991eab90f3f",
      ),
      (
        0, "INSERT INTO \"ledger\".\"accounts\"(\"account_no\",\"balance\",\"active\",\"label\") VALUES(%s,%s,%s,%s) RETURNING *",
        "[17,17,true,\"值🙂\"]", "b7b8a7045542f56ba4d2cfaaa3d6e7b7d91aebfabd0742b14aa0e69f7bf48b11",
      ),
      (
        0, "UPDATE \"ledger\".\"accounts\" SET \"balance\"=%s WHERE \"account_no\"=%s RETURNING \"account_no\"",
        "[17,17]", "9c3ec26ba5af8b599c2e5fd88f465f964c17a7e8139be8563234698f96083bb1",
      ),
      (
        0, "DELETE FROM \"ledger\".\"accounts\" WHERE \"account_no\"=%s", "[17]",
        "45798894aa6b6d08d3792a896bbc44f5ce5f56c90116f5c147ab861b5b88e4f2",
      ),
      (
        1, "SELECT \"User ID\",\"quota\",\"live\",\"zone\",\"score\",\"note\" FROM \"App-X\".\"Customer.Space\" WHERE \"User ID\"=%s",
        "[\"值🙂\"]", "523a36f49b7a04e72136e1d29bdafa631d3cb87144ceac7791d032425e5d72d2",
      ),
      (
        1, "INSERT INTO \"App-X\".\"Customer.Space\"(\"User ID\",\"quota\",\"live\",\"zone\",\"score\",\"note\") VALUES(%s,%s,%s,%s,%s,%s) RETURNING *",
        "[\"值🙂\",17,true,\"值🙂\",17,\"值🙂\"]", "661e33c66384e1ecae732c1db58a6c9aaf1b91c42329bf95482ac9ca322c666c",
      ),
      (
        1, "UPDATE \"App-X\".\"Customer.Space\" SET \"quota\"=%s WHERE \"User ID\"=%s RETURNING \"User ID\"",
        "[17,\"值🙂\"]", "d9fe79fbdfeb7a0e0e117a36eb39543f8687613c4c603299d707c6a26672088f",
      ),
      (
        1, "DELETE FROM \"App-X\".\"Customer.Space\" WHERE \"User ID\"=%s", "[\"值🙂\"]",
        "4d3664fa3b1374773e4bce749df5c05b476f450c9e5f2ec9ac886abe6fb2f2db",
      ),
      (
        2, "SELECT \"member_uuid\",\"email\",\"is_active\" FROM \"identity\".\"members\" WHERE \"member_uuid\"=%s::UUID",
        "[\"A8098C1AF86E11DABD1A00112444BE1E\"]", "f3ded52274c8ea22243904f4eb5f67435b84f5d3d19c118c616c6a7290d70aeb",
      ),
      (
        2, "INSERT INTO \"identity\".\"members\"(\"member_uuid\",\"email\",\"is_active\") VALUES(%s::UUID,%s,%s) RETURNING *",
        "[\"A8098C1AF86E11DABD1A00112444BE1E\",\"值🙂\",true]", "6ea8b7081def53092a10c903c4ed5f62cd98e2e511619c91f5e1e754e4f1f4f4",
      ),
      (
        2, "UPDATE \"identity\".\"members\" SET \"email\"=%s WHERE \"member_uuid\"=%s::UUID RETURNING \"member_uuid\"",
        "[\"值🙂\",\"A8098C1AF86E11DABD1A00112444BE1E\"]", "208264893641392834ca72f1ce95c6523315d2e4348356f0ad6c1998f15c4650",
      ),
      (
        2, "DELETE FROM \"identity\".\"members\" WHERE \"member_uuid\"=%s::UUID",
        "[\"A8098C1AF86E11DABD1A00112444BE1E\"]", "16ba347ef2c526a68eaeb1761fbb0b9764782fd9716c01126a42f576a8d259f4",
      ),
    ] {
    let report = sql52_report(layout, source, parameters)
    assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
    assert_eq(
      v3_dislock_sha256(sql_canonical_v1(v4_test_at(report, ["descriptor"]))),
      digest,
    )
    for
      claim in [
        "captureFactsProduced", "sourceFactsProduced", "sourceAuthenticated", "actualDriverResultsVerified",
        "sourceWindowVerified", "modelCoverageAccepted", "moonbitProjectionVerified",
        "databaseSyntaxValidated",
      ] {
      assert_eq(v4_test_at(report, [claim]), Json(false))
    }
  }
}

///|
test "sql52 UUID spelling identity preserves original binding observations" {
  let source = "SELECT * FROM identity.members WHERE member_uuid=%(pk_1)s::UUID"
  let mut previous_hash = ""
  for
    spelling in [
      "a8098c1a-f86e-11da-bd1a-00112444be1e", "A8098C1A-F86E-11DA-BD1A-00112444BE1E",
      "A8098C1AF86E11DABD1A00112444BE1E",
    ] {
    let parameters : Json = { "pk_1": Json(spelling) }
    let before = parameters.stringify()
    let config = parse_sql_config_v2(sql52_config_text(2)).unwrap()
    let report = sql_candidate_check_v2_json(
      normalize_sql_candidate_v2(config, source, parameters),
    )
    assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
    assert_eq(v4_test_at(report, ["originalParameters"]), parameters)
    assert_eq(parameters.stringify(), before)
    let bindings = match v4_test_at(report, ["bindings"]) {
      Array(items) => items
      _ => []
    }
    assert_eq(
      v4_test_at(bindings[0], ["value", "value"]),
      Json("a8098c1a-f86e-11da-bd1a-00112444be1e"),
    )
    let digest = sql_string_v1(v4_test_at(report, ["originalParametersSha256"]))
    assert_true(digest != previous_hash)
    previous_hash = digest
  }
}

///|
test "sql52 valid UUID casts and distinct unseen runtime keys need no known ids" {
  for
    source in [
      "SELECT * FROM identity.members WHERE member_uuid=%s", "SELECT * FROM identity.members WHERE member_uuid=CAST(%s AS UUID)",
      "SELECT * FROM identity.members WHERE (member_uuid=(%s::UUID))",
    ] {
    for
      key in [
        "00000000000000000000000000000000", "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF", "00000000000000000000000000000011",
      ] {
      assert_eq(
        v4_test_at(sql52_report(2, source, Json([Json(key)]).stringify()), [
          "status",
        ]),
        Json("recognized"),
      )
    }
  }
}

///|
test "sql52 independent config and zero caller budgets cannot be candidate authorized" {
  let source = "SELECT * FROM ledger.accounts WHERE account_no=%s"
  let config = parse_sql_config_v2(sql52_config_text(0)).unwrap()
  let normalized = sql_candidate_check_v2_json(
    normalize_sql_candidate_v2(config, source, Json([Json(7)])),
  )
  let candidate = v4_test_at(normalized, ["descriptor"])
  for
    options in [
      sql_verification_options_v2(max_checks=0),
      sql_verification_options_v2(max_tokens=0),
      sql_verification_options_v2(max_sql_bytes=0),
    ] {
    let report = sql_candidate_check_v2_json(
      verify_sql_candidate_v2(
        config,
        source,
        Json([Json(7)]),
        candidate,
        options~,
      ),
    )
    assert_eq(v4_test_at(report, ["status"]), Json("unknown"))
    assert_eq(v4_test_at(report, ["valid"]), Json(false))
    assert_eq(v4_test_at(report, ["sourceFactsProduced"]), Json(false))
  }
  let fields = object_fields(v4_json_copy(candidate), "candidate")
  fields["configSha256"] = Json("untrusted")
  let mismatch = sql_candidate_check_v2_json(
    verify_sql_candidate_v2(
      config,
      source,
      Json([Json(7)]),
      Json::object(fields),
    ),
  )
  assert_eq(v4_test_at(mismatch, ["status"]), Json("mismatch"))
}

///|
test "sql52 candidate provenance and completeness flags never grant source acceptance" {
  let source = "SELECT * FROM ledger.accounts WHERE account_no=%s"
  let config = parse_sql_config_v2(sql52_config_text(0)).unwrap()
  let report = sql_candidate_check_v2_json(
    normalize_sql_candidate_v2(config, source, Json([Json(7)])),
  )
  let candidate = v4_test_at(report, ["descriptor"])
  for
    name in [
      "sourceAuthenticated", "sourceFactsProduced", "modelCoverageAccepted", "moonbitProjectionVerified",
      "complete",
    ] {
    let fields = object_fields(v4_json_copy(candidate), "candidate")
    fields[name] = Json(true)
    let checked = sql_candidate_check_v2_json(
      verify_sql_candidate_v2(
        config,
        source,
        Json([Json(7)]),
        Json::object(fields),
      ),
    )
    assert_eq(v4_test_at(checked, ["status"]), Json("mismatch"))
    assert_eq(v4_test_at(checked, ["sourceFactsProduced"]), Json(false))
    assert_eq(v4_test_at(checked, ["captureFactsProduced"]), Json(false))
    assert_eq(v4_test_at(checked, ["modelCoverageAccepted"]), Json(false))
  }
}

///|
test "sql52 V1 acceptance and wire formats remain separate" {
  assert_true(parse_sql_config_v1(sql52_config_text(0)) is Err(_))
  assert_true(
    parse_sql_config_v2(sql_config_v1_json(sp37_config()).stringify()) is Err(_),
  )
  for
    source in [
      "SELECT feature_key FROM app.flags WHERE feature_key=%s::UUID", "SELECT feature_key FROM app.flags WHERE feature_key=CAST(%s AS UUID)",
    ] {
    assert_eq(
      v4_test_at(sp37_normalize(source, "[\"x\"]"), ["valid"]),
      Json(false),
    )
  }
  let source = "SELECT * FROM ledger.accounts WHERE account_no=%s"
  let config = parse_sql_config_v2(sql52_config_text(0)).unwrap()
  let normalized = sql_candidate_check_v2_json(
    normalize_sql_candidate_v2(config, source, Json([Json(7)])),
  )
  let fields = object_fields(
    v4_test_at(normalized, ["descriptor"]),
    "candidate",
  )
  fields["format"] = Json("moontxnwitness-sql-ast-candidate/v1")
  let report = sql_candidate_check_v2_json(
    verify_sql_candidate_v2(
      config,
      source,
      Json([Json(7)]),
      Json::object(fields),
    ),
  )
  assert_eq(v4_test_at(report, ["status"]), Json("mismatch"))
}

///|
test "sql52 unsupported partial and conditional SQL remains diagnostic" {
  for
    source in [
      "SELECT account_no FROM ledger.accounts WHERE account_no=%s", "SELECT * FROM ledger.accounts WHERE account_no=%s AND active=true",
      "SELECT * FROM ledger.accounts WHERE account_no>%s", "SELECT * FROM ledger.accounts WHERE account_no=%s OR account_no=%s",
      "SELECT * FROM ledger.accounts WHERE account_no IN (%s)", "SELECT * FROM ledger.accounts WHERE account_no=NULL",
      "SELECT * FROM ledger.accounts WHERE account_no=%s LIMIT 1", "SELECT * FROM ledger.accounts WHERE account_no=%s FOR UPDATE",
      "SELECT * FROM ledger.accounts WHERE account_no=%s::UUID", "SELECT * FROM ledger.accounts a JOIN ledger.accounts b ON a.account_no=b.account_no WHERE a.account_no=%s",
      "SELECT * FROM ledger.accounts WHERE account_no=abs(%s)", "UPDATE ledger.accounts SET account_no=%s WHERE account_no=%s",
      "UPDATE ledger.accounts SET balance=1 WHERE account_no=%s", "UPDATE ledger.accounts SET balance=balance+1 WHERE account_no=%s",
      "DELETE FROM ledger.accounts", "INSERT INTO ledger.accounts(account_no,balance) VALUES(%s,%s)",
      "INSERT INTO ledger.accounts(account_no,balance,active,label) VALUES(%s,%s,%s,%s),(%s,%s,%s,%s)",
      "INSERT INTO ledger.accounts(account_no,balance,active,label) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
    ] {
    let report = sql52_report(0, source, "[7]")
    assert_eq(v4_test_at(report, ["valid"]), Json(false))
    assert_eq(v4_test_at(report, ["sourceFactsProduced"]), Json(false))
  }
}

///|
test "sql52 UUID functions literals arrays and malformed observations remain diagnostic" {
  for
    source in [
      "SELECT * FROM identity.members WHERE member_uuid=%s::UUID[]", "SELECT * FROM identity.members WHERE member_uuid=%s::text",
      "SELECT * FROM identity.members WHERE member_uuid=CAST(%s::text AS UUID)",
      "SELECT * FROM identity.members WHERE member_uuid=uuid_generate_v4()", "SELECT * FROM identity.members WHERE member_uuid='00000000-0000-0000-0000-000000000001'::UUID",
    ] {
    assert_eq(
      v4_test_at(
        sql52_report(2, source, "[\"00000000000000000000000000000001\"]"),
        ["valid"],
      ),
      Json(false),
    )
  }
  for
    parameters in [
      "[null]", "[true]", "[\"not-uuid\"]", "[\"0000000000000000-0000000000000000\"]",
      "[\"{00000000-0000-0000-0000-000000000001}\"]",
    ] {
    assert_eq(
      v4_test_at(
        sql52_report(
          2, "SELECT * FROM identity.members WHERE member_uuid=%s::UUID", parameters,
        ),
        ["valid"],
      ),
      Json(false),
    )
  }
}

///|
test "sql52 config business columns and type declarations stay bounded" {
  let base = sql_json_v1(sql52_config_text(0), 262144)
  for count in [0, 17] {
    let fields = object_fields(v4_json_copy(base), "config")
    let table = object_fields(fields.at("table"), "table")
    let columns : Array[Json] = []
    for index = 0; index < count; index = index + 1 {
      columns.push({ "name": Json("v" + index.to_string()), "type": "int64" })
    }
    table["businessColumns"] = Json(columns)
    assert_true(parse_sql_config_v2(Json::object(fields).stringify()) is Err(_))
  }
  assert_true(
    parse_sql_config_v2("{\"format\":\"x\",\"for\\u006dat\":\"x\"}") is Err(_),
  )
}

///|
test "sql52 wire input and option errors never produce facts" {
  for
    options in [
      "{\"maxChecks\":-1}", "{\"maxChecks\":true}", "{\"complete\":true}", "null",
    ] {
    let report = sql52_report(
      0,
      "SELECT * FROM ledger.accounts WHERE account_no=%s",
      "[7]",
      options~,
    )
    assert_eq(v4_test_at(report, ["status"]), Json("invalid"))
    assert_eq(v4_test_at(report, ["sourceFactsProduced"]), Json(false))
  }
  let report = sql52_report(
    0, "SELECT * FROM ledger.accounts WHERE account_no=%s", "[9223372036854775808]",
  )
  assert_eq(v4_test_at(report, ["valid"]), Json(false))
  assert_eq(v4_test_at(report, ["status"]), Json("mismatch"))
}
