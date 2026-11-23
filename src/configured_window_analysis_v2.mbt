///|
fn window_value_v2(
  config : SQLConfigV2,
  raw : Json,
  column : String,
) -> Json raise {
  let kind = projected_column_kind_v2(config, column)
  window_object_v2(
    sql_typed_value_v2(
      raw,
      kind,
      config.parser_config.limits.at("max_text_bytes"),
    ),
  ).at("value")
}

///|
fn window_typed_row_v2(config : SQLConfigV2, raw : Json) -> Json raise {
  let row = window_object_v2(raw)
  let values : Map[String, Json] = Map([])
  for column in config.parser_config.tables[0].columns {
    values[column.name] = sql_typed_value_v2(
      required(row, column.name, "source row"),
      column.kind,
      config.parser_config.limits.at("max_text_bytes"),
    )
  }
  Json(values)
}

///|
fn window_image_v2(config : SQLConfigV2, typed : Json) -> Json raise {
  let fields = window_object_v2(v4_json_copy(typed))
  fields.remove(config.parser_config.tables[0].key)
  { "body": Json(sql_canonical_v1(Json(fields))) }
}

///|
fn window_key_v2(config : SQLConfigV2, typed : Json) -> Json raise {
  window_object_v2(
    window_object_v2(typed).at(config.parser_config.tables[0].key),
  ).at("value")
}

///|
fn window_capture_atom_v2(atom : Json) -> Json raise {
  let fields = window_object_v2(atom)
  let kind = sql_string_v1(fields.at("pythonType"))
  if kind == "int" {
    let text = sql_string_v1(fields.at("decimal"))
    let digits = if text.has_prefix("-") { text[1:].to_owned() } else { text }
    if digits.length() > 16 ||
      (digits.length() == 16 && digits > "9007199254740991") {
      { "captureType": "int", "value": Json(text) }
    } else {
      sql_json_v1(text, 32)
    }
  } else if kind == "uuid.UUID" {
    { "captureType": "UUID", "value": fields.at("value") }
  } else {
    fields.at("value")
  }
}

///|
fn window_capture_cell_v2(typed : Json) -> Json raise {
  let fields = window_object_v2(typed)
  let kind = sql_string_v1(fields.at("type"))
  let value = fields.at("value")
  window_capture_atom_v2(
    if kind == "int64" {
      { "pythonType": "int", "decimal": value }
    } else if kind == "uuid" {
      { "pythonType": "uuid.UUID", "value": value }
    } else {
      {
        "pythonType": Json(if kind == "bool" { "bool" } else { "str" }),
        "value": value,
      }
    },
  )
}

///|
fn window_effect_record_v2(raw : Json) -> Json raise {
  let effect = window_object_v2(v4_json_copy(raw))
  effect.remove("requestSeq")
  effect.remove("resultSeq")
  Json(effect)
}

///|
fn window_catalog_result_v2(
  descriptor : Json,
  native : Json,
  catalog : Json,
  work : SourceWorkV4,
) -> Unit raise {
  let d = window_object_v2(descriptor)
  let names : Map[Int32, String] = Map([])
  for field in orm_array(window_object_v2(d.at("businessResult")).at("columns")) {
    let f = window_object_v2(field)
    names[fetch_number_v1(f.at("nativeIndex"), 52)] = sql_string_v1(
      f.at("column"),
    )
  }
  for image in orm_array(d.at("hiddenResults")) {
    let i = window_object_v2(image)
    for field in orm_array(i.at("columns")) {
      let f = window_object_v2(field)
      names[fetch_number_v1(f.at("nativeIndex"), 52)] = sql_string_v1(
        f.at("column"),
      )
    }
    let v = window_object_v2(i.at("version"))
    names[fetch_number_v1(v.at("nativeIndex"), 52)] = sql_string_v1(
      v.at("column"),
    )
  }
  let c = window_object_v2(catalog)
  let columns : Map[String, Json] = Map([])
  for column in orm_array(c.at("columns")) {
    columns[sql_string_v1(window_object_v2(column).at("name"))] = column
  }
  for index, raw in orm_array(window_object_v2(native).at("fields")) {
    work.charge()
    let field = window_object_v2(raw)
    let column = match names.get(index) {
      Some(name) => window_object_v2(columns.at(name))
      None => fail("mismatch:window-native-field-source-missing")
    }
    source_equal_v4(
      field.at("oid"),
      column.at("oid"),
      "window-field-native-type",
    )
    source_equal_v4(
      field.at("tableOid"),
      c.at("oid"),
      "window-field-native-table",
    )
    source_equal_v4(
      field.at("tableColumn"),
      column.at("number"),
      "window-field-native-column",
    )
  }
}

