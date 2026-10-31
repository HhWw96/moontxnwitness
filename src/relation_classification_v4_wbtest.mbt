///|
fn rcl_history(body : Array[Json], empty~ : Bool = false) -> HistoryV4 {
  parse_history_v4(rpg_trace(body, empty~).stringify()).unwrap()
}

///|
fn rcl_rule(report : Json, category : String) -> Json {
  relation_classification_at_v4(report, ["judgment", "rules", category])
}

///|
fn rcl_report(
  history : HistoryV4,
  categories~ : Array[String] = ["G0", "G1a", "G1b", "G1c", "G2-item", "INT"],
) -> Json {
  relation_classification_v4_json(
    classify_relation_point_v4(history, categories~),
  )
}

///|
fn rcl_number(value : Json) -> Int32 {
  match value {
    Number(n, ..) => n.to_int()
    _ => -1
  }
}

///|
fn rcl_g0_body() -> Array[Json] {
  let body = [
    rpg_begin("A"),
    rpg_begin("B"),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_write("B", "1", "v2", Some("v1")),
    rpg_write("B", "2", "u1", Some("u0")),
    rpg_write("A", "2", "u2", Some("u1")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  body
}

///|
fn rcl_direct_body(category : String) -> Array[Json] {
  if category == "INT" {
    let body = [
      rpg_begin("A"),
      rpg_write("A", "1", "v1", Some("v0")),
      rpg_read("A", "1", Some("v0")),
    ]
    rpg_commit(body, "A")
    return body
  }
  let body = [rpg_begin("P"), rpg_write("P", "1", "p1", Some("v0"))]
  if category == "G1a" {
    body.push({ "kind": "rollback_ok", "tx": "P" })
  } else {
    body.push(rpg_write("P", "1", "p2", Some("p1")))
    rpg_commit(body, "P")
  }
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "1", Some("p1")))
  rpg_commit(body, "R")
  body
}

///|
test "relation classification 01 defaults cover six distinct categories with new contract" {
  let body = [rpg_begin("R"), rpg_read("R", "1", Some("v0"))]
  rpg_commit(body, "R")
  let history = rcl_history(body)
  let result = classify_relation_point_v4(history)
  assert_eq(result.status(), "checked-compatible")
  let report = relation_classification_v4_json(result)
  assert_eq(
    capture_field(report, "format"),
    Json("moontxnwitness-relation-classification/v4"),
  )
  assert_eq(
    capture_field(report, "algorithm"),
    Json("v4-relation-point-category-5"),
  )
  assert_eq(
    capture_field(report, "semanticContract"),
    Json("moontxnwitness-relation-point-category-classification-v4-5"),
  )
  assert_eq(
    v4_test_at(report, ["execution", "counterContract"]),
    Json("v4-relation-point-category-counters-5"),
  )
  assert_eq(
    v4_test_at(report, ["execution", "categories"]),
    Json(["G0", "G1a", "G1b", "G1c", "G2-item", "INT"]),
  )
  assert_eq(
    v4_test_at(report, ["judgment", "acceptsIsolationModels"]),
    Json(false),
  )
  assert_true(verify_relation_classification_v4(history, report))
}

///|
test "relation classification 02 WW G0 evidence keeps most specific label and implication closure" {
  let report = rcl_report(rcl_history(rcl_g0_body()))
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("refuted"))
  let evidence = capture_field(rcl_rule(report, "G0"), "evidence")
  assert_eq(capture_field(evidence, "specificCategory"), Json("G0"))
  assert_eq(v3_test_items(evidence, "edges").length(), 2)
  let implied = v3_test_items(
    v4_test_at(report, ["judgment"]),
    "impliedAnomalies",
  )
  assert_true(
    implied.contains(Json("G0")) &&
    implied.contains(Json("G1c")) &&
    implied.contains(Json("G1")),
  )
}

///|
test "relation classification 03 requesting G1c retains concrete WW only G0 witness" {
  let report = rcl_report(rcl_history(rcl_g0_body()), categories=["G1c"])
  let evidence = capture_field(rcl_rule(report, "G1c"), "evidence")
  assert_eq(capture_field(evidence, "requestedCategory"), Json("G1c"))
  assert_eq(capture_field(evidence, "specificCategory"), Json("G0"))
  assert_eq(
    v4_test_at(report, ["judgment", "impliedAnomalies"]),
    Json(["G0", "G1c", "G1"]),
  )
}

///|
test "relation classification 04 WR cycle resolves original relation primary key version and query index" {
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
  let report = rcl_report(rcl_history(body), categories=["G1c"])
  let evidence = capture_field(rcl_rule(report, "G1c"), "evidence")
  assert_eq(capture_field(evidence, "specificCategory"), Json("G1c"))
  let entries = v3_test_items(evidence, "edges")
  assert_eq(entries.length(), 2)
  for position, entry in entries {
    assert_eq(
      v4_test_at(entry, ["edge", "to"]),
      v4_test_at(entries[(position + 1) % entries.length()], ["edge", "from"]),
    )
    assert_eq(v4_test_at(entry, ["identity", "relation"]), Json("items"))
    assert_eq(v4_test_at(entry, ["identity", "primaryType"]), Json("int64"))
    for link in v3_test_items(entry, "observationLinks") {
      assert_true(rcl_number(capture_field(link, "fromObservationSeq")) > 0)
      assert_true(rcl_number(capture_field(link, "toObservationSeq")) > 0)
      assert_eq(capture_field(link, "queryIndex"), Json(0))
    }
    assert_false(v3_test_items(entry, "sources").is_empty())
  }
}

