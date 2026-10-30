///|
fn classification_test_result(
  trace : Json,
  options~ : String = "{}",
) -> Json raise {
  @json.parse(classify_v3_json(trace.stringify(), options))
}

///|
fn classification_test_rule(report : Json, category : String) -> Json {
  object_fields_unchecked_v3(object_fields_unchecked_v3(report).at("rules")).at(
    category,
  )
}

///|
fn classification_test_cycle_trace(
  category : String,
  noise~ : Bool = false,
) -> Json {
  let body : Array[Json] = [
    { "kind": "begin", "tx": "A", "connection": "a" },
    { "kind": "begin", "tx": "B", "connection": "b" },
  ]
  if category == "G0" {
    body.push({
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "x1",
      "predecessor": "x0",
    })
    body.push({
      "kind": "write",
      "tx": "B",
      "key": "y",
      "version": "y1",
      "predecessor": "y0",
    })
    body.push({
      "kind": "write",
      "tx": "A",
      "key": "y",
      "version": "y2",
      "predecessor": "y1",
    })
    body.push({
      "kind": "write",
      "tx": "B",
      "key": "x",
      "version": "x2",
      "predecessor": "x1",
    })
  } else if category == "G1c" {
    body.push({
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "x1",
      "predecessor": "x0",
    })
    body.push({
      "kind": "write",
      "tx": "B",
      "key": "y",
      "version": "y1",
      "predecessor": "y0",
    })
    body.push({ "kind": "read", "tx": "A", "key": "y", "version": "y1" })
    body.push({ "kind": "read", "tx": "B", "key": "x", "version": "x1" })
  } else {
    body.push({ "kind": "read", "tx": "A", "key": "y", "version": "y0" })
    body.push({ "kind": "read", "tx": "B", "key": "x", "version": "x0" })
    body.push({
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "x1",
      "predecessor": "x0",
    })
    body.push({
      "kind": "write",
      "tx": "B",
      "key": "y",
      "version": "y1",
      "predecessor": "y0",
    })
  }
  body.push({ "kind": "commit_request", "tx": "A" })
  body.push({ "kind": "commit_ok", "tx": "A" })
  body.push({ "kind": "commit_request", "tx": "B" })
  body.push({ "kind": "commit_ok", "tx": "B" })
  if noise {
    body.push({ "kind": "begin", "tx": "N", "connection": "n" })
    body.push({ "kind": "read", "tx": "N", "key": "x", "version": "x0" })
    body.push({ "kind": "commit_request", "tx": "N" })
    body.push({ "kind": "commit_ok", "tx": "N" })
  }
  v3_test_trace(body)
}

///|
test "classification25 G0 retains a pure write cycle and G1 implication" {
  let report = classification_test_result(classification_test_cycle_trace("G0"))
  assert_eq(capture_field(report, "status"), Json("refuted"))
  assert_eq(
    capture_field(classification_test_rule(report, "G0"), "status"),
    Json("refuted"),
  )
  assert_eq(
    capture_field(classification_test_rule(report, "G1c"), "status"),
    Json("refuted"),
  )
  assert_eq(
    capture_field(report, "impliedAnomalies"),
    Json(["G0", "G1c", "G1"]),
  )
  assert_eq(capture_field(report, "acceptsIsolationModels"), Json(false))
}

///|
test "classification25 WR cycle is found independently of G0" {
  let report = classification_test_result(
    classification_test_cycle_trace("G1c"),
  )
  assert_eq(
    capture_field(classification_test_rule(report, "G1c"), "status"),
    Json("refuted"),
  )
  assert_eq(
    capture_field(classification_test_rule(report, "G0"), "status"),
    Json("checked-compatible"),
  )
}

///|
test "classification25 item anti-dependency cycle is found" {
  let report = classification_test_result(
    classification_test_cycle_trace("G2-item"),
  )
  assert_eq(
    capture_field(classification_test_rule(report, "G2-item"), "status"),
    Json("refuted"),
  )
  assert_eq(
    capture_field(classification_test_rule(report, "G0"), "status"),
    Json("checked-compatible"),
  )
  assert_eq(capture_field(report, "impliedAnomalies"), Json(["G2-item", "G2"]))
}

///|
test "classification25 zero budget is unknown, never no cycle" {
  let report = classification_test_result(
    classification_test_cycle_trace("G2-item"),
    options="{\"maxStates\":0,\"maxEdgeChecks\":0}",
  )
  assert_eq(capture_field(report, "status"), Json("inconclusive"))
  assert_eq(
    capture_field(classification_test_rule(report, "G2-item"), "status"),
    Json("unknown"),
  )
}

///|
test "classification25 empty dependency graph completes even with zero budget" {
  let report = classification_test_result(
    v3_test_completed([]),
    options="{\"maxStates\":0,\"maxEdgeChecks\":0}",
  )
  assert_eq(capture_field(report, "status"), Json("checked-compatible"))
}

