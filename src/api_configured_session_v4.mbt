///|
fn configured_session_wire_options_v4(
  text : String,
) -> ConfiguredSessionOptionsV4 raise {
  let o = source_object_v4(sql_json_v1(text, 8192))
  known_fields(
    o,
    [
      "maxJournalChecks", "maxResults", "maxInstallationChecks", "maxFetchChecksPerResult",
      "maxReturnedRowChecksPerResult", "maxSourceChecksPerResult",
    ],
    "configured-session-options",
  )
  let result = configured_session_options_v4(
    max_journal_checks=source_wire_limit_v4(o, "maxJournalChecks", 1000000),
    max_results=source_wire_limit_v4(o, "maxResults", 32),
    max_installation_checks=source_wire_limit_v4(
      o, "maxInstallationChecks", 1000000,
    ),
    max_fetch_checks=source_wire_limit_v4(o, "maxFetchChecksPerResult", 1000000),
    max_result_checks=source_wire_limit_v4(
      o, "maxReturnedRowChecksPerResult", 1000000,
    ),
    max_source_checks=source_wire_limit_v4(
      o, "maxSourceChecksPerResult", 1000000,
    ),
  )
  match result {
    Ok(value) => value
    Err(reason) => fail(reason)
  }
}

///|
pub fn configured_session_options_v4_json(text : String) -> String {
  (
    {
      "valid": true,
      "options": configured_session_options_record_v4(
        configured_session_wire_options_v4(text),
      ),
    } : Json).stringify() catch {
    error =>
      ({ "valid": false, "error": Json(error.to_string()) } : Json).stringify()
  }
}

///|
pub fn configured_session_bundle_v4_json(text : String) -> String {
  try {
    let raw = sql_json_v1(text, 33554432)
    let f = orm_exact(raw, [
      "format", "configText", "lifecycleText", "diagnosticTraceText", "sourceInputsText",
    ])
    if f.at("format") != Json("moontxnwitness-configured-session-input/v1") {
      fail("Unknown configured session input format")
    }
    for
      key in [
        "configText", "lifecycleText", "diagnosticTraceText", "sourceInputsText",
      ] {
      ignore(sql_string_v1(f.at(key)))
    }
    ({ "valid": true, "input": raw } : Json).stringify()
  } catch {
    error =>
      ({ "valid": false, "error": Json(error.to_string()) } : Json).stringify()
  }
}

///|
pub fn diagnose_configured_session_v4_json(
  config_text : String,
  lifecycle_text : String,
  diagnostic_trace_text : String,
  source_inputs_text : String,
  options_text : String,
) -> String {
  try {
    let config = match parse_sql_config_v1(config_text) {
      Ok(c) => c
      Err(reason) => fail(reason)
    }
    configured_session_diagnostic_v4_json(
      diagnose_configured_session_v4(
        config,
        lifecycle_text,
        diagnostic_trace_text,
        sql_json_v1(source_inputs_text, 12582912),
        options=configured_session_wire_options_v4(options_text),
      ),
    ).stringify()
  } catch {
    error =>
      (
        {
          "format": "moontxnwitness-configured-session-diagnostic/v4",
          "status": "invalid",
          "sourceFactsProduced": false,
          "writerWindowVerified": false,
          "sourceAuthenticated": false,
          "serverInstanceIdentityAuthenticated": false,
          "isolationModelChecked": false,
          "isolationAnalysisReady": false,
          "reason": Json(error.to_string()),
        } : Json).stringify()
  }
}

///|
pub fn verify_configured_session_diagnostic_v4_json(
  config_text : String,
  lifecycle_text : String,
  diagnostic_trace_text : String,
  source_inputs_text : String,
  report_text : String,
  expected_options_text : String,
) -> Bool {
  try {
    let actual = sql_json_v1(report_text, 67108864)
    let expected = sql_json_v1(
      diagnose_configured_session_v4_json(
        config_text, lifecycle_text, diagnostic_trace_text, source_inputs_text, expected_options_text,
      ),
      67108864,
    )
    sql_canonical_v1(actual) == sql_canonical_v1(expected)
  } catch {
    _ => false
  }
}
