///|
fn gs_test_transactions(count : Int32) -> Array[Transaction] {
  Array::makei(count, index => tx(index.to_string(), []))
}

///|
fn gs_test_budget(
  max_states~ : Int32 = 100000,
  max_edges~ : Int32 = 1000000,
) -> ClassificationV3Budget {
  {
    max_states,
    max_edge_checks: max_edges,
    states: 0,
    edge_checks: 0,
    limited: false,
    reason: "complete",
  }
}

///|
fn gs_test_single_history() -> History {
  hist(
    [
      tx("A", [read_op("x", "x0"), read_op("y", "y1")]),
      tx("B", [write_op("x", "x1"), write_op("y", "y1")]),
    ],
    orders={ "x": ["x0", "x1"], "y": ["y0", "y1"] },
  )
}

///|
fn gs_test_rule(report : Json, category : String) -> Json {
  v4_test_at(report, ["judgment", "rules", category])
}

///|
fn gs_test_validate_cycle(
  input : Array[Edge],
  cycle : Array[Edge],
) -> Unit raise {
  assert_true(cycle.length() >= 2)
  assert_eq(cycle.filter(edge => edge.kind == RW).length(), 1)
  assert_true(
    cycle.all(edge => edge.kind == RW || edge.kind == WR || edge.kind == WW),
  )
  let seen : Map[String, Bool] = Map([])
  for index, edge in cycle {
    assert_true(input.contains(edge))
    assert_false(seen.contains(edge.from))
    seen[edge.from] = true
    assert_eq(edge.to, cycle[(index + 1) % cycle.length()].from)
  }
}

///|
/// Independent oracle: enumerate every simple two/three-node cycle and each
/// possible position of its one RW. Pair masks retain all parallel edge kinds.
fn gs_test_oracle(masks : Array[Int32]) -> Bool {
  let pairs = [(0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1)]
  let matrix = FixedArray::make(9, 0)
  for index, pair in pairs {
    matrix[pair.0 * 3 + pair.1] = masks[index]
  }
  for a in 0..<3 {
    for b in 0..<3 {
      if a == b {
        continue
      }
      for
        cycle in [
          [matrix[a * 3 + b], matrix[b * 3 + a]],
          [
            matrix[a * 3 + b],
            matrix[b * 3 + (3 - a - b)],
            matrix[(3 - a - b) * 3 + a],
          ],
        ] {
        for rw_index in 0..<cycle.length() {
          let mut valid = true
          for index, mask in cycle {
            if index == rw_index {
              if (mask & 4) == 0 {
                valid = false
              }
            } else if (mask & 3) == 0 {
              valid = false
            }
          }
          if valid {
            return true
          }
        }
      }
    }
  }
  false
}

///|
fn gs_test_edges(masks : Array[Int32]) -> Array[Edge] {
  let pairs = [(0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1)]
  let result : Array[Edge] = []
  for index, pair in pairs {
    for kind in [WW, WR, RW, RT] {
      let bit = match kind {
        WW => 1
        WR => 2
        RW => 4
        RT => 8
      }
      if (masks[index] & bit) != 0 {
        result.push(classification_test_edge(pair.0, pair.1, kind))
      }
    }
  }
  result
}

///|
test "G-single 01 all 4096 simple three-node graphs match an independent oracle" {
  let transactions = gs_test_transactions(3)
  for code in 0..<4096 {
    let mut remainder = code
    let masks : Array[Int32] = []
    for _ in 0..<6 {
      masks.push(
        match remainder % 4 {
          0 => 0
          1 => 1
          2 => 2
          _ => 4
        },
      )
      remainder /= 4
    }
    let edges = gs_test_edges(masks)
    let budget = gs_test_budget()
    let cycle = g_single_cycle_v4(
      3,
      edges,
      adjacency(transactions, edges),
      budget,
    )
    assert_eq(!cycle.is_empty(), gs_test_oracle(masks))
    assert_false(budget.limited)
    if !cycle.is_empty() {
      gs_test_validate_cycle(edges, cycle)
    }
  }
}

