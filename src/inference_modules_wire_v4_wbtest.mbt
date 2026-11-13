///|
fn imwire_options() -> String {
  (
    #|{"modules":["original-read-sources/v1","original-version-constraints/v1"],"modelOptions":{"models":["serializable"]},"maxInferenceChecks":1000000}
  )
}

///|
test "inference wire 01 compiled modules classify and independently reverify" {
  let source = mraw_history(mraw_simple()).source_text
  let report = classify_with_inference_v4_json(source, imwire_options())
  assert_eq(
    v4_test_at(@json.parse(report), ["status"]),
    Json("checked-compatible"),
  )
  assert_eq(
    v4_test_at(
      @json.parse(
        verify_with_inference_v4_json(source, report, imwire_options()),
      ),
      ["valid"],
    ),
    Json(true),
  )
}

///|
test "inference wire 02 inference-only evidence replays from original inputs" {
  let source = mraw_history(mraw_simple()).source_text
  let report = infer_dependencies_v4_json(source, imwire_options())
  assert_eq(v4_test_at(@json.parse(report), ["status"]), Json("executed"))
  assert_eq(
    v4_test_at(
      @json.parse(verify_inference_v4_json(source, report, imwire_options())),
      ["valid"],
    ),
    Json(true),
  )
}

///|
test "inference wire 03 duplicate decoded option keys are refused before normalization" {
  for
    options in [
      (
        #|{"modules":[],"mo\u0064ules":[]}
      ),
      (
        #|{"modules":[],"modelOptions":{"models":["serializable"],"mo\u0064els":["snapshot-isolation"]}}
      ),
      (
        #|{"modules":[],"maxInferenceChecks":0,"maxInferenceChecks":1000000}
      ),
    ] {
    assert_eq(
      v4_test_at(@json.parse(inference_options_v4_content_json(options)), [
        "status",
      ]),
      Json("invalid"),
    )
  }
}

///|
test "inference wire 04 unknown compiled modules cannot supply code or precomputed verdicts" {
  for
    options in [
      (
        #|{"modules":["module-from-report"]}
      ),
      (
        #|{"modules":[{"id":"original-read-sources/v1","code":"checked-compatible"}]}
      ),
      (
        #|{"modules":[],"complete":true}
      ),
      (
        #|{"modules":["original-read-sources/v1","original-read-sources/v1"]}
      ),
      (
        #|{"modelOptions":{}}
      ),
    ] {
    assert_eq(
      v4_test_at(@json.parse(inference_options_v4_content_json(options)), [
        "status",
      ]),
      Json("invalid"),
    )
  }
}

///|
test "inference wire 05 zero budget remains unknown and cannot borrow report limits" {
  let source = mraw_history(mraw_simple()).source_text
  let options =
    #|{"modules":["original-read-sources/v1"],"maxInferenceChecks":0,"modelOptions":{"models":["serializable"]}}
  let report = classify_with_inference_v4_json(source, options)
  assert_eq(v4_test_at(@json.parse(report), ["status"]), Json("unknown"))
  assert_eq(
    v4_test_at(
      @json.parse(
        verify_with_inference_v4_json(source, report, imwire_options()),
      ),
      ["valid"],
    ),
    Json(false),
  )
}

///|
test "inference wire 06 duplicate report keys fail verification even when semantic fields match" {
  let source = mraw_history(mraw_simple()).source_text
  let report = classify_with_inference_v4_json(source, imwire_options())
  let altered = "{\"status\":\"checked-compatible\"," + report[1:].to_owned()
  assert_eq(
    v4_test_at(
      @json.parse(
        verify_with_inference_v4_json(source, altered, imwire_options()),
      ),
      ["valid"],
    ),
    Json(false),
  )
}

///|
test "inference wire 07 strict budgets and nested source options remain independent" {
  for
    options in [
      (
        #|{"modules":[],"maxInferenceChecks":-1}
      ),
      (
        #|{"modules":[],"maxInferenceChecks":1000001}
      ),
      (
        #|{"modules":[],"maxInferenceChecks":1.5}
      ),
      (
        #|{"modules":[],"modelOptions":{"maxStates":100001}}
      ),
      (
        #|{"modules":[],"modelOptions":{"mode":"automatic"}}
      ),
    ] {
    assert_eq(
      v4_test_at(@json.parse(inference_options_v4_content_json(options)), [
        "status",
      ]),
      Json("invalid"),
    )
  }
}

///|
test "inference wire 08 normalizer expands only the caller-selected module identities" {
  let result = @json.parse(inference_options_v4_content_json(imwire_options()))
  assert_eq(v4_test_at(result, ["valid"]), Json(true))
  assert_eq(
    v4_test_at(result, ["options", "modules"]),
    Json(["original-read-sources/v1", "original-version-constraints/v1"]),
  )
  assert_eq(
    v4_test_at(result, ["options", "maxInferenceChecks"]),
    Json(1000000),
  )
}
