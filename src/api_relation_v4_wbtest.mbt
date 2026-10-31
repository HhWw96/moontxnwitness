///|
fn wire034_source() -> String {
  (
    {
      "traceSchema": 3,
      "dataModel": "point-register-v1",
      "clockDomain": "wire034",
      "scope": { "exclusiveWriters": true },
      "gaps": [],
      "events": [
        {
          "seq": 1,
          "time": 0,
          "kind": "snapshot",
          "initial": { "x": "x0" },
          "consistent": true,
        },
        { "seq": 2, "time": 1, "kind": "begin", "tx": "R", "connection": "c" },
        {
          "seq": 3,
          "time": 2,
          "kind": "read",
          "tx": "R",
          "key": "x",
          "version": "x0",
        },
        { "seq": 4, "time": 3, "kind": "commit_request", "tx": "R" },
        { "seq": 5, "time": 4, "kind": "commit_ok", "tx": "R" },
      ],
    } : Json).stringify()
}

///|
fn wire034_at(text : String, path : Array[String]) -> Json raise {
  v4_test_at(@json.parse(text), path)
}

///|
test "wire034 01 known nonrelation source remains explicitly unsupported" {
  assert_eq(
    wire034_at(classify_relation_v4_json(wire034_source(), "{}"), [
      "judgment", "status",
    ]),
    Json("unsupported"),
  )
}

///|
test "wire034 02 relation caller budgets are not taken from reports" {
  let text = wire034_source()
  let report = classify_relation_v4_json(text, "{\"maxStates\":0}")
  assert_eq(
    wire034_at(
      verify_relation_classification_v4_json(text, report, "{\"maxStates\":0}"),
      ["valid"],
    ),
    Json(true),
  )
  assert_eq(
    wire034_at(verify_relation_classification_v4_json(text, report, "{}"), [
      "valid",
    ]),
    Json(false),
  )
}

///|
test "wire034 03 unknown relation options rejected" {
  assert_eq(
    wire034_at(
      classify_relation_v4_json(
        wire034_source(),
        "{\"model\":\"read-committed\"}",
      ),
      ["status"],
    ),
    Json("invalid"),
  )
}

///|
test "wire034 04 repeated relation category rejected" {
  assert_eq(
    wire034_at(
      classify_relation_v4_json(
        wire034_source(),
        "{\"categories\":[\"G0\",\"G0\"]}",
      ),
      ["status"],
    ),
    Json("invalid"),
  )
}

///|
test "wire034 05 category names never silently ignored" {
  for categories in ["[]", "[\"serializable\"]", "[\"G-single\"]", "null"] {
    assert_eq(
      wire034_at(
        classify_relation_v4_json(
          wire034_source(),
          "{\"categories\":" + categories + "}",
        ),
        ["status"],
      ),
      Json("invalid"),
    )
  }
}

///|
test "wire034 06 escaped duplicate relation options rejected" {
  assert_eq(
    wire034_at(
      classify_relation_v4_json(
        wire034_source(),
        "{\"maxStates\":1,\"max\\u0053tates\":0}",
      ),
      ["status"],
    ),
    Json("invalid"),
  )
}

///|
test "wire034 07 budget bounds and integer validation" {
  for
    opts in [
      "{\"maxGraphChecks\":1000001}", "{\"maxStates\":-1}", "{\"maxEdgeChecks\":0.5}",
      "{\"maxStates\":true}",
    ] {
    assert_eq(
      wire034_at(classify_relation_v4_json(wire034_source(), opts), ["status"]),
      Json("invalid"),
    )
  }
}

///|
test "wire034 08 raw source diagnostics and exact verification" {
  let source = wire034_source()
  let report = inspect_capture_anomalies_v4_json(source, "{}")
  assert_eq(
    wire034_at(report, ["format"]),
    Json("moontxnwitness-captured-source-anomalies/v4"),
  )
  assert_eq(
    wire034_at(verify_capture_anomalies_v4_json(source, report, "{}"), ["valid"]),
    Json(true),
  )
}

///|
test "wire034 09 source inspection caller budget zero is independently bound" {
  let source = wire034_source()
  let report = inspect_capture_anomalies_v4_json(source, "{\"maxChecks\":0}")
  assert_eq(wire034_at(report, ["status"]), Json("unknown"))
  assert_eq(
    wire034_at(verify_capture_anomalies_v4_json(source, report, "{}"), ["valid"]),
    Json(false),
  )
  assert_eq(
    wire034_at(
      verify_capture_anomalies_v4_json(source, report, "{\"maxChecks\":0}"),
      ["valid"],
    ),
    Json(true),
  )
}

///|
test "wire034 10 source diagnostic report duplicate key rejected" {
  let source = wire034_source()
  let report = inspect_capture_anomalies_v4_json(source, "{}")
  let duplicate = "{\"format\":\"forged\"," + report[1:].to_owned()
  assert_eq(
    wire034_at(verify_capture_anomalies_v4_json(source, duplicate, "{}"), [
      "valid",
    ]),
    Json(false),
  )
}