///|
test "G-single 02 fixed multigraphs retain parallel choices and exclude RT" {
  let transactions = gs_test_transactions(3)
  let mut state = 917L
  for _ in 0..<2048 {
    let masks : Array[Int32] = []
    for _ in 0..<6 {
      state = state * 48271L % 2147483647L
      masks.push(((state >> 8) & 15L).to_int())
    }
    let edges = gs_test_edges(masks)
    let budget = gs_test_budget()
    let cycle = g_single_cycle_v4(
      3,
      edges,
      adjacency(transactions, edges),
      budget,
    )
    assert_eq(!cycle.is_empty(), gs_test_oracle(masks))
    assert_false(budget.limited)
    if !cycle.is_empty() {
      gs_test_validate_cycle(edges, cycle)
    }
  }
}

///|
test "G-single 03 zero one and two anti-dependencies stay distinct" {
  let transactions = gs_test_transactions(3)
  for kinds in [[WW, WR, WW], [RW, WR, WW], [RW, RW, WW], [RW, RW, RW]] {
    let edges = [
      classification_test_edge(0, 1, kinds[0]),
      classification_test_edge(1, 2, kinds[1]),
      classification_test_edge(2, 0, kinds[2]),
    ]
    let cycle = g_single_cycle_v4(
      3,
      edges,
      adjacency(transactions, edges),
      gs_test_budget(),
    )
    assert_eq(!cycle.is_empty(), kinds.filter(kind => kind == RW).length() == 1)
  }
}

///|
test "G-single 04 shorter zero-RW and two-RW cycles cannot hide a one-RW cycle" {
  let transactions = gs_test_transactions(7)
  let edges = [
    classification_test_edge(0, 1, WW),
    classification_test_edge(1, 0, WR),
    classification_test_edge(2, 3, RW),
    classification_test_edge(3, 2, RW),
    classification_test_edge(4, 5, RW),
    classification_test_edge(5, 6, WW),
    classification_test_edge(6, 4, WR),
  ]
  let graph = adjacency(transactions, edges)
  let (shortest, _) = shortest_cycle(transactions, edges)
  assert_eq(shortest.length(), 2)
  let cycle = g_single_cycle_v4(7, edges, graph, gs_test_budget())
  assert_eq(cycle.length(), 3)
  gs_test_validate_cycle(edges, cycle)
  assert_true(cycle.all(edge => ["4", "5", "6"].contains(edge.from)))
}

///|
test "G-single 05 parallel RW and WR edges preserve the legal one-RW witness" {
  let transactions = gs_test_transactions(2)
  let edges = [
    classification_test_edge(0, 1, RW),
    classification_test_edge(1, 0, RW),
    classification_test_edge(1, 0, WR),
  ]
  let cycle = g_single_cycle_v4(
    2,
    edges,
    adjacency(transactions, edges),
    gs_test_budget(),
  )
  assert_true(cycle == [edges[0], edges[2]])
  gs_test_validate_cycle(edges, cycle)
}

///|
test "G-single 06 a later seed is searched after an earlier RW has no return path" {
  let transactions = gs_test_transactions(4)
  let edges = [
    classification_test_edge(0, 1, RW),
    classification_test_edge(2, 3, RW),
    classification_test_edge(3, 2, WW),
  ]
  let cycle = g_single_cycle_v4(
    4,
    edges,
    adjacency(transactions, edges),
    gs_test_budget(),
  )
  assert_true(cycle == [edges[1], edges[2]])
}

///|
test "G-single 07 real-time edges cannot complete a data category cycle" {
  let transactions = gs_test_transactions(2)
  let edges = [
    classification_test_edge(0, 1, RW),
    classification_test_edge(1, 0, RT),
  ]
  let budget = gs_test_budget()
  assert_true(
    g_single_cycle_v4(2, edges, adjacency(transactions, edges), budget).is_empty(),
  )
  assert_false(budget.limited)
}