///|
test "relation classification 05 item anti dependency cycle preserves exact requested scope" {
  let history = rcl_history(rpg_skew_body())
  let report = rcl_report(history, categories=["G2-item"])
  let evidence = capture_field(rcl_rule(report, "G2-item"), "evidence")
  assert_eq(capture_field(evidence, "specificCategory"), Json("G2-item"))
  assert_eq(capture_field(evidence, "containsPredicateEdges"), Json(false))
  assert_eq(
    v4_test_at(report, ["judgment", "impliedAnomalies"]),
    Json(["G2-item", "G2"]),
  )
  for entry in v3_test_items(evidence, "edges") {
    assert_eq(v4_test_at(entry, ["edge", "kind"]), Json("rw"))
  }
  assert_true(
    verify_relation_classification_v4(history, report, categories=["G2-item"]),
  )
}

///|
test "relation classification 06 reliable G1a is retained when all cycle budgets are zero" {
  let report = relation_classification_v4_json(
    classify_relation_point_v4(
      rcl_history(rcl_direct_body("G1a")),
      max_states=0,
      max_edge_checks=0,
    ),
  )
  assert_eq(capture_field(rcl_rule(report, "G1a"), "status"), Json("refuted"))
  assert_eq(capture_field(rcl_rule(report, "G1a"), "states"), Json(0))
  assert_eq(capture_field(rcl_rule(report, "G1a"), "edgeChecks"), Json(0))
  assert_eq(capture_field(rcl_rule(report, "G1a"), "directProofs"), Json(1))
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("refuted"))
  assert_eq(
    v4_test_at(report, ["judgment", "impliedAnomalies"]),
    Json(["G1a", "G1"]),
  )
}

///|
test "relation classification 07 reliable G1b does not borrow cycle edge or state budget" {
  let report = relation_classification_v4_json(
    classify_relation_point_v4(
      rcl_history(rcl_direct_body("G1b")),
      categories=["G1b"],
      max_states=0,
      max_edge_checks=0,
    ),
  )
  assert_eq(capture_field(rcl_rule(report, "G1b"), "status"), Json("refuted"))
  assert_eq(capture_field(rcl_rule(report, "G1b"), "directProofs"), Json(1))
  assert_eq(
    v4_test_at(report, ["judgment", "impliedAnomalies"]),
    Json(["G1b", "G1"]),
  )
}

///|
test "relation classification 08 INT remains a separate direct category with no false G1 implication" {
  let history = rcl_history(rcl_direct_body("INT"))
  let report = relation_classification_v4_json(
    classify_relation_point_v4(
      history,
      categories=["INT"],
      max_states=0,
      max_edge_checks=0,
    ),
  )
  assert_eq(capture_field(rcl_rule(report, "INT"), "status"), Json("refuted"))
  assert_eq(v4_test_at(report, ["judgment", "impliedAnomalies"]), Json(["INT"]))
  assert_true(
    verify_relation_classification_v4(
      history,
      report,
      categories=["INT"],
      max_states=0,
      max_edge_checks=0,
    ),
  )
}

///|
test "relation classification 09 INT cannot hide an independent aborted or intermediate read source" {
  for category in ["G1a", "G1b"] {
    let body = [rpg_begin("P"), rpg_write("P", "1", "p1", Some("v0"))]
    if category == "G1a" {
      body.push({ "kind": "rollback_ok", "tx": "P" })
    } else {
      body.push(rpg_write("P", "1", "p2", Some("p1")))
      rpg_commit(body, "P")
    }
    body.push(rpg_begin("A"))
    body.push(
      rpg_write(
        "A",
        "1",
        "a1",
        Some(if category == "G1a" { "v0" } else { "p2" }),
      ),
    )
    body.push(rpg_read("A", "1", Some("p1")))
    rpg_commit(body, "A")
    let report = rcl_report(rcl_history(body))
    assert_eq(
      capture_field(rcl_rule(report, category), "status"),
      Json("refuted"),
    )
    assert_eq(capture_field(rcl_rule(report, "INT"), "status"), Json("refuted"))
  }
}

///|
fn rcl_budget_after_proof(
  history : HistoryV4,
  category : String,
  source_complete~ : Bool = false,
) -> Int32 raise {
  let parsed = match history.payload {
    RelationSnapshot(parsed) => parsed
    _ => fail("Expected relation capture")
  }
  let full = relation_graph_point_v4(parsed)
  for maximum in 0..<full.checks {
    let graph = relation_graph_point_v4(parsed, max_checks=maximum)
    if graph.limited &&
      (if source_complete {
        graph.index.reads_complete
      } else {
        !graph.index.direct.get_or_default(category, []).is_empty()
      }) {
      return maximum
    }
  }
  fail("Expected a bounded run with source progress before exhaustion")
}

