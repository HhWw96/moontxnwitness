///|
fn rpg_row(key : String, version : String, value~ : String = "same") -> Json {
  {
    "key": Json(key),
    "version": Json(version),
    "values": { "value": Json(value) },
  }
}

///|
fn rpg_trace(body : Array[Json], empty~ : Bool = false) -> Json {
  let events : Array[Json] = [
    {
      "kind": "snapshot",
      "consistent": true,
      "initial": {
        "items": if empty {
          Json(([] : Array[Json]))
        } else {
          Json([rpg_row("1", "v0"), rpg_row("2", "u0"), rpg_row("3", "z0")])
        },
      },
    },
  ]
  for raw in body {
    events.push(raw)
  }
  for position, raw in events {
    let fields = object_fields_unchecked_v3(raw)
    fields["seq"] = Json(position + 1)
    fields["time"] = Json(position)
  }
  {
    "traceSchema": 3,
    "dataModel": "relation-set-v1",
    "relationSchema": {
      "items": {
        "primaryKey": "id",
        "columns": { "id": "int64", "value": "text" },
      },
    },
    "clockDomain": "relation-point-test",
    "scope": { "exclusiveWriters": true, "completeSnapshotTables": ["items"] },
    "events": Json(events),
    "gaps": [],
  }
}

///|
fn rpg_begin(tx : String) -> Json {
  { "kind": "begin", "tx": Json(tx), "connection": Json(tx) }
}

///|
fn rpg_write(
  tx : String,
  key : String,
  version : String,
  predecessor : String?,
  action~ : String = "update",
  value~ : String = "same",
) -> Json {
  {
    "kind": "row_write",
    "tx": Json(tx),
    "relation": "items",
    "key": Json(key),
    "action": Json(action),
    "version": Json(version),
    "predecessor": relation_v3_optional_text(predecessor),
    "values": if action == "delete" {
      Json::null()
    } else {
      ({ "value": Json(value) } : Json)
    },
  }
}

///|
fn rpg_read(
  tx : String,
  key : String,
  version : String?,
  value~ : String = "same",
) -> Json {
  {
    "kind": "row_read",
    "tx": Json(tx),
    "relation": "items",
    "predicate": [{ "column": "id", "op": "eq", "value": Json(key) }],
    "rows": Json(
      match version {
        Some(v) => [rpg_row(key, v, value~)]
        None => []
      },
    ),
    "complete": true,
  }
}

///|
fn rpg_commit(body : Array[Json], tx : String) -> Unit {
  body.push({ "kind": "commit_request", "tx": Json(tx) })
  body.push({ "kind": "commit_ok", "tx": Json(tx) })
}

///|
fn rpg_graph(
  body : Array[Json],
  empty~ : Bool = false,
  max_checks~ : Int32 = 1000000,
) -> RelationPointGraphV4 raise {
  relation_graph_point_v4(
    relation_v3_parse(rpg_trace(body, empty~).stringify()),
    max_checks~,
  )
}

///|
fn rpg_gap(result : RelationPointGraphV4, code : String) -> Bool {
  result.index.gaps.any(gap => {
    object_fields_unchecked_v3(gap).get("code") == Some(Json(code))
  })
}

///|
fn rpg_direct(result : RelationPointGraphV4, category : String) -> Array[Json] {
  result.index.direct.get_or_default(category, [])
}

///|
fn rpg_cycle(result : RelationPointGraphV4, category : String) -> Array[Edge] {
  let budget : ClassificationV3Budget = {
    max_states: 100000,
    max_edge_checks: 1000000,
    states: 0,
    edge_checks: 0,
    limited: false,
    reason: "complete",
  }
  classification_v3_cycle(
    result.base.transactions,
    result.base.edges,
    adjacency(result.base.transactions, result.base.edges),
    category,
    budget,
  )
}

///|
test "relation point graph 01 empty snapshots have no invented register operations" {
  let result = rpg_graph([])
  assert_true(result.base.complete)
  assert_true(result.base.history is None)
  assert_true(result.base.list_parsed is None)
  assert_true(result.base.edges.is_empty())
  assert_true(result.base.transactions.is_empty())
}

///|
test "relation point graph 02 primary key read of initial row is complete without writer node" {
  let body = [rpg_begin("R"), rpg_read("R", "1", Some("v0"))]
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(result.base.complete)
  assert_true(result.base.edges.is_empty())
  assert_true(result.base.transactions.all(tx => tx.ops.is_empty()))
  assert_true(result.index.reads[0].usable)
}

///|
test "relation point graph 03 WR keeps original row and delivered query identities" {
  let body = [rpg_begin("A"), rpg_write("A", "1", "v1", Some("v0"))]
  rpg_commit(body, "A")
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "1", Some("v1")))
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(result.base.complete)
  let edges = result.base.edges.filter(edge => edge.kind == WR)
  assert_eq(edges.length(), 1)
  assert_eq(edges[0].from, "A")
  assert_eq(edges[0].to, "R")
  let proof = result.base.sources.at(edges[0])[0]
  assert_eq(v4_test_at(proof, ["identity", "relation"]), Json("items"))
  assert_eq(v4_test_at(proof, ["identity", "primaryKey"]), Json("1"))
  assert_eq(v4_test_at(proof, ["queryObservation", "kind"]), Json("row_read"))
  assert_eq(
    v4_test_at(proof, ["readSource", "source", "original", "kind"]),
    Json("row_write"),
  )
}

