///|
priv struct OrmProfileDerivedV3 {
  normalized : Json
  history : History
}

///|
priv struct OrmProfileWindowV3 {
  records : Array[Json]
  opened : Int
  quiesced : Int
  closed : Int
}

///|
fn orm_profile_diagnostic_gaps_v3(
  gaps : Array[Json],
  index? : Bool = false,
) -> Unit raise {
  let seen : Map[String, Bool] = Map([])
  for raw in gaps {
    let gap = orm_exact(raw, ["code", "message"])
    let code = orm_text(required(gap, "code", "gap"))
    let message = orm_text(required(gap, "message", "gap"))
    let allowed = if code == "diagnostic_instrumentation_only" {
      message ==
      "No verified initial/version/predicate mapping; raw observations never grant complete analysis coverage."
    } else if !index && code == "source_unsealed" {
      message == "Journal and explicit source window have not both been sealed."
    } else if !index && code == "diagnostic_only" {
      message ==
      "This export is incomplete diagnostic evidence, not a complete analysis input."
    } else {
      false
    }
    orm_assert(
      allowed && !seen.contains(code),
      "Unresolved or duplicate raw diagnostic gap",
    )
    seen[code] = true
  }
  orm_assert(
    seen.contains("diagnostic_instrumentation_only"),
    "Original diagnostic instrumentation gap must remain",
  )
  if !index {
    orm_assert(
      seen.contains("source_unsealed") && seen.contains("diagnostic_only"),
      "Original diagnostic source/export boundary must remain",
    )
  }
}

///|
fn orm_profile_window_v3(
  text : String,
  nonce : Json,
) -> OrmProfileWindowV3 raise {
  orm_assert(
    orm_utf8_size(text) <= 8388608 && text.has_suffix("\n"),
    "Complete bounded profile lifecycle JSONL required",
  )
  let lines = text.split("\n").to_array()
  orm_assert(
    lines.length() >= 6 &&
    lines.length() <= 65537 &&
    lines[lines.length() - 1].is_empty(),
    "Profile lifecycle record bound",
  )
  let records : Array[Json] = []
  let prefix = StringBuilder()
  let mut opened = -1
  let mut quiesced = -1
  let mut closed = -1
  let mut domain = ""
  for i in 0..<(lines.length() - 1) {
    let line = lines[i].to_owned()
    orm_assert(
      !line.is_empty() && orm_utf8_size(line) <= 524288,
      "Profile lifecycle record byte bound",
    )
    let raw = guarded_json(line, limit=524288)
    let value = object_fields(raw, "profile lifecycle")
    orm_equal(
      required(value, "seq", "lifecycle"),
      (i + 1).to_json(),
      "Contiguous profile lifecycle sequence",
    )
    let kind = orm_text(required(value, "kind", "lifecycle"))
    if i == 0 {
      orm_exact(raw, [
        "seq", "kind", "format", "diagnosticOnly", "processMonotonicDomain",
      ])
      |> ignore
      orm_equal(
        required(value, "format", "header"),
        "moontxnwitness-instrumentation/v1".to_json(),
        "Original instrumentation header",
      )
      orm_equal(
        required(value, "diagnosticOnly", "header"),
        true.to_json(),
        "Original diagnostic flag remains",
      )
      orm_assert(kind == "header", "Initial lifecycle header required")
      domain = identifier(
        required(value, "processMonotonicDomain", "header"),
        "process domain",
      )
    } else if i == lines.length() - 2 {
      orm_exact(raw, ["seq", "kind", "prefixSha256", "records"]) |> ignore
      orm_assert(kind == "seal", "Terminal lifecycle seal required")
      orm_equal(
        required(value, "records", "seal"),
        i.to_json(),
        "Lifecycle seal count",
      )
      orm_equal(
        required(value, "prefixSha256", "seal"),
        v3_dislock_sha256(prefix.to_string()).to_json(),
        "Original lifecycle prefix bytes",
      )
    } else {
      orm_equal(
        required(value, "processMonotonicDomain", "lifecycle"),
        domain.to_json(),
        "One process domain",
      )
      let ns = orm_text(required(value, "monotonicNs", "lifecycle"))
      orm_assert(
        ns.length() >= 1 && ns.length() <= 20,
        "Bounded monotonic decimal text",
      )
      for ch in ns.iter() {
        orm_assert(
          ch >= '0' && ch <= '9',
          "Monotonic timestamps remain decimal observations",
        )
      }
      if kind == "profile-window-open" ||
        kind == "profile-window-quiesced" ||
        kind == "profile-window-close" {
        orm_equal(
          required(value, "profile", "window"),
          "fastapi-users-sqlalchemy-7.0.0-pg18/1".to_json(),
          "Pinned profile window",
        )
        orm_equal(
          required(value, "installationNonce", "window"),
          nonce,
          "One actual installation nonce",
        )
        if kind == "profile-window-open" {
          orm_assert(
            opened < 0 && quiesced < 0 && closed < 0,
            "Exactly one initial profile window",
          )
          opened = i
        } else if kind == "profile-window-quiesced" {
          orm_assert(
            opened >= 0 && quiesced < 0 && closed < 0,
            "Profile quiescence order",
          )
          quiesced = i
        } else {
          orm_assert(
            opened >= 0 && quiesced > opened && closed < 0,
            "Profile finalization order",
          )
          closed = i
        }
      }
      orm_assert(
        ![
          "driver-error", "commit-error", "executemany-begin", "executemany-end",
          "executemany-result", "executemany-parameters", "executemany-nextset",
        ].contains(kind),
        "Unproven error/batch lifecycle cannot close profile coverage",
      )
    }
    records.push(raw)
    prefix.write_string(line)
    prefix.write_string("\n")
  }
  orm_assert(
    opened >= 0 &&
    opened < quiesced &&
    quiesced < closed &&
    closed < records.length() - 1,
    "Complete profile lifecycle window required",
  )
  { records, opened, quiesced, closed, }
}

