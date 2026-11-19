///|
priv struct WindowCaseV2 {
  execution : Json
  execution_note : Int32
  native : Json
  native_note : Int32
  deliveries : Array[Json]
  delivery_notes : Array[Int32]
  call_start : Int32
  call_end : Int32
}

///|
priv struct WindowLifecycleV2 {
  cases : Array[WindowCaseV2]
  commits : Map[String, Json]
  trace_events : Array[Json]
  trace_by_seq : Map[Int32, Json]
  begin_by_tx : Map[String, Json]
}

///|
priv struct WindowPoolLeaseV2 {
  pid : Json
  mut ordinal : Int32
  mut borrowed : Bool
  mut transaction : String?
}

///|
fn window_pool_event_v2(
  leases : Map[String, WindowPoolLeaseV2],
  opened : Map[String, Bool],
  event : Map[String, Json],
  kind : String,
) -> Unit raise {
  let frame = orm_exact(window_frame_v2(event), [
    "format", "connection", "backendPid", "lease", "transactionStatus",
  ])
  let connection = sql_string_v1(frame.at("connection"))
  let pid = fetch_number_v1(frame.at("backendPid"), 2147483647)
  let ordinal = fetch_number_v1(frame.at("lease"), 65536)
  if !opened.contains(connection) ||
    frame.at("format") != Json("moontxnwitness-configured-point-pool/v1") ||
    frame.at("transactionStatus") != Json(0) ||
    pid == 0 {
    fail("mismatch:window-invalid-pool-boundary")
  }
  if kind == "configured-point-pool-enroll" {
    if ordinal != 0 || leases.contains(connection) {
      fail("mismatch:window-invalid-pool-enrollment")
    }
    leases[connection] = {
      pid: Json(pid),
      ordinal: 0,
      borrowed: false,
      transaction: None,
    }
    return
  }
  let lease = match leases.get(connection) {
    Some(value) => value
    None => fail("mismatch:window-pool-enrollment-missing")
  }
  if lease.pid != Json(pid) || lease.transaction is Some(_) {
    fail("mismatch:window-pool-backend-or-transaction")
  }
  if kind == "configured-point-pool-checkout" {
    if lease.borrowed || ordinal != lease.ordinal + 1 {
      fail("mismatch:window-invalid-pool-checkout")
    }
    lease.ordinal = ordinal
    lease.borrowed = true
  } else {
    if !lease.borrowed || ordinal != lease.ordinal {
      fail("mismatch:window-invalid-pool-checkin")
    }
    lease.borrowed = false
  }
}

///|
fn window_pool_lease_v2(
  leases : Map[String, WindowPoolLeaseV2],
  connection : String,
  borrowed : Bool,
) -> WindowPoolLeaseV2 raise {
  match leases.get(connection) {
    Some(lease) if lease.borrowed == borrowed => lease
    _ => fail("mismatch:window-pool-lease-state")
  }
}

///|
fn window_object_v2(raw : Json) -> Map[String, Json] raise {
  object_fields(raw, "configured V2 window")
}

///|
fn window_frame_v2(event : Map[String, Json]) -> Json raise {
  sql_json_v1(
    sql_string_v1(required(event, "frameText", "window frame")),
    61440,
  )
}

