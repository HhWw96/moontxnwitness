///|
fn rpred_read(
  tx : String,
  rows : Array[Json],
  predicate~ : Array[Json] = [{ "column": "value", "op": "eq", "value": "yes" }],
  complete~ : Bool = true,
) -> Json {
  {
    "kind": "row_read",
    "tx": Json(tx),
    "relation": "items",
    "predicate": Json(predicate),
    "rows": Json(rows),
    "complete": Json(complete),
  }
}

///|
fn rpred_history(body : Array[Json], empty~ : Bool = false) -> HistoryV4 {
  parse_history_v4(rpg_trace(body, empty~).stringify()).unwrap()
}

///|
fn rpred_graph(
  body : Array[Json],
  empty~ : Bool = false,
  max_graph_checks~ : Int32 = 1000000,
  max_predicate_checks~ : Int32 = 1000000,
  max_candidate_visits~ : Int32 = 100000,
) -> RelationPredicateGraphV4 {
  build_relation_predicate_graph_v4(
    rpred_history(body, empty~),
    max_graph_checks~,
    max_predicate_checks~,
    max_candidate_visits~,
  ).unwrap()
}

///|
fn rpred_edges(
  graph : RelationPredicateGraphV4,
  scope : String,
  kind : Dependency,
) -> Array[RelationScopedEdgeV4] {
  graph.scoped_edges.filter(edge => {
    edge.scope == scope && edge.dependency.kind == kind
  })
}

///|
fn rpred_has(
  graph : RelationPredicateGraphV4,
  scope : String,
  kind : Dependency,
  from : String,
  to : String,
) -> Bool {
  rpred_edges(graph, scope, kind).any(edge => {
    edge.dependency.from == from && edge.dependency.to == to
  })
}

///|
fn rpred_gap(graph : RelationPredicateGraphV4, code : String) -> Bool {
  graph.gaps.any(gap => {
    object_fields_unchecked_v3(gap).get("code") == Some(Json(code))
  })
}

///|
fn rpred_empty_skew() -> Array[Json] {
  let body = [
    rpg_begin("A"),
    rpg_begin("B"),
    rpred_read("A", []),
    rpred_read("B", []),
    rpg_write("A", "1", "a1", None, action="insert", value="yes"),
    rpg_write("B", "2", "b1", None, action="insert", value="yes"),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  body
}

///|
test "relation predicate 01 complete empty SELECT skew yields predicate RW without fabricated item reads" {
  let graph = rpred_graph(rpred_empty_skew(), empty=true)
  assert_true(graph.complete)
  assert_true(rpred_has(graph, "predicate", RW, "A", "B"))
  assert_true(rpred_has(graph, "predicate", RW, "B", "A"))
  assert_eq(graph.scoped_edges.length(), 2)
  assert_true(rpred_edges(graph, "item", RW).is_empty())
  assert_true(rpred_edges(graph, "item", WR).is_empty())
}

///|
fn rpred_false_true_false() -> Array[Json] {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "a1", Some("v0"), value="yes"),
  ]
  rpg_commit(body, "A")
  body.push(rpg_begin("B"))
  body.push(rpg_write("B", "1", "b1", Some("a1"), value="no"))
  rpg_commit(body, "B")
  body.push(rpg_begin("Q"))
  body.push(rpred_read("Q", []))
  rpg_commit(body, "Q")
  body
}

///|
test "relation predicate 02 F T F negative selection is ambiguous and cannot choose a source" {
  let graph = rpred_graph(rpred_false_true_false())
  assert_false(graph.complete)
  assert_true(rpred_gap(graph, "predicate-negative-source-ambiguous"))
  assert_true(rpred_has(graph, "item", WW, "A", "B"))
  assert_true(rpred_edges(graph, "predicate", WR).is_empty())
  assert_true(rpred_edges(graph, "predicate", RW).is_empty())
  let domain = graph.queries[0].domains[0]
  assert_eq(v3_test_items(domain, "candidateSources").length(), 2)
  assert_eq(capture_field(domain, "inferredConstraintOnly"), Json(true))
}

///|
fn rpred_toggle_history() -> Array[Json] {
  let body : Array[Json] = []
  let mut predecessor = "v0"
  for
    (tx, version, value) in [
      ("A", "a1", "yes"),
      ("B", "b1", "zzz"),
      ("C", "c1", "no"),
      ("D", "d1", "yes"),
    ] {
    body.push(rpg_begin(tx))
    body.push(rpg_write(tx, "1", version, Some(predecessor), value~))
    rpg_commit(body, tx)
    predecessor = version
  }
  body.push(rpg_begin("Q"))
  body.push(
    rpred_read("Q", [rpg_row("1", "b1", value="zzz")], predicate=[
      { "column": "value", "op": "ge", "value": "yes" },
    ]),
  )
  rpg_commit(body, "Q")
  body
}

///|
test "relation predicate 03 toggle is local previous membership rather than selected versus later membership" {
  let graph = rpred_graph(rpred_toggle_history())
  assert_true(graph.complete)
  assert_true(rpred_has(graph, "item", WR, "B", "Q"))
  assert_true(rpred_has(graph, "predicate", WR, "A", "Q"))
  assert_false(rpred_has(graph, "predicate", WR, "B", "Q"))
  assert_true(rpred_has(graph, "item", RW, "Q", "C"))
  assert_false(rpred_has(graph, "item", RW, "Q", "D"))
  assert_true(rpred_has(graph, "predicate", RW, "Q", "C"))
  assert_true(rpred_has(graph, "predicate", RW, "Q", "D"))
}

