///|
test "draft analysis scratch epochs do not leak own writes across transactions" {
  let result = analyze(
    hist([
      tx("A", [write_op("x", "x1"), read_op("x", "x1")]),
      tx("B", [read_op("x", "x0")]),
    ]),
  )
  assert_true(result.outcome == Consistent)
  assert_eq(result.serial_order, ["B", "A"])
  assert_true(!has_code(result, "read_your_writes"))
}

///|
test "draft analysis keeps the first read operation for repeatability diagnostics" {
  let result = analyze(
    hist([
      tx("A", [read_op("x", "x0"), read_op("x", "x1"), read_op("x", "x0")]),
      tx("B", [write_op("x", "x1")]),
      tx("C", [read_op("x", "x0")]),
    ]),
  )
  let findings = result.findings.filter(f => f.code == "non_repeatable_read")
  assert_eq(findings.length(), 1)
  assert_eq(findings[0].ops, [0, 1])
}

///|
test "draft write indexing preserves interleaved multi-key final operations" {
  let h = hist([
    tx("A", [write_op("x", "x1"), write_op("y", "y1"), write_op("x", "x2")]),
  ])
  let writes = collect_writes(h)
  assert_true(!writes.at("x").at("x1").is_final)
  assert_true(writes.at("x").at("x2").is_final)
  assert_eq(writes.at("x").at("x2").op, 2)
  assert_true(writes.at("y").at("y1").is_final)
  assert_eq(writes.at("y").at("y1").op, 1)
}

///|
test "draft write indexing keeps only the latest own write for read diagnostics" {
  let result = analyze(
    hist([
      tx("A", [
        write_op("x", "x1"),
        read_op("x", "x1"),
        write_op("x", "x2"),
        read_op("x", "x1"),
      ]),
    ]),
  )
  let findings = result.findings.filter(f => f.code == "read_your_writes")
  assert_eq(findings.length(), 1)
  assert_eq(findings[0].ops, [2, 3])
}

///|
test "draft two-version rank shortcut retains both anti and write-read dependencies" {
  let result = analyze(
    hist([
      tx("A", [read_op("x", "x0")]),
      tx("B", [write_op("x", "x1")]),
      tx("C", [read_op("x", "x1")]),
    ]),
  )
  assert_true(result.outcome == Consistent)
  assert_eq(result.edges.length(), 2)
  assert_true(result.edges[0].kind == RW)
  assert_true(result.edges[1].kind == WR)
  assert_eq(result.serial_order, ["A", "B", "C"])
}

///|
test "draft lazy scratch ignores unused initial keys while preserving skipped transactions" {
  let h = hist([
    tx("Skipped", [read_op("unused0", "initial")]),
    tx("A", [write_op("x", "x1"), read_op("x", "x1")]),
    tx("B", [read_op("x", "x0")]),
    tx("SkippedAfter", [read_op("unused1023", "initial")]),
  ])
  for i in 0..<1024 {
    h.initial["unused" + i.to_string()] = "initial"
  }
  let result = analyze(h)
  assert_true(result.outcome == Consistent)
  assert_eq(result.edges.length(), 1)
  assert_eq(result.edges[0].from, "B")
  assert_eq(result.edges[0].to, "A")
  assert_eq(result.serial_order.length(), 4)
  assert_true(result.serial_order.contains("Skipped"))
  assert_true(result.serial_order.contains("SkippedAfter"))
  assert_true(!has_code(result, "read_your_writes"))
}