///|
test "relation point graph 04 old row read creates item RW to later committed effect" {
  let body = [
    rpg_begin("R"),
    rpg_read("R", "1", Some("v0")),
    rpg_begin("A"),
    rpg_write("A", "1", "v1", Some("v0")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(result.base.complete)
  let edges = result.base.edges.filter(edge => edge.kind == RW)
  assert_eq(edges.length(), 1)
  assert_eq(edges[0].from, "R")
  assert_eq(edges[0].to, "A")
  assert_eq(edges[0].from_version, Some("v0"))
  assert_eq(edges[0].to_version, Some("v1"))
  assert_false(result.base.edges.any(edge => edge.kind == RT))
}

///|
test "relation point graph 05 final committed predecessor chain creates WW with source path" {
  let body = [rpg_begin("A"), rpg_write("A", "1", "v1", Some("v0"))]
  rpg_commit(body, "A")
  body.push(rpg_begin("B"))
  body.push(rpg_write("B", "1", "v2", Some("v1")))
  rpg_commit(body, "B")
  let result = rpg_graph(body)
  assert_true(result.base.complete)
  let edge = result.base.edges[0]
  assert_true(edge.kind == WW)
  assert_eq(edge.from, "A")
  assert_eq(edge.to, "B")
  assert_eq(
    v3_test_items(result.base.sources.at(edge)[0], "predecessorPath").length(),
    2,
  )
  assert_eq(
    result.index.chains[0].map(source => {
      result.index.parsed.sources[source].row.version
    }),
    ["v1", "v2"],
  )
}

///|
fn rpg_skew_body() -> Array[Json] {
  let body = [
    rpg_begin("A"),
    rpg_begin("B"),
    rpg_read("A", "2", Some("u0")),
    rpg_read("B", "1", Some("v0")),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_write("B", "2", "u1", Some("u0")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  body
}

///|
test "relation point graph 06 two key write skew has a closed item anti dependency witness" {
  let result = rpg_graph(rpg_skew_body())
  assert_true(result.base.complete)
  let cycle = rpg_cycle(result, "G2-item")
  assert_eq(cycle.length(), 2)
  assert_true(cycle.all(edge => edge.kind == RW))
  for position, edge in cycle {
    assert_eq(edge.to, cycle[(position + 1) % cycle.length()].from)
    assert_false(result.base.sources.at(edge).is_empty())
  }
}

///|
test "relation point graph 07 opposite row version orders retain a genuine G0 cycle" {
  let body = [
    rpg_begin("A"),
    rpg_begin("B"),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_write("B", "1", "v2", Some("v1")),
    rpg_write("B", "2", "u1", Some("u0")),
    rpg_write("A", "2", "u2", Some("u1")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  let result = rpg_graph(body)
  assert_true(result.base.complete)
  let cycle = rpg_cycle(result, "G0")
  assert_eq(cycle.length(), 2)
  assert_true(cycle.all(edge => edge.kind == WW))
}

///|
test "relation point graph 08 reciprocal final row reads retain G1c independently from G0" {
  let body = [
    rpg_begin("A"),
    rpg_begin("B"),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_write("B", "2", "u1", Some("u0")),
    rpg_read("A", "2", Some("u1")),
    rpg_read("B", "1", Some("v1")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  let result = rpg_graph(body)
  assert_true(result.base.complete)
  assert_true(rpg_cycle(result, "G0").is_empty())
  let cycle = rpg_cycle(result, "G1c")
  assert_eq(cycle.length(), 2)
  assert_true(cycle.all(edge => edge.kind == WR))
}

///|
test "relation point graph 09 committed read from aborted row is direct G1a" {
  let body = [
    rpg_begin("P"),
    rpg_write("P", "1", "v1", Some("v0")),
    ({ "kind": "rollback_ok", "tx": "P" } : Json),
    rpg_begin("R"),
    rpg_read("R", "1", Some("v1")),
  ]
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_eq(rpg_direct(result, "G1a").length(), 1)
  assert_true(rpg_direct(result, "G1b").is_empty())
  assert_false(result.base.complete)
  assert_true(result.base.edges.is_empty())
}

///|
test "relation point graph 10 external intermediate row effect is direct G1b" {
  let body = [
    rpg_begin("P"),
    rpg_write("P", "1", "v1", Some("v0")),
    rpg_begin("R"),
    rpg_read("R", "1", Some("v1")),
    rpg_write("P", "1", "v2", Some("v1")),
  ]
  rpg_commit(body, "P")
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_eq(rpg_direct(result, "G1b").length(), 1)
  assert_true(rpg_direct(result, "G1a").is_empty())
  assert_false(result.index.reads[0].usable)
}

///|
test "relation point graph 11 own intermediate reads are legal before later overwrite" {
  let body = [
    rpg_begin("P"),
    rpg_write("P", "1", "v1", Some("v0")),
    rpg_read("P", "1", Some("v1")),
    rpg_write("P", "1", "v2", Some("v1")),
    rpg_read("P", "1", Some("v2")),
  ]
  rpg_commit(body, "P")
  let result = rpg_graph(body)
  assert_true(result.base.complete)
  assert_true(rpg_direct(result, "G1b").is_empty())
  assert_true(rpg_direct(result, "INT").is_empty())
  assert_true(result.index.reads.all(read => read.usable))
}

///|
test "relation point graph 12 stale own row read is direct INT" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_read("A", "1", Some("v0")),
  ]
  rpg_commit(body, "A")
  let result = rpg_graph(body)
  assert_eq(rpg_direct(result, "INT").length(), 1)
  assert_true(rpg_direct(result, "G1a").is_empty())
}

///|
test "relation point graph 13 empty own read after insert is direct INT" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "4", "a", None, action="insert"),
    rpg_read("A", "4", None),
  ]
  rpg_commit(body, "A")
  assert_eq(rpg_direct(rpg_graph(body), "INT").length(), 1)
}

///|
test "relation point graph 14 own tombstone yields legal empty point read" {
  let body = [
    rpg_begin("D"),
    rpg_write("D", "1", "d1", Some("v0"), action="delete"),
    rpg_read("D", "1", None),
  ]
  rpg_commit(body, "D")
  let result = rpg_graph(body)
  assert_true(result.base.complete)
  assert_true(result.index.reads[0].usable)
  assert_true(rpg_direct(result, "INT").is_empty())
  assert_true(result.base.edges.is_empty())
}

///|
test "relation point graph 15 delete then reinsert retains tombstone in original path and audit" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "d1", Some("v0"), action="delete"),
    rpg_write("A", "1", "v2", Some("d1"), action="insert"),
    rpg_read("A", "1", Some("v2")),
  ]
  rpg_commit(body, "A")
  let result = rpg_graph(body)
  assert_true(result.base.complete)
  let tombstone = result.index.versions.at("d1")
  assert_true(result.index.surviving[tombstone])
  assert_false(result.index.final_set[tombstone])
  assert_eq(
    result.index.parsed.sources[result.index.chains[0][0]].row.version,
    "v2",
  )
  assert_eq(
    v4_test_at(relation_point_source_json_v4(result.index, tombstone), [
      "original", "action",
    ]),
    Json("delete"),
  )
}

///|
test "relation point graph 16 null reinsert cannot erase an earlier own tombstone" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "d1", Some("v0"), action="delete"),
    rpg_write("A", "1", "v2", None, action="insert"),
  ]
  rpg_commit(body, "A")
  let result = rpg_graph(body)
  assert_false(result.base.complete)
  // A write predecessor is not a SELECT observation and cannot prove INT.
  assert_true(rpg_direct(result, "INT").is_empty())
  assert_true(rpg_gap(result, "invalid-local-row-write"))
  assert_true(result.index.diagnostics.any(diagnostic => {
    capture_field(diagnostic, "code") == Json("unproven-local-row-write-source")
  }))
  assert_true(result.index.blocked.contains(0))
}

///|
test "relation point graph 17 uniquely resolved final deletion gives empty point read WR" {
  let body = [
    rpg_begin("D"),
    rpg_write("D", "1", "d1", Some("v0"), action="delete"),
  ]
  rpg_commit(body, "D")
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "1", None))
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(result.base.complete)
  let edge = result.base.edges.filter(edge => edge.kind == WR)[0]
  assert_eq(edge.from, "D")
  assert_eq(edge.to, "R")
  assert_eq(edge.from_version, Some("d1"))
  assert_true(edge.to_version is None)
  assert_eq(
    v4_test_at(result.base.sources.at(edge)[0], ["readSource", "kind"]),
    Json("uniquely-resolved-tombstone-absence"),
  )
}

///|
test "relation point graph 18 initial absence uses no invented writer or version" {
  let body = [
    rpg_begin("R"),
    rpg_read("R", "4", None),
    rpg_begin("I"),
    rpg_write("I", "4", "i1", None, action="insert"),
  ]
  rpg_commit(body, "I")
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(result.base.complete)
  let edge = result.base.edges.filter(edge => edge.kind == RW)[0]
  assert_eq(edge.from, "R")
  assert_eq(edge.to, "I")
  assert_true(edge.from_version is None)
  assert_eq(
    v4_test_at(result.base.sources.at(edge)[0], ["readSource", "kind"]),
    Json("initial-absence"),
  )
  assert_eq(result.base.transactions.length(), 2)
}

///|
test "relation point graph 19 repeated absence states are not disambiguated using event time" {
  let body = [rpg_begin("I"), rpg_write("I", "4", "i1", None, action="insert")]
  rpg_commit(body, "I")
  body.push(rpg_begin("D"))
  body.push(rpg_write("D", "4", "d1", Some("i1"), action="delete"))
  rpg_commit(body, "D")
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "4", None))
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_false(result.base.complete)
  assert_true(rpg_gap(result, "ambiguous-point-absence"))
  assert_false(
    result.base.edges.any(edge => edge.to == "R" || edge.from == "R"),
  )
}

///|
test "relation point graph 20 two distinct tombstones keep external absence unknown" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "d1", Some("v0"), action="delete"),
  ]
  rpg_commit(body, "A")
  body.push(rpg_begin("B"))
  body.push(rpg_write("B", "1", "v2", Some("d1"), action="insert"))
  rpg_commit(body, "B")
  body.push(rpg_begin("C"))
  body.push(rpg_write("C", "1", "d3", Some("v2"), action="delete"))
  rpg_commit(body, "C")
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "1", None))
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(rpg_gap(result, "ambiguous-point-absence"))
  assert_eq(result.base.edges.filter(edge => edge.kind == WW).length(), 2)
}

///|
test "relation point graph 21 explicit row source after reinsert bypasses absence ambiguity" {
  let body = [rpg_begin("A"), rpg_write("A", "4", "i1", None, action="insert")]
  rpg_commit(body, "A")
  body.push(rpg_begin("B"))
  body.push(rpg_write("B", "4", "d2", Some("i1"), action="delete"))
  rpg_commit(body, "B")
  body.push(rpg_begin("C"))
  body.push(rpg_write("C", "4", "i3", Some("d2"), action="insert"))
  rpg_commit(body, "C")
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "4", Some("i3")))
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(result.base.complete)
  assert_true(
    result.base.edges.any(edge => {
      edge.kind == WR && edge.from == "C" && edge.to == "R"
    }),
  )
}

