///|
fn leg_test_graph(
  body : Array[Json],
  max_checks~ : Int32 = 1000000,
) -> EffectiveListGraphV4 raise {
  list_graph_effective_v4(
    list_v3_parse(classification26_test_list(body).stringify()),
    max_checks~,
  )
}

///|
test "effective list graph 01 own multi append order is retained" {
  let result = leg_test_graph([
    { "kind": "begin", "tx": "A", "connection": "a" },
    { "kind": "append", "tx": "A", "key": "x", "id": "a1", "value": "same" },
    { "kind": "append", "tx": "A", "key": "x", "id": "a2", "value": "same" },
    {
      "kind": "list_read",
      "tx": "A",
      "key": "x",
      "items": [
        { "id": "a1", "value": "same" },
        { "id": "a2", "value": "same" },
      ],
    },
    { "kind": "commit_request", "tx": "A" },
    { "kind": "commit_ok", "tx": "A" },
  ])
  assert_true(result.base.complete)
  assert_true(result.index.journal_complete)
  assert_eq(result.index.reads.length(), 1)
  assert_true(result.index.reads[0].usable)
  assert_eq(
    list_effective_item_ids_v4(
      result.index.parsed,
      result.index.reads[0].own_at_read,
    ),
    ["a1", "a2"],
  )
  assert_eq(result.index.intrinsic.length(), 1)
}

///|
fn leg_test_begin(id : String) -> Json {
  { "kind": "begin", "tx": Json(id), "connection": Json(id) }
}

///|
fn leg_test_append(
  tx : String,
  id : String,
  key~ : String = "x",
  value~ : String = "same",
) -> Json {
  {
    "kind": "append",
    "tx": Json(tx),
    "key": Json(key),
    "id": Json(id),
    "value": Json(value),
  }
}

///|
fn leg_test_read(tx : String, ids : Array[String], key~ : String = "x") -> Json {
  {
    "kind": "list_read",
    "tx": Json(tx),
    "key": Json(key),
    "items": Json(ids.map(id => ({ "id": Json(id), "value": "same" } : Json))),
  }
}

///|
fn leg_test_commit(body : Array[Json], tx : String) -> Unit {
  body.push({ "kind": "commit_request", "tx": Json(tx) })
  body.push({ "kind": "commit_ok", "tx": Json(tx) })
}

///|
fn leg_test_external(ids : Array[String]) -> Array[Json] {
  let body = [
    leg_test_begin("A"),
    leg_test_append("A", "a1"),
    leg_test_append("A", "a2"),
  ]
  leg_test_commit(body, "A")
  body.push(leg_test_begin("R"))
  body.push(leg_test_read("R", ids))
  leg_test_commit(body, "R")
  body
}

///|
fn leg_test_has_gap(result : EffectiveListGraphV4, code : String) -> Bool {
  result.index.gaps.any(gap => {
    object_fields_unchecked_v3(gap).get("code") == Some(Json(code))
  })
}

///|
test "effective list graph 02 external complete multi append read retains every source" {
  let result = leg_test_graph(leg_test_external(["a1", "a2"]))
  assert_true(result.base.complete)
  assert_eq(result.base.edges.filter(edge => edge.kind == WR).length(), 2)
  assert_eq(result.base.edges.filter(edge => edge.kind == RW).length(), 0)
  for edge in result.base.edges {
    assert_false(result.base.sources.at(edge).is_empty())
    assert_true(edge.from == "A" && edge.to == "R")
  }
}

///|
test "effective list graph 03 external intermediate prefix is isolated from graph claims" {
  let result = leg_test_graph(leg_test_external(["a1"]))
  assert_false(result.base.complete)
  assert_true(leg_test_has_gap(result, "external-intermediate-list-prefix"))
  assert_false(result.index.reads[0].usable)
  assert_true(result.base.edges.is_empty())
  assert_true(result.index.reads_complete)
}

