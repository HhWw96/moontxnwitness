///|
priv struct SQLRawColumnV1 {
  parts : Array[String]
  star : Bool
  output : String?
}

///|
fn SQLParseWorkV1::raw_column(
  self : SQLParseWorkV1,
  with_alias~ : Bool = false,
) -> SQLRawColumnV1 raise {
  let parts : Array[String] = []
  let mut star = false
  if self.accept("*") {
    star = true
  } else {
    parts.push(self.identifier())
    while self.accept(".") {
      if self.accept("*") {
        star = true
        break
      }
      parts.push(self.identifier())
      if parts.length() > 3 {
        fail("unsupported:catalog-column")
      }
    }
  }
  let mut output : String? = None
  if with_alias {
    if self.accept("as") {
      output = Some(self.identifier())
    } else {
      let next = self.peek()
      if next.kind == "id" ||
        (next.kind == "word" && !sql_reserved_v1(next.value)) {
        output = Some(self.identifier())
      }
    }
  }
  { parts, star, output, }
}

///|
fn SQLParseWorkV1::raw_columns(
  self : SQLParseWorkV1,
) -> Array[SQLRawColumnV1] raise {
  let columns = [self.raw_column(with_alias=true)]
  while self.accept(",") {
    columns.push(self.raw_column(with_alias=true))
  }
  columns
}

///|
fn SQLParseWorkV1::relation(self : SQLParseWorkV1) -> Unit raise {
  let first = self.identifier()
  let (schema, name) = if self.accept(".") {
    self.resolution = "explicit-schema"
    (first, self.identifier())
  } else {
    self.resolution = "configured-default-schema-requires-session-proof"
    match self.config.default_schema {
      Some(schema) => (schema, first)
      None => fail("unsupported:schema-resolution")
    }
  }
  self.table = self.config.tables
    .iter()
    .find_first(table => table.schema == schema && table.name == name)
  if self.table is None {
    fail("mismatch:unknown-table")
  }
  if self.accept("as") {
    self.table_alias = Some(self.identifier())
  } else {
    let next = self.peek()
    if next.kind == "id" ||
      (next.kind == "word" && !sql_reserved_v1(next.value)) {
      self.table_alias = Some(self.identifier())
    }
  }
}

///|
fn SQLParseWorkV1::column(
  self : SQLParseWorkV1,
  raw : SQLRawColumnV1,
) -> SQLColumnV1? raise {
  let table = self.table.unwrap()
  let count = raw.parts.length() - (if raw.star { 0 } else { 1 })
  if count < 0 || count > 2 {
    fail("unsupported:column-shape")
  }
  if count == 1 && raw.parts[0] != self.table_alias.unwrap_or(table.name) {
    fail("mismatch:column-qualifier")
  }
  if count == 2 &&
    (
      self.table_alias is Some(_) ||
      raw.parts[0] != table.schema ||
      raw.parts[1] != table.name
    ) {
    fail("mismatch:column-qualifier")
  }
  if raw.star {
    return None
  }
  let name = raw.parts[raw.parts.length() - 1]
  match table.columns.iter().find_first(column => column.name == name) {
    Some(column) => Some(column)
    None => fail("mismatch:unknown-column")
  }
}

///|
fn SQLParseWorkV1::projections(
  self : SQLParseWorkV1,
  columns : Array[SQLRawColumnV1],
) -> Array[Json] raise {
  let result : Array[Json] = []
  for raw in columns {
    sql_charge_v1(self)
    match self.column(raw) {
      None => {
        if raw.output is Some(_) {
          fail("unsupported:star-alias")
        }
        for column in self.table.unwrap().columns {
          sql_charge_v1(self)
          result.push({
            "column": Json(column.name),
            "outputName": Json(column.name),
          })
        }
      }
      Some(column) =>
        result.push({
          "column": Json(column.name),
          "outputName": Json(raw.output.unwrap_or(column.name)),
        })
    }
    if result.length() > self.config.limits.at("max_ast_nodes") {
      fail("budget:projections")
    }
  }
  result
}

///|
fn sql_typed_value_v1(
  value : Json,
  kind : String,
  text_limit : Int32,
) -> Json raise {
  match kind {
    "int64" => { "type": "int64", "value": Json(sql_number_text_v1(value)) }
    "bool" =>
      match value {
        True | False => { "type": "bool", "value": value }
        _ => fail("parameter:bool")
      }
    "text" =>
      match value {
        String(text) if orm_utf8_size(text) <= text_limit &&
          !text.contains("\u0000") => { "type": "text", "value": Json(text) }
        _ => fail("parameter:text")
      }
    _ => fail("parameter:type")
  }
}