///|
fn window_lifecycle_v2(
  text : String,
  trace_text : String,
  start_digest : String,
  end_digest : String,
  install_digest : String,
  config : SQLConfigV2,
  projection_options : PointProjectionOptionsV2,
  peer : Json,
  work : SourceWorkV4,
) -> WindowLifecycleV2 raise {
  if orm_utf8_size(text) > 8388608 || !text.has_suffix("\n") {
    fail("unsupported:window-lifecycle-byte-bound-or-tail")
  }
  let lines = text.split("\n").to_array()
  if lines.length() < 6 || lines.length() > 65537 {
    fail("unsupported:window-lifecycle-record-bound")
  }
  let trace = window_object_v2(sql_json_v1(trace_text, 8388608))
  source_equal_v4(trace.at("traceSchema"), Json(3), "window-trace-schema")
  for gap in orm_array(trace.at("gaps")) {
    work.charge()
    let code = sql_string_v1(window_object_v2(gap).at("code"))
    if ![
        "initialization_unproven", "diagnostic_instrumentation_only", "point_source_window_unverified",
        "source_unsealed", "diagnostic_only",
      ].contains(code) {
      fail("unsupported:window-original-capture-gap:" + code)
    }
  }
  let events = orm_array(trace.at("events"))
  let trace_by_seq : Map[Int32, Json] = Map([])
  let begins : Map[String, Json] = Map([])
  let requests : Map[String, Int32] = Map([])
  let oks : Map[String, Int32] = Map([])
  let connection_tx : Map[String, String] = Map([])
  for index, raw in events {
    work.charge()
    let event = window_object_v2(raw)
    let seq = fetch_number_v1(event.at("seq"), 100000000)
    if seq != index + 1 {
      fail("mismatch:window-trace-sequence")
    }
    trace_by_seq[seq] = raw
    let kind = sql_string_v1(event.at("kind"))
    if kind == "snapshot" {
      if seq != 1 ||
        event.at("consistent") != Json(false) ||
        !window_object_v2(event.at("initial")).is_empty() {
        fail("mismatch:window-diagnostic-snapshot")
      }
      continue
    }
    let tx = sql_string_v1(event.at("tx"))
    if kind == "begin" {
      let connection = sql_string_v1(event.at("connection"))
      if begins.contains(tx) ||
        connection_tx.contains(connection) ||
        begins.length() >= 32 {
        fail("unsupported:window-transaction-boundary-or-limit")
      }
      begins[tx] = raw
      connection_tx[connection] = tx
    } else if kind == "statement" || kind == "rows" {
      if !begins.contains(tx) || requests.contains(tx) || oks.contains(tx) {
        fail("mismatch:window-statement-transaction-order")
      }
      if kind == "rows" && event.get("error") is Some(_) {
        fail("unsupported:window-failed-statement")
      }
      if kind == "rows" {
        let statement = fetch_number_v1(event.at("statement"), 100000000)
        let referenced = match trace_by_seq.get(statement) {
          Some(value) => window_object_v2(value)
          None => fail("mismatch:window-rows-statement-missing")
        }
        if statement >= seq ||
          referenced.at("kind") != Json("statement") ||
          referenced.at("tx") != Json(tx) {
          fail("mismatch:window-rows-statement-identity")
        }
      }
    } else if kind == "commit_request" {
      if !begins.contains(tx) || requests.contains(tx) {
        fail("mismatch:window-commit-request")
      }
      requests[tx] = seq
    } else if kind == "commit_ok" {
      if !requests.contains(tx) || oks.contains(tx) {
        fail("mismatch:window-commit-confirmation")
      }
      oks[tx] = seq
      let connection = sql_string_v1(
        window_object_v2(begins.at(tx)).at("connection"),
      )
      connection_tx.remove(connection)
    } else {
      fail("unsupported:window-unconfirmed-or-unsupported-transaction-event")
    }
  }
  if begins.is_empty() ||
    begins.length() != oks.length() ||
    !connection_tx.is_empty() {
    fail("unsupported:window-unclosed-transactions")
  }
  let opened : Map[String, Bool] = Map([])
  let leases : Map[String, WindowPoolLeaseV2] = Map([])
  let active : Map[String, Json] = Map([])
  let execute_calls : Map[Int32, (Int32, Int32, Json)] = Map([])
  let commit_calls : Map[String, Json] = Map([])
  let commit_responses : Map[String, Json] = Map([])
  let checkpoints : Map[String, (Int32, Json)] = Map([])
  let projections : Map[Int32, Json] = Map([])
  let cases : Array[WindowCaseV2] = []
  let result_indices : Map[String, Int32] = Map([])
  let used_projections : Map[Int32, Bool] = Map([])
  let prefix = StringBuilder()
  let mut domain : Json = Json::null()
  let mut asynchronous = false
  let mut pooled = false
  let mut started = false
  let mut ended = false
  for index in 0..<(lines.length() - 1) {
    work.charge()
    let raw = sql_json_v1(lines[index].to_owned(), 524288)
    let event = window_object_v2(raw)
    let seq = index + 1
    source_equal_v4(event.at("seq"), Json(seq), "window-lifecycle-sequence")
    let kind = sql_string_v1(event.at("kind"))
    if index == 0 {
      source_equal_v4(
        event.at("format"),
        Json("moontxnwitness-instrumentation/v1"),
        "window-header",
      )
      if kind != "header" || event.at("diagnosticOnly") != Json(true) {
        fail("mismatch:window-header")
      }
      domain = event.at("processMonotonicDomain")
      projected_identity_v2(domain)
    } else if index == lines.length() - 2 {
      if kind != "seal" ||
        event.at("records") != Json(index) ||
        event.at("prefixSha256") != Json(v3_dislock_sha256(prefix.to_string())) {
        fail("mismatch:window-lifecycle-seal")
      }
      if !ended {
        fail("unsupported:window-end-boundary-missing")
      }
      break
    } else {
      source_equal_v4(
        event.at("processMonotonicDomain"),
        domain,
        "window-lifecycle-domain",
      )
      if kind == "configured-point-producer" {
        let frame = window_object_v2(window_frame_v2(event))
        if seq != 2 {
          fail("mismatch:window-producer-position")
        }
        match sql_string_v1(frame.at("format")) {
          "moontxnwitness-point-producer/v2" => ()
          "moontxnwitness-async-point-producer/v2" => asynchronous = true
          "moontxnwitness-async-point-pool-producer/v1" => {
            asynchronous = true
            pooled = true
          }
          _ => fail("unsupported:window-point-producer-format")
        }
        source_equal_v4(
          frame.at("config"),
          config.record,
          "window-producer-config",
        )
        source_equal_v4(
          frame.at("projectionOptions"),
          projection_options.record,
          "window-producer-independent-options",
        )
      } else if kind == "configured-window-start" ||
        kind == "configured-window-end" {
        let frame = window_object_v2(window_frame_v2(event))
        if kind == "configured-window-start" {
          if seq != 3 || started {
            fail("mismatch:window-start-boundary")
          }
          source_equal_v4(
            frame.at("installationLogSha256"),
            Json(install_digest),
            "window-installation-binding",
          )
          source_equal_v4(
            frame.at("snapshotInputSha256"),
            Json(start_digest),
            "window-start-binding",
          )
          started = true
        } else {
          if !started || ended || !opened.is_empty() || !active.is_empty() {
            fail("unsupported:window-end-with-live-connections")
          }
          source_equal_v4(
            frame.at("snapshotInputSha256"),
            Json(end_digest),
            "window-end-binding",
          )
          ended = true
        }
      } else if kind == "instrumentation-detached" {
        if !ended {
          fail("unsupported:window-premature-detach")
        }
      } else {
        if !started || ended {
          fail("unsupported:window-event-outside-boundaries")
        }
        if kind == "connect" {
          let connection = sql_string_v1(event.at("connection"))
          if opened.contains(connection) ||
            event.at("asynchronous") != Json(asynchronous) {
            fail("mismatch:window-connection")
          }
          opened[connection] = true
        } else if pooled &&
          [
            "configured-point-pool-enroll", "configured-point-pool-checkout", "configured-point-pool-checkin",
          ].contains(kind) {
          window_pool_event_v2(leases, opened, event, kind)
        } else if kind == "connection-close" {
          let connection = sql_string_v1(event.at("connection"))
          if !opened.contains(connection) || active.contains(connection) {
            fail("mismatch:window-close")
          }
          if pooled {
            ignore(window_pool_lease_v2(leases, connection, false))
          }
          opened.remove(connection)
        } else if kind == "call-start" || kind == "call-end" {
          let connection = sql_string_v1(event.at("connection"))
          let call_method = sql_string_v1(event.at("method"))
          if !opened.contains(connection) ||
            !["execute", "commit"].contains(call_method) {
            fail("unsupported:window-call-kind")
          }
          if kind == "call-start" {
            if active.contains(connection) {
              fail("unsupported:window-overlapping-calls")
            }
            if pooled {
              let lease = window_pool_lease_v2(leases, connection, true)
              let tx = sql_string_v1(event.at("tx"))
              match lease.transaction {
                Some(previous) if previous != tx =>
                  fail("mismatch:window-pool-transaction-switch")
                None if call_method == "commit" =>
                  fail("mismatch:window-pool-commit-without-execute")
                _ => lease.transaction = Some(tx)
              }
            }
            active[connection] = raw
          } else {
            let start = match active.get(connection) {
              Some(value) => window_object_v2(value)
              None => fail("mismatch:window-call-start-missing")
            }
            for key in ["callId", "method", "tx"] {
              source_equal_v4(
                event.at(key),
                start.at(key),
                "window-call-identity",
              )
            }
            if event.at("succeeded") != Json(true) {
              fail("unsupported:window-failed-call")
            }
            active.remove(connection)
            let tx = sql_string_v1(event.at("tx"))
            if !begins.contains(tx) ||
              window_object_v2(begins.at(tx)).at("connection") !=
              Json(connection) {
              fail("mismatch:window-call-transaction")
            }
            let start_seq = fetch_number_v1(start.at("seq"), 65536)
            if call_method == "execute" {
              let statement = fetch_number_v1(
                event.at("statementSeq"),
                100000000,
              )
              if execute_calls.contains(statement) ||
                execute_calls.length() >= 128 {
                fail("unsupported:window-statement-limit")
              }
              let observed = window_object_v2(trace_by_seq.at(statement))
              if observed.at("kind") != Json("statement") ||
                observed.at("tx") != Json(tx) {
                fail("mismatch:window-call-statement")
              }
              execute_calls[statement] = (start_seq, seq, raw)
            } else {
              if commit_calls.contains(tx) || !commit_responses.contains(tx) {
                fail("mismatch:window-commit-response-missing")
              }
              let refs = window_object_v2(event.at("journalEventSeqs"))
              if refs.get("begin") !=
                Some(window_object_v2(begins.at(tx)).at("seq")) ||
                refs.get("commit_request") != Some(Json(requests.at(tx))) ||
                refs.get("commit_ok") != Some(Json(oks.at(tx))) ||
                event.get("nativeCommandTag") != Some(Json("COMMIT")) {
                fail("mismatch:window-commit-trace-references")
              }
              commit_calls[tx] = {
                "startSeq": Json(start_seq),
                "endSeq": Json(seq),
                "connection": Json(connection),
              }
              if pooled {
                window_pool_lease_v2(leases, connection, true).transaction = None
              }
            }
          }
        } else if kind == "commit-response" {
          let connection = sql_string_v1(event.at("connection"))
          let call = match active.get(connection) {
            Some(value) => window_object_v2(value)
            None => fail("mismatch:window-response-call")
          }
          let tx = sql_string_v1(call.at("tx"))
          if call.at("method") != Json("commit") ||
            event.at("commandTag") != Json("COMMIT") ||
            event.at("transactionStatus") != Json(0) ||
            event.at("request") != Json(requests.at(tx)) ||
            commit_responses.contains(tx) {
            fail("unsupported:window-native-commit-not-confirmed")
          }
          commit_responses[tx] = raw
        } else if kind == "configured-point-projection" {
          projections[seq] = window_frame_v2(event)
        } else if kind == "configured-point-native" {
          let frame = window_frame_v2(event)
          let n = window_object_v2(frame)
          let connection = sql_string_v1(n.at("connection"))
          if !opened.contains(connection) {
            fail("mismatch:window-native-closed-connection")
          }
          if pooled {
            let lease = window_pool_lease_v2(leases, connection, true)
            source_equal_v4(
              window_object_v2(n.at("native")).at("backendPid"),
              lease.pid,
              "window-pool-native-backend",
            )
          }
          let note = fetch_number_v1(n.at("projectionNoteSeq"), 65536)
          let execution = match projections.get(note) {
            Some(value) => value
            None => fail("mismatch:window-projection-missing")
          }
          let e = window_object_v2(execution)
          for key in ["connection", "cursor"] {
            source_equal_v4(
              e.at(key),
              n.at(key),
              "window-execution-native-identity",
            )
          }
          let statement = fetch_number_v1(n.at("statementSeq"), 100000000)
          let (start, finish, call) = match execute_calls.get(statement) {
            Some(value) => value
            None => fail("mismatch:window-native-execution-call")
          }
          source_equal_v4(
            window_object_v2(call).at("connection"),
            n.at("connection"),
            "window-native-call-connection",
          )
          if used_projections.contains(note) ||
            note >= start ||
            finish >= seq ||
            window_object_v2(call).at("tx") != n.at("tx") {
            fail("mismatch:window-native-order")
          }
          let result = sql_string_v1(n.at("resultId"))
          if result_indices.contains(result) {
            fail("mismatch:window-duplicate-result")
          }
          used_projections[note] = true
          result_indices[result] = cases.length()
          cases.push({
            execution,
            execution_note: note,
            native: frame,
            native_note: seq,
            deliveries: [],
            delivery_notes: [],
            call_start: start,
            call_end: finish,
          })
        } else if kind == "configured-point-delivery" {
          let frame = window_frame_v2(event)
          let connection = sql_string_v1(
            window_object_v2(frame).at("connection"),
          )
          if !opened.contains(connection) {
            fail("mismatch:window-delivery-closed-connection")
          }
          if pooled {
            ignore(window_pool_lease_v2(leases, connection, true))
          }
          let result = sql_string_v1(window_object_v2(frame).at("resultId"))
          let i = match result_indices.get(result) {
            Some(i) => i
            None => fail("mismatch:window-delivery-result")
          }
          cases[i].deliveries.push(frame)
          cases[i].delivery_notes.push(seq)
        } else if kind == "configured-point-writer" {
          let frame = window_frame_v2(event)
          let f = window_object_v2(frame)
          let tx = sql_string_v1(f.at("tx"))
          if pooled {
            let lease = window_pool_lease_v2(
              leases,
              sql_string_v1(f.at("connection")),
              true,
            )
            if lease.transaction != Some(tx) {
              fail("mismatch:window-pool-writer-transaction")
            }
            source_equal_v4(
              window_object_v2(f.at("native")).at("backendPid"),
              lease.pid,
              "window-pool-writer-backend",
            )
          }
          if checkpoints.contains(tx) {
            fail("mismatch:window-duplicate-writer-checkpoint")
          }
          checkpoints[tx] = (seq, frame)
        } else {
          fail("unsupported:window-uncovered-lifecycle-event:" + kind)
        }
      }
    }
    prefix.write_string(lines[index].to_owned())
    prefix.write_char('\n')
  }
  if cases.length() != execute_calls.length() ||
    projections.length() != used_projections.length() ||
    commit_calls.length() != begins.length() {
    fail("unsupported:window-uncovered-operations-or-outcomes")
  }
  let commits : Map[String, Json] = Map([])
  let xids : Map[String, String] = Map([])
  for tx, call_raw in commit_calls {
    work.charge()
    let call = window_object_v2(call_raw)
    let (note, raw) = match checkpoints.get(tx) {
      Some(value) => value
      None => fail("unsupported:window-writer-checkpoint-missing")
    }
    let f = window_object_v2(raw)
    let connection = sql_string_v1(call.at("connection"))
    let n = window_object_v2(f.at("native"))
    let checkpoint_sql = "SELECT pg_catalog.jsonb_build_object('peer'," +
      effects_peer_sql_v4() +
      ",'xid',pg_catalog.pg_current_xact_id_if_assigned()::text,'login',SESSION_USER,'pid',pg_catalog.pg_backend_pid())::text"
    if f.at("format") != Json("moontxnwitness-point-writer-checkpoint/v2") ||
      f.at("connection") != Json(connection) ||
      f.at("sql") != Json(checkpoint_sql) ||
      note >= fetch_number_v1(call.at("startSeq"), 65536) ||
      n.at("status") != Json(2) ||
      n.at("transactionStatus") != Json(2) ||
      n.at("commandStatusBase64") != Json("U0VMRUNUIDE=") ||
      n.at("clientEncodingBase64") != Json("VVRGOA==") ||
      n.at("commandTuples") !=
      Json({ "pythonType": "builtins.int", "value": "1" }) {
      fail("mismatch:window-writer-probe")
    }
    let fields = orm_array(n.at("fields"))
    let rows = orm_array(n.at("rows"))
    if fields.length() != 1 ||
      rows.length() != 1 ||
      orm_array(rows[0]).length() != 1 {
      fail("mismatch:window-probe-shape")
    }
    let field = window_object_v2(fields[0])
    if field.at("oid") != Json(25) || field.at("format") != Json(0) {
      fail("mismatch:window-probe-native-type")
    }
    let text = sql_string_v1(f.at("deliveredText"))
    if sql_string_v1(orm_array(rows[0])[0]).length() > 5464 {
      fail("unsupported:window-writer-probe-byte-budget")
    }
    let encoded = @base64.decode(
      sql_string_v1(orm_array(rows[0])[0])[:],
      ignore_whitespace=false,
    )
    if encoded.length() > 4096 ||
      @base64.encode(encoded[:]) != sql_string_v1(orm_array(rows[0])[0]) ||
      @utf8.decode(encoded[:], ignore_bom=false) != text {
      fail("mismatch:window-probe-native-delivery")
    }
    let row = orm_exact(sql_json_v1(text, 4096), ["peer", "xid", "login", "pid"])
    source_equal_v4(row.at("peer"), peer, "window-writer-peer")
    source_equal_v4(
      row.at("pid"),
      n.at("backendPid"),
      "window-writer-driver-pid",
    )
    ignore(source_oid_v4(row.at("pid")))
    let xid = row.at("xid")
    if xid != Json::null() {
      let id = effects_xid_v4(xid)
      if xids.contains(id) {
        fail("mismatch:window-duplicate-writer-xid")
      }
      xids[id] = tx
    }
    commits[tx] = {
      "connection": Json(connection),
      "writerXid": xid,
      "writerPid": row.at("pid"),
      "writerLogin": row.at("login"),
      "checkpointSeq": Json(note),
      "commitStartSeq": call.at("startSeq"),
      "commitEndSeq": call.at("endSeq"),
      "traceCommitRequestSeq": Json(requests.at(tx)),
      "traceCommitOkSeq": Json(oks.at(tx)),
    }
  }
  for case in cases {
    let tx = sql_string_v1(window_object_v2(case.native).at("tx"))
    let checkpoint = fetch_number_v1(
      window_object_v2(commits.at(tx)).at("checkpointSeq"),
      65536,
    )
    if case.native_note >= checkpoint ||
      case.delivery_notes.any(note => note >= checkpoint) {
      fail("unsupported:window-result-not-delivered-before-commit")
    }
  }
  { cases, commits, trace_events: events, trace_by_seq, begin_by_tx: begins, }
}
