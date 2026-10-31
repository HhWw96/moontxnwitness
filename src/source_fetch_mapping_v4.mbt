///|
pub struct SourceFetchMappingV4 {
  priv record : Json
}

///|
pub fn source_fetch_mapping_v4_json(result : SourceFetchMappingV4) -> Json {
  v4_json_copy(result.record)
}

///|
fn source_augmented_config_v4(config : SQLConfigV1) -> SQLConfigV1 raise {
  let raw = source_object_v4(v4_json_copy(config.record))
  for table in orm_array(raw.at("tables")) {
    let t = source_object_v4(table)
    let columns = orm_array(t.at("columns"))
    if columns.length() >= 128 {
      fail("unsupported:source-fetch-column-capacity")
    }
    columns.push({
      "name": "__mtw_source_version",
      "type": "int64",
      "comparison": Json::null(),
    })
  }
  match parse_sql_config_v1(Json::object(raw).stringify()) {
    Ok(value) => value
    Err(reason) => fail("mismatch:source-derived-config:" + reason)
  }
}

///|
pub fn verify_source_fetch_mapping_v4(
  installation : SourceInstallationCheckV4,
  execution : Json,
  native : Json,
  deliveries : Json,
  source_context : Json,
  max_checks~ : Int32 = 1000000,
  max_fetch_checks~ : Int32 = 1000000,
  grammar_options~ : SQLVerificationOptionsV1 = sql_verification_options_v1(),
) -> SourceFetchMappingV4 {
  let work : SourceWorkV4 = { limit: max_checks, checks: 0, }
  let mut reason = ""
  let mut fetch : Json = Json::null()
  let mut native_delivery : Json = Json::null()
  let candidates : Array[Json] = []
  let mut native_delivered = 0
  let status = try {
    if max_checks < 0 ||
      max_checks > 1000000 ||
      max_fetch_checks < 0 ||
      max_fetch_checks > 1000000 {
      fail("invalid:source-fetch-caller-budget")
    }
    work.charge()
    if source_object_v4(installation.record).at("valid") != Json(true) {
      fail("unsupported:source-installation-components-not-verified")
    }
    let context = orm_exact(source_context, [
      "format", "installationLogSha256", "databaseOid",
    ])
    if context.at("format") != Json("caller-asserted-installation-epoch/v1") ||
      context.at("installationLogSha256") != Json(installation.log_digest) {
      fail("mismatch:source-installation-epoch")
    }
    let env = source_object_v4(
      source_object_v4(installation.record).at("environment"),
    )
    source_equal_v4(
      context.at("databaseOid"),
      env.at("databaseOid"),
      "fetch-database-identity",
    )
    let augmented = source_augmented_config_v4(installation.config)
    let candidate_digest = source_object_v4(
      source_object_v4(execution).at("candidate"),
    ).at("configSha256")
    let fetch_config = if candidate_digest == Json(installation.config.digest) {
      installation.config
    } else if candidate_digest == Json(augmented.digest) {
      augmented
    } else {
      fail("mismatch:source-fetch-config-contract")
    }
    // The selected candidate is still independently recomputed against this allowed configuration.
    native_delivery = configured_fetch_check_v1_json(
      verify_configured_fetch_v1(
        fetch_config,
        execution,
        native,
        deliveries,
        max_checks=max_fetch_checks,
        grammar_options~,
      ),
    )
    let f = source_object_v4(native_delivery)
    fetch = source_select_result_constraints_v4(native_delivery, native, work)
    if f.at("valid") != Json(true) {
      if f.at("status") == Json("mismatch") || f.at("status") == Json("invalid") {
        fail("mismatch:source-independent-original-fetch")
      }
      if sql_canonical_v1(native_delivery).contains("budget:") {
        fail("budget:source-independent-original-fetch")
      }
      fail("unsupported:source-independent-original-fetch-incomplete")
    }
    let result_constraints = source_object_v4(fetch)
    if result_constraints.at("valid") != Json(true) {
      let detail = sql_string_v1(result_constraints.at("reason"))
      if result_constraints.at("status") == Json("mismatch") {
        fail("mismatch:source-SELECT-result-constraints:" + detail)
      }
      if detail.contains("budget:") {
        fail("budget:source-SELECT-result-constraints")
      }
      fail("unsupported:source-SELECT-result-constraints:" + detail)
    }
    let descriptor = source_object_v4(
      source_object_v4(f.at("grammar")).at("descriptor"),
    )
    let source_table = source_object_v4(descriptor.at("table"))
    let mut table_index = -1
    for index, table in installation.config.tables {
      if source_table.at("schema") == Json(table.schema) &&
        source_table.at("table") == Json(table.name) {
        table_index = index
      }
    }
    if table_index < 0 ||
      table_index >= installation.installed_catalogs.length() {
      fail("mismatch:source-configured-table-binding")
    }
    let table = installation.config.tables[table_index]
    let catalog = source_object_v4(installation.installed_catalogs[table_index])
    let catalog_columns = orm_array(catalog.at("columns"))
    let fields = orm_array(source_object_v4(native).at("fields"))
    let projections = orm_array(descriptor.at("projections"))
    let mut has_version_projection = false
    for projection in projections {
      if source_object_v4(projection).at("column") ==
        Json("__mtw_source_version") {
        has_version_projection = true
      }
    }
    if !has_version_projection {
      fail("unsupported:read-version-not-delivered-by-original-SELECT")
    }
    let names : Array[String] = []
    let kinds : Array[String] = []
    let oids : Array[Int32] = []
    let formats : Array[Int32] = []
    let mut version_index = -1
    for index, projection in projections {
      work.charge()
      let p = source_object_v4(projection)
      let name = sql_string_v1(p.at("column"))
      let field = source_object_v4(fields[index])
      let mut position = -1
      for at, column in catalog_columns {
        if source_object_v4(column).at("name") == Json(name) {
          position = at
        }
      }
      if position < 0 {
        fail("mismatch:source-projection-catalog-column")
      }
      let physical = source_object_v4(catalog_columns[position])
      if field.at("tableOid") != catalog.at("oid") ||
        field.at("tableColumn") != physical.at("number") ||
        field.at("oid") != physical.at("oid") {
        fail("mismatch:source-native-physical-column")
      }
      names.push(name)
      let mut kind = if name == "__mtw_source_version" { "int64" } else { "" }
      for column in table.columns {
        if column.name == name {
          kind = column.kind
        }
      }
      if kind.is_empty() {
        fail("mismatch:source-projection-config-kind")
      }
      kinds.push(kind)
      oids.push(fetch_number_v1(field.at("oid"), 100000000))
      formats.push(fetch_number_v1(field.at("format"), 1))
      if name == "__mtw_source_version" {
        if version_index >= 0 {
          fail("unsupported:source-duplicate-version-projection")
        }
        version_index = index
      }
    }
    if version_index < 0 {
      fail("unsupported:read-version-not-delivered-by-original-SELECT")
    }
    for column in table.columns {
      if !names.contains(column.name) {
        fail("unsupported:row-projection-incomplete")
      }
    }
    native_delivered = fetch_number_v1(f.at("deliveredRows"), 256)
    let raw_rows = orm_array(source_object_v4(native).at("rows"))
    if native_delivered == 0 {
      fail("unsupported:empty-result-predicate-source-unproven")
    }
    for row_index in 0..<native_delivered {
      work.charge()
      let raw = orm_array(raw_rows[row_index])
      let values : Array[Json] = []
      for index, cell in raw {
        work.charge()
        values.push(
          fetch_cell_v1(cell, kinds[index], oids[index], formats[index]),
        )
      }
      let version_value = source_object_v4(values[version_index]).at("value")
      let version = sql_string_v1(version_value)
      if !sql_digits_v1(version) || version == "0" {
        fail("mismatch:source-delivered-version")
      }
      let initial = match installation.initial_versions.get(version) {
        Some(value) => source_object_v4(value)
        None =>
          fail("unsupported:delivered-version-effective-write-source-missing")
      }
      if initial.at("schema") != Json(table.schema) ||
        initial.at("table") != Json(table.name) ||
        initial.at("tableOid") != catalog.at("oid") {
        fail("mismatch:source-version-relation")
      }
      let row = source_object_v4(initial.at("row"))
      for index, name in names {
        work.charge()
        source_equal_v4(
          values[index],
          sql_typed_value_v1(row.at(name), kinds[index], 65536),
          "delivered-initial-business-value",
        )
      }
      candidates.push({
        "deliveryRow": Json(row_index),
        "schema": Json(table.schema),
        "table": Json(table.name),
        "tableOid": catalog.at("oid"),
        "version": initial.at("version"),
        "sourceKind": "locked-initial-row",
        "initialRequestSeq": initial.at("requestSeq"),
        "initialResultSeq": initial.at("resultSeq"),
      })
    }
    if f.at("completeFetchVerified") != Json(true) {
      fail("unsupported:fetch-not-exhausted")
    }
    "matched-initial-components"
  } catch {
    error => {
      reason = error.to_string()
      if reason.contains("mismatch:") {
        "mismatch"
      } else if reason.contains("invalid:") {
        "invalid"
      } else {
        "unknown"
      }
    }
  }
  {
    record: {
      "format": "moontxnwitness-source-fetch-mapping/v4",
      "semanticContract": "original-select-initial-source-and-returned-constraints/v4-2",
      "algorithm": "independent-native-initial-row-and-predicate-join-2",
      "counterContract": "source-fetch-mapping-step-counters/v4-2",
      "status": Json(status),
      "valid": Json(status == "matched-initial-components"),
      "initialSourceMappingConsistent": Json(
        status == "matched-initial-components",
      ),
      "sourceFactsProduced": false,
      "sourceAuthenticated": false,
      "writerWindowVerified": false,
      "serverInstanceIdentityAuthenticated": false,
      "isolationModelChecked": false,
      "sourceContextScope": "caller supplied installation epoch/database consistency only; does not authenticate server or observer",
      "installationLogSha256": Json(installation.log_digest),
      "businessConfigSha256": Json(installation.config.digest),
      "installation": v4_json_copy(installation.record),
      "nativeDeliveryCheck": native_delivery,
      "fetch": fetch,
      "deliveredRows": Json(native_delivered),
      "initialSourceCandidates": Json(candidates),
      "reason": Json(reason),
      "gaps": [
        "writer-window-not-closed", "privileged-DDL-exclusion-not-proven", "server-instance-and-observer-not-authenticated",
        "no-effective-post-initial-write-source-protocol",
      ],
      "execution": {
        "checks": Json(work.checks),
        "maxChecks": Json(max_checks),
        "maxFetchChecks": Json(max_fetch_checks),
        "limited": Json(reason.contains("budget:")),
      },
    },
  }
}