///|
test "effective list graph 04 missing writer prefix is unknown and cannot manufacture G2" {
  let result = leg_test_graph(leg_test_external(["a2"]))
  assert_false(result.base.complete)
  assert_true(leg_test_has_gap(result, "missing-or-reordered-writer-prefix"))
  assert_true(result.base.edges.is_empty())
  assert_true(
    g_single_cycle_v4(
      result.base.transactions.length(),
      result.base.edges,
      adjacency(result.base.transactions, result.base.edges),
      gs_test_budget(),
    ).is_empty(),
  )
}

///|
test "effective list graph 05 interleaved transaction blocks retain incompatible WW evidence" {
  let body = [
    leg_test_begin("A"),
    leg_test_begin("B"),
    leg_test_append("A", "a1"),
    leg_test_append("B", "b"),
    leg_test_append("A", "a2"),
  ]
  leg_test_commit(body, "A")
  leg_test_commit(body, "B")
  body.push(leg_test_begin("R"))
  body.push(leg_test_read("R", ["a1", "b", "a2"]))
  leg_test_commit(body, "R")
  let result = leg_test_graph(body)
  assert_true(result.index.reads[0].usable)
  assert_false(result.base.complete)
  assert_true(
    leg_test_has_gap(result, "incompatible-effective-transaction-order"),
  )
  let cycle = classification_v3_cycle(
    result.base.transactions,
    result.base.edges,
    adjacency(result.base.transactions, result.base.edges),
    "G0",
    gs_test_budget(),
  )
  assert_eq(cycle.length(), 2)
  assert_true(cycle.all(edge => edge.kind == WW))
  for edge in cycle {
    assert_false(result.base.sources.at(edge).is_empty())
  }
}

///|
fn leg_test_rollback_body() -> Array[Json] {
  let body = [
    leg_test_begin("A"),
    leg_test_append("A", "a1"),
    ({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "s1" } : Json),
    leg_test_append("A", "a2"),
    leg_test_read("A", ["a1", "a2"]),
    ({ "kind": "rollback_to", "tx": "A", "instance": "s1" } : Json),
    leg_test_append("A", "a3"),
    leg_test_read("A", ["a1", "a3"]),
  ]
  leg_test_commit(body, "A")
  body
}

///|
test "effective list graph 06 past own read survives rollback while final append set changes" {
  let result = leg_test_graph(leg_test_rollback_body())
  assert_true(result.base.complete)
  assert_eq(result.index.reads.length(), 2)
  assert_true(result.index.reads.all(read => read.usable))
  assert_eq(
    list_effective_item_ids_v4(
      result.index.parsed,
      result.index.reads[0].own_at_read,
    ),
    ["a1", "a2"],
  )
  assert_eq(
    list_effective_item_ids_v4(
      result.index.parsed,
      result.index.reads[1].own_at_read,
    ),
    ["a1", "a3"],
  )
  assert_eq(
    list_effective_item_ids_v4(
      result.index.parsed,
      result.index.groups.at("x").at("A"),
    ),
    ["a1", "a3"],
  )
  assert_eq(v3_test_items(result.base.normalized, "effects").length(), 3)
  assert_eq(
    capture_field(
      list_v3_analyze_parsed(result.index.parsed, {
        max_states: 100000,
        max_operations: 1000000,
      }),
      "status",
    ),
    Json("consistent"),
  )
}

///|
test "effective list graph 07 external revoked read cannot poison a valid earlier own read" {
  let body = leg_test_rollback_body()
  body.push(leg_test_begin("R"))
  body.push(leg_test_read("R", ["a1", "a2"]))
  leg_test_commit(body, "R")
  let result = leg_test_graph(body)
  assert_true(result.index.reads[0].usable)
  assert_true(result.index.reads[1].usable)
  assert_false(result.index.reads[2].usable)
  assert_eq(
    list_effective_item_ids_v4(
      result.index.parsed,
      result.index.reads[0].own_at_read,
    ),
    ["a1", "a2"],
  )
  assert_false(result.base.complete)
  assert_false(
    result.base.edges.any(edge => {
      edge.to == "R" && edge.from_version == Some("a2")
    }),
  )
}

