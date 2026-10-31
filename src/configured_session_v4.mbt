///|
pub struct ConfiguredSessionOptionsV4 {
  priv max_journal_checks : Int32
  priv max_results : Int32
  priv max_installation_checks : Int32
  priv max_fetch_checks : Int32
  priv max_result_checks : Int32
  priv max_source_checks : Int32
}

///|
pub fn configured_session_options_v4(
  max_journal_checks~ : Int32 = 1000000,
  max_results~ : Int32 = 32,
  max_installation_checks~ : Int32 = 1000000,
  max_fetch_checks~ : Int32 = 1000000,
  max_result_checks~ : Int32 = 1000000,
  max_source_checks~ : Int32 = 1000000,
) -> Result[ConfiguredSessionOptionsV4, String] {
  if max_results < 0 ||
    max_results > 128 ||
    [
      max_journal_checks, max_installation_checks, max_fetch_checks, max_result_checks,
      max_source_checks,
    ].any(n => n < 0 || n > 1000000) {
    Err("Configured session caller limits exceed their declared bounds")
  } else {
    Ok({
      max_journal_checks,
      max_results,
      max_installation_checks,
      max_fetch_checks,
      max_result_checks,
      max_source_checks,
    })
  }
}

///|
fn configured_session_options_record_v4(o : ConfiguredSessionOptionsV4) -> Json {
  {
    "maxJournalChecks": Json(o.max_journal_checks),
    "maxResults": Json(o.max_results),
    "maxInstallationChecks": Json(o.max_installation_checks),
    "maxFetchChecksPerResult": Json(o.max_fetch_checks),
    "maxReturnedRowChecksPerResult": Json(o.max_result_checks),
    "maxSourceChecksPerResult": Json(o.max_source_checks),
  }
}

///|
pub struct ConfiguredSessionDiagnosticV4 {
  priv record : Json
}

///|
priv struct ConfiguredSessionCaseV4 {
  execution : Json
  execution_text : String
  execution_note : Int32
  native : Json
  native_text : String
  native_note : Int32
  deliveries : Array[Json]
  delivery_texts : Array[String]
}

///|
fn configured_session_identity_v4(value : Json) -> String raise {
  let f = source_object_v4(value)
  let names : Array[Json] = []
  for key in ["connection", "cursor", "tx"] {
    let name = sql_string_v1(required(f, key, "configured-result-identity"))
    if name.is_empty() || orm_utf8_size(name) > 512 {
      fail("mismatch:session-empty-result-identity")
    }
    names.push(Json(name))
  }
  names.push(
    Json(
      fetch_number_v1(
        required(f, "statementSeq", "configured-result-identity"),
        100000000,
      ),
    ),
  )
  Json(names).stringify()
}