///|
test "relation classification 10 an earlier direct proof survives later graph budget exhaustion" {
  let body = rcl_direct_body("G1a")
  body.push(rpg_begin("N"))
  body.push(rpg_read("N", "2", Some("u0")))
  rpg_commit(body, "N")
  let history = rcl_history(body)
  let maximum = rcl_budget_after_proof(history, "G1a")
  let report = relation_classification_v4_json(
    classify_relation_point_v4(
      history,
      max_states=0,
      max_edge_checks=0,
      max_graph_checks=maximum,
    ),
  )
  assert_eq(v4_test_at(report, ["execution", "graphLimited"]), Json(true))
  assert_eq(capture_field(rcl_rule(report, "G1a"), "status"), Json("refuted"))
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("refuted"))
  assert_true(
    verify_relation_classification_v4(
      history,
      report,
      max_states=0,
      max_edge_checks=0,
      max_graph_checks=maximum,
    ),
  )
}

///|
test "relation classification 11 complete direct source checks are not made unknown by edge construction limit" {
  let history = rcl_history(rpg_skew_body())
  let maximum = rcl_budget_after_proof(history, "G1a", source_complete=true)
  let report = relation_classification_v4_json(
    classify_relation_point_v4(history, max_graph_checks=maximum),
  )
  assert_eq(v4_test_at(report, ["execution", "graphLimited"]), Json(true))
  for category in ["G1a", "G1b", "INT"] {
    assert_eq(
      capture_field(rcl_rule(report, category), "status"),
      Json("checked-compatible"),
    )
  }
  assert_eq(
    capture_field(rcl_rule(report, "G2-item"), "status"),
    Json("unknown"),
  )
}

///|
test "relation classification 12 zero source budget cannot claim completed checks or absent anomalies" {
  let report = relation_classification_v4_json(
    classify_relation_point_v4(
      rcl_history(rcl_direct_body("G1a")),
      max_graph_checks=0,
    ),
  )
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("inconclusive"))
  assert_eq(v4_test_at(report, ["execution", "graphChecks"]), Json(0))
  for category in relation_classification_categories_v4() {
    assert_eq(
      capture_field(rcl_rule(report, category), "status"),
      Json("unknown"),
    )
  }
}

///|
test "relation classification 13 missing returned source keeps necessary source checks unknown" {
  let body = [rpg_begin("R"), rpg_read("R", "1", Some("missing"))]
  rpg_commit(body, "R")
  let report = rcl_report(rcl_history(body))
  for category in relation_classification_categories_v4() {
    assert_eq(
      capture_field(rcl_rule(report, category), "status"),
      Json("unknown"),
    )
  }
}

