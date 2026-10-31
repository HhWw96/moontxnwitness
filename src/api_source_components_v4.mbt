///|
fn source_wire_limit_v4(
  options : Map[String, Json],
  key : String,
  fallback : Int32,
) -> Int32 raise {
  match options.get(key) {
    None => fallback
    Some(value) => fetch_number_v1(value, 1000000)
  }
}

///|
fn source_wire_error_v4(error : Error, format : String) -> String {
  (
    {
      "format": Json(format),
      "status": "invalid",
      "valid": false,
      "sourceFactsProduced": false,
      "sourceAuthenticated": false,
      "writerWindowVerified": false,
      "isolationModelChecked": false,
      "reason": Json(error.to_string()),
    } : Json).stringify()
}

///|
fn source_wire_install_v4(
  config_text : String,
  policy_text : String,
  log_text : String,
  receipt_text : String,
  options_text : String,
) -> SourceInstallationCheckV4 raise {
  let config = match parse_sql_config_v1(config_text) {
    Ok(value) => value
    Err(reason) => fail(reason)
  }
  let options = source_object_v4(sql_json_v1(options_text, 8192))
  known_fields(options, ["maxChecks"], "source-install-options")
  verify_source_installation_v4(
    config,
    sql_json_v1(policy_text, 8192),
    log_text,
    sql_json_v1(receipt_text, 2097152),
    max_checks=source_wire_limit_v4(options, "maxChecks", 1000000),
  )
}

///|
pub fn verify_source_installation_v4_json(
  config_text : String,
  policy_text : String,
  log_text : String,
  receipt_text : String,
  options_text : String,
) -> String {
  source_installation_check_v4_json(
    source_wire_install_v4(
      config_text, policy_text, log_text, receipt_text, options_text,
    ),
  ).stringify() catch {
    error =>
      source_wire_error_v4(error, "moontxnwitness-source-installation-check/v4")
  }
}

///|
pub fn verify_source_installation_report_v4_json(
  config_text : String,
  policy_text : String,
  log_text : String,
  receipt_text : String,
  report_text : String,
  expected_options_text : String,
) -> Bool {
  try {
    let actual = sql_json_v1(report_text, 2097152)
    let expected = source_installation_check_v4_json(
      source_wire_install_v4(
        config_text, policy_text, log_text, receipt_text, expected_options_text,
      ),
    )
    sql_canonical_v1(actual) == sql_canonical_v1(expected)
  } catch {
    _ => false
  }
}

///|
fn source_wire_mapping_v4(
  config_text : String,
  policy_text : String,
  log_text : String,
  receipt_text : String,
  execution_text : String,
  native_text : String,
  deliveries_text : String,
  context_text : String,
  options_text : String,
) -> SourceFetchMappingV4 raise {
  let config = match parse_sql_config_v1(config_text) {
    Ok(value) => value
    Err(reason) => fail(reason)
  }
  let options = source_object_v4(sql_json_v1(options_text, 8192))
  known_fields(
    options,
    ["maxChecks", "maxInstallationChecks", "maxFetchChecks", "grammarOptions"],
    "source-fetch-options",
  )
  let installation = verify_source_installation_v4(
    config,
    sql_json_v1(policy_text, 8192),
    log_text,
    sql_json_v1(receipt_text, 2097152),
    max_checks=source_wire_limit_v4(options, "maxInstallationChecks", 1000000),
  )
  let grammar_options = match options.get("grammarOptions") {
    None => sql_verification_options_v1()
    Some(value) => sql_wire_options_v1(value.stringify())
  }
  verify_source_fetch_mapping_v4(
    installation,
    sql_json_v1(execution_text, 1048576),
    sql_json_v1(native_text, 524288),
    sql_json_v1(deliveries_text, 2097152),
    sql_json_v1(context_text, 8192),
    max_checks=source_wire_limit_v4(options, "maxChecks", 1000000),
    max_fetch_checks=source_wire_limit_v4(options, "maxFetchChecks", 1000000),
    grammar_options~,
  )
}

///|
pub fn verify_source_fetch_mapping_v4_json(
  config_text : String,
  policy_text : String,
  log_text : String,
  receipt_text : String,
  execution_text : String,
  native_text : String,
  deliveries_text : String,
  context_text : String,
  options_text : String,
) -> String {
  source_fetch_mapping_v4_json(
    source_wire_mapping_v4(
      config_text, policy_text, log_text, receipt_text, execution_text, native_text,
      deliveries_text, context_text, options_text,
    ),
  ).stringify() catch {
    error =>
      source_wire_error_v4(error, "moontxnwitness-source-fetch-mapping/v4")
  }
}

///|
pub fn verify_source_fetch_mapping_report_v4_json(
  config_text : String,
  policy_text : String,
  log_text : String,
  receipt_text : String,
  execution_text : String,
  native_text : String,
  deliveries_text : String,
  context_text : String,
  report_text : String,
  expected_options_text : String,
) -> Bool {
  try {
    let actual = sql_json_v1(report_text, 4194304)
    let expected = source_fetch_mapping_v4_json(
      source_wire_mapping_v4(
        config_text, policy_text, log_text, receipt_text, execution_text, native_text,
        deliveries_text, context_text, expected_options_text,
      ),
    )
    sql_canonical_v1(actual) == sql_canonical_v1(expected)
  } catch {
    _ => false
  }
}