///|
fn rpred_competing_deletes(mode : String) -> Array[Json] {
  let body = [rpg_begin("A")]
  if mode == "revoked" {
    body.push({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "s1" })
  }
  body.push(rpg_write("A", "1", "da", Some("v0"), action="delete"))
  if mode == "aborted" {
    body.push({ "kind": "rollback_ok", "tx": "A" })
  } else if mode == "revoked" {
    body.push({ "kind": "rollback_to", "tx": "A", "instance": "s1" })
    rpg_commit(body, "A")
  } else {
    body.push({ "kind": "commit_request", "tx": "A" })
  }
  body.push(rpg_begin("B"))
  body.push(rpg_write("B", "1", "db", Some("v0"), action="delete"))
  rpg_commit(body, "B")
  body.push(rpg_begin("Q"))
  body.push(
    rpred_read("Q", [], predicate=[
      { "column": "id", "op": "eq", "value": "1" },
      { "column": "value", "op": "eq", "value": "same" },
    ]),
  )
  rpg_commit(body, "Q")
  body
}

///|
test "relation predicate 04 unreturned row considers aborted revoked and unconfirmed raw delete sources" {
  for mode in ["aborted", "revoked", "unknown"] {
    let graph = rpred_graph(rpred_competing_deletes(mode))
    assert_false(graph.complete)
    assert_true(rpred_gap(graph, "predicate-candidate-source-not-installed"))
    assert_true(rpred_edges(graph, "predicate", WR).is_empty())
    let domain = graph.queries[0].domains[0]
    assert_eq(v3_test_items(domain, "candidateSources").length(), 2)
  }
}

///|
test "relation predicate 05 SQL modification and RETURNING zero rows do not become an empty SELECT" {
  let body = [
    rpg_begin("A"),
    (
      {
        "kind": "statement",
        "tx": "A",
        "sql": "DELETE FROM items WHERE value='yes' RETURNING *",
      } : Json),
    (
      { "kind": "condition", "tx": "A", "predicate": {}, "matched": false } :
      Json),
  ]
  rpg_commit(body, "A")
  let graph = rpred_graph(body)
  assert_false(graph.complete)
  assert_true(graph.queries.is_empty())
  assert_true(graph.scoped_edges.is_empty())
  assert_true(rpred_gap(graph, "predicate-program-prefix-unproven"))
}

///|
test "relation predicate 06 equal returned item and predicate dependencies retain separate scopes" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "a1", Some("v0"), value="yes"),
  ]
  rpg_commit(body, "A")
  body.push(rpg_begin("Q"))
  body.push(rpred_read("Q", [rpg_row("1", "a1", value="yes")]))
  rpg_commit(body, "Q")
  let graph = rpred_graph(body)
  assert_true(graph.complete)
  assert_true(rpred_has(graph, "item", WR, "A", "Q"))
  assert_true(rpred_has(graph, "predicate", WR, "A", "Q"))
  assert_eq(graph.scoped_edges.length(), 2)
  assert_false(graph.scoped_edges[0] == graph.scoped_edges[1])
}

///|
test "relation predicate 07 incomplete actual delivery cannot infer an absent result" {
  let body = [rpg_begin("Q"), rpred_read("Q", [], complete=false)]
  rpg_commit(body, "Q")
  let graph = rpred_graph(body)
  assert_false(graph.complete)
  assert_true(rpred_gap(graph, "predicate-result-not-completely-delivered"))
  assert_true(graph.scoped_edges.is_empty())
}

///|
test "relation predicate 08 missing initial table coverage leaves a wildcard source" {
  let trace = rpg_trace(rpred_false_true_false())
  object_fields_unchecked_v3(capture_field(trace, "scope"))["completeSnapshotTables"] = Json(
    ([] : Array[Json]),
  )
  let graph = build_relation_predicate_graph_v4(
    parse_history_v4(trace.stringify()).unwrap(),
  ).unwrap()
  assert_false(graph.complete)
  assert_true(rpred_gap(graph, "predicate-negative-window-not-closed"))
  assert_eq(
    capture_field(graph.queries[0].domains[0], "wildcardSource"),
    Json(true),
  )
  assert_true(rpred_edges(graph, "predicate", RW).is_empty())
}

///|
test "relation predicate 09 missing original window events do not become complete" {
  let trace = rpg_trace(rpred_empty_skew(), empty=true)
  object_fields_unchecked_v3(trace)["gaps"] = Json([
    { "code": "dropped-event", "message": "An event is missing" },
  ])
  let graph = build_relation_predicate_graph_v4(
    parse_history_v4(trace.stringify()).unwrap(),
  ).unwrap()
  assert_false(graph.complete)
  assert_true(rpred_gap(graph, "predicate-input-window-unproven"))
  assert_true(rpred_edges(graph, "predicate", RW).is_empty())
}

///|
test "relation predicate 10 returned row must satisfy the requested typed predicate" {
  let body = [rpg_begin("Q"), rpred_read("Q", [rpg_row("1", "v0")])]
  rpg_commit(body, "Q")
  let graph = rpred_graph(body)
  assert_false(graph.complete)
  assert_true(
    rpred_gap(graph, "returned-row-does-not-prove-predicate-membership"),
  )
  assert_true(graph.scoped_edges.is_empty())
}

