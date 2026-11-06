///|
priv struct PointWindowCallsV4 {
  reads : Map[Int32, (Int32, Int32, Json)]
  commits : Map[String, Json]
}

///|
fn point_window_calls_v4(
  lifecycle : String,
  start_hash : String,
  end_hash : String,
  work : SourceWorkV4,
) -> PointWindowCallsV4 raise {
  // The writer verifier has already checked sequence, seal and clock domain.
  let active : Map[String, Json] = Map([])
  let opened : Map[String, Bool] = Map([])
  let reads : Map[Int32, (Int32, Int32, Json)] = Map([])
  let commits : Map[String, Json] = Map([])
  let mut started = false
  let mut ended = false
  for line in lifecycle.split("\n") {
    if line.is_empty() {
      continue
    }
    work.charge()
    let raw = sql_json_v1(line.to_owned(), 524288)
    let event = source_object_v4(raw)
    let seq = fetch_number_v1(event.at("seq"), 65536)
    match sql_string_v1(event.at("kind")) {
      "header" | "seal" => ()
      "configured-point-start" | "configured-point-end" as boundary => {
        let frame = orm_exact(
          sql_json_v1(sql_string_v1(event.at("frameText")), 61440),
          ["sha256"],
        )
        if boundary == "configured-point-start" {
          if started || seq != 2 || frame.at("sha256") != Json(start_hash) {
            fail("mismatch:point-start-boundary")
          }
          started = true
        } else {
          if !started ||
            ended ||
            !active.is_empty() ||
            !opened.is_empty() ||
            frame.at("sha256") != Json(end_hash) {
            fail("mismatch:point-end-boundary")
          }
          ended = true
        }
      }
      "instrumentation-detached" =>
        if !ended {
          fail("unsupported:point-premature-detach")
        }
      kind => {
        if !started || ended {
          fail("unsupported:point-event-outside-window")
        }
        match kind {
          "connect" => {
            let connection = sql_string_v1(event.at("connection"))
            if opened.contains(connection) ||
              event.at("asynchronous") != Json(false) {
              fail("unsupported:point-connection")
            }
            opened[connection] = true
          }
          "connection-close" => {
            let connection = sql_string_v1(event.at("connection"))
            if !opened.contains(connection) || active.contains(connection) {
              fail("unsupported:point-connection-close")
            }
            opened.remove(connection)
          }
          "call-start" | "call-end" => {
            let connection = sql_string_v1(event.at("connection"))
            let call_method = sql_string_v1(event.at("method"))
            if !opened.contains(connection) ||
              !["execute", "commit"].contains(call_method) {
              fail("unsupported:point-call")
            }
            if kind == "call-start" {
              if active.contains(connection) {
                fail("unsupported:point-overlapping-connection-calls")
              }
              active[connection] = raw
            } else {
              let start = match active.get(connection) {
                Some(call) => source_object_v4(call)
                None => fail("mismatch:point-call-without-start")
              }
              for key in ["callId", "method", "tx"] {
                if event.at(key) != start.at(key) {
                  fail("mismatch:point-call-identity")
                }
              }
              active.remove(connection)
              if event.at("succeeded") != Json(true) {
                fail("unsupported:point-failed-call")
              }
              if call_method == "execute" {
                let statement = fetch_number_v1(
                  event.at("statementSeq"),
                  100000000,
                )
                if reads.contains(statement) || reads.length() >= 128 {
                  fail("unsupported:point-statement-count")
                }
                reads[statement] = (
                  fetch_number_v1(start.at("seq"), 65536),
                  seq,
                  raw,
                )
              } else {
                let tx = sql_string_v1(event.at("tx"))
                if commits.contains(tx) {
                  fail("mismatch:point-duplicate-commit")
                }
                commits[tx] = raw
              }
            }
          }
          "configured-execution"
          | "configured-native-result"
          | "configured-delivery"
          | "configured-writer-checkpoint"
          | "commit-response" => ()
          _ => fail("unsupported:point-uncovered-lifecycle-event")
        }
      }
    }
  }
  if !ended {
    fail("unsupported:point-window-markers-missing")
  }
  { reads, commits, }
}

