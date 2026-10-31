///|
fn source44_fixture() -> Json raise {
  sql_json_v1(
    "{\"config\":{\"format\":\"moontxnwitness-configured-sql/v1\",\"tables\":[{\"schema\":\"ledger\",\"table\":\"accounts\",\"primaryKey\":\"account_no\",\"columns\":[{\"name\":\"account_no\",\"type\":\"int64\",\"comparison\":null},{\"name\":\"balance\",\"type\":\"int64\",\"comparison\":null},{\"name\":\"active\",\"type\":\"bool\",\"comparison\":null},{\"name\":\"version\",\"type\":\"text\",\"comparison\":\"postgres-c-utf8-v1\"}],\"model\":\"relation-set-v1\"},{\"schema\":\"Feature-X\",\"table\":\"Flag.Store\",\"primaryKey\":\"Feature Key\",\"columns\":[{\"name\":\"Feature Key\",\"type\":\"text\",\"comparison\":\"postgres-c-utf8-v1\"},{\"name\":\"enabled\",\"type\":\"bool\",\"comparison\":null},{\"name\":\"source id\",\"type\":\"text\",\"comparison\":\"postgres-c-utf8-v1\"}],\"model\":\"relation-set-v1\"},{\"schema\":\"业务\",\"table\":\"Object Space\",\"primaryKey\":\"Key\",\"columns\":[{\"name\":\"Key\",\"type\":\"int64\",\"comparison\":null},{\"name\":\"note\",\"type\":\"text\",\"comparison\":\"postgres-c-utf8-v1\"},{\"name\":\"score\",\"type\":\"int64\",\"comparison\":null},{\"name\":\"flag\",\"type\":\"bool\",\"comparison\":null},{\"name\":\"region\",\"type\":\"text\",\"comparison\":\"postgres-c-utf8-v1\"},{\"name\":\"revision\",\"type\":\"text\",\"comparison\":\"postgres-c-utf8-v1\"}],\"model\":\"relation-set-v1\"}],\"defaultSchema\":\"ledger\",\"limits\":{\"max_sql_bytes\":65536,\"max_tokens\":8192,\"max_ast_nodes\":4096,\"max_nesting\":64,\"max_terms\":128,\"max_insert_rows\":128,\"max_text_bytes\":65536}},\"policy\":{\"namespace\":\"mtw_source_quote'\\\\safe\",\"writers\":[\"mtw_source_writer\"],\"maxInitialRows\":4096,\"maxLogBytes\":16777216},\"environment\":{\"owner\":\"mtw_source_owner\",\"writers\":[{\"name\":\"mtw_source_writer\",\"login\":true,\"createDb\":false,\"bypassRls\":false,\"superuser\":false,\"createRole\":false,\"replication\":false,\"ownerMembership\":false,\"privilegedMembership\":false,\"canSetReplicationRole\":false}],\"database\":\"postgres\",\"ownerRole\":{\"name\":\"mtw_source_owner\",\"login\":false,\"bypassRls\":false,\"superuser\":false,\"createRole\":false,\"replication\":false},\"backendPid\":123792,\"databaseOid\":5,\"eventTriggers\":[],\"clientEncoding\":\"UTF8\",\"serverEncoding\":\"UTF8\",\"replicationRole\":\"origin\",\"serverVersionNum\":\"180006\",\"standardConformingStrings\":\"on\"},\"catalog\":{\"oid\":16388,\"rls\":false,\"kind\":\"r\",\"owner\":\"mtw_source_owner\",\"rules\":false,\"table\":\"accounts\",\"schema\":\"ledger\",\"columns\":[{\"oid\":20,\"name\":\"account_no\",\"number\":1,\"default\":null,\"notNull\":true,\"identity\":\"\",\"typeKind\":\"b\",\"collation\":null,\"generated\":\"\",\"typeSchema\":\"pg_catalog\",\"elementType\":0,\"collationSchema\":null,\"collationProvider\":null,\"collationDeterministic\":null},{\"oid\":20,\"name\":\"balance\",\"number\":2,\"default\":null,\"notNull\":false,\"identity\":\"\",\"typeKind\":\"b\",\"collation\":null,\"generated\":\"\",\"typeSchema\":\"pg_catalog\",\"elementType\":0,\"collationSchema\":null,\"collationProvider\":null,\"collationDeterministic\":null},{\"oid\":16,\"name\":\"active\",\"number\":3,\"default\":null,\"notNull\":false,\"identity\":\"\",\"typeKind\":\"b\",\"collation\":null,\"generated\":\"\",\"typeSchema\":\"pg_catalog\",\"elementType\":0,\"collationSchema\":null,\"collationProvider\":null,\"collationDeterministic\":null},{\"oid\":25,\"name\":\"version\",\"number\":4,\"default\":null,\"notNull\":false,\"identity\":\"\",\"typeKind\":\"b\",\"collation\":\"C\",\"generated\":\"\",\"typeSchema\":\"pg_catalog\",\"elementType\":0,\"collationSchema\":\"pg_catalog\",\"collationProvider\":\"c\",\"collationDeterministic\":true},{\"oid\":20,\"name\":\"__mtw_source_version\",\"number\":5,\"default\":null,\"notNull\":true,\"identity\":\"\",\"typeKind\":\"b\",\"collation\":null,\"generated\":\"\",\"typeSchema\":\"pg_catalog\",\"elementType\":0,\"collationSchema\":null,\"collationProvider\":null,\"collationDeterministic\":null}],\"forceRls\":false,\"inherits\":false,\"triggers\":[{\"body\":\"DECLARE v bigint; b bigint; k jsonb; oldk jsonb; vals jsonb; BEGIN IF NOT (SESSION_USER::text COLLATE pg_catalog.\\\"C\\\" = ANY(ARRAY['mtw_source_writer']::text[])) THEN RAISE EXCEPTION 'writer login outside source scope' USING ERRCODE='42501'; END IF; IF NOT EXISTS(SELECT 1 FROM \\\"mtw_source_quote'\\\\safe\\\".scope WHERE relation_oid=TG_RELID AND primary_key=TG_ARGV[0]) THEN RAISE EXCEPTION 'relation outside source scope' USING ERRCODE='42501'; END IF; IF TG_OP='DELETE' THEN v:=pg_catalog.nextval('\\\"mtw_source_quote''\\\\safe\\\".versions'::pg_catalog.regclass); b:=OLD.\\\"__mtw_source_version\\\"; k:=pg_catalog.to_jsonb(OLD)->TG_ARGV[0]; oldk:=k; vals:=NULL; ELSE v:=NEW.\\\"__mtw_source_version\\\"; k:=pg_catalog.to_jsonb(NEW)->TG_ARGV[0]; vals:=pg_catalog.to_jsonb(NEW)-'__mtw_source_version'; IF TG_OP='UPDATE' THEN b:=OLD.\\\"__mtw_source_version\\\"; oldk:=pg_catalog.to_jsonb(OLD)->TG_ARGV[0]; ELSE b:=NULL; oldk:=NULL; END IF; END IF; INSERT INTO \\\"mtw_source_quote'\\\\safe\\\".effects(version,base_version,relation_oid,operation,writer_xid,writer_login,writer_pid,row_key,old_key,row_values) VALUES(v,b,TG_RELID,TG_OP,pg_catalog.pg_current_xact_id()::text,SESSION_USER,pg_catalog.pg_backend_pid(),k,oldk,vals); RETURN NULL; END;\",\"name\":\"__mtw_source_after\",\"type\":29,\"owner\":\"mtw_source_owner\",\"argsHex\":\"6163636f756e745f6e6f00\",\"enabled\":\"A\",\"argCount\":0,\"function\":\"after_write\",\"parallel\":\"u\",\"settings\":[\"search_path=pg_catalog, pg_temp\",\"standard_conforming_strings=on\"],\"volatile\":\"v\",\"noColumns\":true,\"returnType\":2279,\"noCondition\":true,\"functionSchema\":\"mtw_source_quote'\\\\safe\",\"securityDefiner\":true},{\"body\":\"BEGIN IF NOT (SESSION_USER::text COLLATE pg_catalog.\\\"C\\\" = ANY(ARRAY['mtw_source_writer']::text[])) THEN RAISE EXCEPTION 'writer login outside source scope' USING ERRCODE='42501'; END IF; IF NOT EXISTS(SELECT 1 FROM \\\"mtw_source_quote'\\\\safe\\\".scope WHERE relation_oid=TG_RELID AND primary_key=TG_ARGV[0]) THEN RAISE EXCEPTION 'relation outside source scope' USING ERRCODE='42501'; END IF; NEW.\\\"__mtw_source_version\\\" := pg_catalog.nextval('\\\"mtw_source_quote''\\\\safe\\\".versions'::pg_catalog.regclass); RETURN NEW; END;\",\"name\":\"__mtw_source_before\",\"type\":23,\"owner\":\"mtw_source_owner\",\"argsHex\":\"6163636f756e745f6e6f00\",\"enabled\":\"A\",\"argCount\":0,\"function\":\"before_write\",\"parallel\":\"u\",\"settings\":[\"search_path=pg_catalog, pg_temp\",\"standard_conforming_strings=on\"],\"volatile\":\"v\",\"noColumns\":true,\"returnType\":2279,\"noCondition\":true,\"functionSchema\":\"mtw_source_quote'\\\\safe\",\"securityDefiner\":true}],\"persistence\":\"p\",\"primaryKeys\":[{\"keys\":1,\"ready\":true,\"valid\":true,\"columns\":[\"account_no\"],\"immediate\":true}],\"uniqueIndexes\":[{\"keys\":1,\"ready\":true,\"valid\":true,\"columns\":[\"account_no\"],\"immediate\":true,\"noPredicate\":true,\"noExpression\":true},{\"keys\":1,\"ready\":true,\"valid\":true,\"columns\":[\"__mtw_source_version\"],\"immediate\":true,\"noPredicate\":true,\"noExpression\":true}]},\"sourceCatalog\":{\"owner\":\"mtw_source_owner\",\"objects\":[{\"kind\":\"r\",\"name\":\"effects\",\"owner\":\"mtw_source_owner\"},{\"kind\":\"i\",\"name\":\"effects_pkey\",\"owner\":\"mtw_source_owner\"},{\"kind\":\"r\",\"name\":\"scope\",\"owner\":\"mtw_source_owner\"},{\"kind\":\"i\",\"name\":\"scope_pkey\",\"owner\":\"mtw_source_owner\"},{\"kind\":\"S\",\"name\":\"versions\",\"owner\":\"mtw_source_owner\"}],\"sequence\":{\"type\":20,\"cache\":1,\"cycle\":false,\"start\":1,\"maximum\":9223372036854775807,\"minimum\":1,\"increment\":1},\"namespace\":\"mtw_source_quote'\\\\safe\",\"ownerMembers\":[],\"functionCount\":2,\"nonOwnerGrants\":[]}}",
    65536,
  )
}

