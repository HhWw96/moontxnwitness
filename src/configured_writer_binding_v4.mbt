///|
priv struct WriterCheckpointV4 {
  tx : String
  xid : String?
  login : Json
  pid : Json
  note : Int32
}

///|
priv struct WriterCommitV4 {
  checkpoint : WriterCheckpointV4
  call : String
  start : Int32
  mut response : (Int32, Json)?
}

///|
fn writer_checkpoint_v4(
  raw : Json,
  peer : Json,
  note : Int32,
) -> (String, WriterCheckpointV4) raise {
  let frame = orm_exact(raw, [
    "connection", "tx", "sql", "driverPid", "statusBefore", "statusAfter", "nativeStatus",
    "nativeTag", "nativeColumns", "nativeBase64", "deliveredText",
  ])
  if frame.at("sql") !=
    Json(
      "SELECT pg_catalog.jsonb_build_object('peer'," +
      effects_peer_sql_v4() +
      ",'xid',pg_catalog.pg_current_xact_id_if_assigned()::text,'login',SESSION_USER,'pid',pg_catalog.pg_backend_pid())::text",
    ) ||
    frame.at("statusBefore") != Json(2) ||
    frame.at("statusAfter") != Json(2) ||
    frame.at("nativeStatus") != Json(2) ||
    frame.at("nativeTag") != Json("SELECT 1") ||
    frame.at("nativeColumns") != Json([{ "oid": 25, "format": 0 }]) {
    fail("mismatch:writer-checkpoint-request")
  }
  let encoded = sql_string_v1(frame.at("nativeBase64"))
  if encoded.length() > 5464 {
    fail("mismatch:writer-checkpoint-native-size")
  }
  let bytes = @base64.decode(encoded[:], ignore_whitespace=false)
  let delivery = sql_string_v1(frame.at("deliveredText"))
  if bytes.length() > 4096 ||
    @base64.encode(bytes[:]) != encoded ||
    @utf8.decode(bytes[:], ignore_bom=false) != delivery {
    fail("mismatch:writer-checkpoint-native-delivery")
  }
  let row = orm_exact(sql_json_v1(delivery, 4096), [
    "peer", "xid", "login", "pid",
  ])
  if row.at("peer") != peer ||
    row.at("pid") != frame.at("driverPid") ||
    fetch_number_v1(row.at("pid"), 2147483647) == 0 ||
    orm_native_text(row.at("login"), 63).is_empty() {
    fail("mismatch:writer-checkpoint-peer-or-driver")
  }
  let xid = match row.at("xid") {
    Null => None
    value => Some(effects_xid_v4(value))
  }
  (
    orm_native_text(frame.at("connection"), 512),
    {
      tx: orm_native_text(frame.at("tx"), 512),
      xid,
      login: row.at("login"),
      pid: row.at("pid"),
      note,
    },
  )
}

///|
fn writer_trace_events_v4(
  trace_text : String,
  work : SourceWorkV4,
) -> (
  Map[Int32, Json],
  Map[String, Int32],
  Map[String, Int32],
  Map[String, Int32],
) raise {
  let trace = source_object_v4(sql_json_v1(trace_text, 8388608))
  let events : Map[Int32, Json] = Map([])
  let begins : Map[String, Int32] = Map([])
  let requests : Map[String, Int32] = Map([])
  let ends : Map[String, Int32] = Map([])
  let mut previous = 0
  for raw in orm_array(required(trace, "events", "writer-trace")) {
    work.charge()
    let event = source_object_v4(raw)
    let seq = fetch_number_v1(required(event, "seq", "writer-trace"), 100000000)
    if seq <= previous {
      fail("mismatch:writer-trace-sequence")
    }
    previous = seq
    let kind = sql_string_v1(required(event, "kind", "writer-trace"))
    let index = match kind {
      "begin" => begins
      "commit_request" => requests
      "commit_ok" | "rollback_ok" | "disconnect" => ends
      _ => continue
    }
    let tx = orm_native_text(required(event, "tx", "writer-trace"), 512)
    if tx.is_empty() || index.contains(tx) {
      fail("mismatch:writer-trace-boundary")
    }
    index[tx] = seq
    events[seq] = raw
  }
  (events, begins, requests, ends)
}