///|
fn configured_session_records_v4(
  text : String,
  options : ConfiguredSessionOptionsV4,
  work : SourceWorkV4,
) -> (Array[ConfiguredSessionCaseV4], Array[Json]) raise {
  if orm_utf8_size(text) > 8388608 || !text.has_suffix("\n") {
    fail("unsupported:session-lifecycle-size-or-unsealed-tail")
  }
  let lines = text.split("\n").to_array()
  if lines.length() < 3 || lines.length() > 65537 {
    fail("unsupported:session-lifecycle-record-count")
  }
  let prefix = StringBuilder()
  let executions : Map[Int32, (Json, String)] = Map([])
  let execution_ids : Map[String, Bool] = Map([])
  let execution_notes : Array[Int32] = []
  let used : Map[Int32, Bool] = Map([])
  let results : Map[String, Int32] = Map([])
  let cases : Array[ConfiguredSessionCaseV4] = []
  let mut domain = ""
  for index in 0..<(lines.length() - 1) {
    work.charge()
    let line = lines[index].to_owned()
    if line.is_empty() || orm_utf8_size(line) > 524288 {
      fail("mismatch:session-lifecycle-record-size")
    }
    let raw = sql_json_v1(line, 524288)
    let record = source_object_v4(raw)
    if record.get("seq") != Some(Json(index + 1)) {
      fail("mismatch:session-lifecycle-sequence-gap")
    }
    let kind = sql_string_v1(required(record, "kind", "session-lifecycle"))
    if index == 0 {
      known_fields(
        record,
        [
          "seq", "kind", "format", "diagnosticOnly", "processMonotonicDomain", "experimentalBudget",
          "limits",
        ],
        "session-header",
      )
      if kind != "header" ||
        record.get("format") != Some(Json("moontxnwitness-instrumentation/v1")) ||
        record.get("diagnosticOnly") != Some(Json(true)) {
        fail("mismatch:session-lifecycle-header")
      }
      domain = sql_string_v1(
        required(record, "processMonotonicDomain", "session-header"),
      )
      if domain.is_empty() {
        fail("mismatch:session-empty-clock-domain")
      }
    } else if index == lines.length() - 2 {
      let _ = orm_exact(raw, ["seq", "kind", "prefixSha256", "records"])
      if kind != "seal" ||
        record.get("records") != Some(Json(index)) ||
        record.get("prefixSha256") !=
        Some(Json(v3_dislock_sha256(prefix.to_string()))) {
        fail("mismatch:session-lifecycle-seal")
      }
    } else if kind == "seal" || kind == "header" {
      fail("mismatch:session-lifecycle-extra-header-or-seal")
    } else if [
        "configured-execution", "configured-native-result", "configured-delivery",
      ].contains(kind) {
      known_fields(
        record,
        ["seq", "kind", "processMonotonicDomain", "monotonicNs", "frameText"],
        "session-frame",
      )
      if record.get("processMonotonicDomain") != Some(Json(domain)) {
        fail("mismatch:session-frame-clock-domain")
      }
      let frame_text = sql_string_v1(
        required(record, "frameText", "session-frame"),
      )
      let frame = sql_json_v1(frame_text, 61440)
      let f = source_object_v4(frame)
      let identity = configured_session_identity_v4(frame)
      if kind == "configured-execution" {
        if execution_ids.contains(identity) {
          fail("mismatch:session-duplicate-execution-identity")
        }
        execution_ids[identity] = true
        executions[index + 1] = (frame, frame_text)
        execution_notes.push(index + 1)
      } else if kind == "configured-native-result" {
        let note = fetch_number_v1(
          required(f, "executionNoteSeq", "native-result"),
          65536,
        )
        let (execution, original) = match executions.get(note) {
          Some(v) => v
          None => fail("mismatch:session-native-execution-reference")
        }
        if configured_session_identity_v4(execution) != identity ||
          used.contains(note) {
          fail("mismatch:session-native-execution-identity")
        }
        if cases.length() >= options.max_results {
          fail("budget:session-results")
        }
        let result_id = sql_string_v1(required(f, "resultId", "native-result"))
        if result_id.is_empty() || results.contains(result_id) {
          fail("mismatch:session-duplicate-native-result")
        }
        used[note] = true
        results[result_id] = cases.length()
        cases.push({
          execution,
          execution_text: original,
          execution_note: note,
          native: frame,
          native_text: frame_text,
          native_note: index + 1,
          deliveries: [],
          delivery_texts: [],
        })
      } else {
        let result_id = sql_string_v1(
          required(f, "resultId", "actual-delivery"),
        )
        let position = match results.get(result_id) {
          Some(n) => n
          None => fail("mismatch:session-delivery-result-reference")
        }
        let result = cases[position]
        if configured_session_identity_v4(result.native) != identity ||
          f.get("nativeNoteSeq") != Some(Json(result.native_note)) {
          fail("mismatch:session-delivery-native-reference")
        }
        result.deliveries.push(frame)
        result.delivery_texts.push(frame_text)
      }
    }
    if index < lines.length() - 2 {
      prefix.write_string(line)
      prefix.write_string("\n")
    }
  }
  let unmatched : Array[Json] = []
  for note in execution_notes {
    work.charge()
    if !used.contains(note) {
      unmatched.push({
        "executionNoteSeq": Json(note),
        "originalExecution": executions.at(note).0,
        "reason": "recognized execution has no independently retained ordinary native result",
      })
    }
  }
  (cases, unmatched)
}

