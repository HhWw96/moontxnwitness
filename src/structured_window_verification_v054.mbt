// Explicit opt-in structured-report transport. Default entry points remain
// on their original text verification path. Source and model algorithms
// are called from the existing bodies, never copied into this profile.

///|
pub fn analyze_configured_window_structured_v2_json(
  config_text : String,
  policy_text : String,
  bundle_text : String,
  options_text : String,
) -> String {
  let (_, text) = configured_window_analysis_record_v2(
    config_text, policy_text, bundle_text, options_text, false,
  )
  text
}

///|
pub fn verify_configured_window_structured_v2_json(
  config_text : String,
  policy_text : String,
  bundle_text : String,
  report_text : String,
  options_text : String,
) -> String {
  try {
    let (actual, actual_canonical) = configured_window_analysis_record_v2(
      config_text, policy_text, bundle_text, options_text, true,
    )
    window_report_depth_v2(actual, 64)
    let expected = sql_json_v1(report_text, 33554432)
    let equal = actual_canonical == sql_canonical_v1(expected)
    (
      {
        "format": "moontxnwitness-configured-window-verification/v2",
        "valid": Json(
          equal && window_object_v2(actual).at("coverageComplete") == Json(true),
        ),
        "reportMatches": Json(equal),
        "recomputed": actual,
      } : Json).stringify()
  } catch {
    error =>
      (
        {
          "format": "moontxnwitness-configured-window-verification/v2",
          "valid": false,
          "reason": Json(error.to_string()),
        } : Json).stringify()
  }
}

///|
fn configured_window_analysis_failure_v2(reason : String) -> Json {
  {
    "format": "moontxnwitness-configured-window-analysis/v2",
    "status": Json(
      if reason.contains("budget:") || reason.contains("unsupported:") {
        "unknown"
      } else {
        "invalid"
      },
    ),
    "coverageComplete": false,
    "sourceMappingVerified": false,
    "writerWindowVerified": false,
    "sourceAuthenticated": false,
    "reason": Json(reason),
  }
}

///|
// Both callers reconstruct the same record through the same parser and failure
// sites. The encoding choice is private transport work, not an input policy.
fn configured_window_analysis_record_v2(
  config_text : String,
  policy_text : String,
  bundle_text : String,
  options_text : String,
  canonical : Bool,
) -> (Json, String) {
  let record = try {
    let config = match parse_sql_config_v2(config_text) {
      Ok(value) => value
      Err(reason) => fail(reason)
    }
    window_analysis_body_v2(
      config,
      sql_json_v1(policy_text, 8192),
      sql_json_v1(bundle_text, 33554432),
      sql_json_v1(options_text, 262144),
      v3_dislock_sha256(bundle_text),
    )
  } catch {
    error => configured_window_analysis_failure_v2(error.to_string())
  }
  window_bounded_record_v2(
    record, canonical, 33554432, "budget:window-report-bytes", configured_window_analysis_failure_v2,
  )
}

///|
// Canonical JSON sorts object keys but keeps the compact encoding of keys,
// numbers and values. Its byte length therefore enforces the same wire bound.
// The two fixed small failure factories also bound parser/failure reports.
fn window_bounded_record_v2(
  record : Json,
  canonical : Bool,
  maximum : Int32,
  byte_reason : String,
  failure : (String) -> Json,
) -> (Json, String) {
  let encoded = if canonical {
    sql_canonical_v1(record)
  } else {
    record.stringify()
  }
  if orm_utf8_size(encoded) <= maximum {
    (record, encoded)
  } else {
    let rejected = failure(byte_reason)
    (
      rejected,
      if canonical {
        sql_canonical_v1(rejected)
      } else {
        rejected.stringify()
      },
    )
  }
}

