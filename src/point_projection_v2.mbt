///|
fn point_projection_build_v2(
  work : PointProjectionWorkV2,
  config : SQLConfigV2,
  source : String,
  original_parameters : Json,
  options : PointProjectionOptionsV2,
) -> Json raise {
  if sql_canonical_v1(config.record) != sql_canonical_v1(options.config.record) {
    fail("invalid:independent-projection-config-conflict")
  }
  work.charge()
  if orm_utf8_size(sql_canonical_v1(original_parameters)) > 1048576 {
    fail("budget:typed-parameter-bytes")
  }
  let semantic = work.parameters(original_parameters)
  let grammar = object_fields(
    sql_candidate_check_v2_json(
      normalize_sql_candidate_v2(
        config,
        source,
        semantic,
        options=work.budget.grammar_options,
      ),
    ),
    "V2 grammar",
  )
  if grammar.at("valid") != Json(true) {
    if grammar.at("status") == Json("invalid") {
      fail("invalid:projection-original-SQL")
    }
    if grammar.at("status") == Json("mismatch") {
      fail("mismatch:projection-original-bindings")
    }
    fail("unsupported:projection-original-grammar")
  }
  let candidate = grammar.at("descriptor")
  let plan = object_fields(candidate, "independent V2 plan")
  let star = point_has_star_v2(work, config, source)
  if star && options.star_columns is None {
    fail("unsupported:projection-star-view-required")
  }
  let table = config.parser_config.tables[0]
  let operation = sql_string_v1(plan.at("operation"))
  let projections = orm_array(plan.at("projections"))
  let original_returning = orm_array(plan.at("returning"))
  let business = if operation == "select" {
    projections
  } else {
    original_returning
  }
  let used = [table.schema, table.name, options.version_column]
  for column in table.columns {
    used.push(column.name)
  }
  for projection in projections + original_returning {
    used.push(
      sql_string_v1(object_fields(projection, "projection").at("outputName")),
    )
  }
  let old_alias = point_fresh_v2(work, "__mtw_v2_old", used)
  let new_alias = point_fresh_v2(work, "__mtw_v2_new", used)
  let target = point_quote_v2(table.schema) + "." + point_quote_v2(table.name)
  let mut read_alias = ""
  let mut sql = ""
  if operation == "insert" {
    let names = orm_array(plan.at("insertColumns")).map(c => {
      point_quote_v2(sql_string_v1(c))
    })
    let rows = orm_array(plan.at("insertRows"))
    let values = orm_array(rows[0]).map(reference => work.scalar(reference))
    sql = "INSERT INTO " +
      target +
      " (" +
      names.join(", ") +
      ") VALUES (" +
      values.join(", ") +
      ")"
  } else {
    if operation == "select" {
      let terms : Array[String] = []
      for projection in projections {
        work.charge()
        let p = object_fields(projection, "projection")
        terms.push(
          point_quote_v2(sql_string_v1(p.at("column"))) +
          " AS " +
          point_quote_v2(sql_string_v1(p.at("outputName"))),
        )
      }
      read_alias = point_fresh_v2(work, "__mtw_v2_read_version", used)
      terms.push(
        point_quote_v2(options.version_column) +
        " AS " +
        point_quote_v2(read_alias),
      )
      sql = "SELECT " + terms.join(", ") + " FROM " + target
    } else if operation == "update" {
      let terms : Array[String] = []
      for assignment in orm_array(plan.at("assignments")) {
        work.charge()
        let a = object_fields(assignment, "assignment")
        terms.push(
          point_quote_v2(sql_string_v1(a.at("column"))) +
          " = " +
          work.scalar(a.at("value")),
        )
      }
      sql = "UPDATE " + target + " SET " + terms.join(", ")
    } else {
      sql = "DELETE FROM " + target
    }
    let predicate = object_fields(
      orm_array(plan.at("predicates"))[0],
      "point predicate",
    )
    sql += " WHERE " + point_quote_v2(sql_string_v1(predicate.at("column")))
    if predicate.at("collation") != Json::null() {
      sql += " COLLATE " +
        point_quote_v2(sql_string_v1(predicate.at("collation")))
    }
    sql += " = " + work.scalar(predicate.at("value"))
  }
  let business_columns : Array[Json] = []
  for index, projection in business {
    work.charge()
    let p = object_fields(projection, "business projection")
    business_columns.push({
      "nativeIndex": Json(index),
      "column": p.at("column"),
      "outputName": p.at("outputName"),
    })
  }
  let business_result : Json = {
    "mode": Json(if business.is_empty() { "no-result" } else { "rows" }),
    "rowImage": Json(
      if operation == "select" {
        "read"
      } else if operation == "delete" {
        "old"
      } else {
        "new"
      },
    ),
    "columns": Json(business_columns),
    "requiresProjectionBeforeDelivery": true,
    "nativeResultDirectlyDeliverable": false,
  }
  let hidden : Array[Json] = []
  let returning_sql : Array[String] = []
  if operation == "select" {
    let columns : Array[Json] = []
    for column in table.columns {
      work.charge()
      let mut native_index = -1
      for index, projection in business {
        if object_fields(projection, "projection").at("column") ==
          Json(column.name) {
          native_index = index
        }
      }
      if native_index < 0 {
        fail("mismatch:independent-full-row-projection")
      }
      columns.push({
        "column": Json(column.name),
        "nativeIndex": Json(native_index),
      })
    }
    hidden.push({
      "image": "read",
      "role": "positive-read-version-candidate",
      "columns": Json(columns),
      "version": {
        "column": Json(options.version_column),
        "type": "int64",
        "nativeIndex": Json(business.length()),
        "outputName": Json(read_alias),
      },
    })
  } else {
    let business_alias = if operation == "delete" {
      old_alias
    } else {
      new_alias
    }
    for projection in business {
      let p = object_fields(projection, "business projection")
      returning_sql.push(
        point_quote_v2(business_alias) +
        "." +
        point_quote_v2(sql_string_v1(p.at("column"))) +
        " AS " +
        point_quote_v2(sql_string_v1(p.at("outputName"))),
      )
    }
    let images = if operation == "update" {
      ["old", "new"]
    } else if operation == "insert" {
      ["new"]
    } else {
      ["old"]
    }
    for image in images {
      let image_alias = if image == "old" { old_alias } else { new_alias }
      let columns : Array[Json] = []
      for column in table.columns {
        work.charge()
        let name = point_fresh_v2(
          work,
          "__mtw_v2_" + image + "_" + columns.length().to_string(),
          used,
        )
        columns.push({
          "column": Json(column.name),
          "nativeIndex": Json(returning_sql.length()),
          "outputName": Json(name),
        })
        returning_sql.push(
          point_quote_v2(image_alias) +
          "." +
          point_quote_v2(column.name) +
          " AS " +
          point_quote_v2(name),
        )
      }
      let name = point_fresh_v2(work, "__mtw_v2_" + image + "_version", used)
      let version : Json = {
        "column": Json(options.version_column),
        "type": "int64",
        "nativeIndex": Json(returning_sql.length()),
        "outputName": Json(name),
      }
      returning_sql.push(
        point_quote_v2(image_alias) +
        "." +
        point_quote_v2(options.version_column) +
        " AS " +
        point_quote_v2(name),
      )
      hidden.push({
        "image": Json(image),
        "role": "write-effect-observation-only",
        "columns": Json(columns),
        "version": version,
      })
    }
    sql += " RETURNING WITH (OLD AS " +
      point_quote_v2(old_alias) +
      ", NEW AS " +
      point_quote_v2(new_alias) +
      ") " +
      returning_sql.join(", ")
  }
  if orm_utf8_size(sql) > options.max_sql_bytes {
    fail("budget:projection-SQL-bytes")
  }
  let bindings : Array[Json] = []
  for binding in orm_array(grammar.at("bindings")) {
    work.charge()
    let b = object_fields(binding, "independent binding")
    bindings.push({
      "reference": b.at("reference"),
      "value": point_bound_atom_v2(b.at("value")),
    })
  }
  let proofs : Array[Json] = [
    "independent-MoonBit-original-SQL-parameters-and-projection-recomputation", "PostgreSQL18-catalog-key-types-business-types-text-comparison-and-column-order",
    "installed-bigint-version-column-nonnull-unique-per-change-and-effective-write-journal",
    "session-schema-server-encoding-permissions-triggers-rules-and-DDL-epoch", "actual-statement-success-native-result-types-command-tag-and-complete-fetch",
    "original-business-row-and-no-result-delivery-projection", "initialized-snapshot-negative-read-sources-and-closed-writer-window",
  ]
  if star {
    proofs.append([
      "preinstallation-physical-columns-and-order-equal-declared-business-star-view",
      "version-column-newly-installed-and-not-an-original-business-column", "postinstallation-only-declared-version-column-added-to-original-table-schema",
      "independent-MoonBit-catalog-installation-and-business-star-projection-recomputation",
    ])
  }
  let document : Json = {
    "format": "moontxnwitness-sql-point-projection/v2",
    "projectionContract": "postgres18-point-crud-same-statement-row-versions/v1",
    "postgresqlMajor": 18,
    "driverFormat": "psycopg-positional-s-with-percent-escaping/v1",
    "originalSql": Json(source),
    "originalSqlSha256": Json(v3_dislock_sha256(source)),
    "candidate": candidate,
    "configSha256": Json(config.digest),
    "originalParameters": v4_json_copy(original_parameters),
    "typedInputBindings": Json(bindings),
    "independentOptions": options.record,
    "optionsSha256": Json(v3_dislock_sha256(sql_canonical_v1(options.record))),
    "projectedSql": Json(sql),
    "projectedSqlSha256": Json(v3_dislock_sha256(sql)),
    "parameterMap": Json(work.mapping),
    "businessResult": business_result,
    "hiddenResults": Json(hidden),
    "businessStarView": if star {
      {
        "contract": "preinstallation-business-schema/v1",
        "columns": Json(options.star_columns.unwrap()),
        "catalogVerified": false,
        "installationVerified": false,
        "equivalentToCurrentNativeStar": false,
      }
    } else {
      Json::null()
    },
    "returningAliases": if operation == "select" {
      Json::null()
    } else {
      { "old": Json(old_alias), "new": Json(new_alias) }
    },
    "nativeColumnCount": Json(
      if operation == "select" {
        business.length() + 1
      } else {
        returning_sql.length()
      },
    ),
    "zeroRowsPolicy": "diagnostic-only-no-absence-source",
    "returningIsPredicateRead": false,
    "writeImagesAreSelectFacts": false,
    "producesDeletionVersion": false,
    "databaseExecuted": false,
    "databaseSyntaxValidated": false,
    "sourceAuthenticated": false,
    "captureFactsProduced": false,
    "sourceFactsProduced": false,
    "completeWindow": false,
    "modelCoverageAccepted": false,
    "moonbitProjectionVerified": false,
    "requiredProofs": Json(proofs),
  }
  if orm_utf8_size(sql_canonical_v1(document)) > options.max_descriptor_bytes {
    fail("budget:projection-descriptor-bytes")
  }
  document
}