///|
fn point_window_raw_row_v4(
  row : Json,
  table : SQLTableV1,
) -> Map[String, Json] raise {
  let values = source_object_v4(row)
  let typed : Map[String, Json] = Map([])
  for column in table.columns {
    let value = required(values, column.name, "point-source-row")
    if value == Json::null() {
      fail("unsupported:point-null")
    }
    typed[column.name] = source_object_v4(
      sql_typed_value_v1(value, column.kind, 65536),
    ).at("value")
  }
  typed
}

///|
priv struct PointWindowOperationV4 {
  statement : Int32
  tx : String
  key : Json
  version : String
  values : Map[String, Json]
  update : Bool
  assignments : Map[String, Json]
  native_note : Int32
}

///|
fn point_window_operation_v4(
  result : ConfiguredSessionCaseV4,
  config : SQLConfigV1,
  catalog : Map[String, Json],
  work : SourceWorkV4,
) -> PointWindowOperationV4 raise {
  let execution = source_object_v4(result.execution)
  let statement = fetch_number_v1(execution.at("statementSeq"), 100000000)
  let tx = sql_string_v1(execution.at("tx"))
  let original_candidate = source_object_v4(execution.at("candidate"))
  let claimed = source_object_v4(original_candidate.at("descriptor"))
  let update = claimed.at("operation") == Json("update")
  let native = source_object_v4(result.native)
  let grammar = if update {
    let checked = source_object_v4(
      sql_candidate_check_v1_json(
        verify_sql_candidate_v1(
          config,
          sql_string_v1(execution.at("sql")),
          execution.at("parameters"),
          execution.at("candidate"),
        ),
      ),
    )
    if checked.at("status") == Json("unknown") {
      fail("unsupported:point-update-grammar")
    }
    if checked.at("valid") != Json(true) {
      fail("mismatch:point-update-grammar")
    }
    let expected = source_object_v4(checked.at("expectedCandidate"))
    for field in ["sqlSha256", "parametersSha256"] {
      if native.at(field) != expected.at(field) {
        fail("mismatch:point-update-digest")
      }
    }
    if execution.at("format") != Json("moontxnwitness-configured-execution/v1") ||
      native.at("format") != Json("moontxnwitness-native-result/v1") ||
      native.at("status") != Json(2) ||
      execution.at("sourceFactsProduced") != Json(false) ||
      native.at("sourceFactsProduced") != Json(false) {
      fail("mismatch:point-update-frame")
    }
    checked
  } else {
    let check = source_object_v4(
      configured_fetch_check_v1_json(
        verify_configured_fetch_v1(
          config,
          result.execution,
          result.native,
          Json(result.deliveries),
          max_checks=work.limit - work.checks,
        ),
      ),
    )
    work.checks += fetch_number_v1(
      source_object_v4(check.at("execution")).at("checks"),
      work.limit - work.checks,
    )
    if check.at("completeFetchVerified") != Json(true) {
      match check.at("status") {
        String("mismatch") | String("invalid") =>
          fail("mismatch:point-delivery")
        _ => fail("unsupported:point-delivery-incomplete")
      }
    }
    source_object_v4(check.at("grammar"))
  }
  let descriptor = source_object_v4(grammar.at("descriptor"))
  let bindings = orm_array(grammar.at("bindings"))
  let table = config.tables[0]
  let terms = orm_array(descriptor.at("predicates"))
  if terms.length() != 1 ||
    descriptor.at("schemaResolution") != Json("explicit-schema") {
    fail("unsupported:point-explicit-table-and-one-predicate")
  }
  let term = source_object_v4(terms[0])
  if term.at("column") != Json(table.key) || term.at("operator") != Json("eq") {
    fail("unsupported:point-key-equality")
  }
  let key = source_select_expected_v4(term.at("value"), bindings, work)
  let physical = orm_array(catalog.at("columns"))
  let fields = orm_array(native.at("fields"))
  let rows = orm_array(native.at("rows"))
  if rows.length() != 1 {
    fail("unsupported:point-result-cardinality")
  }
  let cells = orm_array(rows[0])
  let projections = orm_array(
    descriptor.at(if update { "returning" } else { "projections" }),
  )
  if fields.length() != projections.length() ||
    cells.length() != fields.length() {
    fail("mismatch:point-native-arity")
  }
  let values : Map[String, Json] = Map([])
  let decoded : Array[Json] = []
  for index, projection in projections {
    work.charge()
    let projected = source_object_v4(projection)
    let name = projected.at("column")
    let col = match table.columns.iter().find_first(c => Json(c.name) == name) {
      Some(column) => column
      None => fail("mismatch:point-projection-column")
    }
    let field = source_object_v4(fields[index])
    let original = match
      physical
      .iter()
      .find_first(c => object_fields_unchecked_v3(c).get("name") == Some(name)) {
      Some(column) => source_object_v4(column)
      None => fail("mismatch:point-catalog-column")
    }
    if field.at("name") != projected.at("outputName") ||
      field.at("tableOid") != catalog.at("oid") ||
      field.at("tableColumn") != original.at("number") ||
      field.at("oid") != original.at("oid") ||
      values.contains(col.name) {
      fail("mismatch:point-physical-column")
    }
    if cells[index] == Json::null() {
      fail("unsupported:point-null")
    }
    let value = fetch_cell_v1(
      cells[index],
      col.kind,
      fetch_number_v1(field.at("oid"), 100000000),
      fetch_number_v1(field.at("format"), 1),
    )
    decoded.push(value)
    values[col.name] = source_object_v4(value).at("value")
  }
  if update {
    let mut delivered = 0
    let mut complete = false
    for raw in result.deliveries {
      work.charge()
      let batch = source_object_v4(raw)
      let rows = orm_array(batch.at("rows"))
      let fetch = sql_string_v1(batch.at("method"))
      if batch.at("format") != Json("moontxnwitness-actual-delivery/v1") ||
        batch.at("sourceFactsProduced") != Json(false) ||
        batch.at("start") != Json(delivered) ||
        !["fetchone", "fetchmany", "fetchall"].contains(fetch) ||
        (
          !rows.is_empty() &&
          (
            complete ||
            delivered != 0 ||
            rows.length() != 1 ||
            rows[0] != Json(decoded)
          )
        ) {
        fail("mismatch:point-update-delivery")
      }
      delivered += rows.length()
      match batch.at("complete") {
        True => {
          if delivered != 1 {
            fail("mismatch:point-update-exhaustion")
          }
          complete = true
        }
        False =>
          if fetch == "fetchall" {
            fail("mismatch:point-update-fetchall")
          }
        _ => fail("mismatch:point-update-delivery-flag")
      }
    }
    if !complete {
      fail("unsupported:point-update-delivery-incomplete")
    }
  }
  if values.length() != table.columns.length() ||
    !values.contains("__mtw_source_version") {
    fail("unsupported:point-full-row-and-version")
  }
  let version = effects_decimal_v4(
    values.at("__mtw_source_version"),
    "9223372036854775807",
  )
  values.remove("__mtw_source_version")
  let key_value = source_object_v4(key).at("value")
  if values.at(table.key) != key_value {
    fail("mismatch:point-returned-key")
  }
  let assignments : Map[String, Json] = Map([])
  for assignment in orm_array(descriptor.at("assignments")) {
    work.charge()
    let field = source_object_v4(assignment)
    let name = sql_string_v1(field.at("column"))
    if name == "__mtw_source_version" {
      fail("unsupported:point-version-assignment")
    }
    assignments[name] = source_object_v4(
      source_select_expected_v4(field.at("value"), bindings, work),
    ).at("value")
  }
  {
    statement,
    tx,
    key: key_value,
    version,
    values,
    update,
    assignments,
    native_note: result.native_note,
  }
}

