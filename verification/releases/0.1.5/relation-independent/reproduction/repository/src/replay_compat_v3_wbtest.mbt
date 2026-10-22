///|
fn recorded_legacy_v3_report(trace : String, engine : String) -> Json raise {
  let report = v3_analysis(trace, "{}")
  let fields = object_fields_unchecked_v3(report)
  fields["version"] = engine.to_json()
  match fields.get("evidence") {
    Some(Object(evidence)) =>
      if evidence.get("tool") == Some("MoonTxnWitness".to_json()) &&
        evidence.get("schemaVersion") == Some((2).to_json()) {
        evidence["version"] = engine.to_json()
      }
    _ => ()
  }
  report
}

///|
test "v3 released engines preserve nested engine and exact semantic field checks" {
  let trace = v3_test_completed([
    { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
  ]).stringify()
  for engine in ["0.1.1", "0.1.2", "0.1.3", "0.1.4"] {
    let report = recorded_legacy_v3_report(trace, engine)
    assert_true(result_valid(verify_v3_json(trace, report.stringify())))
    let fields = object_fields_unchecked_v3(report)
    let evidence = object_fields_unchecked_v3(fields.at("evidence"))
    evidence["version"] = version().to_json()
    assert_true(!result_valid(verify_v3_json(trace, report.stringify())))
    evidence["version"] = engine.to_json()
    fields["status"] = "violation".to_json()
    assert_true(!result_valid(verify_v3_json(trace, report.stringify())))
    fields["status"] = "consistent".to_json()
    fields["version"] = "0.1.0".to_json()
    evidence["version"] = "0.1.0".to_json()
    assert_true(!result_valid(verify_v3_json(trace, report.stringify())))
  }
}

///|
test "v3 released capsule header must match recorded report engine" {
  let trace = v3_test_completed([]).stringify()
  for engine in ["0.1.1", "0.1.2", "0.1.3", "0.1.4"] {
    let report = recorded_legacy_v3_report(trace, engine)
    let report_fields = object_fields_unchecked_v3(report)
    let capsule : Json = {
      "format": "moontxnwitness-replay/v3",
      "schemaVersion": 3,
      "tool": "MoonTxnWitness",
      "engineVersion": engine.to_json(),
      "traceText": trace.to_json(),
      "traceSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "normalizedText": report_fields.at("normalized").stringify().to_json(),
      "normalizedSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "reportText": report.stringify().to_json(),
      "reportSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "evidenceText": report_fields.at("evidence").stringify().to_json(),
      "evidenceSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    }
    assert_true(result_valid(capsule_v3_content_json(capsule.stringify())))
    let fields = object_fields_unchecked_v3(capsule)
    fields["engineVersion"] = version().to_json()
    assert_true(!result_valid(capsule_v3_content_json(capsule.stringify())))
    fields["engineVersion"] = "99.0.0".to_json()
    assert_true(!result_valid(capsule_v3_content_json(capsule.stringify())))
  }
}

///|
test "v3 released list replay preserves observed values and exact budgets" {
  let trace : Json = {
    "traceSchema": 3,
    "dataModel": "append-list-v1",
    "clockDomain": "legacy-list-replay",
    "scope": { "exclusiveWriters": true },
    "gaps": [],
    "events": [
      {
        "seq": 1,
        "time": 0,
        "kind": "snapshot",
        "initial": { "x": [{ "id": "seed", "value": "0.1.3" }] },
        "consistent": true,
      },
      { "seq": 2, "time": 1, "kind": "begin", "tx": "A", "connection": "C" },
      {
        "seq": 3,
        "time": 2,
        "kind": "append",
        "tx": "A",
        "key": "x",
        "id": "next",
        "value": "0.1.3",
      },
      {
        "seq": 4,
        "time": 3,
        "kind": "list_read",
        "tx": "A",
        "key": "x",
        "items": [
          { "id": "seed", "value": "0.1.3" },
          { "id": "next", "value": "0.1.3" },
        ],
      },
      { "seq": 5, "time": 4, "kind": "commit_request", "tx": "A" },
      { "seq": 6, "time": 5, "kind": "commit_ok", "tx": "A" },
    ],
  }
  let text = trace.stringify()
  for engine in ["0.1.1", "0.1.2", "0.1.3", "0.1.4"] {
    let report = recorded_legacy_v3_report(text, engine)
    assert_true(result_valid(verify_v3_json(text, report.stringify())))
    let fields = object_fields_unchecked_v3(report)
    let evidence = object_fields_unchecked_v3(fields.at("evidence"))
    assert_true(!evidence.contains("version"))
    let source = object_fields_unchecked_v3(
      presence_capture_array(evidence.at("sourceEvidence"), "sources")[0],
    )
    source["value"] = "0.1.4".to_json()
    assert_true(!result_valid(verify_v3_json(text, report.stringify())))
    let unchanged = recorded_legacy_v3_report(text, engine)
    let execution = object_fields_unchecked_v3(
      object_fields_unchecked_v3(unchanged).at("execution"),
    )
    let options = object_fields_unchecked_v3(execution.at("analysisOptions"))
    options["maxStates"] = (0).to_json()
    assert_true(!result_valid(verify_v3_json(text, unchanged.stringify())))
  }
}