///|
fn SQLParseWorkV1::scalar(
  self : SQLParseWorkV1,
  column : SQLColumnV1,
) -> Json raise {
  let token = self.peek()
  if token.kind == "bind" || token.kind == "named" {
    let _ = self.take()
    let style = if token.kind == "bind" { "positional" } else { "named" }
    if self.style != "" && self.style != style {
      fail("unsupported:mixed-binds")
    }
    self.style = style
    let reference : Json = {
      "kind": Json(style),
      "value": if style == "positional" {
        Json(self.refs.length())
      } else {
        Json(token.value)
      },
      "type": Json(column.kind),
    }
    self.refs.push(reference)
    return reference
  }
  if self.accept("(") {
    let value = self.scalar(column)
    self.expect(")")
    return value
  }
  let negative = self.accept("-")
  let token = self.take()
  let value : Json = if token.kind == "num" {
    let text = sql_decimal_v1((if negative { "-" } else { "" }) + token.value)
    if column.kind != "int64" {
      fail("literal:type")
    }
    return { "kind": "literal", "value": Json(text), "type": "int64" }
  } else if negative {
    fail("unsupported:negative-expression")
  } else if token.kind == "str" {
    Json(token.value)
  } else if token.kind == "word" && token.value == "true" {
    Json(true)
  } else if token.kind == "word" && token.value == "false" {
    Json(false)
  } else {
    fail("unsupported:scalar")
  }
  let typed = object_fields(
    sql_typed_value_v1(
      value,
      column.kind,
      self.config.limits.at("max_text_bytes"),
    ),
    "typed scalar",
  )
  { "kind": "literal", "value": typed.at("value"), "type": Json(column.kind) }
}

///|
fn SQLParseWorkV1::conjunction(
  self : SQLParseWorkV1,
  terms : Array[Json],
  depth : Int32,
) -> Unit raise {
  if depth > self.config.limits.at("max_nesting") {
    fail("budget:predicate-nesting")
  }
  while true {
    sql_charge_v1(self)
    if self.accept("(") {
      self.conjunction(terms, depth + 1)
      self.expect(")")
    } else {
      let raw = self.raw_column()
      let column = self.column(raw).unwrap()
      let collation = if self.accept("collate") {
        let name = self.identifier()
        if name != "C" || column.kind != "text" {
          fail("unsupported:collation")
        }
        Json(name)
      } else {
        Json::null()
      }
      let operator_token = self.take()
      if operator_token.kind != "symbol" {
        fail("grammar:operator-token-kind")
      }
      let op = operator_token.value
      let operation = match op {
        "=" => "eq"
        "<" => "lt"
        "<=" => "le"
        ">" => "gt"
        ">=" => "ge"
        _ => fail("unsupported:predicate")
      }
      if column.kind == "bool" && operation != "eq" {
        fail("unsupported:boolean-range")
      }
      let value = self.scalar(column)
      terms.push({
        "column": Json(column.name),
        "operator": Json(operation),
        "value": value,
        "collation": collation,
      })
      if terms.length() > self.config.limits.at("max_terms") {
        fail("budget:terms")
      }
    }
    if !self.accept("and") {
      break
    }
  }
}