///|
fn configured_session_trace_v4(
  text : String,
  cases : Array[ConfiguredSessionCaseV4],
  work : SourceWorkV4,
) -> (Json, Array[Json]) raise {
  if text == "null" {
    return (
      {
        "supplied": false,
        "statementBindingsVerified": false,
        "sourceJournalIndexVerified": false,
        "producerGaps": [],
      },
      [],
    )
  }
  let trace = source_object_v4(sql_json_v1(text, 8388608))
  let statements : Map[Int32, Json] = Map([])
  let tx_connections : Map[String, String] = Map([])
  let statement_order : Array[Int32] = []
  let mut previous = 0
  for event in orm_array(required(trace, "events", "diagnostic-trace")) {
    work.charge()
    let e = source_object_v4(event)
    let seq = fetch_number_v1(required(e, "seq", "diagnostic-event"), 100000000)
    if seq <= previous {
      fail("mismatch:session-diagnostic-event-identity")
    }
    previous = seq
    let kind = sql_string_v1(required(e, "kind", "diagnostic-event"))
    if kind == "begin" {
      let tx = sql_string_v1(required(e, "tx", "diagnostic-begin"))
      if tx_connections.contains(tx) {
        fail("mismatch:session-repeated-transaction-identity")
      }
      tx_connections[tx] = sql_string_v1(
        required(e, "connection", "diagnostic-begin"),
      )
    } else if kind == "statement" {
      statements[seq] = event
      statement_order.push(seq)
    }
  }
  let used : Map[Int32, Bool] = Map([])
  for result in cases {
    work.charge()
    let e = source_object_v4(result.execution)
    let seq = fetch_number_v1(e.at("statementSeq"), 100000000)
    let statement = match statements.get(seq) {
      Some(s) => source_object_v4(s)
      None => fail("mismatch:session-original-statement-missing")
    }
    if statement.get("tx") != e.get("tx") ||
      statement.get("sql") != e.get("sql") {
      fail("mismatch:session-original-statement-binding")
    }
    let tx = sql_string_v1(e.at("tx"))
    if tx_connections.get(tx) != Some(sql_string_v1(e.at("connection"))) {
      fail("mismatch:session-original-connection-binding")
    }
    if used.contains(seq) {
      fail("mismatch:session-original-statement-reused")
    }
    used[seq] = true
  }
  let unprojected : Array[Json] = []
  for seq in statement_order {
    work.charge()
    if !used.contains(seq) && unprojected.length() < 128 {
      unprojected.push({
        "originalStatement": statements.at(seq),
        "reason": "statement is not covered by a configured ordinary SELECT/native/delivery result",
      })
    }
  }
  let empty_producer_gaps : Array[Json] = []
  (
    {
      "supplied": true,
      "sourceSha256": Json(v3_dislock_sha256(text)),
      "statementBindingsVerified": true,
      "sourceJournalIndexVerified": false,
      "producerDiagnosticsTrustedAsFacts": false,
      "producerGaps": trace.get_or_default("gaps", Json(empty_producer_gaps)),
      "unprojectedDetailLimit": 128,
      "unprojectedStatementCount": Json(
        statement_order.length() - used.length(),
      ),
      "unprojectedDetailsTruncated": Json(
        statement_order.length() - used.length() > 128,
      ),
    },
    unprojected,
  )
}