///|
test "relation classification 14 unknown version order does not prevent complete direct source checks" {
  let body = [
    rpg_begin("A"),
    rpg_begin("B"),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_write("B", "1", "v2", Some("v0")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  let report = rcl_report(rcl_history(body))
  for category in ["G0", "G1c", "G2-item"] {
    assert_eq(
      capture_field(rcl_rule(report, category), "status"),
      Json("unknown"),
    )
  }
  for category in ["G1a", "G1b", "INT"] {
    assert_eq(
      capture_field(rcl_rule(report, category), "status"),
      Json("checked-compatible"),
    )
  }
}

///|
test "relation classification 15 raw competing tombstones cannot manufacture WR or G1c" {
  for mode in ["aborted", "reverted", "intermediate", "unknown"] {
    let history = rcl_history(rpg_ambiguous_raw_delete_body(mode))
    let report = rcl_report(history)
    assert_eq(v4_test_at(report, ["judgment", "status"]), Json("inconclusive"))
    assert_eq(capture_field(rcl_rule(report, "G1c"), "status"), Json("unknown"))
    for edge in v3_test_items(v4_test_at(report, ["judgment"]), "dependencies") {
      assert_false(
        capture_field(edge, "kind") == Json("wr") &&
        capture_field(edge, "to") == Json("R"),
      )
    }
    assert_true(verify_relation_classification_v4(history, report))
  }
}

///|
test "relation classification 16 shorter WW cycle does not hide another requested G2 item cycle" {
  let body = rcl_g0_body()
  body.push(rpg_begin("C"))
  body.push(rpg_begin("D"))
  body.push(rpg_read("C", "4", Some("w0")))
  body.push(rpg_read("D", "3", Some("z0")))
  body.push(rpg_write("C", "3", "z1", Some("z0")))
  body.push(rpg_write("D", "4", "w1", Some("w0")))
  rpg_commit(body, "C")
  rpg_commit(body, "D")
  let trace = rpg_trace(body)
  let snapshot = object_fields_unchecked_v3(v3_test_items(trace, "events")[0])
  let rows = match capture_field(snapshot.at("initial"), "items") {
    Array(rows) => rows
    _ => []
  }
  rows.push(rpg_row("4", "w0"))
  let history = parse_history_v4(trace.stringify()).unwrap()
  let report = rcl_report(history, categories=["G0", "G2-item"])
  assert_eq(capture_field(rcl_rule(report, "G0"), "status"), Json("refuted"))
  assert_eq(
    capture_field(rcl_rule(report, "G2-item"), "status"),
    Json("refuted"),
  )
  for
    entry in v3_test_items(
      capture_field(rcl_rule(report, "G2-item"), "evidence"),
      "edges",
    ) {
    assert_true(
      [Json("C"), Json("D")].contains(v4_test_at(entry, ["edge", "from"])),
    )
  }
}

///|
test "relation classification 17 repeated delivered reads retain every source on shared WR edge" {
  let body = [
    rpg_begin("A"),
    rpg_begin("B"),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_write("B", "2", "u1", Some("u0")),
    rpg_read("A", "2", Some("u1")),
    rpg_read("B", "1", Some("v1")),
    rpg_read("B", "1", Some("v1")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  let report = rcl_report(rcl_history(body), categories=["G1c"])
  let entries = v3_test_items(
    capture_field(rcl_rule(report, "G1c"), "evidence"),
    "edges",
  )
  let repeated = entries.filter(entry => {
      v4_test_at(entry, ["edge", "to"]) == Json("B")
    })[0]
  assert_eq(v3_test_items(repeated, "sources").length(), 2)
  let links = v3_test_items(repeated, "observationLinks")
  assert_eq(links.length(), 2)
  assert_eq(capture_field(links[0], "queryIndex"), Json(0))
  assert_eq(capture_field(links[1], "queryIndex"), Json(1))
}

///|
test "relation classification 18 exact cycle budget succeeds and either exhausted bound is unknown" {
  let history = rcl_history(rpg_skew_body())
  let full = rcl_report(history, categories=["G2-item"])
  let states = rcl_number(capture_field(rcl_rule(full, "G2-item"), "states"))
  let checks = rcl_number(
    capture_field(rcl_rule(full, "G2-item"), "edgeChecks"),
  )
  assert_true(states > 0 && checks > 0)
  assert_eq(
    classify_relation_point_v4(
      history,
      categories=["G2-item"],
      max_states=states,
      max_edge_checks=checks,
    ).status(),
    "refuted",
  )
  for limits in [(states - 1, checks), (states, checks - 1)] {
    let result = classify_relation_point_v4(
      history,
      categories=["G2-item"],
      max_states=limits.0,
      max_edge_checks=limits.1,
    )
    assert_eq(result.status(), "inconclusive")
    assert_eq(
      capture_field(
        rcl_rule(relation_classification_v4_json(result), "G2-item"),
        "status",
      ),
      Json("unknown"),
    )
  }
}

///|
test "relation classification 19 every category has independent counters regardless of request order" {
  let history = rcl_history(rpg_skew_body())
  let first = rcl_report(history, categories=[
    "G0", "G1a", "G1b", "G1c", "G2-item", "INT",
  ])
  let second = rcl_report(history, categories=[
    "INT", "G2-item", "G1c", "G1b", "G1a", "G0",
  ])
  for category in relation_classification_categories_v4() {
    assert_eq(rcl_rule(first, category), rcl_rule(second, category))
  }
}

///|
test "relation classification 20 a reliable direct refutation dominates other category timeout" {
  let body = rcl_g0_body()
  body.push(rpg_begin("P"))
  body.push(rpg_write("P", "3", "p1", Some("z0")))
  body.push({ "kind": "rollback_ok", "tx": "P" })
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "3", Some("p1")))
  rpg_commit(body, "R")
  let history = rcl_history(body)
  let report = relation_classification_v4_json(
    classify_relation_point_v4(
      history,
      categories=["G0", "G1a"],
      max_states=0,
      max_edge_checks=0,
    ),
  )
  assert_eq(capture_field(rcl_rule(report, "G0"), "status"), Json("unknown"))
  assert_eq(capture_field(rcl_rule(report, "G1a"), "status"), Json("refuted"))
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("refuted"))
}

///|
test "relation classification 21 wrong model is unsupported while old generic relation entry stays unsupported" {
  let register = register_history_v4(skew()).unwrap()
  assert_eq(classify_relation_point_v4(register).status(), "unsupported")
  let relation = rcl_history(rpg_skew_body())
  assert_eq(classify_v4(relation).status(), "unsupported")
  assert_eq(classify_relation_point_v4(relation).status(), "refuted")
}

///|
test "relation classification 22 category selection rejects duplicates empty and unsupported additions" {
  let history = rcl_history(rpg_skew_body())
  for
    categories in [
      ([] : Array[String]),
      ["G0", "G0"],
      ["G-single"],
      ["serializable"],
      ["G2"],
    ] {
    assert_eq(
      classify_relation_point_v4(history, categories~).status(),
      "invalid",
    )
  }
}

///|
test "relation classification 23 all caller budgets are bounded before analysis" {
  let history = rcl_history(rpg_skew_body())
  for maximum in [-1, 100001] {
    assert_eq(
      classify_relation_point_v4(history, max_states=maximum).status(),
      "invalid",
    )
  }
  for maximum in [-1, 1000001] {
    assert_eq(
      classify_relation_point_v4(history, max_edge_checks=maximum).status(),
      "invalid",
    )
    assert_eq(
      classify_relation_point_v4(history, max_graph_checks=maximum).status(),
      "invalid",
    )
  }
}

///|
test "relation classification 24 verify rejects changed conclusion schema model algorithm and counters" {
  let history = rcl_history(rpg_skew_body())
  for field in ["algorithm", "semanticContract", "dataModel", "schemaVersion"] {
    let report = rcl_report(history)
    object_fields_unchecked_v3(report)[field] = Json("tampered")
    assert_false(verify_relation_classification_v4(history, report))
  }
  let report = rcl_report(history)
  object_fields_unchecked_v3(v4_test_at(report, ["judgment"]))["status"] = Json(
    "checked-compatible",
  )
  assert_false(verify_relation_classification_v4(history, report))
  let counters = rcl_report(history)
  object_fields_unchecked_v3(v4_test_at(counters, ["execution"]))["graphChecks"] = Json(
    0,
  )
  assert_false(verify_relation_classification_v4(history, counters))
}

///|
test "relation classification 25 proof cannot increase caller graph or cycle budget" {
  let history = rcl_history(rpg_skew_body())
  let report = rcl_report(history)
  assert_false(
    verify_relation_classification_v4(history, report, max_graph_checks=0),
  )
  assert_false(
    verify_relation_classification_v4(
      history,
      report,
      max_states=0,
      max_edge_checks=0,
    ),
  )
  object_fields_unchecked_v3(v4_test_at(report, ["execution", "limits"]))["graphChecks"] = Json(
    0,
  )
  assert_false(
    verify_relation_classification_v4(history, report, max_graph_checks=0),
  )
}

///|
test "relation classification 26 source primary key query index version and raw seq are bound" {
  let history = rcl_history(rpg_skew_body())
  for part in ["identity", "queryIndex", "version", "seq"] {
    let report = rcl_report(history, categories=["G2-item"])
    let entry = v3_test_items(
        capture_field(rcl_rule(report, "G2-item"), "evidence"),
        "edges",
      )[0]
    let source = v3_test_items(entry, "sources")[0]
    if part == "identity" {
      object_fields_unchecked_v3(capture_field(entry, "identity"))["primaryKey"] = Json(
        "99",
      )
    } else if part == "queryIndex" {
      object_fields_unchecked_v3(source)["queryIndex"] = Json(99)
    } else if part == "version" {
      object_fields_unchecked_v3(v4_test_at(source, ["laterEffect", "fact"]))["version"] = Json(
        "invented",
      )
    } else {
      object_fields_unchecked_v3(v4_test_at(source, ["queryObservation"]))["seq"] = Json(
        999,
      )
    }
    assert_false(
      verify_relation_classification_v4(history, report, categories=["G2-item"]),
    )
  }
}

///|
test "relation classification 27 raw observations remain original and no inferred order is added as fact" {
  let history = rcl_history(rpg_rollback_body())
  let before = history.source_text()
  let report = rcl_report(history)
  assert_eq(
    v4_test_at(report, ["observations", "document"]),
    history.source_document,
  )
  assert_eq(history.source_text(), before)
  assert_eq(
    v4_test_at(report, ["inferences", "versionOrderCompletion"]),
    Json(false),
  )
  assert_false(
    object_fields_unchecked_v3(v4_test_at(report, ["observations", "document"])).contains(
      "versionOrders",
    ),
  )
}

///|
test "relation classification 28 detached views do not leak snapshot or result mutations" {
  let history = rcl_history(rpg_skew_body())
  let result = classify_relation_point_v4(history)
  let original = render_relation_classification_v4(result)
  let view = relation_classification_v4_json(result)
  object_fields_unchecked_v3(v4_test_at(view, ["observations", "document"]))["gaps"] = Json([
      "fake",
    ],
  )
  object_fields_unchecked_v3(v4_test_at(view, ["inferences"]))["sourceAudit"] = Json([
      "fake",
    ],
  )
  assert_eq(render_relation_classification_v4(result), original)
  assert_eq(
    render_relation_classification_v4(classify_relation_point_v4(history)),
    original,
  )
}

///|
test "relation classification 29 empty source work can complete with zero budgets without invented transactions" {
  let history = rcl_history([], empty=true)
  let report = relation_classification_v4_json(
    classify_relation_point_v4(
      history,
      max_states=0,
      max_edge_checks=0,
      max_graph_checks=0,
    ),
  )
  assert_eq(
    v4_test_at(report, ["judgment", "status"]),
    Json("checked-compatible"),
  )
  assert_eq(v4_test_at(report, ["execution", "graphChecks"]), Json(0))
  assert_true(
    v3_test_items(v4_test_at(report, ["judgment"]), "dependencies").is_empty(),
  )
  for category in relation_classification_categories_v4() {
    assert_eq(
      capture_field(rcl_rule(report, category), "status"),
      Json("checked-compatible"),
    )
  }
}

///|
test "relation classification 30 past delivered own read remains legal after later savepoint rollback" {
  let report = rcl_report(rcl_history(rpg_rollback_body()))
  assert_eq(
    v4_test_at(report, ["judgment", "status"]),
    Json("checked-compatible"),
  )
  for category in ["G1a", "G1b", "INT"] {
    assert_eq(
      capture_field(rcl_rule(report, category), "directProofs"),
      Json(0),
    )
  }
  let reads = v3_test_items(
    v4_test_at(report, ["inferences"]),
    "readSourceResolutions",
  )
  assert_eq(
    v4_test_at(reads[0], ["ownAtDelivery", "fact", "version"]),
    Json("v1"),
  )
  assert_eq(capture_field(reads[0], "usable"), Json(true))
}

///|
test "relation classification 31 WW witness retains intermediate tombstone path with original effects" {
  let body = [
    rpg_begin("A"),
    rpg_begin("B"),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_write("B", "1", "d2", Some("v1"), action="delete"),
    rpg_write("B", "1", "v3", Some("d2"), action="insert"),
    rpg_write("B", "2", "u1", Some("u0")),
    rpg_write("A", "2", "u2", Some("u1")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  let report = rcl_report(rcl_history(body), categories=["G0"])
  let entries = v3_test_items(
    capture_field(rcl_rule(report, "G0"), "evidence"),
    "edges",
  )
  let path = v3_test_items(
    v3_test_items(
      entries.filter(entry => {
        v4_test_at(entry, ["identity", "primaryKey"]) == Json("1")
      })[0],
      "sources",
    )[0],
    "predecessorPath",
  )
  assert_eq(path.length(), 3)
  assert_eq(v4_test_at(path[1], ["original", "action"]), Json("delete"))
  assert_eq(v4_test_at(path[1], ["fact", "values"]), Json::null())
}

///|
test "relation classification 32 unknown COMMIT outcome is neither aborted nor confirmed WR" {
  let body = [
    rpg_begin("P"),
    rpg_write("P", "1", "v1", Some("v0")),
    ({ "kind": "commit_request", "tx": "P" } : Json),
    rpg_begin("R"),
    rpg_read("R", "1", Some("v1")),
  ]
  rpg_commit(body, "R")
  let report = rcl_report(rcl_history(body))
  assert_eq(capture_field(rcl_rule(report, "G1a"), "status"), Json("unknown"))
  assert_eq(capture_field(rcl_rule(report, "G1a"), "directProofs"), Json(0))
  assert_true(
    v3_test_items(v4_test_at(report, ["judgment"]), "dependencies").is_empty(),
  )
}

///|
test "relation classification 33 reliable other key counterexample survives missing source elsewhere" {
  let body = rpg_skew_body()
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "3", Some("missing")))
  rpg_commit(body, "R")
  let report = rcl_report(rcl_history(body))
  assert_eq(
    v4_test_at(report, ["judgment", "dependencyGraphComplete"]),
    Json(false),
  )
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("refuted"))
  assert_eq(
    capture_field(rcl_rule(report, "G2-item"), "status"),
    Json("refuted"),
  )
  assert_eq(capture_field(rcl_rule(report, "G1a"), "status"), Json("unknown"))
}

