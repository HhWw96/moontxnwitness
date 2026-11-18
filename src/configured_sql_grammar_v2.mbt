///|
fn SQLParseWorkV1::scalar_v2(
  self : SQLParseWorkV1,
  column : SQLColumnV1,
) -> Json raise {
  if self.accept("(") {
    let value = self.scalar_v2(column)
    self.expect(")")
    return value
  }
  if column.kind != "uuid" {
    return self.scalar(column)
  }
  let cast = self.accept("cast")
  if cast {
    self.expect("(")
  }
  let token = self.peek()
  if token.kind != "bind" && token.kind != "named" {
    fail("unsupported:V2-UUID-direct-bind")
  }
  // Shared scalar only allocates the original bind reference; V2 types values.
  let reference = self.scalar(column)
  if cast {
    self.expect("as")
    self.expect("uuid")
    self.expect(")")
  } else if self.accept("::") {
    self.expect("uuid")
  }
  reference
}

///|
fn SQLParseWorkV1::point_predicate_v2(self : SQLParseWorkV1) -> Json raise {
  if self.accept("(") {
    let predicate = self.point_predicate_v2()
    self.expect(")")
    return predicate
  }
  let column = match self.column(self.raw_column()) {
    Some(column) => column
    None => fail("unsupported:V2-point-column")
  }
  if column.name != self.table.unwrap().key {
    fail("unsupported:V2-point-primary-key")
  }
  let collation = if self.accept("collate") {
    let name = self.identifier()
    if name != "C" || column.kind != "text" {
      fail("unsupported:collation")
    }
    Json(name)
  } else {
    Json::null()
  }
  self.expect("=")
  {
    "column": Json(column.name),
    "operator": "eq",
    "value": self.scalar_v2(column),
    "collation": collation,
  }
}

///|
fn sql_projections_v2(
  work : SQLParseWorkV1,
  projections : Array[Json],
  full~ : Bool,
) -> Unit raise {
  let names : Array[String] = []
  let outputs : Array[String] = []
  for projection in projections {
    sql_charge_v1(work)
    let fields = object_fields(projection, "V2 projection")
    let name = sql_string_v1(fields.at("column"))
    let output = sql_string_v1(fields.at("outputName"))
    if names.contains(name) || outputs.contains(output) {
      fail("unsupported:V2-duplicate-projection")
    }
    names.push(name)
    outputs.push(output)
  }
  if full && names.length() != work.table.unwrap().columns.length() {
    fail("unsupported:V2-full-row-select")
  }
}

///|
fn sql_bound_assignment_v2(value : Json) -> Unit raise {
  if object_fields(value, "V2 scalar").at("kind") == Json("literal") {
    fail("unsupported:V2-parameter-assignment")
  }
}

