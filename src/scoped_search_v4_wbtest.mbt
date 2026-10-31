///|
fn sgt_graph(
  input : Array[(String, String, ScopedDataKindV4)],
  nodes~ : Array[String] = ["A", "B", "C"],
  orders~ : Array[ScopedOrderEdgeInputV4] = [],
  data_complete~ : Bool = true,
  process_complete~ : Bool = false,
  realtime_complete~ : Bool = false,
  gaps~ : Array[Json] = [],
) -> ScopedDependencyGraphV4 {
  let edges = input.mapi((position, entry) => {
    (
      {
        id: "e" + position.to_string(),
        from: entry.0,
        to: entry.1,
        kind: entry.2,
        sources: [
          (
            {
              "originalEdge": Json(position),
              "from": Json(entry.0),
              "to": Json(entry.1),
            } : Json),
        ],
      } : ScopedDataEdgeInputV4)
  })
  scoped_dependency_graph_v4(
    nodes,
    edges,
    order_edges=orders,
    data_complete~,
    process_complete~,
    realtime_complete~,
    gaps~,
  ).unwrap()
}

///|
fn sgt_order(
  id : String,
  from : String,
  to : String,
  kind : ScopedOrderKindV4,
  context~ : String = "ctx",
) -> ScopedOrderEdgeInputV4 {
  {
    id,
    from,
    to,
    kind,
    context_id: context,
    from_source: {
      transaction: from,
      observation: { "tx": Json(from), "kind": "commit_ok" },
    },
    to_source: {
      transaction: to,
      observation: { "tx": Json(to), "kind": "begin" },
    },
  }
}

///|
fn sgt_report(
  graph : ScopedDependencyGraphV4,
  category : ScopedCategoryV4,
  rule~ : ScopedRuleSetV4 = Adya2000Mixed,
  context~ : ScopedOrderContextV4 = ScopedDataOnly,
  states~ : Int32 = 100000,
  edges~ : Int32 = 1000000,
) -> Json {
  scoped_search_v4_json(
    search_scoped_category_v4(
      graph,
      category,
      rule_set=rule,
      order_context=context,
      max_states=states,
      max_edge_checks=edges,
    ),
  )
}

///|
fn sgt_hit(
  graph : ScopedDependencyGraphV4,
  category : ScopedCategoryV4,
  rule~ : ScopedRuleSetV4 = Adya2000Mixed,
  context~ : ScopedOrderContextV4 = ScopedDataOnly,
) -> Bool {
  search_scoped_category_v4(
    graph,
    category,
    rule_set=rule,
    order_context=context,
  ).status() ==
  "refuted"
}

///|
fn sgt_categories() -> Array[ScopedCategoryV4] {
  [
    ScopedG0,
    ScopedG1c,
    ScopedG2Item,
    ScopedG2,
    ScopedGSingleItem,
    ScopedGSingle,
    ScopedGNonadjacent,
  ]
}

///|
test "scoped36 01 empty complete graph has no category cycle" {
  let graph = sgt_graph([], nodes=[])
  for category in sgt_categories() {
    assert_eq(
      search_scoped_category_v4(
        graph,
        category,
        rule_set=Adya2000Mixed,
        max_states=0,
        max_edge_checks=0,
      ).status(),
      "checked-compatible",
    )
  }
}

///|
test "scoped36 02 all WW cycle refutes G0 and G1c without fabricating an anti dependency" {
  let graph = sgt_graph([
    ("A", "B", ScopedWWItem),
    ("B", "A", ScopedWWPredicate),
  ])
  assert_true(sgt_hit(graph, ScopedG0))
  assert_true(sgt_hit(graph, ScopedG1c))
  assert_false(sgt_hit(graph, ScopedG2))
  assert_eq(
    v4_test_at(sgt_report(graph, ScopedG1c), ["witness", "specificCategory"]),
    Json("G0"),
  )
}