///|
fn rpg_rollback_body() -> Array[Json] {
  let body = [
    rpg_begin("A"),
    ({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "s1" } : Json),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_read("A", "1", Some("v1")),
    ({ "kind": "rollback_to", "tx": "A", "instance": "s1" } : Json),
    rpg_read("A", "1", Some("v0")),
    rpg_write("A", "1", "v2", Some("v0")),
  ]
  rpg_commit(body, "A")
  body
}

///|
test "relation point graph 22 savepoint rollback preserves prior delivered own row read" {
  let result = rpg_graph(rpg_rollback_body())
  assert_true(result.base.complete)
  assert_true(result.index.reads.all(read => read.usable))
  assert_true(rpg_direct(result, "G1a").is_empty())
  assert_true(rpg_direct(result, "G1b").is_empty())
  assert_true(rpg_direct(result, "INT").is_empty())
  assert_eq(
    result.index.parsed.sources[result.index.reads[0].own].row.version,
    "v1",
  )
  assert_false(result.index.surviving[result.index.versions.at("v1")])
}

///|
test "relation point graph 23 foreign rolled back row read is G1a without erasing own past read" {
  let body = rpg_rollback_body()
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "1", Some("v1")))
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(result.index.reads[0].usable)
  assert_eq(rpg_direct(result, "G1a").length(), 1)
}

///|
test "relation point graph 24 own read after rollback cannot retain a revoked effect" {
  let body = [
    rpg_begin("A"),
    ({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "s1" } : Json),
    rpg_write("A", "1", "v1", Some("v0")),
    ({ "kind": "rollback_to", "tx": "A", "instance": "s1" } : Json),
    rpg_read("A", "1", Some("v1")),
  ]
  rpg_commit(body, "A")
  let result = rpg_graph(body)
  assert_eq(rpg_direct(result, "INT").length(), 1)
  assert_true(rpg_direct(result, "G1a").is_empty())
}

///|
test "relation point graph 25 repeated savepoint names use distinct validated instances" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "v1", Some("v0")),
    (
      { "kind": "savepoint", "tx": "A", "name": "same", "instance": "outer" } :
      Json),
    rpg_write("A", "1", "v2", Some("v1")),
    (
      { "kind": "savepoint", "tx": "A", "name": "same", "instance": "inner" } :
      Json),
    rpg_write("A", "1", "v3", Some("v2")),
    ({ "kind": "rollback_to", "tx": "A", "instance": "inner" } : Json),
    rpg_read("A", "1", Some("v2")),
    ({ "kind": "release", "tx": "A", "instance": "inner" } : Json),
    ({ "kind": "rollback_to", "tx": "A", "instance": "outer" } : Json),
    rpg_read("A", "1", Some("v1")),
  ]
  rpg_commit(body, "A")
  let result = rpg_graph(body)
  assert_true(result.base.complete)
  assert_true(result.index.reads.all(read => read.usable))
  assert_false(result.index.surviving[result.index.versions.at("v2")])
  assert_false(result.index.surviving[result.index.versions.at("v3")])
  assert_true(result.index.final_set[result.index.versions.at("v1")])
}

///|
test "relation point graph 26 commit request and release do not confirm unknown transaction" {
  let body = [
    rpg_begin("A"),
    ({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "s1" } : Json),
    rpg_write("A", "1", "v1", Some("v0")),
    ({ "kind": "release", "tx": "A", "instance": "s1" } : Json),
    ({ "kind": "commit_request", "tx": "A" } : Json),
  ]
  let result = rpg_graph(body)
  assert_false(result.base.complete)
  assert_false(result.index.final_set[result.index.versions.at("v1")])
  assert_true(result.base.edges.is_empty())
}

///|
test "relation point graph 27 branched predecessors stay unknown without inferred version order" {
  let body = [
    rpg_begin("A"),
    rpg_begin("B"),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_write("B", "1", "v2", Some("v0")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  let result = rpg_graph(body)
  assert_false(result.base.complete)
  assert_true(rpg_gap(result, "branched-row-predecessor"))
  assert_true(result.base.edges.is_empty())
}

///|
test "relation point graph 28 missing predecessor source cannot be fabricated" {
  let body = [rpg_begin("A"), rpg_write("A", "1", "v1", Some("missing"))]
  rpg_commit(body, "A")
  let result = rpg_graph(body)
  assert_true(rpg_gap(result, "missing-row-predecessor-source"))
  assert_false(result.base.complete)
  assert_true(result.base.edges.is_empty())
}

///|
test "relation point graph 29 future predecessor does not order committed writes" {
  let body = [
    rpg_begin("A"),
    rpg_begin("B"),
    rpg_write("A", "1", "v1", Some("v2")),
    rpg_write("B", "1", "v2", Some("v0")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  let result = rpg_graph(body)
  assert_true(rpg_gap(result, "invalid-row-predecessor-chain"))
  assert_true(result.base.edges.is_empty())
}

///|
test "relation point graph 30 missing returned row source stays unknown" {
  let body = [rpg_begin("R"), rpg_read("R", "1", Some("missing"))]
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(rpg_gap(result, "missing-relation-point-row-source"))
  assert_false(result.base.complete)
}

///|
test "relation point graph 31 value mismatch cannot establish a reads from edge" {
  let body = [rpg_begin("R"), rpg_read("R", "1", Some("v0"), value="different")]
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(rpg_gap(result, "invalid-relation-point-row-source"))
  assert_true(result.base.edges.is_empty())
  assert_true(rpg_direct(result, "G1a").is_empty())
}

///|
test "relation point graph 32 range and extra predicates remain explicit unsupported scope" {
  for
    predicate in [
      ([{ "column": "id", "op": "ge", "value": "1" }] : Array[Json]),
      [
        { "column": "id", "op": "eq", "value": "1" },
        { "column": "value", "op": "eq", "value": "same" },
      ],
    ] {
    let read = rpg_read("R", "1", Some("v0"))
    object_fields_unchecked_v3(read)["predicate"] = Json(predicate)
    let body = [rpg_begin("R"), read]
    rpg_commit(body, "R")
    let result = rpg_graph(body)
    assert_true(rpg_gap(result, "relation-predicate-outside-single-primary-eq"))
    assert_true(result.base.edges.is_empty())
  }
}

///|
test "relation point graph 33 partial fetch does not prove a complete point observation" {
  let read = rpg_read("R", "1", Some("v0"))
  object_fields_unchecked_v3(read)["complete"] = Json(false)
  let body = [rpg_begin("R"), read]
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(rpg_gap(result, "relation-point-result-not-completely-delivered"))
  assert_false(result.base.complete)
}

///|
test "relation point graph 34 bad key order does not mask reliable other key cycle" {
  let body = [
    rpg_begin("P"),
    rpg_begin("Q"),
    rpg_write("P", "1", "v1", Some("v0")),
    rpg_write("Q", "1", "v2", Some("v0")),
  ]
  rpg_commit(body, "P")
  rpg_commit(body, "Q")
  body.push(rpg_begin("A"))
  body.push(rpg_begin("B"))
  body.push(rpg_read("A", "3", Some("z0")))
  body.push(rpg_read("B", "2", Some("u0")))
  body.push(rpg_write("A", "2", "u1", Some("u0")))
  body.push(rpg_write("B", "3", "z1", Some("z0")))
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  let result = rpg_graph(body)
  assert_false(result.base.complete)
  assert_true(rpg_gap(result, "branched-row-predecessor"))
  let cycle = rpg_cycle(result, "G2-item")
  assert_eq(cycle.length(), 2)
  assert_true(cycle.all(edge => edge.from == "A" || edge.from == "B"))
}

///|
test "relation point graph 35 identical business values do not alias unique row versions" {
  let body = [rpg_begin("A"), rpg_write("A", "1", "same|id", Some("v0"))]
  rpg_commit(body, "A")
  body.push(rpg_begin("B"))
  body.push(rpg_write("B", "1", "same:id", Some("same|id")))
  rpg_commit(body, "B")
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "1", Some("same|id")))
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(result.base.complete)
  assert_true(
    result.base.edges.any(edge => {
      edge.kind == WR && edge.from == "A" && edge.to == "R"
    }),
  )
  assert_true(
    result.base.edges.any(edge => {
      edge.kind == RW && edge.from == "R" && edge.to == "B"
    }),
  )
  assert_true(
    result.index.versions.at("same|id") != result.index.versions.at("same:id"),
  )
}

///|
test "relation point graph 36 exact construction budget succeeds and exhaustion stays visible" {
  let body = rpg_skew_body()
  let full = rpg_graph(body)
  assert_true(full.checks > 0)
  let exact = rpg_graph(body, max_checks=full.checks)
  assert_true(exact.base.complete)
  assert_false(exact.limited)
  for maximum in [0, 1, full.checks - 1] {
    let limited = rpg_graph(body, max_checks=maximum)
    assert_false(limited.base.complete)
    assert_true(limited.limited)
    assert_true(limited.checks <= maximum)
  }
}

///|
test "relation point graph 37 graph transaction capacity is separate from exact interpreter" {
  let body : Array[Json] = []
  for position in 0..<129 {
    let tx = "T" + position.to_string()
    body.push(rpg_begin(tx))
    rpg_commit(body, tx)
  }
  let result = rpg_graph(body)
  assert_false(result.base.complete)
  assert_eq(result.base.reason, "relation-point-capacity-128-4096")
  assert_true(result.base.edges.is_empty())
  assert_eq(result.checks, 0)
}

///|
test "relation point graph 38 public builder validates model budget and protects aliases" {
  let history = parse_history_v4(rpg_trace(rpg_skew_body()).stringify()).unwrap()
  let result = build_relation_point_graph_v4(history).unwrap()
  let original = relation_point_graph_v4_json(result)
  let changed = relation_point_graph_v4_json(result)
  object_fields_unchecked_v3(changed)["edges"] = Json(["fake"])
  object_fields_unchecked_v3(v3_test_items(changed, "sourceAudit")[0])["original"] = Json(
    "changed",
  )
  assert_eq(relation_point_graph_v4_json(result), original)
  assert_true(build_relation_point_graph_v4(history, max_checks=-1) is Err(_))
  assert_true(
    build_relation_point_graph_v4(history, max_checks=1000001) is Err(_),
  )
  assert_true(
    build_relation_point_graph_v4(register_history_v4(skew()).unwrap())
    is Err(_),
  )
}

///|
test "relation point graph 39 original observations effects and sources remain unchanged" {
  let trace = rpg_trace(rpg_rollback_body())
  let parsed = relation_v3_parse(trace.stringify())
  let before = parsed.normalized.stringify()
  let result = relation_graph_point_v4(parsed)
  assert_eq(parsed.normalized.stringify(), before)
  let record = relation_point_graph_v4_json(result)
  assert_eq(
    capture_field(record, "observations"),
    capture_field(trace, "events"),
  )
  assert_eq(
    capture_field(record, "writeEffects"),
    capture_field(parsed.normalized, "effects"),
  )
  for fact in v3_test_items(record, "sourceAudit") {
    assert_eq(
      capture_field(capture_field(fact, "original"), "seq"),
      capture_field(capture_field(fact, "fact"), "sourceSeq"),
    )
  }
}

///|
test "relation point graph 40 incomplete snapshot does not prove initial absence" {
  let body = [rpg_begin("R"), rpg_read("R", "4", None)]
  rpg_commit(body, "R")
  let trace = rpg_trace(body)
  object_fields_unchecked_v3(capture_field(trace, "scope"))["completeSnapshotTables"] = Json(
    ([] : Array[Json]),
  )
  let result = relation_graph_point_v4(relation_v3_parse(trace.stringify()))
  assert_false(result.base.complete)
  assert_true(rpg_gap(result, "absence-requires-complete-source-window"))
  assert_false(result.index.reads[0].usable)
}

///|
test "relation point graph 41 stale own predecessor is a source gap and cannot create WW" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_write("A", "1", "v2", Some("v0")),
  ]
  rpg_commit(body, "A")
  let result = rpg_graph(body)
  assert_true(rpg_direct(result, "INT").is_empty())
  assert_true(rpg_gap(result, "invalid-local-row-write"))
  assert_true(result.index.diagnostics.any(diagnostic => {
    capture_field(diagnostic, "code") == Json("unproven-local-row-write-source")
  }))
  assert_false(result.base.complete)
  assert_true(result.base.edges.is_empty())
}