///|
fn writer_commits_v4(
  lifecycle : String,
  trace : String,
  peer : Json,
  work : SourceWorkV4,
  by_tx? : Map[String, Json],
) -> Map[String, Json] raise {
  let (events, begins, requests, ends) = writer_trace_events_v4(trace, work)
  if !lifecycle.has_suffix("\n") || orm_utf8_size(lifecycle) > 8388608 {
    fail("mismatch:writer-lifecycle-size-or-tail")
  }
  let lines = lifecycle.split("\n").to_array()
  if lines.length() < 3 || lines.length() > 65537 {
    fail("mismatch:writer-lifecycle-length")
  }
  let prefix = StringBuilder()
  let pending : Map[String, WriterCheckpointV4] = Map([])
  let commits : Map[String, WriterCommitV4] = Map([])
  let checkpoints : Map[String, String] = Map([])
  let bindings : Map[String, Json] = Map([])
  let mut domain = Json::null()
  for index in 0..<(lines.length() - 1) {
    work.charge()
    let seq = index + 1
    let line = lines[index].to_owned()
    let raw = sql_json_v1(line, 524288)
    let e = source_object_v4(raw)
    if e.get("seq") != Some(Json(seq)) {
      fail("mismatch:writer-lifecycle-sequence")
    }
    let kind = sql_string_v1(required(e, "kind", "writer-lifecycle"))
    if index == 0 {
      domain = required(e, "processMonotonicDomain", "writer-header")
      if kind != "header" ||
        e.get("format") != Some(Json("moontxnwitness-instrumentation/v1")) ||
        e.get("diagnosticOnly") != Some(Json(true)) ||
        orm_native_text(domain, 512).is_empty() {
        fail("mismatch:writer-lifecycle-header")
      }
    } else if index == lines.length() - 2 {
      let _ = orm_exact(raw, ["seq", "kind", "records", "prefixSha256"])
      if kind != "seal" ||
        e.at("records") != Json(index) ||
        e.at("prefixSha256") != Json(v3_dislock_sha256(prefix.to_string())) {
        fail("mismatch:writer-lifecycle-seal")
      }
      break
    } else {
      if kind == "header" ||
        kind == "seal" ||
        e.get("processMonotonicDomain") != Some(domain) {
        fail("mismatch:writer-lifecycle-domain")
      }
      if kind == "configured-writer-checkpoint" {
        let (connection, checkpoint) = writer_checkpoint_v4(
          sql_json_v1(
            sql_string_v1(required(e, "frameText", "writer-lifecycle")),
            61440,
          ),
          peer,
          seq,
        )
        let begin = match begins.get(checkpoint.tx) {
          Some(n) => source_object_v4(events.at(n))
          None => fail("mismatch:writer-checkpoint-missing-begin")
        }
        if begin.get("connection") != Some(Json(connection)) ||
          commits.contains(connection) {
          fail("mismatch:writer-checkpoint-connection")
        }
        match checkpoint.xid {
          Some(xid) => {
            if checkpoints.get(xid) is Some(tx) && tx != checkpoint.tx {
              fail("mismatch:writer-checkpoint-duplicate-XID")
            }
            checkpoints[xid] = checkpoint.tx
          }
          None => ()
        }
        pending[connection] = checkpoint
      } else if kind == "call-start" {
        let connection = sql_string_v1(
          required(e, "connection", "writer-call-start"),
        )
        commits.remove(connection)
        if pending.get(connection) is Some(checkpoint) {
          pending.remove(connection)
          if e.get("method") == Some(Json("commit")) &&
            e.get("tx") == Some(Json(checkpoint.tx)) {
            commits[connection] = {
              checkpoint,
              call: sql_string_v1(required(e, "callId", "writer-call-start")),
              start: seq,
              response: None,
            }
          }
        }
      } else if kind == "commit-response" {
        let connection = sql_string_v1(
          required(e, "connection", "writer-commit-response"),
        )
        if commits.get(connection) is Some(commit) {
          if commit.response is Some(_) {
            fail("mismatch:writer-duplicate-commit-response")
          }
          commit.response = Some((seq, raw))
        }
      } else if kind == "call-end" && e.get("method") == Some(Json("commit")) {
        let connection = sql_string_v1(
          required(e, "connection", "writer-call-end"),
        )
        if commits.get(connection) is Some(commit) {
          commits.remove(connection)
          let tx = commit.checkpoint.tx
          if e.get("callId") != Some(Json(commit.call)) ||
            e.get("tx") != Some(Json(tx)) {
            fail("mismatch:writer-commit-call")
          }
          if e.get("succeeded") == Some(Json(true)) &&
            e.get("nativeCommandTag") == Some(Json("COMMIT")) &&
            commit.response is Some((response_seq, response)) {
            let r = source_object_v4(response)
            let refs = source_object_v4(
              required(e, "journalEventSeqs", "writer-call-end"),
            )
            if requests.get(tx) is Some(request) && ends.get(tx) is Some(end) {
              if !(begins.at(tx) < request && request < end) ||
                source_object_v4(events.at(end)).at("kind") != Json("commit_ok") ||
                r.get("request") != Some(Json(request)) ||
                r.get("commandTag") != Some(Json("COMMIT")) ||
                r.get("transactionStatus") != Some(Json(0)) ||
                refs.get("commit_request") != Some(Json(request)) ||
                refs.get("commit_ok") != Some(Json(end)) {
                fail("mismatch:writer-commit-evidence")
              }
              let xid_value = match commit.checkpoint.xid {
                Some(xid) => Json(xid)
                None => Json::null()
              }
              let binding : Json = {
                "tx": Json(tx),
                "connection": Json(connection),
                "writerXid": xid_value,
                "writerPid": commit.checkpoint.pid,
                "writerLogin": commit.checkpoint.login,
                "checkpointSeq": Json(commit.checkpoint.note),
                "commitStartSeq": Json(commit.start),
                "commitResponseSeq": Json(response_seq),
                "commitEndSeq": Json(seq),
                "traceCommitRequestSeq": Json(request),
                "traceCommitSeq": Json(end),
              }
              if by_tx is Some(records) {
                if records.contains(tx) {
                  fail("mismatch:writer-duplicate-commit")
                }
                records[tx] = binding
              }
              if commit.checkpoint.xid is Some(xid) {
                if bindings.contains(xid) {
                  fail("mismatch:writer-duplicate-commit")
                }
                bindings[xid] = binding
              }
            }
          }
        }
      } else if [
          "connection-close", "pool-reset", "pool-checkin", "pool-invalidate",
        ].contains(kind) {
        if e.get("connection") is Some(String(connection)) {
          pending.remove(connection)
          commits.remove(connection)
        }
      }
    }
    prefix.write_string(line)
    prefix.write_string("\n")
  }
  bindings
}