///|
test "scoped36 03 WR cycle has G1c without G0" {
  let graph = sgt_graph([
    ("A", "B", ScopedWRItem),
    ("B", "A", ScopedWRPredicate),
  ])
  assert_false(sgt_hit(graph, ScopedG0))
  assert_true(sgt_hit(graph, ScopedG1c))
  assert_false(sgt_hit(graph, ScopedG2))
}

///|
test "scoped36 04 a single item RW is single item general single nonadjacent and G2 item" {
  let graph = sgt_graph([
    ("A", "B", ScopedRWItem),
    ("B", "A", ScopedWRPredicate),
  ])
  for
    category in [
      ScopedG2Item,
      ScopedG2,
      ScopedGSingleItem,
      ScopedGSingle,
      ScopedGNonadjacent,
    ] {
    assert_true(sgt_hit(graph, category))
  }
  assert_eq(
    v4_test_at(sgt_report(graph, ScopedGSingle), ["witness", "specificCategory"]),
    Json("G-single-item"),
  )
}

///|
test "scoped36 05 predicate single never implies an item anomaly" {
  let graph = sgt_graph([
    ("A", "B", ScopedRWPredicate),
    ("B", "A", ScopedWWItem),
  ])
  assert_true(sgt_hit(graph, ScopedGSingle))
  assert_false(sgt_hit(graph, ScopedGSingleItem))
  assert_false(sgt_hit(graph, ScopedG2Item))
  let implied = v3_test_items(
    v4_test_at(sgt_report(graph, ScopedG2), ["witness"]),
    "impliedPhenomena",
  )
  assert_false(implied.contains(Json("G2-item")))
}

///|
test "scoped36 06 mixed item predicate cycle explicitly differs between the two G2 item rules" {
  let graph = sgt_graph([
    ("A", "B", ScopedRWItem),
    ("B", "A", ScopedRWPredicate),
  ])
  assert_true(sgt_hit(graph, ScopedG2Item, rule=Adya2000Mixed))
  assert_false(sgt_hit(graph, ScopedG2Item, rule=ElleFixed4e359e5))
  assert_true(sgt_hit(graph, ScopedG2, rule=ElleFixed4e359e5))
  assert_false(sgt_hit(graph, ScopedGSingle))
  assert_false(sgt_hit(graph, ScopedGNonadjacent))
}

///|
test "scoped36 07 two adjacent item RW edges are G2 item but not single or nonadjacent" {
  let graph = sgt_graph([("A", "B", ScopedRWItem), ("B", "A", ScopedRWItem)])
  assert_true(sgt_hit(graph, ScopedG2Item))
  assert_false(sgt_hit(graph, ScopedGSingle))
  assert_false(sgt_hit(graph, ScopedGNonadjacent))
}

///|
test "scoped36 08 first and last RW edges are adjacent across the ring boundary" {
  let graph = sgt_graph([
    ("A", "B", ScopedRWItem),
    ("B", "C", ScopedWRItem),
    ("C", "A", ScopedRWPredicate),
  ])
  assert_true(sgt_hit(graph, ScopedG2))
  assert_false(sgt_hit(graph, ScopedGNonadjacent))
}

///|
test "scoped36 09 four node separated RW edges form a nonadjacent witness" {
  let graph = sgt_graph(
    [
      ("A", "B", ScopedWRItem),
      ("B", "C", ScopedRWItem),
      ("C", "D", ScopedWWPredicate),
      ("D", "A", ScopedRWPredicate),
    ],
    nodes=["A", "B", "C", "D"],
  )
  assert_true(sgt_hit(graph, ScopedGNonadjacent))
  assert_false(sgt_hit(graph, ScopedGSingle))
  assert_eq(
    v4_test_at(sgt_report(graph, ScopedGNonadjacent), [
      "witness", "antiDependencies", "total",
    ]),
    Json(2),
  )
}

