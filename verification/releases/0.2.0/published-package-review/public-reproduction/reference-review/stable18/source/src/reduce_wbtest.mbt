///|
test "reduction discards noise and proves one-minimality" {
  let h = hist(
    [tx("n1", []), ..skew().transactions, tx("n2", []), tx("n3", [])],
  )
  let before = history_json(h).stringify()
  let r = reduce_history(h)
  assert_true(r.report.outcome == Violation)
  assert_eq(r.history.transactions.length(), 2)
  assert_true(r.one_minimal)
  assert_eq(history_json(h).stringify(), before)
  for i in 0..<r.history.transactions.length() {
    assert_true(analyze(without_chunk(r.history, i, 1)).outcome != Violation)
  }
}

///|
test "reduction prunes asserted orders without introducing searched constraints" {
  let h = hist(
    [
      tx("A", [read_op("x", "x0"), write_op("x", "x1")]),
      tx("B", [read_op("x", "x0"), write_op("x", "x2")]),
      tx("noise", [write_op("x", "x3")]),
    ],
    orders=Map([("x", ["x0", "x1", "x2", "x3"])]),
  )
  let r = reduce_history(h)
  assert_true(r.report.outcome == Violation)
  assert_eq(r.history.transactions.length(), 2)
  assert_true(r.history.version_orders.at("x") == ["x0", "x1", "x2"])
}

///|
test "reduction preserves aborted-writer provenance" {
  let r = reduce_history(
    hist([
      tx("A", [write_op("x", "bad")], status=Aborted),
      tx("R", [read_op("x", "bad")]),
      tx("noise", []),
    ]),
  )
  assert_eq(r.history.transactions.length(), 2)
  assert_true(has_code(r.report, "aborted_read"))
  assert_true(r.one_minimal)
}

///|
test "reduction supports exact-search violations without a cycle" {
  let h = hist([
    tx("A", [write_op("x", "x1"), write_op("y", "y1")]),
    tx("B", [write_op("x", "x2"), write_op("y", "y2")]),
    tx("R", [read_op("x", "x1"), read_op("y", "y2")]),
    tx("noise", []),
  ])
  let r = reduce_history(h)
  assert_true(has_code(r.report, "no_serial_execution"))
  assert_eq(r.history.transactions.length(), 3)
  assert_true(r.history.version_orders.is_empty())
  assert_true(r.one_minimal)
}

///|
test "reduction does not create a violation from a consistent history" {
  let r = reduce_history(hist([tx("A", [])]))
  assert_eq(r.status, "not-violation")
  assert_true(!r.one_minimal)
}

///|
test "reduction budget returns retained evidence without false minimality" {
  let r = reduce_history(
    hist([tx("n1", []), ..skew().transactions]),
    max_checks=1,
  )
  assert_eq(r.status, "budget")
  assert_true(!r.one_minimal)
  assert_true(r.report.outcome == Violation)
}

///|
test "reduction rejects invalid transport" {
  assert_true(shrink_json("{").contains("invalid"))
}

///|
test "safe integer timestamps export as numbers through the maximum boundary" {
  let maximum = 9007199254740991.0.to_int64()
  let h = hist(
    [tx("T", [], start=Some(0L), end=Some(maximum))],
    model=StrictSerializable,
  )
  assert_true(parse_history(history_json(h).stringify()) == Ok(h))
}

///|
test "strict counterexamples survive reduction export and independent verification" {
  let h = hist(
    [
      tx("W", [write_op("x", "x1")], start=Some(1L), end=Some(2L)),
      tx("R", [read_op("x", "x0")], start=Some(3L), end=Some(4L)),
    ],
    model=StrictSerializable,
  )
  let r = reduce_history(h)
  assert_true(
    parse_history(history_json(r.history).stringify()) == Ok(r.history),
  )
  assert_true(verify_cycle(r.history, r.report.witness))
}