///|
test "relation predicate 11 missing returned version remains a source gap" {
  let body = [
    rpg_begin("Q"),
    rpred_read("Q", [rpg_row("1", "missing", value="yes")]),
  ]
  rpg_commit(body, "Q")
  let graph = rpred_graph(body)
  assert_true(rpred_gap(graph, "predicate-returned-row-source-missing"))
  assert_false(graph.complete)
  assert_true(graph.scoped_edges.is_empty())
}

///|
test "relation predicate 12 duplicate returned key cannot prove a full result set" {
  let body = [
    rpg_begin("Q"),
    rpred_read("Q", [rpg_row("1", "v0"), rpg_row("1", "v0")]),
  ]
  rpg_commit(body, "Q")
  let graph = rpred_graph(body)
  assert_true(rpred_gap(graph, "predicate-result-key-or-uniqueness-mismatch"))
  assert_false(graph.complete)
}

///|
test "relation predicate 13 primary key range AND field equality scans only matching returned objects" {
  let body = [
    rpg_begin("Q"),
    rpred_read("Q", [rpg_row("2", "u0")], predicate=[
      { "column": "id", "op": "ge", "value": "2" },
      { "column": "id", "op": "lt", "value": "3" },
      { "column": "value", "op": "eq", "value": "same" },
    ]),
  ]
  rpg_commit(body, "Q")
  let graph = rpred_graph(body)
  assert_true(graph.complete)
  assert_true(graph.scoped_edges.is_empty())
  assert_eq(graph.queries[0].domains.length(), 3)
}

///|
test "relation predicate 14 empty AND is a complete table SELECT and cannot omit a present row" {
  let body = [rpg_begin("Q"), rpred_read("Q", [], predicate=[])]
  rpg_commit(body, "Q")
  let graph = rpred_graph(body)
  assert_false(graph.complete)
  assert_true(rpred_gap(graph, "predicate-negative-has-no-observed-source"))
}

///|
test "relation predicate 15 partial candidate enumeration cannot emit edges from truncated ranks" {
  let graph = rpred_graph(rpred_false_true_false(), max_candidate_visits=1)
  assert_false(graph.complete)
  assert_true(graph.predicate_budget.limited)
  assert_eq(graph.predicate_budget.candidates, 1)
  assert_true(rpred_edges(graph, "predicate", WR).is_empty())
  assert_true(rpred_edges(graph, "predicate", RW).is_empty())
  assert_eq(capture_field(graph.queries[0].domains[0], "closed"), Json(false))
}

///|
test "relation predicate 16 zero evaluation budget never claims predicate completion" {
  let graph = rpred_graph(
    rpred_empty_skew(),
    empty=true,
    max_predicate_checks=0,
  )
  assert_false(graph.complete)
  assert_eq(graph.predicate_budget.evaluations, 0)
  assert_true(rpred_gap(graph, "predicate-evaluation-budget"))
  assert_true(graph.scoped_edges.is_empty())
}

///|
test "relation predicate 17 exact observed budgets complete while one fewer cannot" {
  let body = rpred_empty_skew()
  let full = rpred_graph(body, empty=true)
  let exact = rpred_graph(
    rpred_empty_skew(),
    empty=true,
    max_graph_checks=full.graph_checks,
    max_predicate_checks=full.predicate_budget.evaluations,
    max_candidate_visits=full.predicate_budget.candidates,
  )
  assert_true(exact.complete)
  assert_true(exact.scoped_edges == full.scoped_edges)
  let short = rpred_graph(
    rpred_empty_skew(),
    empty=true,
    max_predicate_checks=full.predicate_budget.evaluations - 1,
  )
  assert_false(short.complete)
  assert_true(short.predicate_budget.limited)
  assert_eq(
    short.predicate_budget.evaluations,
    full.predicate_budget.evaluations - 1,
  )
}

///|
test "relation predicate 18 zero source budget is an explicit gap and no invented edge" {
  let graph = rpred_graph(rpred_empty_skew(), empty=true, max_graph_checks=0)
  assert_false(graph.complete)
  assert_true(graph.graph_limited)
  assert_eq(graph.graph_checks, 0)
  assert_true(graph.scoped_edges.is_empty())
}

///|
test "relation predicate 19 verifier caller budgets cannot be raised by the supplied record" {
  let history = rpred_history(rpred_empty_skew(), empty=true)
  let graph = build_relation_predicate_graph_v4(history).unwrap()
  let record = relation_predicate_graph_v4_json(graph)
  assert_true(verify_relation_predicate_graph_v4(history, record))
  assert_false(
    verify_relation_predicate_graph_v4(history, record, max_predicate_checks=0),
  )
  assert_false(
    verify_relation_predicate_graph_v4(history, record, max_candidate_visits=0),
  )
  assert_false(
    verify_relation_predicate_graph_v4(history, record, max_graph_checks=0),
  )
}

