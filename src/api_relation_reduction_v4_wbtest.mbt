///|
test "relation reduction wire 01 category is explicit and final classification is bound" {
  let h = rrt_history(rrt_g2_body(noise=1))
  let text = reduce_relation_category_v4_json(
    h.source_text,
    "{\"category\":\"G2-item\"}",
  )
  let report = guarded_json(text, limit=33554432) catch { _ => Json::null() }
  assert_eq(rrt_at(report, ["oneMinimal"]), Json(true))
  assert_eq(
    rrt_at(report, ["classification", "algorithm"]),
    Json("v4-relation-point-category-5"),
  )
}

///|
test "relation reduction wire 02 missing invalid and excessive options reject" {
  let source = rrt_history(rrt_g2_body()).source_text
  for
    options in [
      "{}", "{\"category\":\"G2\"}", "{\"category\":\"G0\",\"maxChecks\":257}", "{\"category\":\"INT\",\"extra\":1}",
    ] {
    let value = guarded_json(
      reduce_relation_category_v4_json(source, options),
      limit=33554432,
    ) catch {
      _ => Json::null()
    }
    assert_eq(rrt_at(value, ["status"]), Json("invalid"))
  }
}

///|
test "relation reduction wire 03 escaped duplicate options reject before normalization" {
  let source = rrt_history(rrt_g2_body()).source_text
  let value = guarded_json(
    reduce_relation_category_v4_json(
      source, "{\"category\":\"G0\",\"maxChecks\":1,\"max\\u0043hecks\":0}",
    ),
    limit=33554432,
  ) catch {
    _ => Json::null()
  }
  assert_eq(rrt_at(value, ["status"]), Json("invalid"))
}

///|
test "relation reduction wire 04 verification uses caller budget instead of report limits" {
  let source = rrt_history(rrt_g2_body()).source_text
  let report = reduce_relation_category_v4_json(
    source, "{\"category\":\"G2-item\",\"maxChecks\":0}",
  )
  assert_eq(
    verify_relation_category_reduction_v4_json(
      source, report, "{\"category\":\"G2-item\",\"maxChecks\":0}",
    ),
    wire_v4_verified(true),
  )
  assert_eq(
    verify_relation_category_reduction_v4_json(
      source, report, "{\"category\":\"G2-item\"}",
    ),
    wire_v4_verified(false),
  )
}

///|
test "relation reduction wire 05 report duplicate keys cannot hide a false minimum" {
  let source = rrt_history(rrt_g2_body()).source_text
  let report = reduce_relation_category_v4_json(
    source, "{\"category\":\"G2-item\"}",
  )
  let duplicated = "{\"oneMinimal\":false," + report[1:].to_owned()
  assert_eq(
    verify_relation_category_reduction_v4_json(
      source, duplicated, "{\"category\":\"G2-item\"}",
    ),
    wire_v4_verified(false),
  )
}

///|
test "relation reduction wire 06 incomplete and non-relation results remain visible" {
  let source = rrt_history(rrt_g2_body()).source_text
  let value = guarded_json(
    reduce_relation_category_v4_json(
      source, "{\"category\":\"G2-item\",\"maxChecks\":0}",
    ),
    limit=33554432,
  ) catch {
    _ => Json::null()
  }
  assert_eq(rrt_at(value, ["status"]), Json("budget"))
  let other = register_history_v4(skew()).unwrap().source_text
  let unsupported = guarded_json(
    reduce_relation_category_v4_json(other, "{\"category\":\"G2-item\"}"),
    limit=33554432,
  ) catch {
    _ => Json::null()
  }
  assert_eq(rrt_at(unsupported, ["status"]), Json("unsupported"))
}

///|
test "relation reduction wire 07 report and capsule guards reject ambiguous JSON" {
  let duplicate = relation_reduction_report_v4_content_json(
    "{\"status\":\"one\",\"st\\u0061tus\":\"two\"}",
  )
  let value = guarded_json(duplicate, limit=33554432) catch {
    _ => Json::null()
  }
  assert_eq(rrt_at(value, ["status"]), Json("invalid"))
  let capsule = relation_reduction_capsule_v4_content_json(
    "{\"format\":\"moontxnwitness-relation-category-replay/v4\",\"schemaVersion\":4,\"schemaVersion\":4}",
  )
  let invalid = guarded_json(capsule, limit=33554432) catch {
    _ => Json::null()
  }
  assert_eq(rrt_at(invalid, ["status"]), Json("invalid"))
}