///|
fn sql_descriptor_v2(
  work : SQLParseWorkV1,
  config : SQLConfigV2,
  source : String,
) -> Json raise {
  let token = work.take()
  if token.kind != "word" ||
    !["select", "insert", "update", "delete"].contains(token.value) {
    fail("unsupported:V2-statement-kind")
  }
  let operation = token.value
  let mut projections : Array[Json] = []
  let insert_columns : Array[String] = []
  let insert_rows : Array[Json] = []
  let assignments : Array[Json] = []
  let predicates : Array[Json] = []
  let mut key_reference : Json = Json::null()
  if operation == "select" {
    let raw = work.raw_columns()
    work.expect("from")
    work.relation()
    projections = work.projections(raw)
    sql_projections_v2(work, projections, full=true)
  } else if operation == "insert" {
    work.expect("into")
    work.relation()
    work.expect("(")
    insert_columns.push(work.identifier())
    while work.accept(",") {
      insert_columns.push(work.identifier())
    }
    work.expect(")")
    let table = work.table.unwrap()
    if insert_columns.length() != table.columns.length() ||
      !insert_columns.contains(table.key) {
      fail("unsupported:V2-full-row-insert")
    }
    let selected : Array[SQLColumnV1] = []
    for name in insert_columns {
      if selected.any(column => column.name == name) {
        fail("unsupported:V2-duplicate-insert-column")
      }
      match table.columns.iter().find_first(column => column.name == name) {
        Some(column) => selected.push(column)
        None => fail("mismatch:V2-insert-column")
      }
    }
    work.expect("values")
    work.expect("(")
    let row : Array[Json] = []
    for index, column in selected {
      if index != 0 {
        work.expect(",")
      }
      let value = work.scalar_v2(column)
      sql_bound_assignment_v2(value)
      if column.name == table.key {
        key_reference = value
      }
      row.push(value)
    }
    work.expect(")")
    insert_rows.push(Json(row))
  } else {
    if operation == "delete" {
      work.expect("from")
    }
    work.relation()
    if operation == "update" {
      work.expect("set")
      let seen : Array[String] = []
      while true {
        let column = match work.column(work.raw_column()) {
          Some(column) => column
          None => fail("unsupported:V2-assignment-column")
        }
        if column.name == work.table.unwrap().key {
          fail("unsupported:primary-key-update")
        }
        if seen.contains(column.name) {
          fail("unsupported:duplicate-assignment")
        }
        seen.push(column.name)
        work.expect("=")
        let value = work.scalar_v2(column)
        sql_bound_assignment_v2(value)
        assignments.push({ "column": Json(column.name), "value": value })
        if !work.accept(",") {
          break
        }
      }
    }
  }
  if operation != "insert" {
    work.expect("where")
    let predicate = work.point_predicate_v2()
    key_reference = object_fields(predicate, "V2 predicate").at("value")
    predicates.push(predicate)
  }
  let returning = if operation != "select" && work.accept("returning") {
    let result = work.projections(work.raw_columns())
    sql_projections_v2(work, result, full=false)
    result
  } else {
    []
  }
  let _ = work.accept(";")
  if work.peek().kind != "eof" {
    fail("unsupported:V2-remaining-SQL")
  }
  if work.stray_percent && !work.refs.is_empty() {
    fail("unsupported:driver-percent-ambiguity")
  }
  if (work.tokens.length() - 1) * 2 + 2 > work.config.limits.at("max_ast_nodes") {
    fail("budget:conservative-structure")
  }
  {
    "format": "moontxnwitness-sql-point-crud-candidate/v2",
    "parserContract": "sqlglot-30.26-postgres-single-table-point-crud/v2",
    "sqlglotVersion": "30.26.0",
    "configSha256": Json(config.digest),
    "sqlSha256": Json(v3_dislock_sha256(source)),
    "originalSql": Json(source),
    "table": work.table.unwrap().record,
    "operation": Json(operation),
    "schemaResolution": Json(work.resolution),
    "keyReference": key_reference,
    "projections": Json(projections),
    "predicates": Json(predicates),
    "assignments": Json(assignments),
    "insertColumns": Json(insert_columns),
    "insertRows": Json(insert_rows),
    "returning": Json(returning),
    "parameters": Json(work.refs.copy()),
    "requiresNoParameterArgument": Json(work.stray_percent),
    "databaseSyntaxValidated": false,
    "sourceAuthenticated": false,
    "captureFactsProduced": false,
    "sourceFactsProduced": false,
    "modelCoverageAccepted": false,
    "moonbitProjectionVerified": false,
    "returningIsPredicateRead": false,
    "requiredProofs": [
      "independent-MoonBit-v2-original-SQL-and-parameter-projection", "catalog-types-nonnull-primary-key-text-collation-and-DDL-epoch",
      "session-schema-and-encoding", "actual-execution-success-delivered-full-row-and-complete-fetch",
      "same-statement-or-native-observed-read-version-identity", "initialized-snapshot-dynamic-absence-and-complete-source-window",
      "installed-unique-version-sources-effective-writes-and-rollback-journal", "model-specific-projection-and-coverage",
    ],
  }
}

///|
fn sql_bindings_v2(work : SQLParseWorkV1, parameters : Json) -> Json raise {
  if work.stray_percent && parameters != Json::null() {
    fail("parameter:percent-requires-None")
  }
  if work.refs.is_empty() {
    match parameters {
      Null => ()
      Array(items) if items.is_empty() => ()
      Object(fields) if fields.is_empty() => ()
      _ => fail("parameter:unexpected")
    }
    return Json(([] : Array[Json]))
  }
  let values : Array[Json] = []
  if work.style == "named" {
    let fields = match parameters {
      Object(fields) => fields
      _ => fail("parameter:V2-named-object")
    }
    let names : Array[String] = []
    for reference in work.refs {
      let name = sql_string_v1(
        object_fields(reference, "V2 reference").at("value"),
      )
      if !names.contains(name) {
        names.push(name)
      }
      values.push(
        match fields.get(name) {
          Some(value) => value
          None => fail("parameter:V2-missing-named-value")
        },
      )
    }
    if fields.length() != names.length() {
      fail("parameter:extra-named-value")
    }
  } else {
    match parameters {
      Array(items) if items.length() == work.refs.length() =>
        values.append(items)
      _ => fail("parameter:positional-arity")
    }
  }
  let result : Array[Json] = []
  for index, reference in work.refs {
    sql_charge_v1(work)
    let kind = sql_string_v1(
      object_fields(reference, "V2 reference").at("type"),
    )
    let typed = sql_typed_value_v2(
      values[index],
      kind,
      work.config.limits.at("max_text_bytes"),
    ) catch {
      error => fail("parameter:V2-scalar:" + error.to_string())
    }
    result.push({ "reference": reference, "value": typed })
  }
  Json(result)
}
