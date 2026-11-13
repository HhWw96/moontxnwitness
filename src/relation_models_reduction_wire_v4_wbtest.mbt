///|
fn rmrwire_source() -> String {
  rmt_facts(rrt_g2_body(noise=1)).history.source_text
}

///|
test "relation model reduction wire 01 explicit target produces a verified closed selection" {
  let source = rmrwire_source()
  let options = "{\"model\":\"serializable\"}"
  let report = reduce_relation_models_v4_json(source, options)
  assert_eq(rmwire_status(report, "status"), Json("reduced"))
  assert_eq(rmwire_status(report, "preserveModel"), Json("serializable"))
  assert_eq(rmwire_status(report, "oneMinimal"), Json(true))
  assert_eq(
    rmwire_status(
      relation_model_reduction_report_v4_content_json(report),
      "valid",
    ),
    Json(true),
  )
  assert_eq(
    verify_relation_model_reduction_v4_json(source, report, options),
    wire_v4_verified(true),
  )
}

///|
test "relation model reduction wire 02 envelope requires one exact target and bounded budgets" {
  for
    options in [
      "{}", "[]", "null", "{\"model\":\"unknown\"}", "{\"model\":[\"serializable\"]}",
      "{\"model\":\"serializable\",\"maxChecks\":-1}", "{\"model\":\"serializable\",\"maxChecks\":257}",
      "{\"model\":\"serializable\",\"maxChecks\":0.5}", "{\"model\":\"serializable\",\"maxChecks\":true}",
      "{\"model\":\"serializable\",\"complete\":true}", "{\"model\":\"serializable\",\"modelOptions\":null}",
      "{\"model\":\"serializable\",\"modelOptions\":{\"maxStates\":100001}}", "{\"model\":\"serializable\",\"modelOptions\":{\"models\":[\"unknown\"]}}",
    ] {
    assert_eq(
      rmwire_status(
        relation_model_reduction_options_v4_content_json(options),
        "status",
      ),
      Json("invalid"),
    )
  }
}

///|
test "relation model reduction wire 03 duplicate decoded envelope and nested keys reject first" {
  for
    options in [
      "{\"model\":\"serializable\",\"mo\\u0064el\":\"read-uncommitted\"}", "{\"model\":\"serializable\",\"maxChecks\":0,\"max\\u0043hecks\":256}",
      "{\"model\":\"serializable\",\"modelOptions\":{\"maxStates\":0,\"max\\u0053tates\":100000}}",
      "{\"model\":\"serializable\",\"modelOptions\":{\"clients\":[{\"id\":\"a\",\"transactions\":[],\"trans\\u0061ctions\":[]}]}}",
    ] {
    assert_eq(
      rmwire_status(
        reduce_relation_models_v4_json(rmrwire_source(), options),
        "status",
      ),
      Json("invalid"),
    )
  }
}

///|
test "relation model reduction wire 04 zero candidate budget is bound independently" {
  let source = rmrwire_source()
  let options = "{\"model\":\"serializable\",\"maxChecks\":0}"
  let report = reduce_relation_models_v4_json(source, options)
  assert_eq(rmwire_status(report, "status"), Json("budget"))
  assert_eq(
    verify_relation_model_reduction_v4_json(source, report, options),
    wire_v4_verified(true),
  )
  assert_eq(
    verify_relation_model_reduction_v4_json(
      source, report, "{\"model\":\"serializable\"}",
    ),
    wire_v4_verified(false),
  )
}

///|
test "relation model reduction wire 05 selected model and nested limits cannot be read from report" {
  let source = rmrwire_source()
  let options = "{\"model\":\"serializable\",\"modelOptions\":{\"maxStates\":99999}}"
  let report = reduce_relation_models_v4_json(source, options)
  assert_eq(
    verify_relation_model_reduction_v4_json(source, report, options),
    wire_v4_verified(true),
  )
  assert_eq(
    verify_relation_model_reduction_v4_json(
      source, report, "{\"model\":\"read-committed\"}",
    ),
    wire_v4_verified(false),
  )
  assert_eq(
    verify_relation_model_reduction_v4_json(
      source, report, "{\"model\":\"serializable\"}",
    ),
    wire_v4_verified(false),
  )
  assert_eq(
    verify_relation_model_reduction_v4_json(source, report, "{}"),
    wire_v4_verified(false),
  )
}

///|
test "relation model reduction wire 06 duplicate sources and foreign data models fail closed" {
  let source = rmrwire_source()
  let duplicate = "{\"traceSchema\":3," + source[1:].to_owned()
  let options = "{\"model\":\"serializable\"}"
  assert_eq(
    rmwire_status(reduce_relation_models_v4_json(duplicate, options), "status"),
    Json("invalid"),
  )
  assert_eq(
    rmwire_status(
      reduce_relation_models_v4_json(wire034_source(), options),
      "status",
    ),
    Json("invalid"),
  )
}

