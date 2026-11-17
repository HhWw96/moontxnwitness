///|
fn window53_reduce(index : Int32, options : String) -> Json raise {
  let fixture = window_object_v2(window52_fixture(index))
  sql_json_v1(
    reduce_configured_window_v2_json(
      fixture.at("config").stringify(),
      fixture.at("policy").stringify(),
      sql_string_v1(fixture.at("bundleText")),
      options,
    ),
    67108864,
  )
}

///|
fn window53_verify(
  index : Int32,
  report : Json,
  options : String,
) -> Json raise {
  let fixture = window_object_v2(window52_fixture(index))
  sql_json_v1(
    verify_configured_window_reduction_v2_json(
      fixture.at("config").stringify(),
      fixture.at("policy").stringify(),
      sql_string_v1(fixture.at("bundleText")),
      report.stringify(),
      options,
    ),
    67108864,
  )
}

///|
test "configured window53 reduction preserves a genuine source-bound refutation" {
  let options = "{\"preserveModel\":\"serializable\"}"
  let report = window53_reduce(1, options)
  assert_eq(v4_test_at(report, ["windowVerified"]), Json(true))
  assert_eq(v4_test_at(report, ["refutationPreserved"]), Json(true))
  assert_eq(v4_test_at(report, ["oneMinimal"]), Json(true))
  let verification = window53_verify(1, report, options)
  assert_eq(v4_test_at(verification, ["valid"]), Json(true))
  assert_eq(v4_test_at(verification, ["refutationVerified"]), Json(true))
  assert_eq(v4_test_at(verification, ["oneMinimalVerified"]), Json(true))
}

///|
test "configured window53 compatible original is not a refutation" {
  let report = window53_reduce(0, "{\"preserveModel\":\"serializable\"}")
  assert_eq(v4_test_at(report, ["status"]), Json("not-refuted"))
  assert_eq(v4_test_at(report, ["refutationPreserved"]), Json(false))
  assert_eq(v4_test_at(report, ["oneMinimal"]), Json(false))
}

///|
test "configured window53 unknown original cannot enter reduction" {
  let options = "{\"preserveModel\":\"serializable\"}"
  let report = window53_reduce(2, options)
  assert_eq(v4_test_at(report, ["windowVerified"]), Json(false))
  assert_eq(v4_test_at(report, ["refutationPreserved"]), Json(false))
  assert_eq(v4_test_at(report, ["oneMinimal"]), Json(false))
  assert_eq(
    v4_test_at(window53_verify(2, report, options), ["valid"]),
    Json(false),
  )
}

///|
test "configured window53 unfinished candidates cannot claim one-minimal" {
  let options = "{\"preserveModel\":\"serializable\",\"reductionOptions\":{\"maxChecks\":0}}"
  let report = window53_reduce(1, options)
  assert_eq(v4_test_at(report, ["windowVerified"]), Json(true))
  assert_eq(v4_test_at(report, ["oneMinimal"]), Json(false))
  let changed = window_object_v2(report)
  changed["oneMinimal"] = Json(true)
  assert_eq(
    v4_test_at(window53_verify(1, report, options), ["valid"]),
    Json(false),
  )
}