///|
test "relation predicate 20 source scope conclusion candidate and budget tampering are rejected" {
  let history = rpred_history(rpred_empty_skew(), empty=true)
  let graph = build_relation_predicate_graph_v4(history).unwrap()
  for kind in ["scope", "semantic", "conclusion", "candidate", "budget"] {
    let record = relation_predicate_graph_v4_json(graph)
    let fields = object_fields_unchecked_v3(record)
    match kind {
      "scope" =>
        object_fields_unchecked_v3(v3_test_items(record, "scopedEdges")[0])["scope"] = Json(
          "item",
        )
      "semantic" => fields["semanticContract"] = Json("adya-1999")
      "conclusion" => fields["complete"] = Json(false)
      "budget" =>
        object_fields_unchecked_v3(v4_test_at(record, ["execution", "limits"]))["graphChecks"] = Json(
          999999,
        )
      _ => {
        let queries = v3_test_items(
          capture_field(record, "inferences"),
          "queries",
        )
        let domain = v3_test_items(queries[0], "candidateDomains")[0]
        object_fields_unchecked_v3(domain)["candidateSources"] = Json(
          ([] : Array[Json]),
        )
      }
    }
    assert_false(verify_relation_predicate_graph_v4(history, record))
  }
}

///|
test "relation predicate 21 output mutation does not alias source history or later reports" {
  let history = rpred_history(rpred_empty_skew(), empty=true)
  let graph = build_relation_predicate_graph_v4(history).unwrap()
  let before = history_v4_json(history)
  let record = relation_predicate_graph_v4_json(graph)
  object_fields_unchecked_v3(record)["observations"] = Json::null()
  let edges = graph.edges()
  edges.clear()
  assert_eq(history_v4_json(history), before)
  assert_eq(graph.edges().length(), 2)
  assert_true(
    verify_relation_predicate_graph_v4(
      history,
      relation_predicate_graph_v4_json(graph),
    ),
  )
}

///|
test "relation predicate 22 actual own delivered rows survive later rollback without dirty read accusation" {
  let body = [
    rpg_begin("A"),
    ({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "s1" } : Json),
    rpg_write("A", "1", "a1", Some("v0"), value="yes"),
    rpred_read("A", [rpg_row("1", "a1", value="yes")]),
    ({ "kind": "rollback_to", "tx": "A", "instance": "s1" } : Json),
  ]
  rpg_commit(body, "A")
  let graph = rpred_graph(body)
  assert_false(graph.complete)
  assert_true(
    rpred_gap(graph, "predicate-own-view-needs-installed-order-proof"),
  )
  assert_true(graph.diagnostics.is_empty())
  assert_eq(
    capture_field(graph.queries[0].domains[0], "ownAtDelivery"),
    Json(true),
  )
  assert_eq(
    v4_test_at(graph.queries[0].domains[0], ["candidateSources"]),
    Json([
      relation_point_source_json_v4(graph.index, graph.index.versions.at("a1")),
    ]),
  )
}

///|
test "relation predicate 23 own matching row omitted from complete query is a real local result gap" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "a1", Some("v0"), value="yes"),
    rpred_read("A", []),
  ]
  rpg_commit(body, "A")
  let graph = rpred_graph(body)
  assert_false(graph.complete)
  assert_true(rpred_gap(graph, "predicate-own-matching-row-not-delivered"))
  assert_true(graph.diagnostics.is_empty())
}

///|
test "relation predicate 24 raw delete and reinsert do not claim physical incarnation equivalence" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "d1", Some("v0"), action="delete"),
    rpg_write("A", "1", "a1", Some("d1"), action="insert", value="yes"),
  ]
  rpg_commit(body, "A")
  body.push(rpg_begin("Q"))
  body.push(rpred_read("Q", [rpg_row("1", "a1", value="yes")]))
  rpg_commit(body, "Q")
  let graph = rpred_graph(body)
  assert_false(graph.complete)
  assert_true(rpred_gap(graph, "physical-incarnation-equivalence-unproven"))
  assert_true(rpred_gap(graph, "predicate-incarnation-source-unproven"))
  assert_eq(
    v4_test_at(relation_predicate_graph_v4_json(graph), [
      "objectAdapter", "physicalEntityIncarnationEquivalence",
    ]),
    Json("not-claimed"),
  )
}

///|
test "relation predicate 25 aborted actual returned item is a source proof not a chosen negative source" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "a1", Some("v0"), value="yes"),
    ({ "kind": "rollback_ok", "tx": "A" } : Json),
    rpg_begin("Q"),
    rpred_read("Q", [rpg_row("1", "a1", value="yes")]),
  ]
  rpg_commit(body, "Q")
  let graph = rpred_graph(body)
  assert_false(graph.complete)
  assert_eq(capture_field(graph.diagnostics[0], "code"), Json("G1a"))
  assert_true(graph.scoped_edges.is_empty())
}

///|
test "relation predicate 26 intermediate actual returned item is identified separately from membership edges" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "a1", Some("v0"), value="yes"),
    rpg_write("A", "1", "a2", Some("a1"), value="yes"),
  ]
  rpg_commit(body, "A")
  body.push(rpg_begin("Q"))
  body.push(rpred_read("Q", [rpg_row("1", "a1", value="yes")]))
  rpg_commit(body, "Q")
  let graph = rpred_graph(body)
  assert_false(graph.complete)
  assert_eq(capture_field(graph.diagnostics[0], "code"), Json("G1b"))
  assert_true(rpred_edges(graph, "predicate", WR).is_empty())
}

///|
test "relation predicate 27 repeated queries keep every actual query identity" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "a1", Some("v0"), value="yes"),
  ]
  rpg_commit(body, "A")
  body.push(rpg_begin("Q"))
  for _ in 0..<2 {
    body.push(rpred_read("Q", [rpg_row("1", "a1", value="yes")]))
  }
  rpg_commit(body, "Q")
  let graph = rpred_graph(body)
  assert_true(graph.complete)
  assert_eq(rpred_edges(graph, "item", WR).length(), 2)
  assert_eq(rpred_edges(graph, "predicate", WR).length(), 2)
  assert_true(graph.scoped_edges.any(edge => edge.dependency.to_op == Some(0)))
  assert_true(graph.scoped_edges.any(edge => edge.dependency.to_op == Some(1)))
}