///|
fn orm_profile_index_v3(
  index : Map[String, Json],
  events : Array[Json],
) -> Unit raise {
  orm_equal(
    required(index, "indexSchema", "index"),
    (1).to_json(),
    "Known journal index",
  )
  orm_equal(
    required(index, "traceSchema", "index"),
    (3).to_json(),
    "v3 journal index",
  )
  orm_equal(
    required(index, "closed", "index"),
    true.to_json(),
    "Journal tail synchronized before profile analysis",
  )
  // The generic observer intentionally has no full-source acceptance claim.
  orm_equal(
    required(index, "sourceClosed", "index"),
    false.to_json(),
    "Original diagnostic sourceClosed remains false",
  )
  orm_equal(
    required(index, "eventCount", "index"),
    events.length().to_json(),
    "Index/export event count",
  )
  orm_equal(
    required(index, "durableSeq", "index"),
    events.length().to_json(),
    "Index/export durable tail",
  )
  orm_assert(!events.is_empty(), "Actual initial snapshot required")
  orm_equal(
    required(index, "lastTime", "index"),
    orm_get(events[events.length() - 1], "time"),
    "Index/export tail time",
  )
  for field in ["activeTransactions", "commitRequests"] {
    orm_assert(
      orm_array(required(index, field, "index")).is_empty(),
      "Active/requested transaction prevents closure",
    )
  }
  let refs = orm_exact(required(index, "references", "index"), [
    "activeTransactions", "unreadResults", "versionSources",
  ])
  for field in ["activeTransactions", "unreadResults"] {
    orm_assert(
      orm_array(required(refs, field, "references")).is_empty(),
      "Active source/result reference prevents closure",
    )
  }
  orm_profile_diagnostic_gaps_v3(
    orm_array(required(index, "gaps", "index")),
    index=true,
  )
  let segments = orm_array(required(index, "segments", "index"))
  orm_assert(
    !segments.is_empty() && segments.length() <= 4096,
    "Bounded source segment descriptors required",
  )
  let mut next = 1L
  for raw in segments {
    let segment = object_fields(raw, "segment")
    let count = v3_capture_seq(
      required(segment, "eventCount", "segment"),
      "segment count",
    )
    let first = v3_capture_seq(
      required(segment, "firstSeq", "segment"),
      "first seq",
    )
    let last = v3_capture_seq(
      required(segment, "lastSeq", "segment"),
      "last seq",
    )
    orm_assert(
      count <= 65536L && first == next && last == first + count - 1L,
      "Segment descriptor sequence/count binding",
    )
    next = last + 1L
  }
  orm_assert(
    next == (events.length() + 1).to_int64(),
    "Segment descriptors exactly cover exported events",
  )
}