///|
fn SQLParseWorkV1::descriptor(
  self : SQLParseWorkV1,
  source : String,
) -> Json raise {
  let operation = self.take()
  if operation.kind != "word" ||
    !["select", "insert", "update", "delete"].contains(operation.value) {
    fail("unsupported:statement-kind")
  }
  let mut projections : Array[Json] = []
  let insert_columns : Array[String] = []
  let insert_rows : Array[Json] = []
  let assignments : Array[Json] = []
  if operation.value == "select" {
    let raw = self.raw_columns()
    self.expect("from")
    self.relation()
    projections = self.projections(raw)
  } else if operation.value == "insert" {
    self.expect("into")
    self.relation()
    self.expect("(")
    insert_columns.push(self.identifier())
    while self.accept(",") {
      insert_columns.push(self.identifier())
    }
    self.expect(")")
    let table = self.table.unwrap()
    if !insert_columns.contains(table.key) {
      fail("unsupported:insert-primary-key")
    }
    let selected : Array[SQLColumnV1] = []
    for name in insert_columns {
      if selected.any(column => column.name == name) {
        fail("unsupported:duplicate-insert-column")
      }
      match table.columns.iter().find_first(column => column.name == name) {
        Some(column) => selected.push(column)
        None => fail("mismatch:insert-column")
      }
    }
    self.expect("values")
    while true {
      self.expect("(")
      let row : Array[Json] = []
      for index, column in selected {
        if index != 0 {
          self.expect(",")
        }
        row.push(self.scalar(column))
      }
      self.expect(")")
      insert_rows.push(Json(row))
      if insert_rows.length() > self.config.limits.at("max_insert_rows") {
        fail("budget:insert-rows")
      }
      if !self.accept(",") {
        break
      }
    }
  } else {
    if operation.value == "delete" {
      self.expect("from")
    }
    self.relation()
    if operation.value == "update" {
      self.expect("set")
      let seen : Array[String] = []
      while true {
        let column = self.column(self.raw_column()).unwrap()
        if column.name == self.table.unwrap().key {
          fail("unsupported:primary-key-update")
        }
        if seen.contains(column.name) {
          fail("unsupported:duplicate-assignment")
        }
        seen.push(column.name)
        self.expect("=")
        assignments.push({
          "column": Json(column.name),
          "value": self.scalar(column),
        })
        if !self.accept(",") {
          break
        }
      }
    }
  }
  let predicates : Array[Json] = []
  if self.accept("where") {
    self.conjunction(predicates, 0)
  }
  let ordering : Array[Json] = []
  if operation.value == "select" && self.accept("order") {
    self.expect("by")
    while true {
      let column = self.column(self.raw_column()).unwrap()
      let descending = if self.accept("desc") {
        true
      } else {
        let _ = self.accept("asc")
        false
      }
      ordering.push({
        "column": Json(column.name),
        "descending": Json(descending),
        "nullsFirst": Json(descending),
      })
      if !self.accept(",") {
        break
      }
    }
  }
  let returning = if operation.value != "select" && self.accept("returning") {
    self.projections(self.raw_columns())
  } else {
    []
  }
  let _ = self.accept(";")
  if self.peek().kind != "eof" {
    fail("unsupported:remaining-SQL")
  }
  if self.stray_percent && !self.refs.is_empty() {
    fail("unsupported:driver-percent-ambiguity")
  }
  if (self.tokens.length() - 1) * 2 + 2 > self.config.limits.at("max_ast_nodes") {
    fail("budget:conservative-structure")
  }
  {
    "format": "moontxnwitness-sql-ast-candidate/v1",
    "parserContract": "sqlglot-30.26-postgres-single-table/v1",
    "sqlglotVersion": "30.26.0",
    "configSha256": Json(self.config.digest),
    "sqlSha256": Json(v3_dislock_sha256(source)),
    "originalSql": Json(source),
    "table": self.table.unwrap().record,
    "operation": Json(operation.value),
    "schemaResolution": Json(self.resolution),
    "projections": Json(projections),
    "predicates": Json(predicates),
    "assignments": Json(assignments),
    "insertColumns": Json(insert_columns),
    "insertRows": Json(insert_rows),
    "returning": Json(returning),
    "ordering": Json(ordering),
    "parameters": Json(self.refs.copy()),
    "requiresNoParameterArgument": Json(self.stray_percent),
    "databaseSyntaxValidated": false,
    "sourceAuthenticated": false,
    "captureFactsProduced": false,
    "moonbitProjectionVerified": false,
    "returningIsPredicateRead": false,
    "requiredProofs": [
      "catalog-types-primary-key-and-text-collation", "session-schema-resolution",
      "server-encoding-and-string-literal-rules", "actual-execution-and-delivered-result-shape",
      "complete-fetch-for-predicate-read", "installed-unique-version-sources-and-effective-write-ledger",
      "same-statement-or-native-observed-read-version-identity", "complete-source-window-and-writer-scope",
      "independent-MoonBit-original-SQL-parameters-source-projection",
    ],
  }
}

///|
fn SQLParseWorkV1::bindings(
  self : SQLParseWorkV1,
  parameters : Json,
) -> Json raise {
  if self.stray_percent && parameters != Json::null() {
    fail("parameter:percent-requires-None")
  }
  if self.refs.is_empty() {
    match parameters {
      Null => ()
      Array(items) if items.is_empty() => ()
      Object(fields) if fields.is_empty() => ()
      _ => fail("parameter:unexpected")
    }
    return Json(([] : Array[Json]))
  }
  let values : Array[Json] = []
  if self.style == "named" {
    let fields = object_fields(parameters, "named parameters")
    let names : Array[String] = []
    for reference in self.refs {
      let name = sql_string_v1(
        object_fields(reference, "reference").at("value"),
      )
      if !names.contains(name) {
        names.push(name)
      }
      values.push(required(fields, name, "named parameters"))
    }
    if fields.length() != names.length() {
      fail("parameter:extra-named-value")
    }
  } else {
    match parameters {
      Array(items) if items.length() == self.refs.length() =>
        values.append(items)
      _ => fail("parameter:positional-arity")
    }
  }
  let bindings : Array[Json] = []
  for index, reference in self.refs {
    sql_charge_v1(self)
    let kind = sql_string_v1(object_fields(reference, "reference").at("type"))
    bindings.push({
      "reference": reference,
      "value": sql_typed_value_v1(
        values[index],
        kind,
        self.config.limits.at("max_text_bytes"),
      ),
    })
  }
  Json(bindings)
}