///|
pub struct PointProjectionCheckV2 {
  priv record : Json
}

///|
pub fn point_projection_check_v2_json(result : PointProjectionCheckV2) -> Json {
  v4_json_copy(result.record)
}

///|
pub fn verify_point_projection_v2(
  config : SQLConfigV2,
  source : String,
  original_typed_parameters : Json,
  independent_options : PointProjectionOptionsV2,
  supplied_descriptor : Json,
  budget~ : PointProjectionVerificationOptionsV2 = point_projection_verification_options_v2(),
) -> PointProjectionCheckV2 {
  let work : PointProjectionWorkV2 = {
    budget,
    checks: 0,
    atoms: [],
    named: Map([]),
    container: "",
    mapping: [],
  }
  let mut expected : Json = Json::null()
  let mut reason = ""
  let status = try {
    if budget.max_checks < 0 || budget.max_checks > 1000000 {
      fail("invalid:projection-caller-budget")
    }
    work.charge()
    expected = point_projection_build_v2(
      work, config, source, original_typed_parameters, independent_options,
    )
    let actual = sql_canonical_v1(supplied_descriptor)
    if orm_utf8_size(actual) > independent_options.max_descriptor_bytes {
      fail("budget:supplied-projection-bytes")
    }
    if actual == sql_canonical_v1(expected) {
      "matched"
    } else {
      reason = "supplied point projection differs from independent original SQL, typed parameters, config or caller options"
      "mismatch"
    }
  } catch {
    error => {
      reason = error.to_string()
      if reason.contains("budget:") || reason.contains("unsupported:") {
        "unknown"
      } else if reason.contains("invalid:") {
        "invalid"
      } else if reason.contains("mismatch:") {
        "mismatch"
      } else {
        "invalid"
      }
    }
  }
  {
    record: {
      "format": "moontxnwitness-point-projection-verification/v2",
      "semanticContract": "moonbit-independent-postgres18-point-projection/v2",
      "algorithm": "moonbit-point-projection-recomputation-2",
      "status": Json(status),
      "valid": Json(status == "matched"),
      "descriptorRecomputed": Json(expected != Json::null()),
      "expectedDescriptor": expected,
      "originalTypedParameters": v4_json_copy(original_typed_parameters),
      "databaseExecuted": false,
      "databaseSyntaxValidated": false,
      "sourceAuthenticated": false,
      "captureFactsProduced": false,
      "sourceFactsProduced": false,
      "completeWindow": false,
      "modelCoverageAccepted": false,
      "moonbitProjectionVerified": false,
      "commitVerified": false,
      "gaps": [
        Json(
          if reason.is_empty() {
            "descriptor-reproduction-only-execution-catalog-installation-source-window-and-model-unproven"
          } else {
            reason
          },
        ),
      ],
      "execution": {
        "counterContract": "point-projection-step-checks-2",
        "checks": Json(work.checks),
        "maxChecks": Json(budget.max_checks),
        "maxProjectedSqlBytes": Json(independent_options.max_sql_bytes),
        "maxDescriptorBytes": Json(independent_options.max_descriptor_bytes),
      },
      "scope": "independent deterministic construction claim only; no driver, execution, native result, SourceDDL, version provenance, negative-read source or model history acceptance",
    },
  }
}
