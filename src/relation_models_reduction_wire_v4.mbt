///|
priv struct WireRelationModelReductionV4 {
  model : ElleModelV4
  wire : WireRelationModelsOptionsV4
  checks : Int32
}

///|
fn wire_relation_model_reduction_options_v4(
  text : String,
) -> WireRelationModelReductionV4 raise {
  let fields = object_fields(
    sql_json_v1(text, 8192),
    "relation model reduction options",
  )
  known_fields(
    fields,
    ["model", "modelOptions", "maxChecks"],
    "relation model reduction options",
  )
  let model = wire_model_name_v4(
    required(fields, "model", "relation model reduction options"),
  )
  let nested = fields.get_or_default("modelOptions", Json::object(Map([])))
  let _ = object_fields(nested, "relation model options")
  {
    model,
    wire: wire_relation_models_options_v4(nested.stringify()),
    checks: wire_v4_int(fields, "maxChecks", 256, 256),
  }
}

///|
fn wire_relation_model_reduction_record_v4(
  value : WireRelationModelReductionV4,
) -> Json {
  {
    "model": Json(model_name_v4(value.model)),
    "modelOptions": wire_relation_models_options_record_v4(value.wire),
    "maxChecks": Json(value.checks),
  }
}

///|
fn wire_relation_model_reduce_v4(
  text : String,
  options : String,
) -> RelationModelReductionV4 raise {
  let selected = wire_relation_model_reduction_options_v4(options)
  reduce_relation_models_v4(
    wire_relation_models_facts_v4(text, selected.wire),
    selected.model,
    selected.wire.wire.options,
    max_checks=selected.checks,
    realtime_known=selected.wire.realtime_known,
  )
}

///|
pub fn relation_model_reduction_options_v4_content_json(
  text : String,
) -> String {
  (
    {
      "valid": true,
      "options": wire_relation_model_reduction_record_v4(
        wire_relation_model_reduction_options_v4(text),
      ),
    } : Json).stringify() catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
pub fn reduce_relation_models_v4_json(
  text : String,
  options : String,
) -> String {
  relation_model_reduction_v4_json(wire_relation_model_reduce_v4(text, options)).stringify(
    indent=2,
  ) catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
pub fn verify_relation_model_reduction_v4_json(
  text : String,
  report : String,
  expected_options : String,
) -> String {
  try {
    let selected = wire_relation_model_reduction_options_v4(expected_options)
    wire_v4_verified(
      verify_relation_model_reduction_v4(
        wire_relation_models_facts_v4(text, selected.wire),
        sql_json_v1(report, 33554432),
        selected.model,
        selected.wire.wire.options,
        max_checks=selected.checks,
        realtime_known=selected.wire.realtime_known,
      ),
    )
  } catch {
    _ => wire_v4_verified(false)
  }
}

///|
fn wire_relation_model_digest_v4(value : Json) -> Bool {
  match value {
    String(digest) =>
      digest.length() == 64 &&
      digest.iter().all(c => (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))
    _ => false
  }
}

///|
pub fn relation_model_reduction_report_v4_content_json(text : String) -> String {
  try {
    let value = sql_json_v1(text, 33554432)
    let fields = object_fields(value, "relation model reduction report")
    let names = [
      "format", "schemaVersion", "semanticContract", "classificationContract", "algorithm",
      "status", "preserveModel", "requiredOutcome", "sourceSha256", "originalFacts",
      "selectedTransactions", "selectedOriginalEvents", "originalEventSequence",
      "analysisView", "analysisViewSemantics", "removedTransactions", "oneMinimal",
      "oneMinimalScope", "unresolvedCandidates", "sourceCoverage", "initialClassification",
      "classification", "execution", "sourcePolicy",
    ]
    known_fields(fields, names, "relation model reduction report")
    for name in names {
      ignore(required(fields, name, "relation model reduction report"))
    }
    if fields.at("format") != Json("moontxnwitness-relation-model-reduction/v4") ||
      fields.at("schemaVersion") != Json(4) ||
      fields.at("semanticContract") !=
      Json("relation-predicate-model-reduction/v1") ||
      fields.at("classificationContract") !=
      Json("relation-predicate-models/v1") ||
      fields.at("algorithm") !=
      Json("source-closed-single-delete-fixed-relation-model-1") ||
      fields.at("requiredOutcome") != Json("refuted") {
      fail("Unsupported relation model reduction report identity")
    }
    ignore(wire_model_name_v4(fields.at("preserveModel")))
    if !wire_relation_model_digest_v4(fields.at("sourceSha256")) {
      fail("Report source digest must be lower-case SHA-256")
    }
    match fields.at("oneMinimal") {
      True | False => ()
      _ => fail("oneMinimal must be boolean")
    }
    let execution = object_fields(
      fields.at("execution"),
      "relation model reduction execution",
    )
    known_fields(
      execution,
      [
        "counterContract", "candidateChecks", "passes", "maxChecks", "candidateLimitReached",
        "candidateBudgetExhausted", "candidateAudit", "finalRevalidation", "suppliedOptions",
        "classificationOptions",
      ],
      "relation model reduction execution",
    )
    if execution.get("counterContract") !=
      Some(Json("relation-model-single-delete-candidate-checks-1")) {
      fail("Unsupported relation model reduction counter contract")
    }
    let source_policy = object_fields(
      fields.at("sourcePolicy"),
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
pub fn relation_model_reduction_capsule_v4_content_json(
  text : String,
) -> String {
  try {
    let value = sql_json_v1(text, 67108864)
    let fields = object_fields(value, "relation model reduction capsule")
    let names = [
      "format", "schemaVersion", "tool", "producer", "operation", "semanticContract",
      "classificationContract", "algorithm", "counterContract", "sourceText", "sourceSha256",
      "optionsText", "optionsSha256", "reportText", "reportSha256",
    ]
    known_fields(fields, names, "relation model reduction capsule")
    for name in names {
      ignore(required(fields, name, "relation model reduction capsule"))
    }
    if fields.at("format") !=
      Json("moontxnwitness-relation-model-reduction-replay/v4") ||
      fields.at("schemaVersion") != Json(4) ||
      fields.at("tool") != Json("MoonTxnWitness") ||
      fields.at("operation") != Json("reduce-relation-models") ||
      fields.at("semanticContract") !=
      Json("relation-predicate-model-reduction/v1") ||
      fields.at("classificationContract") !=
      Json("relation-predicate-models/v1") ||
      fields.at("algorithm") !=
      Json("source-closed-single-delete-fixed-relation-model-1") ||
      fields.at("counterContract") !=
      Json("relation-model-single-delete-candidate-checks-1") {
      fail("Unsupported relation model reduction capsule identity")
    }
    let producer = object_fields(fields.at("producer"), "producer")
    known_fields(producer, ["version"], "producer")
    match required(producer, "version", "producer") {
      String(_) => ()
      _ => fail("Producer version must be text")
    }
    for name in ["sourceText", "optionsText", "reportText"] {
      match fields.at(name) {
        String(_) => ()
        _ => fail("Capsule payloads must be text")
      }
    }
    for name in ["sourceSha256", "optionsSha256", "reportSha256"] {
      if !wire_relation_model_digest_v4(fields.at(name)) {
        fail("Capsule digests must be lower-case SHA-256")
      }
    }
    ({ "valid": true, "value": value } : Json).stringify()
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}