///|
test "scoped36 10 a shorter all WW component cannot hide another component target anomaly" {
  let graph = sgt_graph(
    [
      ("A", "B", ScopedWWItem),
      ("B", "A", ScopedWWItem),
      ("C", "D", ScopedRWPredicate),
      ("D", "E", ScopedWRItem),
      ("E", "C", ScopedWWItem),
    ],
    nodes=["A", "B", "C", "D", "E"],
  )
  let report = sgt_report(graph, ScopedGSingle)
  assert_eq(capture_field(report, "status"), Json("refuted"))
  assert_eq(
    v4_test_at(report, ["witness", "vertices"]),
    Json(["C", "D", "E", "C"]),
  )
}

///|
test "scoped36 11 parallel relationships preserve both WR and RW path choices" {
  let graph = sgt_graph([
    ("A", "B", ScopedWRItem),
    ("A", "B", ScopedRWPredicate),
    ("B", "A", ScopedWWItem),
  ])
  assert_true(sgt_hit(graph, ScopedG1c))
  assert_true(sgt_hit(graph, ScopedGSingle))
  assert_false(sgt_hit(graph, ScopedG0))
  let steps = v3_test_items(
    v4_test_at(sgt_report(graph, ScopedGSingle), ["witness"]),
    "steps",
  )
  assert_eq(capture_field(steps[0], "id"), Json("e1"))
  assert_eq(capture_field(steps[0], "kind"), Json("rw-predicate"))
}

///|
test "scoped36 12 actual predicate WR on the return path does not turn item single into predicate single" {
  let graph = sgt_graph([
    ("A", "B", ScopedRWItem),
    ("B", "A", ScopedWRPredicate),
  ])
  assert_eq(
    v4_test_at(sgt_report(graph, ScopedGSingle), ["witness", "specificCategory"]),
    Json("G-single-item"),
  )
}

///|
test "scoped36 13 missing provenance is excluded and negative checking remains unknown" {
  let graph = scoped_dependency_graph_v4(["A", "B"], [
    { id: "bad", from: "A", to: "B", kind: ScopedWWItem, sources: [], },
    {
      id: "good",
      from: "B",
      to: "A",
      kind: ScopedWWItem,
      sources: [Json("declared")],
    },
  ]).unwrap()
  assert_eq(
    search_scoped_category_v4(graph, ScopedG0, rule_set=Adya2000Mixed).status(),
    "unknown",
  )
  assert_eq(graph.edges.length(), 1)
}

///|
test "scoped36 14 an unrelated missing edge cannot erase an already supported cycle" {
  let graph = scoped_dependency_graph_v4(["A", "B", "C"], [
    { id: "ab", from: "A", to: "B", kind: ScopedWWItem, sources: [Json("ab")], },
    { id: "ba", from: "B", to: "A", kind: ScopedWWItem, sources: [Json("ba")], },
    { id: "bad", from: "C", to: "A", kind: ScopedRWItem, sources: [], },
  ]).unwrap()
  assert_true(sgt_hit(graph, ScopedG0))
  assert_false(graph.data_complete)
}

///|
test "scoped36 15 coverage gaps prevent a compatible conclusion but preserve positive witnesses" {
  let gap : Json = { "code": "incomplete-window" }
  assert_eq(
    search_scoped_category_v4(
      sgt_graph([], gaps=[gap]),
      ScopedG0,
      rule_set=Adya2000Mixed,
    ).status(),
    "unknown",
  )
  assert_true(
    sgt_hit(
      sgt_graph([("A", "B", ScopedWWItem), ("B", "A", ScopedWWItem)], gaps=[gap]),
      ScopedG0,
    ),
  )
}

///|
test "scoped36 16 no state allowance cannot become a negative cycle answer" {
  let report = sgt_report(
    sgt_graph([("A", "B", ScopedWWItem), ("B", "A", ScopedWWItem)]),
    ScopedG0,
    states=0,
  )
  assert_eq(capture_field(report, "status"), Json("unknown"))
  assert_eq(v4_test_at(report, ["execution", "states"]), Json(0))
}