///|
pub fn diagnose_configured_session_v4(
  config : SQLConfigV1,
  lifecycle_text : String,
  diagnostic_trace_text : String,
  source_input : Json,
  options~ : ConfiguredSessionOptionsV4 = configured_session_options_v4().unwrap(),
) -> ConfiguredSessionDiagnosticV4 {
  let work : SourceWorkV4 = { limit: options.max_journal_checks, checks: 0, }
  let reports : Array[Json] = []
  let mut installation_record : Json = Json::null()
  let mut trace_record : Json = Json::null()
  let mut unmatched : Array[Json] = []
  let mut unprojected : Array[Json] = []
  let mut reason = ""
  let mut result_status = "unknown"
  let mut source_status = "not-requested"
  let mut journal_valid = false
  let mut result_mismatch = false
  let mut source_mismatch = false
  let status = try {
    let (cases, pending) = configured_session_records_v4(
      lifecycle_text, options, work,
    )
    unmatched = pending
    let (trace, misses) = configured_session_trace_v4(
      diagnostic_trace_text, cases, work,
    )
    trace_record = trace
    unprojected = misses
    journal_valid = true
    let source_requested = source_input != Json::null()
    let mut installation : SourceInstallationCheckV4? = None
    let mut source_context : Json = Json::null()
    if source_requested {
      let input = orm_exact(source_input, [
        "format", "policyText", "logText", "receiptText", "sourceContextText",
      ])
      if input.at("format") !=
        Json("moontxnwitness-configured-installation-input/v1") {
        fail("invalid:session-source-input-format")
      }
      let checked = verify_source_installation_v4(
        config,
        sql_json_v1(sql_string_v1(input.at("policyText")), 8192),
        sql_string_v1(input.at("logText")),
        sql_json_v1(sql_string_v1(input.at("receiptText")), 2097152),
        max_checks=options.max_installation_checks,
      )
      installation = Some(checked)
      installation_record = source_installation_check_v4_json(checked)
      source_context = sql_json_v1(
        sql_string_v1(input.at("sourceContextText")),
        8192,
      )
    }
    let mut result_unknown = cases.is_empty() ||
      !unmatched.is_empty() ||
      !unprojected.is_empty()
    let mut source_unknown = cases.is_empty()
    for result in cases {
      work.charge()
      let execution = source_object_v4(result.execution)
      let candidate = source_object_v4(
        required(execution, "candidate", "session-original-execution"),
      )
      let candidate_digest = required(
        candidate, "configSha256", "session-original-candidate",
      )
      let capture_config = if candidate_digest == Json(config.digest) {
        config
      } else if source_requested {
        let augmented = source_augmented_config_v4(config)
        if candidate_digest != Json(augmented.digest) {
          fail("mismatch:session-capture-config-binding")
        }
        augmented
      } else {
        fail("mismatch:session-capture-config-binding")
      }
      let native_check = configured_fetch_check_v1_json(
        verify_configured_fetch_v1(
          capture_config,
          result.execution,
          result.native,
          Json(result.deliveries),
          max_checks=options.max_fetch_checks,
        ),
      )
      let selected = source_select_result_constraints_v4(
        native_check,
        result.native,
        { limit: options.max_result_checks, checks: 0, },
      )
      let n = source_object_v4(native_check)
      let s = source_object_v4(selected)
      if n.at("status") == Json("mismatch") ||
        s.at("status") == Json("mismatch") {
        result_mismatch = true
      }
      if n.at("valid") != Json(true) || s.at("valid") != Json(true) {
        result_unknown = true
      }
      let mapping = match installation {
        Some(checked) =>
          source_fetch_mapping_v4_json(
            verify_source_fetch_mapping_v4(
              checked,
              result.execution,
              result.native,
              Json(result.deliveries),
              source_context,
              max_checks=options.max_source_checks,
              max_fetch_checks=options.max_fetch_checks,
            ),
          )
        None => Json::null()
      }
      if installation is Some(_) {
        let m = source_object_v4(mapping)
        if m.at("status") == Json("mismatch") {
          source_mismatch = true
        }
        if m.at("valid") != Json(true) {
          source_unknown = true
        }
      }
      reports.push({
        "executionNoteSeq": Json(result.execution_note),
        "nativeNoteSeq": Json(result.native_note),
        "identity": sql_json_v1(
          configured_session_identity_v4(result.native),
          8192,
        ),
        "nativeDeliveryCheck": native_check,
        "returnedRowConstraints": selected,
        "initialSourceMapping": mapping,
        "originalTexts": {
          "executionText": Json(result.execution_text),
          "nativeText": Json(result.native_text),
          "deliveriesText": Json("[" + result.delivery_texts.join(",") + "]"),
        },
      })
      result_status = if result_mismatch {
        "mismatch"
      } else if result_unknown {
        "partial-or-unknown"
      } else {
        "consistent-observed-results"
      }
      if source_requested {
        source_status = if source_mismatch {
          "mismatch"
        } else if source_unknown {
          "partial-or-unknown"
        } else {
          "consistent-initial-components"
        }
      }
    }
    "diagnostic-only"
  } catch {
    error => {
      reason = error.to_string()
      if !result_mismatch {
        result_status = "unknown"
      }
      if source_input != Json::null() && !source_mismatch {
        source_status = "unknown"
      }
      "input-unverified"
    }
  }
  {
    record: {
      "format": "moontxnwitness-configured-session-diagnostic/v4",
      "schemaVersion": 4,
      "semanticContract": "original-configured-session-diagnostics/v4-1",
      "algorithm": "shared-installation-and-original-frame-diagnostics-1",
      "counterContract": "configured-session-journal-and-independent-component-budgets-1",
      "status": Json(status),
      "resultConsistency": Json(result_status),
      "initialSourceStatus": Json(source_status),
      "diagnosticOnly": true,
      "sourceFactsProduced": false,
      "writerWindowVerified": false,
      "sourceAuthenticated": false,
      "serverInstanceIdentityAuthenticated": false,
      "isolationModelChecked": false,
      "isolationAnalysisReady": false,
      "lifecycleIntegrityChecked": Json(journal_valid),
      "lifecycleSha256": Json(v3_dislock_sha256(lifecycle_text)),
      "configurationSha256": Json(config.digest),
      "diagnosticTrace": trace_record,
      "installationComponents": installation_record,
      "results": Json(reports),
      "reason": Json(reason),
      "unmatchedExecutions": Json(unmatched),
      "unprojectedStatements": Json(unprojected),
      "gaps": [
        "writer-window-not-closed", "server-instance-and-observer-not-authenticated",
        "privileged-DDL-exclusion-not-proven", "no-effective-post-initial-write-source-protocol",
        "no-isolation-model-history-produced",
      ],
      "execution": {
        "journalChecks": Json(work.checks),
        "limits": configured_session_options_record_v4(options),
        "componentBudgets": "independent per result; original installation is recomputed once and reused as an opaque typed value",
      },
      "scope": {
        "resultOrder": "original observation sequence, never commit order",
        "logicalSessionDerivedFromPool": false,
        "syntheticSelectCreated": false,
        "sourceLookupFillsMissingBusinessColumns": false,
        "supportsPostInitialSourceFacts": false,
      },
    },
  }
}

///|
pub fn configured_session_diagnostic_v4_json(
  value : ConfiguredSessionDiagnosticV4,
) -> Json {
  v4_json_copy(value.record)
}

///|
pub fn verify_configured_session_diagnostic_v4(
  config : SQLConfigV1,
  lifecycle_text : String,
  diagnostic_trace_text : String,
  source_input : Json,
  report : Json,
  expected_options~ : ConfiguredSessionOptionsV4 = configured_session_options_v4().unwrap(),
) -> Bool {
  let expected = diagnose_configured_session_v4(
    config,
    lifecycle_text,
    diagnostic_trace_text,
    source_input,
    options=expected_options,
  )
  sql_canonical_v1(report) == sql_canonical_v1(expected.record)
}
