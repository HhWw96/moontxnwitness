///|
// Static hashes are from the frozen, independently executed Python constructor.
fn point52_case(
  index : Int32,
) -> (SQLConfigV2, String, Json, PointProjectionOptionsV2, String) raise {
  let configs = [
    "{\"defaultSchema\":null,\"format\":\"moontxnwitness-configured-sql/v2\",\"limits\":{\"max_ast_nodes\":4096,\"max_nesting\":64,\"max_sql_bytes\":65536,\"max_text_bytes\":65536,\"max_tokens\":8192},\"table\":{\"businessColumns\":[{\"comparison\":null,\"name\":\"balance\",\"type\":\"int64\"},{\"comparison\":null,\"name\":\"active\",\"type\":\"bool\"},{\"comparison\":\"postgres-c-utf8-v1\",\"name\":\"label\",\"type\":\"text\"}],\"primaryKey\":{\"comparison\":null,\"name\":\"account_no\",\"type\":\"int64\"},\"schema\":\"ledger\",\"table\":\"accounts\"}}",
    "{\"defaultSchema\":null,\"format\":\"moontxnwitness-configured-sql/v2\",\"limits\":{\"max_ast_nodes\":4096,\"max_nesting\":64,\"max_sql_bytes\":65536,\"max_text_bytes\":65536,\"max_tokens\":8192},\"table\":{\"businessColumns\":[{\"comparison\":null,\"name\":\"quota\",\"type\":\"int64\"},{\"comparison\":null,\"name\":\"live\",\"type\":\"bool\"},{\"comparison\":\"postgres-c-utf8-v1\",\"name\":\"zone\",\"type\":\"text\"}],\"primaryKey\":{\"comparison\":\"postgres-c-utf8-v1\",\"name\":\"User ID\",\"type\":\"text\"},\"schema\":\"App-X\",\"table\":\"Customer.Space\"}}",
    "{\"defaultSchema\":null,\"format\":\"moontxnwitness-configured-sql/v2\",\"limits\":{\"max_ast_nodes\":4096,\"max_nesting\":64,\"max_sql_bytes\":65536,\"max_text_bytes\":65536,\"max_tokens\":8192},\"table\":{\"businessColumns\":[{\"comparison\":\"postgres-c-utf8-v1\",\"name\":\"电子邮件\",\"type\":\"text\"},{\"comparison\":null,\"name\":\"启用\",\"type\":\"bool\"}],\"primaryKey\":{\"comparison\":null,\"name\":\"用户编号\",\"type\":\"uuid\"},\"schema\":\"业务\",\"table\":\"成员\"}}",
    "{\"defaultSchema\":null,\"format\":\"moontxnwitness-configured-sql/v2\",\"limits\":{\"max_ast_nodes\":4096,\"max_nesting\":64,\"max_sql_bytes\":65536,\"max_text_bytes\":65536,\"max_tokens\":8192},\"table\":{\"businessColumns\":[{\"comparison\":null,\"name\":\"__mtw_v2_new\",\"type\":\"int64\"},{\"comparison\":null,\"name\":\"__mtw_v2_old_0\",\"type\":\"int64\"}],\"primaryKey\":{\"comparison\":null,\"name\":\"k\",\"type\":\"int64\"},\"schema\":\"s\",\"table\":\"__mtw_v2_old\"}}",
    "{\"defaultSchema\":null,\"format\":\"moontxnwitness-configured-sql/v2\",\"limits\":{\"max_ast_nodes\":4096,\"max_nesting\":64,\"max_sql_bytes\":65536,\"max_text_bytes\":65536,\"max_tokens\":8192},\"table\":{\"businessColumns\":[{\"comparison\":null,\"name\":\"v%\\\"\",\"type\":\"int64\"}],\"primaryKey\":{\"comparison\":null,\"name\":\"k\",\"type\":\"int64\"},\"schema\":\"s%\",\"table\":\"t%s\"}}",
    "{\"defaultSchema\":null,\"format\":\"moontxnwitness-configured-sql/v2\",\"limits\":{\"max_ast_nodes\":4096,\"max_nesting\":64,\"max_sql_bytes\":65536,\"max_text_bytes\":65536,\"max_tokens\":8192},\"table\":{\"businessColumns\":[{\"comparison\":null,\"name\":\"v\",\"type\":\"bool\"}],\"primaryKey\":{\"comparison\":\"postgres-c-utf8-v1\",\"name\":\"k*\",\"type\":\"text\"},\"schema\":\"s\",\"table\":\"t\"}}",
  ]
  let (config_index, source, parameters, options, digest) = [
      (
        0, "SELECT \"account_no\", \"balance\", \"active\", \"label\" FROM \"ledger\".\"accounts\" WHERE \"account_no\"=%s",
        "{\"container\":\"tuple\",\"items\":[{\"decimal\":\"7\",\"pythonType\":\"int\"}]}",
        "{\"businessStarColumns\":[\"account_no\",\"balance\",\"active\",\"label\"],\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":\"preinstallation-business-schema/v1\",\"versionColumn\":\"__mtw_source_version\",\"versionType\":\"int64\"}",
        "070a5a198784336cff511eda78bd3def3e7da4fdbc7c0880b266934e53d0e05b",
      ),
      (
        0, "INSERT INTO \"ledger\".\"accounts\"(\"account_no\", \"balance\", \"active\", \"label\") VALUES (%s, %s, %s, %s) RETURNING *",
        "{\"container\":\"tuple\",\"items\":[{\"decimal\":\"8\",\"pythonType\":\"int\"},{\"decimal\":\"17\",\"pythonType\":\"int\"},{\"pythonType\":\"bool\",\"value\":true},{\"pythonType\":\"str\",\"value\":\"原始🙂文本\"}]}",
        "{\"businessStarColumns\":[\"account_no\",\"balance\",\"active\",\"label\"],\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":\"preinstallation-business-schema/v1\",\"versionColumn\":\"__mtw_source_version\",\"versionType\":\"int64\"}",
        "27e9cc59554bff44b20c8a80c9a836faa55ac90b9014c3b94698fd3bc2d44965",
      ),
      (
        0, "UPDATE \"ledger\".\"accounts\" SET \"balance\"=%s WHERE \"account_no\"=%s RETURNING *",
        "{\"container\":\"tuple\",\"items\":[{\"decimal\":\"23\",\"pythonType\":\"int\"},{\"decimal\":\"7\",\"pythonType\":\"int\"}]}",
        "{\"businessStarColumns\":[\"account_no\",\"balance\",\"active\",\"label\"],\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":\"preinstallation-business-schema/v1\",\"versionColumn\":\"__mtw_source_version\",\"versionType\":\"int64\"}",
        "395a93f325c30c298250958f95db22ffc7a9a7a4af6c83b0022a39c390e51812",
      ),
      (
        0, "DELETE FROM \"ledger\".\"accounts\" WHERE \"account_no\"=%s RETURNING \"account_no\" AS \"Business Key\"",
        "{\"container\":\"tuple\",\"items\":[{\"decimal\":\"7\",\"pythonType\":\"int\"}]}",
        "{\"businessStarColumns\":[\"account_no\",\"balance\",\"active\",\"label\"],\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":\"preinstallation-business-schema/v1\",\"versionColumn\":\"__mtw_source_version\",\"versionType\":\"int64\"}",
        "8976072ae0e117f7a2d906e088ad47f1b4483e08e126e77632ac9177b82da6dc",
      ),
      (
        0, "INSERT INTO \"ledger\".\"accounts\"(\"account_no\", \"balance\", \"active\", \"label\") VALUES (%s, %s, %s, %s)",
        "{\"container\":\"tuple\",\"items\":[{\"decimal\":\"8\",\"pythonType\":\"int\"},{\"decimal\":\"17\",\"pythonType\":\"int\"},{\"pythonType\":\"bool\",\"value\":true},{\"pythonType\":\"str\",\"value\":\"原始🙂文本\"}]}",
        "{\"businessStarColumns\":[\"account_no\",\"balance\",\"active\",\"label\"],\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":\"preinstallation-business-schema/v1\",\"versionColumn\":\"__mtw_source_version\",\"versionType\":\"int64\"}",
        "52f4b5545a1352577722402b40ef01d1debf9acf4b81d5d78b4e08159acf70e5",
      ),
      (
        1, "SELECT x.* FROM \"App-X\".\"Customer.Space\" x WHERE x.\"User ID\"=%s",
        "{\"container\":\"tuple\",\"items\":[{\"pythonType\":\"str\",\"value\":\"键🙂\"}]}",
        "{\"businessStarColumns\":[\"User ID\",\"quota\",\"live\",\"zone\"],\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":\"preinstallation-business-schema/v1\",\"versionColumn\":\"__mtw_source_version\",\"versionType\":\"int64\"}",
        "4acea774e0c44f24b17e82cc00e457399f68cf1d953e67f89b5b7d728012003c",
      ),
      (
        2, "UPDATE \"业务\".\"成员\" SET \"电子邮件\"=%s WHERE \"用户编号\"=%s RETURNING *",
        "{\"container\":\"tuple\",\"items\":[{\"pythonType\":\"str\",\"value\":\"new@example.invalid\"},{\"pythonType\":\"uuid.UUID\",\"value\":\"a8098c1a-f86e-11da-bd1a-00112444be1e\"}]}",
        "{\"businessStarColumns\":[\"用户编号\",\"电子邮件\",\"启用\"],\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":\"preinstallation-business-schema/v1\",\"versionColumn\":\"__mtw_source_version\",\"versionType\":\"int64\"}",
        "f539f3454eb70c42da24ca240471d9e8b143946ef499f371b19d9b0177bb8bf3",
      ),
      (
        0, "UPDATE ledger.accounts SET label=%(Name)s,balance=%(same)s WHERE account_no=%(same)s",
        "{\"container\":\"dict\",\"items\":[{\"name\":\"same\",\"value\":{\"decimal\":\"12\",\"pythonType\":\"int\"}},{\"name\":\"Name\",\"value\":{\"pythonType\":\"str\",\"value\":\"100% raw %(same)s\"}}]}",
        "{\"businessStarColumns\":[\"account_no\",\"balance\",\"active\",\"label\"],\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":\"preinstallation-business-schema/v1\",\"versionColumn\":\"__mtw_source_version\",\"versionType\":\"int64\"}",
        "1738899a33c657323d7288679263d5c349146fd9fee88bb0e70b1ce0097241cd",
      ),
      (
        0, "UPDATE ledger.accounts SET label=%s,balance=%s WHERE account_no=9223372036854775807",
        "{\"container\":\"list\",\"items\":[{\"pythonType\":\"str\",\"value\":\"\\\"; DROP TABLE never; -- %s\"},{\"decimal\":\"-9223372036854775808\",\"pythonType\":\"int\"}]}",
        "{\"businessStarColumns\":[\"account_no\",\"balance\",\"active\",\"label\"],\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":\"preinstallation-business-schema/v1\",\"versionColumn\":\"__mtw_source_version\",\"versionType\":\"int64\"}",
        "18f9b8452586b723aede56c331f4e74207619092cd46359233ff221e1668ebea",
      ),
      (
        2, "SELECT * FROM \"业务\".\"成员\" WHERE \"用户编号\"=%s", "{\"container\":\"list\",\"items\":[{\"pythonType\":\"uuid.UUID\",\"value\":\"a8098c1a-f86e-11da-bd1a-00112444be1e\"}]}",
        "{\"businessStarColumns\":[\"用户编号\",\"电子邮件\",\"启用\"],\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":\"preinstallation-business-schema/v1\",\"versionColumn\":\"__mtw_source_version\",\"versionType\":\"int64\"}",
        "3417e81657be1efbbb186c5de501fb40138a88ca7f5de244ec3c7a2924ddd1b3",
      ),
      (
        2, "SELECT * FROM \"业务\".\"成员\" WHERE \"用户编号\"=%s", "{\"container\":\"list\",\"items\":[{\"pythonType\":\"str\",\"value\":\"A8098C1A-F86E-11DA-BD1A-00112444BE1E\"}]}",
        "{\"businessStarColumns\":[\"用户编号\",\"电子邮件\",\"启用\"],\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":\"preinstallation-business-schema/v1\",\"versionColumn\":\"__mtw_source_version\",\"versionType\":\"int64\"}",
        "09a626cf6cb7981d117ad2c25c6ef4901a479d3ff4fe1062ee46b41da6a66003",
      ),
      (
        2, "SELECT * FROM \"业务\".\"成员\" WHERE \"用户编号\"=%s", "{\"container\":\"list\",\"items\":[{\"pythonType\":\"str\",\"value\":\"A8098C1AF86E11DABD1A00112444BE1E\"}]}",
        "{\"businessStarColumns\":[\"用户编号\",\"电子邮件\",\"启用\"],\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":\"preinstallation-business-schema/v1\",\"versionColumn\":\"__mtw_source_version\",\"versionType\":\"int64\"}",
        "dfbac6a44937fab0204f8910fffbf93a09e8c0d6ca35b9d7b24697c3cb78e7f2",
      ),
      (
        3, "UPDATE s.__mtw_v2_old SET __mtw_v2_new=%s WHERE k=%s RETURNING k AS __mtw_v2_old_version",
        "{\"container\":\"tuple\",\"items\":[{\"decimal\":\"1\",\"pythonType\":\"int\"},{\"decimal\":\"2\",\"pythonType\":\"int\"}]}",
        "{\"businessStarColumns\":[\"k\",\"__mtw_v2_new\",\"__mtw_v2_old_0\"],\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":\"preinstallation-business-schema/v1\",\"versionColumn\":\"__mtw_source_version\",\"versionType\":\"int64\"}",
        "bb5dc9b7fcd647e05e19ebd7a722832d323bafd00732667d2b11d35ec8e8fec5",
      ),
      (
        4, "SELECT * FROM \"s%\".\"t%s\" WHERE k=7", "{\"container\":\"none\",\"items\":[]}",
        "{\"businessStarColumns\":[\"k\",\"v%\\\"\"],\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":\"preinstallation-business-schema/v1\",\"versionColumn\":\"version%\\\"\",\"versionType\":\"int64\"}",
        "7ed1b9dfd724dadc9d3f72adca00a20f4119c626ddc37920f94e266296f9aea3",
      ),
      (
        5, "SELECT /* * */ \"k*\",v FROM s.t WHERE \"k*\"='*'", "{\"container\":\"none\",\"items\":[]}",
        "{\"businessStarColumns\":null,\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":null,\"versionColumn\":\"__mtw_source_version\",\"versionType\":\"int64\"}",
        "dcc74ad456b0f4e73fa96b0d268aa9eb0e074b2054a6436708ac65ef8f85e34d",
      ),
      (
        0, "SELECT label AS title,active AS enabled,account_no AS pk,balance AS amount FROM ledger.accounts WHERE account_no=7",
        "{\"container\":\"none\",\"items\":[]}", "{\"businessStarColumns\":null,\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":null,\"versionColumn\":\"__mtw_source_version\",\"versionType\":\"int64\"}",
        "3563fec36772fc3e6d47d644441299fd8e8b62f4ff2ef06e8670022f052ab1c2",
      ),
      (
        0, "SELECT label AS title,active AS enabled,account_no AS pk,balance AS amount FROM ledger.accounts WHERE account_no=7",
        "{\"container\":\"tuple\",\"items\":[]}", "{\"businessStarColumns\":null,\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":null,\"versionColumn\":\"__mtw_source_version\",\"versionType\":\"int64\"}",
        "5333b636044d9cf9f4552ea8099ce05112362caea3545a7215f6580c3fbc1054",
      ),
      (
        0, "SELECT label AS title,active AS enabled,account_no AS pk,balance AS amount FROM ledger.accounts WHERE account_no=7",
        "{\"container\":\"list\",\"items\":[]}", "{\"businessStarColumns\":null,\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":null,\"versionColumn\":\"__mtw_source_version\",\"versionType\":\"int64\"}",
        "dcac34e9f4733e9f0260d35cd12b8ab3b551575c6ad8321559e483b1f72f7e57",
      ),
      (
        0, "SELECT label AS title,active AS enabled,account_no AS pk,balance AS amount FROM ledger.accounts WHERE account_no=7",
        "{\"container\":\"dict\",\"items\":[]}", "{\"businessStarColumns\":null,\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":null,\"versionColumn\":\"__mtw_source_version\",\"versionType\":\"int64\"}",
        "859e7a97290d378f7f115e511d8498a7ef6ff0d6534cdb2d5ef96a7a30d90f60",
      ),
      (
        0, "DELETE FROM ledger.accounts WHERE account_no=%s", "{\"container\":\"tuple\",\"items\":[{\"decimal\":\"7\",\"pythonType\":\"int\"}]}",
        "{\"businessStarColumns\":null,\"maxDescriptorBytes\":16777216,\"maxProjectedSqlBytes\":131072,\"starContract\":null,\"versionColumn\":\"version_identity\",\"versionType\":\"int64\"}",
        "26c65c98e7901548a123f45bbde75b1ad864020b571d14b70f031a56f2077177",
      ),
    ][index]
  let config = parse_sql_config_v2(configs[config_index]).unwrap()
  (
    config,
    source,
    sql_json_v1(parameters, 1048576),
    point_projection_options_wire_v2(config, options),
    digest,
  )
}