///|
fn point_window_image_v4(
  values : Map[String, Json],
  names : Map[String, String],
  primary : String,
) -> Json {
  let image : Map[String, Json] = Map([])
  for name, wire_name in names {
    if name != primary {
      image[wire_name] = values.at(name)
    }
  }
  Json(image)
}

///|
fn point_window_analyze_v4(
  before : String,
  after : String,
  session_text : String,
  options : String,
) -> Json raise {
  let limits = source_object_v4(sql_json_v1(options, 8192))
  known_fields(
    limits,
    [
      "maxRows", "maxChecks", "maxInstallationChecks", "maxBindingChecks", "maxPointChecks",
      "maxSourceChecks", "maxStates", "maxEdgeChecks",
    ],
    "point-window-options",
  )
  let work : SourceWorkV4 = {
    limit: source_wire_limit_v4(limits, "maxPointChecks", 1000000),
    checks: 0,
  }
  let max_source = source_wire_limit_v4(limits, "maxSourceChecks", 1000000)
  let max_states = wire_v4_int(limits, "maxStates", 100000, 100000)
  let max_edges = source_wire_limit_v4(limits, "maxEdgeChecks", 1000000)
  for key in ["maxPointChecks", "maxSourceChecks", "maxStates", "maxEdgeChecks"] {
    limits.remove(key)
  }
  let source : ConfiguredPointSourceV4 = {
    commits: Map([]),
    installation: None,
    effects: None,
  }
  let window = source_object_v4(
    configured_writer_window_v4(
      before,
      after,
      session_text,
      Json(limits).stringify(),
      point_source=source,
    ),
  )
  if window.at("retainedEffects") != Json(0) ||
    window.at("ledgerDeltaCovered") != Json(true) {
    fail("unsupported:point-window-not-closed")
  }
  let installation = source.installation.unwrap()
  let effects = source.effects.unwrap()
  if installation.config.tables.length() != 1 {
    fail("unsupported:point-single-table")
  }
  let table = installation.config.tables[0]
  let catalog = source_object_v4(installation.installed_catalogs[0])
  let config = source_augmented_config_v4(installation.config)
  let session = source_object_v4(sql_json_v1(session_text, 33554432))
  let lifecycle = sql_string_v1(session.at("lifecycleText"))
  let trace = sql_string_v1(session.at("diagnosticTraceText"))
  let start_hash = v3_dislock_sha256(before)
  let end_hash = v3_dislock_sha256(after)
  let calls = point_window_calls_v4(lifecycle, start_hash, end_hash, work)
  let session_options = configured_session_options_v4(max_results=128).unwrap()
  let (cases, pending) = configured_session_records_v4(
    lifecycle, session_options, work,
  )
  let _ = configured_session_trace_v4(trace, cases, work)
  if !pending.is_empty() ||
    cases.length() != calls.reads.length() ||
    cases.is_empty() ||
    source.commits.length() != calls.commits.length() ||
    source.commits.length() > 32 {
    fail("unsupported:point-incomplete-operations-or-commits")
  }
  let operations : Map[Int32, PointWindowOperationV4] = Map([])
  let written : Map[String, (String, Int32)] = Map([])
  for result in cases {
    work.charge()
    let op = point_window_operation_v4(result, config, catalog, work)
    let (_, call_end, call) = match calls.reads.get(op.statement) {
      Some(value) => value
      None => fail("mismatch:point-execution-call")
    }
    let commit = match source.commits.get(op.tx) {
      Some(value) => source_object_v4(value)
      None => fail("unsupported:point-unconfirmed-commit")
    }
    let client_call = source_object_v4(call)
    if client_call.at("tx") != Json(op.tx) ||
      client_call.at("connection") != commit.at("connection") ||
      result.execution_note <= call_end ||
      result.native_note >= fetch_number_v1(commit.at("checkpointSeq"), 65536) ||
      operations.contains(op.statement) {
      fail("mismatch:point-operation-lifecycle")
    }
    if op.update {
      let effect = match effects.get(op.version) {
        Some(value) => source_object_v4(value)
        None => fail("unsupported:point-write-effect-missing")
      }
      if written.contains(op.version) ||
        effect.at("operation") != Json("UPDATE") ||
        effect.at("relationOid") != catalog.at("oid") ||
        effect.at("writerXid") != commit.at("writerXid") {
        fail("mismatch:point-write-identity")
      }
      written[op.version] = (op.tx, call_end)
    }
    operations[op.statement] = op
  }
  if written.length() != effects.length() {
    fail("unsupported:point-uncovered-write")
  }
  let trace_document = source_object_v4(sql_json_v1(trace, 8388608))
  for gap in orm_array(trace_document.at("gaps")) {
    work.charge()
    let code = source_object_v4(gap).at("code")
    if ![
        "initialization_unproven", "diagnostic_instrumentation_only", "configured_source_window_unproven",
        "read_version_unproven", "source_unsealed", "diagnostic_only",
      ].any(item => code == Json(item)) {
      fail("unsupported:point-original-capture-gap")
    }
  }
  let relation = "configured_row"
  let columns : Map[String, Json] = Map([])
  let names : Map[String, String] = Map([])
  let original_names : Map[String, Json] = Map([])
  for index, column in table.columns {
    let wire_name = if column.name == table.key {
      "pk"
    } else {
      "c" + index.to_string()
    }
    names[column.name] = wire_name
    original_names[wire_name] = Json(column.name)
    columns[wire_name] = Json(column.kind)
  }
  let references : Map[String, Json] = Map([])
  for raw in orm_array(window.at("matchedEffects")) {
    let effect = source_object_v4(source_object_v4(raw).at("effect"))
    references[sql_string_v1(effect.at("version"))] = {
      "kind": "end-effect",
      "requestSeq": effect.at("requestSeq"),
      "resultSeq": effect.at("resultSeq"),
      "rowIndex": effect.at("rowIndex"),
    }
  }
  let initial : Array[Json] = []
  let baseline : Map[String, Map[String, Json]] = Map([])
  for version, raw in installation.initial_versions {
    work.charge()
    let source_row = source_object_v4(raw)
    let values = point_window_raw_row_v4(source_row.at("row"), table)
    baseline[version] = values
    references[version] = {
      "kind": "installed-initial",
      "requestSeq": source_row.at("requestSeq"),
      "resultSeq": source_row.at("resultSeq"),
    }
    let key = values.at(table.key)
    initial.push({
      "key": key,
      "version": Json(version),
      "values": point_window_image_v4(values, names, table.key),
    })
  }
  let events : Array[Json] = [
    {
      "kind": "snapshot",
      "consistent": true,
      "initial": Json(Map([(relation, Json(initial))])),
    },
  ]
  let provenance : Array[Json] = []
  let seen_read : Map[(String, String), String] = Map([])
  let seen_write : Map[(String, String), Bool] = Map([])
  let begun : Map[String, Bool] = Map([])
  let committed : Map[String, Bool] = Map([])
  let mut checked_statements = 0
  for raw in orm_array(trace_document.at("events")) {
    work.charge()
    let e = source_object_v4(raw)
    let kind = sql_string_v1(e.at("kind"))
    let original_seq = fetch_number_v1(e.at("seq"), 100000000)
    if kind == "rows" || kind == "snapshot" {
      continue
    }
    if !["begin", "statement", "commit_request", "commit_ok"].contains(kind) {
      fail("unsupported:point-original-transaction-event")
    }
    let tx = sql_string_v1(e.at("tx"))
    let commit = match source.commits.get(tx) {
      Some(value) => source_object_v4(value)
      None => fail("unsupported:point-original-transaction-unconfirmed")
    }
    let projected : Json = match kind {
      "begin" => {
        if begun.contains(tx) || e.at("connection") != commit.at("connection") {
          fail("mismatch:point-begin")
        }
        begun[tx] = true
        {
          "kind": "begin",
          "tx": Json(tx),
          "connection": commit.at("connection"),
        }
      }
      "commit_request" | "commit_ok" => {
        if !begun.contains(tx) || committed.contains(tx) {
          fail("mismatch:point-commit-order")
        }
        if kind == "commit_ok" {
          committed[tx] = true
        }
        { "kind": Json(kind), "tx": Json(tx) }
      }
      _ => {
        let op = match operations.get(original_seq) {
          Some(op) => op
          None => fail("unsupported:point-uncovered-statement")
        }
        if op.tx != tx ||
          !begun.contains(tx) ||
          original_seq >=
          fetch_number_v1(commit.at("traceCommitRequestSeq"), 100000000) {
          fail("mismatch:point-statement-order")
        }
        checked_statements += 1
        let slot = (tx, op.key.stringify())
        let version = op.version
        let image = point_window_image_v4(op.values, names, table.key)
        let event : Json = if op.update {
          let effect = source_object_v4(effects.at(version))
          let predecessor = sql_string_v1(effect.at("baseVersion"))
          if seen_write.contains(slot) ||
            seen_read.get(slot) != Some(predecessor) {
            fail("unsupported:point-update-needs-predecessor-read")
          }
          let base = match baseline.get(predecessor) {
            Some(row) => row
            None =>
              point_window_raw_row_v4(
                source_object_v4(effects.at(predecessor)).at("rowValues"),
                table,
              )
          }
          let expected = point_window_raw_row_v4(effect.at("rowValues"), table)
          if expected.at(table.key) != op.key {
            fail("mismatch:point-effect-key")
          }
          for column in table.columns {
            work.charge()
            let name = column.name
            if expected.at(name) != op.values.at(name) ||
              expected.at(name) !=
              op.assignments.get_or_default(name, base.at(name)) {
              fail("mismatch:point-effect-values")
            }
          }
          seen_write[slot] = true
          {
            "kind": "row_write",
            "tx": Json(tx),
            "relation": Json(relation),
            "key": op.key,
            "action": "update",
            "version": Json(version),
            "predecessor": Json(predecessor),
            "values": image,
          }
        } else {
          let expected = match baseline.get(version) {
            Some(row) => row
            None => {
              let (writer, update_end) = match written.get(version) {
                Some(value) => value
                None => fail("unsupported:point-read-source-missing")
              }
              let (_, read_end, _) = calls.reads.at(original_seq)
              if writer == tx {
                if !seen_write.contains(slot) || update_end >= read_end {
                  fail("mismatch:point-future-own-write")
                }
              } else {
                let writer_commit = source_object_v4(source.commits.at(writer))
                if fetch_number_v1(writer_commit.at("commitStartSeq"), 65536) >=
                  read_end {
                  fail("mismatch:point-future-external-write")
                }
              }
              point_window_raw_row_v4(
                source_object_v4(effects.at(version)).at("rowValues"),
                table,
              )
            }
          }
          for column in table.columns {
            work.charge()
            if expected.at(column.name) != op.values.at(column.name) {
              fail("mismatch:point-read-image")
            }
          }
          seen_read[slot] = version
          {
            "kind": "row_read",
            "tx": Json(tx),
            "relation": Json(relation),
            "predicate": [{ "column": "pk", "op": "eq", "value": op.key }],
            "rows": [
              { "key": op.key, "version": Json(version), "values": image },
            ],
            "complete": true,
          }
        }
        let (_, end, _) = calls.reads.at(original_seq)
        provenance.push({
          "historySeq": Json(events.length() + 1),
          "originalStatementSeq": Json(original_seq),
          "callEndSeq": Json(end),
          "nativeResultSeq": Json(op.native_note),
          "sourceVersion": Json(version),
          "versionSource": references.at(version),
        })
        event
      }
    }
    events.push(projected)
  }
  if checked_statements != operations.length() ||
    committed.length() != source.commits.length() {
    fail("unsupported:point-uncovered-original-operations")
  }
  let history : Json = {
    "traceSchema": 3,
    "dataModel": "relation-set-v1",
    "clockDomain": "configured-point-order-only",
    "relationSchema": Json(
      Map([(relation, { "primaryKey": Json("pk"), "columns": Json(columns) })]),
    ),
    "scope": {
      "exclusiveWriters": true,
      "completeSnapshotTables": [Json(relation)],
    },
    "gaps": [],
    "events": Json(
      events.mapi((index, event) => {
        let fields = object_fields_unchecked_v3(event)
        fields["seq"] = Json(index + 1)
        fields["time"] = Json(index)
        Json(fields)
      }),
    ),
  }
  let history_text = history.stringify()
  let parsed = wire_v4_history(history_text)
  let model_options = model_options_v4(
    models=[ElleSerializable],
    relation_profile=ModelRelationAtomicRows,
    max_source_checks=max_source,
    max_states~,
    max_edge_checks=max_edges,
  ).unwrap()
  let facts = model_facts_v4(parsed).unwrap()
  let model = model_classification_v4_json(
    classify_models_v4(facts, model_options),
  )
  let category = relation_classification_v4_json(
    classify_relation_point_v4(
      parsed,
      categories=["G2-item"],
      max_graph_checks=max_source,
      max_states~,
      max_edge_checks=max_edges,
    ),
  )
  {
    "format": "moontxnwitness-configured-point-window/v4",
    "status": source_object_v4(model).at("status"),
    "coverageComplete": true,
    "sourceAuthenticated": false,
    "startSha256": Json(start_hash),
    "endSha256": Json(end_hash),
    "sessionSha256": Json(v3_dislock_sha256(session_text)),
    "optionsSha256": Json(v3_dislock_sha256(options)),
    "scope": "owned PostgreSQL point window and supplied original observations",
    "history": history,
    "operationSources": Json(provenance),
    "relationSource": {
      "schema": Json(table.schema),
      "table": Json(table.name),
      "columns": Json(original_names),
    },
    "writerWindow": Json(window),
    "model": model,
    "itemCategory": category,
    "checks": Json(work.checks),
    "maxPointChecks": Json(work.limit),
  }
}

