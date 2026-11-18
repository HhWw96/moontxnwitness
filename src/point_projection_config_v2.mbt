///|
pub struct PointProjectionOptionsV2 {
  priv config : SQLConfigV2
  priv version_column : String
  priv star_columns : Array[String]?
  priv max_sql_bytes : Int32
  priv max_descriptor_bytes : Int32
  priv record : Json
}

///|
pub fn point_projection_options_v2(
  config : SQLConfigV2,
  version_column~ : String = "__mtw_source_version",
  version_type~ : String = "int64",
  star_contract~ : String? = None,
  business_star_columns~ : Array[String]? = None,
  max_projected_sql_bytes~ : Int32 = 131072,
  max_descriptor_bytes~ : Int32 = 16777216,
) -> Result[PointProjectionOptionsV2, String] {
  try {
    let _ = sql_identifier_v2(Json(version_column))
    let names = config.parser_config.tables[0].columns.map(c => c.name)
    if names.contains(version_column) || version_type != "int64" {
      fail("invalid:projection-version-column")
    }
    let star_columns = match (star_contract, business_star_columns) {
      (None, None) => None
      (Some("preinstallation-business-schema/v1"), Some(columns)) => {
        if columns != names {
          fail("invalid:projection-business-star-view")
        }
        Some(columns.copy())
      }
      _ => fail("invalid:projection-star-contract")
    }
    if max_projected_sql_bytes < 1 ||
      max_projected_sql_bytes > 2097152 ||
      max_descriptor_bytes < 1 ||
      max_descriptor_bytes > 67108864 {
      fail("invalid:projection-options-byte-limits")
    }
    let record : Json = {
      "config": config.record,
      "versionColumn": Json(version_column),
      "versionType": "int64",
      "starContract": match star_contract {
        Some(value) => Json(value)
        None => Json::null()
      },
      "businessStarColumns": match star_columns {
        Some(columns) => Json(columns)
        None => Json::null()
      },
      "maxProjectedSqlBytes": Json(max_projected_sql_bytes),
      "maxDescriptorBytes": Json(max_descriptor_bytes),
    }
    Ok({
      config,
      version_column,
      star_columns,
      max_sql_bytes: max_projected_sql_bytes,
      max_descriptor_bytes,
      record,
    })
  } catch {
    error => Err(error.to_string())
  }
}

///|
pub struct PointProjectionVerificationOptionsV2 {
  priv max_checks : Int32
  priv grammar_options : SQLVerificationOptionsV2
}

///|
pub fn point_projection_verification_options_v2(
  max_checks~ : Int32 = 1000000,
  grammar_options~ : SQLVerificationOptionsV2 = sql_verification_options_v2(),
) -> PointProjectionVerificationOptionsV2 {
  { max_checks, grammar_options, }
}

///|
priv struct PointProjectionWorkV2 {
  budget : PointProjectionVerificationOptionsV2
  mut checks : Int32
  atoms : Array[Json]
  named : Map[String, Json]
  mut container : String
  mapping : Array[Json]
}

///|
fn PointProjectionWorkV2::charge(self : PointProjectionWorkV2) -> Unit raise {
  if self.checks >= self.budget.max_checks {
    fail("budget:point-projection-checks")
  }
  self.checks += 1
}

///|
fn point_atom_v2(raw : Json) -> (Json, Json) raise {
  let fields = object_fields(raw, "original typed parameter atom")
  let kind = sql_string_v1(
    required(fields, "pythonType", "typed parameter atom"),
  )
  if kind == "int" {
    let fields = orm_exact(raw, ["pythonType", "decimal"])
    let decimal = sql_string_v1(fields.at("decimal"))
    if sql_decimal_v1(decimal) != decimal {
      fail("invalid:typed-int-observation")
    }
    (v4_json_copy(raw), sql_json_v1(decimal, 32))
  } else {
    let fields = orm_exact(raw, ["pythonType", "value"])
    let value = fields.at("value")
    if kind == "bool" {
      if value != Json(true) && value != Json(false) {
        fail("invalid:typed-bool-observation")
      }
    } else if kind == "str" || kind == "uuid.UUID" {
      let text = sql_string_v1(value)
      if !sql_well_formed_utf16_v1(text) || text.contains("\u0000") {
        fail("invalid:typed-string-observation")
      }
      if kind == "uuid.UUID" && sql_uuid_identity_v2(value) != text {
        fail("invalid:typed-UUID-object-observation")
      }
    } else {
      fail("invalid:typed-parameter-Python-type")
    }
    (v4_json_copy(raw), value)
  }
}