///|
fn point52_expected(index : Int32) -> Json raise {
  let (config, source, parameters, options, _) = point52_case(index)
  let work : PointProjectionWorkV2 = {
    budget: point_projection_verification_options_v2(),
    checks: 0,
    atoms: [],
    named: Map([]),
    container: "",
    mapping: [],
  }
  point_projection_build_v2(work, config, source, parameters, options)
}

///|
fn point52_check(
  index : Int32,
  candidate : Json,
  budget~ : PointProjectionVerificationOptionsV2 = point_projection_verification_options_v2(),
) -> Json raise {
  let (config, source, parameters, options, _) = point52_case(index)
  point_projection_check_v2_json(
    verify_point_projection_v2(
      config,
      source,
      parameters,
      options,
      candidate,
      budget~,
    ),
  )
}

///|
fn point52_no_facts(report : Json) -> Unit raise {
  for
    name in [
      "databaseExecuted", "databaseSyntaxValidated", "sourceAuthenticated", "captureFactsProduced",
      "sourceFactsProduced", "completeWindow", "modelCoverageAccepted", "moonbitProjectionVerified",
      "commitVerified",
    ] {
    assert_eq(v4_test_at(report, [name]), Json(false))
  }
}

///|
test "projection52 twenty independent frozen Python descriptor hashes and three layouts" {
  for index = 0; index < 20; index = index + 1 {
    let (_, _, parameters, _, digest) = point52_case(index)
    let expected = point52_expected(index)
    assert_eq(v3_dislock_sha256(sql_canonical_v1(expected)), digest)
    let report = point52_check(index, expected)
    assert_eq(v4_test_at(report, ["status"]), Json("matched"))
    assert_eq(v4_test_at(report, ["originalTypedParameters"]), parameters)
    point52_no_facts(report)
  }
}

