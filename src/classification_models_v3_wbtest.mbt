///|
fn classification26_test_report(
  trace : Json,
  options? : String = "{\"models\":[\"adya-pl-1-v1\",\"adya-pl-2-v1\",\"adya-pl-2.99-v1\",\"elle-generalized-si-v1\",\"adya-pl-3-v1\",\"strict-pl-ss-v1\"]}",
) -> Json raise {
  @json.parse(classify_v3_json(trace.stringify(), options))
}

///|
fn classification26_test_model(report : Json, name : String) -> Json raise {
  object_fields_unchecked_v3(capture_field(report, "models")).at(name)
}

///|
fn classification26_test_list(body : Array[Json]) -> Json {
  let trace = v3_test_trace(body)
  let fields = object_fields_unchecked_v3(trace)
  fields["dataModel"] = "append-list-v1".to_json()
  let events = presence_capture_array(fields.at("events"), "events") catch {
    _ => []
  }
  object_fields_unchecked_v3(events[0])["initial"] = { "x": [], "y": [] }
  trace
}

///|
fn classification26_test_list_skew() -> Json {
  classification26_test_list([
    { "kind": "begin", "tx": "A", "connection": "a" },
    { "kind": "begin", "tx": "B", "connection": "b" },
    { "kind": "list_read", "tx": "A", "key": "y", "items": [] },
    { "kind": "list_read", "tx": "B", "key": "x", "items": [] },
    { "kind": "append", "tx": "A", "key": "x", "id": "a", "value": "same" },
    { "kind": "append", "tx": "B", "key": "y", "id": "b", "value": "same" },
    { "kind": "commit_request", "tx": "A" },
    { "kind": "commit_ok", "tx": "A" },
    { "kind": "commit_request", "tx": "B" },
    { "kind": "commit_ok", "tx": "B" },
  ])
}

///|
/// Synthetic call evidence only; no driver or database is invoked here.
fn classification26_test_envelope(
  trace : Json,
  windows : Array[(Int64, Int64)],
) -> Json raise {
  let text = trace.stringify()
  let normalized = @json.parse(normalize_capture_v3_json(text))
  let n = object_fields(normalized, "normalized")
  let events = presence_capture_array(n.at("observations"), "observations")
  let txs = presence_capture_array(n.at("transactions"), "transactions")
  let records : Array[Json] = [
    {
      "kind": "header",
      "format": "moontxnwitness-instrumentation/v1",
      "diagnosticOnly": true,
      "processMonotonicDomain": "test-process",
    },
  ]
  for index, raw_tx in txs {
    let tx = object_fields(raw_tx, "transaction")
    if tx.at("status") != "committed".to_json() {
      continue
    }
    let id = identifier(tx.at("id"), "id")
    let connection = tx.at("connection")
    let begin = tx.at("beginSeq")
    let (start_ns, end_ns) = windows[index]
    let statements = events.filter(raw => {
      let fields = object_fields_unchecked_v3(raw)
      fields.get("tx") == Some(id.to_json()) &&
      fields.get("kind") == Some("statement".to_json())
    })
    let calls : Array[Json] = if statements.is_empty() {
      [Json::null()]
    } else {
      statements.map(raw => object_fields_unchecked_v3(raw).at("seq"))
    }
    for ordinal, statement in calls {
      let call_id = "sql-" + id + "-" + ordinal.to_string()
      records.push({
        "kind": "call-start",
        "callId": call_id.to_json(),
        "method": "execute",
        "connection": connection,
        "tx": id.to_json(),
        "processMonotonicDomain": "test-process",
        "monotonicNs": (start_ns + ordinal.to_int64() * 2L)
        .to_string()
        .to_json(),
        "statementSeq": Json::null(),
        "journalEventSeqs": { "begin": begin },
      })
      records.push({
        "kind": "call-end",
        "callId": call_id.to_json(),
        "method": "execute",
        "connection": connection,
        "tx": id.to_json(),
        "processMonotonicDomain": "test-process",
        "monotonicNs": (start_ns + ordinal.to_int64() * 2L + 1L)
        .to_string()
        .to_json(),
        "succeeded": true,
        "statementSeq": statement,
        "journalEventSeqs": { "begin": begin },
      })
    }
    let request = events.filter(raw => {
        let fields = object_fields_unchecked_v3(raw)
        fields.get("kind") == Some("commit_request".to_json()) &&
        fields.get("tx") == Some(id.to_json())
      })[0]
    let commit = events.filter(raw => {
        let fields = object_fields_unchecked_v3(raw)
        fields.get("kind") == Some("commit_ok".to_json()) &&
        fields.get("tx") == Some(id.to_json())
      })[0]
    let request_seq = object_fields_unchecked_v3(request).at("seq")
    let commit_seq = object_fields_unchecked_v3(commit).at("seq")
    let call_id = "commit-" + id
    records.push({
      "kind": "call-start",
      "callId": call_id.to_json(),
      "method": "commit",
      "connection": connection,
      "tx": id.to_json(),
      "processMonotonicDomain": "test-process",
      "monotonicNs": (end_ns - 2L).to_string().to_json(),
      "statementSeq": Json::null(),
      "journalEventSeqs": { "begin": begin },
    })
    records.push({
      "kind": "commit-response",
      "connection": connection,
      "request": request_seq,
      "commandTag": "COMMIT",
      "transactionStatus": 0,
      "processMonotonicDomain": "test-process",
      "monotonicNs": (end_ns - 1L).to_string().to_json(),
    })
    records.push({
      "kind": "call-end",
      "callId": call_id.to_json(),
      "method": "commit",
      "connection": connection,
      "tx": id.to_json(),
      "processMonotonicDomain": "test-process",
      "monotonicNs": end_ns.to_string().to_json(),
      "succeeded": true,
      "nativeCommandTag": "COMMIT",
      "statementSeq": Json::null(),
      "journalEventSeqs": {
        "begin": begin,
        "commit_request": request_seq,
        "commit_ok": commit_seq,
      },
    })
  }
  classification26_test_pack_envelope(text, records, events.length())
}

