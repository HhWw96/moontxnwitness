///|
fn sge_report(
  graph : ScopedDependencyGraphV4,
  context~ : ScopedOrderContextV4 = ScopedDataOnly,
  rule~ : ScopedRuleSetV4 = ElleFixed4e359e5,
  states~ : Int32 = 100000,
  edges~ : Int32 = 1000000,
) -> Json {
  scoped_search_v4_json(
    search_si_extension_v4(
      graph,
      rule_set=rule,
      order_context=context,
      max_states=states,
      max_edge_checks=edges,
    ),
  )
}

///|
fn sge_separated_cycle() -> ScopedDependencyGraphV4 {
  sgt_graph(
    [
      ("A", "B", ScopedWRItem),
      ("B", "C", ScopedRWItem),
      ("C", "D", ScopedWWPredicate),
      ("D", "A", ScopedRWPredicate),
    ],
    nodes=["A", "B", "C", "D"],
  )
}

///|
test "scoped SI 01 adjacent write skew RW cycle has no I step and is allowed by Ext" {
  let graph = sgt_graph([
    ("A", "B", ScopedRWItem),
    ("B", "A", ScopedRWPredicate),
  ])
  assert_true(sgt_hit(graph, ScopedG2))
  assert_eq(
    capture_field(sge_report(graph), "status"),
    Json("checked-compatible"),
  )
  assert_eq(
    v4_test_at(sge_report(graph), ["execution", "virtualArcs"]),
    Json(0),
  )
}

///|
test "scoped SI 02 literal I then A generates a self loop with both original edges" {
  let graph = sgt_graph([
    ("A", "B", ScopedWRPredicate),
    ("B", "A", ScopedRWItem),
  ])
  let report = sge_report(graph)
  assert_eq(capture_field(report, "status"), Json("refuted"))
  let derived_steps = v3_test_items(
    v4_test_at(report, ["witness"]),
    "virtualSteps",
  )
  assert_eq(derived_steps.length(), 1)
  assert_eq(capture_field(derived_steps[0], "from"), Json("A"))
  assert_eq(capture_field(derived_steps[0], "to"), Json("A"))
  assert_eq(v3_test_items(derived_steps[0], "originalSteps").length(), 2)
  assert_eq(capture_field(derived_steps[0], "composition"), Json("I;A"))
}

///|
test "scoped SI 03 two separated anti dependencies create a two arc Ext cycle" {
  let report = sge_report(sge_separated_cycle())
  assert_eq(capture_field(report, "status"), Json("refuted"))
  assert_eq(
    v3_test_items(v4_test_at(report, ["witness"]), "virtualSteps").length(),
    2,
  )
  assert_eq(v3_test_items(v4_test_at(report, ["witness"]), "steps").length(), 4)
  assert_eq(
    v4_test_at(report, ["witness", "antiDependencies", "cyclicallyAdjacent"]),
    Json(false),
  )
}

///|
test "scoped SI 04 sequential extension does not transitively cross two A steps" {
  let graph = sgt_graph([
    ("A", "B", ScopedWRItem),
    ("B", "C", ScopedRWItem),
    ("C", "A", ScopedRWPredicate),
  ])
  assert_true(sgt_hit(graph, ScopedG2))
  assert_eq(
    capture_field(sge_report(graph), "status"),
    Json("checked-compatible"),
  )
}

///|
test "scoped SI 05 a dependency only cycle is still rejected" {
  let graph = sgt_graph([
    ("A", "B", ScopedWWItem),
    ("B", "A", ScopedWRPredicate),
  ])
  let report = sge_report(graph)
  assert_eq(capture_field(report, "status"), Json("refuted"))
  assert_eq(v4_test_at(report, ["witness", "specificCategory"]), Json("G1c"))
}

///|
test "scoped SI 06 process order enters I only in explicitly selected process context" {
  let graph = sgt_graph(
    [("B", "A", ScopedRWItem)],
    orders=[sgt_order("p", "A", "B", ScopedProcess)],
    process_complete=true,
  )
  assert_eq(
    capture_field(sge_report(graph), "status"),
    Json("checked-compatible"),
  )
  assert_eq(
    capture_field(sge_report(graph, context=ScopedWithProcess), "status"),
    Json("refuted"),
  )
  assert_eq(
    capture_field(sge_report(graph, context=ScopedWithRealtime), "status"),
    Json("unknown"),
  )
}

///|
test "scoped SI 07 realtime order uses explicit original order references" {
  let graph = sgt_graph(
    [("B", "A", ScopedRWPredicate)],
    orders=[sgt_order("r", "A", "B", ScopedRealtime)],
    realtime_complete=true,
  )
  let report = sge_report(graph, context=ScopedWithRealtime)
  assert_eq(capture_field(report, "status"), Json("refuted"))
  assert_eq(
    v4_test_at(report, ["witness", "specificCategory"]),
    Json("G-single-realtime"),
  )
  let steps = v3_test_items(v4_test_at(report, ["witness"]), "steps")
  assert_eq(capture_field(steps[0], "kind"), Json("realtime"))
  assert_eq(
    v4_test_at(steps[0], ["fromOriginal", "observation", "tx"]),
    Json("A"),
  )
}