///|
test "projection52 UUID normalized binding remains distinct from original object and spelling" {
  for index in [9, 10, 11] {
    let expected = point52_expected(index)
    let bindings = orm_array(v4_test_at(expected, ["typedInputBindings"]))
    assert_eq(v4_test_at(bindings[0], ["value", "pythonType"]), Json("str"))
    assert_eq(
      v4_test_at(bindings[0], ["value", "value"]),
      Json("a8098c1a-f86e-11da-bd1a-00112444be1e"),
    )
    let mapping = orm_array(v4_test_at(expected, ["parameterMap"]))
    assert_eq(
      v4_test_at(mapping[0], ["value", "pythonType"]),
      Json(if index == 9 { "uuid.UUID" } else { "str" }),
    )
    if index == 10 {
      assert_eq(
        v4_test_at(mapping[0], ["value", "value"]),
        Json("A8098C1A-F86E-11DA-BD1A-00112444BE1E"),
      )
    }
  }
}

///|
test "projection52 dict order and original occurrence parameter map remain separate" {
  let expected = point52_expected(7)
  let items = orm_array(v4_test_at(expected, ["originalParameters", "items"]))
  assert_eq(v4_test_at(items[0], ["name"]), Json("same"))
  assert_eq(v4_test_at(items[1], ["name"]), Json("Name"))
  let mapping = orm_array(v4_test_at(expected, ["parameterMap"]))
  assert_eq(v4_test_at(mapping[0], ["original", "name"]), Json("Name"))
  assert_eq(v4_test_at(mapping[1], ["original", "name"]), Json("same"))
  assert_eq(v4_test_at(mapping[2], ["original", "name"]), Json("same"))
}

