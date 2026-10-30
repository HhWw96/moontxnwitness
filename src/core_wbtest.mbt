///|
fn read_op(key : String, version : String) -> Operation {
  { kind: Read, key, version, }
}

///|
fn write_op(key : String, version : String) -> Operation {
  { kind: Write, key, version, }
}

///|
fn tx(
  id : String,
  ops : Array[Operation],
  status~ : TxStatus = Committed,
  start~ : Int64? = None,
  end~ : Int64? = None,
) -> Transaction {
  { id, status, ops, start, end, }
}

///|
fn hist(
  txs : Array[Transaction],
  orders~ : Map[String, Array[String]] = Map([]),
  model~ : Model = Serializable,
) -> History {
  {
    model,
    initial: { "x": "x0", "y": "y0" },
    version_orders: orders,
    transactions: txs,
  }
}

///|
fn skew() -> History {
  hist([
    tx("T1", [read_op("x", "x0"), write_op("y", "y1")]),
    tx("T2", [read_op("y", "y0"), write_op("x", "x1")]),
  ])
}

///|
fn has_code(r : Report, code : String) -> Bool {
  r.findings.any(f => f.code == code)
}

///|
test "empty history has a valid empty serial order" {
  let r = analyze(hist([]))
  assert_true(r.outcome == Consistent)
  assert_eq(r.serial_order.length(), 0)
}

///|
test "two-key write skew has a verified two-edge rw cycle" {
  let h = skew()
  let r = analyze(h)
  assert_true(r.outcome == Violation)
  assert_eq(r.witness.length(), 2)
  assert_true(r.witness.all(e => e.kind == RW))
  assert_true(verify_cycle(h, r.witness))
}

///|
test "acyclic wr and rw dependencies produce a satisfying serial order" {
  let h = hist([
    tx("T1", [read_op("x", "x0"), write_op("y", "y1")]),
    tx("T2", [read_op("y", "y1"), write_op("x", "x1")]),
  ])
  let r = analyze(h)
  assert_true(r.outcome == Consistent)
  assert_true(r.serial_order == ["T1", "T2"])
}

///|
test "mutually observed future external writes form an information cycle" {
  let h = hist([
    tx("A", [read_op("y", "y1"), write_op("x", "x1")]),
    tx("B", [read_op("x", "x1"), write_op("y", "y1")]),
  ])
  let r = analyze(h)
  assert_true(r.outcome == Violation)
  assert_true(r.witness.all(e => e.kind == WR))
}

///|
test "missing order admits a serialization without asserting an observed order" {
  let r = analyze(
    hist([tx("W1", [write_op("x", "x1")]), tx("W2", [write_op("x", "x2")])]),
  )
  assert_true(r.outcome == Consistent)
  assert_eq(r.search.status, "found")
  assert_eq(r.order_sources.at("x"), "searched")
  assert_eq(r.serial_order.length(), 2)
}

///|
test "explicit complete write order resolves ambiguity" {
  let h = hist(
    [tx("W1", [write_op("x", "x1")]), tx("W2", [write_op("x", "x2")])],
    orders={ "x": ["x0", "x2", "x1"] },
  )
  let r = analyze(h)
  assert_true(r.outcome == Consistent)
  assert_true(r.serial_order == ["W2", "W1"])
}

///|
test "lost update with an asserted version order is rejected" {
  let h = hist(
    [
      tx("U1", [read_op("x", "x0"), write_op("x", "x1")]),
      tx("U2", [read_op("x", "x0"), write_op("x", "x2")]),
    ],
    orders={ "x": ["x0", "x1", "x2"] },
  )
  let r = analyze(h)
  assert_true(r.outcome == Violation)
  assert_true(r.witness.any(e => e.kind == WW))
  assert_true(r.witness.any(e => e.kind == RW))
}

///|
test "aborted source version is a definite dirty read" {
  let r = analyze(
    hist([
      tx("W", [write_op("x", "v")], status=Aborted),
      tx("R", [read_op("x", "v")]),
    ]),
  )
  assert_true(r.outcome == Violation)
  assert_true(has_code(r, "aborted_read"))
}

///|
test "unknown source outcome is not mislabeled as dirty or safe" {
  let r = analyze(
    hist([
      tx("W", [write_op("x", "v")], status=Unknown),
      tx("R", [read_op("x", "v")]),
    ]),
  )
  assert_true(r.outcome == Inconclusive)
  assert_true(has_code(r, "unknown_writer"))
  assert_true(!has_code(r, "aborted_read"))
}

///|
test "unrecorded read version makes the history inconclusive" {
  let r = analyze(hist([tx("R", [read_op("x", "unseen")])]))
  assert_true(r.outcome == Inconclusive)
  assert_true(has_code(r, "unobserved_version"))
}

///|
test "aborted readers do not constrain the committed graph" {
  let r = analyze(hist([tx("R", [read_op("x", "unseen")], status=Aborted)]))
  assert_true(r.outcome == Consistent)
  assert_eq(r.edges.length(), 0)
}