///|
// Retain the former strict self-report parse's container-depth gate without
// encoding/parsing the Json again. Entering even an empty container consumes
// depth; a scalar leaf is still accepted when no container depth remains.
// Only verifiers call this gate. Text report producers keep their old scope.
fn window_report_depth_v2(record : Json, remaining : Int32) -> Unit raise {
  match record {
    Array(items) => {
      if remaining <= 0 {
        raise @json.DepthLimitExceeded
      }
      for item in items {
        window_report_depth_v2(item, remaining - 1)
      }
    }
    Object(fields) => {
      if remaining <= 0 {
        raise @json.DepthLimitExceeded
      }
      for _, item in fields {
        window_report_depth_v2(item, remaining - 1)
      }
    }
    _ => ()
  }
}

///|
pub fn reduce_configured_window_structured_v2_json(
  config_text : String,
  policy_text : String,
  bundle_text : String,
  options_text : String,
) -> String {
  let (_, text) = configured_window_reduction_record_v2(
    config_text, policy_text, bundle_text, options_text, false,
  )
  text
}

///|
pub fn verify_configured_window_reduction_structured_v2_json(
  config_text : String,
  policy_text : String,
  bundle_text : String,
  report_text : String,
  options_text : String,
) -> String {
  try {
    let (actual, actual_canonical) = configured_window_reduction_record_v2(
      config_text, policy_text, bundle_text, options_text, true,
    )
    window_report_depth_v2(actual, 64)
    let expected = sql_json_v1(report_text, 67108864)
    let equal = actual_canonical == sql_canonical_v1(expected)
    let result = window_object_v2(actual)
    let valid = equal &&
      result.at("windowVerified") == Json(true) &&
      result.at("reduction") != Json::null() &&
      result.at("status") != Json("invalid")
    (
      {
        "format": "moontxnwitness-configured-window-reduction-verification/v1",
        "valid": Json(valid),
        "reportMatches": Json(equal),
        "status": result.at("status"),
        "refutationVerified": Json(
          valid && result.at("refutationPreserved") == Json(true),
        ),
        "oneMinimalVerified": Json(
          valid &&
          result.at("refutationPreserved") == Json(true) &&
          result.at("oneMinimal") == Json(true),
        ),
        "sourceAuthenticated": false,
        "recomputedSha256": Json(v3_dislock_sha256(actual_canonical)),
      } : Json).stringify()
  } catch {
    error =>
      (
        {
          "format": "moontxnwitness-configured-window-reduction-verification/v1",
          "valid": false,
          "reportMatches": false,
          "refutationVerified": false,
          "oneMinimalVerified": false,
          "sourceAuthenticated": false,
          "reason": Json(error.to_string()),
        } : Json).stringify()
  }
}

///|
fn configured_window_reduction_failure_v2(reason : String) -> Json {
  {
    "format": "moontxnwitness-configured-window-reduction/v1",
    "semanticContract": "verified-configured-window-model-selection/v1",
    "status": Json(configured_window_reduction_error_status_v2(reason)),
    "preserveModel": "serializable",
    "windowVerified": false,
    "refutationPreserved": false,
    "oneMinimal": false,
    "originalWindowRetained": true,
    "sourceAuthenticated": false,
    "reason": Json(reason),
  }
}

///|
fn configured_window_reduction_record_v2(
  config_text : String,
  policy_text : String,
  bundle_text : String,
  options_text : String,
  canonical : Bool,
) -> (Json, String) {
  let record = try {
    let config = match parse_sql_config_v2(config_text) {
      Ok(value) => value
      Err(reason) => fail(reason)
    }
    let policy = sql_json_v1(policy_text, 8192)
    let bundle = sql_json_v1(bundle_text, 33554432)
    let options = configured_window_reduction_options_v2(options_text)
    configured_window_reduction_body_v2(
      config,
      policy,
      bundle,
      v3_dislock_sha256(bundle_text),
      options,
    )
  } catch {
    error => configured_window_reduction_failure_v2(error.to_string())
  }
  window_bounded_record_v2(
    record, canonical, 67108864, "budget:configured-window-reduction-report-bytes",
    configured_window_reduction_failure_v2,
  )
}