///|
test "scoped36 17 no edge allowance does not overshoot the caller budget" {
  let report = sgt_report(
    sgt_graph([("A", "B", ScopedWWItem), ("B", "A", ScopedWWItem)]),
    ScopedG0,
    edges=0,
  )
  assert_eq(capture_field(report, "status"), Json("unknown"))
  assert_eq(v4_test_at(report, ["execution", "edgeChecks"]), Json(0))
}

///|
test "scoped36 18 exact positive budgets pass and one less remains unknown" {
  let graph = sgt_graph([("A", "B", ScopedWWItem), ("B", "A", ScopedWWItem)], nodes=[
    "A", "B",
  ])
  let full = sgt_report(graph, ScopedG0)
  let states = match v4_test_at(full, ["execution", "states"]) {
    Number(n, ..) => n.to_int()
    _ => 0
  }
  let edges = match v4_test_at(full, ["execution", "edgeChecks"]) {
    Number(n, ..) => n.to_int()
    _ => 0
  }
  assert_eq(
    capture_field(sgt_report(graph, ScopedG0, states~, edges~), "status"),
    Json("refuted"),
  )
  assert_eq(
    capture_field(
      sgt_report(graph, ScopedG0, states=states - 1, edges~),
      "status",
    ),
    Json("unknown"),
  )
  assert_eq(
    capture_field(
      sgt_report(graph, ScopedG0, states~, edges=edges - 1),
      "status",
    ),
    Json("unknown"),
  )
}

///|
test "scoped36 19 invalid budgets are unsupported rather than compatible" {
  let graph = sgt_graph([])
  assert_eq(
    capture_field(sgt_report(graph, ScopedG0, states=100001), "status"),
    Json("unsupported"),
  )
  assert_eq(
    capture_field(sgt_report(graph, ScopedG0, edges=-1), "status"),
    Json("unsupported"),
  )
}

///|
test "scoped36 20 graph construction detaches caller nodes edges and source objects" {
  let source : Json = { "original": "before" }
  let nodes = ["A", "B"]
  let input : Array[ScopedDataEdgeInputV4] = [
    { id: "ab", from: "A", to: "B", kind: ScopedWWItem, sources: [source], },
    { id: "ba", from: "B", to: "A", kind: ScopedWWItem, sources: [Json("ba")], },
  ]
  let graph = scoped_dependency_graph_v4(nodes, input).unwrap()
  let before = scoped_dependency_graph_v4_json(graph)
  object_fields_unchecked_v3(source)["original"] = Json("after")
  nodes.clear()
  input.clear()
  assert_eq(scoped_dependency_graph_v4_json(graph), before)
  assert_true(sgt_hit(graph, ScopedG0))
}

///|
test "scoped36 21 witness category rule context source hash and budgets cannot be tampered" {
  let graph = sgt_graph([("A", "B", ScopedRWItem), ("B", "A", ScopedWRItem)])
  for field in ["category", "rule", "context", "source", "step", "budget"] {
    let report = sgt_report(graph, ScopedGSingle)
    let fields = object_fields_unchecked_v3(report)
    match field {
      "category" => fields["requestedCategory"] = Json("G0")
      "rule" => fields["ruleSet"] = Json("other")
      "context" => fields["orderContext"] = Json("realtime")
      "source" => fields["sourceGraphSha256"] = Json("fake")
      "step" =>
        object_fields_unchecked_v3(
          v3_test_items(v4_test_at(report, ["witness"]), "steps")[0],
        )["id"] = Json("fake")
      _ =>
        object_fields_unchecked_v3(v4_test_at(report, ["execution", "limits"]))["states"] = Json(
          99999,
        )
    }
    assert_false(
      verify_scoped_category_v4(
        graph,
        report,
        ScopedGSingle,
        rule_set=Adya2000Mixed,
      ),
    )
  }
}