///|
test "effective list graph 08 equal business values retain independent identities and multi edges" {
  let body = [
    leg_test_begin("A"),
    leg_test_append("A", "a1"),
    leg_test_append("A", "a2"),
    leg_test_begin("B"),
    leg_test_append("B", "b1"),
  ]
  leg_test_commit(body, "A")
  leg_test_commit(body, "B")
  body.push(leg_test_begin("R"))
  body.push(leg_test_read("R", ["a1", "a2", "b1"]))
  leg_test_commit(body, "R")
  let result = leg_test_graph(body)
  assert_true(result.base.complete)
  assert_eq(result.index.active.length(), 3)
  assert_eq(result.base.edges.filter(edge => edge.kind == WR).length(), 3)
  assert_eq(result.base.edges.filter(edge => edge.kind == WW).length(), 2)
}

///|
test "effective list graph 09 nested same-name marks use instance identities" {
  let body : Array[Json] = [
    leg_test_begin("A"),
    leg_test_append("A", "a1"),
    {
      "kind": "savepoint",
      "tx": "A",
      "name": "same|name",
      "instance": "outer|1",
    },
    leg_test_append("A", "a2"),
    {
      "kind": "savepoint",
      "tx": "A",
      "name": "same|name",
      "instance": "inner|2",
    },
    leg_test_append("A", "a3"),
    leg_test_read("A", ["a1", "a2", "a3"]),
    { "kind": "rollback_to", "tx": "A", "instance": "inner|2" },
    leg_test_read("A", ["a1", "a2"]),
    { "kind": "release", "tx": "A", "instance": "inner|2" },
    { "kind": "rollback_to", "tx": "A", "instance": "outer|1" },
    leg_test_append("A", "a4"),
    leg_test_read("A", ["a1", "a4"]),
    { "kind": "release", "tx": "A", "instance": "outer|1" },
  ]
  leg_test_commit(body, "A")
  let result = leg_test_graph(body)
  assert_true(result.base.complete)
  assert_true(result.index.reads.all(read => read.usable))
  assert_eq(
    list_effective_item_ids_v4(
      result.index.parsed,
      result.index.groups.at("x").at("A"),
    ),
    ["a1", "a4"],
  )
  assert_eq(
    list_effective_item_ids_v4(
      result.index.parsed,
      result.index.reads[1].own_at_read,
    ),
    ["a1", "a2"],
  )
}

///|
test "effective list graph 10 missing source remains visible and yields no graph acceptance" {
  let body = [leg_test_begin("R"), leg_test_read("R", ["missing|id"])]
  leg_test_commit(body, "R")
  let result = leg_test_graph(body)
  assert_false(result.base.complete)
  assert_false(result.index.reads[0].usable)
  assert_true(result.base.edges.is_empty())
  assert_eq(
    capture_field(
      v3_test_items(list_graph_effective_v4_json(result), "readStates")[0],
      "observed",
    ),
    Json([Json::null()]),
  )
  assert_false(result.index.gaps.is_empty())
}

///|
test "effective list graph 11 exact construction budget completes and smaller budget stays unknown" {
  let body = leg_test_rollback_body()
  let full = leg_test_graph(body)
  let exact = leg_test_graph(body, max_checks=full.checks)
  assert_true(exact.base.complete)
  assert_false(exact.limited)
  assert_eq(exact.checks, full.checks)
  let limited = leg_test_graph(body, max_checks=full.checks - 1)
  assert_false(limited.base.complete)
  assert_true(limited.limited)
  assert_eq(limited.checks, full.checks - 1)
  assert_eq(
    v4_test_at(list_graph_effective_v4_json(limited), [
      "execution", "limits", "constructionChecks",
    ]),
    Json(full.checks - 1),
  )
}

///|
test "effective list graph 12 explicit opaque builder rejects wrong models and invalid budgets" {
  let register = register_history_v4(skew()).unwrap()
  assert_true(build_list_graph_effective_v4(register) is Err(_))
  let snapshot = parse_history_v4(
    classification26_test_list(leg_test_external(["a1", "a2"])).stringify(),
  ).unwrap()
  assert_true(build_list_graph_effective_v4(snapshot, max_checks=-1) is Err(_))
  assert_true(
    build_list_graph_effective_v4(snapshot, max_checks=1000001) is Err(_),
  )
  let result = build_list_graph_effective_v4(snapshot).unwrap()
  let original = list_graph_effective_v4_json(result)
  let exported = list_graph_effective_v4_json(result)
  let groups = v3_test_items(exported, "effectiveGroups")
  object_fields_unchecked_v3(groups[0])["items"] = Json(["changed"])
  assert_eq(list_graph_effective_v4_json(result), original)
}

