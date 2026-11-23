///|
priv struct PredicateRowV1 {
  key : Int64
  version : String
  values : Json
}

///|
priv struct PredicateReadV1 {
  sequence : Int32
  tx : String
  lower : Int64
  upper : Int64
  snapshot : String
  rows : Array[PredicateRowV1]
  request_seq : Int32
}

///|
priv struct PredicateInsertV1 {
  tx : String
  sequence : Int32
  xid : String
  row : PredicateRowV1
}

///|
fn predicate_mode_sql_v1() -> String {
  "SELECT pg_catalog.jsonb_build_object('isolation',pg_catalog.current_setting('transaction_isolation'),'snapshot',pg_catalog.pg_current_snapshot()::text,'xid',pg_catalog.pg_current_xact_id_if_assigned()::text,'login',SESSION_USER,'pid',pg_catalog.pg_backend_pid(),'peer'," +
  effects_peer_sql_v4() +
  ")::text"
}

///|
fn predicate_range_sql_v1(table : SQLTableV1) -> String raise {
  let key = "t." + admission_qi_v2(table.key)
  "SELECT pg_catalog.to_jsonb(t)::text FROM " +
  admission_target_v2(table) +
  " t WHERE " +
  key +
  ">=%s::bigint AND " +
  key +
  "<%s::bigint ORDER BY " +
  key
}

///|
fn predicate_insert_sql_v1(table : SQLTableV1) -> String raise {
  let names = table.columns.map(column => admission_qi_v2(column.name))
  let slots = table.columns.map(column => {
    match column.kind {
      "int64" => "%s::bigint"
      "text" => "%s::text"
      "bool" => "%s::boolean"
      _ => fail("unsupported:predicate-insert-column")
    }
  })
  "WITH mtw_inserted AS (INSERT INTO " +
  admission_target_v2(table) +
  " (" +
  names.join(",") +
  ") VALUES (" +
  slots.join(",") +
  ") RETURNING *) SELECT pg_catalog.to_jsonb(mtw_inserted)::text FROM mtw_inserted"
}

///|
fn predicate_row_v1(config : SQLConfigV2, value : Json) -> PredicateRowV1 raise {
  let names = config.parser_config.tables[0].columns.map(column => column.name)
  names.push("__mtw_source_version")
  let raw = orm_exact(value, names)
  let version = source_positive_v4(raw.at("__mtw_source_version"))
  let _ = effects_decimal_v4(Json(version), "9223372036854775807")
  let values = window_typed_row_v2(config, value)
  let key = relation_v3_int64(sql_string_v1(window_key_v2(config, values)))
  { key, version, values, }
}

///|
fn predicate_model_row_v1(
  config : SQLConfigV2,
  row : PredicateRowV1,
) -> Json raise {
  {
    "key": window_key_v2(config, row.values),
    "version": Json("row:" + row.version),
    "values": window_image_v2(config, row.values),
  }
}

///|
fn predicate_add_event_v1(
  events : Map[Int32, Json],
  sequence : Int32,
  event : Json,
) -> Unit raise {
  if sequence == 0 || events.contains(sequence) {
    fail("mismatch:predicate-duplicate-sequence")
  }
  events[sequence] = event
}

