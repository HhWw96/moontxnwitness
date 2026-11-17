// Source-closed transaction selection over an independently verified window.
// No classifier, source fact, candidate rule or old counter is redefined here.

///|
priv struct ConfiguredWindowReductionOptionsV2 {
  window : Json
  relation : WireRelationModelReductionV4
  supplied : Json
}

///|
fn configured_window_reduction_options_v2(
  text : String,
) -> ConfiguredWindowReductionOptionsV2 raise {
  let supplied = sql_json_v1(text, 524288)
  let fields = object_fields(supplied, "configured window reduction options")
  known_fields(
    fields,
    ["preserveModel", "windowOptions", "reductionOptions"],
    "configured window reduction options",
  )
  if required(fields, "preserveModel", "configured window reduction options") !=
    Json("serializable") {
    fail("unsupported:configured-window-reduction-model-must-be-serializable")
  }
  let window = fields.get_or_default("windowOptions", {})
  let _ = object_fields(window, "independent window analysis options")
  if orm_utf8_size(window.stringify()) > 262144 {
    fail("budget:configured-window-reduction-window-options-bytes")
  }
  let reduction = fields.get_or_default("reductionOptions", {})
  let reduced_fields = object_fields(reduction, "independent reduction options")
  known_fields(
    reduced_fields,
    ["maxChecks", "modelOptions"],
    "independent reduction options",
  )
  if orm_utf8_size(reduction.stringify()) > 8192 {
    fail("budget:configured-window-reduction-model-options-bytes")
  }
  let model_fields = object_fields(
    reduced_fields.get_or_default("modelOptions", {}),
    "independent reduction model budgets",
  )
  // Only existing numeric budgets are selected here. The caller cannot replace
  // the model, facts, source profile, logical clients or ordering assumptions.
  known_fields(
    model_fields,
    ["maxSourceChecks", "maxStates", "maxEdgeChecks"],
    "independent reduction model budgets",
  )
  let relation = wire_relation_model_reduction_options_v4(
    (
      {
        "model": "serializable",
        "maxChecks": Json(wire_v4_int(reduced_fields, "maxChecks", 256, 256)),
        "modelOptions": {
          "models": ["serializable"],
          "maxSourceChecks": Json(
            wire_v4_int(model_fields, "maxSourceChecks", 1000000, 1000000),
          ),
          "maxStates": Json(
            wire_v4_int(model_fields, "maxStates", 100000, 100000),
          ),
          "maxEdgeChecks": Json(
            wire_v4_int(model_fields, "maxEdgeChecks", 1000000, 1000000),
          ),
          // The current history has a derived program-order clock. This adapter
          // makes no new real-time/session claim, and never infers one from a pool.
          "realtimeKnown": false,
        },
      } : Json).stringify(),
  )
  { window, relation, supplied, }
}

///|
fn configured_window_reduction_error_status_v2(reason : String) -> String {
  if reason.contains("budget:") || reason.contains("unsupported:") {
    "unknown"
  } else {
    "invalid"
  }
}

///|
fn configured_window_reduction_serial_positive_v2(window : Json) -> Bool raise {
  let serial = window_object_v2(window_object_v2(window).at("serialReplay"))
  let judgment = window_object_v2(serial.at("judgment"))
  judgment.at("status") == Json("consistent") &&
  window_object_v2(judgment.at("evidence")).at("kind") ==
  Json("serial-relation-replay")
}

///|
fn configured_window_reduction_existing_v2(
  window : Json,
  selected : WireRelationModelReductionV4,
) -> Json raise {
  let observed = window_object_v2(window)
  let history_text = observed.at("history").stringify()
  // Preserve the existing model reduction's 8 MiB original-facts wire limit.
  if orm_utf8_size(history_text) > 8388608 {
    fail("budget:configured-window-reduction-derived-history-bytes")
  }
  let facts = wire_relation_models_facts_v4(history_text, selected.wire)
  let reduced = reduce_relation_models_v4(
    facts,
    selected.model,
    selected.wire.wire.options,
    max_checks=selected.checks,
    realtime_known=selected.wire.realtime_known,
  )
  let reduction = relation_model_reduction_v4_json(reduced)
  if orm_utf8_size(reduction.stringify()) > 33554432 {
    fail("budget:configured-window-reduction-nested-report-bytes")
  }
  let r = window_object_v2(reduction)
  if r.at("semanticContract") != Json("relation-predicate-model-reduction/v1") ||
    r.at("classificationContract") != Json("relation-predicate-models/v1") ||
    r.at("preserveModel") != Json("serializable") {
    fail("unsupported:configured-window-reduction-nested-contract")
  }
  if window_object_v2(r.at("originalFacts")).at("history") !=
    observed.at("history") {
    fail("mismatch:configured-window-reduction-original-history-binding")
  }
  reduction
}