///|
test "projection52 none tuple list dict are distinct even with identical semantic empty parameters" {
  let none = point52_expected(15)
  for index in [16, 17, 18] {
    let report = point52_check(index, none)
    assert_eq(v4_test_at(report, ["status"]), Json("mismatch"))
    point52_no_facts(report)
  }
}

///|
test "projection52 deterministic quote escaping aliases and literal values do not interpolate" {
  let percent = point52_expected(13)
  let sql = sql_string_v1(v4_test_at(percent, ["projectedSql"]))
  assert_true(sql.contains("FROM \"s%%\".\"t%%s\""))
  let literal = point52_expected(8)
  assert_true(
    !sql_string_v1(v4_test_at(literal, ["projectedSql"])).contains("DROP TABLE"),
  )
  let aliases = object_fields(
    v4_test_at(point52_expected(12), ["returningAliases"]),
    "aliases",
  )
  assert_true(aliases.at("old") != Json("__mtw_v2_old"))
  assert_true(aliases.at("new") != Json("__mtw_v2_new"))
}

///|
test "projection52 write OLD NEW hidden images never become reads or deletion versions" {
  for index in [1, 2, 3, 4] {
    let expected = point52_expected(index)
    for hidden in orm_array(v4_test_at(expected, ["hiddenResults"])) {
      assert_eq(
        v4_test_at(hidden, ["role"]),
        Json("write-effect-observation-only"),
      )
      assert_eq(v4_test_at(hidden, ["version", "type"]), Json("int64"))
    }
    assert_eq(v4_test_at(expected, ["producesDeletionVersion"]), Json(false))
    assert_eq(v4_test_at(expected, ["writeImagesAreSelectFacts"]), Json(false))
    assert_eq(v4_test_at(expected, ["returningIsPredicateRead"]), Json(false))
  }
  assert_eq(
    v4_test_at(point52_expected(4), ["businessResult", "mode"]),
    Json("no-result"),
  )
}