///|
fn configured_writer_session_commits_v4(
  effects : Map[String, Json],
  session_input : String,
  peer : Json,
  work : SourceWorkV4,
  by_tx? : Map[String, Json],
) -> Map[String, Json] raise {
  let session = orm_exact(sql_json_v1(session_input, 33554432), [
    "format", "configText", "lifecycleText", "diagnosticTraceText", "sourceInputsText",
  ])
  let install = orm_exact(
    sql_json_v1(sql_string_v1(session.at("sourceInputsText")), 12582912),
    ["format", "policyText", "logText", "receiptText", "sourceContextText"],
  )
  if session.at("format") != Json("moontxnwitness-configured-session-input/v1") ||
    session.at("configText") != effects.at("configText") ||
    install.at("format") !=
    Json("moontxnwitness-configured-installation-input/v1") ||
    install.at("policyText") != effects.at("policyText") ||
    install.at("logText") != effects.at("installationLogText") ||
    install.at("receiptText") != effects.at("installationReceiptText") {
    fail("mismatch:writer-session-installation-binding")
  }
  writer_commits_v4(
    sql_string_v1(session.at("lifecycleText")),
    sql_string_v1(session.at("diagnosticTraceText")),
    peer,
    work,
    by_tx?,
  )
}

///|
fn configured_writer_binding_v4(
  effect : Map[String, Json],
  commits : Map[String, Json],
) -> Json? raise {
  let xid = sql_string_v1(effect.at("writerXid"))
  match commits.get(xid) {
    Some(binding) => {
      let b = source_object_v4(binding)
      if b.at("writerPid") != effect.at("writerPid") ||
        b.at("writerLogin") != effect.at("writerLogin") {
        fail("mismatch:writer-effect-identity")
      }
      Some(binding)
    }
    None => None
  }
}