///|
fn source44_run_environment(f : Json) -> Unit raise {
  let root = source_object_v4(f)
  let _ = source_environment_v4(
    root.at("environment"),
    source_policy_v4(root.at("policy")),
    { limit: 1000000, checks: 0, },
  )
}

///|
fn source44_run_catalog(f : Json) -> Unit raise {
  let root = source_object_v4(f)
  let config = match parse_sql_config_v1(root.at("config").stringify()) {
    Ok(c) => c
    Err(reason) => fail(reason)
  }
  let _ = source_table_catalog_v4(
    config.tables[0],
    source_policy_v4(root.at("policy")),
    "mtw_source_owner",
    root.at("catalog"),
    true,
    { limit: 1000000, checks: 0, },
  )
}

///|
fn source44_run_private(f : Json) -> Unit raise {
  let root = source_object_v4(f)
  source_private_catalog_v4(
    root.at("sourceCatalog"),
    source_policy_v4(root.at("policy")),
    "mtw_source_owner",
    { limit: 1000000, checks: 0, },
  )
}

///|
test "source44 01 actual environment cell" {
  source44_run_environment(source44_fixture())
}

///|
test "source44 02 actual installed catalog cell" {
  source44_run_catalog(source44_fixture())
}

///|
test "source44 03 actual private catalog cell" {
  source44_run_private(source44_fixture())
}