///|
test "relation classification 34 graph capacity does not change six transaction exact interpreter cap" {
  let body : Array[Json] = []
  let mut previous = "v0"
  for number in 0..<8 {
    let tx = "T" + number.to_string()
    let version = "v" + (number + 1).to_string()
    body.push(rpg_begin(tx))
    body.push(rpg_write(tx, "1", version, Some(previous)))
    rpg_commit(body, tx)
    previous = version
  }
  let history = rcl_history(body)
  assert_true(analyze_v4(history).outcome() == Inconclusive)
  assert_eq(classify_relation_point_v4(history).status(), "checked-compatible")
}

///|
test "relation classification 35 early delivered INT proof survives later source budget without claiming completion" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_read("A", "1", Some("v0")),
    rpg_read("A", "2", Some("u0")),
  ]
  rpg_commit(body, "A")
  let history = rcl_history(body)
  let maximum = rcl_budget_after_proof(history, "INT")
  let report = relation_classification_v4_json(
    classify_relation_point_v4(
      history,
      categories=["INT"],
      max_states=0,
      max_edge_checks=0,
      max_graph_checks=maximum,
    ),
  )
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("refuted"))
  assert_eq(v4_test_at(report, ["execution", "graphLimited"]), Json(true))
  assert_eq(
    capture_field(rcl_rule(report, "INT"), "sourceChecksComplete"),
    Json(false),
  )
  let proofs = v3_test_items(
    capture_field(rcl_rule(report, "INT"), "evidence"),
    "proofs",
  )
  assert_eq(
    v4_test_at(proofs[0], ["source", "effectAuditComplete"]),
    Json(true),
  )
  assert_eq(
    v4_test_at(proofs[0], ["expectedLocalEffect", "finalCommittedEffect"]),
    Json(true),
  )

  assert_eq(v4_test_at(proofs[0], ["original", "kind"]), Json("row_read"))
  assert_eq(capture_field(proofs[0], "queryIndex"), Json(0))
  assert_true(
    verify_relation_classification_v4(
      history,
      report,
      categories=["INT"],
      max_states=0,
      max_edge_checks=0,
      max_graph_checks=maximum,
    ),
  )
}

