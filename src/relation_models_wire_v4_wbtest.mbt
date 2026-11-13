///|
fn rmwire_source() -> String {
  rpred_history(rmt_single()).source_text
}

///|
fn rmwire_status(text : String, name : String) -> Json raise {
  capture_field(@json.parse(text), name)
}

///|
test "relation model wire 01 default six and explicit fourteen preserve distinct semantics" {
  let source = rmwire_source()
  let report = classify_relation_models_v4_json(source, "{}")
  let all = classify_relation_models_v4_json(
    source, "{\"models\":\"elle-core\"}",
  )
  assert_eq(rmwire_status(report, "status"), Json("checked-compatible"))
  assert_eq(v3_test_items(@json.parse(report), "models").length(), 6)
  assert_eq(v3_test_items(@json.parse(all), "models").length(), 14)
  assert_eq(
    rmwire_status(report, "semanticContract"),
    Json("relation-predicate-models/v1"),
  )
  assert_eq(
    rmwire_status(verify_relation_models_v4_json(source, report, "{}"), "valid"),
    Json(true),
  )
  assert_eq(
    rmwire_status(verify_relation_models_v4_json(source, all, "{}"), "valid"),
    Json(false),
  )
}

///|
test "relation model wire 02 wrong data models fail closed" {
  for source in [wire034_source(), mlp_history(mlp_multi()).source_text] {
    assert_eq(
      rmwire_status(classify_relation_models_v4_json(source, "{}"), "status"),
      Json("invalid"),
    )
    assert_eq(
      rmwire_status(verify_relation_models_v4_json(source, "{}", "{}"), "valid"),
      Json(false),
    )
  }
}

///|
test "relation model wire 03 duplicate decoded option keys and unknown policy are rejected" {
  for
    options in [
      "{\"models\":[],\"mo\\u0064els\":[]}", "{\"clients\":[{\"id\":\"a\",\"transactions\":[],\"trans\\u0061ctions\":[]}]}",
      "{\"maxStates\":0,\"maxStates\":1}", "{\"models\":[]}", "{\"models\":[\"serializable\",\"serializable\"]}",
      "{\"models\":[\"unknown\"]}", "{\"complete\":true}", "{\"maxStates\":100001}",
      "{\"maxStates\":-1}", "{\"maxSourceChecks\":1000001}", "{\"maxEdgeChecks\":0.5}",
      "{\"clientsComplete\":1}",
    ] {
    assert_eq(
      rmwire_status(relation_model_options_v4_content_json(options), "status"),
      Json("invalid"),
    )
  }
}

///|
test "relation model wire 04 duplicate source and report keys cannot survive normalization" {
  let source = rmwire_source()
  let duplicate_source = "{\"traceSchema\":3," + source[1:].to_owned()
  assert_eq(
    rmwire_status(
      classify_relation_models_v4_json(duplicate_source, "{}"),
      "status",
    ),
    Json("invalid"),
  )
  let report = classify_relation_models_v4_json(source, "{}")
  let duplicate_report = "{\"schemaVersion\":4," + report[1:].to_owned()
  assert_eq(
    rmwire_status(
      relation_model_report_v4_content_json(duplicate_report),
      "status",
    ),
    Json("invalid"),
  )
  assert_eq(
    rmwire_status(
      verify_relation_models_v4_json(source, duplicate_report, "{}"),
      "valid",
    ),
    Json(false),
  )
}

///|
test "relation model wire 05 graph absence helpers never relabel predicate skew as RR failure" {
  let source = rpred_history(rpred_empty_skew(), empty=true).source_text
  let text = classify_relation_models_v4_json(
    source, "{\"models\":[\"repeatable-read\",\"snapshot-isolation\",\"serializable\"]}",
  )
  let report = @json.parse(text)
  assert_eq(mct_status(report, ElleRepeatableRead), "checked-compatible")
  assert_eq(mct_status(report, ElleSnapshotIsolation), "checked-compatible")
  assert_eq(mct_status(report, ElleSerializable), "refuted")
}

///|
test "relation model wire 06 zero states are unknown and the independent verifier binds the limit" {
  let source = rmwire_source()
  let options = "{\"maxStates\":0}"
  let report = classify_relation_models_v4_json(source, options)
  assert_eq(rmwire_status(report, "status"), Json("unknown"))
  assert_eq(
    rmwire_status(
      verify_relation_models_v4_json(source, report, options),
      "valid",
    ),
    Json(true),
  )
  assert_eq(
    rmwire_status(verify_relation_models_v4_json(source, report, "{}"), "valid"),
    Json(false),
  )
}