///|
test "classification25 unsupported model stays unsupported" {
  let trace = classification_test_cycle_trace("G2-item")
  object_fields_unchecked_v3(trace)["dataModel"] = Json("append-list-v1")
  assert_eq(
    capture_field(classification_test_result(trace), "status"),
    Json("unsupported"),
  )
}

///|
test "classification25 incomplete source facts never become compatible" {
  let trace = classification_test_cycle_trace("G2-item")
  object_fields_unchecked_v3(trace)["gaps"] = Json([
    { "code": "lost", "message": "event lost" },
  ])
  let report = classification_test_result(trace)
  assert_eq(capture_field(report, "status"), Json("inconclusive"))
}

///|
test "classification25 source proof retains all original matching reads" {
  let trace = classification_test_cycle_trace("G1c")
  let report = classification_test_result(trace)
  let rule = classification_test_rule(report, "G1c")
  let evidence = capture_field(rule, "evidence")
  let edges = v3_test_items(evidence, "edges")
  assert_eq(edges.length(), 2)
  for edge in edges {
    assert_true(!v3_test_items(edge, "fromObservationSeq").is_empty())
    assert_true(!v3_test_items(edge, "toObservationSeq").is_empty())
  }
  assert_eq(
    capture_field(capture_field(report, "normalized"), "observations"),
    capture_field(trace, "events"),
  )
}

///|
test "classification25 verifier binds original text including whitespace" {
  let text = classification_test_cycle_trace("G2-item").stringify()
  let report = classify_v3_json(text, "{}")
  assert_eq(
    capture_field(
      @json.parse(verify_classification_v3_json(text, report)),
      "valid",
    ),
    Json(true),
  )
  assert_eq(
    capture_field(
      @json.parse(verify_classification_v3_json(text + " ", report)),
      "valid",
    ),
    Json(false),
  )
}

///|
test "classification25 verifier rejects rule, budget and source tampering" {
  let text = classification_test_cycle_trace("G2-item").stringify()
  let report = @json.parse(classify_v3_json(text, "{}"))
  object_fields_unchecked_v3(classification_test_rule(report, "G2-item"))["status"] = Json(
    "checked-compatible",
  )
  assert_eq(
    capture_field(
      @json.parse(verify_classification_v3_json(text, report.stringify())),
      "valid",
    ),
    Json(false),
  )
  let report = @json.parse(classify_v3_json(text, "{}"))
  object_fields_unchecked_v3(
    capture_field(capture_field(report, "execution"), "classificationOptions"),
  )["maxStates"] = Json(0)
  assert_eq(
    capture_field(
      @json.parse(verify_classification_v3_json(text, report.stringify())),
      "valid",
    ),
    Json(false),
  )
  let report = @json.parse(classify_v3_json(text, "{}"))
  object_fields_unchecked_v3(report)["sourceTraceText"] = Json("{}")
  assert_eq(
    capture_field(
      @json.parse(verify_classification_v3_json(text, report.stringify())),
      "valid",
    ),
    Json(false),
  )
}

///|
test "classification25 options reject duplicate labels and out-of-range budgets" {
  let text = classification_test_cycle_trace("G0").stringify()
  for
    options in [
      "{\"categories\":[\"G0\",\"G0\"]}", "{\"categories\":[]}", "{\"maxStates\":100001}",
      "{\"maxEdgeChecks\":1.5}", "{\"unknown\":1}",
    ] {
    assert_eq(
      capture_field(@json.parse(classify_v3_json(text, options)), "status"),
      Json("invalid"),
    )
  }
}

///|
test "classification25 reduction preserves the requested category and single-delete result" {
  let trace = classification_test_cycle_trace("G2-item", noise=true)
  let reduced = @json.parse(
    reduce_classification_v3_json(
      trace.stringify(),
      "{\"category\":\"G2-item\"}",
    ),
  )
  assert_eq(capture_field(reduced, "status"), Json("reduced"))
  assert_eq(capture_field(reduced, "removed"), Json(["N"]))
  assert_eq(capture_field(reduced, "oneMinimal"), Json(true))
  assert_true(
    classification_v3_rule_refuted(capture_field(reduced, "report"), "G2-item"),
  )
  let reduced_text = match capture_field(reduced, "reducedTraceText") {
    String(value) => value
    _ => fail("Missing reduced trace text")
  }
  assert_eq(
    capture_field(
      @json.parse(
        verify_classification_v3_json(
          reduced_text,
          capture_field(reduced, "report").stringify(),
        ),
      ),
      "valid",
    ),
    Json(true),
  )
}