///|
fn classification26_test_pack_envelope(
  trace_text : String,
  records : Array[Json],
  event_count : Int,
) -> Json {
  let prefix = StringBuilder()
  for index, record in records {
    object_fields_unchecked_v3(record)["seq"] = (index + 1).to_json()
    prefix.write_string(record.stringify())
    prefix.write_string("\n")
  }
  let seal : Json = {
    "seq": (records.length() + 1).to_json(),
    "kind": "seal",
    "records": records.length().to_json(),
    "prefixSha256": v3_dislock_sha256(prefix.to_string()).to_json(),
  }
  let all = records.copy()
  all.push(seal)
  prefix.write_string(seal.stringify())
  prefix.write_string("\n")
  let lifecycle_text = prefix.to_string()
  let index_text = (
    {
      "closed": true,
      "sourceClosed": true,
      "eventCount": event_count.to_json(),
      "durableSeq": event_count.to_json(),
      "gaps": [],
    } : Json).stringify()
  let interval_text = (
    {
      "format": "moontxnwitness-client-intervals/v1",
      "sourceTraceSha256": v3_dislock_sha256(trace_text).to_json(),
      "sourceLifecycleSha256": v3_dislock_sha256(lifecycle_text).to_json(),
      "sourceJournalIndexSha256": v3_dislock_sha256(index_text).to_json(),
      "records": all.to_json(),
    } : Json).stringify()
  {
    "format": "moontxnwitness-classification-source/v1",
    "traceText": trace_text.to_json(),
    "intervalEvidenceText": interval_text.to_json(),
    "lifecycleText": lifecycle_text.to_json(),
    "journalIndexText": index_text.to_json(),
  }
}

///|
test "classification26 empty register history checks five models and leaves strict unknown without intervals" {
  let report = classification26_test_report(v3_test_completed([]))
  assert_eq(
    capture_field(report, "algorithm"),
    "v3-isolation-model-1".to_json(),
  )
  for name in classification_models_v3_names() {
    assert_eq(
      capture_field(classification26_test_model(report, name), "status"),
      (if name == "strict-pl-ss-v1" {
        "inconclusive"
      } else {
        "checked-compatible"
      }).to_json(),
    )
  }
}