///|
fn PointProjectionWorkV2::parameters(
  self : PointProjectionWorkV2,
  raw : Json,
) -> Json raise {
  let fields = orm_exact(raw, ["container", "items"])
  self.container = sql_string_v1(fields.at("container"))
  let items = orm_array(fields.at("items"))
  if items.length() > 17 {
    fail("budget:typed-parameter-count")
  }
  let semantic : Array[Json] = []
  let semantic_named : Map[String, Json] = Map([])
  if self.container == "none" {
    if !items.is_empty() {
      fail("invalid:none-parameter-items")
    }
    return Json::null()
  }
  if !["list", "tuple", "dict"].contains(self.container) {
    fail("invalid:typed-parameter-container")
  }
  for item in items {
    self.charge()
    if self.container == "dict" {
      let item = orm_exact(item, ["name", "value"])
      let name = sql_string_v1(item.at("name"))
      if name.is_empty() ||
        !sql_well_formed_utf16_v1(name) ||
        name.contains("\u0000") ||
        orm_utf8_size(name) > 128 ||
        self.named.contains(name) {
        fail("invalid:typed-dict-key")
      }
      let (atom, value) = point_atom_v2(item.at("value"))
      self.named[name] = atom
      semantic_named[name] = value
    } else {
      let (atom, value) = point_atom_v2(item)
      self.atoms.push(atom)
      semantic.push(value)
    }
  }
  if self.container == "dict" {
    Json::object(semantic_named)
  } else {
    Json(semantic)
  }
}

///|
fn point_bound_atom_v2(typed : Json) -> Json raise {
  let fields = object_fields(typed, "independent typed binding")
  let kind = sql_string_v1(fields.at("type"))
  let value = fields.at("value")
  if kind == "int64" {
    { "pythonType": "int", "decimal": value }
  } else {
    {
      "pythonType": Json(if kind == "bool" { "bool" } else { "str" }),
      "value": value,
    }
  }
}

///|
fn PointProjectionWorkV2::scalar(
  self : PointProjectionWorkV2,
  reference : Json,
) -> String raise {
  self.charge()
  let fields = object_fields(reference, "independent reference")
  let kind = sql_string_v1(fields.at("kind"))
  let sql_type = sql_string_v1(fields.at("type"))
  let (atom, origin) : (Json, Json) = if kind == "named" {
    let name = sql_string_v1(fields.at("value"))
    match self.named.get(name) {
      Some(atom) => (atom, { "kind": "named", "name": Json(name) })
      None => fail("mismatch:projection-original-named-binding")
    }
  } else if kind == "positional" {
    let index = fetch_number_v1(fields.at("value"), 16)
    if index >= self.atoms.length() {
      fail("mismatch:projection-original-positional-binding")
    }
    (self.atoms[index], { "kind": "positional", "index": Json(index) })
  } else if kind == "literal" {
    let atom = point_bound_atom_v2({
      "type": Json(sql_type),
      "value": fields.at("value"),
    })
    (atom, { "kind": "literal", "value": atom })
  } else {
    fail("mismatch:projection-reference-kind")
  }
  self.mapping.push({
    "projectedIndex": Json(self.mapping.length()),
    "original": origin,
    "sqlType": Json(sql_type),
    "value": atom,
    "cast": if sql_type == "uuid" {
      Json("uuid")
    } else {
      Json::null()
    },
  })
  if sql_type == "uuid" {
    "CAST(%s AS UUID)"
  } else {
    "%s"
  }
}

///|
fn point_quote_v2(text : String) -> String {
  let result = StringBuilder()
  result.write_char('"')
  for c in text.to_array() {
    if c == '"' || c == '%' {
      result.write_char(c)
    }
    result.write_char(c)
  }
  result.write_char('"')
  result.to_string()
}

///|
fn point_fresh_v2(
  work : PointProjectionWorkV2,
  base : String,
  used : Array[String],
) -> String raise {
  let mut name = base
  let mut suffix = 0
  while used.contains(name) {
    work.charge()
    suffix += 1
    name = base + "_" + suffix.to_string()
  }
  used.push(name)
  name
}

///|
fn point_has_star_v2(
  work : PointProjectionWorkV2,
  config : SQLConfigV2,
  source : String,
) -> Bool raise {
  let lexer : SQLParseWorkV1 = {
    config: config.parser_config,
    options: sql_verification_options_v1(
      max_checks=work.budget.max_checks - work.checks,
      max_tokens=work.budget.grammar_options.max_tokens,
      max_sql_bytes=work.budget.grammar_options.max_sql_bytes,
    ),
    tokens: [],
    refs: [],
    pos: 0,
    checks: 0,
    table: None,
    table_alias: None,
    resolution: "",
    style: "",
    stray_percent: false,
  }
  let result : Result[Unit, String] = try {
    sql_lex_shared_v1(lexer, source, true)
    Ok(())
  } catch {
    error => Err(error.to_string())
  }
  work.checks += lexer.checks
  match result {
    Err(reason) => fail(reason)
    Ok(_) => ()
  }
  // In the independently accepted V2 grammar only result projections can have
  // a symbol star. Quoted identifiers, strings and comments are separate tokens.
  lexer.tokens.any(token => token.kind == "symbol" && token.value == "*")
}
