///|
pub fn verify_snapshot_admission_v2_json(
  config_text : String,
  policy_text : String,
  installation_log_text : String,
  installation_receipt_text : String,
  snapshot_log_text : String,
  snapshot_receipt_text : String,
  options_text : String,
) -> String {
  try {
    let config = match parse_sql_config_v2(config_text) {
      Ok(value) => value
      Err(reason) => fail("invalid:" + reason)
    }
    if orm_utf8_size(options_text) > 8192 {
      fail("budget:snapshot-admission-wire-options-bytes")
    }
    let (checks, installation_checks, row_limit, effect_limit) = try {
      let options = object_fields(
        sql_json_v1(options_text, 8192),
        "independent snapshot admission options",
      )
      known_fields(
        options,
        ["maxChecks", "maxInstallationChecks", "maxRows", "maxEffects"],
        "snapshot admission options",
      )
      fn limit(
        name : String,
        fallback : Int32,
        maximum : Int32,
      ) -> Int32 raise {
        match options.get(name) {
          None => fallback
          Some(value) => fetch_number_v1(value, maximum)
        }
      }
      (
        limit("maxChecks", 1000000, 1000000),
        limit("maxInstallationChecks", 1000000, 1000000),
        limit("maxRows", 4096, 16384),
        limit("maxEffects", 4096, 16384),
      )
    } catch {
      _ => fail("invalid:snapshot-admission-wire-options")
    }
    let installation = verify_source_admission_v2(
      config,
      sql_json_v1(policy_text, 8192),
      installation_log_text,
      sql_json_v1(installation_receipt_text, 2097152),
      max_checks=installation_checks,
    )
    snapshot_admission_v2_json(
      verify_snapshot_admission_v2(
        installation,
        snapshot_log_text,
        sql_json_v1(snapshot_receipt_text, 2097152),
        max_checks=checks,
        max_rows=row_limit,
        max_effects=effect_limit,
      ),
    ).stringify()
  } catch {
    error =>
      (
        {
          "format": "moontxnwitness-source-snapshot-admission/v2",
          "status": Json(
            if error.to_string().contains("budget:") {
              "unknown"
            } else {
              "invalid"
            },
          ),
          "valid": false,
          "snapshotVerified": false,
          "controlComplete": false,
          "sourceFactsProduced": false,
          "sourceAuthenticated": false,
          "completeWindow": false,
          "writerWindowVerified": false,
          "modelCoverageAccepted": false,
          "commitVerified": false,
          "gaps": [Json(error.to_string())],
        } : Json).stringify()
  }
}
