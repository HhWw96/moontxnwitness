///|
fn source_oid_v4(value : Json) -> String raise {
  let text = source_positive_v4(value)
  if text.length() > 10 || (text.length() == 10 && text > "4294967295") {
    fail("mismatch:source-OID-range")
  }
  text
}

///|
fn source_environment_v4(
  value : Json,
  policy : SourcePolicyV4,
  work : SourceWorkV4,
) -> String raise {
  work.charge()
  let e = orm_exact(value, [
    "database", "databaseOid", "backendPid", "serverVersionNum", "serverEncoding",
    "clientEncoding", "standardConformingStrings", "replicationRole", "owner", "eventTriggers",
    "ownerRole", "writers",
  ])
  let _ = sql_identifier_v1(e.at("database"))
  let _ = source_oid_v4(e.at("databaseOid"))
  let _ = source_positive_v4(e.at("backendPid"))
  let version = sql_string_v1(e.at("serverVersionNum"))
  if !sql_digits_v1(version) ||
    version.length() != 6 ||
    version < "180000" ||
    version >= "190000" {
    fail("unsupported:source-PG18")
  }
  for
    (name, expected) in [
      ("serverEncoding", "UTF8"),
      ("clientEncoding", "UTF8"),
      ("standardConformingStrings", "on"),
      ("replicationRole", "origin"),
    ] {
    if e.at(name) != Json(expected) {
      fail("unsupported:source-environment")
    }
  }
  if e.at("eventTriggers") != Json::array([]) {
    fail("unsupported:source-DDL-event-trigger")
  }
  let owner = sql_identifier_v1(e.at("owner"))
  let role = orm_exact(e.at("ownerRole"), [
    "name", "superuser", "login", "createRole", "replication", "bypassRls",
  ])
  source_equal_v4(role.at("name"), Json(owner), "owner-role")
  for key in ["superuser", "login", "createRole", "replication", "bypassRls"] {
    if role.at(key) != Json(false) {
      fail("unsupported:source-owner-privilege")
    }
  }
  let writers = orm_array(e.at("writers"))
  let seen : Array[String] = []
  for raw in writers {
    work.charge()
    let writer = orm_exact(raw, [
      "name", "login", "superuser", "createRole", "createDb", "replication", "bypassRls",
      "ownerMembership", "privilegedMembership", "canSetReplicationRole",
    ])
    let name = sql_identifier_v1(writer.at("name"))
    if !policy.writers.contains(name) ||
      seen.contains(name) ||
      name == owner ||
      writer.at("login") != Json(true) {
      fail("mismatch:source-writer-identity")
    }
    seen.push(name)
    for
      field in [
        "superuser", "createRole", "createDb", "replication", "bypassRls", "ownerMembership",
        "privilegedMembership", "canSetReplicationRole",
      ] {
      if writer.at(field) != Json(false) {
        fail("unsupported:source-writer-privilege")
      }
    }
  }
  if seen.length() != policy.writers.length() {
    fail("mismatch:source-writer-inventory")
  }
  owner
}

///|
fn source_args_hex_v4(key : String) -> String {
  let out = StringBuilder()
  let hex = "0123456789abcdef"
  let bytes = @utf8.encode(key)
  for index in 0..<bytes.length() {
    let n = bytes[index].to_int()
    out.write_char(hex[n >> 4].to_int().unsafe_to_char())
    out.write_char(hex[n & 15].to_int().unsafe_to_char())
  }
  out.write_string("00")
  out.to_string()
}

///|
fn source_table_catalog_v4(
  table : SQLTableV1,
  policy : SourcePolicyV4,
  owner : String,
  raw : Json,
  installed : Bool,
  work : SourceWorkV4,
) -> String raise {
  work.charge()
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
  for index, raw_column in columns {
    work.charge()
    let column = orm_exact(raw_column, [
      "name", "number", "oid", "generated", "identity", "notNull", "typeKind", "typeSchema",
      "elementType", "collation", "collationSchema", "collationProvider", "collationDeterministic",
      "default",
    ])
    let metadata = index == table.columns.length()
    let name = if metadata {
      "__mtw_source_version"
    } else {
      table.columns[index].name
    }
    let kind = if metadata { "int64" } else { table.columns[index].kind }
    if column.at("name") != Json(name) || column.at("number") != Json(index + 1) {
      fail("mismatch:source-column-position")
    }
    let type_oid = source_oid_v4(column.at("oid"))
    let supported = match kind {
      "int64" => ["20", "21", "23"].contains(type_oid)
      "bool" => type_oid == "16"
      "text" => ["25", "1043"].contains(type_oid)
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
    if (metadata || name == table.key) && column.at("notNull") != Json(true) {
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
    let (before_body, after_body) = source_functions_v4(policy)
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

///|
fn source_private_catalog_v4(
  raw : Json,
  policy : SourcePolicyV4,
  owner : String,
  work : SourceWorkV4,
) -> Unit raise {
  work.charge()
  let c = orm_exact(raw, [
    "namespace", "owner", "objects", "nonOwnerGrants", "ownerMembers", "sequence",
    "functionCount",
  ])
  if c.at("namespace") != Json(policy.source_schema) ||
    c.at("owner") != Json(owner) {
    fail("mismatch:source-private-owner")
  }
  if c.at("nonOwnerGrants") != Json::array([]) ||
    c.at("ownerMembers") != Json::array([]) {
    fail("unsupported:source-private-access")
  }
  let objects = orm_array(c.at("objects"))
  if objects.length() != 5 {
    fail("mismatch:source-private-object-count")
  }
  let expected : Map[String, String] = Map([
    ("scope", "r"),
    ("effects", "r"),
    ("scope_pkey", "i"),
    ("effects_pkey", "i"),
    ("versions", "S"),
  ])
  let seen : Array[String] = []
  for object in objects {
    work.charge()
    let o = orm_exact(object, ["name", "kind", "owner"])
    let name = sql_string_v1(o.at("name"))
    if seen.contains(name) ||
      expected.get(name) != Some(sql_string_v1(o.at("kind"))) ||
      o.at("owner") != Json(owner) {
      fail("mismatch:source-private-object")
    }
    seen.push(name)
  }
  let sequence = orm_exact(c.at("sequence"), [
    "type", "start", "increment", "minimum", "maximum", "cache", "cycle",
  ])
  for
    (field, value) in [
      ("type", 20),
      ("start", 1),
      ("increment", 1),
      ("minimum", 1),
      ("cache", 1),
    ] {
    source_equal_v4(sequence.at(field), Json(value), "sequence")
  }
  if source_positive_v4(sequence.at("maximum")) != "9223372036854775807" ||
    sequence.at("cycle") != Json(false) ||
    c.at("functionCount") != Json(2) {
    fail("mismatch:source-sequence-or-functions")
  }
}
