///|
test "newly ready lower index preempts an older ready transaction" {
  let txs = [tx("low", []), tx("unlock", []), tx("already-ready", [])]
  let edges = [topology_edge("unlock", "low")]
  assert_true(
    topological_order(txs, edges) == ["unlock", "low", "already-ready"],
  )
}

///|
test "parallel dependencies enqueue a target only after the last edge" {
  let txs = [
    tx("target", []),
    tx("first", []),
    tx("second", []),
    tx("free", []),
  ]
  let edge = topology_edge("first", "target")
  let edges = [edge, edge, topology_edge("second", "target")]
  assert_true(
    topological_order(txs, edges) == ["first", "second", "target", "free"],
  )
}

///|
test "topology excludes noncommitted transactions and retains the acyclic prefix of a cycle" {
  let txs = [
    tx("aborted", [], status=Aborted),
    tx("unknown", [], status=Unknown),
    tx("free", []),
    tx("cycle-a", []),
    tx("cycle-b", []),
  ]
  let edges = [
    topology_edge("cycle-a", "cycle-b"),
    topology_edge("cycle-b", "cycle-a"),
  ]
  assert_true(topological_order(txs, edges) == ["free"])
  assert_true(topological_order([], []).is_empty())
}

///|
test "self loops and incoming dependencies from noncommitted sources stay blocked" {
  let txs = [
    tx("self", []),
    tx("aborted", [], status=Aborted),
    tx("unknown", [], status=Unknown),
    tx("blocked", []),
    tx("free", []),
  ]
  let edges = [
    topology_edge("self", "self"),
    topology_edge("aborted", "blocked"),
    topology_edge("unknown", "blocked"),
    topology_edge("free", "aborted"),
  ]
  assert_true(topological_order(txs, edges) == ["free"])
}

///|
test "full budget disconnected histories preserve input order independently of ID spelling" {
  let txs = Array::makei(512, i => tx((511 - i).to_string(), []))
  let expected = txs.map(transaction => transaction.id)
  assert_true(topological_order(txs, []) == expected)
}

///|
test "reverse chain and branching DAG retain original-index tie order" {
  let txs = Array::makei(512, i => tx("n" + i.to_string(), []))
  let edges = Array::makei(511, i => {
    topology_edge("n" + (i + 1).to_string(), "n" + i.to_string())
  })
  let expected = Array::makei(512, i => "n" + (511 - i).to_string())
  assert_true(topological_order(txs, edges) == expected)
  let branches = [
    topology_edge("n5", "n1"),
    topology_edge("n1", "n0"),
    topology_edge("n2", "n0"),
    topology_edge("n3", "n4"),
  ]
  assert_true(
    topological_order(Array::makei(6, i => txs[i]), branches) ==
    ["n2", "n3", "n4", "n5", "n1", "n0"],
  )
}