///|
test "a known cycle still disproves consistency with unrelated unknown transactions" {
  let h = skew()
  let txs = h.transactions.copy()
  txs.push(tx("unknown", [], status=Unknown))
  let r = analyze({ ..h, transactions: txs, })
  assert_true(r.outcome == Violation)
  assert_true(has_code(r, "unknown_commit"))
}

///|
test "own final and intermediate writes are valid local read sources" {
  let r = analyze(
    hist([
      tx("T", [
        write_op("x", "x1"),
        read_op("x", "x1"),
        write_op("x", "x2"),
        read_op("x", "x2"),
      ]),
    ]),
  )
  assert_true(r.outcome == Consistent)
  assert_eq(r.edges.length(), 0)
}

///|
test "read-your-writes violation has operation provenance" {
  let r = analyze(hist([tx("T", [write_op("x", "x1"), read_op("x", "x0")])]))
  assert_true(r.outcome == Violation)
  assert_true(has_code(r, "read_your_writes"))
  assert_true(r.findings[0].ops == [0, 1])
}

///|
test "reads of own future write are impossible in a serial register transaction" {
  let r = analyze(hist([tx("T", [read_op("x", "x1"), write_op("x", "x1")])]))
  assert_true(r.outcome == Violation)
  assert_true(has_code(r, "future_read"))
}

///|
test "external intermediate version is rejected even after source commits" {
  let r = analyze(
    hist([
      tx("W", [write_op("x", "x1"), write_op("x", "x2")]),
      tx("R", [read_op("x", "x1")]),
    ]),
  )
  assert_true(r.outcome == Violation)
  assert_true(has_code(r, "intermediate_read"))
}

///|
test "non-repeatable read without an own write violates the model" {
  let r = analyze(
    hist([
      tx("W", [write_op("x", "x1")]),
      tx("R", [read_op("x", "x0"), read_op("x", "x1")]),
    ]),
  )
  assert_true(r.outcome == Violation)
  assert_true(has_code(r, "non_repeatable_read"))
}

///|
test "normal serializability does not silently enforce real time" {
  let h = hist([
    tx("W", [write_op("x", "x1")], start=Some(1L), end=Some(2L)),
    tx("R", [read_op("x", "x0")], start=Some(3L), end=Some(4L)),
  ])
  let r = analyze(h)
  assert_true(r.outcome == Consistent)
  assert_true(r.serial_order == ["R", "W"])
}

///|
test "strict serializability combines real-time and rw constraints" {
  let h = hist(
    [
      tx("W", [write_op("x", "x1")], start=Some(1L), end=Some(2L)),
      tx("R", [read_op("x", "x0")], start=Some(3L), end=Some(4L)),
    ],
    model=StrictSerializable,
  )
  let r = analyze(h)
  assert_true(r.outcome == Violation)
  assert_true(r.witness.any(e => e.kind == RT))
}

///|
test "strict mode with missing intervals is inconclusive" {
  let r = analyze(
    hist([tx("R", [read_op("x", "x0")])], model=StrictSerializable),
  )
  assert_true(r.outcome == Inconclusive)
  assert_true(has_code(r, "missing_interval"))
}

///|
test "equal endpoint ticks do not imply a strict before relation" {
  let h = hist(
    [
      tx("W", [write_op("x", "x1")], start=Some(1L), end=Some(2L)),
      tx("R", [read_op("x", "x0")], start=Some(2L), end=Some(3L)),
    ],
    model=StrictSerializable,
  )
  assert_true(analyze(h).outcome == Consistent)
}

///|
test "duplicate transaction identifiers are invalid typed inputs" {
  assert_true(analyze(hist([tx("T", []), tx("T", [])])).outcome == Invalid)
}

///|
test "reused versions cannot be used to infer read sources" {
  let r = analyze(
    hist([tx("A", [write_op("x", "v")]), tx("B", [write_op("x", "v")])]),
  )
  assert_true(r.outcome == Invalid)
  assert_true(has_code(r, "duplicate_write_version"))
}

///|
test "writing an initial version is invalid" {
  let r = analyze(hist([tx("A", [write_op("x", "x0")])]))
  assert_true(r.outcome == Invalid)
  assert_true(has_code(r, "initial_version_reused"))
}

///|
test "every operated key needs an initial version" {
  let r = analyze(hist([tx("A", [read_op("missing", "v")])]))
  assert_true(r.outcome == Invalid)
  assert_true(has_code(r, "missing_initial"))
}

///|
test "incomplete supplied version orders are invalid rather than silently extended" {
  let h = hist([tx("A", [write_op("x", "x1")])], orders={ "x": ["x0"] })
  assert_true(analyze(h).outcome == Invalid)
}

///|
test "duplicate and unrecorded entries in version orders are rejected" {
  assert_true(
    analyze(hist([], orders={ "x": ["x0", "x0"] })).outcome == Invalid,
  )
  assert_true(
    analyze(hist([], orders={ "unknown": ["v0"] })).outcome == Invalid,
  )
}

///|
test "invalid time intervals are rejected for typed library callers" {
  let r = analyze(hist([tx("A", [], start=Some(10L), end=Some(9L))]))
  assert_true(r.outcome == Invalid)
}