///|
test "scoped SI 08 edge budget zero cannot build or prove an extension edge" {
  let graph = sgt_graph([("A", "B", ScopedWRItem), ("B", "A", ScopedRWItem)])
  let report = sge_report(graph, edges=0)
  assert_eq(capture_field(report, "status"), Json("unknown"))
  assert_eq(v4_test_at(report, ["execution", "edgeChecks"]), Json(0))
}

///|
test "scoped SI 09 immediate derived self loop is already a proof without a DFS state allowance" {
  let graph = sgt_graph([("A", "B", ScopedWRItem), ("B", "A", ScopedRWItem)])
  let report = sge_report(graph, states=0)
  assert_eq(capture_field(report, "status"), Json("refuted"))
  assert_eq(v4_test_at(report, ["execution", "states"]), Json(0))
  assert_true(
    verify_si_extension_v4(
      graph,
      report,
      rule_set=ElleFixed4e359e5,
      max_states=0,
    ),
  )
}

///|
test "scoped SI 10 exact positive budgets pass and smaller ones are unknown" {
  let graph = sge_separated_cycle()
  let full = sge_report(graph)
  let states = match v4_test_at(full, ["execution", "states"]) {
    Number(n, ..) => n.to_int()
    _ => 0
  }
  let edges = match v4_test_at(full, ["execution", "edgeChecks"]) {
    Number(n, ..) => n.to_int()
    _ => 0
  }
  assert_eq(
    capture_field(sge_report(graph, states~, edges~), "status"),
    Json("refuted"),
  )
  assert_eq(
    capture_field(sge_report(graph, states=states - 1, edges~), "status"),
    Json("unknown"),
  )
  assert_eq(
    capture_field(sge_report(graph, states~, edges=edges - 1), "status"),
    Json("unknown"),
  )
}

///|
test "scoped SI 11 incomplete source context cannot hide a positive extension proof" {
  let graph = sgt_graph(
    [("A", "B", ScopedWRItem), ("B", "A", ScopedRWItem)],
    data_complete=false,
  )
  assert_eq(capture_field(sge_report(graph), "status"), Json("refuted"))
  assert_eq(
    capture_field(sge_report(sgt_graph([], data_complete=false)), "status"),
    Json("unknown"),
  )
}

///|
test "scoped SI 12 derived_steps composition intermediate source identity is verified" {
  let graph = sgt_graph([
    ("A", "B", ScopedWRPredicate),
    ("B", "A", ScopedRWItem),
  ])
  let report = sge_report(graph)
  let arc = v3_test_items(v4_test_at(report, ["witness"]), "virtualSteps")[0]
  let original = v3_test_items(arc, "originalSteps")
  object_fields_unchecked_v3(original[0])["to"] = Json("C")
  assert_false(verify_si_extension_v4(graph, report, rule_set=ElleFixed4e359e5))
}

///|
test "scoped SI 13 caller rules and context never come from the report" {
  let graph = sge_separated_cycle()
  let report = sge_report(graph)
  assert_true(verify_si_extension_v4(graph, report, rule_set=ElleFixed4e359e5))
  assert_false(verify_si_extension_v4(graph, report, rule_set=Adya2000Mixed))
  assert_false(
    verify_si_extension_v4(
      graph,
      report,
      rule_set=ElleFixed4e359e5,
      order_context=ScopedWithProcess,
    ),
  )
  assert_false(
    verify_si_extension_v4(
      graph,
      report,
      rule_set=ElleFixed4e359e5,
      max_edge_checks=0,
    ),
  )
}

///|
test "scoped SI 14 original I edge takes provenance priority over an equal I A projection" {
  let graph = sgt_graph([
    ("A", "B", ScopedWRItem),
    ("B", "C", ScopedRWPredicate),
    ("A", "C", ScopedWRPredicate),
    ("C", "A", ScopedWWItem),
  ])
  let report = sge_report(graph)
  assert_eq(capture_field(report, "status"), Json("refuted"))
  let steps = v3_test_items(v4_test_at(report, ["witness"]), "steps")
  assert_eq(steps.length(), 2)
  assert_eq(capture_field(steps[0], "id"), Json("e2"))
  assert_eq(capture_field(steps[1], "id"), Json("e3"))
}

///|
test "scoped SI 15 invalid input budget is unsupported not an acyclicity result" {
  assert_eq(
    capture_field(sge_report(sgt_graph([]), states=-1), "status"),
    Json("unsupported"),
  )
  assert_eq(
    capture_field(sge_report(sgt_graph([]), edges=1000001), "status"),
    Json("unsupported"),
  )
}

///|
test "scoped SI 16 nested witness edits do not alter original graph or later proofs" {
  let graph = sgt_graph([("A", "B", ScopedWRItem), ("B", "A", ScopedRWItem)])
  let before = scoped_dependency_graph_v4_json(graph)
  let report = sge_report(graph)
  let derived_steps = v3_test_items(
      v4_test_at(report, ["witness"]),
      "virtualSteps",
    )[0]
  object_fields_unchecked_v3(derived_steps)["composition"] = Json(
    "transitive-closure",
  )
  assert_eq(scoped_dependency_graph_v4_json(graph), before)
  assert_false(verify_si_extension_v4(graph, report, rule_set=ElleFixed4e359e5))
  assert_true(
    verify_si_extension_v4(graph, sge_report(graph), rule_set=ElleFixed4e359e5),
  )
}