///|
test "effective list graph 13 an own read before a future append uses its actual program position" {
  let body = [
    leg_test_begin("A"),
    leg_test_append("A", "a1"),
    leg_test_read("A", ["a1"]),
    leg_test_append("A", "a2"),
  ]
  leg_test_commit(body, "A")
  let result = leg_test_graph(body)
  assert_true(result.base.complete)
  assert_true(result.index.reads[0].usable)
  assert_eq(
    list_effective_item_ids_v4(
      result.index.parsed,
      result.index.reads[0].own_at_read,
    ),
    ["a1"],
  )
  assert_eq(
    list_effective_item_ids_v4(
      result.index.parsed,
      result.index.groups.at("x").at("A"),
    ),
    ["a1", "a2"],
  )
  assert_true(result.base.edges.is_empty())
}

///|
test "effective list graph 14 releasing a mark is not a transaction commit" {
  let result = leg_test_graph([
    leg_test_begin("A"),
    { "kind": "savepoint", "tx": "A", "name": "s", "instance": "s1" },
    leg_test_append("A", "a1"),
    leg_test_read("A", ["a1"]),
    { "kind": "release", "tx": "A", "instance": "s1" },
  ])
  assert_false(result.base.complete)
  assert_true(result.index.active.is_empty())
  assert_true(result.index.outcomes.get("A") == Some(Unknown))
  assert_eq(
    list_effective_item_ids_v4(
      result.index.parsed,
      result.index.reads[0].own_at_read,
    ),
    ["a1"],
  )
}

///|
test "effective list graph 15 unobserved cross-transaction append order is never guessed" {
  let body = [
    leg_test_begin("A"),
    leg_test_append("A", "a1"),
    leg_test_append("A", "a2"),
    leg_test_begin("B"),
    leg_test_append("B", "b1"),
    leg_test_append("B", "b2"),
  ]
  leg_test_commit(body, "A")
  leg_test_commit(body, "B")
  let result = leg_test_graph(body)
  assert_false(result.base.complete)
  assert_true(leg_test_has_gap(result, "missing-effective-transaction-order"))
  assert_true(result.base.edges.is_empty())
  assert_eq(result.index.intrinsic.length(), 2)
}

///|
test "effective list graph 16 repeated reads retain all original evidence for each edge" {
  let body = leg_test_external(["a1", "a2"])
  // Add another committed reader so source edges retain distinct identities.
  body.push(leg_test_begin("R2"))
  body.push(leg_test_read("R2", ["a1", "a2"]))
  body.push(leg_test_read("R2", ["a1", "a2"]))
  leg_test_commit(body, "R2")
  let result = leg_test_graph(body)
  assert_true(result.base.complete)
  let edges = result.base.edges.filter(edge => {
    edge.kind == WR && edge.to == "R2"
  })
  assert_eq(edges.length(), 2)
  for edge in edges {
    assert_eq(result.base.sources.at(edge).length(), 2)
  }
  assert_eq(
    v3_test_items(list_graph_effective_v4_json(result), "edgeSources").length(),
    result.base.edges.length(),
  )
}

///|
test "effective list graph 17 missing initial prefix is quarantined" {
  let trace = classification26_test_list(leg_test_external(["a1", "a2"]))
  let events = v3_test_items(trace, "events")
  object_fields_unchecked_v3(events[0])["initial"] = {
    "x": [{ "id": "initial", "value": "same" }],
    "y": [],
  }
  let result = list_graph_effective_v4(list_v3_parse(trace.stringify()))
  assert_false(result.base.complete)
  assert_true(leg_test_has_gap(result, "missing-or-reordered-initial-prefix"))
  assert_true(result.base.edges.is_empty())
}