///|
test "scoped36 22 verifier never accepts report supplied rule or larger budgets" {
  let graph = sgt_graph([
    ("A", "B", ScopedRWItem),
    ("B", "A", ScopedRWPredicate),
  ])
  let report = sgt_report(graph, ScopedG2Item)
  assert_true(
    verify_scoped_category_v4(
      graph,
      report,
      ScopedG2Item,
      rule_set=Adya2000Mixed,
    ),
  )
  assert_false(
    verify_scoped_category_v4(
      graph,
      report,
      ScopedG2Item,
      rule_set=ElleFixed4e359e5,
    ),
  )
  assert_false(
    verify_scoped_category_v4(
      graph,
      report,
      ScopedG2Item,
      rule_set=Adya2000Mixed,
      max_states=0,
    ),
  )
}

///|
test "scoped36 23 changing an unused edge source changes the bound entire input" {
  let first = sgt_graph([
    ("A", "B", ScopedWWItem),
    ("B", "A", ScopedWWItem),
    ("A", "C", ScopedWRItem),
  ])
  let report = sgt_report(first, ScopedG0)
  let input : Array[ScopedDataEdgeInputV4] = [
    ("A", "B", ScopedWWItem),
    ("B", "A", ScopedWWItem),
    ("A", "C", ScopedWRItem),
  ].mapi((i, e) => {
    (
      {
        id: "e" + i.to_string(),
        from: e.0,
        to: e.1,
        kind: e.2,
        sources: [
          (
            { "originalEdge": Json(i), "from": Json(e.0), "to": Json(e.1) } :
            Json),
        ],
      } : ScopedDataEdgeInputV4)
  })
  input[2].sources[0] = Json("changed unrelated source")
  let second = scoped_dependency_graph_v4(["A", "B", "C"], input).unwrap()
  assert_false(first.input_sha256() == second.input_sha256())
  assert_false(
    verify_scoped_category_v4(second, report, ScopedG0, rule_set=Adya2000Mixed),
  )
}

///|
test "scoped36 24 explicit process order refutes only its augmented context" {
  let graph = sgt_graph(
    [("B", "A", ScopedWWItem)],
    orders=[sgt_order("p", "A", "B", ScopedProcess)],
    process_complete=true,
  )
  assert_false(sgt_hit(graph, ScopedG0))
  let report = sgt_report(graph, ScopedG0, context=ScopedWithProcess)
  assert_eq(capture_field(report, "status"), Json("refuted"))
  assert_eq(
    v4_test_at(report, ["witness", "specificCategory"]),
    Json("G0-process"),
  )
}

///|
test "scoped36 25 an async or unspecified process relation never promotes itself into realtime" {
  let graph = sgt_graph(
    [("B", "A", ScopedWWItem)],
    orders=[sgt_order("p", "A", "B", ScopedProcess)],
    process_complete=true,
  )
  assert_eq(
    capture_field(
      sgt_report(graph, ScopedG0, context=ScopedWithRealtime),
      "status",
    ),
    Json("unknown"),
  )
  let implied = v3_test_items(
    v4_test_at(sgt_report(graph, ScopedG0, context=ScopedWithProcess), [
      "witness",
    ]),
    "impliedPhenomena",
  )
  assert_false(implied.contains(Json("G0-realtime")))
}

///|
test "scoped36 26 explicitly supplied realtime source stays separate from process" {
  let graph = sgt_graph(
    [("B", "A", ScopedWWItem)],
    orders=[sgt_order("r", "A", "B", ScopedRealtime)],
    realtime_complete=true,
  )
  assert_true(sgt_hit(graph, ScopedG0, context=ScopedWithRealtime))
  assert_false(sgt_hit(graph, ScopedG0, context=ScopedWithProcess))
  assert_eq(
    v4_test_at(sgt_report(graph, ScopedG0, context=ScopedWithRealtime), [
      "witness", "specificCategory",
    ]),
    Json("G0-realtime"),
  )
}

///|
test "scoped36 27 missing process completeness affects process but not data results" {
  let graph = sgt_graph([], orders=[])
  assert_eq(
    capture_field(sgt_report(graph, ScopedG0), "status"),
    Json("checked-compatible"),
  )
  assert_eq(
    capture_field(
      sgt_report(graph, ScopedG0, context=ScopedWithProcess),
      "status",
    ),
    Json("unknown"),
  )
}