///|
test "classification26 G0 refutes every stronger model through logical closure" {
  let report = classification26_test_report(
    classification_test_cycle_trace("G0"),
  )
  for name in classification_models_v3_names() {
    assert_eq(
      capture_field(classification26_test_model(report, name), "status"),
      "refuted".to_json(),
    )
  }
}

///|
test "classification26 write skew is compatible with generalized SI but refutes serial and repeatable-item models" {
  let report = classification26_test_report(
    classification_test_cycle_trace("G2-item"),
  )
  assert_eq(
    capture_field(
      classification26_test_model(report, "elle-generalized-si-v1"),
      "status",
    ),
    "checked-compatible".to_json(),
  )
  assert_eq(
    capture_field(classification26_test_model(report, "adya-pl-2-v1"), "status"),
    "checked-compatible".to_json(),
  )
  assert_eq(
    capture_field(
      classification26_test_model(report, "adya-pl-2.99-v1"),
      "status",
    ),
    "refuted".to_json(),
  )
  assert_eq(
    capture_field(classification26_test_model(report, "adya-pl-3-v1"), "status"),
    "refuted".to_json(),
  )
}

///|
test "classification26 confirmed aborted reads refute PL2 despite conservative projection gaps" {
  let trace = v3_test_trace([
    { "kind": "begin", "tx": "W", "connection": "w" },
    {
      "kind": "write",
      "tx": "W",
      "key": "x",
      "version": "x1",
      "predecessor": "x0",
    },
    { "kind": "rollback_ok", "tx": "W" },
    { "kind": "begin", "tx": "R", "connection": "r" },
    { "kind": "read", "tx": "R", "key": "x", "version": "x1" },
    { "kind": "commit_request", "tx": "R" },
    { "kind": "commit_ok", "tx": "R" },
  ])
  let report = classification26_test_report(trace)
  assert_eq(
    capture_field(classification_test_rule(report, "G1a"), "status"),
    "refuted".to_json(),
  )
  assert_eq(
    capture_field(classification26_test_model(report, "adya-pl-2-v1"), "status"),
    "refuted".to_json(),
  )
  assert_eq(capture_field(report, "status"), "refuted".to_json())
}

///|
test "classification26 overwritten intermediate read has a direct G1b proof" {
  let trace = v3_test_trace([
    { "kind": "begin", "tx": "W", "connection": "w" },
    {
      "kind": "write",
      "tx": "W",
      "key": "x",
      "version": "x1",
      "predecessor": "x0",
    },
    {
      "kind": "write",
      "tx": "W",
      "key": "x",
      "version": "x2",
      "predecessor": "x1",
    },
    { "kind": "commit_request", "tx": "W" },
    { "kind": "commit_ok", "tx": "W" },
    { "kind": "begin", "tx": "R", "connection": "r" },
    { "kind": "read", "tx": "R", "key": "x", "version": "x1" },
    { "kind": "commit_request", "tx": "R" },
    { "kind": "commit_ok", "tx": "R" },
  ])
  let report = classification26_test_report(trace)
  assert_eq(
    capture_field(classification_test_rule(report, "G1b"), "status"),
    "refuted".to_json(),
  )
  assert_eq(
    capture_field(classification26_test_model(report, "adya-pl-2-v1"), "status"),
    "refuted".to_json(),
  )
}