///|
test "relation predicate 28 opaque delimiter identities cannot collide in scope deduplication" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "a|:x\u0000", Some("v0"), value="yes"),
  ]
  rpg_commit(body, "A")
  body.push(rpg_begin("Q"))
  body.push(rpred_read("Q", [rpg_row("1", "a|:x\u0000", value="yes")]))
  rpg_commit(body, "Q")
  let graph = rpred_graph(body)
  assert_true(graph.complete)
  assert_eq(graph.scoped_edges.length(), 2)
  assert_eq(graph.scoped_edges[0].dependency.from_version, Some("a|:x\u0000"))
}

///|
test "relation predicate 29 unconfirmed transaction outcome remains an explicit coverage gap" {
  let graph = rpred_graph([
    rpg_begin("A"),
    rpg_write("A", "1", "a1", Some("v0"), value="yes"),
    { "kind": "commit_request", "tx": "A" },
  ])
  assert_false(graph.complete)
  assert_true(rpred_gap(graph, "predicate-transaction-outcome-unconfirmed"))
}

///|
test "relation predicate 30 register histories cannot be relabeled as predicate captures" {
  let history = parse_history_v4(
    "{\"initial\":{\"x\":\"x0\"},\"transactions\":[]}",
  ).unwrap()
  assert_true(build_relation_predicate_graph_v4(history) is Err(_))
}

///|
test "relation predicate 31 missing producer prevents a closed negative window even for earlier queries" {
  let body = rpred_empty_skew()
  body.push(rpg_begin("Q"))
  body.push(rpred_read("Q", [rpg_row("1", "missing", value="yes")]))
  rpg_commit(body, "Q")
  let graph = rpred_graph(body, empty=true)
  assert_false(graph.complete)
  assert_true(rpred_gap(graph, "predicate-returned-row-source-missing"))
  assert_true(rpred_gap(graph, "predicate-negative-window-not-closed"))
  assert_true(rpred_edges(graph, "predicate", RW).is_empty())
}