///|
fn orm_profile_source_refs_v3(
  window : OrmProfileWindowV3,
  installation : Map[String, Json],
  final_record : Map[String, Json],
  initial_controls : Array[OrmControl2],
  final_controls : Array[OrmControl2],
) -> Unit raise {
  let opened = object_fields(window.records[window.opened], "open")
  let closed = object_fields(window.records[window.closed], "close")
  let metadata = object_fields(
    required(installation, "metadata", "installation"),
    "metadata",
  )
  orm_assert(
    !initial_controls.is_empty() && !final_controls.is_empty(),
    "Actual initialization and finalization queries required",
  )
  let initial_commit = initial_controls[initial_controls.length() - 1]
  let final_commit = final_controls[final_controls.length() - 1]
  orm_assert(
    initial_commit.sql == "COMMIT" &&
    initial_commit.after == "IDLE" &&
    final_commit.sql == "COMMIT" &&
    final_commit.after == "IDLE",
    "Both actual control windows must commit",
  )
  orm_equal(
    required(opened, "initialCommitSourceSeq", "open"),
    initial_commit.seq.to_double().to_json(),
    "Opening references actual initialization COMMIT",
  )
  orm_equal(
    required(opened, "initialSnapshotSourceSeq", "open"),
    required(metadata, "initialSnapshotQuerySeq", "metadata"),
    "Opening references actual initialized snapshot",
  )
  orm_equal(
    required(closed, "finalCommitSourceSeq", "close"),
    final_commit.seq.to_double().to_json(),
    "Closing references actual finalization COMMIT",
  )
  orm_equal(
    required(closed, "finalSnapshotSourceSeq", "close"),
    required(final_record, "finalSnapshotQuerySeq", "final"),
    "Closing references actual final snapshot",
  )
  orm_equal(
    required(closed, "finalLedgerSourceSeq", "close"),
    required(final_record, "ledgerQuerySeq", "final"),
    "Closing references actual final ledger",
  )
}