///|
test "effective list graph 18 multi-append writer supports a genuine one-RW witness" {
  let body = [
    leg_test_begin("A"),
    leg_test_begin("B"),
    leg_test_read("B", []),
    leg_test_append("A", "a1"),
    leg_test_append("A", "a2"),
    leg_test_append("A", "ay", key="y"),
    leg_test_read("B", ["ay"], key="y"),
  ]
  leg_test_commit(body, "A")
  leg_test_commit(body, "B")
  let result = leg_test_graph(body)
  assert_true(result.base.complete)
  assert_eq(
    result.base.edges
    .filter(edge => edge.kind == RW && edge.key == Some("x"))
    .length(),
    2,
  )
  let cycle = g_single_cycle_v4(
    result.base.transactions.length(),
    result.base.edges,
    adjacency(result.base.transactions, result.base.edges),
    gs_test_budget(),
  )
  assert_eq(cycle.length(), 2)
  assert_eq(cycle.filter(edge => edge.kind == RW).length(), 1)
  assert_eq(cycle[0].from, cycle[cycle.length() - 1].to)
  for position, edge in cycle {
    assert_eq(edge.to, cycle[(position + 1) % cycle.length()].from)
  }
  for edge in cycle {
    assert_false(result.base.sources.at(edge).is_empty())
  }
}

///|
test "effective list graph 19 graph capacity stays separate from six-transaction exact interpretation" {
  let body : Array[Json] = []
  let values : Array[String] = []
  for number in 0..<7 {
    let id = "T" + number.to_string()
    let item = "i" + number.to_string()
    body.push(leg_test_begin(id))
    body.push(leg_test_append(id, item))
    leg_test_commit(body, id)
    values.push(item)
  }
  body.push(leg_test_begin("R"))
  body.push(leg_test_read("R", values))
  leg_test_commit(body, "R")
  let source = classification26_test_list(body).stringify()
  let result = list_graph_effective_v4(list_v3_parse(source))
  assert_true(result.base.complete)
  assert_eq(result.base.transactions.length(), 8)
  assert_eq(
    capture_field(list_v3_analysis(source, "{}"), "status"),
    Json("inconclusive"),
  )
}

///|
test "effective list graph 20 zero-work and zero-budget histories stay distinct" {
  let empty = leg_test_graph([], max_checks=0)
  assert_true(empty.base.complete)
  assert_eq(empty.checks, 0)
  let limited = leg_test_graph(leg_test_external(["a1", "a2"]), max_checks=0)
  assert_false(limited.base.complete)
  assert_false(limited.index.journal_complete)
  assert_true(limited.limited)
  assert_eq(limited.checks, 0)
  assert_true(limited.index.reads.all(read => !read.usable))
}

///|
test "effective list graph 21 nested composite keys never alias delimiter-bearing identities" {
  let body = [
    leg_test_begin("a|b"),
    leg_test_append("a|b", "left|id", key="x"),
    leg_test_begin("a"),
    leg_test_append("a", "right:id", key="b|x"),
  ]
  leg_test_commit(body, "a|b")
  leg_test_commit(body, "a")
  body.push(leg_test_begin("reader|:[]"))
  body.push(leg_test_read("reader|:[]", ["left|id"], key="x"))
  body.push(leg_test_read("reader|:[]", ["right:id"], key="b|x"))
  leg_test_commit(body, "reader|:[]")
  let trace = classification26_test_list(body)
  let events = v3_test_items(trace, "events")
  object_fields_unchecked_v3(events[0])["initial"] = { "x": [], "b|x": [] }
  let result = list_graph_effective_v4(list_v3_parse(trace.stringify()))
  assert_true(result.base.complete)
  assert_true(result.index.groups.at("x").contains("a|b"))
  assert_true(result.index.groups.at("b|x").contains("a"))
  assert_eq(result.base.edges.length(), 2)
  assert_false(result.base.edges.any(edge => edge.kind == WW))
  assert_true(
    result.base.edges.any(edge => edge.key == Some("x") && edge.from == "a|b"),
  )
  assert_true(
    result.base.edges.any(edge => edge.key == Some("b|x") && edge.from == "a"),
  )
}

