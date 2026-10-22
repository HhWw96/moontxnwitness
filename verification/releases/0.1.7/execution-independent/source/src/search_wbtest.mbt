///|
test "unknown writer order can make atomic mixed observations impossible" {
  let h = hist([
    tx("A", [write_op("x", "x1"), write_op("y", "y1")]),
    tx("B", [write_op("x", "x2"), write_op("y", "y2")]),
    tx("R", [read_op("x", "x1"), read_op("y", "y2")]),
  ])
  let r = analyze(h)
  assert_true(r.outcome == Violation)
  assert_eq(r.search.status, "exhausted")
  assert_true(has_code(r, "no_serial_execution"))
  assert_true(r.witness.is_empty())
}

///|
test "searched completion does not overwrite asserted order provenance" {
  let h = hist(
    [
      tx("A", [write_op("x", "x1"), write_op("y", "y1")]),
      tx("B", [write_op("x", "x2"), write_op("y", "y2")]),
    ],
    orders=Map([("y", ["y0", "y2", "y1"])]),
  )
  let r = analyze(h)
  assert_true(r.outcome == Consistent)
  assert_eq(r.serial_order[0], "B")
  assert_eq(r.order_sources.at("y"), "asserted")
  assert_eq(r.order_sources.at("x"), "searched")
  assert_true(r.inferred_orders.at("x") == ["x0", "x2", "x1"])
}

///|
test "completion size limit cannot turn missing information into a negative claim" {
  let txs = Array::makei(9, i => {
    tx("t" + i.to_string(), [write_op("x", "v" + i.to_string())])
  })
  let r = analyze(hist(txs))
  assert_true(r.outcome == Inconclusive)
  assert_eq(r.search.status, "skipped")
  assert_true(has_code(r, "search_limit"))
}

///|
test "completion attempt budget never reports exhaustive failure" {
  let h = hist([tx("A", [write_op("x", "x1")]), tx("B", [write_op("x", "x2")])])
  let (s, p) = search_serial(h, Map([]), [], max_attempts=1)
  assert_eq(s.status, "budget")
  assert_true(p is None)
}

///|
test "completion operation budget never reports exhaustive failure" {
  let h = hist([tx("A", [read_op("x", "x0"), write_op("x", "x1")])])
  let (s, p) = search_serial(h, Map([]), [], max_operations=1)
  assert_eq(s.status, "budget")
  assert_true(p is None)
}

///|
test "unknown outcomes are not silently solved away" {
  let r = analyze(
    hist([
      tx("A", [write_op("x", "x1")]),
      tx("B", [write_op("x", "x2")]),
      tx("U", [], status=Unknown),
    ]),
  )
  assert_true(r.outcome == Inconclusive)
  assert_true(has_code(r, "unknown_commit"))
  assert_eq(r.search.status, "not-needed")
}