///|
test "relation point graph 42 unknown writer outcome cannot become G1a or confirmed source" {
  let body = [
    rpg_begin("P"),
    rpg_write("P", "1", "v1", Some("v0")),
    ({ "kind": "commit_request", "tx": "P" } : Json),
    rpg_begin("R"),
    rpg_read("R", "1", Some("v1")),
  ]
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(rpg_gap(result, "unconfirmed-row-writer-outcome"))
  assert_true(rpg_direct(result, "G1a").is_empty())
  assert_true(result.base.edges.is_empty())
}

///|
test "relation point graph 43 dirty update source is diagnostic not a fabricated read" {
  let body = [
    rpg_begin("P"),
    rpg_write("P", "1", "v1", Some("v0")),
    ({ "kind": "rollback_ok", "tx": "P" } : Json),
    rpg_begin("A"),
    rpg_write("A", "1", "v2", Some("v1")),
  ]
  rpg_commit(body, "A")
  let result = rpg_graph(body)
  assert_false(result.base.complete)
  assert_false(result.index.diagnostics.is_empty())
  assert_true(result.index.reads.is_empty())
  assert_true(rpg_direct(result, "G1a").is_empty())
  assert_true(result.base.edges.is_empty())
}

///|
test "relation point graph 44 absence cannot read from a future deletion" {
  let body = [
    rpg_begin("R"),
    rpg_read("R", "1", None),
    rpg_begin("D"),
    rpg_write("D", "1", "d1", Some("v0"), action="delete"),
  ]
  rpg_commit(body, "D")
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(rpg_gap(result, "absence-source-was-not-observed-before-query"))
  assert_true(result.base.edges.is_empty())
}

///|
test "relation point graph 45 structured identities isolate delimiter bearing text keys across relations" {
  let trace = rpg_trace([])
  object_fields_unchecked_v3(trace)["relationSchema"] = {
    "items": {
      "primaryKey": "id",
      "columns": { "id": "text", "value": "text" },
    },
    "other": {
      "primaryKey": "id",
      "columns": { "id": "text", "value": "text" },
    },
  }
  object_fields_unchecked_v3(capture_field(trace, "scope"))["completeSnapshotTables"] = Json([
      "items", "other",
    ],
  )
  let snapshot = v3_test_items(trace, "events")[0]
  object_fields_unchecked_v3(snapshot)["initial"] = {
    "items": [
      { "key": "a|b:c", "version": "left:0", "values": { "value": "same" } },
    ],
    "other": [
      { "key": "a|b:c", "version": "right|0", "values": { "value": "same" } },
    ],
  }
  let body = [rpg_begin("tx|a:b"), rpg_read("tx|a:b", "a|b:c", Some("left:0"))]
  let second = rpg_read("tx|a:b", "a|b:c", Some("right|0"))
  object_fields_unchecked_v3(second)["relation"] = Json("other")
  body.push(second)
  rpg_commit(body, "tx|a:b")
  let events = v3_test_items(trace, "events")
  for raw in body {
    let fields = object_fields_unchecked_v3(raw)
    fields["seq"] = Json(events.length() + 1)
    fields["time"] = Json(events.length())
    events.push(raw)
  }
  let result = relation_graph_point_v4(relation_v3_parse(trace.stringify()))
  assert_true(result.base.complete)
  assert_eq(result.index.keys.length(), 2)
  assert_true(result.index.reads[0].key != result.index.reads[1].key)
  assert_eq(
    result.index.parsed.sources[result.index.reads[0].observed].row.version,
    "left:0",
  )
  assert_eq(
    result.index.parsed.sources[result.index.reads[1].observed].row.version,
    "right|0",
  )
}

///|
test "relation point graph 46 query only negative keys do not mutate captured source identity set" {
  let body = [
    rpg_begin("R"),
    rpg_read("R", "4", None),
    rpg_read("R", "5", None),
  ]
  rpg_commit(body, "R")
  let parsed = relation_v3_parse(rpg_trace(body).stringify())
  let before = parsed.keys.length()
  let result = relation_graph_point_v4(parsed)
  assert_true(result.base.complete)
  assert_eq(parsed.keys.length(), before)
  assert_eq(result.index.keys.length(), before + 2)
  assert_eq(result.index.reads[0].observed, -1)
  assert_eq(result.index.reads[1].observed, -1)
  assert_true(result.base.edges.is_empty())
}