///|
fn orm_profile_calls_v3(
  window : OrmProfileWindowV3,
  events : Array[Json],
  transactions : Array[Json],
) -> Json raise {
  let starts : Map[String, Map[String, Json]] = Map([])
  let ended : Map[String, Bool] = Map([])
  let statement_calls : Map[Int64, Bool] = Map([])
  let outcomes : Map[String, Bool] = Map([])
  let responses : Map[Int64, Map[String, Json]] = Map([])
  let txs : Map[String, Map[String, Json]] = Map([])
  for raw in transactions {
    let tx = object_fields(raw, "transaction")
    orm_assert(
      required(tx, "status", "transaction") != "unknown".to_json(),
      "Unconfirmed transaction outcome prevents promotion",
    )
    txs[orm_text(required(tx, "id", "transaction"))] = tx
  }
  for i, raw in window.records {
    let value = object_fields(raw, "lifecycle")
    let kind = orm_text(required(value, "kind", "lifecycle"))
    if kind == "call-start" {
      let id = identifier(required(value, "callId", "call"), "call id")
      orm_assert(!starts.contains(id), "Duplicate actual call identity")
      starts[id] = value
    } else if kind == "commit-response" {
      let request = v3_capture_seq(
        required(value, "request", "response"),
        "commit request",
      )
      orm_assert(
        request <= events.length().to_int64() && !responses.contains(request),
        "Actual response request binding",
      )
      let event = object_fields(events[request.to_int() - 1], "request")
      orm_equal(
        required(event, "kind", "request"),
        "commit_request".to_json(),
        "Actual COMMIT request event",
      )
      let tx = match txs.get(orm_text(required(event, "tx", "request"))) {
        Some(tx) => tx
        None => fail("Commit response lacks an original transaction")
      }
      orm_equal(
        required(value, "connection", "response"),
        required(tx, "connection", "transaction"),
        "COMMIT response connection",
      )
      orm_equal(
        required(value, "transactionStatus", "response"),
        (0).to_json(),
        "Actual IDLE after COMMIT response",
      )
      let tag = required(value, "commandTag", "response")
      orm_assert(
        tag == "COMMIT".to_json() || tag == "ROLLBACK".to_json(),
        "Actual native COMMIT/ROLLBACK response required",
      )
      orm_assert(
        i > window.opened && i < window.quiesced,
        "COMMIT response inside original worker window",
      )
      responses[request] = value
    } else if kind == "call-end" {
      let id = identifier(required(value, "callId", "call"), "call id")
      let start = match starts.get(id) {
        Some(start) => start
        None => fail("Call end without original start")
      }
      orm_assert(!ended.contains(id), "Duplicate actual call end")
      ended[id] = true
      for field in ["method", "connection", "tx"] {
        orm_equal(
          required(value, field, "call end"),
          required(start, field, "call start"),
          "Actual paired call " + field,
        )
      }
      orm_equal(
        required(value, "succeeded", "call"),
        true.to_json(),
        "Successful original driver calls required",
      )
      let call_method = orm_text(required(value, "method", "call"))
      orm_assert(
        ["execute", "commit", "rollback"].contains(call_method),
        "Only fixed single-statement profile calls",
      )
      match required(value, "tx", "call") {
        Null => {
          orm_assert(
            call_method != "execute",
            "A SQL execute cannot lack an original transaction",
          )
          for call in [start, value] {
            orm_equal(
              required(call, "statementSeq", "administrative call"),
              Json::null(),
              "Administrative completion cannot contain SQL",
            )
            orm_assert(
              object_fields(
                required(call, "journalEventSeqs", "administrative call"),
                "refs",
              ).is_empty(),
              "Administrative completion cannot assert transaction facts",
            )
          }
        }
        String(id) => {
          let tx = match txs.get(id) {
            Some(tx) => tx
            None => fail("Actual call transaction missing from original trace")
          }
          orm_equal(
            required(value, "connection", "call"),
            required(tx, "connection", "transaction"),
            "Actual call uses transaction connection",
          )
          let first = v3_capture_seq(
            required(start, "seq", "call start"),
            "call start",
          )
          orm_assert(
            first > (window.opened + 1).to_int64() && i < window.quiesced,
            "All transaction calls stay inside initialized/quiesced window",
          )
          let refs = object_fields(
            required(value, "journalEventSeqs", "call"),
            "event refs",
          )
          orm_equal(
            required(refs, "begin", "refs"),
            required(tx, "beginSeq", "tx"),
            "Actual call BEGIN reference",
          )
          if call_method == "execute" {
            match value.get("statementSeq") {
              Some(Number(n, ..)) if n > 0.0 &&
                n <= events.length().to_double() &&
                n.to_int().to_double() == n => {
                let seq = n.to_int()
                let statement = object_fields(events[seq - 1], "statement")
                orm_equal(
                  required(statement, "kind", "statement"),
                  "statement".to_json(),
                  "Actual execute statement reference",
                )
                orm_equal(
                  required(statement, "tx", "statement"),
                  id.to_json(),
                  "Actual execute transaction",
                )
                orm_assert(
                  !statement_calls.contains(n.to_int64()),
                  "Each original SQL statement has exactly one actual execute call",
                )
                statement_calls[n.to_int64()] = true
              }
              _ =>
                fail(
                  "Every fixed-profile execute requires its actual original statement; unmapped controls remain diagnostic",
                )
            }
          } else {
            let status = orm_text(required(tx, "status", "transaction"))
            let terminal = if status == "committed" {
              "commit_ok"
            } else {
              "rollback_ok"
            }
            orm_equal(
              required(refs, terminal, "refs"),
              required(tx, "endSeq", "transaction"),
              "Actual call terminal event reference",
            )
            if call_method == "commit" {
              let request = v3_capture_seq(
                required(refs, "commit_request", "refs"),
                "commit request",
              )
              let response = match responses.get(request) {
                Some(response) => response
                None => fail("COMMIT lacks an actual native response")
              }
              let response_seq = v3_capture_seq(
                required(response, "seq", "response"),
                "response sequence",
              )
              orm_assert(
                response_seq > first && response_seq < (i + 1).to_int64(),
                "Native response belongs inside this actual COMMIT call",
              )
              orm_equal(
                orm_get(events[request.to_int() - 1], "tx"),
                id.to_json(),
                "COMMIT request belongs to this transaction",
              )
              let expected_tag = (if status == "committed" {
                "COMMIT"
              } else {
                "ROLLBACK"
              }).to_json()
              orm_equal(
                required(value, "nativeCommandTag", "call"),
                expected_tag,
                "Native command agrees with transaction outcome",
              )
              orm_equal(
                required(response, "commandTag", "response"),
                expected_tag,
                "Original native response agrees with actual call and outcome",
              )
            } else {
              orm_assert(
                status == "aborted",
                "Rollback cannot establish a committed outcome",
              )
            }
            orm_assert(
              !outcomes.contains(id),
              "One confirmed terminal call per transaction",
            )
            outcomes[id] = true
          }
        }
        _ => fail("Actual call transaction must be a string or null")
      }
    }
  }
  orm_assert(
    starts.length() == ended.length(),
    "Unfinished actual driver call prevents promotion",
  )
  orm_assert(
    outcomes.length() == transactions.length(),
    "Every original transaction has confirmed driver completion",
  )
  for event in events {
    if orm_get(event, "kind") == "statement".to_json() {
      orm_assert(
        statement_calls.contains(
          v3_capture_seq(orm_get(event, "seq"), "statement"),
        ),
        "Original statement lacks actual execute delivery call",
      )
    }
  }
  {
    "pairedCalls": ended.length().to_json(),
    "confirmedTransactions": outcomes.length().to_json(),
    "statementCalls": statement_calls.length().to_json(),
  }
}

