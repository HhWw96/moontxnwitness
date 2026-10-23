///|
priv struct ClassificationIntervalV3 {
  transaction : String
  connection : String
  domain : String
  begin_ns : Int64
  end_ns : Int64
  start_call : Json
  end_call : Json
}

///|
priv struct ClassificationIntervalsV3 {
  complete : Bool
  reason : String
  edges : Array[Edge]
  sources : Map[Edge, Array[Json]]
  evidence : Json
}

///|
priv struct ClassificationSourceV3 {
  trace_text : String
  interval_text : String?
  lifecycle_text : String?
  index_text : String?
}

///|
fn classification_source_v3(text : String) -> ClassificationSourceV3 raise {
  if orm_utf8_size(text) > 33554432 { fail("Classification source envelope exceeds 32 MiB UTF-8") }
  let root = object_fields(guarded_json(text, limit=33554432), "classification source")
  if root.get("format") != Some("moontxnwitness-classification-source/v1".to_json()) {
    if orm_utf8_size(text) > 8388608 { fail("Classification trace exceeds 8 MiB UTF-8") }
    return { trace_text: text, interval_text: None, lifecycle_text: None, index_text: None }
  }
  known_fields(root, ["format", "traceText", "intervalEvidenceText", "lifecycleText", "journalIndexText"], "classification source envelope")
  let trace_text = v3_dislock_text(required(root, "traceText", "classification source"), "traceText")
  let interval_text = v3_dislock_text(required(root, "intervalEvidenceText", "classification source"), "intervalEvidenceText")
  let lifecycle_text = v3_dislock_text(required(root, "lifecycleText", "classification source"), "lifecycleText")
  let index_text = v3_dislock_text(required(root, "journalIndexText", "classification source"), "journalIndexText")
  for value in [trace_text, interval_text, lifecycle_text, index_text] { if orm_utf8_size(value) > 8388608 { fail("Each classification source component is limited to 8 MiB UTF-8") } }
  { trace_text, interval_text: Some(interval_text), lifecycle_text: Some(lifecycle_text), index_text: Some(index_text) }
}

///|
fn classification_interval_ns(value : Json) -> Int64 raise {
  let text = v3_dislock_text(value, "monotonicNs")
  let number = relation_v3_int64(text)
  if number < 0L { fail("monotonicNs must be a canonical nonnegative int64 decimal string") }
  number
}