///|
test "relation point graph 47 missing row source on one key preserves another source bound G2" {
  let body = rpg_skew_body()
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "3", Some("unknown")))
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_false(result.base.complete)
  assert_true(rpg_gap(result, "missing-relation-point-row-source"))
  let cycle = rpg_cycle(result, "G2-item")
  assert_eq(cycle.length(), 2)
  assert_true(cycle.all(edge => edge.from == "A" || edge.from == "B"))
}

///|
test "relation point graph 48 repeated delivered reads preserve all original query identities on one edge" {
  let body = [rpg_begin("A"), rpg_write("A", "1", "v1", Some("v0"))]
  rpg_commit(body, "A")
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "1", Some("v1")))
  body.push(rpg_read("R", "1", Some("v1")))
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(result.base.complete)
  let edges = result.base.edges.filter(edge => edge.kind == WR)
  assert_eq(edges.length(), 1)
  let sources = result.base.sources.at(edges[0])
  assert_eq(sources.length(), 2)
  assert_true(
    capture_field(sources[0], "readSeq") != capture_field(sources[1], "readSeq"),
  )
  assert_eq(capture_field(sources[0], "queryIndex"), Json(0))
  assert_eq(capture_field(sources[1], "queryIndex"), Json(1))
}

///|
test "relation point graph 49 cross key returned producer cannot establish a WR" {
  let body = [rpg_begin("R"), rpg_read("R", "2", Some("v0"))]
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_false(result.base.complete)
  assert_true(rpg_gap(result, "invalid-relation-point-row-source"))
  assert_true(result.base.edges.is_empty())
}

///|
test "relation point graph 50 effect revocation and final write ledgers are independently checked" {
  let trace = rpg_trace(rpg_rollback_body())
  let parsed = relation_v3_parse(trace.stringify())
  let version = parsed.sources.filter(source => source.row.version == "v1")[0]
  let source_index = parsed.sources
    .mapi((position, source) => (position, source))
    .filter(pair => pair.1.row.version == version.row.version)[0].0
  object_fields_unchecked_v3(parsed.source_evidence[source_index])["revertedBy"] = Json::null()
  let result = relation_graph_point_v4(parsed)
  assert_false(result.base.complete)
  assert_true(rpg_gap(result, "relation-effect-ledger-mismatch"))
  let second = relation_v3_parse(trace.stringify())
  let transactions = v3_test_items(second.normalized, "transactions")
  object_fields_unchecked_v3(transactions[0])["finalWrites"] = Json(
    ([] : Array[Json]),
  )
  let mismatch = relation_graph_point_v4(second)
  assert_false(mismatch.base.complete)
  assert_true(rpg_gap(mismatch, "relation-final-effect-ledger-mismatch"))
}

///|
test "relation point graph 51 eight final writers are graph supported without lifting exact limits" {
  let body : Array[Json] = []
  let mut previous = "v0"
  for position in 0..<8 {
    let tx = "T" + position.to_string()
    let version = "v" + (position + 1).to_string()
    body.push(rpg_begin(tx))
    body.push(rpg_write(tx, "1", version, Some(previous)))
    rpg_commit(body, tx)
    previous = version
  }
  let trace = rpg_trace(body)
  let parsed = relation_v3_parse(trace.stringify())
  let result = relation_graph_point_v4(parsed)
  assert_true(result.base.complete)
  assert_eq(result.base.transactions.length(), 8)
  assert_eq(result.base.edges.filter(edge => edge.kind == WW).length(), 7)
  assert_eq(
    capture_field(
      relation_v3_analyze_parsed(parsed, {
        max_states: 100000,
        max_operations: 1000000,
      }),
      "status",
    ),
    Json("inconclusive"),
  )
}

///|
test "relation point graph 52 compressed WW source path retains intermediate tombstone and reinsert" {
  let body = [rpg_begin("A"), rpg_write("A", "1", "v1", Some("v0"))]
  rpg_commit(body, "A")
  body.push(rpg_begin("B"))
  body.push(rpg_write("B", "1", "d2", Some("v1"), action="delete"))
  body.push(rpg_write("B", "1", "v3", Some("d2"), action="insert"))
  rpg_commit(body, "B")
  let result = rpg_graph(body)
  assert_true(result.base.complete)
  let edge = result.base.edges.filter(edge => edge.kind == WW)[0]
  let path = v3_test_items(result.base.sources.at(edge)[0], "predecessorPath")
  assert_eq(path.length(), 3)
  assert_eq(path.map(source => v4_test_at(source, ["fact", "version"])), [
    Json("v3"),
    Json("d2"),
    Json("v1"),
  ])
  assert_eq(v4_test_at(path[1], ["original", "action"]), Json("delete"))
}

///|
test "relation point graph 53 zero work snapshot with zero budget completes but source work does not" {
  let empty = rpg_graph([], empty=true, max_checks=0)
  assert_true(empty.base.complete)
  assert_eq(empty.checks, 0)
  let nonempty = rpg_graph([], max_checks=0)
  assert_false(nonempty.base.complete)
  assert_true(nonempty.limited)
}

///|
test "relation point graph 54 one thousand serial histories never receive a graph counterexample" {
  let mut random = 174931L
  for sample in 0..<1000 {
    let body : Array[Json] = []
    let versions = ["v0", "u0", "z0"]
    let deleted = [false, false, false]
    for tx_index in 0..<3 {
      let tx = "T" + tx_index.to_string()
      body.push(rpg_begin(tx))
      for operation in 0..<4 {
        random = (random * 1103515245L + 12345L) & 2147483647L
        let key = (random % 3L).to_int()
        let mode = (random / 3L % 3L).to_int()
        let wire = (key + 1).to_string()
        if mode == 0 {
          body.push(
            rpg_read(
              tx,
              wire,
              if deleted[key] {
                None
              } else {
                Some(versions[key])
              },
            ),
          )
        } else {
          let version = "s" +
            sample.to_string() +
            "-" +
            tx_index.to_string() +
            "-" +
            operation.to_string()
          let action = if deleted[key] {
            "insert"
          } else if mode == 2 {
            "delete"
          } else {
            "update"
          }
          body.push(rpg_write(tx, wire, version, Some(versions[key]), action~))
          versions[key] = version
          deleted[key] = action == "delete"
        }
      }
      rpg_commit(body, tx)
    }
    let parsed = relation_v3_parse(rpg_trace(body).stringify())
    let exact = relation_v3_analyze_parsed(parsed, {
      max_states: 100000,
      max_operations: 1000000,
    })
    assert_eq(capture_field(exact, "status"), Json("consistent"))
    let graph = relation_graph_point_v4(parsed)
    for category in ["G0", "G1c", "G2-item"] {
      assert_true(rpg_cycle(graph, category).is_empty())
    }
    for category in ["G1a", "G1b", "INT"] {
      assert_true(rpg_direct(graph, category).is_empty())
    }
  }
}

///|
test "relation point graph 55 varied multi write skews match the independent serial interpreter" {
  for sample in 0..<128 {
    let first = sample % 3
    let second = (first + 1) % 3
    let keys = ["1", "2", "3"]
    let initial = ["v0", "u0", "z0"]
    let body = [rpg_begin("A"), rpg_begin("B")]
    let read_a = rpg_read("A", keys[second], Some(initial[second]))
    let read_b = rpg_read("B", keys[first], Some(initial[first]))
    if sample % 2 == 0 {
      body.push(read_a)
      body.push(read_b)
    } else {
      body.push(read_b)
      body.push(read_a)
    }
    let mut a = initial[first]
    let mut b = initial[second]
    for step in 0..<(1 + sample % 3) {
      let next_a = "a" + step.to_string()
      let next_b = "b" + step.to_string()
      let write_a = rpg_write("A", keys[first], next_a, Some(a))
      let write_b = rpg_write("B", keys[second], next_b, Some(b))
      if sample % 4 < 2 {
        body.push(write_a)
        body.push(write_b)
      } else {
        body.push(write_b)
        body.push(write_a)
      }
      a = next_a
      b = next_b
    }
    rpg_commit(body, "A")
    rpg_commit(body, "B")
    let parsed = relation_v3_parse(rpg_trace(body).stringify())
    assert_eq(
      capture_field(
        relation_v3_analyze_parsed(parsed, {
          max_states: 100000,
          max_operations: 1000000,
        }),
        "status",
      ),
      Json("violation"),
    )
    let graph = relation_graph_point_v4(parsed)
    assert_true(graph.base.complete)
    let cycle = rpg_cycle(graph, "G2-item")
    assert_eq(cycle.length(), 2)
    assert_true(cycle.all(edge => edge.kind == RW))
  }
}