///|
test "effective list graph 22 key and item delimiter collisions preserve separate sources" {
  let body = [
    leg_test_begin("P"),
    leg_test_append("P", "z", key="x|y"),
    leg_test_begin("Q"),
    leg_test_append("Q", "y|z", key="x"),
  ]
  leg_test_commit(body, "P")
  leg_test_commit(body, "Q")
  body.push(leg_test_begin("R"))
  body.push(leg_test_read("R", ["z"], key="x|y"))
  body.push(leg_test_read("R", ["y|z"], key="x"))
  leg_test_commit(body, "R")
  let trace = classification26_test_list(body)
  object_fields_unchecked_v3(v3_test_items(trace, "events")[0])["initial"] = {
    "x|y": [],
    "x": [],
  }
  let result = list_graph_effective_v4(list_v3_parse(trace.stringify()))
  assert_true(result.base.complete)
  assert_eq(result.index.active.length(), 2)
  assert_eq(result.base.edges.length(), 2)
  assert_true(
    result.base.edges.any(edge => {
      edge.key == Some("x|y") && edge.from_version == Some("z")
    }),
  )
  assert_true(
    result.base.edges.any(edge => {
      edge.key == Some("x") && edge.from_version == Some("y|z")
    }),
  )
}

///|
test "effective list graph 23 cross-key source identity errors are never repaired by the graph" {
  let body = [leg_test_begin("A"), leg_test_append("A", "only-x", key="x")]
  leg_test_commit(body, "A")
  body.push(leg_test_begin("R"))
  body.push(leg_test_read("R", ["only-x"], key="y"))
  leg_test_commit(body, "R")
  let result = leg_test_graph(body)
  assert_false(result.base.complete)
  assert_false(result.index.reads[0].usable)
  assert_true(result.base.edges.is_empty())
  let duplicate = classification26_test_list([
    leg_test_begin("A"),
    leg_test_append("A", "same-id", key="x"),
    leg_test_append("A", "same-id", key="y"),
  ])
  assert_true(parse_history_v4(duplicate.stringify()) is Err(_))
}

///|
fn leg_test_local_snapshot_order(own_before_read : Bool) -> Array[Json] {
  let body = [leg_test_begin("A")]
  if own_before_read {
    body.push(leg_test_append("A", "a1"))
    body.push(leg_test_read("A", ["a1"]))
  } else {
    body.push(leg_test_read("A", []))
  }
  body.push(leg_test_begin("B"))
  body.push(leg_test_append("B", "b"))
  leg_test_commit(body, "B")
  if !own_before_read {
    body.push(leg_test_append("A", "a1"))
  }
  leg_test_commit(body, "A")
  body.push(leg_test_begin("R"))
  body.push(leg_test_read("R", ["b", "a1"]))
  leg_test_commit(body, "R")
  body
}

///|
fn leg_test_no_local_ww_inference(own_before_read : Bool) -> Unit raise {
  let body = leg_test_local_snapshot_order(own_before_read)
  let result = leg_test_graph(body)
  let graph = adjacency(result.base.transactions, result.base.edges)
  let write_cycle = classification_v3_cycle(
    result.base.transactions,
    result.base.edges,
    graph,
    "G0",
    gs_test_budget(),
  )
  assert_true(write_cycle.is_empty())
  assert_false(
    result.base.edges.any(edge => {
      edge.kind == WW && edge.from == "A" && edge.to == "B"
    }),
  )
  assert_true(
    result.base.edges.any(edge => {
      edge.kind == WW && edge.from == "B" && edge.to == "A"
    }),
  )
  assert_true(
    result.base.edges.any(edge => {
      edge.kind == RW && edge.from == "A" && edge.to == "B"
    }),
  )
  assert_true(result.base.complete)
  let cycle = g_single_cycle_v4(
    result.base.transactions.length(),
    result.base.edges,
    graph,
    gs_test_budget(),
  )
  assert_eq(cycle.length(), 2)
  assert_eq(cycle.filter(edge => edge.kind == RW).length(), 1)
  assert_eq(
    capture_field(
      list_v3_analysis(classification26_test_list(body).stringify(), "{}"),
      "status",
    ),
    Json("violation"),
  )
}

