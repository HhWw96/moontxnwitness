///|
test "window54 optimized verification keeps the original self-report depth gate" {
  let mut nested : Json = Json::null()
  for _ in 0..<62 {
    nested = Json([nested])
  }
  let options : Json = {
    "preserveModel": "serializable",
    "windowOptions": { "unknownDepth": nested },
  }
  let _ = sql_json_v1(options.stringify(), 524288)
  let fixture = window_object_v2(window52_fixture(1))
  let config = fixture.at("config").stringify()
  let policy = fixture.at("policy").stringify()
  let bundle = sql_string_v1(fixture.at("bundleText"))
  let text = reduce_configured_window_structured_v2_json(
    config,
    policy,
    bundle,
    options.stringify(),
  )
  let old_reason = try {
    let _ = sql_json_v1(text, 67108864)
    ""
  } catch {
    error => report_error_text(error)
  }
  assert_true(!old_reason.is_empty())
  let checked = sql_json_v1(
    verify_configured_window_reduction_structured_v2_json(
      config,
      policy,
      bundle,
      "{}",
      options.stringify(),
    ),
    1048576,
  )
  assert_eq(v4_test_at(checked, ["valid"]), Json(false))
  assert_eq(v4_test_at(checked, ["reason"]), Json(old_reason))
}

///|
test "window54 canonical byte guard retains compact UTF-8 limits" {
  let document : Json = {
    "zz": Json("quotes\" and slash\\ and 🙂\n".repeat(12)),
    "aa": [{ "punctuation": "{[]}", "value": true }, Json::null()],
  }
  let compact = document.stringify()
  let canonical = sql_canonical_v1(document)
  let maximum = orm_utf8_size(compact)
  assert_eq(orm_utf8_size(canonical), maximum)
  for mode in [false, true] {
    let (record, encoded) = window_bounded_record_v2(
      document, mode, maximum, "budget:window-test", configured_window_analysis_failure_v2,
    )
    assert_eq(record, document)
    assert_eq(orm_utf8_size(encoded), maximum)
    let (limited, _) = window_bounded_record_v2(
      document,
      mode,
      maximum - 1,
      "budget:window-test",
      configured_window_analysis_failure_v2,
    )
    assert_eq(v4_test_at(limited, ["status"]), Json("unknown"))
    assert_eq(v4_test_at(limited, ["coverageComplete"]), Json(false))
  }
}

///|
test "window54 text and structured paths keep the 64-container limit" {
  for leaf in [Json::null(), ({} : Json), Json(([] : Array[Json]))] {
    for layers in [0, 1, 62, 63, 64, 65] {
      let mut value = leaf
      for index in 0..<layers {
        value = if index % 2 == 0 { Json([value]) } else { { "next": value } }
      }
      let original_accepts = try {
        let _ = sql_json_v1(value.stringify(), 1048576)
        true
      } catch {
        _ => false
      }
      let optimized_accepts = try {
        window_report_depth_v2(value, 64)
        true
      } catch {
        _ => false
      }
      assert_eq(
        original_accepts,
        layers + (if leaf == Json::null() { 0 } else { 1 }) <= 64,
      )
      assert_eq(optimized_accepts, original_accepts)
    }
  }
}

///|
test "configured JSON depth skips brackets in escaped strings" {
  let mut text = "A quote \" then a backslash \\ and more brackets "
  for _ in 0..<70 {
    text = text + "[{"
  }
  let input : Json = { "text": Json(text) }
  assert_eq(sql_json_v1(input.stringify(), 1024), input)
}
