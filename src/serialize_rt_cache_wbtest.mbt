///|
fn rtquote038_edge(from : String, to : String) -> Edge {
  {
    from,
    to,
    kind: RT,
    key: None,
    from_op: None,
    to_op: None,
    from_version: None,
    to_version: None,
    reason: "The source completed before the target began on the asserted common observer clock.",
  }
}

///|
fn rtquote038_report(edges : Array[Edge]) -> Report {
  { ..analyze(hist([])), edges, }
}

///|
fn rtquote038_check(edges : Array[Edge]) -> Unit raise {
  let report = rtquote038_report(edges)
  let expected = report_json(report).stringify()
  assert_eq(report_string(report), expected)
  assert_eq(report_json(report).stringify(), expected)
  let old = json_text()
  let strings : Map[String, String] = Map([])
  old.write_char('[')
  for i, edge in edges {
    if i > 0 {
      old.write_char(',')
    }
    write_edge(old, edge, strings)
  }
  old.write_char(']')
  let current = json_text()
  write_report_edges(current, edges, Map([]))
  assert_eq(current.to_string(), old.to_string())
}

///|
test "rtquote038 01 standard RT bytes retain the complete original shell" {
  rtquote038_check([rtquote038_edge("A", "B")])
  let text = json_text()
  write_report_edges(text, [rtquote038_edge("A", "B")], Map([]))
  assert_eq(
    text.to_string(),
    "[{\"from\":\"A\",\"to\":\"B\",\"kind\":\"rt\",\"key\":null,\"fromOp\":null,\"toOp\":null,\"fromVersion\":null,\"toVersion\":null,\"reason\":\"The source completed before the target began on the asserted common observer clock.\"}]",
  )
}

///|
test "rtquote038 02 empty and repeated endpoint names keep official JSON quotes" {
  rtquote038_check([
    rtquote038_edge("", ""),
    rtquote038_edge("A", "B"),
    rtquote038_edge("B", "A"),
    rtquote038_edge("A", "B"),
    rtquote038_edge("", "A"),
  ])
}

///|
test "rtquote038 03 all Unicode and escaped endpoint pairs match the structured serializer" {
  let names = [
    "月", "🙂𐐷", "é", "é", "a\"\\b", "\n\r\t\b\f\u0000\u001f", "  ",
    "中/文",
  ]
  let edges : Array[Edge] = []
  for from in names {
    for to in names {
      edges.push(rtquote038_edge(from, to))
      edges.push(rtquote038_edge(from, to))
    }
  }
  rtquote038_check(edges)
}

///|
test "rtquote038 04 native Map special object-property names do not collide" {
  let names = [
    "__proto__", "constructor", "toString", "hasOwnProperty", "edges", "version",
  ]
  let edges : Array[Edge] = []
  for from in names {
    for to in names {
      edges.push(rtquote038_edge(from, to))
    }
  }
  rtquote038_check(edges)
}

///|
test "rtquote038 05 every optional provenance field forces the unchanged fallback" {
  let base = rtquote038_edge("from🙂", "to\"\\")
  let edges : Array[Edge] = []
  for mask in 0..<32 {
    let edge : Edge = {
      ..base,
      key: if mask % 2 != 0 {
        Some("key\u0000")
      } else {
        None
      },
      from_op: if mask / 2 % 2 != 0 {
        Some(-2147483648)
      } else {
        None
      },
      to_op: if mask / 4 % 2 != 0 {
        Some(2147483647)
      } else {
        None
      },
      from_version: if mask / 8 % 2 != 0 {
        Some("")
      } else {
        None
      },
      to_version: if mask / 16 % 2 != 0 {
        Some("版本\n")
      } else {
        None
      },
    }
    assert_eq(has_standard_rt_shell(edge), mask == 0)
    edges.push(edge)
  }
  rtquote038_check(edges)
}

///|
test "rtquote038 06 custom RT reasons are never replaced by the standard constant" {
  let base = rtquote038_edge("same", "end")
  rtquote038_check([
    { ..base, reason: "", },
    { ..base, reason: base.reason + "\n", },
    { ..base, reason: "custom\"\\\u0000🙂", },
    base,
  ])
}

///|
test "rtquote038 07 non-RT dependencies preserve generic fields and ordering" {
  let edges : Array[Edge] = []
  for kind in [WW, WR, RW] {
    let base = { ..rtquote038_edge("A", "B"), kind, }
    assert_true(!has_standard_rt_shell(base))
    edges.push(base)
    edges.push({
      ..base,
      key: Some("k"),
      from_op: Some(0),
      to_op: Some(1),
      from_version: Some("v0"),
      to_version: Some("v1"),
    })
  }
  rtquote038_check(edges)
}

