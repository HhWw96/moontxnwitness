///|
fn capture_gap(code : String, message : String) -> Json {
  { "code": Json(code), "message": Json(message) }
}

///|
fn capture_result(
  status : String,
  gaps : Array[Json],
  history : Json,
) -> String {
  let result : Json = {
    "schema": 1,
    "status": Json(status),
    "coverage": { "complete": Json(status == "ready"), "gaps": Json(gaps) },
    "history": history,
  }
  result.stringify(indent=2)
}

///|
fn capture_time(event : Map[String, Json], path : String) -> Int64 raise {
  match timestamp(event, "time", path) {
    Some(time) => time
    None => fail(path + ".time must be a non-negative safe integer")
  }
}

///|
fn capture_active_tx(
  event : Map[String, Json],
  ids : Map[String, Int32],
  active : Map[String, Bool],
  path : String,
) -> Int32 raise {
  let id = identifier(required(event, "tx", path), path + ".tx")
  match (ids.get(id), active.get(id)) {
    (Some(index), Some(true)) => index
    _ => fail(path + ": transaction must have an unmatched begin event")
  }
}

///|
/// Validate a complete capture envelope before exposing an ordinary history.
/// Declared capture scope is an assumption, not authenticated source evidence.
pub fn normalize_capture_json(text : String) -> String {
  try {
    let root = object_fields(guarded_json(text, limit=8388608), "capture")
    known_fields(
      root,
      ["traceSchema", "clockDomain", "scope", "events", "gaps"],
      "capture",
    )
    if required(root, "traceSchema", "capture") != Json(1) {
      fail("traceSchema must be 1")
    }
    let _ = identifier(required(root, "clockDomain", "capture"), "clockDomain")
    let scope = object_fields(required(root, "scope", "capture"), "scope")
    known_fields(scope, ["exclusiveWriters"], "scope")
    let exclusive = match required(scope, "exclusiveWriters", "scope") {
      True => true
      False => false
      _ => fail("scope.exclusiveWriters must be a boolean")
    }
    let gaps : Array[Json] = []
    if !exclusive {
      gaps.push(
        capture_gap(
          "writer_scope_unproven", "Other writers have not been excluded from the declared capture scope",
        ),
      )
    }
    let raw_gaps = match required(root, "gaps", "capture") {
      Array(items) => items
      _ => fail("gaps must be an array")
    }
    for raw_gap in raw_gaps {
      let gap = object_fields(raw_gap, "gaps entry")
      known_fields(gap, ["code", "message"], "gaps entry")
      let code = identifier(required(gap, "code", "gap"), "gap.code")
      let message = match required(gap, "message", "gap") {
        String(s) if s.length() > 0 && s.length() <= 4096 => s
        _ =>
          fail(
            "gap.message must be a nonempty string of at most 4096 code units",
          )
      }
      gaps.push(capture_gap(code, message))
    }
    let events = match required(root, "events", "capture") {
      Array(items) => items
      _ => fail("events must be an array")
    }
    if events.length() > 65536 {
      fail("At most 65,536 capture events are supported")
    }
    let initial : Map[String, String] = Map([])
    let ids : Map[String, Int32] = Map([])
    let active : Map[String, Bool] = Map([])
    let txs : Array[Transaction] = []
    let mut snapshot_seen = false
    let mut expected_seq = 1L
    let mut last_time = 0L
    let mut operation_count = 0
    for index, raw_event in events {
      let path = "events[" + index.to_string() + "]"
      let event = object_fields(raw_event, path)
      let seq = match required(event, "seq", path) {
        Number(n, ..) if n >= 1.0 &&
          n <= 9007199254740991.0 &&
          n.to_int64().to_double() == n => n.to_int64()
        _ => fail(path + ".seq must be a positive safe integer")
      }
      if seq < expected_seq {
        fail(path + ": duplicate or out-of-order sequence number")
      }
      if seq > expected_seq {
        gaps.push(
          capture_gap("sequence_gap", path + ": one or more events are missing"),
        )
      }
      expected_seq = seq + 1L
      let time = capture_time(event, path)
      if time < last_time {
        fail(path + ": event time goes backwards in clockDomain")
      }
      last_time = time
      let kind = identifier(required(event, "kind", path), path + ".kind")
      match kind {
        "snapshot" => {
          known_fields(
            event,
            ["kind", "seq", "time", "initial", "consistent"],
            path,
          )
          if snapshot_seen || txs.length() > 0 {
            fail("Exactly one snapshot must precede every transaction")
          }
          snapshot_seen = true
          match required(event, "consistent", path) {
            True => ()
            False =>
              gaps.push(
                capture_gap(
                  "inconsistent_snapshot", "Initialization was not captured from a consistent database state",
                ),
              )
            _ => fail(path + ".consistent must be a boolean")
          }
          let raw_initial = object_fields(
            required(event, "initial", path),
            path + ".initial",
          )
          for key, value in raw_initial {
            let _ = identifier(Json(key), "initial key")
            initial[key] = identifier(value, "initial." + key)
          }
        }
        "begin" => {
          known_fields(event, ["kind", "seq", "time", "tx"], path)
          if !snapshot_seen {
            fail("A snapshot must precede begin events")
          }
          let id = identifier(required(event, "tx", path), path + ".tx")
          if ids.contains(id) {
            fail(path + ": transaction identifiers cannot be reused")
          }
          if txs.length() >= 512 {
            fail("At most 512 captured transactions are supported")
          }
          ids[id] = txs.length()
          active[id] = true
          txs.push({
            id,
            status: Unknown,
            ops: [],
            start: Some(time),
            end: None,
          })
        }
        "op" => {
          known_fields(event, ["kind", "seq", "time", "tx", "op"], path)
          let tx_index = capture_active_tx(event, ids, active, path)
          let op = object_fields(required(event, "op", path), path + ".op")
          known_fields(op, ["type", "key", "version"], path + ".op")
          let kind = match required(op, "type", path) {
            String("read") => Read
            String("write") => Write
            _ => fail(path + ".op.type must be read or write")
          }
          let key = identifier(required(op, "key", path), path + ".op.key")
          let version = identifier(
            required(op, "version", path),
            path + ".op.version",
          )
          if !initial.contains(key) {
            gaps.push(
              capture_gap(
                "missing_initial",
                "No captured initial version for key " + key,
              ),
            )
          }
          operation_count += 1
          if operation_count > 10000 {
            fail("At most 10,000 captured operations are supported")
          }
          txs[tx_index].ops.push({ kind, key, version, })
        }
        "end" => {
          known_fields(event, ["kind", "seq", "time", "tx", "status"], path)
          let tx_index = capture_active_tx(event, ids, active, path)
          let status = match required(event, "status", path) {
            String("committed") => Committed
            String("aborted") => Aborted
            String("unknown") => {
              gaps.push(
                capture_gap(
                  "unknown_commit", "The final outcome of a captured transaction is unknown",
                ),
              )
              Unknown
            }
            _ => fail(path + ".status must be committed, aborted or unknown")
          }
          let tx = txs[tx_index]
          active[tx.id] = false
          txs[tx_index] = { ..tx, status, end: Some(time), }
        }
        "sql" => {
          // Raw SQL is transport evidence; only normalized op events carry model semantics.
          known_fields(
            event,
            [
              "kind", "seq", "time", "tx", "phase", "sql", "mapped", "affectedRows",
              "errorClass", "sqlstate", "returnedRows", "exhausted", "parameters",
              "rows",
            ],
            path,
          )
          match event.get("phase") {
            None => ()
            Some(String(phase)) if [
                "execute-request", "execute-ack", "execute-error", "fetch", "fetch-error",
                "commit-ack", "commit-error", "rollback-ack", "rollback-error",
              ].contains(phase) => ()
            _ => fail(path + ".phase is unsupported")
          }
          for field in ["sql", "sqlstate"] {
            match event.get(field) {
              None | Some(Null) | Some(String(_)) => ()
              _ => fail(path + "." + field + " must be a string or null")
            }
          }
          match event.get("errorClass") {
            None | Some(String(_)) => ()
            _ => fail(path + ".errorClass must be a string")
          }
          for field in ["mapped", "exhausted"] {
            match event.get(field) {
              None | Some(True) | Some(False) => ()
              _ => fail(path + "." + field + " must be a boolean")
            }
          }
          for field in ["affectedRows", "returnedRows"] {
            match event.get(field) {
              None => ()
              Some(Number(n, ..)) if n >=
                (if field == "affectedRows" { -1.0 } else { 0.0 }) &&
                n <= 9007199254740991.0 &&
                n.to_int64().to_double() == n => ()
              _ => fail(path + "." + field + " must be a safe integer count")
            }
          }
          match event.get("rows") {
            None | Some(Array(_)) => ()
            _ => fail(path + ".rows must be an array")
          }
          if event.get("mapped") == Some(Json(false)) {
            gaps.push(
              capture_gap(
                "unmapped_sql", "A SQL observation has no supported semantic mapping",
              ),
            )
          }
          match event.get("tx") {
            None | Some(Null) => ()
            Some(_) => {
              let _ = capture_active_tx(event, ids, active, path)
            }
          }
        }
        _ => fail(path + ": unsupported event kind " + kind)
      }
    }
    if !snapshot_seen {
      gaps.push(
        capture_gap("missing_snapshot", "No initial snapshot was captured"),
      )
    }
    for id, open in active {
      if open {
        gaps.push(
          capture_gap(
            "outstanding_transaction",
            "No end event for transaction " + id,
          ),
        )
      }
    }
    // Validate identities even when coverage is incomplete; never expose partial history.
    let writes : Map[String, Map[String, Bool]] = Map([])
    for tx in txs {
      for op in tx.ops {
        if op.kind == Write {
          let versions = writes.get_or_default(op.key, Map([]))
          if versions.contains(op.version) ||
            initial.get(op.key) == Some(op.version) {
            fail(
              "Captured write versions must be unique per key and distinct from initialization",
            )
          }
          versions[op.version] = true
          writes[op.key] = versions
        }
      }
    }
    if gaps.length() > 0 {
      return capture_result("inconclusive", gaps, Json::null())
    }
    let history = history_json({
      model: Serializable,
      initial,
      version_orders: Map([]),
      transactions: txs,
    })
    match parse_history(history.stringify()) {
      Err(reason) => fail("Normalized history rejected: " + reason)
      Ok(h) => {
        let findings = validate_history(h)
        if findings.length() > 0 {
          fail("Normalized history rejected: " + findings[0].message)
        }
      }
    }
    capture_result("ready", [], history)
  } catch {
    error =>
      capture_result(
        "invalid",
        [capture_gap("invalid_capture", error.to_string())],
        Json::null(),
      )
  }
}