///|
test "relation point graph 56 internal mismatch does not mask independent aborted or intermediate source" {
  for aborted in [true, false] {
    let body = [rpg_begin("P"), rpg_write("P", "1", "p1", Some("v0"))]
    if aborted {
      body.push({ "kind": "rollback_ok", "tx": "P" })
    } else {
      body.push(rpg_write("P", "1", "p2", Some("p1")))
      rpg_commit(body, "P")
    }
    body.push(rpg_begin("A"))
    body.push(
      rpg_write("A", "1", "a1", if aborted { Some("v0") } else { Some("p2") }),
    )
    body.push(rpg_read("A", "1", Some("p1")))
    rpg_commit(body, "A")
    let result = rpg_graph(body)
    assert_eq(rpg_direct(result, "INT").length(), 1)
    assert_eq(
      rpg_direct(result, if aborted { "G1a" } else { "G1b" }).length(),
      1,
    )
    assert_false(result.base.complete)
  }
}

///|
fn rpg_ambiguous_raw_delete_body(mode : String) -> Array[Json] {
  let body = [rpg_begin("P")]
  if mode == "reverted" {
    body.push({ "kind": "savepoint", "tx": "P", "name": "s", "instance": "s1" })
  }
  body.push(rpg_write("P", "1", "p-delete", Some("v0"), action="delete"))
  let mut predecessor = "v0"
  if mode == "aborted" {
    body.push({ "kind": "rollback_ok", "tx": "P" })
  } else if mode == "reverted" {
    body.push({ "kind": "rollback_to", "tx": "P", "instance": "s1" })
    rpg_commit(body, "P")
  } else if mode == "intermediate" {
    body.push(
      rpg_write("P", "1", "p-reinsert", Some("p-delete"), action="insert"),
    )
    rpg_commit(body, "P")
    predecessor = "p-reinsert"
  } else {
    body.push({ "kind": "commit_request", "tx": "P" })
  }
  body.push(rpg_begin("D"))
  body.push(rpg_write("D", "1", "d-final", Some(predecessor), action="delete"))
  rpg_commit(body, "D")
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "1", None))
  rpg_commit(body, "R")
  body
}

///|
test "relation point graph 57 empty reads cannot discard nonfinal raw delete candidates" {
  for mode in ["aborted", "reverted", "intermediate", "unknown"] {
    let result = rpg_graph(rpg_ambiguous_raw_delete_body(mode))
    assert_eq(
      mode + ":" + result.index.reads[0].reason,
      mode + ":ambiguous-point-absence",
    )
    assert_false(result.base.complete)
    assert_false(
      result.base.edges.any(edge => edge.kind == WR && edge.to == "R"),
    )
    assert_false(result.index.reads[0].usable)
  }
}

///|
test "relation point graph 58 unique nonfinal tombstone is not promoted to a committed absence source" {
  for mode in ["aborted", "reverted", "intermediate", "unknown"] {
    let body = [rpg_begin("P")]
    if mode == "reverted" {
      body.push({
        "kind": "savepoint",
        "tx": "P",
        "name": "s",
        "instance": "s1",
      })
    }
    body.push(rpg_write("P", "1", "p-delete", Some("v0"), action="delete"))
    if mode == "aborted" {
      body.push({ "kind": "rollback_ok", "tx": "P" })
    } else if mode == "reverted" {
      body.push({ "kind": "rollback_to", "tx": "P", "instance": "s1" })
      rpg_commit(body, "P")
    } else if mode == "intermediate" {
      body.push(
        rpg_write("P", "1", "p-reinsert", Some("p-delete"), action="insert"),
      )
      rpg_commit(body, "P")
    } else {
      body.push({ "kind": "commit_request", "tx": "P" })
    }
    body.push(rpg_begin("R"))
    body.push(rpg_read("R", "1", None))
    rpg_commit(body, "R")
    let result = rpg_graph(body)
    assert_false(result.base.complete)
    assert_false(result.index.reads[0].usable)
    assert_false(
      result.base.edges.any(edge => edge.kind == WR && edge.to == "R"),
    )
  }
}

///|
test "relation point graph 59 raw absence candidates are not filtered using cross connection event seq" {
  let body = [
    rpg_begin("D"),
    rpg_write("D", "1", "d1", Some("v0"), action="delete"),
  ]
  rpg_commit(body, "D")
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "1", None))
  rpg_commit(body, "R")
  body.push(rpg_begin("P"))
  body.push(rpg_write("P", "1", "p-insert", Some("d1"), action="insert"))
  body.push(rpg_write("P", "1", "p-delete", Some("p-insert"), action="delete"))
  body.push({ "kind": "rollback_ok", "tx": "P" })
  let result = rpg_graph(body)
  assert_eq(result.index.reads[0].reason, "ambiguous-point-absence")
  assert_false(result.base.edges.any(edge => edge.kind == WR && edge.to == "R"))
}

///|
test "relation point graph 60 confirmed aborted writes do not poison later legal committed sources" {
  let body = [
    rpg_begin("P"),
    rpg_write("P", "1", "p1", Some("v0")),
    ({ "kind": "rollback_ok", "tx": "P" } : Json),
    rpg_begin("A"),
    rpg_write("A", "1", "v1", Some("v0")),
  ]
  rpg_commit(body, "A")
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "1", Some("v1")))
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(result.base.complete)
  assert_false(result.index.surviving[result.index.versions.at("p1")])
  assert_false(rpg_gap(result, "relation-effect-ledger-mismatch"))
  assert_false(rpg_gap(result, "relation-final-effect-ledger-mismatch"))
  assert_true(
    result.base.edges.any(edge => {
      edge.kind == WR && edge.from == "A" && edge.to == "R"
    }),
  )
}

///|
fn rpg_external_changed_body(mode : String) -> Array[Json] {
  let key = if mode == "absence-present" { "4" } else { "1" }
  let body = [rpg_begin("W")]
  if mode == "absence-present" {
    body.push(rpg_write("W", key, "v1", None, action="insert"))
  } else {
    body.push(
      rpg_write(
        "W",
        key,
        "v1",
        Some("v0"),
        action=if mode == "present-absence" { "delete" } else { "update" },
      ),
    )
  }
  rpg_commit(body, "W")
  body.push(rpg_begin("R"))
  if mode == "savepoint" {
    body.push({ "kind": "savepoint", "tx": "R", "name": "s", "instance": "s1" })
  }
  body.push(
    rpg_read(
      "R",
      key,
      if mode == "absence-present" {
        None
      } else {
        Some("v0")
      },
    ),
  )
  if mode == "savepoint" {
    body.push({ "kind": "rollback_to", "tx": "R", "instance": "s1" })
  }
  body.push(
    rpg_read(
      "R",
      key,
      if mode == "present-absence" {
        None
      } else {
        Some("v1")
      },
    ),
  )
  rpg_commit(body, "R")
  body
}

///|
test "relation point graph 61 external same key version change is formal INT" {
  let result = rpg_graph(rpg_external_changed_body("version"))
  assert_eq(rpg_direct(result, "INT").length(), 1)
}

///|
test "relation point graph 62 external read expectation survives savepoint rollback" {
  let result = rpg_graph(rpg_external_changed_body("savepoint"))
  assert_eq(rpg_direct(result, "INT").length(), 1)
}

///|
test "relation point graph 63 uniquely known present to absence change is formal INT" {
  assert_eq(
    rpg_direct(rpg_graph(rpg_external_changed_body("present-absence")), "INT").length(),
    1,
  )
}

///|
test "relation point graph 64 known initial absence to present change is formal INT" {
  assert_eq(
    rpg_direct(rpg_graph(rpg_external_changed_body("absence-present")), "INT").length(),
    1,
  )
}

///|
test "relation point graph 65 own delivered read cannot overwrite the external base across rollback" {
  let body = [
    rpg_begin("R"),
    rpg_read("R", "1", Some("v0")),
    ({ "kind": "savepoint", "tx": "R", "name": "s", "instance": "s1" } : Json),
    rpg_write("R", "1", "own", Some("v0")),
    rpg_read("R", "1", Some("own")),
    ({ "kind": "rollback_to", "tx": "R", "instance": "s1" } : Json),
    rpg_read("R", "1", Some("v0")),
  ]
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(rpg_direct(result, "INT").is_empty())
  assert_true(result.base.complete)
}