///|
fn predicate_verify_reads_v1(
  config : SQLConfigV2,
  reads : Array[PredicateReadV1],
  initial : Map[String, PredicateRowV1],
  inserts : Map[String, PredicateInsertV1],
  before : SnapshotAdmissionV2,
  after : SnapshotAdmissionV2,
  work : SourceWorkV4,
  events : Map[Int32, Json],
) -> Unit raise {
  let (_, start_upper, _) = effects_snapshot_bounds_v4(
    sql_string_v1(window_object_v2(before.snapshot).at("snapshot")),
    work,
  )
  let (_, end_upper, _) = effects_snapshot_bounds_v4(
    sql_string_v1(window_object_v2(after.snapshot).at("snapshot")),
    work,
  )
  for _, insert in inserts {
    work.charge()
    if source_version_after_v4(start_upper, insert.xid) ||
      !source_version_after_v4(end_upper, insert.xid) {
      fail("mismatch:predicate-writer-outside-window")
    }
  }
  for read in reads {
    let (_, upper, active) = effects_snapshot_bounds_v4(read.snapshot, work)
    if source_version_after_v4(start_upper, upper) ||
      source_version_after_v4(upper, end_upper) {
      fail("mismatch:predicate-snapshot-outside-window")
    }
    let expected : Map[String, PredicateRowV1] = Map([])
    for version, row in initial {
      work.charge()
      if read.lower <= row.key && row.key < read.upper {
        let writer = effects_xid_v4(
          window_object_v2(before.effects.at(version)).at("writerXid"),
        )
        if !effects_xid_completed_v4(writer, upper, active) {
          fail("mismatch:predicate-initial-row-not-visible")
        }
        expected[version] = row
      }
    }
    for version, insert in inserts {
      work.charge()
      let visible = if insert.tx == read.tx {
        insert.sequence < read.sequence
      } else {
        effects_xid_completed_v4(insert.xid, upper, active)
      }
      if visible && read.lower <= insert.row.key && insert.row.key < read.upper {
        expected[version] = insert.row
      }
    }
    let observed : Array[Json] = []
    let mut previous : Int64? = None
    for row in read.rows {
      work.charge()
      match previous {
        Some(key) if key >= row.key =>
          fail("mismatch:predicate-native-row-order")
        _ => ()
      }
      previous = Some(row.key)
      match expected.get(row.version) {
        None => fail("mismatch:predicate-unexpected-row")
        Some(current) =>
          source_equal_v4(row.values, current.values, "predicate-visible-row")
      }
      expected.remove(row.version)
      observed.push(predicate_model_row_v1(config, row))
    }
    if !expected.is_empty() {
      fail("mismatch:predicate-missing-visible-row")
    }
    predicate_add_event_v1(events, read.sequence, {
      "kind": "row_read",
      "tx": Json(read.tx),
      "relation": "configured",
      "predicate": [
        { "column": "pk", "op": "ge", "value": Json(read.lower.to_string()) },
        { "column": "pk", "op": "lt", "value": Json(read.upper.to_string()) },
      ],
      "rows": Json(observed),
      "complete": true,
      "originalSnapshot": Json(read.snapshot),
      "originalRequestSeq": Json(read.request_seq),
    })
  }
}