///|
test "G-single 08 exact witness budget succeeds while either smaller budget is unknown" {
  let transactions = gs_test_transactions(2)
  let edges = [
    classification_test_edge(0, 1, RW),
    classification_test_edge(1, 0, WR),
  ]
  let graph = adjacency(transactions, edges)
  let exact = gs_test_budget(max_states=1, max_edges=2)
  assert_true(g_single_cycle_v4(2, edges, graph, exact) == edges)
  assert_false(exact.limited)
  assert_eq(exact.states, 1)
  assert_eq(exact.edge_checks, 2)
  for
    budget in [
      gs_test_budget(max_states=0, max_edges=2),
      gs_test_budget(max_states=1, max_edges=1),
    ] {
    assert_true(g_single_cycle_v4(2, edges, graph, budget).is_empty())
    assert_true(budget.limited)
    assert_true(budget.states <= budget.max_states)
    assert_true(budget.edge_checks <= budget.max_edge_checks)
  }
}

///|
test "G-single 09 exact exhaustion of a completed no-cycle search is not a timeout" {
  let transactions = gs_test_transactions(2)
  let edges = [classification_test_edge(0, 1, RW)]
  let budget = gs_test_budget(max_states=1, max_edges=1)
  assert_true(
    g_single_cycle_v4(2, edges, adjacency(transactions, edges), budget).is_empty(),
  )
  assert_false(budget.limited)
  assert_eq(budget.states, 1)
  assert_eq(budget.edge_checks, 1)
  let no_rw = [
    classification_test_edge(0, 1, WW),
    classification_test_edge(1, 0, WR),
  ]
  let scan = gs_test_budget(max_states=0, max_edges=2)
  assert_true(
    g_single_cycle_v4(2, no_rw, adjacency(transactions, no_rw), scan).is_empty(),
  )
  assert_false(scan.limited)
}

///|
test "G-single 10 typed classification emits an exact source-bound witness" {
  let snapshot = register_history_v4(gs_test_single_history()).unwrap()
  let result = classify_v4(snapshot, categories=["G-single"])
  let report = classification_v4_json(result)
  assert_eq(result.status(), "refuted")
  let rule = gs_test_rule(report, "G-single")
  assert_eq(capture_field(rule, "status"), Json("refuted"))
  assert_eq(
    v4_test_at(rule, ["evidence", "specificCategory"]),
    Json("G-single-item"),
  )
  assert_eq(v4_test_at(rule, ["evidence", "rwEdgeCount"]), Json(1))
  assert_eq(v4_test_at(rule, ["evidence", "rwScope"]), Json("item"))
  assert_eq(
    v4_test_at(rule, ["evidence", "requestedCategory"]),
    Json("G-single"),
  )
  assert_eq(
    v4_test_at(report, ["judgment", "impliedAnomalies"]),
    Json([
      "G-single-item", "G-single", "G-nonadjacent-item", "G-nonadjacent", "G2-item",
      "G2",
    ]),
  )
  assert_eq(
    capture_field(report, "algorithm"),
    Json("v4-source-bound-category-g-single-1"),
  )
  assert_eq(
    v4_test_at(report, ["execution", "counterContract"]),
    Json("v4-category-g-single-seed-bfs-counters-1"),
  )
  assert_true(
    verify_classification_v4(snapshot, report, categories=["G-single"]),
  )
  assert_false(verify_classification_v4(snapshot, report))
}