///|
test "relation predicate 32 independently sourced positive predicate cycle survives a missing source elsewhere" {
  let body = [
    rpg_begin("A"),
    rpg_begin("B"),
    rpg_write("A", "1", "a1", Some("v0"), value="yes"),
    rpg_write("B", "2", "b1", Some("u0"), value="yes"),
    rpred_read("A", [
      rpg_row("1", "a1", value="yes"),
      rpg_row("2", "b1", value="yes"),
    ]),
    rpred_read("B", [
      rpg_row("1", "a1", value="yes"),
      rpg_row("2", "b1", value="yes"),
    ]),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  body.push(rpg_begin("Q"))
  body.push(rpred_read("Q", [rpg_row("3", "missing", value="yes")]))
  rpg_commit(body, "Q")
  let graph = rpred_graph(body)
  assert_false(graph.complete)
  assert_true(rpred_gap(graph, "predicate-returned-row-source-missing"))
  assert_true(rpred_has(graph, "item", WR, "A", "B"))
  assert_true(rpred_has(graph, "item", WR, "B", "A"))
  assert_true(rpred_has(graph, "predicate", WR, "A", "B"))
  assert_true(rpred_has(graph, "predicate", WR, "B", "A"))
}

///|
fn rpred_mask_membership(mask : Int32, rank : Int32) -> Bool {
  if rank == 0 {
    return false
  }
  let mut divisor = 1
  for _ in 1..<rank {
    divisor *= 2
  }
  mask / divisor % 2 == 1
}

///|
fn rpred_oracle_chain(
  length : Int32,
  mask : Int32,
  selected : Int32,
) -> Array[Json] {
  let body : Array[Json] = []
  for rank in 1..<(length + 1) {
    let tx = "T" + rank.to_string()
    body.push(rpg_begin(tx))
    body.push(
      rpg_write(
        tx,
        "1",
        "v" + rank.to_string(),
        Some("v" + (rank - 1).to_string()),
        value=if rpred_mask_membership(mask, rank) { "yes" } else { "no" },
      ),
    )
    rpg_commit(body, tx)
  }
  body.push(rpg_begin("Q"))
  body.push(
    rpred_read(
      "Q",
      if selected < 0 {
        []
      } else {
        [rpg_row("1", "v" + selected.to_string(), value="yes")]
      },
    ),
  )
  rpg_commit(body, "Q")
  body
}

///|
test "relation predicate 33 1024 frozen chain selections equal independent intersection of concrete ghost choices" {
  let mut histories = 0
  let mut masks = 1
  for length in 0..<8 {
    for mask in 0..<masks {
      let selections = [-1]
      for rank in 1..<(length + 1) {
        if rpred_mask_membership(mask, rank) {
          selections.push(rank)
        }
      }
      for selected in selections {
        let graph = rpred_graph(rpred_oracle_chain(length, mask, selected))
        let concrete : Array[Int32] = []
        if selected >= 0 {
          concrete.push(selected)
        } else {
          for rank in 0..<(length + 1) {
            if !rpred_mask_membership(mask, rank) {
              concrete.push(rank)
            }
          }
        }
        for rank in 1..<(length + 1) {
          let toggle = rpred_mask_membership(mask, rank) !=
            rpred_mask_membership(mask, rank - 1)
          let expected_wr = toggle && concrete.all(choice => rank <= choice)
          let expected_rw = toggle && concrete.all(choice => rank > choice)
          let tx = "T" + rank.to_string()
          assert_eq(rpred_has(graph, "predicate", WR, tx, "Q"), expected_wr)
          assert_eq(rpred_has(graph, "predicate", RW, "Q", tx), expected_rw)
          assert_eq(rpred_has(graph, "item", WR, tx, "Q"), selected == rank)
          assert_eq(
            rpred_has(graph, "item", RW, "Q", tx),
            selected >= 0 && rank == selected + 1,
          )
        }
        // Independent concrete-choice oracle: derive the entire predicate
        // dependency set for each ghost position and compare those sets.
        let concrete_edge_sets = concrete.map(choice => {
          let dependencies : Array[String] = []
          for rank in 1..<(length + 1) {
            if rpred_mask_membership(mask, rank) !=
              rpred_mask_membership(mask, rank - 1) {
              dependencies.push(
                (if rank <= choice { "WR-" } else { "RW-" }) + rank.to_string(),
              )
            }
          }
          dependencies
        })
        assert_eq(
          graph.complete,
          concrete_edge_sets.all(edges => edges == concrete_edge_sets[0]),
        )
        histories += 1
      }
    }
    masks *= 2
  }
  assert_eq(histories, 1024)
}

///|
test "relation predicate 34 Def3 retains all prior and equal membership toggles as separately sourced dependencies" {
  let graph = rpred_graph(rpred_oracle_chain(3, 5, 3))
  assert_true(graph.complete)
  for tx in ["T1", "T2", "T3"] {
    assert_true(rpred_has(graph, "predicate", WR, tx, "Q"))
  }
  assert_eq(rpred_edges(graph, "predicate", WR).length(), 3)
  assert_eq(rpred_edges(graph, "item", WR).length(), 1)
}

///|
test "relation predicate 35 equivalent nonmatches retain their universally later toggle and complete" {
  let graph = rpred_graph(rpred_oracle_chain(2, 2, -1))
  assert_true(graph.complete)
  assert_false(rpred_gap(graph, "predicate-negative-source-ambiguous"))
  assert_true(rpred_has(graph, "predicate", RW, "Q", "T2"))
  assert_false(rpred_has(graph, "predicate", RW, "Q", "T1"))
  assert_true(rpred_edges(graph, "predicate", WR).is_empty())
  let edge = rpred_edges(graph, "predicate", RW)[0]
  let proof = graph.sources.at(edge)[0]
  assert_eq(capture_field(proof, "minimumInstalledRank"), Json(0))
  assert_eq(capture_field(proof, "maximumInstalledRank"), Json(1))
  assert_eq(v3_test_items(proof, "candidateSources").length(), 2)
}

///|
test "relation predicate 36 intermediate nonmatching source is retained without assuming the target model already holds" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "a1", Some("v0"), value="no"),
    rpg_write("A", "1", "a2", Some("a1"), value="yes"),
  ]
  rpg_commit(body, "A")
  body.push(rpg_begin("Q"))
  body.push(rpred_read("Q", []))
  rpg_commit(body, "Q")
  let graph = rpred_graph(body)
  assert_false(graph.complete)
  assert_true(rpred_gap(graph, "predicate-candidate-source-not-installed"))
  assert_eq(
    v3_test_items(graph.queries[0].domains[0], "candidateSources").length(),
    2,
  )
  assert_false(rpred_has(graph, "predicate", RW, "Q", "A"))
}

///|
test "relation predicate 37 equal business values have distinct item writers but only a changed predicate writer" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "a1", Some("v0"), value="yes"),
  ]
  rpg_commit(body, "A")
  body.push(rpg_begin("B"))
  body.push(rpg_write("B", "1", "b1", Some("a1"), value="yes"))
  rpg_commit(body, "B")
  body.push(rpg_begin("Q"))
  body.push(rpred_read("Q", [rpg_row("1", "b1", value="yes")]))
  rpg_commit(body, "Q")
  let graph = rpred_graph(body)
  assert_true(graph.complete)
  assert_true(rpred_has(graph, "item", WR, "B", "Q"))
  assert_false(rpred_has(graph, "item", WR, "A", "Q"))
  assert_true(rpred_has(graph, "predicate", WR, "A", "Q"))
  assert_false(rpred_has(graph, "predicate", WR, "B", "Q"))
}

///|
test "relation predicate 38 typed bool membership uses the common parser and no string coercion" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "a1", Some("v0"), value="yes"),
  ]
  rpg_commit(body, "A")
  body.push(rpg_begin("Q"))
  body.push(rpred_read("Q", [rpg_row("1", "a1", value="yes")]))
  rpg_commit(body, "Q")
  let trace = rpg_trace(body)
  object_fields_unchecked_v3(
    v4_test_at(trace, ["relationSchema", "items", "columns"]),
  )["value"] = Json("bool")
  for event in v3_test_items(trace, "events") {
    match capture_field(event, "kind") {
      String("snapshot") =>
        for row in v3_test_items(capture_field(event, "initial"), "items") {
          object_fields_unchecked_v3(capture_field(row, "values"))["value"] = Json(
            false,
          )
        }
      String("row_write") =>
        object_fields_unchecked_v3(capture_field(event, "values"))["value"] = Json(
          true,
        )
      String("row_read") => {
        for row in v3_test_items(event, "rows") {
          object_fields_unchecked_v3(capture_field(row, "values"))["value"] = Json(
            true,
          )
        }
        object_fields_unchecked_v3(v3_test_items(event, "predicate")[0])["value"] = Json(
          true,
        )
      }
      _ => ()
    }
  }
  let graph = build_relation_predicate_graph_v4(
    parse_history_v4(trace.stringify()).unwrap(),
  ).unwrap()
  assert_true(graph.complete)
  assert_true(rpred_has(graph, "predicate", WR, "A", "Q"))
  assert_true(rpred_has(graph, "item", WR, "A", "Q"))
}