///|
test "relation point graph 66 known aborted and intermediate identities do not hide external INT" {
  for aborted in [true, false] {
    let body = [rpg_begin("W"), rpg_write("W", "1", "v1", Some("v0"))]
    if aborted {
      body.push({ "kind": "rollback_ok", "tx": "W" })
    } else {
      body.push(rpg_write("W", "1", "v2", Some("v1")))
      rpg_commit(body, "W")
    }
    body.push(rpg_begin("R"))
    body.push(rpg_read("R", "1", Some("v0")))
    body.push(rpg_read("R", "1", Some("v1")))
    rpg_commit(body, "R")
    let result = rpg_graph(body)
    assert_eq(rpg_direct(result, "INT").length(), 1)
    assert_eq(
      rpg_direct(result, if aborted { "G1a" } else { "G1b" }).length(),
      1,
    )
  }
}

///|
test "relation point graph 67 unknown producer outcome does not erase known delivered identity INT" {
  let body = [
    rpg_begin("W"),
    rpg_write("W", "1", "v1", Some("v0")),
    ({ "kind": "commit_request", "tx": "W" } : Json),
    rpg_begin("R"),
    rpg_read("R", "1", Some("v0")),
    rpg_read("R", "1", Some("v1")),
  ]
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_eq(rpg_direct(result, "INT").length(), 1)
  assert_false(result.base.complete)
}

///|
fn rpg_unproved_between_body(
  kind : String,
  after~ : Bool = false,
  other_tx~ : Bool = false,
) -> Array[Json] {
  let body = [rpg_begin("W"), rpg_write("W", "1", "v1", Some("v0"))]
  rpg_commit(body, "W")
  let unknown_tx = if other_tx { "U" } else { "R" }
  if other_tx {
    body.push(rpg_begin("U"))
  }
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "1", Some("v0")))
  let unknown : Json = if kind == "condition" {
    {
      "kind": "condition",
      "tx": Json(unknown_tx),
      "predicate": {},
      "matched": true,
    }
  } else {
    {
      "kind": "statement",
      "tx": Json(unknown_tx),
      "sql": "SELECT may_change_unobserved_state()",
    }
  }
  if !after {
    body.push(unknown)
  }
  body.push(rpg_read("R", "1", Some("v1")))
  if after {
    body.push(unknown)
  }
  if other_tx {
    rpg_commit(body, "U")
  }
  rpg_commit(body, "R")
  body
}

///|
test "relation point graph 68 unproved SQL or condition blocks comparisons across its actual position" {
  for kind in ["statement", "condition"] {
    let result = rpg_graph(rpg_unproved_between_body(kind))
    assert_true(rpg_direct(result, "INT").is_empty())
    assert_false(result.base.complete)
    assert_true(rpg_gap(result, "relation-unproved-program-prefix"))
  }
}

///|
test "relation point graph 69 unproved later operations cannot erase earlier completed INT" {
  for kind in ["statement", "condition"] {
    assert_eq(
      rpg_direct(rpg_graph(rpg_unproved_between_body(kind, after=true)), "INT").length(),
      1,
    )
  }
}

///|
test "relation point graph 70 other transaction unproved program does not hide a reliable INT" {
  assert_eq(
    rpg_direct(
      rpg_graph(rpg_unproved_between_body("statement", other_tx=true)),
      "INT",
    ).length(),
    1,
  )
}

///|
test "relation point graph 71 missing source cannot be skipped to compare nonadjacent known reads" {
  let body = [rpg_begin("W"), rpg_write("W", "1", "v1", Some("v0"))]
  rpg_commit(body, "W")
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "1", Some("v0")))
  body.push(rpg_read("R", "1", Some("unknown")))
  body.push(rpg_read("R", "1", Some("v1")))
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(rpg_direct(result, "INT").is_empty())
  assert_false(result.base.complete)
}

///|
test "relation point graph 72 ambiguous negative source cannot be used as an external read baseline" {
  let body = rpg_ambiguous_raw_delete_body("aborted")
  body.pop() |> ignore
  body.pop() |> ignore
  body.push(rpg_read("R", "1", Some("v0")))
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(rpg_direct(result, "INT").is_empty())
  assert_true(rpg_gap(result, "ambiguous-point-absence"))
}

///|
test "relation point graph 73 unproved own mutation prevents a fabricated local INT" {
  let body = [
    rpg_begin("R"),
    rpg_write("R", "1", "own", Some("v0")),
    (
      {
        "kind": "statement",
        "tx": "R",
        "sql": "SELECT may_restore_own_state()",
      } : Json),
    rpg_read("R", "1", Some("v0")),
  ]
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(rpg_direct(result, "INT").is_empty())
  assert_true(rpg_gap(result, "relation-unproved-program-prefix"))
}

///|
test "relation point graph 74 unknown semantics do not justify own predecessor mismatch after their boundary" {
  let body = [
    rpg_begin("R"),
    rpg_write("R", "1", "own", Some("v0")),
    ({ "kind": "condition", "tx": "R", "predicate": {}, "matched": true } : Json),
    rpg_write("R", "1", "later", Some("v0")),
  ]
  rpg_commit(body, "R")
  let result = rpg_graph(body)
  assert_true(rpg_direct(result, "INT").is_empty())
  assert_false(result.base.complete)
}

///|
test "relation point graph 75 reliable external INT keeps exact nearest raw reads and query identities" {
  let result = rpg_graph(rpg_external_changed_body("version"))
  let proof = rpg_direct(result, "INT")[0]
  assert_eq(
    v4_test_at(proof, ["expectedExternalObservation", "queryIndex"]),
    Json(0),
  )
  assert_eq(
    v4_test_at(proof, ["actualExternalObservation", "queryIndex"]),
    Json(1),
  )
  assert_eq(
    v4_test_at(proof, [
      "expectedExternalObservation", "readSource", "source", "fact", "version",
    ]),
    Json("v0"),
  )
  assert_eq(
    v4_test_at(proof, [
      "actualExternalObservation", "readSource", "source", "fact", "version",
    ]),
    Json("v1"),
  )
  assert_eq(
    v4_test_at(proof, ["expectedExternalObservation", "original", "kind"]),
    Json("row_read"),
  )
  assert_eq(
    v4_test_at(proof, ["actualExternalObservation", "original", "seq"]),
    capture_field(proof, "observationSeq"),
  )
}

///|
fn rpg_own_successor_body(
  own_read~ : Bool = false,
  back_read~ : Bool = true,
) -> Array[Json] {
  let body = [rpg_begin("A"), rpg_begin("B")]
  if !own_read {
    body.push(rpg_read("A", "1", Some("v0")))
  }
  body.push(rpg_write("A", "1", "x1", Some("v0")))
  if own_read {
    body.push(rpg_read("A", "1", Some("x1")))
  }
  body.push(rpg_write("B", "1", "x2", Some("x1")))
  if back_read {
    body.push(rpg_write("B", "2", "y1", Some("u0")))
    body.push(rpg_read("A", "2", Some("y1")))
  }
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  body
}

///|
test "relation point graph 76 own read contributes no item RW to a later writer" {
  let result = rpg_graph(rpg_own_successor_body(own_read=true))
  assert_false(result.base.edges.any(edge => edge.kind == RW))
  assert_eq(rpg_cycle(result, "G1c").length(), 2)
  assert_true(rpg_cycle(result, "G2-item").is_empty())
}

///|
test "relation point graph 77 own direct successor cannot be skipped to invent a G2 label" {
  let result = rpg_graph(rpg_own_successor_body())
  assert_false(result.base.edges.any(edge => edge.kind == RW))
  assert_eq(rpg_cycle(result, "G1c").length(), 2)
  assert_true(rpg_cycle(result, "G2-item").is_empty())
}

///|
test "relation point graph 78 acyclic old read own write chain has WW without transitive RW" {
  let result = rpg_graph(rpg_own_successor_body(back_read=false))
  assert_true(result.base.complete)
  assert_eq(result.base.edges.length(), 1)
  assert_true(result.base.edges[0].kind == WW)
}

