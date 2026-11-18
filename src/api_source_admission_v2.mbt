///|
pub fn verify_source_admission_v2_json(
  config_text : String,
  policy_text : String,
  original_log : String,
  receipt_text : String,
  options_text : String,
) -> String {
  try {
    let config = match parse_sql_config_v2(config_text) {
      Ok(value) => value
      Err(reason) => fail("invalid:" + reason)
    }
    if orm_utf8_size(options_text) > 8192 {
      fail("budget:source-admission-wire-options-bytes")
    }
    let limit = try {
      let options = object_fields(
        sql_json_v1(options_text, 8192),
        "source admission options",
      )
      known_fields(options, ["maxChecks"], "source admission options")
      match options.get("maxChecks") {
        None => 1000000
        Some(value) => fetch_number_v1(value, 1000000)
      }
    } catch {
      _ => fail("invalid:source-admission-wire-options")
    }
    source_admission_v2_json(
      verify_source_admission_v2(
        config,
        sql_json_v1(policy_text, 8192),
        original_log,
        sql_json_v1(receipt_text, 2097152),
        max_checks=limit,
      ),
    ).stringify()
  } catch {
    error =>
      (
        {
          "format": "moontxnwitness-source-installation-admission/v2",
          "status": Json(
            if error.to_string().contains("budget:") {
              "unknown"
            } else {
              "invalid"
            },
          ),
          "valid": false,
          "installationVerified": false,
          "sourceAuthenticated": false,
          "sourceFactsProduced": false,
          "captureFactsProduced": false,
          "completeWindow": false,
          "writerWindowVerified": false,
          "modelCoverageAccepted": false,
          "commitVerified": false,
          "execution": { "checks": 0, "limit": 0 },
          "gaps": [Json(error.to_string())],
        } : Json).stringify()
  }
}
