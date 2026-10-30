///|
fn rdc_history(own_read~ : Bool = false, back_read~ : Bool = true) -> History {
  let operations : Array[Operation] = []
  if !own_read {
    operations.push(read_op("x", "x0"))
  }
  operations.push(write_op("x", "x1"))
  if own_read {
    operations.push(read_op("x", "x1"))
  }
  if back_read {
    operations.push(read_op("y", "y1"))
  }
  let writer = [write_op("x", "x2")]
  if back_read {
    writer.push(write_op("y", "y1"))
  }
  hist([tx("A", operations), tx("B", writer)], orders={
    "x": ["x0", "x1", "x2"],
    "y": if back_read {
      ["y0", "y1"]
    } else {
      ["y0"]
    },
  })
}

///|
fn rdc_graph(input : History) -> V4CategoryGraph raise {
  v4_category_graph(register_history_v4(input).unwrap())
}

///|
fn rdc_rule(report : Json, category : String) -> Json {
  v4_test_at(report, ["judgment", "rules", category])
}

///|
test "register direct category 01 own read is not an external RW source" {
  let history = rdc_history(own_read=true)
  let graph = rdc_graph(history)
  assert_false(graph.base.edges.any(edge => edge.kind == RW))
  let report = classification_v4_json(
    classify_v4(register_history_v4(history).unwrap()),
  )
  assert_eq(capture_field(rdc_rule(report, "G1c"), "status"), Json("refuted"))
  assert_eq(
    capture_field(rdc_rule(report, "G2-item"), "status"),
    Json("checked-compatible"),
  )
}

///|
test "register direct category 02 own installed successor stops RW before a later writer" {
  let history = rdc_history()
  let graph = rdc_graph(history)
  assert_false(graph.base.edges.any(edge => edge.kind == RW))
  let report = classification_v4_json(
    classify_v4(register_history_v4(history).unwrap()),
  )
  assert_eq(capture_field(rdc_rule(report, "G1c"), "status"), Json("refuted"))
  assert_eq(
    capture_field(rdc_rule(report, "G2-item"), "status"),
    Json("checked-compatible"),
  )
  assert_eq(
    v4_test_at(report, ["judgment", "impliedAnomalies"]),
    Json(["G1c", "G1"]),
  )
}

///|
test "register direct category 03 acyclic own successor chain contains only adjacent WW" {
  let graph = rdc_graph(rdc_history(back_read=false))
  assert_true(graph.base.complete)
  assert_eq(graph.base.edges.length(), 1)
  assert_true(graph.base.edges[0].kind == WW)
  assert_eq(graph.base.edges[0].from, "A")
  assert_eq(graph.base.edges[0].to, "B")
}

///|
test "register direct category 04 genuine direct external RW preserves G2 witness" {
  let graph = rdc_graph(skew())
  assert_eq(graph.base.edges.filter(edge => edge.kind == RW).length(), 2)
  let snapshot = register_history_v4(skew()).unwrap()
  let report = classification_v4_json(classify_v4(snapshot))
  assert_eq(
    capture_field(rdc_rule(report, "G2-item"), "status"),
    Json("refuted"),
  )
  assert_true(verify_classification_v4(snapshot, report))
}

///|
fn rdc_long_history() -> History {
  hist(
    [
      tx("R", [read_op("x", "x0"), read_op("y", "y1")]),
      tx("B", [write_op("x", "x1")]),
      tx("C", [write_op("x", "x2"), write_op("y", "y1")]),
    ],
    orders={ "x": ["x0", "x1", "x2"], "y": ["y0", "y1"] },
  )
}

///|
test "register direct category 05 real longer RW WW WR path replaces a transitive shortcut" {
  let history = rdc_long_history()
  let graph = rdc_graph(history)
  assert_false(
    graph.base.edges.any(edge => {
      edge.kind == RW && edge.from == "R" && edge.to == "C"
    }),
  )
  assert_true(
    graph.base.edges.any(edge => {
      edge.kind == RW && edge.from == "R" && edge.to == "B"
    }),
  )
  assert_true(
    graph.base.edges.any(edge => {
      edge.kind == WW && edge.from == "B" && edge.to == "C"
    }),
  )
  let snapshot = register_history_v4(history).unwrap()
  let report = classification_v4_json(
    classify_v4(snapshot, categories=["G2-item"]),
  )
  let proof = capture_field(rdc_rule(report, "G2-item"), "evidence")
  assert_eq(v3_test_items(proof, "edges").length(), 3)
  assert_true(
    verify_classification_v4(snapshot, report, categories=["G2-item"]),
  )
}