///|
fn rpg_direct_successor_cycle_body() -> Array[Json] {
  let body = [
    rpg_begin("R"),
    rpg_read("R", "1", Some("v0")),
    rpg_begin("B"),
    rpg_write("B", "1", "x1", Some("v0")),
    rpg_begin("C"),
    rpg_write("C", "1", "x2", Some("x1")),
    rpg_write("C", "2", "y1", Some("u0")),
    rpg_read("R", "2", Some("y1")),
  ]
  rpg_commit(body, "B")
  rpg_commit(body, "C")
  rpg_commit(body, "R")
  body
}

///|
test "relation point graph 79 later writer is reachable by complete WW path rather than direct RW shortcut" {
  let result = rpg_graph(rpg_direct_successor_cycle_body())
  assert_false(
    result.base.edges.any(edge => {
      edge.kind == RW && edge.from == "R" && edge.to == "C"
    }),
  )
  assert_true(
    result.base.edges.any(edge => {
      edge.kind == RW && edge.from == "R" && edge.to == "B"
    }),
  )
  assert_true(
    result.base.edges.any(edge => {
      edge.kind == WW && edge.from == "B" && edge.to == "C"
    }),
  )
  let cycle = rpg_cycle(result, "G2-item")
  assert_eq(cycle.length(), 3)
  assert_eq(cycle.filter(edge => edge.kind == RW).length(), 1)
  for edge in cycle {
    assert_false(result.base.sources.at(edge).is_empty())
  }
}

///|
test "relation point graph 80 rolled back local writes are not installed successors and cannot suppress real RW" {
  let body = [
    rpg_begin("A"),
    rpg_read("A", "1", Some("v0")),
    ({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "s1" } : Json),
    rpg_write("A", "1", "discarded", Some("v0")),
    ({ "kind": "rollback_to", "tx": "A", "instance": "s1" } : Json),
    rpg_begin("B"),
    rpg_write("B", "1", "x2", Some("v0")),
    rpg_write("B", "2", "y1", Some("u0")),
    rpg_read("A", "2", Some("y1")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  let result = rpg_graph(body)
  assert_true(
    result.base.edges.any(edge => {
      edge.kind == RW && edge.from == "A" && edge.to == "B"
    }),
  )
  assert_eq(rpg_cycle(result, "G2-item").length(), 2)
}

///|
test "relation point graph 81 initial absence also stops on the reader own installed insert" {
  let body = [
    rpg_begin("A"),
    rpg_read("A", "4", None),
    rpg_write("A", "4", "x1", None, action="insert"),
    rpg_begin("B"),
    rpg_write("B", "4", "x2", Some("x1")),
    rpg_write("B", "2", "y1", Some("u0")),
    rpg_read("A", "2", Some("y1")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  let result = rpg_graph(body)
  assert_false(result.base.edges.any(edge => edge.kind == RW))
  assert_eq(rpg_cycle(result, "G1c").length(), 2)
  assert_true(rpg_cycle(result, "G2-item").is_empty())
}

///|
fn rpg_write_source_mismatch_body() -> Array[Json] {
  let body = [
    rpg_begin("A"), rpg_begin("B"),
    rpg_write("A", "1", "A1", Some("v0")),
    rpg_write("B", "1", "B1", Some("A1")),
    rpg_write("A", "1", "A2", Some("B1")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  body
}

///|
test "relation point graph 82 original independent write only mismatch is not read INT" {
  let result = rpg_graph(rpg_write_source_mismatch_body())
  assert_true(result.index.reads.is_empty())
  assert_true(rpg_direct(result, "INT").is_empty())
  assert_true(rpg_gap(result, "invalid-local-row-write"))
  assert_false(result.base.complete)
}

///|
fn rpg_local_write_mismatch_body(read_after~ : Bool = true) -> Array[Json] {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "A1", Some("v0")),
    rpg_write("A", "1", "A2", Some("v0")),
  ]
  if read_after {
    body.push(rpg_read("A", "1", Some("v0")))
  }
  rpg_commit(body, "A")
  body
}

///|
test "relation point graph 83 unknown local write state cannot manufacture a later own read INT" {
  let result = rpg_graph(rpg_local_write_mismatch_body())
  assert_true(rpg_direct(result, "INT").is_empty())
  assert_true(rpg_gap(result, "relation-unproved-program-prefix"))
  assert_false(result.index.reads[0].usable)
  assert_false(relation_point_program_known_v4(result.index, "A", result.index.reads[0].seq))
}

///|
test "relation point graph 84 inactive own predecessor is a write source gap not a read witness" {
  let body = [
    rpg_begin("A"),
    ({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "s1" } : Json),
    rpg_write("A", "1", "A1", Some("v0")),
    ({ "kind": "rollback_to", "tx": "A", "instance": "s1" } : Json),
    rpg_write("A", "1", "A2", Some("A1")),
    rpg_read("A", "1", Some("v0")),
  ]
  rpg_commit(body, "A")
  let result = rpg_graph(body)
  assert_true(rpg_direct(result, "INT").is_empty())
  assert_true(rpg_gap(result, "own-predecessor-not-active"))
  assert_true(rpg_gap(result, "relation-unproved-program-prefix"))
}

///|
test "relation point graph 85 earlier actual read INT survives a later unknown write state" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "A1", Some("v0")),
    rpg_read("A", "1", Some("v0")),
    rpg_write("A", "1", "A2", Some("v0")),
    rpg_read("A", "1", Some("v0")),
  ]
  rpg_commit(body, "A")
  let result = rpg_graph(body)
  assert_eq(rpg_direct(result, "INT").length(), 1)
  let proof = rpg_direct(result, "INT")[0]
  assert_eq(v4_test_at(proof, ["original", "kind"]), Json("row_read"))
  assert_eq(capture_field(proof, "queryIndex"), Json(0))
  assert_eq(capture_field(proof, "observationSeq"), Json(4))
}

///|
test "relation point graph 86 missing predecessor prevents invented read after invalid first write" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "A1", Some("missing")),
    rpg_read("A", "1", Some("v0")),
  ]
  rpg_commit(body, "A")
  let result = rpg_graph(body)
  assert_true(rpg_direct(result, "INT").is_empty())
  assert_true(rpg_gap(result, "missing-row-predecessor-source"))
  assert_true(rpg_gap(result, "relation-unproved-program-prefix"))
}

///|
test "relation point graph 87 known write followed by stale delivered read remains INT with exact query index" {
  let body = [
    rpg_begin("A"),
    rpg_read("A", "2", Some("u0")),
    rpg_write("A", "1", "A1", Some("v0")),
    rpg_read("A", "1", Some("v0")),
  ]
  rpg_commit(body, "A")
  let result = rpg_graph(body)
  let proofs = rpg_direct(result, "INT")
  assert_eq(proofs.length(), 1)
  assert_eq(capture_field(proofs[0], "queryIndex"), Json(1))
  assert_eq(v4_test_at(proofs[0], ["original", "kind"]), Json("row_read"))
  assert_eq(v4_test_at(proofs[0], ["original", "seq"]), capture_field(proofs[0], "observationSeq"))
}

///|
test "relation point graph 88 every retained INT proof points to an actually delivered query" {
  let own = [rpg_begin("A"), rpg_write("A", "1", "A1", Some("v0")), rpg_read("A", "1", Some("v0"))]
  rpg_commit(own, "A")
  let revoked = [
    rpg_begin("A"),
    ({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "s1" } : Json),
    rpg_write("A", "1", "A1", Some("v0")),
    ({ "kind": "rollback_to", "tx": "A", "instance": "s1" } : Json),
    rpg_read("A", "1", Some("A1")),
  ]
  rpg_commit(revoked, "A")
  for body in [own, revoked, rpg_external_changed_body("version")] {
    let result = rpg_graph(body)
    assert_false(rpg_direct(result, "INT").is_empty())
    for proof in rpg_direct(result, "INT") {
      assert_eq(v4_test_at(proof, ["original", "kind"]), Json("row_read"))
      assert_eq(v4_test_at(proof, ["original", "seq"]), capture_field(proof, "observationSeq"))
      assert_true(result.index.reads.any(read => {
        capture_field(proof, "queryIndex") == Json(read.query_index) &&
        capture_field(proof, "observationSeq") == Json(read.seq.to_double()) &&
        capture_field(proof, "transaction") == Json(read.tx)
      }))
    }
  }
}
