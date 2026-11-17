///|
fn window52_run(index : Int32, options : String) -> Json raise {
  let fixture = window_object_v2(window52_fixture(index))
  sql_json_v1(
    analyze_configured_window_v2_json(
      fixture.at("config").stringify(),
      fixture.at("policy").stringify(),
      sql_string_v1(fixture.at("bundleText")),
      options,
    ),
    33554432,
  )
}

///|
fn window52_verify(
  index : Int32,
  report : Json,
  options : String,
) -> Json raise {
  let fixture = window_object_v2(window52_fixture(index))
  sql_json_v1(
    verify_configured_window_v2_json(
      fixture.at("config").stringify(),
      fixture.at("policy").stringify(),
      sql_string_v1(fixture.at("bundleText")),
      report.stringify(),
      options,
    ),
    33554432,
  )
}

///|
test "configured window52 actual full CRUD has an independent serial certificate" {
  let report = window52_run(0, "{}")
  assert_eq(v4_test_at(report, ["coverageComplete"]), Json(true))
  assert_eq(v4_test_at(report, ["status"]), Json("checked-compatible"))
  assert_eq(v4_test_at(report, ["model", "status"]), Json("unknown"))
  assert_eq(
    v4_test_at(report, ["modelDecision", "basis"]),
    Json("complete-serial-relation-replay"),
  )
  assert_eq(
    v4_test_at(report, ["serialReplay", "judgment", "evidence", "kind"]),
    Json("serial-relation-replay"),
  )
  assert_eq(v4_test_at(window52_verify(0, report, "{}"), ["valid"]), Json(true))
}

///|
test "configured window52 actual RR write skew remains refuted" {
  let report = window52_run(1, "{}")
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
  assert_eq(v4_test_at(report, ["coverageComplete"]), Json(true))
  assert_eq(v4_test_at(report, ["model", "status"]), Json("refuted"))
  assert_eq(v4_test_at(window52_verify(1, report, "{}"), ["valid"]), Json(true))
}

///|
test "configured window52 does not omit actual zero-row conditional writes" {
  let report = window52_run(2, "{}")
  assert_eq(v4_test_at(report, ["status"]), Json("unknown"))
  assert_eq(v4_test_at(report, ["coverageComplete"]), Json(false))
  assert_true(
    sql_string_v1(v4_test_at(report, ["reason"])).contains(
      "window-zero-row-write",
    ),
  )
}

///|
test "configured window52 exhausted point budget remains unknown" {
  let report = window52_run(0, "{\"maxPointChecks\":0}")
  assert_eq(v4_test_at(report, ["status"]), Json("unknown"))
  assert_eq(v4_test_at(report, ["coverageComplete"]), Json(false))
}

///|
test "configured window52 caller budgets cannot be supplied by a serial report" {
  let report = window52_run(0, "{}")
  let exhausted = window52_run(0, "{\"maxSerialOperationChecks\":0}")
  assert_eq(v4_test_at(exhausted, ["status"]), Json("unknown"))
  assert_eq(
    v4_test_at(window52_verify(0, report, "{\"maxSerialOperationChecks\":0}"), [
      "valid",
    ]),
    Json(false),
  )
}
