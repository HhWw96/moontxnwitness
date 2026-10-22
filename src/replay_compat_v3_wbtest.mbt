///|
fn recorded_v011_report(trace : String) -> Json raise {
  let report = v3_analysis(trace, "{}")
  let fields = object_fields_unchecked_v3(report)
  fields["version"] = "0.1.1".to_json()
  match fields.get("evidence") {
    Some(Object(evidence)) => evidence["version"] = "0.1.1".to_json()
    _ => ()
  }
  report
}

///|
test "v3 v011 replay preserves nested engine and exact semantic field checks" {
  let trace = v3_test_completed([
    { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
  ]).stringify()
  let report = recorded_v011_report(trace)
  assert_true(result_valid(verify_v3_json(trace, report.stringify())))
  let fields = object_fields_unchecked_v3(report)
  let evidence = object_fields_unchecked_v3(fields.at("evidence"))
  evidence["version"] = version().to_json()
  assert_true(!result_valid(verify_v3_json(trace, report.stringify())))
  evidence["version"] = "0.1.1".to_json()
  fields["status"] = "violation".to_json()
  assert_true(!result_valid(verify_v3_json(trace, report.stringify())))
}

///|
test "v3 legacy capsule header must match recorded report engine" {
  let trace = v3_test_completed([]).stringify()
  let report = recorded_v011_report(trace)
  let report_fields = object_fields_unchecked_v3(report)
  let capsule : Json = {
    "format": "moontxnwitness-replay/v3",
    "schemaVersion": 3,
    "tool": "MoonTxnWitness",
    "engineVersion": "0.1.1",
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