///|
test "scoped36 28 wrong original order transaction is excluded and cannot refute" {
  let source = sgt_order("p", "A", "B", ScopedProcess)
  let invalid : ScopedOrderEdgeInputV4 = {
    ..source,
    from_source: { transaction: "wrong", observation: { "tx": "wrong" }, },
  }
  let graph = sgt_graph(
    [("B", "A", ScopedWWItem)],
    orders=[invalid],
    process_complete=true,
  )
  assert_eq(
    capture_field(
      sgt_report(graph, ScopedG0, context=ScopedWithProcess),
      "status",
    ),
    Json("unknown"),
  )
  assert_eq(graph.edges.length(), 1)
}

///|
test "scoped36 29 pure inconsistent process cycles are source gaps rather than G0" {
  let graph = sgt_graph(
    [],
    orders=[
      sgt_order("p1", "A", "B", ScopedProcess),
      sgt_order("p2", "B", "A", ScopedProcess),
    ],
    process_complete=true,
  )
  assert_eq(
    capture_field(
      sgt_report(graph, ScopedG0, context=ScopedWithProcess),
      "status",
    ),
    Json("unknown"),
  )
  assert_true(graph.edges.is_empty())
}

///|
test "scoped36 30 duplicate edge IDs and unknown endpoints are rejected" {
  let source : Array[Json] = [Json("declared")]
  assert_true(
    scoped_dependency_graph_v4(["A", "B"], [
      { id: "same", from: "A", to: "B", kind: ScopedWWItem, sources: source, },
      { id: "same", from: "B", to: "A", kind: ScopedWWItem, sources: source, },
    ])
    is Err(_),
  )
  assert_true(
    scoped_dependency_graph_v4(["A"], [
      { id: "e", from: "A", to: "B", kind: ScopedWWItem, sources: source, },
    ])
    is Err(_),
  )
}

///|
test "scoped36 31 primitive self edges are rejected while virtual extension self loops are supported separately" {
  assert_true(
    scoped_dependency_graph_v4(["A"], [
      {
        id: "self",
        from: "A",
        to: "A",
        kind: ScopedWWItem,
        sources: [Json("s")],
      },
    ])
    is Err(_),
  )
}

///|
test "scoped36 32 report mutation cannot modify an already constructed graph" {
  let graph = sgt_graph([("A", "B", ScopedWWItem), ("B", "A", ScopedWWItem)])
  let before = scoped_dependency_graph_v4_json(graph)
  let report = sgt_report(graph, ScopedG0)
  let proof = v3_test_items(
      v3_test_items(v4_test_at(report, ["witness"]), "steps")[0],
      "sources",
    )[0]
  object_fields_unchecked_v3(proof)["from"] = Json("changed")
  assert_eq(scoped_dependency_graph_v4_json(graph), before)
  assert_true(
    verify_scoped_category_v4(
      graph,
      sgt_report(graph, ScopedG0),
      ScopedG0,
      rule_set=Adya2000Mixed,
    ),
  )
}

///|
test "scoped36 33 pure data refutation survives missing order context facts" {
  let graph = sgt_graph([("A", "B", ScopedWWItem), ("B", "A", ScopedWWItem)])
  assert_true(sgt_hit(graph, ScopedG0, context=ScopedWithProcess))
  assert_true(sgt_hit(graph, ScopedG0, context=ScopedWithRealtime))
}

///|
test "scoped36 34 explicit process and realtime opposite edges do not imply a contradiction without nonoverlap applicability" {
  let graph = sgt_graph(
    [],
    orders=[
      sgt_order("p", "A", "B", ScopedProcess),
      sgt_order("r", "B", "A", ScopedRealtime),
    ],
    process_complete=true,
    realtime_complete=true,
  )
  assert_eq(graph.edges.length(), 2)
  assert_eq(
    capture_field(
      sgt_report(graph, ScopedG0, context=ScopedWithProcess),
      "status",
    ),
    Json("checked-compatible"),
  )
  assert_eq(
    capture_field(
      sgt_report(graph, ScopedG0, context=ScopedWithRealtime),
      "status",
    ),
    Json("checked-compatible"),
  )
}