///|
fn orm_profile_derived_v3(
  events : Array[Json],
  facts : Array[Json],
  clock : Json,
) -> (OrmProfileDerivedV3, Array[Json]) raise {
  orm_assert(
    !facts.is_empty() && facts.length() <= 10000,
    "Nonempty bounded original SQL fact set required",
  )
  let by_rows : Map[Int64, Json] = Map([])
  let by_statement : Map[Int64, Json] = Map([])
  for fact in facts {
    let rows = v3_capture_seq(orm_get(fact, "rows"), "rows")
    let statement = v3_capture_seq(orm_get(fact, "statement"), "statement")
    orm_assert(
      statement < rows &&
      !by_rows.contains(rows) &&
      !by_statement.contains(statement),
      "Exact one-to-one original SQL/EOF fact binding",
    )
    by_rows[rows] = fact
    by_statement[statement] = fact
  }
  let derived : Array[Json] = []
  let origins : Array[Json] = []
  let original_to_derived : Map[Int64, Json] = Map([])
  let mut used_statements = 0
  let mut used_rows = 0
  for raw in events {
    let event = object_fields(raw, "original event")
    let kind = orm_text(required(event, "kind", "event"))
    let seq = v3_capture_seq(required(event, "seq", "event"), "event")
    if kind == "statement" {
      orm_assert(
        by_statement.contains(seq),
        "Every original statement requires a proven same-statement mapping",
      )
      used_statements += 1
      continue
    }
    let next = (derived.length() + 1).to_json()
    original_to_derived[seq] = next
    let fact_event : Json = if kind == "rows" {
      let fact = match by_rows.get(seq) {
        Some(fact) => fact
        None =>
          fail("Every original delivered rows event requires a proven SQL fact")
      }
      used_rows += 1
      let data = object_fields(orm_get(fact, "data"), "fact")
      orm_equal(
        required(event, "tx", "rows"),
        orm_get(fact, "tx"),
        "Derived fact transaction remains original",
      )
      let fact_kind = orm_text(orm_get(fact, "kind"))
      orm_assert(
        fact_kind == "read" || fact_kind == "write",
        "Only independently proven point reads/writes",
      )
      let result : Json = {
        "seq": next,
        "time": required(event, "time", "event"),
        "kind": fact_kind.to_json(),
        "tx": required(event, "tx", "event"),
        "key": required(data, "key", "fact"),
        "version": required(data, "version", "fact"),
      }
      if fact_kind == "write" {
        object_fields_unchecked_v3(result)["predecessor"] = required(
          data, "predecessor", "fact",
        )
      }
      result
    } else {
      orm_assert(
        [
          "snapshot", "begin", "savepoint", "rollback_to", "release", "commit_request",
          "commit_ok", "rollback_ok",
        ].contains(kind),
        "Raw hand-written facts, conditions or unknown outcomes cannot enter fixed profile projection",
      )
      let copy = list_v3_copy(event)
      copy["seq"] = next
      match copy.get("commitResponse") {
        Some(Object(response)) => {
          let adjusted = list_v3_copy(response)
          let request = v3_capture_seq(
            required(response, "request", "response"),
            "request",
          )
          adjusted["request"] = match original_to_derived.get(request) {
            Some(value) => value
            None => fail("Missing original retained COMMIT request")
          }
          copy["commitResponse"] = Json::object(adjusted)
        }
        _ => ()
      }
      Json::object(copy)
    }
    derived.push(fact_event)
    origins.push(seq.to_double().to_json())
  }
  orm_assert(
    used_rows == facts.length() && used_statements == facts.length(),
    "Every proven SQL fact must refer to an actual original statement and rows event",
  )
  let projection : Json = {
    "traceSchema": 3,
    "clockDomain": clock,
    "scope": { "exclusiveWriters": true },
    "gaps": [],
    "events": derived.to_json(),
  }
  let normalized = guarded_json(
    normalize_register_capture_v3_json(projection.stringify()),
    limit=33554432,
  )
  orm_equal(
    orm_get(normalized, "status"),
    "ready".to_json(),
    "Derived point facts independently satisfy all lifecycle/source/order rules",
  )
  let history = match
    parse_history(orm_get(normalized, "history").stringify()) {
    Ok(history) => history
    Err(reason) =>
      fail(
        "Derived fixed-profile history failed original validation: " + reason,
      )
  }
  ({ normalized, history, }, origins)
}