///|
test "projection52 star requires explicit independent policy and four unproved obligations" {
  let (config, source, parameters, _, _) = point52_case(5)
  let default_options = point_projection_options_v2(config).unwrap()
  let expected = point52_expected(5)
  let report = point_projection_check_v2_json(
    verify_point_projection_v2(
      config, source, parameters, default_options, expected,
    ),
  )
  assert_eq(v4_test_at(report, ["status"]), Json("unknown"))
  assert_eq(orm_array(v4_test_at(expected, ["requiredProofs"])).length(), 11)
  assert_eq(
    v4_test_at(expected, ["businessStarView", "equivalentToCurrentNativeStar"]),
    Json(false),
  )
  assert_eq(
    v4_test_at(point52_expected(14), ["businessStarView"]),
    Json::null(),
  )
  point52_no_facts(report)
}

///|
test "projection52 own grammar SQL and descriptor budgets cannot be embedded authorized" {
  let expected = point52_expected(2)
  for
    budget in [
      point_projection_verification_options_v2(max_checks=0),
      point_projection_verification_options_v2(
        grammar_options=sql_verification_options_v2(max_checks=0),
      ),
    ] {
    let report = point52_check(2, expected, budget~)
    assert_eq(v4_test_at(report, ["status"]), Json("unknown"))
    point52_no_facts(report)
  }
  let (config, source, parameters, _, _) = point52_case(2)
  for
    options in [
      point_projection_options_v2(config, max_projected_sql_bytes=1).unwrap(),
      point_projection_options_v2(config, max_descriptor_bytes=1).unwrap(),
    ] {
    let report = point_projection_check_v2_json(
      verify_point_projection_v2(config, source, parameters, options, expected),
    )
    assert_eq(v4_test_at(report, ["status"]), Json("unknown"))
    point52_no_facts(report)
  }
}