///|
test "G-single 11 zero-RW and two-RW histories do not refute the selected rule" {
  let write_cycle = hist(
    [
      tx("A", [write_op("x", "x1"), write_op("y", "y2")]),
      tx("B", [write_op("y", "y1"), write_op("x", "x2")]),
    ],
    orders={ "x": ["x0", "x1", "x2"], "y": ["y0", "y1", "y2"] },
  )
  for input in [write_cycle, skew()] {
    let snapshot = register_history_v4(input).unwrap()
    assert_eq(classify_v4(snapshot).status(), "refuted")
    let result = classify_v4(snapshot, categories=["G-single"])
    assert_eq(result.status(), "checked-compatible")
    assert_eq(
      v4_test_at(classification_v4_json(result), [
        "judgment", "acceptsIsolationModels",
      ]),
      Json(false),
    )
  }
}

///|
test "G-single 12 old default and old category subsets retain original evidence shape" {
  let snapshot = register_history_v4(gs_test_single_history()).unwrap()
  for categories in [["G0", "G1c", "G2-item"], ["G2-item"], ["G1c", "G0"]] {
    let report = classification_v4_json(classify_v4(snapshot, categories~))
    assert_eq(
      capture_field(report, "algorithm"),
      Json("v4-source-bound-category-bfs-1"),
    )
    assert_eq(
      v4_test_at(report, ["execution", "counterContract"]),
      Json("v4-category-seed-bfs-counters-1"),
    )
    assert_false(
      object_fields_unchecked_v3(v4_test_at(report, ["judgment", "rules"])).contains(
        "G-single",
      ),
    )
    if categories.contains("G2-item") {
      let evidence = v4_test_at(report, [
        "judgment", "rules", "G2-item", "evidence",
      ])
      assert_eq(capture_field(evidence, "specificCategory"), Json("G2-item"))
      assert_false(object_fields_unchecked_v3(evidence).contains("rwEdgeCount"))
    }
  }
}

///|
test "G-single 13 adding the new category does not change old category counters or witnesses" {
  let snapshot = register_history_v4(gs_test_single_history()).unwrap()
  let old = classification_v4_json(classify_v4(snapshot))
  let mixed = classification_v4_json(
    classify_v4(snapshot, categories=["G-single", "G0", "G1c", "G2-item"]),
  )
  for category in ["G0", "G1c", "G2-item"] {
    assert_eq(gs_test_rule(old, category), gs_test_rule(mixed, category))
  }
}

///|
test "G-single 14 missing order remains unknown and reliable partial proofs survive" {
  let ambiguous = register_history_v4(completion_noise(3)).unwrap()
  let uncertain = classify_v4(ambiguous, categories=["G-single"])
  assert_eq(uncertain.status(), "inconclusive")
  assert_eq(
    capture_field(
      gs_test_rule(classification_v4_json(uncertain), "G-single"),
      "status",
    ),
    Json("unknown"),
  )
  let input = gs_test_single_history()
  input.transactions.push(tx("unknown", [], status=Unknown))
  let partial = classify_v4(register_history_v4(input).unwrap(), categories=[
    "G-single",
  ])
  assert_eq(partial.status(), "refuted")
  assert_eq(
    v4_test_at(classification_v4_json(partial), [
      "judgment", "dependencyGraphComplete",
    ]),
    Json(false),
  )
}

///|
test "G-single 15 typed exact budgets are caller context and cannot be raised by evidence" {
  let snapshot = register_history_v4(gs_test_single_history()).unwrap()
  let full = classification_v4_json(
    classify_v4(snapshot, categories=["G-single"]),
  )
  let rule = gs_test_rule(full, "G-single")
  let max_states = match capture_field(rule, "states") {
    Number(n, ..) => n.to_int()
    _ => -1
  }
  let max_edge_checks = match capture_field(rule, "edgeChecks") {
    Number(n, ..) => n.to_int()
    _ => -1
  }
  let exact = classify_v4(
    snapshot,
    categories=["G-single"],
    max_states~,
    max_edge_checks~,
  )
  assert_eq(exact.status(), "refuted")
  assert_true(
    verify_classification_v4(
      snapshot,
      classification_v4_json(exact),
      categories=["G-single"],
      max_states~,
      max_edge_checks~,
    ),
  )
  let limited = classify_v4(
    snapshot,
    categories=["G-single"],
    max_states~,
    max_edge_checks=max_edge_checks - 1,
  )
  assert_eq(limited.status(), "inconclusive")
  let altered = classification_v4_json(limited)
  v4_test_replace(
    altered,
    ["execution", "limits", "edgeChecksPerCategory"],
    Json(max_edge_checks),
  )
  assert_false(
    verify_classification_v4(
      snapshot,
      altered,
      categories=["G-single"],
      max_states~,
      max_edge_checks=max_edge_checks - 1,
    ),
  )
}