///|
/// Analyze only the configured, independently source-proven fixed base-user CRUD
/// window. Raw diagnostic gaps and the old sourceSchema2 proof remain unchanged.
pub fn orm_profile_source_v3_json(
  text : String,
  options_text : String,
) -> String {
  let mut source_proof : Json = Json::null()
  let mut raw_coverage : Json = Json::null()
  try {
    orm_assert(
      orm_utf8_size(text) <= 67108864,
      "Bounded fixed profile envelope",
    )
    let input = orm_exact(guarded_json(text, limit=67108864), [
      "format", "profile", "traceText", "sourceJournalText", "lifecycleText", "journalIndexText",
    ])
    orm_equal(
      required(input, "format", "input"),
      "moontxnwitness-orm-profile-source/v1".to_json(),
      "Independent fixed profile input format",
    )
    orm_equal(
      required(input, "profile", "input"),
      "fastapi-users-sqlalchemy-7.0.0-pg18/1".to_json(),
      "Pinned fixed base-user profile",
    )
    let trace_text = orm_text(required(input, "traceText", "input"))
    let source_text = orm_text(required(input, "sourceJournalText", "input"))
    let lifecycle_text = orm_text(required(input, "lifecycleText", "input"))
    let index_text = orm_text(required(input, "journalIndexText", "input"))
    orm_assert(
      orm_utf8_size(index_text) <= 2097152,
      "Original journal index byte budget",
    )
    let trace = object_fields(guarded_json(trace_text, limit=8388608), "trace")
    orm_profile_diagnostic_gaps_v3(orm_array(required(trace, "gaps", "trace")))
    let events = orm_array(required(trace, "events", "trace"))
    let lifecycle = object_fields(
      guarded_json(
        normalize_register_capture_v3_json(trace_text),
        limit=33554432,
      ),
      "normalized lifecycle",
    )
    raw_coverage = required(lifecycle, "coverage", "lifecycle")
    orm_assert(
      required(lifecycle, "status", "lifecycle") != "invalid".to_json(),
      "Original lifecycle must remain valid diagnostic evidence",
    )
    let envelope : Json = {
      "schema": 2,
      "profile": required(input, "profile", "input"),
      "traceText": trace_text.to_json(),
      "sourceJournalText": source_text.to_json(),
    }
    source_proof = guarded_json(
      orm_sql_source2_v3_proof_json(envelope.stringify()),
      limit=33554432,
    )
    orm_equal(
      orm_get(source_proof, "controlProfileComplete"),
      true.to_json(),
      "All original sourceSchema2 controls and effects independently verify",
    )
    // Old APIs and original diagnostic proof keep their original non-acceptance.
    orm_equal(
      orm_get(source_proof, "analysisCoverageAccepted"),
      false.to_json(),
      "Original proof remains diagnostic",
    )
    orm_equal(
      orm_get(source_proof, "history"),
      Json::null(),
      "Original proof cannot silently acquire a history",
    )
    let (records, installation_index, initial_controls, final_controls) = orm2_journal(
      source_text,
    )
    let installation = object_fields(
      records[installation_index],
      "installation",
    )
    let final_record = object_fields(
      records[records.length() - 2],
      "final ledger",
    )
    let metadata = object_fields(
      required(installation, "metadata", "installation"),
      "metadata",
    )
    let window = orm_profile_window_v3(
      lifecycle_text,
      required(metadata, "nonce", "metadata"),
    )
    orm_profile_source_refs_v3(
      window, installation, final_record, initial_controls, final_controls,
    )
    let index = object_fields(
      guarded_json(index_text, limit=2097152),
      "journal index",
    )
    orm_profile_index_digest_v3(index_text, index)
    orm_profile_index_v3(index, events)
    orm_profile_ownership_v3(window)
    let calls = orm_profile_calls_v3(
      window,
      events,
      orm_array(required(lifecycle, "transactions", "lifecycle")),
    )
    for record in records {
      orm_assert(
        orm_get(record, "kind") != "source-gap".to_json(),
        "Unproven conditional/error/zero-row SQL source remains inconclusive",
      )
    }
    let facts = orm_array(orm_get(source_proof, "provenFacts"))
    let (projection, origins) = orm_profile_derived_v3(
      events,
      facts,
      required(trace, "clockDomain", "trace"),
    )
    let history = projection.history
    let options = parse_analysis_options(options_text)
    let analysis = analysis_result_json(analyze_with_options(history, options~))
    let result : Json = {
      "schemaVersion": 3,
      "tool": "MoonTxnWitness",
      "version": version().to_json(),
      "algorithm": "v3-orm-profile-source-promotion-1",
      "profile": required(input, "profile", "input"),
      "status": orm_get(analysis, "status"),
      "analysisCoverageAccepted": true,
      "originalDiagnosticCoverage": raw_coverage,
      "originalSourceProof": source_proof,
      "mappingCoverage": {
        "complete": true,
        "gaps": [],
        "actualCalls": calls,
        "provenFacts": facts.length().to_json(),
        "sourceWindowsChecked": true,
      },
      "history": history_json(history),
      "derivedNormalized": projection.normalized,
      "retainedOriginalSeq": origins.to_json(),
      "analysis": analysis,
      "sourceBindings": {
        "traceSha256": v3_dislock_sha256(trace_text).to_json(),
        "sourceJournalSha256": v3_dislock_sha256(source_text).to_json(),
        "lifecycleSha256": v3_dislock_sha256(lifecycle_text).to_json(),
        "journalIndexSha256": v3_dislock_sha256(index_text).to_json(),
      },
      "scope": "Configured PostgreSQL18 fixed base-user point CRUD under the verified controlled-writer window; raw diagnostic coverage stays incomplete. The original index self-checksum and descriptors are checked; segment bytes were not supplied or independently rehashed. One complete engine attachment and returned-lease lifecycle is required; local factories remain diagnostic. No database authentication, arbitrary SQL, range/predicate, ORM-wide or real-time claim.",
    }
    result.stringify(indent=2)
  } catch {
    error => {
      let result : Json = {
        "schemaVersion": 3,
        "tool": "MoonTxnWitness",
        "version": version().to_json(),
        "algorithm": "v3-orm-profile-source-promotion-1",
        "status": "inconclusive",
        "analysisCoverageAccepted": false,
        "history": Json::null(),
        "analysis": Json::null(),
        "originalDiagnosticCoverage": raw_coverage,
        "originalSourceProof": source_proof,
        "mappingCoverage": {
          "complete": false,
          "gaps": [capture_gap("orm_profile_not_proven", error.to_string())],
        },
      }
      result.stringify(indent=2)
    }
  }
}