///|
test "classification26 own overlay mismatch is an operational INT counterexample" {
  let trace = v3_test_completed([
    {
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "x1",
      "predecessor": "x0",
    },
    { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
  ])
  let report = classification26_test_report(trace)
  assert_eq(
    capture_field(classification_test_rule(report, "INT"), "status"),
    "refuted".to_json(),
  )
  assert_eq(
    capture_field(
      classification26_test_model(report, "elle-generalized-si-v1"),
      "status",
    ),
    "refuted".to_json(),
  )
  assert_eq(
    capture_field(classification26_test_model(report, "adya-pl-3-v1"), "status"),
    "inconclusive".to_json(),
  )
  assert_eq(
    capture_field(
      capture_field(
        classification26_test_model(report, "adya-pl-3-v1"),
        "internalValidity",
      ),
      "status",
    ),
    "not-satisfied".to_json(),
  )
}

///|
test "classification26 savepoint rollback restores own overlay without erasing the external snapshot" {
  let trace = v3_test_completed([
    { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
    { "kind": "savepoint", "tx": "A", "name": "s", "instance": "s1" },
    {
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "x1",
      "predecessor": "x0",
    },
    { "kind": "read", "tx": "A", "key": "x", "version": "x1" },
    { "kind": "rollback_to", "tx": "A", "instance": "s1" },
    { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
  ])
  let report = classification26_test_report(trace)
  assert_eq(
    capture_field(classification_test_rule(report, "INT"), "status"),
    "checked-compatible".to_json(),
  )
  assert_eq(
    capture_field(
      classification26_test_model(report, "elle-generalized-si-v1"),
      "status",
    ),
    "checked-compatible".to_json(),
  )
}

///|
test "classification26 repeated read changes violate INT and SI while PL2 remains compatible" {
  let trace = v3_test_trace([
    { "kind": "begin", "tx": "R", "connection": "r" },
    { "kind": "read", "tx": "R", "key": "x", "version": "x0" },
    { "kind": "begin", "tx": "W", "connection": "w" },
    {
      "kind": "write",
      "tx": "W",
      "key": "x",
      "version": "x1",
      "predecessor": "x0",
    },
    { "kind": "commit_request", "tx": "W" },
    { "kind": "commit_ok", "tx": "W" },
    { "kind": "read", "tx": "R", "key": "x", "version": "x1" },
    { "kind": "commit_request", "tx": "R" },
    { "kind": "commit_ok", "tx": "R" },
  ])
  let report = classification26_test_report(trace)
  assert_eq(
    capture_field(classification_test_rule(report, "INT"), "status"),
    "refuted".to_json(),
  )
  assert_eq(
    capture_field(
      classification26_test_model(report, "elle-generalized-si-v1"),
      "status",
    ),
    "refuted".to_json(),
  )
  assert_eq(
    capture_field(classification26_test_model(report, "adya-pl-2-v1"), "status"),
    "checked-compatible".to_json(),
  )
}

///|
test "classification26 list write skew distinguishes SI from serializability" {
  let report = classification26_test_report(classification26_test_list_skew())
  assert_eq(
    capture_field(
      classification26_test_model(report, "elle-generalized-si-v1"),
      "status",
    ),
    "checked-compatible".to_json(),
  )
  assert_eq(
    capture_field(classification26_test_model(report, "adya-pl-3-v1"), "status"),
    "refuted".to_json(),
  )
}

///|
test "classification26 missing append order stays unknown instead of being completed" {
  let trace = classification26_test_list([
    { "kind": "begin", "tx": "A", "connection": "a" },
    { "kind": "append", "tx": "A", "key": "x", "id": "a", "value": "same" },
    { "kind": "commit_request", "tx": "A" },
    { "kind": "commit_ok", "tx": "A" },
    { "kind": "begin", "tx": "B", "connection": "b" },
    { "kind": "append", "tx": "B", "key": "x", "id": "b", "value": "same" },
    { "kind": "commit_request", "tx": "B" },
    { "kind": "commit_ok", "tx": "B" },
  ])
  let report = classification26_test_report(trace)
  assert_eq(capture_field(report, "dependencyGraphComplete"), false.to_json())
  assert_eq(
    capture_field(classification26_test_model(report, "adya-pl-1-v1"), "status"),
    "inconclusive".to_json(),
  )
}

///|
test "classification26 list abort source and intermediate append prefix have explicit proofs" {
  let aborted = classification26_test_list([
    { "kind": "begin", "tx": "W", "connection": "w" },
    { "kind": "append", "tx": "W", "key": "x", "id": "a", "value": "same" },
    { "kind": "rollback_ok", "tx": "W" },
    { "kind": "begin", "tx": "R", "connection": "r" },
    {
      "kind": "list_read",
      "tx": "R",
      "key": "x",
      "items": [{ "id": "a", "value": "same" }],
    },
    { "kind": "commit_request", "tx": "R" },
    { "kind": "commit_ok", "tx": "R" },
  ])
  let report = classification26_test_report(aborted)
  assert_eq(
    capture_field(classification_test_rule(report, "G1a"), "status"),
    "refuted".to_json(),
  )
  let intermediate = classification26_test_list([
    { "kind": "begin", "tx": "W", "connection": "w" },
    { "kind": "append", "tx": "W", "key": "x", "id": "a", "value": "same" },
    { "kind": "begin", "tx": "R", "connection": "r" },
    {
      "kind": "list_read",
      "tx": "R",
      "key": "x",
      "items": [{ "id": "a", "value": "same" }],
    },
    { "kind": "append", "tx": "W", "key": "x", "id": "b", "value": "same" },
    { "kind": "commit_request", "tx": "W" },
    { "kind": "commit_ok", "tx": "W" },
    { "kind": "commit_request", "tx": "R" },
    { "kind": "commit_ok", "tx": "R" },
  ])
  let report = classification26_test_report(intermediate)
  assert_eq(
    capture_field(classification_test_rule(report, "G1b"), "status"),
    "refuted".to_json(),
  )
  assert_eq(
    capture_field(classification26_test_model(report, "adya-pl-2-v1"), "status"),
    "refuted".to_json(),
  )
}

///|
test "classification26 list own append visibility is checked operationally" {
  let trace = classification26_test_list([
    { "kind": "begin", "tx": "A", "connection": "a" },
    { "kind": "append", "tx": "A", "key": "x", "id": "a", "value": "same" },
    { "kind": "list_read", "tx": "A", "key": "x", "items": [] },
    { "kind": "commit_request", "tx": "A" },
    { "kind": "commit_ok", "tx": "A" },
  ])
  let report = classification26_test_report(trace)
  assert_eq(
    capture_field(classification_test_rule(report, "INT"), "status"),
    "refuted".to_json(),
  )
  assert_eq(
    capture_field(classification26_test_model(report, "adya-pl-3-v1"), "status"),
    "inconclusive".to_json(),
  )
  assert_eq(
    capture_field(
      capture_field(
        classification26_test_model(report, "adya-pl-3-v1"),
        "internalValidity",
      ),
      "status",
    ),
    "not-satisfied".to_json(),
  )
}

///|
test "classification26 optional client evidence can finish strict checks" {
  let trace = v3_test_completed([])
  let envelope = classification26_test_envelope(trace, [(10L, 100L)])
  let report = classification26_test_report(envelope)
  assert_eq(
    capture_field(
      classification26_test_model(report, "strict-pl-ss-v1"),
      "status",
    ),
    "checked-compatible".to_json(),
  )
  assert_eq(
    capture_field(
      capture_field(report, "intervalEvidence"),
      "journalSegmentPayloadsRecomputed",
    ),
    false.to_json(),
  )
}

///|
fn classification26_test_stale_trace() -> Json {
  v3_test_trace([
    { "kind": "begin", "tx": "W", "connection": "w" },
    {
      "kind": "write",
      "tx": "W",
      "key": "x",
      "version": "x1",
      "predecessor": "x0",
    },
    { "kind": "commit_request", "tx": "W" },
    { "kind": "commit_ok", "tx": "W" },
    { "kind": "begin", "tx": "R", "connection": "r" },
    { "kind": "read", "tx": "R", "key": "x", "version": "x0" },
    { "kind": "commit_request", "tx": "R" },
    { "kind": "commit_ok", "tx": "R" },
  ])
}

///|
test "classification26 confirmed COMMIT before another actual SQL call refutes strict only" {
  let envelope = classification26_test_envelope(
    classification26_test_stale_trace(),
    [(10L, 100L), (200L, 300L)],
  )
  let report = classification26_test_report(envelope)
  assert_eq(
    capture_field(classification26_test_model(report, "adya-pl-3-v1"), "status"),
    "checked-compatible".to_json(),
  )
  assert_eq(
    capture_field(
      classification26_test_model(report, "strict-pl-ss-v1"),
      "status",
    ),
    "refuted".to_json(),
  )
  assert_true(!v3_test_items(report, "realTimeDependencies").is_empty())
  assert_eq(
    capture_field(
      @json.parse(
        verify_classification_v3_json(envelope.stringify(), report.stringify()),
      ),
      "valid",
    ),
    true.to_json(),
  )
}

///|
test "classification26 equal monotonic boundaries do not create realtime order" {
  let envelope = classification26_test_envelope(
    classification26_test_stale_trace(),
    [(10L, 100L), (100L, 200L)],
  )
  let report = classification26_test_report(envelope)
  assert_eq(capture_field(report, "realTimeDependencies"), Json::array([]))
  assert_eq(
    capture_field(
      classification26_test_model(report, "strict-pl-ss-v1"),
      "status",
    ),
    "checked-compatible".to_json(),
  )
}

///|
test "classification26 differing original bytes or digests reject interval evidence" {
  let envelope = classification26_test_envelope(v3_test_completed([]), [
    (10L, 100L),
  ])
  let fields = object_fields_unchecked_v3(envelope)
  let original_report = classify_v3_json(
    envelope.stringify(),
    "{\"models\":[\"strict-pl-ss-v1\"]}",
  )
  fields["traceText"] = (v3_test_completed([]).stringify() + " ").to_json()
  assert_eq(
    capture_field(classification26_test_report(envelope), "status"),
    "invalid".to_json(),
  )
  assert_eq(
    capture_field(
      @json.parse(
        verify_classification_v3_json(envelope.stringify(), original_report),
      ),
      "valid",
    ),
    false.to_json(),
  )
}

///|
test "classification26 SQL proof options remain explicit and old categories remain unchanged" {
  let trace = d3_test_fixture()
  let report = classification26_test_report(
    trace,
    options="{\"models\":[\"adya-pl-3-v1\"],\"normalizationOptions\":{\"sqlProof\":\"dislock-f9946f0-sql-proof-1\"}}",
  )
  assert_eq(
    capture_field(classification26_test_model(report, "adya-pl-3-v1"), "status"),
    "checked-compatible".to_json(),
  )
  let old = classification_test_result(
    classification_test_cycle_trace("G2-item"),
  )
  assert_eq(capture_field(old, "algorithm"), "v3-register-category-1".to_json())
  assert_eq(capture_field(old, "acceptsIsolationModels"), false.to_json())
}

///|
fn classification26_test_nonadj_oracle(kinds : Array[Int]) -> Bool {
  let pairs = [(0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1)]
  let matrix = Array::make(9, 0)
  for index, pair in pairs {
    matrix[pair.0 * 3 + pair.1] = kinds[index]
  }
  for a in 0..<3 {
    for b in 0..<3 {
      if a == b {
        continue
      }
      let candidates = [
        [matrix[a * 3 + b], matrix[b * 3 + a]],
        [
          matrix[a * 3 + b],
          matrix[b * 3 + (3 - a - b)],
          matrix[(3 - a - b) * 3 + a],
        ],
      ]
      for cycle in candidates {
        if cycle.contains(0) || !cycle.contains(3) {
          continue
        }
        let mut valid = true
        for index, kind in cycle {
          if kind == 3 && cycle[(index + 1) % cycle.length()] == 3 {
            valid = false
          }
        }
        if valid {
          return true
        }
      }
    }
  }
  false
}

///|
test "classification26 nonadjacent search matches all 4096 typed three-node graphs including cyclic wrap" {
  let transactions : Array[Transaction] = [
    { id: "0", status: Committed, ops: [], start: None, end: None, },
    { id: "1", status: Committed, ops: [], start: None, end: None, },
    { id: "2", status: Committed, ops: [], start: None, end: None, },
  ]
  let pairs = [(0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1)]
  for code in 0..<4096 {
    let mut rest = code
    let kinds : Array[Int] = []
    let edges : Array[Edge] = []
    for pair in pairs {
      let kind = rest % 4
      rest /= 4
      kinds.push(kind)
      if kind != 0 {
        edges.push(
          classification_test_edge(
            pair.0,
            pair.1,
            match kind {
              1 => WW
              2 => WR
              _ => RW
            },
          ),
        )
      }
    }
    let budget : ClassificationV3Budget = {
      max_states: 100000,
      max_edge_checks: 1000000,
      states: 0,
      edge_checks: 0,
      limited: false,
      reason: "complete",
    }
    let found = classification_models_v3_nonadj(
      transactions,
      edges,
      adjacency(transactions, edges),
      budget,
    )
    assert_eq(!found.is_empty(), classification26_test_nonadj_oracle(kinds))
    assert_eq(budget.limited, false)
    for index, edge in found {
      assert_true(
        !(edge.kind == RW && found[(index + 1) % found.length()].kind == RW),
      )
    }
  }
}