///|
test "the shortest cycle is found even when a longer cycle appears first" {
  let h : History = {
    model: Serializable,
    initial: { "x": "x0", "y": "y0", "z": "z0", "a": "a0", "b": "b0" },
    version_orders: Map([]),
    transactions: [
      tx("L1", [read_op("x", "x0"), write_op("y", "y1")]),
      tx("L2", [read_op("y", "y0"), write_op("z", "z1")]),
      tx("L3", [read_op("z", "z0"), write_op("x", "x1")]),
      tx("S1", [read_op("a", "a0"), write_op("b", "b1")]),
      tx("S2", [read_op("b", "b0"), write_op("a", "a1")]),
    ],
  }
  let r = analyze(h)
  assert_eq(r.witness.length(), 2)
  assert_true(r.witness.all(e => e.from == "S1" || e.from == "S2"))
}

///|
test "tampered operation provenance invalidates a typed cycle witness" {
  let h = skew()
  let w = analyze(h).witness.copy()
  w[0] = { ..w[0], from_op: Some(999), }
  assert_true(!verify_cycle(h, w))
}

///|
test "an open or repeated cycle path is not a certificate" {
  let h = skew()
  let w = analyze(h).witness
  assert_true(!verify_cycle(h, [w[0]]))
  assert_true(!verify_cycle(h, [w[0], w[0]]))
}

///|
test "generated JSON certificate verifies against its source history" {
  let h = skew()
  let certificate = report_json(analyze(h)).stringify()
  let result = @json.parse(
    verify_certificate_json(history_json(h).stringify(), certificate),
  ) catch {
    _ => abort("invalid transport")
  }
  assert_true(result is Object(m) && m.get("valid") == Some(Json(true)))
}

///|
test "history JSON round trip preserves the workload" {
  let h = skew()
  assert_true(parse_history(history_json(h).stringify()) == Ok(h))
}

///|
test "invalid JSON and unknown operation kinds produce invalid reports" {
  assert_true(parse_history("{") is Err(_))
  assert_true(
    parse_history(
      "{\"initial\":{},\"transactions\":[{\"id\":\"t\",\"status\":\"committed\",\"ops\":[{\"type\":\"append\",\"key\":\"x\",\"version\":\"v\"}]}]}",
    )
    is Err(_),
  )
}

///|
test "unknown input fields and unsupported schemas are rejected" {
  assert_true(
    parse_history("{\"initial\":{},\"transactions\":[],\"extra\":true}")
    is Err(_),
  )
  assert_true(
    parse_history("{\"schemaVersion\":2,\"initial\":{},\"transactions\":[]}")
    is Err(_),
  )
}

///|
test "duplicate object keys include escape-equivalent keys" {
  assert_true(
    parse_history("{\"initial\":{},\"transactions\":[],\"transactions\":[]}")
    is Err(_),
  )
  assert_true(
    parse_history(
      "{\"initial\":{\"x\":\"v0\",\"\\u0078\":\"v1\"},\"transactions\":[]}",
    )
    is Err(_),
  )
}

///|
test "same object-key spelling in separate objects is allowed" {
  let text = "{\"initial\":{\"x\":\"x0\"},\"transactions\":[{\"id\":\"A\",\"status\":\"committed\",\"ops\":[]},{\"id\":\"B\",\"status\":\"committed\",\"ops\":[]}]}"
  assert_true(parse_history(text) is Ok(_))
}

///|
test "identifier control characters and unsafe integer timestamps are rejected" {
  assert_true(
    parse_history("{\"initial\":{\"x\\n\":\"v0\"},\"transactions\":[]}")
    is Err(_),
  )
  assert_true(
    parse_history(
      "{\"initial\":{},\"transactions\":[{\"id\":\"A\",\"status\":\"committed\",\"ops\":[],\"start\":0.5}]}",
    )
    is Err(_),
  )
}

///|
test "deep and oversized inputs fail within explicit resource limits" {
  assert_true(parse_history("[".repeat(65) + "0" + "]".repeat(65)) is Err(_))
  assert_true(parse_history(" ".repeat(1048577)) is Err(_))
}

///|
test "report formats escape untrusted Markdown and DOT identifiers" {
  let h = hist([tx("<script>[bad]", [])])
  let markdown = render_report(analyze(h), "markdown")
  assert_true(!markdown.contains("<script>"))
  assert_true(markdown.contains("&lt;script&gt;"))
  let dot = render_report(analyze(skew()), "dot")
  assert_true(dot.contains("digraph MoonTxnWitness"))
  assert_true(dot.contains("penwidth=3"))
}

///|
test "a truncated dependency graph cannot produce a consistent result" {
  let txs : Array[Transaction] = []
  for i in 0..<512 {
    txs.push(
      tx(
        i.to_string(),
        [],
        start=Some((i * 3).to_int64()),
        end=Some((i * 3 + 1).to_int64()),
      ),
    )
  }
  let r = analyze(hist(txs, model=StrictSerializable))
  assert_true(r.outcome == Inconclusive)
  assert_true(has_code(r, "edge_limit"))
  assert_eq(r.edges.length(), 50000)
}