///|
test "effective list graph 24 a future own append cannot turn a snapshot dependency into WW" {
  leg_test_no_local_ww_inference(false)
}

///|
test "effective list graph 25 a provisional own item cannot order another transaction's append" {
  leg_test_no_local_ww_inference(true)
}

///|
fn leg_test_incompatible_item_orders() -> Array[Json] {
  let body = [
    leg_test_begin("A"),
    leg_test_append("A", "a"),
    leg_test_begin("B"),
    leg_test_append("B", "b"),
  ]
  leg_test_commit(body, "A")
  leg_test_commit(body, "B")
  body.push(leg_test_begin("R1"))
  body.push(leg_test_read("R1", ["a", "b"]))
  leg_test_commit(body, "R1")
  body.push(leg_test_begin("R2"))
  body.push(leg_test_read("R2", ["b", "a"]))
  leg_test_commit(body, "R2")
  body
}

///|
test "effective list graph 26 incompatible item orders are source gaps rather than G0" {
  let result = leg_test_graph(leg_test_incompatible_item_orders())
  let cycle = classification_v3_cycle(
    result.base.transactions,
    result.base.edges,
    adjacency(result.base.transactions, result.base.edges),
    "G0",
    gs_test_budget(),
  )
  assert_true(cycle.is_empty())
  assert_false(result.base.complete)
  assert_true(leg_test_has_gap(result, "incompatible-effective-item-order"))
  assert_false(
    v3_test_items(
      list_graph_effective_v4_json(result),
      "quarantinedDependencies",
    ).is_empty(),
  )
}

///|
test "effective list graph 27 incompatible key isolation retains a reliable other-key witness" {
  let body = leg_test_incompatible_item_orders()
  body.push(leg_test_begin("T"))
  body.push(leg_test_begin("U"))
  body.push(leg_test_read("U", [], key="y"))
  body.push(leg_test_append("T", "ty", key="y"))
  body.push(leg_test_append("T", "tz", key="z"))
  body.push(leg_test_read("U", ["tz"], key="z"))
  leg_test_commit(body, "T")
  leg_test_commit(body, "U")
  let trace = classification26_test_list(body)
  object_fields_unchecked_v3(v3_test_items(trace, "events")[0])["initial"] = {
    "x": [],
    "y": [],
    "z": [],
  }
  let result = list_graph_effective_v4(list_v3_parse(trace.stringify()))
  assert_false(result.base.complete)
  assert_true(result.item_order_validated)
  assert_true(leg_test_has_gap(result, "incompatible-effective-item-order"))
  assert_false(result.base.edges.any(edge => edge.key == Some("x")))
  assert_false(result.quarantined.is_empty())
  for constraint in result.quarantined {
    assert_eq(v4_test_at(constraint, ["edge", "key"]), Json("x"))
    assert_false(v3_test_items(constraint, "sources").is_empty())
  }
  let cycle = g_single_cycle_v4(
    result.base.transactions.length(),
    result.base.edges,
    adjacency(result.base.transactions, result.base.edges),
    gs_test_budget(),
  )
  assert_eq(cycle.length(), 2)
  assert_eq(cycle.filter(edge => edge.kind == RW).length(), 1)
  assert_true(cycle.all(edge => edge.from == "T" || edge.from == "U"))
  assert_eq(
    capture_field(result.base.normalized, "observations"),
    capture_field(trace, "events"),
  )
}

///|
test "effective list graph 28 unfinished item validation exposes no unverified category edges" {
  let body = leg_test_external(["a1", "a2"])
  let full = leg_test_graph(body)
  let mut observed_quarantine = false
  for max_checks in 0..<full.checks {
    let result = leg_test_graph(body, max_checks~)
    assert_true(result.checks <= max_checks)
    if !result.item_order_validated && !result.quarantined.is_empty() {
      observed_quarantine = true
      assert_true(result.limited)
      assert_true(result.base.edges.is_empty())
      assert_false(result.base.complete)
    }
  }
  assert_true(observed_quarantine)
}
