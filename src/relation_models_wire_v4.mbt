///|
priv struct WireRelationModelsOptionsV4 {
  wire : WireModelOptionsV4
  realtime_known : Bool
}

///|
// Keep new namespace policy and duplicate-key checks outside the old parser.
fn wire_relation_models_options_v4(
  text : String,
) -> WireRelationModelsOptionsV4 raise {
  let fields = object_fields(sql_json_v1(text, 8192), "relation model options")
  let realtime_known = match fields.get("realtimeKnown") {
    None | Some(True) => true
    Some(False) => false
    _ => fail("realtimeKnown must be a boolean")
  }
  fields.remove("realtimeKnown")
  {
    wire: wire_model_options_v4(Json::object(fields).stringify()),
    realtime_known,
  }
}

///|
fn wire_relation_models_options_record_v4(
  value : WireRelationModelsOptionsV4,
) -> Json {
  let record = wire_model_options_record_v4(value.wire)
  object_fields_unchecked_v3(record)["realtimeKnown"] = Json(
    value.realtime_known,
  )
  record
}

///|
fn wire_relation_models_facts_v4(
  text : String,
  wire : WireRelationModelsOptionsV4,
) -> ModelFactsV4 raise {
  let _ = sql_json_v1(text, 8388608)
  let facts = wire_model_facts_v4(text, wire.wire)
  match facts.history.payload {
    RelationSnapshot(_) => facts
    _ => fail("relation models require relation-set-v1")
  }
}

///|
pub fn relation_model_options_v4_content_json(text : String) -> String {
  try {
    let wire = wire_relation_models_options_v4(text)
    (
      { "valid": true, "options": wire_relation_models_options_record_v4(wire) } :
      Json).stringify()
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
pub fn classify_relation_models_v4_json(
  text : String,
  options_text : String,
) -> String {
  try {
    let wire = wire_relation_models_options_v4(options_text)
    match
      classify_relation_models_v4(
        wire_relation_models_facts_v4(text, wire),
        wire.wire.options,
        realtime_known=wire.realtime_known,
      ) {
      Ok(result) =>
        relation_model_classification_v4_json(result).stringify(indent=2)
      Err(reason) => wire_v4_failure(reason)
    }
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
pub fn verify_relation_models_v4_json(
  text : String,
  report_text : String,
  expected_options_text : String,
) -> String {
  try {
    let wire = wire_relation_models_options_v4(expected_options_text)
    wire_v4_verified(
      verify_relation_models_v4(
        wire_relation_models_facts_v4(text, wire),
        sql_json_v1(report_text, 33554432),
        wire.wire.options,
        realtime_known=wire.realtime_known,
      ),
    )
  } catch {
    _ => wire_v4_verified(false)
  }
}

///|
// Transport validation cannot replace original-source semantic recomputation.
pub fn relation_model_report_v4_content_json(text : String) -> String {
  try {
    let value = sql_json_v1(text, 33554432)
    let fields = object_fields(value, "relation model report")
    if fields.get("format") !=
      Some(Json("moontxnwitness-relation-model-composition/v4")) ||
      fields.get("schemaVersion") != Some(Json(4)) ||
      fields.get("semanticContract") !=
      Some(Json("relation-predicate-models/v1")) ||
      fields.get("algorithm") !=
      Some(Json("predicate-source-scoped-graph-and-original-prefix-search-1")) {
      fail("Unsupported relation model report identity")
    }
    let execution = object_fields(
      required(fields, "execution", "relation model report"),
      "relation model execution",
    )
    if execution.get("counterContract") !=
      Some(
        Json(
          "relation-model-independent-source-scoped-graph-and-prefix-counters-1",
        ),
      ) {
      fail("Unsupported relation model counter contract")
    }
    let source_policy = object_fields(
      required(fields, "sourcePolicy", "relation model report"),
      "relation source policy",
    )
    known_fields(source_policy, ["realtimeKnown"], "relation source policy")
    match required(source_policy, "realtimeKnown", "relation source policy") {
      True | False => ()
      _ => fail("Relation source policy realtimeKnown must be boolean")
    }
    ({ "valid": true, "value": value } : Json).stringify()
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
pub fn relation_model_capsule_v4_content_json(text : String) -> String {
  try {
    let value = sql_json_v1(text, 67108864)
    let fields = object_fields(value, "relation model capsule")
    known_fields(
      fields,
      [
        "format", "schemaVersion", "tool", "producer", "operation", "semanticContract",
        "algorithm", "counterContract", "sourceText", "sourceSha256", "optionsText",
        "optionsSha256", "reportText", "reportSha256",
      ],
      "relation model capsule",
    )
    if fields.get("format") !=
      Some(Json("moontxnwitness-relation-model-replay/v4")) ||
      fields.get("schemaVersion") != Some(Json(4)) ||
      fields.get("tool") != Some(Json("MoonTxnWitness")) ||
      fields.get("operation") != Some(Json("classify-relation-models")) ||
      fields.get("semanticContract") !=
      Some(Json("relation-predicate-models/v1")) ||
      fields.get("algorithm") !=
      Some(Json("predicate-source-scoped-graph-and-original-prefix-search-1")) ||
      fields.get("counterContract") !=
      Some(
        Json(
          "relation-model-independent-source-scoped-graph-and-prefix-counters-1",
        ),
      ) {
      fail("Unsupported relation model capsule identity")
    }
    let producer = object_fields(
      required(fields, "producer", "relation model capsule"),
      "producer",
    )
    known_fields(producer, ["version"], "producer")
    match required(producer, "version", "producer") {
      String(_) => ()
      _ => fail("Producer version must be text")
    }
    for name in ["sourceText", "optionsText", "reportText"] {
      match required(fields, name, "relation model capsule") {
        String(_) => ()
        _ => fail("Relation model capsule payloads must be text")
      }
    }
    for name in ["sourceSha256", "optionsSha256", "reportSha256"] {
      match required(fields, name, "relation model capsule") {
        String(digest) if digest.length() == 64 &&
          digest
          .iter()
          .all(c => (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) => ()
        _ => fail("Relation model capsule digest must be lower-case SHA-256")
      }
    }
    ({ "valid": true, "value": value } : Json).stringify()
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}
