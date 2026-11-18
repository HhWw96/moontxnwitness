///|
fn admission_catalog_v2(
  config : SQLConfigV2,
  policy : SourcePolicyV4,
  owner : String,
  raw : Json,
  installed : Bool,
  work : SourceWorkV4,
) -> String raise {
  work.charge()
  let table = config.parser_config.tables[0]
  let c = orm_exact(raw, [
    "schema", "table", "oid", "kind", "persistence", "owner", "rls", "forceRls",
    "inherits", "rules", "columns", "primaryKeys", "uniqueIndexes", "triggers",
  ])
  if c.at("schema") != Json(table.schema) ||
    c.at("table") != Json(table.name) ||
    c.at("owner") != Json(owner) {
    fail("mismatch:source-table-identity")
  }
  if c.at("kind") != Json("r") || c.at("persistence") != Json("p") {
    fail("unsupported:source-table-kind")
  }
  for field in ["rls", "forceRls", "inherits", "rules"] {
    if c.at(field) != Json(false) {
      fail("unsupported:source-table-semantics")
    }
  }
  let oid = source_oid_v4(c.at("oid"))
  let columns = orm_array(c.at("columns"))
  if columns.length() !=
    table.columns.length() + (if installed { 1 } else { 0 }) {
    fail("mismatch:source-column-inventory")
  }
  let seen_columns : Array[String] = []
  let mut previous_number = 0
  for raw_column in columns {
    work.charge()
    let column = orm_exact(raw_column, [
      "name", "number", "oid", "generated", "identity", "notNull", "typeKind", "typeSchema",
      "elementType", "collation", "collationSchema", "collationProvider", "collationDeterministic",
      "default",
    ])
    let name = sql_identifier_v2(column.at("name"))
    let metadata = name == "__mtw_source_version"
    let number = fetch_number_v1(column.at("number"), 32767)
    if number <= previous_number ||
      seen_columns.contains(name) ||
      (metadata && !installed) {
      fail("mismatch:admission-physical-column-identity")
    }
    previous_number = number
    seen_columns.push(name)
    let kind = if metadata {
      "int64"
    } else {
      match table.columns.iter().find_first(c => c.name == name) {
        Some(c) => c.kind
        None => fail("mismatch:admission-unconfigured-column")
      }
    }
    let type_oid = source_oid_v4(column.at("oid"))
    let supported = match kind {
      "int64" => ["20", "21", "23"].contains(type_oid)
      "bool" => type_oid == "16"
      "text" => ["25", "1043"].contains(type_oid)
      "uuid" => type_oid == "2950"
      _ => false
    }
    if !supported ||
      (metadata && type_oid != "20") ||
      column.at("typeKind") != Json("b") ||
      column.at("typeSchema") != Json("pg_catalog") ||
      column.at("elementType") != Json(0) ||
      column.at("generated") != Json("") ||
      column.at("identity") != Json("") {
      fail("unsupported:source-column-type")
    }
    if kind == "text" {
      if column.at("collation") != Json("C") ||
        column.at("collationSchema") != Json("pg_catalog") ||
        column.at("collationProvider") != Json("c") ||
        column.at("collationDeterministic") != Json(true) {
        fail("unsupported:source-text-collation")
      }
    } else if column.at("collation") != Json::null() ||
      column.at("collationSchema") != Json::null() ||
      column.at("collationProvider") != Json::null() ||
      column.at("collationDeterministic") != Json::null() {
      fail("mismatch:source-scalar-collation")
    }
    match column.at("notNull") {
      True | False => ()
      _ => fail("mismatch:source-not-null-flag")
    }
    if column.at("notNull") != Json(true) {
      fail("mismatch:source-required-non-null")
    }
    if metadata && column.at("default") != Json::null() {
      fail("mismatch:source-metadata-default")
    }
  }
  let primary = orm_array(c.at("primaryKeys"))
  if primary.length() != 1 {
    fail("mismatch:source-primary-key-count")
  }
  let pk = orm_exact(primary[0], [
    "valid", "ready", "immediate", "keys", "columns",
  ])
  if pk.at("columns") != Json([Json(table.key)]) || pk.at("keys") != Json(1) {
    fail("mismatch:source-single-primary-key")
  }
  for name in ["valid", "ready", "immediate"] {
    if pk.at(name) != Json(true) {
      fail("unsupported:source-primary-key-state")
    }
  }
  let triggers = orm_array(c.at("triggers"))
  if !installed {
    if !triggers.is_empty() {
      fail("unsupported:source-existing-trigger")
    }
  } else {
    let indexes = orm_array(c.at("uniqueIndexes"))
    let mut unique_version = false
    for raw_index in indexes {
      work.charge()
      let i = orm_exact(raw_index, [
        "valid", "ready", "immediate", "keys", "columns", "noPredicate", "noExpression",
      ])
      if i.at("columns") == Json([Json("__mtw_source_version")]) &&
        i.at("keys") == Json(1) &&
        ["valid", "ready", "immediate", "noPredicate", "noExpression"].all(name => {
          i.at(name) == Json(true)
        }) {
        unique_version = true
      }
    }
    if !unique_version {
      fail("mismatch:source-version-unique-index")
    }
    if triggers.length() != 2 {
      fail("mismatch:source-trigger-count")
    }
    let (before_body, after_body) = admission_functions_v2(policy)
    let seen : Array[String] = []
    for raw_trigger in triggers {
      work.charge()
      let t = orm_exact(raw_trigger, [
        "name", "type", "enabled", "argsHex", "noCondition", "noColumns", "functionSchema",
        "function", "body", "securityDefiner", "returnType", "volatile", "parallel",
        "argCount", "owner", "settings",
      ])
      let name = sql_string_v1(t.at("name"))
      let before = name == "__mtw_source_before"
      if (!before && name != "__mtw_source_after") || seen.contains(name) {
        fail("mismatch:source-trigger-identity")
      }
      seen.push(name)
      if t.at("type") != Json(if before { 23 } else { 29 }) ||
        t.at("enabled") != Json("A") ||
        t.at("argsHex") != Json(source_args_hex_v4(table.key)) ||
        t.at("noCondition") != Json(true) ||
        t.at("noColumns") != Json(true) {
        fail("mismatch:source-trigger-scope")
      }
      if t.at("functionSchema") != Json(policy.source_schema) ||
        t.at("function") !=
        Json(if before { "before_write" } else { "after_write" }) ||
        t.at("body") != Json(if before { before_body } else { after_body }) ||
        t.at("owner") != Json(owner) ||
        t.at("securityDefiner") != Json(true) ||
        t.at("returnType") != Json(2279) ||
        t.at("volatile") != Json("v") ||
        t.at("parallel") != Json("u") ||
        t.at("argCount") != Json(0) {
        fail("mismatch:source-trigger-function")
      }
      let settings = orm_array(t.at("settings"))
      if settings.length() != 2 ||
        !settings.contains(Json("search_path=pg_catalog, pg_temp")) ||
        !settings.contains(Json("standard_conforming_strings=on")) {
        fail("mismatch:source-trigger-settings")
      }
    }
  }
  oid
}
