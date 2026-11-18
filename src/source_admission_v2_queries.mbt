///|
fn admission_qi_v2(value : String) -> String raise {
  v3_dislock_quote(value).replace_all(old="%", new="%%")
}

///|
fn admission_target_v2(table : SQLTableV1) -> String raise {
  admission_qi_v2(table.schema) + "." + admission_qi_v2(table.name)
}

///|
fn admission_functions_v2(policy : SourcePolicyV4) -> (String, String) raise {
  let (before, after) = source_functions_v4(policy)
  let marker = "NEW.\"__mtw_source_version\" :="
  let guard_sql = "IF TG_OP='UPDATE' THEN IF (pg_catalog.to_jsonb(OLD)->TG_ARGV[0]) IS DISTINCT FROM " +
    "(pg_catalog.to_jsonb(NEW)->TG_ARGV[0]) THEN RAISE EXCEPTION 'V2 primary key is immutable' " +
    "USING ERRCODE='23514'; END IF; END IF; "
  (before.replace_all(old=marker, new=guard_sql + marker), after)
}

///|
fn admission_ddl_v2(
  config : SQLConfigV2,
  policy : SourcePolicyV4,
) -> Array[String] raise {
  // Reuse only the pure DDL constructor over private grammar structures. No V1
  // configuration parser, wire format or installation verifier is invoked.
  let (old_before, _) = source_functions_v4(policy)
  let (before, _) = admission_functions_v2(policy)
  source_ddl_v4(config.parser_config, policy).map(sql => {
    sql.replace_all(
      old=source_literal_v4(old_before),
      new=source_literal_v4(before),
    )
  })
}

///|
fn admission_snapshot_sql_v2(config : SQLConfigV2) -> String raise {
  let table = config.parser_config.tables[0]
  let version = admission_qi_v2("__mtw_source_version")
  let terms : Array[String] = []
  for column in table.columns {
    if column.kind == "text" {
      let limit = config.parser_config.limits.at("max_text_bytes")
      terms.push(
        "pg_catalog.octet_length(t." +
        admission_qi_v2(column.name) +
        ")>" +
        (if limit < 65536 { limit } else { 65536 }).to_string(),
      )
    }
  }
  let limits = if terms.is_empty() { "FALSE" } else { terms.join(" OR ") }
  "SELECT CASE WHEN (" +
  limits +
  ") OR pg_catalog.octet_length(pg_catalog.to_jsonb(t)::text)>65536 THEN pg_catalog.jsonb_build_object('kind','initial-row-budget') " +
  "ELSE pg_catalog.jsonb_build_object('kind','initial-row','row',pg_catalog.to_jsonb(t)) END::text FROM " +
  admission_target_v2(table) +
  " t WHERE t." +
  version +
  ">%s ORDER BY t." +
  version +
  " LIMIT 1"
}

///|
fn admission_initial_ledger_sql_v2(policy : SourcePolicyV4) -> String raise {
  "SELECT CASE WHEN pg_catalog.octet_length(p.payload)>65536 THEN '{\"kind\":\"initial-ledger-budget\"}' ELSE p.payload END FROM " +
  "(SELECT e.version,pg_catalog.jsonb_build_object('kind','initial-ledger','version',e.version,'baseVersion',e.base_version,'relationOid',e.relation_oid::bigint," +
  "'operation',e.operation,'writerXid',e.writer_xid,'writerLogin',e.writer_login,'writerPid',e.writer_pid,'rowKey',e.row_key,'oldKey',e.old_key,'rowValues',e.row_values)::text payload FROM " +
  admission_qi_v2(policy.source_schema) +
  ".effects e WHERE e.version>%s ORDER BY e.version LIMIT 1) p"
}

///|
fn admission_scope_sql_v2(policy : SourcePolicyV4) -> String raise {
  "SELECT pg_catalog.jsonb_build_object('relation_oid',s.relation_oid::bigint,'relation_schema',s.relation_schema,'relation_table',s.relation_table,'primary_key',s.primary_key,'config_sha256',s.config_sha256)::text FROM " +
  admission_qi_v2(policy.source_schema) +
  ".scope s ORDER BY relation_schema,relation_table"
}

///|
fn admission_row_v2(
  config : SQLConfigV2,
  raw : Json,
  work : SourceWorkV4,
) -> (String, Json) raise {
  let table = config.parser_config.tables[0]
  let row = object_fields(raw, "V2 installed row")
  let names = table.columns.map(c => c.name)
  names.push("__mtw_source_version")
  known_fields(row, names, "V2 installed row")
  if row.length() != names.length() {
    fail("mismatch:admission-row-columns")
  }
  let version = source_positive_v4(row.at("__mtw_source_version"))
  if source_version_after_v4(version, "9223372036854775807") {
    fail("mismatch:admission-version-range")
  }
  let mut key : Json = Json::null()
  for column in table.columns {
    work.charge()
    let typed = sql_typed_value_v2(
      row.at(column.name),
      column.kind,
      config.parser_config.limits.at("max_text_bytes"),
    )
    if column.kind == "uuid" &&
      source_object_v4(typed).at("value") != row.at(column.name) {
      fail("mismatch:admission-canonical-native-UUID")
    }
    if column.name == table.key {
      key = typed
    }
  }
  (version, key)
}