///|
test "relation model reduction wire 07 duplicate report keys never hide a changed minimum" {
  let source = rmrwire_source()
  let options = "{\"model\":\"serializable\"}"
  let report = reduce_relation_models_v4_json(source, options)
  let duplicate = "{\"oneMinimal\":false," + report[1:].to_owned()
  assert_eq(
    rmwire_status(
      relation_model_reduction_report_v4_content_json(duplicate),
      "status",
    ),
    Json("invalid"),
  )
  assert_eq(
    verify_relation_model_reduction_v4_json(source, duplicate, options),
    wire_v4_verified(false),
  )
}

///|
test "relation model reduction wire 08 report identity and extra runtime requests cannot select a checker" {
  let text = reduce_relation_models_v4_json(
    rmrwire_source(),
    "{\"model\":\"serializable\"}",
  )
  for
    name in [
      "format", "semanticContract", "classificationContract", "algorithm",
    ] {
    let report = @json.parse(text)
    object_fields_unchecked_v3(report)[name] = Json("other")
    assert_eq(
      rmwire_status(
        relation_model_reduction_report_v4_content_json(report.stringify()),
        "status",
      ),
      Json("invalid"),
    )
  }
  let report = @json.parse(text)
  object_fields_unchecked_v3(report)["runtimePath"] = Json("another")
  assert_eq(
    rmwire_status(
      relation_model_reduction_report_v4_content_json(report.stringify()),
      "status",
    ),
    Json("invalid"),
  )
}

///|
fn rmrwire_capsule() -> Json {
  let digest = String::make(64, '0')
  {
    "format": "moontxnwitness-relation-model-reduction-replay/v4",
    "schemaVersion": 4,
    "tool": "MoonTxnWitness",
    "producer": { "version": "example" },
    "operation": "reduce-relation-models",
    "semanticContract": "relation-predicate-model-reduction/v1",
    "classificationContract": "relation-predicate-models/v1",
    "algorithm": "source-closed-single-delete-fixed-relation-model-1",
    "counterContract": "relation-model-single-delete-candidate-checks-1",
    "sourceText": "{}",
    "optionsText": "{}",
    "reportText": "{}",
    "sourceSha256": Json(digest),
    "optionsSha256": Json(digest),
    "reportSha256": Json(digest),
  }
}

///|
test "relation model reduction wire 09 capsule transport is strict without granting semantic trust" {
  assert_eq(
    rmwire_status(
      relation_model_reduction_capsule_v4_content_json(
        rmrwire_capsule().stringify(),
      ),
      "valid",
    ),
    Json(true),
  )
  for
    name in [
      "format", "operation", "semanticContract", "classificationContract", "counterContract",
      "sourceSha256",
    ] {
    let capsule = rmrwire_capsule()
    object_fields_unchecked_v3(capsule)[name] = Json("other")
    assert_eq(
      rmwire_status(
        relation_model_reduction_capsule_v4_content_json(capsule.stringify()),
        "status",
      ),
      Json("invalid"),
    )
  }
}

///|
test "relation model reduction wire 10 duplicate capsule and unknown producer fields reject" {
  let raw = rmrwire_capsule().stringify()
  let duplicate = "{\"schemaVersion\":4," + raw[1:].to_owned()
  assert_eq(
    rmwire_status(
      relation_model_reduction_capsule_v4_content_json(duplicate),
      "status",
    ),
    Json("invalid"),
  )
  let capsule = rmrwire_capsule()
  object_fields_unchecked_v3(capture_field(capsule, "producer"))["code"] = Json(
    "run",
  )
  assert_eq(
    rmwire_status(
      relation_model_reduction_capsule_v4_content_json(capsule.stringify()),
      "status",
    ),
    Json("invalid"),
  )
}

///|
test "relation model reduction wire 11 nested real-time policy is independent at verify" {
  let source = rmt_facts(rmt_stale_external()).history.source_text
  let options = "{\"model\":\"strict-serializable\",\"modelOptions\":{\"realtimeKnown\":false}}"
  let report = reduce_relation_models_v4_json(source, options)
  assert_eq(rmwire_status(report, "status"), Json("unknown"))
  assert_eq(
    verify_relation_model_reduction_v4_json(source, report, options),
    wire_v4_verified(true),
  )
  assert_eq(
    verify_relation_model_reduction_v4_json(
      source, report, "{\"model\":\"strict-serializable\"}",
    ),
    wire_v4_verified(false),
  )
  assert_eq(
    rmwire_status(
      relation_model_reduction_report_v4_content_json(report),
      "valid",
    ),
    Json(true),
  )
}