///|
fn window_snapshot_input_v2(input : Json) -> (String, Json) raise {
  let f = orm_exact(input, ["format", "logText", "receiptText"])
  let format = f.at("format")
  let receipt = sql_json_v1(sql_string_v1(f.at("receiptText")), 2097152)
  if ![
      Json("moontxnwitness-configured-source-snapshot/v2"),
      Json("moontxnwitness-configured-source-snapshot-paged/v1"),
      Json("moontxnwitness-configured-source-snapshot-paged/v2"),
    ].contains(format) ||
    window_object_v2(receipt).at("format") != format {
    fail("invalid:window-snapshot-input-format")
  }
  (sql_string_v1(f.at("logText")), receipt)
}

///|
fn window_charge_component_v2(work : SourceWorkV4, report : Json) -> Unit raise {
  let execution = window_object_v2(window_object_v2(report).at("execution"))
  let count = fetch_number_v1(execution.at("checks"), 1000000)
  if count > work.limit - work.checks {
    fail("budget:window-source-total")
  }
  work.checks += count
}

///|
fn window_analysis_body_v2(
  config : SQLConfigV2,
  policy : Json,
  bundle : Json,
  options : Json,
  original_digest : String,
) -> Json raise {
  let opts = window_object_v2(options)
  known_fields(
    opts,
    [
      "maxSourceChecks", "maxPointChecks", "maxRows", "maxEffects", "maxStates",
      "maxEdgeChecks", "maxModelSourceChecks", "maxSerialOperationChecks", "projectionOptions",
      "pointFootprintOnly",
    ],
    "configured-window-v2 options",
  )
  let source_limit = source_wire_limit_v4(opts, "maxSourceChecks", 1000000)
  let point_limit = source_wire_limit_v4(opts, "maxPointChecks", 1000000)
  let max_rows = wire_v4_int(opts, "maxRows", 4096, 16384)
  let max_effects = wire_v4_int(opts, "maxEffects", 4096, 16384)
  let max_states = wire_v4_int(opts, "maxStates", 100000, 100000)
  let max_edges = source_wire_limit_v4(opts, "maxEdgeChecks", 1000000)
  let model_source_limit = source_wire_limit_v4(
    opts, "maxModelSourceChecks", 1000000,
  )
  let serial_operations = source_wire_limit_v4(
    opts, "maxSerialOperationChecks", 1000000,
  )
  let projection_options = point_projection_options_wire_v2(
    config,
    opts.get_or_default("projectionOptions", {}).stringify(),
  )
  let work : SourceWorkV4 = { limit: source_limit, checks: 0, }
  let input = orm_exact(bundle, [
    "format", "contract", "configText", "policyText", "installationLogText", "installationReceiptText",
    "startInputText", "endInputText", "lifecycleText", "diagnosticTraceText",
  ])
  if input.at("format") != Json("moontxnwitness-configured-window-input/v2") ||
    input.at("contract") !=
    Json("postgres18-configured-point-window-observations/v2") {
    fail("invalid:configured-window-v2-contract")
  }
  source_equal_v4(
    sql_json_v1(sql_string_v1(input.at("configText")), 262144),
    config.record,
    "window-independent-config",
  )
  source_equal_v4(
    sql_json_v1(sql_string_v1(input.at("policyText")), 8192),
    policy,
    "window-independent-policy",
  )
  let install_log = sql_string_v1(input.at("installationLogText"))
  let installation = verify_source_admission_v2(
    config,
    policy,
    install_log,
    sql_json_v1(sql_string_v1(input.at("installationReceiptText")), 2097152),
    max_checks=work.limit - work.checks,
  )
  if window_object_v2(installation.record).at("installationVerified") !=
    Json(true) {
    fail("unsupported:window-installation-unverified")
  }
  window_charge_component_v2(work, installation.record)
  let start_text = sql_string_v1(input.at("startInputText"))
  let end_text = sql_string_v1(input.at("endInputText"))
  let (start_log, start_receipt) = window_snapshot_input_v2(
    sql_json_v1(start_text, 16777216),
  )
  let before = verify_snapshot_admission_v2(
    installation,
    start_log,
    start_receipt,
    max_checks=work.limit - work.checks,
    max_rows~,
    max_effects~,
  )
  if window_object_v2(before.record).at("snapshotVerified") != Json(true) {
    fail("unsupported:window-start-snapshot-unverified")
  }
  window_charge_component_v2(work, before.record)
  let (end_log, end_receipt) = window_snapshot_input_v2(
    sql_json_v1(end_text, 16777216),
  )
  source_equal_v4(
    window_object_v2(start_receipt).at("format"),
    window_object_v2(end_receipt).at("format"),
    "window-snapshot-profile",
  )
  let after = verify_snapshot_admission_v2(
    installation,
    end_log,
    end_receipt,
    max_checks=work.limit - work.checks,
    max_rows~,
    max_effects~,
  )
  if window_object_v2(after.record).at("snapshotVerified") != Json(true) {
    fail("unsupported:window-end-snapshot-unverified")
  }
  window_charge_component_v2(work, after.record)
  source_equal_v4(before.peer, after.peer, "window-same-database-instance")
  let effects : Map[String, Json] = Map([])
  for version, raw in before.effects {
    work.charge()
    let ending = match after.effects.get(version) {
      Some(value) => value
      None => fail("mismatch:window-retained-source-deleted")
    }
    source_equal_v4(
      window_effect_record_v2(raw),
      window_effect_record_v2(ending),
      "window-retained-source-immutable",
    )
  }
  for version, raw in after.effects {
    work.charge()
    if !before.effects.contains(version) {
      if window_object_v2(raw).at("operation") == Json("INITIAL") {
        fail("mismatch:window-new-initial-source")
      }
      effects[version] = raw
    }
  }
  let trace_text = sql_string_v1(input.at("diagnosticTraceText"))
  let lifecycle = window_lifecycle_v2(
    sql_string_v1(input.at("lifecycleText")),
    trace_text,
    v3_dislock_sha256(start_text),
    v3_dislock_sha256(end_text),
    v3_dislock_sha256(install_log),
    config,
    projection_options,
    before.peer,
    work,
  )
  let reports : Map[Int32, Json] = Map([])
  let operations : Map[Int32, Json] = Map([])
  let used_effects : Map[String, Bool] = Map([])
  let written : Map[String, (String, Int32)] = Map([])
  let mut point_checks = 0
  for case in lifecycle.cases {
    work.charge()
    let execution = window_object_v2(case.execution)
    let descriptor = execution.at("descriptor")
    let d = window_object_v2(descriptor)
    let n = window_object_v2(case.native)
    let tx = sql_string_v1(n.at("tx"))
    let statement = fetch_number_v1(n.at("statementSeq"), 100000000)
    let checked = projected_result_check_v2_json(
      verify_projected_result_v2(
        config,
        sql_string_v1(d.at("originalSql")),
        d.at("originalParameters"),
        projection_options,
        descriptor,
        case.native,
        Json(case.deliveries),
        options=projected_result_options_v2(
          max_checks=point_limit - point_checks,
          projection_budget=point_projection_verification_options_v2(
            max_checks=point_limit - point_checks,
          ),
        ),
      ),
    )
    let check = window_object_v2(checked)
    if check.at("valid") != Json(true) ||
      check.at("completeObservationVerified") != Json(true) {
      if check.at("status") == Json("mismatch") ||
        check.at("status") == Json("invalid") {
        fail("mismatch:window-point-result")
      }
      fail("unsupported:window-point-observation-incomplete")
    }
    let result_count = fetch_number_v1(
      window_object_v2(check.at("execution")).at("checks"),
      1000000,
    )
    let projection_count = fetch_number_v1(
      window_object_v2(window_object_v2(check.at("projection")).at("execution")).at(
        "checks",
      ),
      1000000,
    )
    if result_count + projection_count > point_limit - point_checks {
      fail("budget:window-point-total")
    }
    point_checks += result_count + projection_count
    let statement_event = window_object_v2(lifecycle.trace_by_seq.at(statement))
    source_equal_v4(
      statement_event.at("sql"),
      d.at("projectedSql"),
      "window-executed-sql",
    )
    let parameters = orm_array(d.at("parameterMap")).map(value => {
      window_capture_atom_v2(window_object_v2(value).at("value"))
    })
    source_equal_v4(
      statement_event.at("parameters"),
      Json(parameters),
      "window-executed-parameters",
    )
    let expected_raw = orm_array(check.at("decodedNativeRows")).map(row => {
      Json(orm_array(row).map(window_capture_cell_v2))
    })
    let mut raw_position = 0
    let mut raw_batches = 0
    for raw in lifecycle.trace_events {
      work.charge()
      let observed = window_object_v2(raw)
      if observed.at("kind") == Json("rows") &&
        observed.get("statement") == Some(Json(statement)) {
        raw_batches += 1
        source_equal_v4(
          observed.at("tx"),
          Json(tx),
          "window-raw-rows-transaction",
        )
        for row in orm_array(observed.at("rows")) {
          if raw_position >= expected_raw.length() {
            fail("mismatch:window-raw-rows-overrun")
          }
          source_equal_v4(
            row,
            expected_raw[raw_position],
            "window-raw-native-rows",
          )
          raw_position += 1
        }
        if observed.at("complete") == Json(true) &&
          raw_position != expected_raw.length() {
          fail("mismatch:window-raw-rows-premature-end")
        }
      }
    }
    if check.at("completeFetchVerified") == Json(true) &&
      (raw_batches == 0 || raw_position != expected_raw.length()) {
      fail("mismatch:window-raw-fetch-observation-missing")
    }
    let commit = window_object_v2(lifecycle.commits.at(tx))
    let native = window_object_v2(n.at("native"))
    window_catalog_result_v2(
      descriptor,
      n.at("native"),
      installation.catalog,
      work,
    )
    source_equal_v4(
      native.at("backendPid"),
      commit.at("writerPid"),
      "window-business-writer-backend",
    )
    let operation = sql_string_v1(check.at("operation"))
    let images = window_object_v2(check.at("rowImageObservations"))
    let rows = fetch_number_v1(check.at("nativeRows"), 1)
    // A zero-row conditional write is still an observation. Until its write
    // predicate has independent semantics, do not silently drop it from replay.
    if operation != "select" && rows != 1 {
      fail("unsupported:window-zero-row-write")
    }
    let mut effect_id = Json::null()
    if operation != "select" && rows == 1 {
      let image = window_object_v2(
        images.at(if operation == "delete" { "old" } else { "new" }),
      )
      let version = window_object_v2(image.at("version")).at("value")
      let key = window_object_v2(check.at("pointKeyIdentity")).at("value")
      let matches : Array[String] = []
      for id, raw in effects {
        work.charge()
        let effect = window_object_v2(raw)
        if effect.at("operation") == Json(operation.to_upper()) &&
          effect.at("writerXid") == commit.at("writerXid") &&
          effect.at("writerLogin") == commit.at("writerLogin") &&
          effect.at("writerPid") == commit.at("writerPid") &&
          (if operation == "delete" {
            effect.at("baseVersion") == version
          } else {
            Json(id) == version
          }) {
          source_equal_v4(
            window_value_v2(
              config,
              effect.at("rowKey"),
              config.parser_config.tables[0].key,
            ),
            key,
            "window-effect-key",
          )
          matches.push(id)
        }
      }
      if matches.length() != 1 || used_effects.contains(matches[0]) {
        fail("unsupported:window-write-effect-not-unique-or-missing")
      }
      let id = matches[0]
      let effect = window_object_v2(effects.at(id))
      if operation == "update" || operation == "delete" {
        let old = window_object_v2(images.at("old"))
        source_equal_v4(
          effect.at("baseVersion"),
          window_object_v2(old.at("version")).at("value"),
          "window-write-predecessor",
        )
        let parent = match
          after.effects.get(sql_string_v1(effect.at("baseVersion"))) {
          Some(value) => window_object_v2(value)
          None => fail("unsupported:window-predecessor-source-missing")
        }
        source_equal_v4(
          window_typed_row_v2(config, parent.at("rowValues")),
          old.at("values"),
          "window-old-image-source",
        )
      }
      if operation != "delete" {
        source_equal_v4(
          window_typed_row_v2(config, effect.at("rowValues")),
          image.at("values"),
          "window-new-image-source",
        )
        written[id] = (tx, statement)
      }
      used_effects[id] = true
      effect_id = Json(id)
    }
    reports[statement] = checked
    operations[statement] = {
      "operation": Json(operation),
      "tx": Json(tx),
      "effectId": effect_id,
      "caseIndex": Json(reports.length() - 1),
      "callEnd": Json(case.call_end),
      "nativeNote": Json(case.native_note),
      "projectionNote": Json(case.execution_note),
      "callStart": Json(case.call_start),
    }
  }
  if used_effects.length() != effects.length() {
    fail("unsupported:window-uncovered-committed-writes")
  }
  let row_relation = "configured_row"
  let primary_kind = config.parser_config.tables[0].columns[0].kind
  let paged = [
    Json("moontxnwitness-configured-source-snapshot-paged/v1"),
    Json("moontxnwitness-configured-source-snapshot-paged/v2"),
  ].contains(window_object_v2(start_receipt).at("format"))
  let point_only = match opts.get("pointFootprintOnly") {
    None => paged
    Some(True) => true
    Some(False) => {
      if paged {
        fail("unsupported:window-paged-requires-point-footprint")
      }
      false
    }
    _ => fail("invalid:window-point-footprint-option")
  }
  let used_keys : Map[String, Bool] = Map([])
  if point_only {
    // Complete source admission still covers every observed row and effect.
    // Only verified point keys participate in the paged window's model input.
    for _, report in reports {
      work.charge()
      let checked = window_object_v2(report)
      let identity = window_object_v2(checked.at("pointKeyIdentity"))
      used_keys[sql_canonical_v1(identity.at("value"))] = true
    }
  }
  let initial : Array[Json] = []
  for version, raw in before.rows {
    work.charge()
    let row = window_typed_row_v2(config, window_object_v2(raw).at("row"))
    let key = window_key_v2(config, row)
    if point_only && !used_keys.contains(sql_canonical_v1(key)) {
      continue
    }
    initial.push({
      "key": key,
      "version": Json("row:" + version),
      "values": window_image_v2(config, row),
    })
  }
  let events : Array[Json] = [
    {
      "kind": "snapshot",
      "consistent": true,
      "initial": Json(Map([(row_relation, Json(initial))])),
    },
  ]
  let provenance : Array[Json] = []
  for raw in lifecycle.trace_events {
    work.charge()
    let e = window_object_v2(raw)
    let kind = sql_string_v1(e.at("kind"))
    if kind == "snapshot" || kind == "rows" {
      continue
    }
    let tx = sql_string_v1(e.at("tx"))
    if kind == "begin" {
      events.push({
        "kind": "begin",
        "tx": Json(tx),
        "connection": e.at("connection"),
      })
    } else if kind == "commit_request" || kind == "commit_ok" {
      events.push({ "kind": Json(kind), "tx": Json(tx) })
    } else {
      let seq = fetch_number_v1(e.at("seq"), 100000000)
      let op = window_object_v2(operations.at(seq))
      let checked = window_object_v2(reports.at(seq))
      let images = window_object_v2(checked.at("rowImageObservations"))
      let operation = sql_string_v1(op.at("operation"))
      let key = window_object_v2(checked.at("pointKeyIdentity")).at("value")
      if operation == "select" {
        let rows : Array[Json] = []
        if checked.at("nativeRows") == Json(1) {
          let image = window_object_v2(images.at("read"))
          let version = sql_string_v1(
            window_object_v2(image.at("version")).at("value"),
          )
          if before.rows.contains(version) {
            source_equal_v4(
              window_typed_row_v2(
                config,
                window_object_v2(before.rows.at(version)).at("row"),
              ),
              image.at("values"),
              "window-initial-read-source",
            )
          } else {
            let (writer, write_seq) = match written.get(version) {
              Some(value) => value
              None => fail("unsupported:window-read-source-missing")
            }
            if writer == tx {
              if write_seq >= seq {
                fail("mismatch:window-future-own-write")
              }
            } else if fetch_number_v1(
                window_object_v2(lifecycle.commits.at(writer)).at(
                  "commitStartSeq",
                ),
                65536,
              ) >=
              fetch_number_v1(op.at("callEnd"), 65536) {
              fail("mismatch:window-future-external-write")
            }
            source_equal_v4(
              window_typed_row_v2(
                config,
                window_object_v2(effects.at(version)).at("rowValues"),
              ),
              image.at("values"),
              "window-committed-read-source",
            )
          }
          rows.push({
            "key": key,
            "version": Json("row:" + version),
            "values": window_image_v2(config, image.at("values")),
          })
        }
        events.push({
          "kind": "row_read",
          "tx": Json(tx),
          "relation": Json(row_relation),
          "predicate": [{ "column": "pk", "op": "eq", "value": key }],
          "rows": Json(rows),
          "complete": true,
        })
      } else if op.at("effectId") != Json::null() {
        let id = sql_string_v1(op.at("effectId"))
        let effect = window_object_v2(effects.at(id))
        let image = if operation == "delete" {
          Json::null()
        } else {
          window_image_v2(
            config,
            window_object_v2(images.at("new")).at("values"),
          )
        }
        events.push({
          "kind": "row_write",
          "tx": Json(tx),
          "relation": Json(row_relation),
          "key": key,
          "action": Json(operation),
          "version": Json(
            (if operation == "delete" { "delete:" } else { "row:" }) + id,
          ),
          "predecessor": match effect.at("baseVersion") {
            Null => Json::null()
            value => Json("row:" + sql_string_v1(value))
          },
          "values": image,
        })
      }
      provenance.push({
        "historySeq": Json(events.length()),
        "originalStatementSeq": Json(seq),
        "projectionNoteSeq": op.at("projectionNote"),
        "callStartSeq": op.at("callStart"),
        "nativeNoteSeq": op.at("nativeNote"),
        "effectIdentity": op.at("effectId"),
        "versionIdentityKind": Json(
          if operation == "delete" {
            "ledger-deletion-event"
          } else {
            "installed-row-version"
          },
        ),
      })
    }
  }
  let history : Json = {
    "traceSchema": 3,
    "dataModel": "relation-set-v1",
    "clockDomain": "configured-window-program-order-v2",
    "relationSchema": Json(
      Map([
        (
          row_relation,
          (
            {
              "primaryKey": "pk",
              "columns": {
                "pk": Json(
                  if primary_kind == "uuid" {
                    "text"
                  } else {
                    primary_kind
                  },
                ),
                "body": "text",
              },
            } : Json),
        ),
      ]),
    ),
    "scope": {
      "exclusiveWriters": true,
      "completeSnapshotTables": [Json(row_relation)],
    },
    "gaps": [],
    "events": Json(
      events.mapi((i, event) => {
        let f = window_object_v2(event)
        f["seq"] = Json(i + 1)
        f["time"] = Json(i)
        Json(f)
      }),
    ),
  }
  let parsed = wire_v4_history(history.stringify())
  let model = model_classification_v4_json(
    classify_models_v4(
      model_facts_v4(parsed).unwrap(),
      model_options_v4(
        models=[ElleSerializable],
        relation_profile=ModelRelationAtomicRows,
        max_source_checks=model_source_limit,
        max_states~,
        max_edge_checks=max_edges,
      ).unwrap(),
    ),
  )
  let category = relation_classification_v4_json(
    classify_relation_point_v4(
      parsed,
      categories=["G2-item"],
      max_graph_checks=model_source_limit,
      max_states~,
      max_edge_checks=max_edges,
    ),
  )
  // A complete serial replay is a separate positive certificate. In particular,
  // it can resolve a point absence whose graph sources remain ambiguous. Keep
  // the graph result unchanged, including its unknown checks and reasons.
  let serial = analysis_v4_json(
    analyze_v4(
      parsed,
      options=analysis_options_v4(
        max_states~,
        max_operation_checks=serial_operations,
      ),
    ),
  )
  let serial_judgment = window_object_v2(
    window_object_v2(serial).at("judgment"),
  )
  let serial_proved = serial_judgment.at("status") == Json("consistent") &&
    window_object_v2(serial_judgment.at("evidence")).at("kind") ==
    Json("serial-relation-replay")
  let graph_status = window_object_v2(model).at("status")
  if graph_status == Json("refuted") && serial_proved {
    fail("mismatch:window-contradictory-model-evidence")
  }
  let decision : Json = if graph_status == Json("refuted") {
    { "status": graph_status, "basis": "relation-atomic-row-graph" }
  } else if serial_proved {
    {
      "status": "checked-compatible",
      "basis": "complete-serial-relation-replay",
    }
  } else {
    { "status": graph_status, "basis": "relation-atomic-row-graph" }
  }
  {
    "format": "moontxnwitness-configured-window-analysis/v2",
    "semanticContract": Json(
      if point_only {
        "postgres18-source-bound-point-crud-touched-keys/v1"
      } else {
        "postgres18-source-bound-point-crud-row-slots/v2"
      },
    ),
    "status": window_object_v2(decision).at("status"),
    "coverageComplete": true,
    "sourceMappingVerified": true,
    "writerWindowVerified": true,
    "sourceAuthenticated": false,
    "bundleSha256": Json(original_digest),
    "configSha256": Json(config.digest),
    "optionsSha256": Json(v3_dislock_sha256(sql_canonical_v1(options))),
    "history": history,
    "operationSources": Json(provenance),
    "model": model,
    "modelDecision": decision,
    "serialReplay": serial,
    "itemCategory": category,
    "installation": installation.record,
    "startSnapshot": before.record,
    "endSnapshot": after.record,
    "execution": {
      "transactions": Json(lifecycle.begin_by_tx.length()),
      "businessStatements": Json(lifecycle.cases.length()),
      "sourceChecks": Json(work.checks),
      "maxSourceChecks": Json(source_limit),
      "pointChecks": Json(point_checks),
      "maxPointChecks": Json(point_limit),
    },
    "scope": "supplied original observations in one explicitly installed, complete PostgreSQL point window; UUIDs retain canonical equality identity and full typed business rows use opaque JSON bodies",
  }
}

