///|
test "point reduction requires a caller-selected supported category" {
  for
    options in [
      "{}", "{\"category\":\"G0\"}", "{\"category\":\"serializable\"}",
    ] {
    let text = reduce_configured_point_window_v4_json("{}", "{}", "{}", options)
    let record = object_fields_unchecked_v3(@json.parse(text))
    assert_eq(record.at("status"), Json("invalid"))
    assert_eq(record.at("oneMinimal"), Json(false))
    assert_true(
      verify_configured_point_reduction_v4_json("{}", "{}", "{}", text, options),
    )
  }
}

///|
test "point reduction rejects untrusted option fields and malformed limits" {
  for
    options in [
      "{\"category\":\"G2-item\",\"trusted\":true}", "{\"category\":\"G2-item\",\"maxChecks\":257}",
      "{\"category\":\"G2-item\",\"maxChecks\":-1}", "{\"category\":\"G2-item\",\"windowOptions\":[]}",
      "{\"category\":\"G2-item\",\"category\":\"G0\"}",
    ] {
    let record = object_fields_unchecked_v3(
      @json.parse(
        reduce_configured_point_window_v4_json("{}", "{}", "{}", options),
      ),
    )
    assert_eq(record.at("status"), Json("invalid"))
    assert_eq(record.at("oneMinimal"), Json(false))
  }
}

///|
test "point reduction verifier binds original inputs options and complete result" {
  let options = "{\"category\":\"G2-item\"}"
  let report = reduce_configured_point_window_v4_json("{}", "{}", "{}", options)
  let changed = object_fields_unchecked_v3(@json.parse(report))
  changed["sourceAuthenticated"] = Json(true)
  assert_false(
    verify_configured_point_reduction_v4_json(
      "{}",
      "{}",
      "{}",
      Json(changed).stringify(),
      options,
    ),
  )
  assert_false(
    verify_configured_point_reduction_v4_json(
      "{ }", "{}", "{}", report, options,
    ),
  )
  assert_false(
    verify_configured_point_reduction_v4_json(
      "{}", "{}", "{}", report, "{\"category\":\"G2-item\",\"maxChecks\":0}",
    ),
  )
  assert_false(
    verify_configured_point_reduction_v4_json(
      "{}",
      "{}",
      "{}",
      report + "{}",
      options,
    ),
  )
}