///|
test "scoped36 35 delimiter identities do not collide in structured endpoint indexes" {
  let graph = sgt_graph(
    [("A|B", "C", ScopedWWItem), ("C", "A|B", ScopedWWItem)],
    nodes=["A|B", "C", "A", "B|C"],
  )
  assert_true(sgt_hit(graph, ScopedG0))
  assert_eq(
    v4_test_at(sgt_report(graph, ScopedG0), ["witness", "vertices"]),
    Json(["A|B", "C", "A|B"]),
  )
}

///|
test "scoped36 36 inconsistent process context does not erase an independent sourced process refutation" {
  let graph = sgt_graph(
    [("D", "C", ScopedWWItem)],
    nodes=["A", "B", "C", "D"],
    orders=[
      sgt_order("p1", "A", "B", ScopedProcess, context="bad"),
      sgt_order("p2", "B", "A", ScopedProcess, context="bad"),
      sgt_order("p3", "C", "D", ScopedProcess, context="good"),
    ],
    process_complete=true,
  )
  assert_false(graph.process_complete)
  assert_true(sgt_hit(graph, ScopedG0, context=ScopedWithProcess))
  assert_eq(
    v4_test_at(sgt_report(graph, ScopedG0, context=ScopedWithProcess), [
      "witness", "vertices",
    ]),
    Json(["C", "D", "C"]),
  )
}

///|
test "scoped36 37 inconsistent realtime component does not erase an independent sourced realtime refutation" {
  let graph = sgt_graph(
    [("D", "C", ScopedWWItem)],
    nodes=["A", "B", "C", "D"],
    orders=[
      sgt_order("r1", "A", "B", ScopedRealtime),
      sgt_order("r2", "B", "A", ScopedRealtime),
      sgt_order("r3", "C", "D", ScopedRealtime),
    ],
    realtime_complete=true,
  )
  assert_false(graph.realtime_complete)
  assert_true(sgt_hit(graph, ScopedG0, context=ScopedWithRealtime))
}

///|
test "scoped36 38 actual overlapping process records and an empty complete realtime relation stay separate" {
  let order : ScopedOrderEdgeInputV4 = {
    id: "p",
    from: "A",
    to: "B",
    kind: ScopedProcess,
    context_id: "logical-session",
    from_source: {
      transaction: "A",
      observation: {
        "tx": "A",
        "clockDomain": "clock",
        "invoke": 0,
        "return": 10,
      },
    },
    to_source: {
      transaction: "B",
      observation: {
        "tx": "B",
        "clockDomain": "clock",
        "invoke": 1,
        "return": 2,
      },
    },
  }
  let graph = sgt_graph(
    [("B", "A", ScopedWWItem)],
    orders=[order],
    process_complete=true,
    realtime_complete=true,
  )
  assert_true(sgt_hit(graph, ScopedG0, context=ScopedWithProcess))
  assert_eq(
    capture_field(
      sgt_report(graph, ScopedG0, context=ScopedWithRealtime),
      "status",
    ),
    Json("checked-compatible"),
  )
}

///|
test "scoped36 39 input fingerprint is stable across source object key insertion orders" {
  let first : Json = { "alpha": 1, "omega": 2 }
  let fields : Map[String, Json] = Map([])
  fields["omega"] = Json(2)
  fields["alpha"] = Json(1)
  let second = Json::object(fields)
  let a = scoped_dependency_graph_v4(["A", "B"], [
    { id: "e", from: "A", to: "B", kind: ScopedWWItem, sources: [first], },
  ]).unwrap()
  let b = scoped_dependency_graph_v4(["A", "B"], [
    { id: "e", from: "A", to: "B", kind: ScopedWWItem, sources: [second], },
  ]).unwrap()
  assert_eq(a.input_sha256(), b.input_sha256())
}