///|
pub fn analyze_configured_point_window_v4_json(
  before : String,
  after : String,
  session : String,
  options : String,
) -> String {
  point_window_analyze_v4(before, after, session, options).stringify() catch {
    error => {
      let reason = error.to_string()
      let status = if reason.contains("unsupported:") ||
        reason.contains("budget:") {
        "unknown"
      } else {
        "invalid"
      }
      (
        {
          "format": "moontxnwitness-configured-point-window/v4",
          "status": Json(status),
          "coverageComplete": false,
          "sourceAuthenticated": false,
          "startSha256": Json(v3_dislock_sha256(before)),
          "endSha256": Json(v3_dislock_sha256(after)),
          "sessionSha256": Json(v3_dislock_sha256(session)),
          "optionsSha256": Json(v3_dislock_sha256(options)),
          "reason": Json(reason),
        } : Json).stringify()
    }
  }
}

///|
pub fn verify_configured_point_window_v4_json(
  before : String,
  after : String,
  session : String,
  report : String,
  options : String,
) -> Bool {
  try {
    let observed = sql_json_v1(report, 33554432)
    let current = sql_json_v1(
      analyze_configured_point_window_v4_json(before, after, session, options),
      33554432,
    )
    source_object_v4(current).at("status") != Json("invalid") &&
    observed == current
  } catch {
    _ => false
  }
}