///|
fn configured_window_reduction_body_v2(
  config : SQLConfigV2,
  policy : Json,
  bundle : Json,
  bundle_digest : String,
  options : ConfiguredWindowReductionOptionsV2,
) -> Json raise {
  // Recompute directly from original inputs. In particular, no history,
  // completeness flag, source map or classification is accepted from a report.
  let window : Json = try {
    let report = window_analysis_body_v2(
      config,
      policy,
      bundle,
      options.window,
      bundle_digest,
    )
    if orm_utf8_size(report.stringify()) > 33554432 {
      fail("budget:configured-window-reduction-window-report-bytes")
    }
    report
  } catch {
    error => {
      let reason = error.to_string()
      {
        "format": "moontxnwitness-configured-window-analysis/v2",
        "status": Json(configured_window_reduction_error_status_v2(reason)),
        "coverageComplete": false,
        "sourceMappingVerified": false,
        "writerWindowVerified": false,
        "sourceAuthenticated": false,
        "reason": Json(reason),
      }
    }
  }
  let observed = window_object_v2(window)
  let window_verified = observed.at("coverageComplete") == Json(true) &&
    observed.at("sourceMappingVerified") == Json(true) &&
    observed.at("writerWindowVerified") == Json(true)
  let record : Json = {
    "format": "moontxnwitness-configured-window-reduction/v1",
    "semanticContract": "verified-configured-window-model-selection/v1",
    "windowSemanticContract": "postgres18-source-bound-point-crud-row-slots/v2",
    "classificationContract": "relation-predicate-models/v1",
    "reductionSemanticContract": "relation-predicate-model-reduction/v1",
    "algorithm": "verified-window-source-closed-relation-model-selection-1",
    "status": Json(
      if observed.at("status") == Json("invalid") {
        "invalid"
      } else {
        "unknown"
      },
    ),
    "preserveModel": "serializable",
    "requiredOutcome": "refuted",
    "windowVerified": Json(window_verified),
    "refutationPreserved": false,
    "oneMinimal": false,
    "sourceAuthenticated": false,
    "originalWindowRetained": true,
    "bundleSha256": Json(bundle_digest),
    "configSha256": Json(config.digest),
    "policySha256": Json(v3_dislock_sha256(sql_canonical_v1(policy))),
    "optionsSha256": Json(v3_dislock_sha256(sql_canonical_v1(options.supplied))),
    "suppliedOptions": options.supplied,
    "effectiveReductionOptions": wire_relation_model_reduction_record_v4(
      options.relation,
    ),
    "window": window,
    "reduction": Json::null(),
    "selectionSemantics": "analysis-only transaction selection over an independently verified immutable window; original bundle and all source records remain required for verification",
  }
  let output = window_object_v2(record)
  if !window_verified {
    output["reason"] = observed.get_or_default(
      "reason",
      Json("unsupported:configured-window-reduction-unverified-window"),
    )
    return record
  }
  if observed.at("semanticContract") !=
    Json("postgres18-source-bound-point-crud-row-slots/v2") {
    fail("unsupported:configured-window-reduction-window-contract")
  }
  let reduction = configured_window_reduction_existing_v2(
    window,
    options.relation,
  ) catch {
    error => {
      output["status"] = Json(
        configured_window_reduction_error_status_v2(error.to_string()),
      )
      output["reason"] = Json(error.to_string())
      // Keep the successful original window proof even if the independent
      // reduction cannot be completed within its own scope or byte budget.
      return record
    }
  }
  let r = window_object_v2(reduction)
  output["reduction"] = reduction
  output["execution"] = {
    "counterContract": "window-and-relation-reduction-separated-counters-1",
    "window": observed.at("execution"),
    "reduction": r.at("execution"),
  }
  let initial = window_object_v2(r.at("initialClassification"))
  let final_classification = window_object_v2(r.at("classification"))
  let initial_refuted = initial.at("status") == Json("refuted")
  let final_refuted = final_classification.at("status") == Json("refuted")
  // Preserve both reports in a contradictory result. It is a failure of the
  // composition, not permission to discard whichever evidence is inconvenient.
  if configured_window_reduction_serial_positive_v2(window) &&
    (initial_refuted || final_refuted) {
    output["status"] = Json("invalid")
    output["contradictoryEvidence"] = Json(true)
    output["reason"] = Json(
      "mismatch:configured-window-serial-positive-vs-relation-model-refutation",
    )
    return record
  }
  let coverage = window_object_v2(r.at("sourceCoverage"))
  let preserved = initial_refuted &&
    final_refuted &&
    coverage.at("originalSourceClosed") == Json(true) &&
    coverage.at("originalSequenceWindowClosed") == Json(true) &&
    coverage.at("reducedSourceClosed") == Json(true)
  output["status"] = r.at("status")
  output["refutationPreserved"] = Json(preserved)
  // An unknown, source-open or unfinished candidate cannot acquire this flag
  // from window validity, a retained cycle, or a supplied report field.
  output["oneMinimal"] = Json(preserved && r.at("oneMinimal") == Json(true))
  record
}

///|
pub fn reduce_configured_window_v2_json(
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
pub fn verify_configured_window_reduction_v2_json(
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