///|
test "relation classification 36 extra predicates remain unknown rather than fabricated point reads" {
  let read = rpg_read("R", "1", Some("v0"))
  object_fields_unchecked_v3(read)["predicate"] = Json([
    ({ "column": "id", "op": "eq", "value": "1" } : Json),
    { "column": "value", "op": "eq", "value": "same" },
  ])
  let body = [rpg_begin("R"), read]
  rpg_commit(body, "R")
  let report = rcl_report(rcl_history(body))
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("inconclusive"))
  for category in relation_classification_categories_v4() {
    assert_eq(
      capture_field(rcl_rule(report, category), "status"),
      Json("unknown"),
    )
  }
}

///|
test "relation classification 37 formal external point read changes cannot be checked compatible" {
  for mode in ["version", "savepoint", "present-absence", "absence-present"] {
    let history = rcl_history(rpg_external_changed_body(mode))
    let report = rcl_report(history, categories=["INT"])
    assert_eq(capture_field(rcl_rule(report, "INT"), "status"), Json("refuted"))
    assert_eq(v4_test_at(report, ["judgment", "status"]), Json("refuted"))
    assert_true(
      verify_relation_classification_v4(history, report, categories=["INT"]),
    )
  }
}

///|
test "relation classification 38 unproved intervening semantics keep INT unknown" {
  for kind in ["statement", "condition"] {
    let report = rcl_report(rcl_history(rpg_unproved_between_body(kind)), categories=[
      "INT",
    ])
    assert_eq(capture_field(rcl_rule(report, "INT"), "status"), Json("unknown"))
    assert_eq(v4_test_at(report, ["judgment", "status"]), Json("inconclusive"))
  }
}