///|
test "register direct category 06 missing version order cannot turn initial constraints into direct RW" {
  let history = hist([
    tx("R", [read_op("x", "x0")]),
    tx("A", [write_op("x", "x1")]),
    tx("B", [write_op("x", "x2")]),
  ])
  let graph = rdc_graph(history)
  assert_false(graph.base.complete)
  assert_false(graph.base.edges.any(edge => edge.kind == RW))
  assert_true(
    graph.base.validity_gaps.any(gap => {
      capture_field(gap, "code") == Json("missing_version_order")
    }),
  )
  let report = classification_v4_json(
    classify_v4(register_history_v4(history).unwrap()),
  )
  for category in ["G0", "G1c", "G2-item"] {
    assert_eq(
      capture_field(rdc_rule(report, category), "status"),
      Json("unknown"),
    )
  }
}

///|
test "register direct category 07 full legacy analysis output and shortest cycle remain unchanged" {
  let history = rdc_history()
  let legacy = analyze_internal(history, false, complete_search=false)
  let before_edges = legacy.edges.copy()
  assert_true(
    legacy.edges.any(edge => {
      edge.kind == RW &&
      edge.from_version == Some("x0") &&
      edge.to_version == Some("x2")
    }),
  )
  let _ = rdc_graph(history)
  let after = analyze_internal(history, false, complete_search=false)
  assert_true(legacy == after)
  assert_true(legacy.edges == before_edges)
}

///|
test "register direct category 08 missing unrelated order cannot hide known G1c refutation" {
  let base = rdc_history()
  base.initial["z"] = "z0"
  base.transactions.push(tx("Z1", [write_op("z", "z1")]))
  base.transactions.push(tx("Z2", [write_op("z", "z2")]))
  let report = classification_v4_json(
    classify_v4(register_history_v4(base).unwrap()),
  )
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("refuted"))
  assert_eq(
    v4_test_at(report, ["judgment", "dependencyGraphComplete"]),
    Json(false),
  )
  assert_eq(capture_field(rdc_rule(report, "G1c"), "status"), Json("refuted"))
  assert_eq(
    capture_field(rdc_rule(report, "G2-item"), "status"),
    Json("unknown"),
  )
}

///|
test "register direct category 09 incomplete operation metadata is uncertainty not compatible" {
  let input = skew()
  for
    field in ["key", "fromVersion", "toVersion", "fromOp", "toOp", "invalidOp"] {
    let report = analyze_internal(input, false, complete_search=false)
    let edge = report.edges[0]
    report.edges[0] = match field {
      "key" => { ..edge, key: None, }
      "fromVersion" => { ..edge, from_version: None, }
      "toVersion" => { ..edge, to_version: None, }
      "fromOp" => { ..edge, from_op: None, }
      "toOp" => { ..edge, to_op: None, }
      _ => { ..edge, from_op: Some(999), }
    }
    let (edges, gaps) = v4_register_direct_category_edges(input, report)
    assert_eq(edges.length(), 1)
    assert_eq(gaps.length(), 1)
    assert_eq(capture_field(gaps[0], "severity"), Json("uncertainty"))
  }
}

///|
test "register direct category 10 reliable G0 survives an unrelated missing order" {
  let input = hist(
    [
      tx("A", [write_op("x", "x1"), write_op("y", "y2")]),
      tx("B", [write_op("y", "y1"), write_op("x", "x2")]),
    ],
    orders={ "x": ["x0", "x1", "x2"], "y": ["y0", "y1", "y2"] },
  )
  input.initial["z"] = "z0"
  input.transactions.push(tx("Z1", [write_op("z", "z1")]))
  input.transactions.push(tx("Z2", [write_op("z", "z2")]))
  let snapshot = register_history_v4(input).unwrap()
  let report = classification_v4_json(classify_v4(snapshot))
  assert_eq(
    v4_test_at(report, ["judgment", "dependencyGraphComplete"]),
    Json(false),
  )
  assert_eq(capture_field(rdc_rule(report, "G0"), "status"), Json("refuted"))
  assert_eq(capture_field(rdc_rule(report, "G1c"), "status"), Json("refuted"))
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("refuted"))
}

///|
test "register direct category 11 verifier rejects reintroduced legacy transitive constraints" {
  let input = rdc_history()
  let snapshot = register_history_v4(input).unwrap()
  let report = classification_v4_json(classify_v4(snapshot))
  assert_true(verify_classification_v4(snapshot, report))
  let edges = match v4_test_at(report, ["judgment", "dependencies"]) {
    Array(edges) => edges
    _ => []
  }
  let old = analyze_internal(input, false, complete_search=false).edges.filter(edge => {
      edge.kind == RW
    })[0]
  edges.push(edge_json(old))
  assert_false(verify_classification_v4(snapshot, report))
}