///|
test "wire034 11 source diagnostic unknown option and duplicate rejected" {
  for
    opts in [
      "{\"model\":\"read-committed\"}", "{\"maxChecks\":1,\"max\\u0043hecks\":0}",
      "{\"maxChecks\":1000001}",
    ] {
    assert_eq(
      wire034_at(inspect_capture_anomalies_v4_json(wire034_source(), opts), [
        "status",
      ]),
      Json("invalid"),
    )
  }
}

///|
test "wire034 12 formal INT exact verification" {
  let source = wire034_source()
  let report = inspect_internal_consistency_v4_json(source, "{}")
  assert_eq(
    wire034_at(report, ["format"]),
    Json("moontxnwitness-internal-consistency/v4"),
  )
  assert_eq(
    wire034_at(verify_internal_consistency_v4_json(source, report, "{}"), [
      "valid",
    ]),
    Json(true),
  )
}

///|
test "wire034 13 formal INT custom budget cannot self authorize" {
  let source = wire034_source()
  let report = inspect_internal_consistency_v4_json(source, "{\"maxChecks\":0}")
  assert_eq(
    wire034_at(verify_internal_consistency_v4_json(source, report, "{}"), [
      "valid",
    ]),
    Json(false),
  )
  assert_eq(
    wire034_at(
      verify_internal_consistency_v4_json(source, report, "{\"maxChecks\":0}"),
      ["valid"],
    ),
    Json(true),
  )
}

///|
test "wire034 14 INT report tampering rejected" {
  let source = wire034_source()
  let value = @json.parse(inspect_internal_consistency_v4_json(source, "{}"))
  object_fields_unchecked_v3(value)["status"] = Json("refuted")
  assert_eq(
    wire034_at(
      verify_internal_consistency_v4_json(source, value.stringify(), "{}"),
      ["valid"],
    ),
    Json(false),
  )
}

///|
test "wire034 15 malformed source and unknown model rejected" {
  for
    text in [
      "{", "{\"traceSchema\":3,\"dataModel\":\"unknown-model\",\"events\":[]}",
    ] {
    assert_eq(
      wire034_at(inspect_internal_consistency_v4_json(text, "{}"), ["status"]),
      Json("invalid"),
    )
    assert_eq(
      wire034_at(classify_relation_v4_json(text, "{}"), ["status"]),
      Json("invalid"),
    )
  }
}

///|
test "wire034 16 nested report duplicate guard" {
  assert_eq(
    wire034_at(
      source_rules_report_v4_content_json(
        "{\"execution\":{\"checks\":1,\"ch\\u0065cks\":2}}",
      ),
      ["status"],
    ),
    Json("invalid"),
  )
  assert_eq(
    wire034_at(source_rules_report_v4_content_json("{}"), ["valid"]),
    Json(true),
  )
}

///|
fn wire034_capsule() -> Json {
  {
    "format": "moontxnwitness-source-rules-replay/v4",
    "schemaVersion": 4,
    "tool": "MoonTxnWitness",
    "producer": { "version": "metadata-only" },
    "operation": "internal-consistency",
    "semanticContract": "s",
    "algorithm": "a",
    "counterContract": "c",
    "profile": "p",
    "sourceText": "{}",
    "sourceSha256": "x",
    "optionsText": "{}",
    "optionsSha256": "x",
    "reportText": "{}",
    "reportSha256": "x",
  }
}

///|
test "wire034 17 independent envelope permits producer metadata without semantics routing" {
  let text = wire034_capsule().stringify()
  assert_eq(
    wire034_at(source_rules_capsule_v4_content_json(text), [
      "producer", "version",
    ]),
    Json("metadata-only"),
  )
}

///|
test "wire034 18 unknown capsule fields rejected" {
  let value = wire034_capsule()
  object_fields_unchecked_v3(value)["acceptsModels"] = Json(true)
  assert_eq(
    wire034_at(source_rules_capsule_v4_content_json(value.stringify()), [
      "status",
    ]),
    Json("invalid"),
  )
}

///|
test "wire034 19 duplicate capsule keys and old format rejected" {
  let capsule = wire034_capsule()
  assert_eq(
    wire034_at(
      source_rules_capsule_v4_content_json(
        "{\"schemaVersion\":4," + capsule.stringify()[1:].to_owned(),
      ),
      ["status"],
    ),
    Json("invalid"),
  )
  object_fields_unchecked_v3(capsule)["format"] = Json(
    "moontxnwitness-replay/v4",
  )
  assert_eq(
    wire034_at(source_rules_capsule_v4_content_json(capsule.stringify()), [
      "status",
    ]),
    Json("invalid"),
  )
}

///|
test "wire034 20 guards reject nonobject producer and malformed options" {
  let capsule = wire034_capsule()
  object_fields_unchecked_v3(capsule)["producer"] = Json("0.3.4")
  assert_eq(
    wire034_at(source_rules_capsule_v4_content_json(capsule.stringify()), [
      "status",
    ]),
    Json("invalid"),
  )
  assert_eq(
    wire034_at(inspect_internal_consistency_v4_json(wire034_source(), "[]"), [
      "status",
    ]),
    Json("invalid"),
  )
}