///|
test "relation predicate 39 exact int64 primary range includes its upper endpoint without numeric rounding" {
  let key = "9223372036854775807"
  let body = [rpg_begin("A"), rpg_write("A", key, "a1", None, action="insert")]
  rpg_commit(body, "A")
  body.push(rpg_begin("Q"))
  body.push(
    rpred_read("Q", [rpg_row(key, "a1")], predicate=[
      { "column": "id", "op": "ge", "value": Json(key) },
      { "column": "id", "op": "le", "value": Json(key) },
    ]),
  )
  rpg_commit(body, "Q")
  let graph = rpred_graph(body)
  assert_true(graph.complete)
  assert_true(rpred_has(graph, "predicate", WR, "A", "Q"))
  let edge = rpred_edges(graph, "predicate", WR)[0]
  assert_eq(
    v4_test_at(graph.sources.at(edge)[0], ["identity", "primaryKey"]),
    Json(key),
  )
}

///|
test "relation predicate 40 a raw later delete is not discarded using cross connection event sequence" {
  let body = [
    rpg_begin("B"),
    rpg_write("B", "1", "db", Some("v0"), action="delete"),
  ]
  rpg_commit(body, "B")
  body.push(rpg_begin("Q"))
  body.push(
    rpred_read("Q", [], predicate=[
      { "column": "id", "op": "eq", "value": "1" },
      { "column": "value", "op": "eq", "value": "same" },
    ]),
  )
  body.push(rpg_begin("A"))
  body.push(rpg_write("A", "1", "da", Some("v0"), action="delete"))
  body.push({ "kind": "rollback_ok", "tx": "A" })
  rpg_commit(body, "Q")
  let graph = rpred_graph(body)
  assert_false(graph.complete)
  assert_eq(
    v3_test_items(graph.queries[0].domains[0], "candidateSources").length(),
    2,
  )
  assert_false(rpred_has(graph, "predicate", WR, "B", "Q"))
}

///|
test "relation predicate 41 nested proof JSON edits do not leak into later output or original history" {
  let history = rpred_history(rpred_empty_skew(), empty=true)
  let graph = build_relation_predicate_graph_v4(history).unwrap()
  let before = history_v4_json(history)
  let record = relation_predicate_graph_v4_json(graph)
  let proof = v3_test_items(v3_test_items(record, "scopedEdges")[0], "sources")[0]
  object_fields_unchecked_v3(v4_test_at(proof, ["query", "original"]))["kind"] = Json(
    "forged-select",
  )
  assert_eq(history_v4_json(history), before)
  assert_false(verify_relation_predicate_graph_v4(history, record))
  assert_true(
    verify_relation_predicate_graph_v4(
      history,
      relation_predicate_graph_v4_json(graph),
    ),
  )
}

///|
test "relation predicate 42 installed WW source retains the entire original intermediate write path" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "a1", Some("v0"), value="yes"),
    rpg_write("A", "1", "a2", Some("a1"), value="yes"),
  ]
  rpg_commit(body, "A")
  body.push(rpg_begin("B"))
  body.push(rpg_write("B", "1", "b1", Some("a2"), value="no"))
  body.push(rpg_write("B", "1", "b2", Some("b1"), value="yes"))
  rpg_commit(body, "B")
  let graph = rpred_graph(body)
  assert_true(graph.complete)
  let edge = rpred_edges(graph, "item", WW)[0]
  let path = v3_test_items(graph.sources.at(edge)[0], "predecessorPath")
  assert_eq(path.length(), 3)
  assert_eq(v4_test_at(path[0], ["fact", "version"]), Json("b2"))
  assert_eq(v4_test_at(path[1], ["fact", "version"]), Json("b1"))
  assert_eq(v4_test_at(path[2], ["fact", "version"]), Json("a2"))
  assert_true(
    path.all(source => {
      v4_test_at(source, ["original", "kind"]) == Json("row_write")
    }),
  )
}

///|
test "relation predicate 43 repeated savepoint names keep distinct local incarnations and delivered reads" {
  let body = [
    rpg_begin("A"),
    ({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "outer" } : Json),
    rpg_write("A", "1", "a1", Some("v0"), value="yes"),
    ({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "inner" } : Json),
    rpg_write("A", "1", "a2", Some("a1"), value="no"),
    rpred_read("A", []),
    ({ "kind": "rollback_to", "tx": "A", "instance": "inner" } : Json),
    rpred_read("A", [rpg_row("1", "a1", value="yes")]),
    ({ "kind": "release", "tx": "A", "instance": "inner" } : Json),
    ({ "kind": "rollback_to", "tx": "A", "instance": "outer" } : Json),
    rpred_read("A", []),
  ]
  rpg_commit(body, "A")
  let graph = rpred_graph(body)
  assert_eq(graph.queries.length(), 3)
  assert_eq(graph.queries[0].own.at(0), graph.index.versions.at("a2"))
  assert_eq(graph.queries[1].own.at(0), graph.index.versions.at("a1"))
  assert_false(graph.queries[2].own.contains(0))
  assert_true(graph.diagnostics.is_empty())
  assert_false(rpred_gap(graph, "predicate-own-matching-row-not-delivered"))
  assert_false(rpred_gap(graph, "predicate-own-delivered-row-state-mismatch"))
}

