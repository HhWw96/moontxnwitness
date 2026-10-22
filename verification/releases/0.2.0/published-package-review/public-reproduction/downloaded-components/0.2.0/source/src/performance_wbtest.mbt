///|
test "streamed report has exactly the structured report values" {
  let quoted = {
    ..skew(),
    transactions: skew().transactions.map(t => { ..t, id: t.id + "\"\\☃", }),
  }
  for h in [skew(), quoted, hist([tx("quote\"\\:|", [read_op("x", "x0")])])] {
    let r = analyze(h)
    let j = @json.parse(report_string(r))
    assert_eq(j, report_json(r))
  }
}

///|
test "structural edge keys cannot collide on delimiter-like identifiers" {
  let h = hist([
    tx("a|b", [read_op("x", "x0"), write_op("y", "y1")]),
    tx("b|c", [read_op("y", "y0"), write_op("x", "x1")]),
  ])
  let r = analyze(h)
  assert_true(r.outcome == Violation)
  assert_eq(r.witness.length(), 2)
  assert_true(verify_cycle(h, r.witness))
}
