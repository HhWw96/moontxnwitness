///|
priv struct WireInferenceOptionsV4 {
  modules : Array[InferenceModuleV4]
  source : WireModelOptionsV4
  maximum : Int32
}

///|
fn wire_inference_modules_v4(text : String) -> WireInferenceOptionsV4 raise {
  let fields = object_fields(
    sql_json_v1(text, 16384),
    "registered inference options",
  )
  known_fields(
    fields,
    ["modules", "modelOptions", "maxInferenceChecks"],
    "registered inference options",
  )
  let seen : Map[String, Bool] = Map([])
  let modules = match
    required(fields, "modules", "registered inference options") {
    Array(items) if items.length() <= 16 =>
      items.map(raw => {
        let id = identifier(raw, "registered module identity")
        if seen.contains(id) {
          fail("Duplicate registered module identity")
        }
        seen[id] = true
        let kind = match id {
          "original-read-sources/v1" => InferenceReadSources
          "original-version-constraints/v1" => InferenceGivenVersions
          "observed-list-prefixes/v1" => InferenceListPrefixes
          "declared-transaction-orders/v1" => InferenceDeclaredOrders
          _ => fail("Unknown compiled inference module identity")
        }
        builtin_inference_module_v4(kind)
      })
    _ =>
      fail(
        "modules must be an explicit array of at most sixteen registered identities",
      )
  }
  let source = wire_model_options_v4(
    match fields.get("modelOptions") {
      None => "{}"
      Some(value) => value.stringify()
    },
  )
  {
    modules,
    source,
    maximum: wire_v4_int(fields, "maxInferenceChecks", 1000000, 1000000),
  }
}

///|
fn wire_inference_facts_v4(
  text : String,
  wire : WireInferenceOptionsV4,
) -> ModelFactsV4 raise {
  let _ = sql_json_v1(text, 8388608)
  wire_model_facts_v4(text, wire.source)
}

///|
pub fn inference_options_v4_content_json(text : String) -> String {
  try {
    let wire = wire_inference_modules_v4(text)
    (
      {
        "valid": true,
        "options": {
          "modules": Json(wire.modules.map(registered => registered.id)),
          "modelOptions": wire_model_options_record_v4(wire.source),
          "maxInferenceChecks": Json(wire.maximum),
        },
      } : Json).stringify()
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
pub fn infer_dependencies_v4_json(
  text : String,
  options_text : String,
) -> String {
  try {
    let wire = wire_inference_modules_v4(options_text)
    match
      infer_dependencies_v4(
        wire_inference_facts_v4(text, wire),
        wire.modules,
        options=wire.source.options,
        max_inference_checks=wire.maximum,
      ) {
      Ok(result) => inference_v4_json(result).stringify(indent=2)
      Err(reason) => wire_v4_failure(reason)
    }
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
pub fn classify_with_inference_v4_json(
  text : String,
  options_text : String,
) -> String {
  try {
    let wire = wire_inference_modules_v4(options_text)
    match
      classify_with_inference_v4(
        wire_inference_facts_v4(text, wire),
        wire.modules,
        options=wire.source.options,
        max_inference_checks=wire.maximum,
      ) {
      Ok(result) => inference_classification_v4_json(result).stringify(indent=2)
      Err(reason) => wire_v4_failure(reason)
    }
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
pub fn verify_with_inference_v4_json(
  text : String,
  report_text : String,
  expected_options_text : String,
) -> String {
  try {
    let wire = wire_inference_modules_v4(expected_options_text)
    wire_v4_verified(
      verify_with_inference_v4(
        wire_inference_facts_v4(text, wire),
        sql_json_v1(report_text, 67108864),
        wire.modules,
        options=wire.source.options,
        max_inference_checks=wire.maximum,
      ),
    )
  } catch {
    _ => wire_v4_verified(false)
  }
}

///|
pub fn verify_inference_v4_json(
  text : String,
  report_text : String,
  expected_options_text : String,
) -> String {
  try {
    let wire = wire_inference_modules_v4(expected_options_text)
    let actual = sql_json_v1(report_text, 67108864)
    let valid = match
      infer_dependencies_v4(
        wire_inference_facts_v4(text, wire),
        wire.modules,
        options=wire.source.options,
        max_inference_checks=wire.maximum,
      ) {
      Ok(result) => actual == result.record
      Err(_) => false
    }
    wire_v4_verified(valid)
  } catch {
    _ => wire_v4_verified(false)
  }
}

///|
/// Transport validation is separate from semantic recomputation.
pub fn inference_report_v4_content_json(text : String) -> String {
  try {
    let value = sql_json_v1(text, 67108864)
    let fields = object_fields(value, "registered inference report")
    let valid_identity = if fields.get("format") ==
      Some(Json("moontxnwitness-inference/v4")) {
      fields.get("semanticContract") ==
      Some(Json("registered-source-inference-modules/v1")) &&
      fields.get("algorithm") ==
      Some(Json("same-original-index-single-pass-modules-1"))
    } else if fields.get("format") ==
      Some(Json("moontxnwitness-model-inference-composition/v4")) {
      fields.get("semanticContract") ==
      Some(Json("registered-inference-and-model-refutations/v1")) &&
      fields.get("algorithm") ==
      Some(Json("base-models-and-conditional-module-refutations-1"))
    } else {
      false
    }
    if !valid_identity || fields.get("schemaVersion") != Some(Json(4)) {
      fail("Unsupported registered inference report identity")
    }
    ({ "valid": true, "value": value } : Json).stringify()
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}
