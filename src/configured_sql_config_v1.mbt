///|
priv struct SQLColumnV1 {
  name : String
  kind : String
}

///|
priv struct SQLTableV1 {
  schema : String
  name : String
  key : String
  columns : Array[SQLColumnV1]
  record : Json
}

///|
pub struct SQLConfigV1 {
  priv tables : Array[SQLTableV1]
  priv record : Json
  priv digest : String
  priv limits : Map[String, Int32]
  priv default_schema : String?
}

///|
pub struct SQLVerificationOptionsV1 {
  priv max_checks : Int32
  priv max_tokens : Int32
  priv max_sql_bytes : Int32
}

///|
pub fn sql_verification_options_v1(
  max_checks~ : Int32 = 1000000,
  max_tokens~ : Int32 = 8192,
  max_sql_bytes~ : Int32 = 65536,
) -> SQLVerificationOptionsV1 {
  { max_checks, max_tokens, max_sql_bytes, }
}

///|
pub fn sql_config_v1_json(config : SQLConfigV1) -> Json {
  v4_json_copy(config.record)
}

///|
fn sql_json_v1(text : String, maximum : Int32) -> Json raise {
  if orm_utf8_size(text) > maximum {
    fail("budget:json-bytes")
  }
  @json.parse(
    text[:],
    max_nesting_depth=64,
    reject_duplicate_keys=true,
    preserve_number_repr=true,
  )
}

///|
fn sql_canonical_v1(value : Json) -> String {
  match value {
    Object(fields) => {
      let keys = fields.keys().to_array()
      keys.sort_by(relation_v3_text_compare)
      let parts = keys.map(key => {
        Json(key).stringify() + ":" + sql_canonical_v1(fields.at(key))
      })
      "{" + parts.join(",") + "}"
    }
    Array(items) => "[" + items.map(sql_canonical_v1).join(",") + "]"
    _ => value.stringify()
  }
}

///|
fn sql_string_v1(value : Json) -> String raise {
  match value {
    String(text) => text
    _ => fail("type:text-required")
  }
}

///|
fn sql_identifier_v1(value : Json) -> String raise {
  let text = sql_string_v1(value)
  if text.is_empty() || orm_utf8_size(text) > 63 || text.contains("\u0000") {
    fail("config:identifier")
  }
  text
}

///|
fn sql_digits_v1(text : String) -> Bool {
  !text.is_empty() && text.to_array().all(c => c >= '0' && c <= '9')
}

///|
fn sql_decimal_v1(text : String) -> String raise {
  if text.length() > 20 {
    fail("type:int64-lexeme-width")
  }
  let chars = text.to_array()
  if chars.is_empty() {
    fail("type:int64")
  }
  let negative = chars[0] == '-'
  let mut start = if negative { 1 } else { 0 }
  if chars.length() - start > 19 {
    fail("type:int64-lexeme-width")
  }
  if start >= chars.length() {
    fail("type:int64")
  }
  for i = start; i < chars.length(); i = i + 1 {
    if chars[i] < '0' || chars[i] > '9' {
      fail("type:integer-lexeme")
    }
  }
  while start + 1 < chars.length() && chars[start] == '0' {
    start += 1
  }
  let builder = StringBuilder()
  for i = start; i < chars.length(); i = i + 1 {
    builder.write_char(chars[i])
  }
  let digits = builder.to_string()
  let bound = if negative {
    "9223372036854775808"
  } else {
    "9223372036854775807"
  }
  if digits.length() > 19 || (digits.length() == 19 && digits > bound) {
    fail("type:int64-range")
  }
  if negative && digits != "0" {
    "-" + digits
  } else {
    digits
  }
}

///|
fn sql_number_text_v1(value : Json) -> String raise {
  match value {
    Number(_, repr=Some(text)) => sql_decimal_v1(text)
    Number(number, repr=None) if number >= -9007199254740991.0 &&
      number <= 9007199254740991.0 &&
      number.to_int64().to_double() == number => number.to_int64().to_string()
    _ => fail("type:exact-integer-required")
  }
}

///|
fn sql_limit_v1(
  fields : Map[String, Json],
  name : String,
  fallback : Int32,
  ceiling : Int32,
) -> Int32 raise {
  match fields.get(name) {
    None => fallback
    Some(value) => {
      let text = sql_number_text_v1(value)
      if !sql_digits_v1(text) || text.length() > 7 {
        fail("config:limit")
      }
      let mut result = 0
      for c in text.to_array() {
        result = result * 10 + c.to_int() - 48
      }
      if result < 1 || result > ceiling {
        fail("config:limit")
      }
      result
    }
  }
}

