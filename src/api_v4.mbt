///|
fn wire_v4_int(
  fields : Map[String, Json],
  name : String,
  fallback : Int32,
  maximum : Int32,
) -> Int32 raise {
  match fields.get(name) {
    None => fallback
    Some(Number(n, ..)) if n >= 0.0 &&
      n <= maximum.to_double() &&
      n.to_int().to_double() == n => n.to_int()
    _ => fail(name + " must be an integer in 0.." + maximum.to_string())
  }
}

///|
fn wire_v4_analysis_options(value : Json) -> AnalysisOptionsV4 raise {
  let fields = object_fields(value, "analysis options v4")
  known_fields(
    fields,
    ["maxAttempts", "maxStates", "maxOperationChecks", "maxCachedStates"],
    "analysis options v4",
  )
  analysis_options_v4(
    max_attempts=wire_v4_int(fields, "maxAttempts", 100000, 100000),
    max_states=wire_v4_int(fields, "maxStates", 100000, 100000),
    max_operation_checks=wire_v4_int(
      fields, "maxOperationChecks", 1000000, 1000000,
    ),
    max_cached_states=wire_v4_int(fields, "maxCachedStates", 50000, 50000),
  )
}

///|
fn wire_v4_classification_options(
  value : Json,
) -> (Array[String], Int32, Int32) raise {
  let fields = object_fields(value, "classification options v4")
  known_fields(
    fields,
    ["categories", "maxStates", "maxEdgeChecks"],
    "classification options v4",
  )
  let seen : Map[String, Bool] = Map([])
  let categories = match fields.get("categories") {
    None => ["G0", "G1c", "G2-item"]
    Some(Array(values)) if !values.is_empty() && values.length() <= 3 =>
      values.map(value => {
        let category = match value {
          String(s) if ["G0", "G1c", "G2-item"].contains(s) && !seen.contains(s) =>
            s
          _ => fail("categories must be distinct supported category names")
        }
        seen[category] = true
        category
      })
    _ =>
      fail(
        "categories must be a nonempty array of distinct supported categories",
      )
  }
  (
    categories,
    wire_v4_int(fields, "maxStates", 100000, 100000),
    wire_v4_int(fields, "maxEdgeChecks", 1000000, 1000000),
  )
}

///|
fn wire_v4_reduction_options(
  value : Json,
) -> (Model, Int32, AnalysisOptionsV4) raise {
  let fields = object_fields(value, "reduction options v4")
  known_fields(
    fields,
    ["preserve", "maxChecks", "analysisOptions"],
    "reduction options v4",
  )
  let preserve = match required(fields, "preserve", "reduction options v4") {
    String("serializable") => Serializable
    String("strict-serializable") => StrictSerializable
    _ =>
      fail("preserve must explicitly name serializable or strict-serializable")
  }
  (
    preserve,
    wire_v4_int(fields, "maxChecks", 256, 256),
    wire_v4_analysis_options(
      fields.get_or_default("analysisOptions", Json::object(Map([]))),
    ),
  )
}

///|
fn wire_v4_history(text : String) -> HistoryV4 raise {
  match parse_history_v4(text) {
    Ok(history) => history
    Err(reason) => fail(reason)
  }
}

///|
fn wire_v4_failure(message : String) -> String {
  let result : Json = {
    "format": "moontxnwitness-wire-error/v4",
    "schemaVersion": 4,
    "status": "invalid",
    "error": Json(message),
  }
  result.stringify(indent=2)
}

///|
pub fn analyze_v4_json(text : String, options_text : String) -> String {
  try {
    let options = wire_v4_analysis_options(
      guarded_json(options_text, limit=8192),
    )
    render_analysis_v4(analyze_v4(wire_v4_history(text), options~))
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
pub fn classify_v4_json(text : String, options_text : String) -> String {
  try {
    let (categories, max_states, max_edge_checks) = wire_v4_classification_options(
      guarded_json(options_text, limit=8192),
    )
    render_classification_v4(
      classify_v4(
        wire_v4_history(text),
        categories~,
        max_states~,
        max_edge_checks~,
      ),
    )
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
pub fn reduce_v4_json(text : String, options_text : String) -> String {
  try {
    let (preserve, max_checks, options) = wire_v4_reduction_options(
      guarded_json(options_text, limit=8192),
    )
    render_reduction_v4(
      reduce_v4(wire_v4_history(text), preserve~, max_checks~, options~),
    )
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
fn wire_v4_verified(valid : Bool) -> String {
  let result : Json = {
    "valid": Json(valid),
    "schemaVersion": 4,
    "scope": "semantic reproduction under caller-supplied options; source observations are not authenticated",
  }
  result.stringify()
}

///|
pub fn verify_v4_json(
  text : String,
  report_text : String,
  options_text : String,
) -> String {
  try {
    let options = wire_v4_analysis_options(
      guarded_json(options_text, limit=8192),
    )
    wire_v4_verified(
      verify_v4(
        wire_v4_history(text),
        guarded_json(report_text, limit=33554432),
        options~,
      ),
    )
  } catch {
    _ => wire_v4_verified(false)
  }
}

///|
pub fn verify_classification_v4_json(
  text : String,
  report_text : String,
  options_text : String,
) -> String {
  try {
    let (categories, max_states, max_edge_checks) = wire_v4_classification_options(
      guarded_json(options_text, limit=8192),
    )
    wire_v4_verified(
      verify_classification_v4(
        wire_v4_history(text),
        guarded_json(report_text, limit=33554432),
        categories~,
        max_states~,
        max_edge_checks~,
      ),
    )
  } catch {
    _ => wire_v4_verified(false)
  }
}

///|
pub fn verify_reduction_v4_json(
  text : String,
  report_text : String,
  options_text : String,
) -> String {
  try {
    let (preserve, max_checks, options) = wire_v4_reduction_options(
      guarded_json(options_text, limit=8192),
    )
    wire_v4_verified(
      verify_reduction_v4(
        wire_v4_history(text),
        guarded_json(report_text, limit=33554432),
        preserve~,
        max_checks~,
        options~,
      ),
    )
  } catch {
    _ => wire_v4_verified(false)
  }
}

///|
/// Duplicate-key guarding also applies to the untrusted outer capsule envelope.
pub fn capsule_v4_content_json(text : String) -> String {
  try {
    let value = guarded_json(text, limit=67108864)
    let fields = object_fields(value, "capsule v4")
    known_fields(
      fields,
      [
        "format", "schemaVersion", "tool", "producer", "operation", "semanticContract",
        "algorithm", "counterContract", "sourceText", "sourceSha256", "optionsText",
        "optionsSha256", "reportText", "reportSha256",
      ],
      "capsule v4",
    )
    if fields.get("format") != Some(Json("moontxnwitness-replay/v4")) ||
      fields.get("schemaVersion") != Some(Json(4)) ||
      fields.get("tool") != Some(Json("MoonTxnWitness")) {
      fail("Unsupported v4 capsule")
    }
    for
      name in [
        "operation", "semanticContract", "algorithm", "counterContract", "sourceText",
        "optionsText", "reportText", "sourceSha256", "optionsSha256", "reportSha256",
      ] {
      match required(fields, name, "capsule v4") {
        String(_) => ()
        _ => fail("Capsule fields must be text")
      }
    }
    match required(fields, "optionsText", "capsule v4") {
      String(options_text) => {
        let _ = guarded_json(options_text, limit=8192)
        ()
      }
      _ => fail("Capsule options must be text")
    }
    let producer = object_fields(
      required(fields, "producer", "capsule v4"),
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
