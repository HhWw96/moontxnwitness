///|
test "df23 packed search keys own returned strings after scratch reuse" {
  let state = Array::make(128, 512)
  let positions = Array::make(128, 12)
  let units = FixedArray::make(257, 0)
  let first = encode_search_state_key(4095, state, positions, units~)
  let cached : Map[String, Bool] = Map([(first, true)])
  state[0] = 0
  positions[127] = 0
  let second = encode_search_state_key(0, state, positions, units~)
  assert_eq(first.length(), 257)
  assert_eq(first.unsafe_get(0).to_int(), 4095)
  assert_eq(first.unsafe_get(1).to_int(), 512)
  assert_eq(first.unsafe_get(256).to_int(), 12)
  assert_eq(second.unsafe_get(0).to_int(), 0)
  assert_true(first != second)
  assert_true(cached.contains(first))
  assert_true(!cached.contains(second))
}

///|
test "df23 packed keys equal every original scalar component at all widths" {
  for size in 0..<129 {
    let state = Array::makei(size, i => i * 17 % 513)
    let positions = Array::makei(size, i => i % 13)
    let expected = StringBuilder()
    expected.write_char((4095).unsafe_to_char())
    for value in state {
      expected.write_char(value.unsafe_to_char())
    }
    for value in positions {
      expected.write_char(value.unsafe_to_char())
    }
    assert_eq(
      encode_search_state_key(4095, state, positions),
      expected.to_string(),
    )
  }
}

///|
test "df23 identifier scan preserves the entire ASCII control boundary" {
  for code in 0..<128 {
    let b = StringBuilder()
    b.write_string("a")
    b.write_char(code.unsafe_to_char())
    b.write_string("z")
    assert_eq(valid_identifier(b.to_string()), code >= 32 && code != 127)
  }
}

///|
test "df23 identifier scan keeps UTF16 length and supplementary scalar semantics" {
  assert_true(valid_identifier("😀".repeat(128)))
  assert_true(!valid_identifier("😀".repeat(128) + "x"))
  assert_true(valid_identifier("é中😀𝄞"))
  assert_true(!valid_identifier("😀\u007f中"))
  assert_true(!valid_identifier("😀\u0000中"))
  assert_true(!valid_identifier(""))
}

///|
test "df23 identifier scan agrees with original predicate on scalar mixtures" {
  for length in 0..<258 {
    let text = "中".repeat(length)
    let previous = text.length() > 0 &&
      text.length() <= 256 &&
      !text.iter().any(c => c.to_int() < 32 || c.to_int() == 127)
    assert_eq(valid_identifier(text), previous)
  }
}

///|
fn df23_edge(from : String, to : String, reason : String) -> Edge {
  {
    from,
    to,
    kind: RT,
    key: None,
    from_op: None,
    to_op: None,
    from_version: None,
    to_version: None,
    reason,
  }
}

///|
test "df23 fixed adjacency retains original duplicate and provenance order" {
  let txs = [tx("A", []), tx("B", []), tx("C", [])]
  let edges = [
    df23_edge("A", "B", "first"),
    df23_edge("A", "C", "second"),
    df23_edge("B", "C", "third"),
    df23_edge("A", "B", "fourth"),
    df23_edge("C", "A", "fifth"),
  ]
  let g = adjacency(txs, edges)
  assert_eq(g.sources.iter().collect(), [0, 0, 1, 0, 2])
  assert_eq(g.targets.iter().collect(), [1, 2, 2, 1, 0])
  assert_eq(g.adj[0].iter().collect(), [0, 1, 3])
  assert_eq(g.adj[1].iter().collect(), [2])
  assert_eq(g.adj[2].iter().collect(), [4])
  let (cycle, info) = shortest_cycle(txs, edges, prepared=g)
  assert_true(cycle == [edges[1], edges[4]])
  assert_eq(info.bfs_roots, 1)
}

///|
test "df23 fixed adjacency handles empty graph and isolated transactions" {
  let empty = adjacency([], [])
  assert_eq(empty.adj.length(), 0)
  assert_eq(empty.sources.length(), 0)
  assert_eq(empty.targets.length(), 0)
  let txs = [tx("A", []), tx("B", [])]
  let g = adjacency(txs, [])
  assert_eq(g.adj[0].length(), 0)
  assert_eq(topological_order(txs, [], prepared=g), ["A", "B"])
}

///|
test "df23 fixed adjacency admits 512 vertices and all original edge indices" {
  let txs = Array::makei(512, i => tx("T" + i.to_string(), []))
  let edges : Array[Edge] = []
  for i in 0..<511 {
    edges.push(df23_edge(txs[i].id, txs[i + 1].id, "next"))
  }
  let g = adjacency(txs, edges)
  assert_eq(g.sources.length(), 511)
  assert_eq(g.adj[511].length(), 0)
  for i in 0..<511 {
    assert_eq(g.adj[i].length(), 1)
    assert_eq(g.adj[i][0], i)
    assert_eq(g.sources[i], i)
    assert_eq(g.targets[i], i + 1)
  }
  assert_eq(topological_order(txs, edges, prepared=g), txs.map(t => t.id))
}

///|
test "df23 sparse adjacency preserves isolated-node counts beside a two-cycle" {
  let txs = Array::makei(512, i => tx("T" + i.to_string(), []))
  let edges = [
    df23_edge("T0", "T1", "forward"),
    df23_edge("T1", "T0", "backward"),
  ]
  let g = adjacency(txs, edges)
  for i in 2..<512 {
    assert_eq(g.adj[i].length(), 0)
  }
  let (cycle, info) = shortest_cycle(txs, edges, prepared=g)
  assert_true(cycle == edges)
  assert_eq(info.components, 511)
  assert_eq(info.cyclic_transactions, 2)
  assert_eq(info.bfs_roots, 1)
  assert_eq(
    topological_order(txs, edges, prepared=g),
    Array::makei(510, i => txs[i + 2].id),
  )
}
