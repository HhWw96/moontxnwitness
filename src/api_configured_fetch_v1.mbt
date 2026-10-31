///|
pub fn verify_configured_fetch_v1_json(
  config_text : String,
  execution_text : String,
  native_text : String,
  deliveries_text : String,
  options_text : String,
) -> String {
  try {
    let config = match parse_sql_config_v1(config_text) {
      Ok(config) => config
      Err(reason) => fail(reason)
    }
    let options = object_fields(
      sql_json_v1(options_text, 8192),
      "fetch options",
    )
    known_fields(options, ["maxChecks", "grammarOptions"], "fetch options")
    let checks = match options.get("maxChecks") {
      None => 1000000
      Some(value) => fetch_number_v1(value, 1000000)
    }
    let grammar = match options.get("grammarOptions") {
      None => sql_verification_options_v1()
      Some(value) => sql_wire_options_v1(value.stringify())
    }
    configured_fetch_check_v1_json(
      verify_configured_fetch_v1(
        config,
        sql_json_v1(execution_text, 1048576),
        sql_json_v1(native_text, 524288),
        sql_json_v1(deliveries_text, 2097152),
        max_checks=checks,
        grammar_options=grammar,
      ),
    ).stringify()
  } catch {
    error =>
      (
        {
          "format": "moontxnwitness-configured-fetch-verification/v1",
          "status": "invalid",
          "valid": false,
          "sourceFactsProduced": false,
          "sourceAuthenticated": false,
          "gaps": [Json(error.to_string())],
        } : Json).stringify()
  }
}
