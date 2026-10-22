///|
fn topology_edge(a : String, b : String) -> Edge {
  {
    from: a,
    to: b,
    kind: WR,
    key: None,
    from_op: None,
    to_op: None,
    from_version: None,
    to_version: None,
    reason: "Topology-only unit fixture",
  }
}

///|
test "acyclic histories avoid breadth-first cycle roots" {
  let r = analyze(
    hist([tx("W", [write_op("x", "x1")]), tx("R", [read_op("x", "x1")])]),
  )
  assert_true(r.outcome == Consistent)
  assert_true(r.graph.analyzed)
  assert_eq(r.graph.cyclic_transactions, 0)
  assert_eq(r.graph.bfs_roots, 0)
}

///|
test "a long acyclic prefix feeding a short cycle is pruned" {
  let txs : Array[Transaction] = []
  let edges : Array[Edge] = []
  for i in 0..<200 {
    txs.push(tx("n" + i.to_string(), []))
    edges.push(
      topology_edge(
        "n" + i.to_string(),
        if i == 199 {
          "A"
        } else {
          "n" + (i + 1).to_string()
        },
      ),
    )
  }
  txs.push(tx("A", []))
  txs.push(tx("B", []))
  edges.push(topology_edge("A", "B"))
  edges.push(topology_edge("B", "A"))
  let (cycle, info) = shortest_cycle(txs, edges)
  assert_eq(cycle.length(), 2)
  assert_eq(info.cyclic_transactions, 2)
  assert_eq(info.cyclic_components, 1)
  assert_eq(info.components, 201)
  assert_eq(info.bfs_roots, 1)
}

///|
test "shortest cycle comparison crosses separate strongly connected regions" {
  let txs = [tx("A", []), tx("B", []), tx("C", []), tx("D", []), tx("E", [])]
  let edges = [
    topology_edge("A", "B"),
    topology_edge("B", "C"),
    topology_edge("C", "A"),
    topology_edge("C", "D"),
    topology_edge("D", "E"),
    topology_edge("E", "D"),
  ]
  let (cycle, info) = shortest_cycle(txs, edges)
  assert_eq(cycle.length(), 2)
  assert_eq(info.cyclic_components, 2)
  assert_eq(info.cyclic_transactions, 5)
}

///|
test "component traversal handles the full transaction depth budget" {
  let txs = Array::makei(512, i => tx("n" + i.to_string(), []))
  let edges = Array::makei(511, i => {
    topology_edge("n" + i.to_string(), "n" + (i + 1).to_string())
  })
  let (cycle, info) = shortest_cycle(txs, edges)
  assert_true(cycle.is_empty())
  assert_eq(info.components, 512)
  assert_eq(info.bfs_roots, 0)
}

///|
test "coverage counts reads and only final committed writes" {
  let r = analyze(
    hist([
      tx("W", [write_op("x", "middle"), write_op("x", "x1")]),
      tx("R", [read_op("x", "x1")]),
    ]),
  )
  let x = r.coverage[0]
  assert_eq(x.key, "x")
  assert_eq(x.committed_reads, 1)
  assert_eq(x.committed_final_writes, 1)
  assert_eq(x.unresolved_reads, 0)
}

///|
test "coverage exposes unresolved sources with a collection action" {
  let r = analyze(hist([tx("R", [read_op("x", "not-captured")])]))
  assert_true(r.outcome == Inconclusive)
  assert_eq(r.coverage[0].unresolved_reads, 1)
  assert_true(
    next_steps(r).contains(
      "扩大采集窗口并寻找读取版本的写入来源。",
    ),
  )
}

///|
test "searched provenance is visible to people instead of becoming an observed fact" {
  let r = analyze(
    hist([tx("A", [write_op("x", "x1")]), tx("B", [write_op("x", "x2")])]),
  )
  assert_true(render_report(r, "markdown").contains("非观测事实"))
  assert_true(render_report(r, "text").contains("只证明存在"))
}