///|
test "scoped36 40 an unbound order source stays unknown while DataOnly remains unaffected" {
  let order = sgt_order("p", "A", "B", ScopedProcess)
  let invalid : ScopedOrderEdgeInputV4 = {
    ..order,
    from_source: { transaction: "A", observation: Json::null(), },
  }
  let graph = sgt_graph(
    [("B", "A", ScopedWWItem)],
    orders=[invalid],
    process_complete=true,
  )
  assert_eq(
    capture_field(
      sgt_report(graph, ScopedG0, context=ScopedWithProcess),
      "status",
    ),
    Json("unknown"),
  )
  assert_eq(
    capture_field(sgt_report(graph, ScopedG0), "status"),
    Json("checked-compatible"),
  )
}

///|
test "scoped36 41 a 128 node cycle retains all sources and one exact anti dependency" {
  let nodes : Array[String] = []
  let edges : Array[(String, String, ScopedDataKindV4)] = []
  for node in 0..<128 {
    nodes.push("T" + node.to_string())
  }
  for node in 0..<128 {
    edges.push(
      (
        nodes[node],
        nodes[(node + 1) % 128],
        if node == 127 {
          ScopedRWItem
        } else {
          ScopedWWItem
        },
      ),
    )
  }
  let graph = sgt_graph(edges, nodes~)
  let result = sgt_report(graph, ScopedGSingleItem)
  assert_eq(capture_field(result, "status"), Json("refuted"))
  assert_eq(
    v3_test_items(v4_test_at(result, ["witness"]), "steps").length(),
    128,
  )
  assert_eq(
    v4_test_at(result, ["witness", "antiDependencies", "total"]),
    Json(1),
  )
  assert_eq(capture_field(sge_report(graph), "status"), Json("refuted"))
}

///|
test "scoped36 42 graph node capacity is checked without changing exact interpreter limits" {
  let nodes : Array[String] = []
  for node in 0..<129 {
    nodes.push("T" + node.to_string())
  }
  assert_true(scoped_dependency_graph_v4(nodes, []) is Err(_))
}

///|
test "scoped36 43 a witness retains every supplied source for its selected relationship" {
  let graph = scoped_dependency_graph_v4(["A", "B"], [
    {
      id: "ab",
      from: "A",
      to: "B",
      kind: ScopedWWItem,
      sources: [Json("source-one"), Json("source-two")],
    },
    {
      id: "ba",
      from: "B",
      to: "A",
      kind: ScopedWWItem,
      sources: [Json("return")],
    },
  ]).unwrap()
  let steps = v3_test_items(
    v4_test_at(sgt_report(graph, ScopedG0), ["witness"]),
    "steps",
  )
  assert_eq(
    capture_field(steps[0], "sources"),
    Json(["source-one", "source-two"]),
  )
}

///|
test "scoped36 44 caller edits to original process records cannot alter constructed proofs" {
  let order = sgt_order("p", "A", "B", ScopedProcess)
  let graph = sgt_graph(
    [("B", "A", ScopedWWItem)],
    orders=[order],
    process_complete=true,
  )
  let before = scoped_dependency_graph_v4_json(graph)
  object_fields_unchecked_v3(order.from_source.observation)["tx"] = Json(
    "changed",
  )
  assert_eq(scoped_dependency_graph_v4_json(graph), before)
  assert_true(sgt_hit(graph, ScopedG0, context=ScopedWithProcess))
}

///|
test "scoped36 45 source key canonicalization uses declared Unicode scalar order" {
  let fields : Map[String, Json] = Map([])
  fields["𝄞"] = Json("high")
  fields["\ue000"] = Json("low")
  let out = StringBuilder()
  scoped_sorted_json_v4(Json::object(fields), out)
  assert_eq(out.to_string(), "{\"\ue000\":\"low\",\"𝄞\":\"high\"}")
  let graph = sgt_graph(
    [("甲", "𝄞", ScopedWWItem), ("𝄞", "甲", ScopedWWItem)],
    nodes=["甲", "𝄞"],
  )
  assert_true(sgt_hit(graph, ScopedG0))
}