///|
test "relation classification 39 reliable prior INT survives later unproved SQL and zero cycle budget" {
  let history = rcl_history(rpg_unproved_between_body("statement", after=true))
  let report = relation_classification_v4_json(
    classify_relation_point_v4(
      history,
      categories=["INT"],
      max_states=0,
      max_edge_checks=0,
    ),
  )
  assert_eq(capture_field(rcl_rule(report, "INT"), "status"), Json("refuted"))
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("refuted"))
}

///|
test "relation classification 40 missing opaque event window cannot imply nearest read consistency" {
  let trace = rpg_trace(rpg_external_changed_body("version"))
  object_fields_unchecked_v3(trace)["gaps"] = Json([
    (
      { "code": "dropped-event", "message": "An operation may have been lost" } :
      Json),
  ])
  let history = parse_history_v4(trace.stringify()).unwrap()
  let report = rcl_report(history, categories=["INT"])
  assert_eq(capture_field(rcl_rule(report, "INT"), "status"), Json("unknown"))
}

///|
test "relation classification 41 external INT expected observation cannot be tampered or raise caller budget" {
  let history = rcl_history(rpg_external_changed_body("version"))
  let report = rcl_report(history, categories=["INT"])
  let proof = v3_test_items(
      capture_field(rcl_rule(report, "INT"), "evidence"),
      "proofs",
    )[0]
  object_fields_unchecked_v3(
    capture_field(proof, "expectedExternalObservation"),
  )["queryIndex"] = Json(999)
  assert_false(
    verify_relation_classification_v4(history, report, categories=["INT"]),
  )
  assert_false(
    verify_relation_classification_v4(
      history,
      rcl_report(history, categories=["INT"]),
      categories=["INT"],
      max_graph_checks=0,
    ),
  )
}

///|
test "relation classification 42 unseen own mutation leaves INT unknown rather than refuting guessed state" {
  let body = [
    rpg_begin("R"),
    rpg_write("R", "1", "own", Some("v0")),
    (
      { "kind": "statement", "tx": "R", "sql": "SELECT unmodeled_own_change()" } :
      Json),
    rpg_read("R", "1", Some("v0")),
  ]
  rpg_commit(body, "R")
  let report = rcl_report(rcl_history(body), categories=["INT"])
  assert_eq(capture_field(rcl_rule(report, "INT"), "status"), Json("unknown"))
  let reads = v3_test_items(
    v4_test_at(report, ["inferences"]),
    "readSourceResolutions",
  )
  assert_eq(capture_field(reads[0], "ownOverlayProven"), Json(false))
  assert_eq(capture_field(reads[0], "ownAtDelivery"), Json::null())
}