///|
test "relation model wire 07 report identity validation does not replace semantic verification" {
  let source = rmwire_source()
  let report = @json.parse(classify_relation_models_v4_json(source, "{}"))
  object_fields_unchecked_v3(report)["status"] = Json("refuted")
  assert_eq(
    rmwire_status(
      relation_model_report_v4_content_json(report.stringify()),
      "valid",
    ),
    Json(true),
  )
  assert_eq(
    rmwire_status(
      verify_relation_models_v4_json(source, report.stringify(), "{}"),
      "valid",
    ),
    Json(false),
  )
  object_fields_unchecked_v3(report)["semanticContract"] = Json("old-models")
  assert_eq(
    rmwire_status(
      relation_model_report_v4_content_json(report.stringify()),
      "status",
    ),
    Json("invalid"),
  )
}

///|
test "relation model wire 08 old generic model reports cannot select the new verifier" {
  let source = rmwire_source()
  let old = classify_models_v4_json(source, "{}")
  assert_eq(
    rmwire_status(relation_model_report_v4_content_json(old), "status"),
    Json("invalid"),
  )
  assert_eq(
    rmwire_status(verify_relation_models_v4_json(source, old, "{}"), "valid"),
    Json(false),
  )
}

///|
fn rmwire_capsule() -> Json {
  let digest = String::make(64, '0')
  {
    "format": "moontxnwitness-relation-model-replay/v4",
    "schemaVersion": 4,
    "tool": "MoonTxnWitness",
    "producer": { "version": "example" },
    "operation": "classify-relation-models",
    "semanticContract": "relation-predicate-models/v1",
    "algorithm": "predicate-source-scoped-graph-and-original-prefix-search-1",
    "counterContract": "relation-model-independent-source-scoped-graph-and-prefix-counters-1",
    "sourceText": "{}",
    "sourceSha256": Json(digest),
    "optionsText": "{}",
    "optionsSha256": Json(digest),
    "reportText": "{}",
    "reportSha256": Json(digest),
  }
}

///|
test "relation model wire 09 strict capsule parsing retains producer metadata without granting semantic trust" {
  let capsule = rmwire_capsule()
  assert_eq(
    rmwire_status(
      relation_model_capsule_v4_content_json(capsule.stringify()),
      "valid",
    ),
    Json(true),
  )
  let fields = object_fields_unchecked_v3(capsule)
  fields["code"] = Json("execute")
  assert_eq(
    rmwire_status(
      relation_model_capsule_v4_content_json(capsule.stringify()),
      "status",
    ),
    Json("invalid"),
  )
}

///|
test "relation model wire 10 capsule duplicates, wrong operations and malformed digests are refused" {
  let raw = rmwire_capsule().stringify()
  let duplicate = "{\"schemaVersion\":4," + raw[1:].to_owned()
  assert_eq(
    rmwire_status(relation_model_capsule_v4_content_json(duplicate), "status"),
    Json("invalid"),
  )
  for field in ["operation", "sourceSha256", "semanticContract"] {
    let capsule = rmwire_capsule()
    object_fields_unchecked_v3(capsule)[field] = Json("wrong")
    assert_eq(
      rmwire_status(
        relation_model_capsule_v4_content_json(capsule.stringify()),
        "status",
      ),
      Json("invalid"),
    )
  }
}

///|
test "relation model wire 11 real-time assurance is a separate new-namespace canonical option" {
  let source = rmt_facts(rmt_stale_external()).history.source_text
  let options = "{\"models\":[\"strict-serializable\"],\"realtimeKnown\":false}"
  let text = classify_relation_models_v4_json(source, options)
  assert_eq(rmwire_status(text, "status"), Json("unknown"))
  assert_eq(
    verify_relation_models_v4_json(source, text, options),
    wire_v4_verified(true),
  )
  assert_eq(
    verify_relation_models_v4_json(
      source, text, "{\"models\":[\"strict-serializable\"]}",
    ),
    wire_v4_verified(false),
  )
  let canonical = @json.parse(relation_model_options_v4_content_json(options))
  assert_eq(
    capture_field(capture_field(canonical, "options"), "realtimeKnown"),
    Json(false),
  )
  assert_eq(
    rmwire_status(
      model_options_v4_content_json("{\"realtimeKnown\":false}"),
      "status",
    ),
    Json("invalid"),
  )
}

///|
test "relation model wire 12 real-time policy must be one decoded boolean key" {
  for
    options in [
      "{\"realtimeKnown\":null}", "{\"realtimeKnown\":0}", "{\"realtimeKnown\":false,\"realtime\\u004bnown\":true}",
    ] {
    assert_eq(
      rmwire_status(relation_model_options_v4_content_json(options), "status"),
      Json("invalid"),
    )
  }
}