///|
fn predicate_admission_body_v1(
  config : SQLConfigV2,
  policy : Json,
  bundle : Json,
  options : Json,
  bundle_digest : String,
) -> Json raise {
  let input = orm_exact(bundle, [
    "format", "contract", "configSha256", "installationLogText", "installationReceiptText",
    "startInputText", "endInputText", "transactions",
  ])
  if input.at("format") !=
    Json("moontxnwitness-configured-predicate-window-input/v1") ||
    input.at("contract") != Json("postgres18-int64-range-insert/v1") ||
    input.at("configSha256") != Json(config.digest) {
    fail("mismatch:predicate-window-identity")
  }
  let table = config.parser_config.tables[0]
  if projected_column_kind_v2(config, table.key) != "int64" {
    fail("unsupported:predicate-key-type")
  }
  let opts = window_object_v2(options)
  known_fields(opts, ["maxChecks"], "predicate window options")
  let limit = source_wire_limit_v4(opts, "maxChecks", 1000000)
  let work : SourceWorkV4 = { limit, checks: 0, }
  let installation = verify_source_admission_v2(
    config,
    policy,
    sql_string_v1(input.at("installationLogText")),
    sql_json_v1(sql_string_v1(input.at("installationReceiptText")), 2097152),
    max_checks=limit,
  )
  if window_object_v2(installation.record).at("installationVerified") !=
    Json(true) {
    fail("unsupported:predicate-installation-unverified")
  }
  window_charge_component_v2(work, installation.record)
  let (start_log, start_receipt) = window_snapshot_input_v2(
    sql_json_v1(sql_string_v1(input.at("startInputText")), 16777216),
  )
  let before = verify_snapshot_admission_v2(
    installation,
    start_log,
    start_receipt,
    max_checks=limit - work.checks,
  )
  if window_object_v2(before.record).at("snapshotVerified") != Json(true) {
    fail("unsupported:predicate-start-snapshot-unverified")
  }
  window_charge_component_v2(work, before.record)
  let (end_log, end_receipt) = window_snapshot_input_v2(
    sql_json_v1(sql_string_v1(input.at("endInputText")), 16777216),
  )
  let after = verify_snapshot_admission_v2(
    installation,
    end_log,
    end_receipt,
    max_checks=limit - work.checks,
  )
  if window_object_v2(after.record).at("snapshotVerified") != Json(true) {
    fail("unsupported:predicate-end-snapshot-unverified")
  }
  window_charge_component_v2(work, after.record)
  source_equal_v4(before.peer, after.peer, "predicate-window-peer")
  let initial : Map[String, PredicateRowV1] = Map([])
  for version, raw in before.rows {
    work.charge()
    let row = predicate_row_v1(config, window_object_v2(raw).at("row"))
    initial[version] = row
    match after.rows.get(version) {
      None => fail("unsupported:predicate-non-insert-window")
      Some(visible) =>
        source_equal_v4(
          window_object_v2(visible).at("row"),
          window_object_v2(raw).at("row"),
          "predicate-retained-row",
        )
    }
  }
  for version, raw in before.effects {
    work.charge()
    match after.effects.get(version) {
      None => fail("mismatch:predicate-retained-effect-missing")
      Some(effect) =>
        source_equal_v4(
          window_effect_record_v2(raw),
          window_effect_record_v2(effect),
          "predicate-retained-effect",
        )
    }
  }
  let txs = orm_array(input.at("transactions"))
  if txs.is_empty() || txs.length() > 32 {
    fail("budget:predicate-transaction-count")
  }
  let events : Map[Int32, Json] = Map([])
  let reads : Array[PredicateReadV1] = []
  let insertions : Map[String, PredicateInsertV1] = Map([])
  let writer_transactions : Map[String, String] = Map([])
  let mut operations = 0
  for index, raw in txs {
    work.charge()
    let txn = orm_exact(raw, [
      "id", "isolation", "begin", "end", "outcome", "sqlstate", "calls", "logReceipt",
      "logText",
    ])
    let tx = "range-" + (index + 1).to_string()
    let isolation = sql_string_v1(txn.at("isolation"))
    let begin_sql = match isolation {
      "repeatable read" => "BEGIN ISOLATION LEVEL REPEATABLE READ"
      "serializable" => "BEGIN ISOLATION LEVEL SERIALIZABLE"
      _ => fail("unsupported:predicate-isolation")
    }
    source_equal_v4(txn.at("id"), Json(tx), "predicate-transaction-identity")
    if txn.at("outcome") != Json("committed") ||
      txn.at("sqlstate") != Json::null() {
      fail("unsupported:predicate-transaction-outcome")
    }
    let begin = fetch_number_v1(txn.at("begin"), 192)
    let end = fetch_number_v1(txn.at("end"), 192)
    let stream = source_parse_control_v2(
      sql_string_v1(txn.at("logText")),
      txn.at("logReceipt"),
      "moontxnwitness-configured-predicate-transaction-log/v1",
      "postgres18-int64-range-insert/v1",
      work,
      allow_predicate_rows=true,
    )
    source_control_ack_v2(
      stream.next("begin", begin_sql, Json::null(), before=0),
      "BEGIN",
    )
    source_control_ack_v2(
      stream.next(
        "safe-path",
        "SET LOCAL search_path TO pg_catalog,pg_temp",
        Json::null(),
      ),
      "SET",
    )
    predicate_add_event_v1(events, begin, { "kind": "begin", "tx": Json(tx) })
    let calls = orm_array(txn.at("calls"))
    if calls.is_empty() || operations + calls.length() > 128 {
      fail("budget:predicate-business-operation-count")
    }
    operations += calls.length()
    let mut previous = begin
    let mut snapshot = ""
    let mut identity = Json::null()
    let mut known_xid = Json::null()
    for raw_call in calls {
      work.charge()
      let call = orm_exact(raw_call, [
        "kind", "parameters", "sequence", "delivered",
      ])
      let kind = sql_string_v1(call.at("kind"))
      let params = orm_array(call.at("parameters"))
      let sequence = fetch_number_v1(call.at("sequence"), 192)
      if sequence <= previous || sequence >= end {
        fail("mismatch:predicate-transaction-sequence")
      }
      previous = sequence
      let sql = match kind {
        "range" => predicate_range_sql_v1(table)
        "insert" => predicate_insert_sql_v1(table)
        _ => fail("unsupported:predicate-statement")
      }
      let command = stream.next(kind, sql, Json(params))
      let mode = orm_exact(
        stream.one("transaction-mode", predicate_mode_sql_v1(), Json::null()),
        ["isolation", "snapshot", "xid", "login", "pid", "peer"],
      )
      source_equal_v4(
        mode.at("isolation"),
        Json(isolation),
        "predicate-transaction-isolation",
      )
      source_equal_v4(
        mode.at("peer"),
        before.peer,
        "predicate-transaction-peer",
      )
      let login = sql_identifier_v1(mode.at("login"))
      let pid = fetch_number_v1(mode.at("pid"), 2147483647)
      if !installation.policy.writers.contains(login) || pid == 0 {
        fail("unsupported:predicate-participant-identity")
      }
      let current_identity : Json = [Json(login), Json(pid)]
      let observed_snapshot = sql_string_v1(mode.at("snapshot"))
      if snapshot == "" {
        let _ = effects_snapshot_bounds_v4(observed_snapshot, work)
        snapshot = observed_snapshot
        identity = current_identity
      } else if snapshot != observed_snapshot || identity != current_identity {
        fail("mismatch:predicate-transaction-snapshot-changed")
      }
      let xid = mode.at("xid")
      if known_xid != Json::null() && known_xid != xid {
        fail("mismatch:predicate-transaction-xid-changed")
      }
      if xid != Json::null() {
        let _ = effects_xid_v4(xid)
        known_xid = xid
      }
      let delivered = orm_array(call.at("delivered"))
      source_equal_v4(
        Json(delivered.length()),
        Json(command.decoded.length()),
        "predicate-delivery-count",
      )
      let rows = command.decoded.mapi((i, value) => {
        let row = predicate_row_v1(config, value)
        let fields = orm_exact(
          delivered[i],
          table.columns.map(column => column.name),
        )
        source_equal_v4(
          window_typed_row_v2(config, Json(fields)),
          row.values,
          "predicate-complete-delivery",
        )
        row
      })
      if kind == "range" {
        if params.length() != 2 {
          fail("mismatch:predicate-range-parameters")
        }
        let lower = relation_v3_int64(sql_string_v1(params[0]))
        let upper = relation_v3_int64(sql_string_v1(params[1]))
        if lower >= upper ||
          params != [Json(lower.to_string()), Json(upper.to_string())] {
          fail("mismatch:predicate-half-open-interval")
        }
        reads.push({
          sequence,
          tx,
          lower,
          upper,
          snapshot,
          rows,
          request_seq: command.request_seq,
        })
      } else {
        if rows.length() != 1 ||
          params.length() != table.columns.length() ||
          xid == Json::null() {
          fail("mismatch:predicate-complete-insert")
        }
        let row = rows[0]
        let id = effects_xid_v4(xid)
        let expected = table.columns.map(column => {
          window_object_v2(window_object_v2(row.values).at(column.name)).at(
            "value",
          )
        })
        source_equal_v4(
          Json(params),
          Json(expected),
          "predicate-insert-bound-values",
        )
        if before.effects.contains(row.version) ||
          insertions.contains(row.version) {
          fail("mismatch:predicate-insert-effect-identity")
        }
        let effect = match after.effects.get(row.version) {
          None => fail("mismatch:predicate-insert-source-missing")
          Some(value) => window_object_v2(value)
        }
        if effect.at("operation") != Json("INSERT") ||
          effect.at("baseVersion") != Json::null() {
          fail("unsupported:predicate-non-insert-window")
        }
        source_equal_v4(
          effect.at("writerXid"),
          xid,
          "predicate-insert-writer-xid",
        )
        source_equal_v4(
          effect.at("writerPid"),
          Json(pid),
          "predicate-insert-writer-pid",
        )
        source_equal_v4(
          effect.at("writerLogin"),
          Json(login),
          "predicate-insert-writer-login",
        )
        source_equal_v4(
          window_typed_row_v2(config, effect.at("rowValues")),
          row.values,
          "predicate-insert-source-values",
        )
        match writer_transactions.get(id) {
          Some(other) if other != tx => fail("mismatch:predicate-xid-reused")
          _ => writer_transactions[id] = tx
        }
        insertions[row.version] = { tx, sequence, xid: id, row, }
        predicate_add_event_v1(events, sequence, {
          "kind": "row_write",
          "tx": Json(tx),
          "relation": "configured",
          "action": "insert",
          "key": window_key_v2(config, row.values),
          "version": Json("row:" + row.version),
          "predecessor": Json::null(),
          "values": window_image_v2(config, row.values),
          "originalRequestSeq": Json(command.request_seq),
        })
      }
    }
    source_control_ack_v2(
      stream.next("commit", "COMMIT", Json::null(), after=0),
      "COMMIT",
    )
    if stream.next_index != stream.commands.length() {
      fail("mismatch:predicate-unaccounted-command")
    }
    predicate_add_event_v1(events, end, { "kind": "commit", "tx": Json(tx) })
  }
  if reads.is_empty() {
    fail("unsupported:predicate-no-range-read")
  }
  for version, _ in after.effects {
    work.charge()
    if !before.effects.contains(version) && !insertions.contains(version) {
      fail("unsupported:predicate-unobserved-write")
    }
  }
  predicate_verify_reads_v1(
    config, reads, initial, insertions, before, after, work, events,
  )
  let timeline : Array[Json] = []
  for sequence in 1..<(events.length() + 1) {
    match events.get(sequence) {
      None => fail("mismatch:predicate-global-sequence-gap")
      Some(value) => timeline.push(value)
    }
  }
  let starting : Array[Json] = []
  let versions = initial.keys().to_array()
  versions.sort()
  for version in versions {
    starting.push(predicate_model_row_v1(config, initial.at(version)))
  }
  {
    "format": "moontxnwitness-configured-predicate-admission/v1",
    "status": "admitted",
    "coverageComplete": true,
    "sourceAuthenticated": false,
    "bundleSha256": Json(bundle_digest),
    "configSha256": Json(config.digest),
    "startingRows": Json(starting),
    "events": Json(timeline),
    "transactions": Json(txs.length()),
    "rangeReads": Json(reads.length()),
    "checks": Json(work.checks),
    "maxChecks": Json(limit),
  }
}

///|
pub fn admit_configured_predicate_window_v1_json(
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
    predicate_admission_body_v1(
      config,
      sql_json_v1(policy_text, 8192),
      sql_json_v1(bundle_text, 33554432),
      sql_json_v1(options_text, 8192),
      v3_dislock_sha256(bundle_text),
    ).stringify()
  } catch {
    error =>
      (
        {
          "format": "moontxnwitness-configured-predicate-admission/v1",
          "status": "unknown",
          "coverageComplete": false,
          "sourceAuthenticated": false,
          "reason": Json(error.to_string()),
        } : Json).stringify()
  }
}