///|
pub fn parse_sql_config_v1(text : String) -> Result[SQLConfigV1, String] {
  try {
    let root = object_fields(sql_json_v1(text, 262144), "SQL config")
    known_fields(
      root,
      ["format", "tables", "defaultSchema", "limits"],
      "SQL config",
    )
    if required(root, "format", "SQL config") !=
      Json("moontxnwitness-configured-sql/v1") {
      fail("config:format")
    }
    let default_schema = match root.get("defaultSchema") {
      None | Some(Null) => None
      Some(value) => Some(sql_identifier_v1(value))
    }
    let limit_fields = object_fields(
      root.get_or_default("limits", Json::object(Map([]))),
      "SQL limits",
    )
    known_fields(
      limit_fields,
      [
        "max_sql_bytes", "max_tokens", "max_ast_nodes", "max_nesting", "max_terms",
        "max_insert_rows", "max_text_bytes",
      ],
      "SQL limits",
    )
    let limits : Map[String, Int32] = Map([])
    let normalized_limits : Map[String, Json] = Map([])
    for
      (name, fallback, ceiling) in [
        ("max_sql_bytes", 65536, 1048576),
        ("max_tokens", 8192, 32768),
        ("max_ast_nodes", 4096, 32768),
        ("max_nesting", 64, 128),
        ("max_terms", 128, 1024),
        ("max_insert_rows", 128, 1024),
        ("max_text_bytes", 65536, 1048576),
      ] {
      let value = sql_limit_v1(limit_fields, name, fallback, ceiling)
      limits[name] = value
      normalized_limits[name] = Json(value)
    }
    let raw_tables = match required(root, "tables", "SQL config") {
      Array(items) if items.length() >= 1 && items.length() <= 128 => items
      _ => fail("config:tables")
    }
    let tables : Array[SQLTableV1] = []
    let records : Array[Json] = []
    for raw in raw_tables {
      let table = object_fields(raw, "table")
      known_fields(
        table,
        ["schema", "table", "primaryKey", "columns", "model"],
        "table",
      )
      let schema = sql_identifier_v1(required(table, "schema", "table"))
      let name = sql_identifier_v1(required(table, "table", "table"))
      let key = sql_identifier_v1(required(table, "primaryKey", "table"))
      if tables.any(t => t.schema == schema && t.name == name) {
        fail("config:duplicate-relation")
      }
      let model = table.get_or_default("model", Json("relation-set-v1"))
      if ![
          Json("relation-set-v1"),
          Json("point-register-v1"),
          Json("append-list-v1"),
        ].contains(model) {
        fail("config:model-hint")
      }
      let raw_columns = match required(table, "columns", "table") {
        Array(items) if items.length() >= 1 && items.length() <= 128 => items
        _ => fail("config:columns")
      }
      let columns : Array[SQLColumnV1] = []
      let column_records : Array[Json] = []
      for raw_column in raw_columns {
        let field = object_fields(raw_column, "column")
        known_fields(field, ["name", "type", "comparison"], "column")
        let column_name = sql_identifier_v1(required(field, "name", "column"))
        let kind = sql_string_v1(required(field, "type", "column"))
        let comparison = field.get_or_default("comparison", Json::null())
        if !["int64", "bool", "text"].contains(kind) ||
          columns.any(c => c.name == column_name) {
          fail("config:column")
        }
        if kind == "text" {
          if comparison != Json("postgres-c-utf8-v1") {
            fail("config:text-comparison")
          }
        } else if comparison != Json::null() {
          fail("config:comparison")
        }
        columns.push({ name: column_name, kind, })
        column_records.push({
          "name": Json(column_name),
          "type": Json(kind),
          "comparison": comparison,
        })
      }
      if !columns.any(c => c.name == key) {
        fail("config:single-primary-key")
      }
      let record : Json = {
        "schema": Json(schema),
        "table": Json(name),
        "primaryKey": Json(key),
        "columns": Json(column_records),
        "model": model,
      }
      tables.push({ schema, name, key, columns, record, })
      records.push(record)
    }
    let record : Json = {
      "format": "moontxnwitness-configured-sql/v1",
      "tables": Json(records),
      "defaultSchema": match default_schema {
        Some(name) => Json(name)
        None => Json::null()
      },
      "limits": Json::object(normalized_limits),
    }
    Ok({
      tables,
      record,
      digest: v3_dislock_sha256(sql_canonical_v1(record)),
      limits,
      default_schema,
    })
  } catch {
    error => Err(error.to_string())
  }
}

///|
fn sql_well_formed_utf16_v1(text : String) -> Bool {
  let units = text.code_units()
  let mut index = 0
  while index < units.length() {
    let value = units[index].to_int()
    if value >= 0xd800 && value <= 0xdbff {
      if index + 1 >= units.length() {
        return false
      }
      let trailing = units[index + 1].to_int()
      if trailing < 0xdc00 || trailing > 0xdfff {
        return false
      }
      index += 2
    } else if value >= 0xdc00 && value <= 0xdfff {
      return false
    } else {
      index += 1
    }
  }
  true
}