///|
test "G-single 16 witness count category and algorithm tampering is rejected" {
  let snapshot = register_history_v4(gs_test_single_history()).unwrap()
  let result = classify_v4(snapshot, categories=["G-single"])
  let wrong_count = classification_v4_json(result)
  v4_test_replace(
    wrong_count,
    ["judgment", "rules", "G-single", "evidence", "rwEdgeCount"],
    Json(2),
  )
  assert_false(
    verify_classification_v4(snapshot, wrong_count, categories=["G-single"]),
  )
  for
    path in [
      ["algorithm"],
      ["execution", "counterContract"],
      ["judgment", "rules", "G-single", "evidence", "rwEdgeCount"],
      ["judgment", "rules", "G-single", "evidence", "cycleRule"],
      ["judgment", "rules", "G-single", "evidence", "specificCategory"],
    ] {
    let altered = classification_v4_json(result)
    v4_test_replace(altered, path, Json("tampered"))
    assert_false(
      verify_classification_v4(snapshot, altered, categories=["G-single"]),
    )
  }
  assert_eq(
    classify_v4(snapshot, categories=["G-single", "G-single"]).status(),
    "invalid",
  )
}

///|
test "G-single 17 original list facts support a one-RW category proof" {
  let source = classification26_test_list([
    { "kind": "begin", "tx": "A", "connection": "a" },
    { "kind": "begin", "tx": "B", "connection": "b" },
    { "kind": "list_read", "tx": "A", "key": "x", "items": [] },
    { "kind": "append", "tx": "B", "key": "x", "id": "bx", "value": "same" },
    { "kind": "append", "tx": "B", "key": "y", "id": "by", "value": "same" },
    {
      "kind": "list_read",
      "tx": "A",
      "key": "y",
      "items": [{ "id": "by", "value": "same" }],
    },
    { "kind": "commit_request", "tx": "A" },
    { "kind": "commit_ok", "tx": "A" },
    { "kind": "commit_request", "tx": "B" },
    { "kind": "commit_ok", "tx": "B" },
  ])
  let snapshot = parse_history_v4(source.stringify()).unwrap()
  let result = classify_v4(snapshot, categories=["G-single"])
  assert_eq(result.status(), "refuted")
  let report = classification_v4_json(result)
  assert_eq(v4_test_at(report, ["observations", "document"]), source)
  assert_eq(
    v4_test_at(report, [
      "judgment", "rules", "G-single", "evidence", "rwEdgeCount",
    ]),
    Json(1),
  )
  assert_true(
    verify_classification_v4(snapshot, report, categories=["G-single"]),
  )
}

///|
test "G-single 18 ordinary list write skew has two RW edges and relation stays unsupported" {
  let list = parse_history_v4(classification26_test_list_skew().stringify()).unwrap()
  assert_eq(
    classify_v4(list, categories=["G-single"]).status(),
    "checked-compatible",
  )
  let relation = parse_history_v4(
    v4_test_model_complete(RelationSetV4, []).stringify(),
  ).unwrap()
  let report = classification_v4_json(
    classify_v4(relation, categories=["G-single"]),
  )
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("unsupported"))
  assert_eq(
    v4_test_at(report, ["judgment", "rules", "G-single", "status"]),
    Json("unsupported"),
  )
}