///|
test "source44 04 rejects owner login" {
  let f = source44_fixture()
  source_object_v4(
    source_object_v4(source_object_v4(f).at("environment")).at("ownerRole"),
  )["login"] = Json(true)
  let rejected = try {
    source44_run_environment(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 05 rejects privileged writer" {
  let f = source44_fixture()
  source_object_v4(
    orm_array(
      source_object_v4(source_object_v4(f).at("environment")).at("writers"),
    )[0],
  )["superuser"] = Json(true)
  let rejected = try {
    source44_run_environment(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 06 rejects missing writer" {
  let f = source44_fixture()
  source_object_v4(source_object_v4(f).at("environment"))["writers"] = Json::array([],
  )
  let rejected = try {
    source44_run_environment(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 07 rejects event trigger" {
  let f = source44_fixture()
  source_object_v4(source_object_v4(f).at("environment"))["eventTriggers"] = [
    "danger",
  ]
  let rejected = try {
    source44_run_environment(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 08 rejects non UTF8" {
  let f = source44_fixture()
  source_object_v4(source_object_v4(f).at("environment"))["serverEncoding"] = Json(
    "LATIN1",
  )
  let rejected = try {
    source44_run_environment(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 09 rejects wrong owner" {
  let f = source44_fixture()
  source_object_v4(source_object_v4(f).at("catalog"))["owner"] = Json("other")
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 10 rejects RLS" {
  let f = source44_fixture()
  source_object_v4(source_object_v4(f).at("catalog"))["rls"] = Json(true)
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 11 rejects OID text" {
  let f = source44_fixture()
  source_object_v4(source_object_v4(f).at("catalog"))["oid"] = Json("123")
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 12 rejects column identity" {
  let f = source44_fixture()
  source_object_v4(
    orm_array(source_object_v4(source_object_v4(f).at("catalog")).at("columns"))[0],
  )["name"] = Json("other")
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 13 rejects column ordinal" {
  let f = source44_fixture()
  source_object_v4(
    orm_array(source_object_v4(source_object_v4(f).at("catalog")).at("columns"))[1],
  )["number"] = Json(1)
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 14 rejects integer domain" {
  let f = source44_fixture()
  source_object_v4(
    orm_array(source_object_v4(source_object_v4(f).at("catalog")).at("columns"))[1],
  )["typeKind"] = Json("d")
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 15 rejects non C collation" {
  let f = source44_fixture()
  source_object_v4(
    orm_array(source_object_v4(source_object_v4(f).at("catalog")).at("columns"))[3],
  )["collation"] = Json("en_US")
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 16 rejects metadata oid" {
  let f = source44_fixture()
  source_object_v4(
    orm_array(source_object_v4(source_object_v4(f).at("catalog")).at("columns"))[4],
  )["oid"] = Json(23)
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 17 rejects metadata nullable" {
  let f = source44_fixture()
  source_object_v4(
    orm_array(source_object_v4(source_object_v4(f).at("catalog")).at("columns"))[4],
  )["notNull"] = Json(false)
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 18 rejects metadata default" {
  let f = source44_fixture()
  source_object_v4(
    orm_array(source_object_v4(source_object_v4(f).at("catalog")).at("columns"))[4],
  )["default"] = Json("1")
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 19 rejects composite key" {
  let f = source44_fixture()
  source_object_v4(
    orm_array(
      source_object_v4(source_object_v4(f).at("catalog")).at("primaryKeys"),
    )[0],
  )["keys"] = Json(2)
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 20 rejects unready key" {
  let f = source44_fixture()
  source_object_v4(
    orm_array(
      source_object_v4(source_object_v4(f).at("catalog")).at("primaryKeys"),
    )[0],
  )["ready"] = Json(false)
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 21 rejects no unique version" {
  let f = source44_fixture()
  source_object_v4(source_object_v4(f).at("catalog"))["uniqueIndexes"] = Json::array([],
  )
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 22 rejects disabled trigger" {
  let f = source44_fixture()
  source_object_v4(
    orm_array(
      source_object_v4(source_object_v4(f).at("catalog")).at("triggers"),
    )[0],
  )["enabled"] = Json("D")
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 23 rejects filtered trigger" {
  let f = source44_fixture()
  source_object_v4(
    orm_array(
      source_object_v4(source_object_v4(f).at("catalog")).at("triggers"),
    )[0],
  )["noCondition"] = Json(false)
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 24 rejects wrong trigger args" {
  let f = source44_fixture()
  source_object_v4(
    orm_array(
      source_object_v4(source_object_v4(f).at("catalog")).at("triggers"),
    )[0],
  )["argsHex"] = Json("00")
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 25 rejects wrong function body" {
  let f = source44_fixture()
  source_object_v4(
    orm_array(
      source_object_v4(source_object_v4(f).at("catalog")).at("triggers"),
    )[0],
  )["body"] = Json("RETURN NULL;")
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 26 rejects wrong function owner" {
  let f = source44_fixture()
  source_object_v4(
    orm_array(
      source_object_v4(source_object_v4(f).at("catalog")).at("triggers"),
    )[0],
  )["owner"] = Json("other")
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 27 rejects unsafe function settings" {
  let f = source44_fixture()
  source_object_v4(
    orm_array(
      source_object_v4(source_object_v4(f).at("catalog")).at("triggers"),
    )[0],
  )["settings"] = ["search_path=public", "standard_conforming_strings=on"]
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 28 rejects source grants" {
  let f = source44_fixture()
  source_object_v4(source_object_v4(f).at("sourceCatalog"))["nonOwnerGrants"] = [
    "grant",
  ]
  let rejected = try {
    source44_run_private(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 29 rejects source owner member" {
  let f = source44_fixture()
  source_object_v4(source_object_v4(f).at("sourceCatalog"))["ownerMembers"] = [
    "outsider",
  ]
  let rejected = try {
    source44_run_private(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 30 rejects sequence cycle" {
  let f = source44_fixture()
  source_object_v4(
    source_object_v4(source_object_v4(f).at("sourceCatalog")).at("sequence"),
  )["cycle"] = Json(true)
  let rejected = try {
    source44_run_private(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 31 rejects sequence maximum" {
  let f = source44_fixture()
  source_object_v4(
    source_object_v4(source_object_v4(f).at("sourceCatalog")).at("sequence"),
  )["maximum"] = Json(1)
  let rejected = try {
    source44_run_private(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 32 rejects extra source object" {
  let f = source44_fixture()
  source_object_v4(source_object_v4(f).at("sourceCatalog"))["functionCount"] = Json(
    3,
  )
  let rejected = try {
    source44_run_private(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 33 rejects extra policy option" {
  let f = source44_fixture()
  source_object_v4(source_object_v4(f).at("policy"))["approved"] = Json(true)
  let rejected = try {
    source44_run_catalog(f)
    false
  } catch {
    _ => true
  }
  assert_eq(rejected, true)
}

///|
test "source44 34 literal and UTF8 arguments" {
  assert_eq(source_literal_v4("a\\b'c"), "'a\\b''c'")
  assert_eq(source_args_hex_v4("Key🙂"), "4b6579f09f998200")
}

///|
test "source44 35 opaque report is detached and zero budget unknown" {
  let f = source_object_v4(source44_fixture())
  let c = match parse_sql_config_v1(f.at("config").stringify()) {
    Ok(c) => c
    Err(reason) => fail(reason)
  }
  let result = verify_source_installation_v4(
    c,
    f.at("policy"),
    "",
    {},
    max_checks=0,
  )
  let report = source_object_v4(source_installation_check_v4_json(result))
  assert_eq(report.at("status"), Json("unknown"))
  report["sourceFactsProduced"] = Json(true)
  assert_eq(
    source_object_v4(source_installation_check_v4_json(result)).at(
      "sourceFactsProduced",
    ),
    Json(false),
  )
}

///|
test "source44 36 negative caller budget invalid" {
  let f = source_object_v4(source44_fixture())
  let c = match parse_sql_config_v1(f.at("config").stringify()) {
    Ok(c) => c
    Err(reason) => fail(reason)
  }
  let result = verify_source_installation_v4(
    c,
    f.at("policy"),
    "",
    {},
    max_checks=-1,
  )
  assert_eq(
    source_object_v4(source_installation_check_v4_json(result)).at("status"),
    Json("invalid"),
  )
}

///|
test "source44 37 actual CREATE TRIGGER acknowledgement" {
  let f = source_object_v4(source44_fixture())
  let config = match parse_sql_config_v1(f.at("config").stringify()) {
    Ok(value) => value
    Err(reason) => fail(reason)
  }
  let ddl = source_ddl_v4(config, source_policy_v4(f.at("policy")))
  let command : SourceCommandV4 = {
    query_id: "install-ddl",
    sql: ddl[11],
    parameters: Json::null(),
    native: {
      "status": 1,
      "tag": "CREATE TRIGGER",
      "fields": 0,
      "columns": [],
      "rows": [],
    },
    decoded: [],
    before: 2,
    after: 2,
    request_seq: 1,
    result_seq: 2,
  }
  source_ddl_ack_v4(command)
}
