///|
fn wire_relation_options_v4(
  text : String,
) -> (Array[String], Int32, Int32, Int32) raise {
  let fields = object_fields(
    guarded_json(text, limit=8192),
    "relation category options v4",
  )
  known_fields(
    fields,
    ["categories", "maxStates", "maxEdgeChecks", "maxGraphChecks"],
    "relation category options v4",
  )
  let seen : Map[String, Bool] = Map([])
  let categories = match fields.get("categories") {
    None => relation_classification_categories_v4()
    Some(Array(values)) if !values.is_empty() && values.length() <= 6 =>
      values.map(value => {
        match value {
          String(name) if relation_classification_categories_v4().contains(name) &&
            !seen.contains(name) => {
            seen[name] = true
            name
          }
          _ =>
            fail(
              "categories must be distinct supported relation category names",
            )
        }
      })
    _ => fail("categories must contain 1..6 supported relation category names")
  }
  (
    categories,
    wire_v4_int(fields, "maxStates", 100000, 100000),
    wire_v4_int(fields, "maxEdgeChecks", 1000000, 1000000),
    wire_v4_int(fields, "maxGraphChecks", 1000000, 1000000),
  )
}

///|
pub fn classify_relation_v4_json(
  text : String,
  options_text : String,
) -> String {
  try {
    let (categories, max_states, max_edge_checks, max_graph_checks) = wire_relation_options_v4(
      options_text,
    )
    render_relation_classification_v4(
      classify_relation_point_v4(
        wire_v4_history(text),
        categories~,
        max_states~,
        max_edge_checks~,
        max_graph_checks~,
      ),
    )
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
pub fn verify_relation_classification_v4_json(
  text : String,
  report_text : String,
  options_text : String,
) -> String {
  try {
    let (categories, max_states, max_edge_checks, max_graph_checks) = wire_relation_options_v4(
      options_text,
    )
    wire_v4_verified(
      verify_relation_classification_v4(
        wire_v4_history(text),
        guarded_json(report_text, limit=33554432),
        categories~,
        max_states~,
        max_edge_checks~,
        max_graph_checks~,
      ),
    )
  } catch {
    _ => wire_v4_verified(false)
  }
}

///|
pub fn inspect_capture_anomalies_v4_json(
  text : String,
  options_text : String,
) -> String {
  try {
    let max_checks = wire_v4_anomaly_options(options_text)
    capture_anomalies_v4_json(
      inspect_capture_anomalies_v4(wire_v4_history(text), max_checks~),
    ).stringify(indent=2)
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
pub fn verify_capture_anomalies_v4_json(
  text : String,
  report_text : String,
  options_text : String,
) -> String {
  try {
    let max_checks = wire_v4_anomaly_options(options_text)
    let expected = capture_anomalies_v4_json(
      inspect_capture_anomalies_v4(wire_v4_history(text), max_checks~),
    )
    wire_v4_verified(guarded_json(report_text, limit=33554432) == expected)
  } catch {
    _ => wire_v4_verified(false)
  }
}

///|
pub fn inspect_internal_consistency_v4_json(
  text : String,
  options_text : String,
) -> String {
  try {
    let max_checks = wire_v4_anomaly_options(options_text)
    internal_consistency_v4_json(
      inspect_internal_consistency_v4(wire_v4_history(text), max_checks~),
    ).stringify(indent=2)
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
pub fn verify_internal_consistency_v4_json(
  text : String,
  report_text : String,
  options_text : String,
) -> String {
  try {
    let max_checks = wire_v4_anomaly_options(options_text)
    wire_v4_verified(
      verify_internal_consistency_v4(
        wire_v4_history(text),
        guarded_json(report_text, limit=33554432),
        max_checks~,
      ),
    )
  } catch {
    _ => wire_v4_verified(false)
  }
}

///|
/// Keep duplicate-key and depth validation before host JSON inspection.
pub fn source_rules_report_v4_content_json(text : String) -> String {
  try {
    let value = guarded_json(text, limit=33554432)
    let _ = object_fields(value, "source rules report v4")
    ({ "valid": true, "value": value } : Json).stringify()
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
/// Independent envelope. Producer version is metadata, never a replay selector.
pub fn source_rules_capsule_v4_content_json(text : String) -> String {
  try {
    let value = guarded_json(text, limit=67108864)
    let fields = object_fields(value, "source rules capsule v4")
    known_fields(
      fields,
      [
        "format", "schemaVersion", "tool", "producer", "operation", "semanticContract",
        "algorithm", "counterContract", "profile", "sourceText", "sourceSha256",
        "optionsText", "optionsSha256", "reportText", "reportSha256",
      ],
      "source rules capsule v4",
    )
    if fields.get("format") !=
      Some(Json("moontxnwitness-source-rules-replay/v4")) ||
      fields.get("schemaVersion") != Some(Json(4)) ||
      fields.get("tool") != Some(Json("MoonTxnWitness")) {
      fail("Unsupported source rules v4 capsule")
    }
    for
      name in [
        "operation", "semanticContract", "algorithm", "counterContract", "profile",
        "sourceText", "sourceSha256", "optionsText", "optionsSha256", "reportText",
        "reportSha256",
      ] {
      match required(fields, name, "source rules capsule v4") {
        String(_) => ()
        _ => fail("Capsule fields must be text")
      }
    }
    let producer = object_fields(
      required(fields, "producer", "source rules capsule v4"),
      "producer",
    )
    known_fields(producer, ["version"], "producer")
    match required(producer, "version", "producer") {
      String(_) => ()
      _ => fail("Producer version must be text")
    }
    value.stringify()
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}