///|
test "projection52 independent config conflict is invalid and version type remains int64" {
  let (config, source, parameters, options, _) = point52_case(2)
  let other = parse_sql_config_v2(sql52_config_text(2)).unwrap()
  let report = point_projection_check_v2_json(
    verify_point_projection_v2(
      other,
      source,
      parameters,
      options,
      point52_expected(2),
    ),
  )
  assert_eq(v4_test_at(report, ["status"]), Json("invalid"))
  for kind in ["uuid", "text", "bigint"] {
    assert_true(
      point_projection_options_v2(config, version_type=kind) is Err(_),
    )
  }
  assert_true(
    point_projection_options_v2(config, version_column="balance") is Err(_),
  )
  point52_no_facts(report)
}

///|
test "projection52 candidate authorization SQL aliases metadata and options tampering mismatch" {
  for
    name in [
      "databaseExecuted", "sourceAuthenticated", "captureFactsProduced", "sourceFactsProduced",
      "completeWindow", "modelCoverageAccepted", "moonbitProjectionVerified",
    ] {
    let fields = object_fields(point52_expected(2), "candidate")
    fields[name] = Json(true)
    let report = point52_check(2, Json::object(fields))
    assert_eq(v4_test_at(report, ["status"]), Json("mismatch"))
    point52_no_facts(report)
  }
  for
    name in [
      "projectedSql", "returningAliases", "hiddenResults", "parameterMap", "businessResult",
      "independentOptions",
    ] {
    let fields = object_fields(point52_expected(2), "candidate")
    fields[name] = Json("tampered")
    assert_eq(
      v4_test_at(point52_check(2, Json::object(fields)), ["status"]),
      Json("mismatch"),
    )
  }
}

