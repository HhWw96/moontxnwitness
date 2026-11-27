///|
pub struct SQLConfigV2 {
  // Private grammar state only; no V1 config parser or wire is invoked.
  priv parser_config : SQLConfigV1
  priv record : Json
  priv digest : String
}

///|
pub struct SQLVerificationOptionsV2 {
  priv max_checks : Int32
  priv max_tokens : Int32
  priv max_sql_bytes : Int32
}

///|
pub fn sql_verification_options_v2(
  max_checks~ : Int32 = 1000000,
  max_tokens~ : Int32 = 8192,
  max_sql_bytes~ : Int32 = 65536,
) -> SQLVerificationOptionsV2 {
  { max_checks, max_tokens, max_sql_bytes, }
}

///|
pub fn sql_config_v2_json(config : SQLConfigV2) -> Json {
  v4_json_copy(config.record)
}

///|
fn sql_identifier_v2(value : Json) -> String raise {
  let text = sql_identifier_v1(value)
  if !sql_well_formed_utf16_v1(text) {
    fail("config:identifier-Unicode")
  }
  text
}

///|
fn sql_config_column_v2(raw : Json, key~ : Bool) -> (SQLColumnV1, Json) raise {
  let fields = object_fields(raw, "V2 column")
  known_fields(fields, ["name", "type", "comparison"], "V2 column")
  let name = sql_identifier_v2(required(fields, "name", "V2 column"))
  let kind = sql_string_v1(required(fields, "type", "V2 column"))
  if !(if key { ["int64", "text", "uuid"] } else { ["int64", "bool", "text"] }).contains(
      kind,
    ) {
    fail("config:V2-column-type")
  }
  let comparison = fields.get_or_default("comparison", Json::null())
  if kind == "text" {
    if comparison != Json("postgres-c-utf8-v1") {
      fail("config:text-comparison")
    }
  } else if comparison != Json::null() {
    fail("config:comparison")
  }
  (
    { name, kind, },
    { "name": Json(name), "type": Json(kind), "comparison": comparison },
  )
}

///|
pub fn parse_sql_config_v2(text : String) -> Result[SQLConfigV2, String] {
  try {
    let root = object_fields(sql_json_v1(text, 262144), "V2 SQL config")
    known_fields(
      root,
      ["format", "table", "defaultSchema", "limits"],
      "V2 SQL config",
    )
    if required(root, "format", "V2 SQL config") !=
      Json("moontxnwitness-configured-sql/v2") {
      fail("config:V2-format")
    }
    let default_schema = match root.get("defaultSchema") {
      None | Some(Null) => None
      Some(value) => Some(sql_identifier_v2(value))
    }
    let table = object_fields(
      required(root, "table", "V2 SQL config"),
      "V2 table",
    )
    known_fields(
      table,
      ["schema", "table", "primaryKey", "businessColumns"],
      "V2 table",
    )
    let schema = sql_identifier_v2(required(table, "schema", "V2 table"))
    let name = sql_identifier_v2(required(table, "table", "V2 table"))
    let (key, key_record) = sql_config_column_v2(
      required(table, "primaryKey", "V2 table"),
      key=true,
    )
    let raw_columns = match required(table, "businessColumns", "V2 table") {
      Array(items) if items.length() >= 1 && items.length() <= 16 => items
      _ => fail("config:V2-business-columns-1-to-16")
    }
    let columns = [key]
    let business_records : Array[Json] = []
    for raw in raw_columns {
      let (column, record) = sql_config_column_v2(raw, key=false)
      if columns.any(c => c.name == column.name) {
        fail("config:V2-duplicate-column")
      }
      columns.push(column)
      business_records.push(record)
    }
    let table_record : Json = {
      "schema": Json(schema),
      "table": Json(name),
      "primaryKey": key_record,
      "businessColumns": Json(business_records),
    }
    let raw_limits = object_fields(
      root.get_or_default("limits", Json::object(Map([]))),
      "V2 limits",
    )
    known_fields(
      raw_limits,
      [
        "max_sql_bytes", "max_tokens", "max_ast_nodes", "max_nesting", "max_text_bytes",
      ],
      "V2 limits",
    )
    let limits : Map[String, Int32] = Map([])
    let normalized_limits : Map[String, Json] = Map([])
    for
      (limit, fallback, ceiling) in [
        ("max_sql_bytes", 65536, 1048576),
        ("max_tokens", 8192, 32768),
        ("max_ast_nodes", 4096, 32768),
        ("max_nesting", 64, 128),
        ("max_text_bytes", 65536, 1048576),
      ] {
      let value = sql_limit_v1(raw_limits, limit, fallback, ceiling)
      limits[limit] = value
      normalized_limits[limit] = Json(value)
    }
    // Fixed V2 grammar bounds used by shared private identifier/projection work.
    limits["max_terms"] = 1
    limits["max_insert_rows"] = 1
    let record : Json = {
      "format": "moontxnwitness-configured-sql/v2",
      "table": table_record,
      "defaultSchema": match default_schema {
        Some(value) => Json(value)
        None => Json::null()
      },
      "limits": Json::object(normalized_limits),
    }
    let digest = v3_dislock_sha256(sql_canonical_v1(record))
    let parser_config : SQLConfigV1 = {
      tables: [{ schema, name, key: key.name, columns, record: table_record, }],
      record,
      digest,
      limits,
      default_schema,
    }
    Ok({ parser_config, record, digest, })
  } catch {
    error => Err(report_error_text(error))
  }
}

///|
// Identity normalization is independent of Python UUID and never alters input JSON.
fn sql_uuid_identity_v2(value : Json) -> String raise {
  let source = sql_string_v1(value)
  let chars = source.to_array()
  if chars.length() != 32 && chars.length() != 36 {
    fail("parameter:UUID-width")
  }
  let digits = StringBuilder()
  for index, c in chars {
    if chars.length() == 36 && [8, 13, 18, 23].contains(index) {
      if c != '-' {
        fail("parameter:UUID-hyphen")
      }
    } else {
      if !((c >= '0' && c <= '9') ||
        (c >= 'a' && c <= 'f') ||
        (c >= 'A' && c <= 'F')) {
        fail("parameter:UUID-hex")
      }
      digits.write_char(c)
    }
  }
  let hex = digits.to_string().to_lower().to_array()
  let result = StringBuilder()
  for index, c in hex {
    if [8, 12, 16, 20].contains(index) {
      result.write_char('-')
    }
    result.write_char(c)
  }
  result.to_string()
}

///|
fn sql_typed_value_v2(
  value : Json,
  kind : String,
  text_limit : Int32,
) -> Json raise {
  if kind == "uuid" {
    { "type": "uuid", "value": Json(sql_uuid_identity_v2(value)) }
  } else {
    if value is String(text) && !sql_well_formed_utf16_v1(text) {
      fail("parameter:text-Unicode")
    }
    sql_typed_value_v1(value, kind, text_limit)
  }
}