///|
test "classification25 reduction refuses another category and honors zero checks" {
  let text = classification_test_cycle_trace("G2-item", noise=true).stringify()
  let other = @json.parse(
    reduce_classification_v3_json(text, "{\"category\":\"G0\"}"),
  )
  assert_eq(capture_field(other, "status"), Json("not-refuted"))
  let limited = @json.parse(
    reduce_classification_v3_json(
      text, "{\"category\":\"G2-item\",\"maxChecks\":0}",
    ),
  )
  assert_eq(capture_field(limited, "status"), Json("budget"))
  assert_eq(capture_field(limited, "oneMinimal"), Json(false))
}

///|
fn classification_test_edge(
  from : Int32,
  to : Int32,
  kind : Dependency,
) -> Edge {
  {
    from: from.to_string(),
    to: to.to_string(),
    kind,
    key: Some("k"),
    from_op: Some(0),
    to_op: Some(0),
    from_version: Some("a"),
    to_version: Some("b"),
    reason: "typed-graph algorithm test only",
  }
}

///|
fn classification_test_oracle(kinds : Array[Int32], category : String) -> Bool {
  let pairs = [(0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1)]
  let matrix = Array::make(9, 0)
  for i, pair in pairs {
    matrix[pair.0 * 3 + pair.1] = kinds[i]
  }
  // Enumerate every simple 2/3-cycle; this does not call the production search.
  for a in 0..<3 {
    for b in 0..<3 {
      if a == b {
        continue
      }
      let candidates = [
        [matrix[a * 3 + b], matrix[b * 3 + a]],
        [
          matrix[a * 3 + b],
          matrix[b * 3 + (3 - a - b)],
          matrix[(3 - a - b) * 3 + a],
        ],
      ]
      for cycle in candidates {
        if cycle.contains(0) {
          continue
        }
        let good = match category {
          "G0" => cycle.all(k => k == 1)
          "G1c" => cycle.all(k => k == 1 || k == 2)
          _ => cycle.contains(3)
        }
        if good {
          return true
        }
      }
    }
  }
  false
}

///|
test "classification25 all 4096 typed three-node graphs agree with simple-cycle oracle" {
  let transactions : Array[Transaction] = [
    { id: "0", status: Committed, ops: [], start: None, end: None, },
    { id: "1", status: Committed, ops: [], start: None, end: None, },
    { id: "2", status: Committed, ops: [], start: None, end: None, },
  ]
  let pairs = [(0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1)]
  for code in 0..<4096 {
    let mut remainder = code
    let kinds : Array[Int32] = []
    let edges : Array[Edge] = []
    for pair in pairs {
      let kind = remainder % 4
      remainder /= 4
      kinds.push(kind)
      if kind != 0 {
        edges.push(
          classification_test_edge(
            pair.0,
            pair.1,
            match kind {
              1 => WW
              2 => WR
              _ => RW
            },
          ),
        )
      }
    }
    let graph = adjacency(transactions, edges)
    for category in ["G0", "G1c", "G2-item"] {
      let budget : ClassificationV3Budget = {
        max_states: 100000,
        max_edge_checks: 1000000,
        states: 0,
        edge_checks: 0,
        limited: false,
        reason: "complete",
      }
      let found = classification_v3_cycle(
        transactions, edges, graph, category, budget,
      )
      assert_eq(!found.is_empty(), classification_test_oracle(kinds, category))
      assert_eq(budget.limited, false)
      if !found.is_empty() {
        assert_true(found.all(e => classification_v3_allowed(e.kind, category)))
        assert_true(found.any(e => classification_v3_seed(e.kind, category)))
        assert_eq(found[0].from, found[found.length() - 1].to)
        let seen : Map[String, Bool] = Map([])
        for edge in found {
          assert_eq(seen.contains(edge.from), false)
          seen[edge.from] = true
        }
      }
    }
  }
}

///|
test "classification25 category search skips shorter cycles outside the requested rule" {
  let transactions : Array[Transaction] = []
  for index in 0..<8 {
    transactions.push({
      id: index.to_string(),
      status: Committed,
      ops: [],
      start: None,
      end: None,
    })
  }
  let edges = [
    classification_test_edge(0, 1, WW),
    classification_test_edge(1, 0, WW),
    classification_test_edge(2, 3, WR),
    classification_test_edge(3, 4, WW),
    classification_test_edge(4, 2, WW),
    classification_test_edge(5, 6, RW),
    classification_test_edge(6, 7, WW),
    classification_test_edge(7, 5, RW),
  ]
  for category in ["G0", "G1c", "G2-item"] {
    // Under the public logical closure, a WW cycle also refutes G1c.
    // For that request, use a shorter RW-only cycle that genuinely does
    // not refute G1c, retaining the independent long-WR search assertion.
    let candidates = if category == "G1c" {
      edges.map(edge => {
        if edge.from == "0" || edge.from == "1" {
          { ..edge, kind: RW, }
        } else {
          edge
        }
      })
    } else {
      edges
    }
    let graph = adjacency(transactions, candidates)
    let budget : ClassificationV3Budget = {
      max_states: 100000,
      max_edge_checks: 1000000,
      states: 0,
      edge_checks: 0,
      limited: false,
      reason: "complete",
    }
    let found = classification_v3_cycle(
      transactions, candidates, graph, category, budget,
    )
    assert_eq(found.length(), if category == "G0" { 2 } else { 3 })
  }
}