///|
test "rtquote038 08 mixed standard RT and generic edges share legitimate prequoted strings" {
  let names : Map[String, String] = Map([
    ("A", Json("A").stringify()),
    ("B", Json("B").stringify()),
  ])
  let edges = [
    rtquote038_edge("A", "B"),
    { ..rtquote038_edge("B", "A"), kind: RW, key: Some("A"), },
    rtquote038_edge("B", "A"),
  ]
  let b = json_text()
  write_report_edges(b, edges, names)
  assert_eq(@json.parse(b.to_string()), Json(edges.map(edge_json)))
  assert_eq(names.at("A"), Json("A").stringify())
  assert_eq(names.at("B"), Json("B").stringify())
}

///|
test "rtquote038 09 independent reports and repeated report calls retain complete bytes" {
  for index in 0..<48 {
    let name = "transaction-" + index.to_string() + "🙂\""
    let edges = [rtquote038_edge(name, "same"), rtquote038_edge("same", name)]
    rtquote038_check(edges)
    rtquote038_check([rtquote038_edge("same", "")])
  }
}

///|
test "rtquote038 10 large official encoded strings retain cold and cached values" {
  let value = StringBuilder()
  for _ in 0..<2048 {
    value.write_string("🙂\"\\\u0000")
  }
  let name = value.to_string()
  rtquote038_check([
    rtquote038_edge(name, "other"),
    rtquote038_edge("other", name),
    rtquote038_edge(name, name),
  ])
}

///|
#cfg(target="js")
fn rtquote038_check_cache_scopes() -> Unit raise {
  let first = new_report_rt_quoted_cache()
  let second = new_report_rt_quoted_cache()
  assert_eq(report_rt_cache_get(first, ""), "")
  let encoded = cached_quote("")
  assert_eq(encoded, "\"\"")
  report_rt_cache_put(first, "", encoded)
  assert_eq(report_rt_cache_get(first, ""), encoded)
  assert_eq(report_rt_cache_get(second, ""), "")
}

///|
#cfg(not(target="js"))
fn rtquote038_check_cache_scopes() -> Unit raise {
  let first : Map[String, String] = Map([])
  let second : Map[String, String] = Map([])
  assert_true(first.get("") is None)
  let encoded = quoted_cached(first, "")
  assert_eq(encoded, "\"\"")
  assert_true(first.get("") == Some(encoded))
  assert_true(second.get("") is None)
}

///|
test "rtquote038 11 report caches keep separate values with official empty-string quoting" {
  rtquote038_check_cache_scopes()
}

///|
#cfg(target="js")
fn rtquote038_check_cache_quotes() -> Unit raise {
  let cache = new_report_rt_quoted_cache()
  let strings : Map[String, String] = Map([])
  for name in ["🙂", "\u0000", "__proto__", "é", "é"] {
    assert_eq(report_rt_cache_get(cache, name), "")
    let value = report_rt_cached_quote(cache, strings, name)
    assert_eq(value, Json(name).stringify())
    assert_eq(report_rt_cache_get(cache, name), value)
    assert_eq(strings.at(name), value)
    assert_eq(report_rt_cached_quote(cache, strings, name), value)
  }
}

///|
#cfg(not(target="js"))
fn rtquote038_check_cache_quotes() -> Unit raise {
  let strings : Map[String, String] = Map([])
  for name in ["🙂", "\u0000", "__proto__", "é", "é"] {
    assert_true(strings.get(name) is None)
    let value = quoted_cached(strings, name)
    assert_eq(value, Json(name).stringify())
    assert_eq(strings.at(name), value)
    assert_eq(quoted_cached(strings, name), value)
  }
}

///|
test "rtquote038 12 cached values retain official quotes and the original MoonBit Map" {
  rtquote038_check_cache_quotes()
}

///|
test "rtquote038 13 all 49770 realtime edges retain complete report evidence and counters" {
  let transactions : Array[Transaction] = []
  for index in 0..<316 {
    let time = index.to_int64() * 2L
    transactions.push(
      tx("T" + index.to_string(), [], start=Some(time), end=Some(time + 1L)),
    )
  }
  let history : History = {
    model: StrictSerializable,
    initial: Map([]),
    version_orders: Map([]),
    transactions,
  }
  let report = analyze(history)
  assert_eq(report.edges.length(), 49770)
  assert_true(report.outcome == Consistent)
  assert_true(!report.graph.edge_budget_exceeded)
  let expected = report_json(report).stringify()
  let encoded = report_string(report)
  assert_true(encoded.length() > 9000000)
  assert_eq(encoded, expected)
  assert_eq(report_json(report).stringify(), expected)
}

///|
test "rtquote038 14 no-edge reports preserve all ordinary report and coverage fields" {
  for history in [hist([]), skew(), completion_noise(6)] {
    let report = analyze(history)
    assert_eq(report_string(report), report_json(report).stringify())
  }
}