///|
test "relation predicate 44 identical textual PKs in two relation types retain separate structured identities" {
  let trace = rpg_trace([])
  object_fields_unchecked_v3(capture_field(trace, "relationSchema"))["labels"] = (
    { "primaryKey": "name", "columns": { "name": "text", "value": "text" } } :
    Json)
  let snapshot = v3_test_items(trace, "events")[0]
  object_fields_unchecked_v3(capture_field(snapshot, "initial"))["labels"] = Json([
      rpg_row("1", "label0"),
    ],
  )
  object_fields_unchecked_v3(capture_field(trace, "scope"))["completeSnapshotTables"] = Json([
      "items", "labels",
    ],
  )
  let graph = build_relation_predicate_graph_v4(
    parse_history_v4(trace.stringify()).unwrap(),
  ).unwrap()
  assert_true(graph.complete)
  assert_eq(graph.index.keys.length(), 4)
  let identities = graph.index.keys.mapi((i, _) => {
    relation_point_key_json_v4(graph.index, i)
  })
  assert_eq(
    identities
    .filter(identity => capture_field(identity, "primaryKey") == Json("1"))
    .length(),
    2,
  )
  assert_eq(
    identities
    .filter(identity => capture_field(identity, "primaryType") == Json("text"))
    .length(),
    1,
  )
}

///|
test "relation predicate 45 input metadata binds unused schema even when graph edges do not change" {
  let first = rpg_trace([], empty=true)
  let first_history = parse_history_v4(first.stringify()).unwrap()
  let report = relation_predicate_graph_v4_json(
    build_relation_predicate_graph_v4(first_history).unwrap(),
  )
  let second = rpg_trace([], empty=true)
  object_fields_unchecked_v3(
    v4_test_at(second, ["relationSchema", "items", "columns"]),
  )["value"] = Json("bool")
  let second_history = parse_history_v4(second.stringify()).unwrap()
  assert_false(verify_relation_predicate_graph_v4(second_history, report))
  assert_eq(
    v4_test_at(report, [
      "inputContract", "relationSchema", "items", "columns", "value",
    ]),
    Json("text"),
  )
  assert_eq(
    v4_test_at(report, ["inputContract", "scope", "exclusiveWriters"]),
    Json(true),
  )
}

///|
test "relation predicate 46 a later unmodeled statement does not erase an earlier independently sourced positive edge" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "a1", Some("v0"), value="yes"),
  ]
  rpg_commit(body, "A")
  body.push(rpg_begin("Q"))
  body.push(rpred_read("Q", [rpg_row("1", "a1", value="yes")]))
  body.push({
    "kind": "statement",
    "tx": "Q",
    "sql": "SELECT unknown_future_effect()",
  })
  rpg_commit(body, "Q")
  let graph = rpred_graph(body)
  assert_false(graph.complete)
  assert_true(rpred_has(graph, "item", WR, "A", "Q"))
  assert_true(rpred_has(graph, "predicate", WR, "A", "Q"))
  assert_true(rpred_gap(graph, "predicate-program-prefix-unproven"))
}

///|
test "relation predicate 47 incomplete candidate work cannot mark its query complete" {
  let graph = rpred_graph(rpred_false_true_false(), max_candidate_visits=1)
  assert_false(graph.complete)
  assert_false(graph.queries[0].complete)
  assert_eq(capture_field(graph.queries[0].domains[0], "closed"), Json(false))
  let output = relation_predicate_graph_v4_json(graph)
  let query = v3_test_items(capture_field(output, "inferences"), "queries")[0]
  assert_eq(capture_field(query, "complete"), Json(false))
}

///|
test "relation predicate 36 all installed versions exclude predicate without inventing a source" {
  let graph = rpred_graph(rpred_oracle_chain(7, 0, -1))
  assert_true(graph.complete)
  assert_true(rpred_edges(graph, "predicate", WR).is_empty())
  assert_true(rpred_edges(graph, "predicate", RW).is_empty())
  let domain = graph.queries[0].domains[0]
  assert_eq(v4_test_at(domain, ["actualReturnedRow"]), Json(false))
  assert_eq(v4_test_at(domain, ["inferredConstraintOnly"]), Json(true))
}

///|
test "relation predicate 37 nonmatches on opposite sides of membership change remain unknown" {
  let graph = rpred_graph(rpred_oracle_chain(3, 2, -1))
  assert_false(graph.complete)
  assert_true(rpred_gap(graph, "predicate-negative-source-ambiguous"))
}

///|
test "relation predicate 38 proving equivalent exclusions still consumes predicate budget" {
  let graph = rpred_graph(rpred_oracle_chain(7, 0, -1), max_predicate_checks=0)
  assert_false(graph.complete)
  assert_true(graph.predicate_budget.limited)
}