///|
test "classification25 reliable refutation survives another category budget limit" {
  let trace = v3_test_trace([
    { "kind": "begin", "tx": "A", "connection": "a" },
    { "kind": "begin", "tx": "B", "connection": "b" },
    { "kind": "begin", "tx": "C", "connection": "c" },
    { "kind": "begin", "tx": "D", "connection": "d" },
    {
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "x1",
      "predecessor": "x0",
    },
    {
      "kind": "write",
      "tx": "B",
      "key": "y",
      "version": "y1",
      "predecessor": "y0",
    },
    {
      "kind": "write",
      "tx": "A",
      "key": "y",
      "version": "y2",
      "predecessor": "y1",
    },
    {
      "kind": "write",
      "tx": "B",
      "key": "x",
      "version": "x2",
      "predecessor": "x1",
    },
    {
      "kind": "write",
      "tx": "C",
      "key": "x",
      "version": "x3",
      "predecessor": "x2",
    },
    {
      "kind": "write",
      "tx": "D",
      "key": "x",
      "version": "x4",
      "predecessor": "x3",
    },
    { "kind": "commit_request", "tx": "A" },
    { "kind": "commit_ok", "tx": "A" },
    { "kind": "commit_request", "tx": "B" },
    { "kind": "commit_ok", "tx": "B" },
    { "kind": "commit_request", "tx": "C" },
    { "kind": "commit_ok", "tx": "C" },
    { "kind": "commit_request", "tx": "D" },
    { "kind": "commit_ok", "tx": "D" },
  ])
  let report = classification_test_result(
    trace,
    options="{\"maxEdgeChecks\":3}",
  )
  assert_eq(capture_field(report, "status"), Json("refuted"))
  assert_eq(
    capture_field(classification_test_rule(report, "G0"), "status"),
    Json("refuted"),
  )
  assert_eq(
    capture_field(classification_test_rule(report, "G2-item"), "status"),
    Json("unknown"),
  )
}

///|
test "classification25 invalid diagnostics can be reproduced without accepting them" {
  let text = "{broken"
  let report = classify_v3_json(text, "{}")
  assert_eq(capture_field(@json.parse(report), "status"), Json("invalid"))
  assert_eq(
    capture_field(
      @json.parse(verify_classification_v3_json(text, report)),
      "valid",
    ),
    Json(true),
  )
  let valid_text = classification_test_cycle_trace("G0").stringify()
  let bad_options = classify_v3_json(valid_text, "{\"maxStates\":100001}")
  assert_eq(
    capture_field(
      @json.parse(verify_classification_v3_json(valid_text, bad_options)),
      "valid",
    ),
    Json(true),
  )
}

///|
test "classification25 raw rolled-back operations cannot bypass the 4096 limit" {
  let body : Array[Json] = [
    { "kind": "begin", "tx": "A", "connection": "a" },
    { "kind": "savepoint", "tx": "A", "name": "s", "instance": "s1" },
  ]
  let mut predecessor = "x0"
  for index in 0..<4097 {
    let version = "v" + index.to_string()
    body.push({
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": Json(version),
      "predecessor": Json(predecessor),
    })
    predecessor = version
  }
  body.push({ "kind": "rollback_to", "tx": "A", "instance": "s1" })
  body.push({ "kind": "commit_request", "tx": "A" })
  body.push({ "kind": "commit_ok", "tx": "A" })
  let report = classification_test_result(v3_test_trace(body))
  assert_eq(capture_field(report, "status"), Json("inconclusive"))
  assert_eq(
    capture_field(classification_test_rule(report, "G0"), "status"),
    Json("unknown"),
  )
}

///|
test "classification25 frozen WW-only history refutes an independent G1c request" {
  let trace = classification_test_cycle_trace("G0")
  let report = classification_test_result(
    trace,
    options="{\"categories\":[\"G1c\"]}",
  )
  assert_eq(capture_field(report, "status"), Json("refuted"))
  let rule = classification_test_rule(report, "G1c")
  assert_eq(capture_field(rule, "status"), Json("refuted"))
  assert_eq(
    capture_field(capture_field(rule, "evidence"), "specificCategory"),
    Json("G0"),
  )
  assert_eq(
    capture_field(report, "impliedAnomalies"),
    Json(["G0", "G1c", "G1"]),
  )
}