///|
fn classification_interval_digest(value : Json) -> String raise {
  let text = v3_dislock_text(value, "source digest")
  if text.length() != 64 || !text.iter().all(ch => (ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f')) { fail("Expected a lower-case SHA-256 digest") }
  text
}

///|
fn classification_interval_event(reference : Json, events : Map[String, Json], kind : String, tx : String) -> Unit raise {
  let seq = v3_capture_seq(reference, "journal event reference")
  let event = object_fields(match events.get(seq.to_double().to_json().stringify()) { Some(value) => value; None => fail("Missing referenced original journal event") }, "journal event")
  if event.get("kind") != Some(kind.to_json()) || event.get("tx") != Some(tx.to_json()) { fail("Interval event reference does not match original kind and transaction") }
}

///|
fn classification_intervals_v3(source : ClassificationSourceV3, normalized : Json) -> ClassificationIntervalsV3 raise {
  let absent : ClassificationIntervalsV3 = { complete: false, reason: "explicit-client-call-interval-evidence-required", edges: [], sources: Map([]), evidence: Json::null() }
  let (interval_text, lifecycle_text, index_text) = match (source.interval_text, source.lifecycle_text, source.index_text) { (Some(a), Some(b), Some(c)) => (a, b, c); _ => return absent }
  let supplied = object_fields(guarded_json(interval_text, limit=8388608), "interval evidence")
  known_fields(supplied, ["format", "sourceTraceSha256", "sourceLifecycleSha256", "sourceJournalIndexSha256", "records"], "interval evidence")
  if supplied.get("format") != Some("moontxnwitness-client-intervals/v1".to_json()) { fail("Unsupported client interval format") }
  if classification_interval_digest(required(supplied, "sourceTraceSha256", "interval evidence")) != v3_dislock_sha256(source.trace_text) ||
    classification_interval_digest(required(supplied, "sourceLifecycleSha256", "interval evidence")) != v3_dislock_sha256(lifecycle_text) ||
    classification_interval_digest(required(supplied, "sourceJournalIndexSha256", "interval evidence")) != v3_dislock_sha256(index_text) { fail("Client interval evidence does not bind exact trace/lifecycle/index bytes") }
  if !lifecycle_text.has_suffix("\n") { fail("Lifecycle journal must be newline terminated") }
  let lines = lifecycle_text.split("\n").to_array()
  if lines.length() < 3 || lines.length() > 32769 || !lines[lines.length() - 1].is_empty() { fail("Incomplete or oversized lifecycle journal") }
  let records : Array[Json] = []
  let prefix = StringBuilder()
  for index in 0..<(lines.length() - 1) {
    let line = lines[index].to_owned()
    if line.is_empty() || orm_utf8_size(line) > 1048576 { fail("Invalid lifecycle record byte budget") }
    let raw = guarded_json(line, limit=1048576)
    let fields = object_fields(raw, "lifecycle record")
    if required(fields, "seq", "lifecycle record") != (index + 1).to_json() { fail("Lifecycle sequence must be contiguous") }
    if index == 0 {
      if fields.get("kind") != Some("header".to_json()) || fields.get("format") != Some("moontxnwitness-instrumentation/v1".to_json()) { fail("Expected instrumentation lifecycle header") }
      let _ = identifier(required(fields, "processMonotonicDomain", "header"), "processMonotonicDomain")
    } else if index == lines.length() - 2 {
      if fields.get("kind") != Some("seal".to_json()) || fields.get("records") != Some(index.to_json()) || fields.get("prefixSha256") != Some(v3_dislock_sha256(prefix.to_string()).to_json()) { fail("Lifecycle seal or prefix digest differs") }
    } else if fields.get("kind") == Some("header".to_json()) || fields.get("kind") == Some("seal".to_json()) { fail("Lifecycle contains an early header or seal") }
    if index != lines.length() - 2 { prefix.write_string(line); prefix.write_string("\n") }
    records.push(raw)
  }
  if required(supplied, "records", "interval evidence") != records.to_json() { fail("Interval records are not the exact original lifecycle records") }
  let domain = identifier(required(object_fields(records[0], "header"), "processMonotonicDomain", "header"), "processMonotonicDomain")
  let n = object_fields(normalized, "normalized")
  let trace_events = presence_capture_array(required(n, "observations", "normalized"), "observations")
  let events : Map[String, Json] = Map([])
  let begin_events : Map[String, Json] = Map([])
  let transactions = presence_capture_array(required(n, "transactions", "normalized"), "transactions")
  let outcomes : Map[String, Json] = Map([])
  let connections : Map[String, String] = Map([])
  for tx_raw in transactions {
    let tx = object_fields(tx_raw, "transaction")
    let id = identifier(required(tx, "id", "transaction"), "transaction.id")
    outcomes[id] = required(tx, "status", "transaction")
    connections[id] = identifier(required(tx, "connection", "transaction"), "connection")
  }
  for raw in trace_events {
    let fields = object_fields(raw, "trace event")
    events[required(fields, "seq", "event").stringify()] = raw
    if fields.get("kind") == Some("begin".to_json()) { begin_events[identifier(required(fields, "tx", "begin"), "begin.tx")] = raw }
  }
  let index = object_fields(guarded_json(index_text, limit=8388608), "journal index")
  let index_complete = index.get("closed") == Some(true.to_json()) && index.get("sourceClosed") == Some(true.to_json()) && index.get("eventCount") == Some(trace_events.length().to_json()) && index.get("durableSeq") == Some(trace_events.length().to_json()) && index.get("gaps") == Some(Json::array([]))
  let starts : Map[String, Json] = Map([])
  let ends : Map[String, Json] = Map([])
  let first : Map[String, Json] = Map([])
  let commits : Map[String, Json] = Map([])
  let observed_statements : Map[String, Bool] = Map([])
  let incomplete_tx : Map[String, Bool] = Map([])
  let responses : Map[String, Map[String, Array[Json]]] = Map([])
  for raw in records {
    let record = object_fields(raw, "lifecycle record")
    let kind = identifier(required(record, "kind", "lifecycle record"), "kind")
    if kind == "header" || kind == "seal" { continue }
    if record.contains("monotonicNs") {
      if record.get("processMonotonicDomain") != Some(domain.to_json()) { fail("A lifecycle journal cannot silently change monotonic clock domain") }
      let _ = classification_interval_ns(record.at("monotonicNs"))
    }
    if kind == "commit-response" {
      let connection = identifier(required(record, "connection", "commit response"), "connection")
      let request = required(record, "request", "commit response")
      let _ = v3_capture_seq(request, "commit request")
      let by_request = responses.get_or_default(connection, Map([]))
      let group = by_request.get_or_default(request.stringify(), [])
      group.push(raw)
      by_request[request.stringify()] = group
      responses[connection] = by_request
    }
    if kind != "call-start" && kind != "call-end" { continue }
    let id = identifier(required(record, "callId", "call"), "callId")
    let call_method = identifier(required(record, "method", "call"), "method")
    if !["execute", "executemany", "commit", "rollback"].contains(call_method) { fail("Unsupported lifecycle call method") }
    let connection = identifier(required(record, "connection", "call"), "connection")
    let _ = classification_interval_ns(required(record, "monotonicNs", "call"))
    if record.get("processMonotonicDomain") != Some(domain.to_json()) { fail("Call clock domain differs from its source header") }
    let tx = match required(record, "tx", "call") { Null => None; value => Some(identifier(value, "call.tx")) }
    match tx {
      Some(tx) => {
        if connections.get(tx) != Some(connection) { fail("Call transaction/connection does not match original capture") }
        let refs = object_fields(required(record, "journalEventSeqs", "call"), "journalEventSeqs")
        for event_kind in ["begin", "commit_request", "commit_ok", "rollback_ok", "disconnect"] {
          match refs.get(event_kind) { Some(seq) => classification_interval_event(seq, events, event_kind, tx); None => () }
        }
      }
      None => ()
    }
    if kind == "call-start" {
      if starts.contains(id) || ends.contains(id) { fail("Call identity is duplicated or starts after its end") }
      starts[id] = raw
      match tx {
        Some(tx) if call_method == "execute" || call_method == "executemany" => {
          if !first.contains(tx) || classification_interval_ns(record.at("monotonicNs")) < classification_interval_ns(object_fields_unchecked_v3(first.at(tx)).at("monotonicNs")) { first[tx] = raw }
        }
        _ => ()
      }
    } else {
      if ends.contains(id) { fail("Call end identity is duplicated") }
      let start = object_fields(match starts.get(id) { Some(value) => value; None => fail("Call end has no original call start") }, "call start")
      for key in ["method", "connection", "tx", "processMonotonicDomain"] { if start.get(key) != record.get(key) { fail("Call start/end identity differs") } }
      if classification_interval_ns(record.at("monotonicNs")) < classification_interval_ns(start.at("monotonicNs")) { fail("Call interval reversed") }
      let _ = presence_capture_bool(required(record, "succeeded", "call end"), "succeeded")
      ends[id] = raw
      match tx {
        Some(tx) => {
          match record.get("statementSeq") {
            Some(value) if value != Json::null() => {
              classification_interval_event(value, events, "statement", tx)
              if call_method != "execute" && call_method != "executemany" { fail("Non-SQL method claims a statement") }
              if observed_statements.contains(value.stringify()) { fail("An original SQL statement is claimed by multiple calls") }
              observed_statements[value.stringify()] = true
            }
            _ => ()
          }
          let refs = object_fields(record.at("journalEventSeqs"), "journalEventSeqs")
          if record.contains("nativeCommandTag") && call_method != "commit" { fail("Only a commit method may claim a native COMMIT tag") }
          if call_method == "commit" && record.get("succeeded") == Some(true.to_json()) && record.get("nativeCommandTag") == Some("COMMIT".to_json()) && refs.contains("commit_ok") && refs.contains("commit_request") {
            let request = refs.at("commit_request")
            let mut confirmed = false
            let returned = responses.get_or_default(connection, Map([])).get_or_default(request.stringify(), [])
            for candidate in returned {
              let response = object_fields_unchecked_v3(candidate)
              if response.get("kind") == Some("commit-response".to_json()) && response.get("connection") == Some(connection.to_json()) && response.get("request") == Some(request) && response.get("commandTag") == Some("COMMIT".to_json()) && response.get("transactionStatus") == Some((0).to_json()) {
                let response_seq = v3_capture_seq(required(response, "seq", "commit response"), "seq")
                let start_seq = v3_capture_seq(required(start, "seq", "call start"), "seq")
                let end_seq = v3_capture_seq(required(record, "seq", "call end"), "seq")
                let response_ns = classification_interval_ns(required(response, "monotonicNs", "commit response"))
                if response_seq > start_seq && response_seq < end_seq && response_ns >= classification_interval_ns(start.at("monotonicNs")) && response_ns <= classification_interval_ns(record.at("monotonicNs")) { confirmed = true }
              }
            }
            if confirmed && returned.length() == 1 {
              if commits.contains(tx) { fail("A transaction has multiple confirmed commit calls") }
              commits[tx] = raw
            }
          }
        }
        None => ()
      }
    }
  }
  for id, start_raw in starts {
    if !ends.contains(id) {
      match object_fields_unchecked_v3(start_raw).get("tx") { Some(String(tx)) => incomplete_tx[tx] = true; _ => () }
    }
  }
  for raw in trace_events {
    let fields = object_fields(raw, "trace event")
    if fields.get("kind") == Some("statement".to_json()) && !observed_statements.contains(required(fields, "seq", "statement").stringify()) { incomplete_tx[identifier(required(fields, "tx", "statement"), "tx")] = true }
  }
  let coverage = object_fields(required(n, "coverage", "normalized"), "coverage")
  let capture_gaps = presence_capture_array(required(coverage, "gaps", "coverage"), "gaps")
  let metadata_gap = capture_gaps.any(raw => {
    let code = object_fields_unchecked_v3(raw).get("code")
    code == Some("instrumentation_metadata_missing".to_json()) || code == Some("instrumentation_metadata_unsealed".to_json())
  })
  let intervals : Array[ClassificationIntervalV3] = []
  let mut complete = index_complete && !metadata_gap
  for tx_raw in transactions {
    let tx = object_fields(tx_raw, "transaction")
    let id = identifier(tx.at("id"), "id")
    if outcomes.get(id) != Some("committed".to_json()) { continue }
    if !first.contains(id) || !commits.contains(id) || incomplete_tx.contains(id) || metadata_gap || !index_complete { complete = false; continue }
    let start = first.at(id)
    let end = commits.at(id)
    let start_fields = object_fields(start, "first SQL call")
    let end_fields = object_fields(end, "confirmed COMMIT call")
    let start_refs = object_fields(start_fields.at("journalEventSeqs"), "first call references")
    if !start_refs.contains("begin") || start_refs.at("begin") != object_fields(begin_events.at(id), "begin").at("seq") { complete = false; continue }
    let begin_ns = classification_interval_ns(start_fields.at("monotonicNs"))
    let end_ns = classification_interval_ns(end_fields.at("monotonicNs"))
    if end_ns < begin_ns { fail("Transaction client interval reversed") }
    intervals.push({ transaction: id, connection: connections.at(id), domain, begin_ns, end_ns, start_call: start, end_call: end })
  }
  if intervals.length() > 128 { return { complete: false, reason: "client-interval-transaction-limit", edges: [], sources: Map([]), evidence: { "traceBytesBound": true, "lifecycleBytesBound": true, "journalIndexBytesBound": true, "journalSegmentPayloadsRecomputed": false } } }
  let edges : Array[Edge] = []
  let sources : Map[Edge, Array[Json]] = Map([])
  for before in intervals {
    for after in intervals {
      if before.transaction == after.transaction || before.domain != after.domain || before.end_ns >= after.begin_ns { continue }
      let edge : Edge = { from: before.transaction, to: after.transaction, kind: RT, key: None, from_op: None, to_op: None, from_version: None, to_version: None, reason: "Confirmed COMMIT response completed before another first SQL call on the same explicitly bound process monotonic clock" }
      edges.push(edge)
      sources[edge] = [{ "beforeCommitCall": before.end_call, "afterFirstSqlCall": after.start_call, "processMonotonicDomain": domain.to_json() }]
    }
  }
  { complete, reason: if complete { "complete-bound-client-call-intervals" } else { "missing-unconfirmed-or-unsealed-client-intervals" }, edges, sources,
    evidence: { "format": "moontxnwitness-client-intervals/v1", "sourceIntervalEvidenceSha256": v3_dislock_sha256(interval_text).to_json(), "sourceTraceSha256": supplied.at("sourceTraceSha256"), "sourceLifecycleSha256": supplied.at("sourceLifecycleSha256"), "sourceJournalIndexSha256": supplied.at("sourceJournalIndexSha256"), "traceBytesBound": true, "lifecycleBytesBound": true, "journalIndexBytesBound": true, "journalSegmentPayloadsRecomputed": false, "intervals": intervals.map(interval => ({ "tx": interval.transaction.to_json(), "connection": interval.connection.to_json(), "processMonotonicDomain": interval.domain.to_json(), "firstSqlBeforeNs": interval.begin_ns.to_string().to_json(), "confirmedCommitAfterNs": interval.end_ns.to_string().to_json() } : Json)).to_json(), "scope": "Explicit DBAPI call boundaries and original source byte bindings; no server snapshot inference or collector authenticity certification" } }
}