///|
test "relation classification 43 own successor cycle is G1c without a fabricated G2 item label" {
  let history = rcl_history(rpg_own_successor_body())
  let report = rcl_report(history, categories=["G1c", "G2-item"])
  assert_eq(capture_field(rcl_rule(report, "G1c"), "status"), Json("refuted"))
  assert_eq(
    capture_field(rcl_rule(report, "G2-item"), "status"),
    Json("checked-compatible"),
  )
  assert_eq(
    v4_test_at(report, ["judgment", "impliedAnomalies"]),
    Json(["G1c", "G1"]),
  )
  assert_true(
    verify_relation_classification_v4(history, report, categories=[
      "G1c", "G2-item",
    ]),
  )
}

///|
test "relation classification 44 direct item witness preserves RW WW WR path without shortcut" {
  let history = rcl_history(rpg_direct_successor_cycle_body())
  let report = rcl_report(history, categories=["G2-item"])
  let entries = v3_test_items(
    capture_field(rcl_rule(report, "G2-item"), "evidence"),
    "edges",
  )
  assert_eq(entries.length(), 3)
  assert_eq(
    entries
    .filter(entry => v4_test_at(entry, ["edge", "kind"]) == Json("rw"))
    .length(),
    1,
  )
  assert_true(
    entries.any(entry => v4_test_at(entry, ["edge", "kind"]) == Json("ww")),
  )
  assert_true(
    verify_relation_classification_v4(history, report, categories=["G2-item"]),
  )
}

///|
test "relation classification 45 write source failure alone cannot refute read based INT" {
  let history = rcl_history(rpg_write_source_mismatch_body())
  let report = rcl_report(history, categories=["G0", "INT"])
  assert_eq(capture_field(rcl_rule(report, "G0"), "status"), Json("unknown"))
  assert_eq(
    capture_field(rcl_rule(report, "INT"), "status"),
    Json("checked-compatible"),
  )
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("inconclusive"))
  assert_eq(capture_field(rcl_rule(report, "INT"), "evidence"), Json::null())
  assert_true(
    verify_relation_classification_v4(history, report, categories=["G0", "INT"]),
  )
}

///|
test "relation classification 46 invalid write prevents guessing the later own read state" {
  let history = rcl_history(rpg_local_write_mismatch_body())
  let report = rcl_report(history, categories=["INT"])
  assert_eq(capture_field(rcl_rule(report, "INT"), "status"), Json("unknown"))
  assert_eq(
    v4_test_at(report, ["judgment", "impliedAnomalies"]),
    Json(([] : Array[Json])),
  )
  let reads = v3_test_items(
    v4_test_at(report, ["inferences"]),
    "readSourceResolutions",
  )
  assert_eq(capture_field(reads[0], "ownOverlayProven"), Json(false))
  assert_eq(capture_field(reads[0], "ownAtDelivery"), Json::null())
  assert_true(
    verify_relation_classification_v4(history, report, categories=["INT"]),
  )
}

///|
test "relation classification 47 actual read proof before invalid write survives zero cycle budget" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "A1", Some("v0")),
    rpg_read("A", "1", Some("v0")),
    rpg_write("A", "1", "A2", Some("v0")),
    rpg_read("A", "1", Some("v0")),
  ]
  rpg_commit(body, "A")
  let history = rcl_history(body)
  let report = relation_classification_v4_json(
    classify_relation_point_v4(
      history,
      categories=["INT"],
      max_states=0,
      max_edge_checks=0,
    ),
  )
  assert_eq(capture_field(rcl_rule(report, "INT"), "status"), Json("refuted"))
  let proofs = v3_test_items(
    capture_field(rcl_rule(report, "INT"), "evidence"),
    "proofs",
  )
  assert_eq(proofs.length(), 1)
  assert_eq(capture_field(proofs[0], "queryIndex"), Json(0))
  assert_eq(v4_test_at(proofs[0], ["original", "kind"]), Json("row_read"))
  assert_eq(capture_field(proofs[0], "observationSeq"), Json(4))
  assert_true(
    verify_relation_classification_v4(
      history,
      report,
      categories=["INT"],
      max_states=0,
      max_edge_checks=0,
    ),
  )
}

///|
test "relation classification 48 delivered read query identity is part of full record verification" {
  let history = rcl_history(rpg_external_changed_body("version"))
  let report = rcl_report(history, categories=["INT"])
  let proof = v3_test_items(
      capture_field(rcl_rule(report, "INT"), "evidence"),
      "proofs",
    )[0]
  assert_eq(capture_field(proof, "queryIndex"), Json(1))
  object_fields_unchecked_v3(proof)["queryIndex"] = Json(0)
  assert_false(
    verify_relation_classification_v4(history, report, categories=["INT"]),
  )
}

///|
test "relation classification 49 missing first write predecessor leaves later own read unknown" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "A1", Some("missing")),
    rpg_read("A", "1", Some("v0")),
  ]
  rpg_commit(body, "A")
  let report = rcl_report(rcl_history(body), categories=["INT"])
  assert_eq(capture_field(rcl_rule(report, "INT"), "status"), Json("unknown"))
  assert_eq(capture_field(rcl_rule(report, "INT"), "evidence"), Json::null())
}