///|
/// Match observed effects to confirmed client commits while keeping coverage open.
pub fn verify_configured_writer_bindings_v4_json(
  effects_input : String,
  session_input : String,
  options : String,
) -> String {
  let format = "moontxnwitness-configured-writer-bindings/v4"
  try {
    let limits = source_object_v4(sql_json_v1(options, 8192))
    known_fields(
      limits,
      ["maxRows", "maxChecks", "maxInstallationChecks", "maxBindingChecks"],
      "writer-options",
    )
    let work : SourceWorkV4 = {
      limit: source_wire_limit_v4(limits, "maxBindingChecks", 1000000),
      checks: 0,
    }
    limits.remove("maxBindingChecks")
    let effects_raw = sql_json_v1(effects_input, 25165824)
    let effect_result = source_object_v4(
      verify_configured_effects_snapshot_v4(effects_raw, Json(limits)),
    )
    let observation = source_object_v4(effect_result.at("observation"))
    let peer = match observation.get("peer") {
      Some(value) => value
      None => fail("mismatch:writer-effect-peer-required")
    }
    let commits = configured_writer_session_commits_v4(
      source_object_v4(effects_raw),
      session_input,
      peer,
      work,
    )
    let matched : Array[Json] = []
    let unmatched : Array[Json] = []
    for raw in orm_array(observation.at("observations")) {
      work.charge()
      match configured_writer_binding_v4(source_object_v4(raw), commits) {
        Some(binding) =>
          matched.push({ "effect": raw, "clientCommit": binding })
        None => unmatched.push(raw)
      }
    }
    (
      {
        "format": Json(format),
        "status": "checked-observed-bindings",
        "valid": true,
        "matchedEffects": Json(matched),
        "unmatchedEffects": Json(unmatched),
        "confirmedClientCheckpoints": Json(commits.length()),
        "checks": Json(work.checks),
        "maxBindingChecks": Json(work.limit),
        "effectsLogSha256": effect_result.at("effectsLogSha256"),
        "installationLogSha256": effect_result.at("installationLogSha256"),
        "sessionInputSha256": Json(v3_dislock_sha256(session_input)),
        "sourceFactsProduced": false,
        "sourceAuthenticated": false,
        "writerWindowVerified": false,
        "isolationAnalysisReady": false,
      } : Json).stringify()
  } catch {
    error =>
      (
        {
          "format": Json(format),
          "status": if error.to_string().contains("budget:") {
            Json("unknown")
          } else {
            Json("invalid")
          },
          "valid": false,
          "reason": Json(error.to_string()),
          "sourceFactsProduced": false,
          "sourceAuthenticated": false,
          "writerWindowVerified": false,
          "isolationAnalysisReady": false,
        } : Json).stringify()
  }
}
