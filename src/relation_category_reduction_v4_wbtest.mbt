///|
fn rrt_history(body : Array[Json]) -> HistoryV4 {
  rcl_history(body)
}

///|
fn rrt_g2_body(noise~ : Int32 = 0) -> Array[Json] {
  let body : Array[Json] = []
  for i in 0..<noise {
    let id = "noise-" + i.to_string()
    body.push(rpg_begin(id))
    body.push(rpg_read(id, "3", Some("z0")))
    rpg_commit(body, id)
  }
  body.push(rpg_begin("A"))
  body.push(rpg_begin("B"))
  body.push(rpg_read("A", "1", Some("v0")))
  body.push(rpg_read("B", "2", Some("u0")))
  body.push(rpg_write("A", "2", "u1", Some("u0")))
  body.push(rpg_write("B", "1", "v1", Some("v0")))
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  body
}

///|
fn rrt_report(
  body : Array[Json],
  category : String,
  max_checks~ : Int32 = 256,
  max_states~ : Int32 = 100000,
  max_edge_checks~ : Int32 = 1000000,
  max_graph_checks~ : Int32 = 1000000,
) -> Json {
  relation_category_reduction_v4_json(
    reduce_relation_category_v4(
      rrt_history(body),
      category~,
      max_checks~,
      max_states~,
      max_edge_checks~,
      max_graph_checks~,
    ),
  )
}

///|
fn rrt_at(report : Json, path : Array[String]) -> Json {
  relation_classification_at_v4(report, path)
}

///|
fn rrt_count(report : Json) -> Int32 {
  rcl_number(rrt_at(report, ["execution", "candidateChecks"]))
}

///|
test "relation category reduction 01 G2 and unrelated transactions reduces to two" {
  let result = reduce_relation_category_v4(
    rrt_history(rrt_g2_body(noise=4)),
    category="G2-item",
  )
  let report = relation_category_reduction_v4_json(result)
  assert_eq(v4_capture_transaction_ids(result.history()), ["A", "B"])
  assert_eq(rrt_at(report, ["status"]), Json("reduced"))
  assert_eq(rrt_at(report, ["oneMinimal"]), Json(true))
  assert_eq(
    rrt_at(report, ["classification", "judgment", "rules", "G2-item", "status"]),
    Json("refuted"),
  )
  assert_eq(rrt_count(report), 6)
}

///|
test "relation category reduction 02 zero candidate budget preserves original refutation and no minimum" {
  let h = rrt_history(rrt_g2_body(noise=1))
  let result = reduce_relation_category_v4(h, category="G2-item", max_checks=0)
  let report = relation_category_reduction_v4_json(result)
  assert_eq(history_v4_json(result.history()), history_v4_json(h))
  assert_eq(rrt_at(report, ["oneMinimal"]), Json(false))
  assert_eq(rrt_count(report), 0)
  assert_eq(rrt_at(report, ["status"]), Json("budget"))
  assert_eq(rrt_at(report, ["execution", "finalRevalidation"]), Json(true))
}

///|
test "relation category reduction 03 exact budget completes every remaining deletion" {
  let report = rrt_report(rrt_g2_body(noise=2), "G2-item", max_checks=4)
  assert_eq(rrt_count(report), 4)
  assert_eq(rrt_at(report, ["oneMinimal"]), Json(true))
  assert_eq(rrt_at(report, ["execution", "candidateLimitReached"]), Json(true))
  assert_eq(
    rrt_at(report, ["execution", "candidateBudgetExhausted"]),
    Json(false),
  )
}

///|
test "relation category reduction 04 one fewer check cannot assert minimum" {
  let report = rrt_report(rrt_g2_body(noise=2), "G2-item", max_checks=3)
  assert_eq(rrt_count(report), 3)
  assert_eq(rrt_at(report, ["oneMinimal"]), Json(false))
  assert_eq(rrt_at(report, ["status"]), Json("budget"))
}

///|
test "relation category reduction 05 source deletion unknown prevents G1a minimum" {
  let report = rrt_report(rcl_direct_body("G1a"), "G1a")
  assert_eq(rrt_at(report, ["oneMinimal"]), Json(false))
  assert_eq(rrt_at(report, ["status"]), Json("undetermined"))
  assert_true(
    !capture_source_array_v4(rrt_at(report, ["unresolvedCandidates"])).is_empty(),
  )
  assert_eq(
    rrt_at(report, ["classification", "judgment", "rules", "G1a", "status"]),
    Json("refuted"),
  )
}