///|
pub fn analyze_configured_window_v2_json(
  config_text : String,
  policy_text : String,
  bundle_text : String,
  options_text : String,
) -> String {
  try {
    let config = match parse_sql_config_v2(config_text) {
      Ok(value) => value
      Err(reason) => fail(reason)
    }
    let report = window_analysis_body_v2(
      config,
      sql_json_v1(policy_text, 8192),
      sql_json_v1(bundle_text, 33554432),
      sql_json_v1(options_text, 262144),
      v3_dislock_sha256(bundle_text),
    ).stringify()
    if orm_utf8_size(report) > 33554432 {
      fail("budget:window-report-bytes")
    }
    report
  } catch {
    error =>
      (
        {
          "format": "moontxnwitness-configured-window-analysis/v2",
          "status": Json(
            if error.to_string().contains("budget:") ||
              error.to_string().contains("unsupported:") {
              "unknown"
            } else {
              "invalid"
            },
          ),
          "coverageComplete": false,
          "sourceMappingVerified": false,
          "writerWindowVerified": false,
          "sourceAuthenticated": false,
          "reason": Json(error.to_string()),
        } : Json).stringify()
  }
}

///|
pub fn verify_configured_window_v2_json(
  config_text : String,
  policy_text : String,
  bundle_text : String,
  report_text : String,
  options_text : String,
) -> String {
  try {
    let actual = sql_json_v1(
      analyze_configured_window_v2_json(
        config_text, policy_text, bundle_text, options_text,
      ),
      33554432,
    )
    let expected = sql_json_v1(report_text, 33554432)
    let equal = sql_canonical_v1(actual) == sql_canonical_v1(expected)
    (
      {
        "format": "moontxnwitness-configured-window-verification/v2",
        "valid": Json(
          equal && window_object_v2(actual).at("coverageComplete") == Json(true),
        ),
        "reportMatches": Json(equal),
        "recomputed": actual,
      } : Json).stringify()
  } catch {
    error =>
      (
        {
          "format": "moontxnwitness-configured-window-verification/v2",
          "valid": false,
          "reason": Json(error.to_string()),
        } : Json).stringify()
  }
}