///|
test "projection52 malformed typed observations cannot be recast as raw valid parameters" {
  let (config, source, _, options, _) = point52_case(9)
  let expected = point52_expected(9)
  for
    parameters in [
      ({ "container": "iterator", "items": [] } : Json),
      {
        "container": "list",
        "items": [
          {
            "pythonType": "uuid.UUID",
            "value": "A8098C1A-F86E-11DA-BD1A-00112444BE1E",
          },
        ],
      },
      {
        "container": "none",
        "items": [{ "pythonType": "int", "decimal": "7" }],
      },
    ] {
    let report = point_projection_check_v2_json(
      verify_point_projection_v2(config, source, parameters, options, expected),
    )
    assert_eq(v4_test_at(report, ["status"]), Json("invalid"))
    point52_no_facts(report)
  }
}

///|
test "projection52 JSON option limits and duplicate fields remain independent" {
  let (config, source, parameters, _, _) = point52_case(0)
  let options = point_projection_options_wire_v2(
    config, "{\"maxDescriptorBytes\":67108864}",
  )
  assert_eq(options.max_descriptor_bytes, 67108864)
  let report = sql_json_v1(
    verify_point_projection_v2_json(
      config.record.stringify(),
      source,
      parameters.stringify(),
      "{}",
      "{\"format\":\"x\",\"format\":\"x\"}",
      "{}",
    ),
    8388608,
  )
  assert_eq(v4_test_at(report, ["status"]), Json("invalid"))
  point52_no_facts(report)
}

///|
test "projection52 returned verification snapshots do not retain mutable caller atoms" {
  let (config, source, parameters, options, _) = point52_case(9)
  let result = verify_point_projection_v2(
    config,
    source,
    parameters,
    options,
    point52_expected(9),
  )
  let atom = object_fields(orm_array(orm_get(parameters, "items"))[0], "atom")
  atom["pythonType"] = Json("str")
  let report = point_projection_check_v2_json(result)
  let mapping = orm_array(
    v4_test_at(report, ["expectedDescriptor", "parameterMap"]),
  )
  assert_eq(v4_test_at(mapping[0], ["value", "pythonType"]), Json("uuid.UUID"))
  assert_eq(v4_test_at(report, ["status"]), Json("matched"))
  point52_no_facts(report)
}