///|
test "relation category reduction 06 G1b preserves actual intermediate producer" {
  let report = rrt_report(rcl_direct_body("G1b"), "G1b")
  assert_eq(rrt_at(report, ["oneMinimal"]), Json(false))
  assert_eq(
    rrt_at(report, ["classification", "judgment", "rules", "G1b", "status"]),
    Json("refuted"),
  )
  assert_eq(
    capture_source_array_v4(rrt_at(report, ["removedTransactions"])).length(),
    0,
  )
}

///|
test "relation category reduction 07 own-read INT is single minimal at one check" {
  let report = rrt_report(rcl_direct_body("INT"), "INT", max_checks=1)
  assert_eq(rrt_count(report), 1)
  assert_eq(rrt_at(report, ["oneMinimal"]), Json(true))
  assert_eq(rrt_at(report, ["status"]), Json("unchanged"))
}

///|
test "relation category reduction 08 WR cycle remains chosen G1c" {
  let body = [
    rpg_begin("A"),
    rpg_begin("B"),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_write("B", "2", "u1", Some("u0")),
    rpg_read("A", "2", Some("u1")),
    rpg_read("B", "1", Some("v1")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  let report = rrt_report(body, "G1c")
  assert_eq(
    rrt_at(report, [
      "classification", "judgment", "rules", "G1c", "evidence", "specificCategory",
    ]),
    Json("G1c"),
  )
  assert_eq(rrt_at(report, ["oneMinimal"]), Json(false))
}

///|
test "relation category reduction 09 G0 chains do not become a false minimum after dropping sources" {
  let report = rrt_report(rcl_g0_body(), "G0")
  assert_eq(
    rrt_at(report, ["classification", "judgment", "rules", "G0", "status"]),
    Json("refuted"),
  )
  assert_eq(rrt_at(report, ["oneMinimal"]), Json(false))
}

///|
test "relation category reduction 10 G2 is not replaced by a shorter G0 cycle" {
  let trace = rpg_trace(rrt_g2_body())
  let events = capture_source_array_v4(
    object_fields_unchecked_v3(trace).at("events"),
  )
  let initial = object_fields_unchecked_v3(
    object_fields_unchecked_v3(events[0]).at("initial"),
  )
  let rows = capture_source_array_v4(initial.at("items"))
  rows.push(rpg_row("4", "q0"))
  rows.push(rpg_row("5", "r0"))
  let extra = [
    rpg_begin("C"),
    rpg_begin("D"),
    rpg_write("C", "4", "q1", Some("q0")),
    rpg_write("D", "4", "q2", Some("q1")),
    rpg_write("D", "5", "r1", Some("r0")),
    rpg_write("C", "5", "r2", Some("r1")),
  ]
  rpg_commit(extra, "C")
  rpg_commit(extra, "D")
  events.append(extra)
  for i, e in events {
    let fields = object_fields_unchecked_v3(e)
    fields["seq"] = Json(i + 1)
    fields["time"] = Json(i)
  }
  let h = parse_history_v4(trace.stringify()).unwrap()
  let report = relation_category_reduction_v4_json(
    reduce_relation_category_v4(h, category="G2-item", max_checks=0),
  )
  assert_eq(rrt_at(report, ["preserveCategory"]), Json("G2-item"))
  assert_eq(
    rrt_at(report, [
      "classification", "judgment", "rules", "G2-item", "evidence", "specificCategory",
    ]),
    Json("G2-item"),
  )
}

///|
fn rrt_combined() -> Array[Json] {
  let body = rcl_direct_body("G1a")
  body.append(rcl_direct_body("INT"))
  body
}

///|
test "relation category reduction 11 another direct anomaly cannot replace requested G1a" {
  let result = reduce_relation_category_v4(
    rrt_history(rrt_combined()),
    category="G1a",
  )
  assert_eq(v4_capture_transaction_ids(result.history()), ["P", "R"])
  assert_eq(
    rrt_at(relation_category_reduction_v4_json(result), [
      "classification", "judgment", "rules", "G1a", "status",
    ]),
    Json("refuted"),
  )
}

///|
test "relation category reduction 12 selecting INT can remove independent G1a reader then producer" {
  let result = reduce_relation_category_v4(
    rrt_history(rrt_combined()),
    category="INT",
  )
  assert_eq(v4_capture_transaction_ids(result.history()), ["A"])
  assert_eq(
    rrt_at(relation_category_reduction_v4_json(result), ["oneMinimal"]),
    Json(true),
  )
}

///|
test "relation category reduction 13 origin sequence preserves every retained event and original facts" {
  let trace = rpg_trace(rrt_g2_body(noise=2))
  let originals = capture_source_array_v4(
    object_fields_unchecked_v3(trace).at("events"),
  )
  let h = parse_history_v4(trace.stringify()).unwrap()
  let result = reduce_relation_category_v4(h, category="G2-item")
  let report = relation_category_reduction_v4_json(result)
  let origins = capture_source_array_v4(
    rrt_at(report, ["originalEventSequence"]),
  )
  let retained = capture_source_array_v4(
    object_fields_unchecked_v3(history_v4_json(result.history())).at("events"),
  )
  assert_eq(origins.length(), retained.length())
  for i, e in retained {
    let original = originals.filter(raw => {
        object_fields_unchecked_v3(raw).at("seq") == origins[i]
      })[0]
    let restored = v4_json_copy(e)
    object_fields_unchecked_v3(restored)["seq"] = origins[i]
    assert_eq(restored, original)
  }
}

///|
test "relation category reduction 14 original and exported JSON snapshots never alias" {
  let h = rrt_history(rrt_g2_body(noise=1))
  let before = history_v4_json(h)
  let result = reduce_relation_category_v4(h, category="G2-item")
  let report = relation_category_reduction_v4_json(result)
  v4_test_replace(report, ["history", "gaps"], Json(["changed"]))
  assert_eq(history_v4_json(h), before)
  assert_eq(
    rrt_at(relation_category_reduction_v4_json(result), ["history", "gaps"]),
    Json(([] : Array[Json])),
  )
}

///|
test "relation category reduction 15 no refutation is not reduction success" {
  let body = [rpg_begin("A"), rpg_read("A", "1", Some("v0"))]
  rpg_commit(body, "A")
  let report = rrt_report(body, "G2-item")
  assert_eq(rrt_at(report, ["status"]), Json("not-refuted"))
  assert_eq(rrt_count(report), 0)
  assert_eq(rrt_at(report, ["oneMinimal"]), Json(false))
}

///|
test "relation category reduction 16 invalid category is visible" {
  let report = rrt_report(rrt_g2_body(), "G2")
  assert_eq(rrt_at(report, ["status"]), Json("invalid"))
  assert_eq(rrt_at(report, ["oneMinimal"]), Json(false))
}

///|
test "relation category reduction 17 invalid budgets never run candidate loops" {
  for maximum in [-1, 257] {
    let report = rrt_report(rrt_g2_body(), "G2-item", max_checks=maximum)
    assert_eq(rrt_at(report, ["status"]), Json("invalid"))
    assert_eq(rrt_count(report), 0)
  }
}

///|
test "relation category reduction 18 graph budget exhaustion cannot be no anomaly" {
  let report = rrt_report(
    rrt_g2_body(),
    "G2-item",
    max_states=0,
    max_edge_checks=0,
  )
  assert_eq(rrt_at(report, ["status"]), Json("undetermined"))
  assert_eq(rrt_at(report, ["oneMinimal"]), Json(false))
  assert_eq(rrt_count(report), 0)
}

///|
test "relation category reduction 19 direct G1a remains reliable with zero cycle budget" {
  let report = rrt_report(
    rcl_direct_body("G1a"),
    "G1a",
    max_states=0,
    max_edge_checks=0,
  )
  assert_eq(
    rrt_at(report, ["classification", "judgment", "rules", "G1a", "status"]),
    Json("refuted"),
  )
  assert_eq(rrt_at(report, ["oneMinimal"]), Json(false))
}

///|
test "relation category reduction 20 actual source budget zero cannot reduce" {
  let report = rrt_report(rcl_direct_body("INT"), "INT", max_graph_checks=0)
  assert_eq(rrt_at(report, ["status"]), Json("undetermined"))
  assert_eq(rrt_count(report), 0)
}

///|
test "relation category reduction 21 verify G0 recomputes caller category and options" {
  let h = rrt_history(rcl_g0_body())
  let result = reduce_relation_category_v4(h, category="G0", max_checks=0)
  let report = relation_category_reduction_v4_json(result)
  assert_true(
    verify_relation_category_reduction_v4(
      h,
      report,
      category="G0",
      max_checks=0,
    ),
  )
  assert_false(
    verify_relation_category_reduction_v4(
      h,
      report,
      category="G0",
      max_checks=1,
    ),
  )
  object_fields_unchecked_v3(report)["oneMinimal"] = Json(true)
  assert_false(
    verify_relation_category_reduction_v4(
      h,
      report,
      category="G0",
      max_checks=0,
    ),
  )
}

///|
test "relation category reduction 22 verify G1a recomputes caller category and options" {
  let h = rrt_history(rcl_direct_body("G1a"))
  let result = reduce_relation_category_v4(h, category="G1a", max_checks=0)
  let report = relation_category_reduction_v4_json(result)
  assert_true(
    verify_relation_category_reduction_v4(
      h,
      report,
      category="G1a",
      max_checks=0,
    ),
  )
  assert_false(
    verify_relation_category_reduction_v4(
      h,
      report,
      category="G1a",
      max_checks=1,
    ),
  )
  object_fields_unchecked_v3(report)["oneMinimal"] = Json(true)
  assert_false(
    verify_relation_category_reduction_v4(
      h,
      report,
      category="G1a",
      max_checks=0,
    ),
  )
}

///|
test "relation category reduction 23 verify G1b recomputes caller category and options" {
  let h = rrt_history(rcl_direct_body("G1b"))
  let result = reduce_relation_category_v4(h, category="G1b", max_checks=0)
  let report = relation_category_reduction_v4_json(result)
  assert_true(
    verify_relation_category_reduction_v4(
      h,
      report,
      category="G1b",
      max_checks=0,
    ),
  )
  assert_false(
    verify_relation_category_reduction_v4(
      h,
      report,
      category="G1b",
      max_checks=1,
    ),
  )
  object_fields_unchecked_v3(report)["oneMinimal"] = Json(true)
  assert_false(
    verify_relation_category_reduction_v4(
      h,
      report,
      category="G1b",
      max_checks=0,
    ),
  )
}

///|
test "relation category reduction 24 verify G1c recomputes caller category and options" {
  let h = rrt_history(rcl_g0_body())
  let result = reduce_relation_category_v4(h, category="G1c", max_checks=0)
  let report = relation_category_reduction_v4_json(result)
  assert_true(
    verify_relation_category_reduction_v4(
      h,
      report,
      category="G1c",
      max_checks=0,
    ),
  )
  assert_false(
    verify_relation_category_reduction_v4(
      h,
      report,
      category="G1c",
      max_checks=1,
    ),
  )
  object_fields_unchecked_v3(report)["oneMinimal"] = Json(true)
  assert_false(
    verify_relation_category_reduction_v4(
      h,
      report,
      category="G1c",
      max_checks=0,
    ),
  )
}

///|
test "relation category reduction 25 verify G2-item recomputes caller category and options" {
  let h = rrt_history(rrt_g2_body())
  let result = reduce_relation_category_v4(h, category="G2-item", max_checks=0)
  let report = relation_category_reduction_v4_json(result)
  assert_true(
    verify_relation_category_reduction_v4(
      h,
      report,
      category="G2-item",
      max_checks=0,
    ),
  )
  assert_false(
    verify_relation_category_reduction_v4(
      h,
      report,
      category="G2-item",
      max_checks=1,
    ),
  )
  object_fields_unchecked_v3(report)["oneMinimal"] = Json(true)
  assert_false(
    verify_relation_category_reduction_v4(
      h,
      report,
      category="G2-item",
      max_checks=0,
    ),
  )
}

///|
test "relation category reduction 26 verify INT recomputes caller category and options" {
  let h = rrt_history(rcl_direct_body("INT"))
  let result = reduce_relation_category_v4(h, category="INT", max_checks=0)
  let report = relation_category_reduction_v4_json(result)
  assert_true(
    verify_relation_category_reduction_v4(
      h,
      report,
      category="INT",
      max_checks=0,
    ),
  )
  assert_false(
    verify_relation_category_reduction_v4(
      h,
      report,
      category="INT",
      max_checks=1,
    ),
  )
  object_fields_unchecked_v3(report)["oneMinimal"] = Json(true)
  assert_false(
    verify_relation_category_reduction_v4(
      h,
      report,
      category="INT",
      max_checks=0,
    ),
  )
}

///|
test "relation category reduction 27 deletion renumbering never heals original sequence loss" {
  let trace = rpg_trace(rrt_g2_body(noise=1))
  for
    i, e in capture_source_array_v4(
      object_fields_unchecked_v3(trace).at("events"),
    ) {
    object_fields_unchecked_v3(e)["seq"] = Json((i + 1) * 10)
  }
  let history = parse_history_v4(trace.stringify()).unwrap()
  let result = reduce_relation_category_v4(history, category="G2-item")
  let report = relation_category_reduction_v4_json(result)
  assert_eq(rrt_at(report, ["oneMinimal"]), Json(false))
  assert_eq(
    rrt_at(report, ["sourceCoverage", "originalSequenceWindowClosed"]),
    Json(false),
  )
  assert_true(
    capture_source_array_v4(rrt_at(report, ["removedTransactions"])).is_empty(),
  )
  assert_eq(history_v4_json(result.history()), history_v4_json(history))
}

///|
test "relation category reduction 28 unknown SQL transaction cannot heal original source closure" {
  let body = rrt_g2_body(noise=1)
  body[1] = {
    "kind": "statement",
    "tx": "noise-0",
    "sql": "UPDATE records SET value=value",
  }
  let h = rrt_history(body)
  let result = reduce_relation_category_v4(h, category="G2-item")
  let report = relation_category_reduction_v4_json(result)
  assert_eq(
    rrt_at(report, ["classification", "judgment", "rules", "G2-item", "status"]),
    Json("refuted"),
  )
  assert_eq(rrt_at(report, ["status"]), Json("undetermined"))
  assert_eq(
    rrt_at(report, ["sourceCoverage", "originalSourceClosed"]),
    Json(false),
  )
  assert_eq(
    rrt_at(report, ["sourceCoverage", "reducedSourceClosed"]),
    Json(false),
  )
  assert_eq(rrt_at(report, ["oneMinimal"]), Json(false))
  assert_eq(rrt_count(report), 0)
  assert_eq(rrt_at(report, ["removedTransactions"]), Json(([] : Array[String])))
  assert_eq(history_v4_json(result.history()), history_v4_json(h))
}

///|
test "relation category reduction 29 original unlocated source gap retains reliable G1a but no minimum" {
  let trace = rpg_trace(rw5_aborted_body())
  object_fields_unchecked_v3(trace)["gaps"] = Json([
    (
      { "code": "lost-window", "message": "unknown original source range" } :
      Json),
  ])
  let h = parse_history_v4(trace.stringify()).unwrap()
  let result = reduce_relation_category_v4(h, category="G1a")
  let report = relation_category_reduction_v4_json(result)
  assert_eq(
    rrt_at(report, ["classification", "judgment", "rules", "G1a", "status"]),
    Json("refuted"),
  )
  assert_eq(rrt_at(report, ["status"]), Json("undetermined"))
  assert_eq(rrt_count(report), 0)
  assert_eq(rrt_at(report, ["oneMinimal"]), Json(false))
  assert_eq(history_v4_json(result.history()), history_v4_json(h))
}

///|
test "relation category reduction 30 strict original-source predicate has its own identity" {
  let h = rrt_history(rrt_g2_body(noise=1))
  let report = relation_category_reduction_v4_json(
    reduce_relation_category_v4(h, category="G2-item"),
  )
  assert_eq(
    rrt_at(report, ["algorithm"]),
    Json("relation-category-single-delete-2"),
  )
  assert_eq(
    rrt_at(report, ["semanticContract"]),
    Json("relation-point-category-transaction-reduction-2"),
  )
  assert_eq(
    rrt_at(report, ["execution", "counterContract"]),
    Json("relation-category-candidate-checks-1"),
  )
  assert_true(
    verify_relation_category_reduction_v4(h, report, category="G2-item"),
  )
  object_fields_unchecked_v3(report)["algorithm"] = Json(
    "relation-category-single-delete-1",
  )
  assert_false(
    verify_relation_category_reduction_v4(h, report, category="G2-item"),
  )
}
