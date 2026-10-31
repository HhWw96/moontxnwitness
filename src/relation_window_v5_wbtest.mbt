///|
fn rw5_history(body : Array[Json], missing~ : Array[Int32] = []) -> HistoryV4 {
  let raw = rpg_trace(body)
  let events = capture_source_array_v4(
    object_fields_unchecked_v3(raw).at("events"),
  )
  object_fields_unchecked_v3(raw)["events"] = Json(
    events.filter(e => {
      !missing.contains(rcl_number(relation_classification_at_v4(e, ["seq"])))
    }),
  )
  parse_history_v4(raw.stringify()).unwrap()
}

///|
fn rw5_rollback_body(kind : String) -> Array[Json] {
  if kind == "INT" {
    let body = [
      rpg_begin("A"),
      ({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "s1" } : Json),
      rpg_write("A", "1", "v1", Some("v0")),
      rpg_read("A", "1", Some("v1")),
      ({ "kind": "rollback_to", "tx": "A", "instance": "s1" } : Json),
      rpg_read("A", "1", Some("v0")),
    ]
    rpg_commit(body, "A")
    body
  } else {
    let body = [
      rpg_begin("P"),
      rpg_write("P", "1", "p1", Some("v0")),
      ({ "kind": "savepoint", "tx": "P", "name": "s", "instance": "s1" } : Json),
      rpg_write("P", "1", "p2", Some("p1")),
      ({ "kind": "rollback_to", "tx": "P", "instance": "s1" } : Json),
    ]
    rpg_commit(body, "P")
    body.push(rpg_begin("R"))
    body.push(rpg_read("R", "1", Some("p1")))
    rpg_commit(body, "R")
    body
  }
}

///|
fn rw5_status(
  history : HistoryV4,
  category : String,
  max_graph_checks~ : Int32 = 1000000,
) -> String {
  relation_category_rule_status_v4(
    classify_relation_point_v4(
      history,
      categories=[category],
      max_graph_checks~,
    ),
    category,
  )
}

///|
test "relation window v5 01 missing rollback cannot invent own-read INT" {
  let body = rw5_rollback_body("INT")
  assert_eq(rw5_status(rw5_history(body), "INT"), "checked-compatible")
  assert_eq(rw5_status(rw5_history(body, missing=[6]), "INT"), "unknown")
}

///|
test "relation window v5 02 missing rollback cannot invent committed intermediate source" {
  let body = rw5_rollback_body("G1b")
  assert_eq(rw5_status(rw5_history(body), "G1b"), "checked-compatible")
  assert_eq(rw5_status(rw5_history(body, missing=[6]), "G1b"), "unknown")
}

///|
test "relation window v5 03 a damaged window has no completed journal or installed graph" {
  let h = rw5_history(rw5_rollback_body("G1b"), missing=[6])
  let graph = build_relation_point_graph_v4(h).unwrap()
  assert_true(graph.index.window_unproven)
  assert_false(graph.index.journal_complete)
  assert_false(graph.index.orders_complete)
  assert_true(graph.base.edges.is_empty())
}

///|
test "relation window v5 04 zero budget never claims a direct source proof" {
  let h = rw5_history(rw5_rollback_body("INT"), missing=[6])
  let graph = build_relation_point_graph_v4(h, max_checks=0).unwrap()
  assert_eq(graph.checks, 0)
  assert_true(graph.limited)
  assert_eq(rw5_status(h, "INT", max_graph_checks=0), "unknown")
}

///|
fn rw5_aborted_body() -> Array[Json] {
  let body = [
    rpg_begin("P"),
    rpg_read("P", "1", Some("v0")),
    rpg_write("P", "1", "p1", Some("v0")),
    ({ "kind": "rollback_ok", "tx": "P" } : Json),
    rpg_begin("R"),
    rpg_read("R", "1", Some("p1")),
  ]
  rpg_commit(body, "R")
  body
}

///|
test "relation window v5 05 confirmed whole abort G1a does not depend on unobserved rollback" {
  let h = rw5_history(rw5_aborted_body(), missing=[3])
  assert_eq(rw5_status(h, "G1a"), "refuted")
  let report = rcl_report(h, categories=["G1a"])
  let proof = capture_source_array_v4(
      relation_classification_at_v4(report, [
        "judgment", "rules", "G1a", "evidence", "proofs",
      ]),
    )[0]
  assert_eq(
    relation_classification_at_v4(proof, ["source", "writerOutcome"]),
    Json("aborted"),
  )
  assert_eq(
    relation_classification_at_v4(proof, ["source", "effectAuditComplete"]),
    Json(false),
  )
  assert_eq(
    relation_classification_at_v4(proof, ["source", "finalCommittedEffect"]),
    Json::null(),
  )
}

///|
test "relation window v5 06 unknown producer outcome is not confirmed abort" {
  let body = [
    rpg_begin("P"),
    rpg_read("P", "1", Some("v0")),
    rpg_write("P", "1", "p1", Some("v0")),
    rpg_begin("R"),
    rpg_read("R", "1", Some("p1")),
  ]
  rpg_commit(body, "R")
  assert_eq(rw5_status(rw5_history(body, missing=[3]), "G1a"), "unknown")
}

///|
test "relation window v5 07 partial savepoint-revocation ledger is not trusted" {
  let body = [
    rpg_begin("P"),
    ({ "kind": "savepoint", "tx": "P", "name": "s", "instance": "s1" } : Json),
    rpg_read("P", "1", Some("v0")),
    rpg_write("P", "1", "p1", Some("v0")),
    ({ "kind": "rollback_to", "tx": "P", "instance": "s1" } : Json),
  ]
  rpg_commit(body, "P")
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "1", Some("p1")))
  rpg_commit(body, "R")
  assert_eq(rw5_status(rw5_history(body), "G1a"), "refuted")
  assert_eq(rw5_status(rw5_history(body, missing=[4]), "G1a"), "unknown")
}

///|
test "relation window v5 08 earlier exact-prefix INT survives a later missing event" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_read("A", "1", Some("v0")),
    rpg_read("A", "1", Some("v0")),
  ]
  rpg_commit(body, "A")
  assert_eq(rw5_status(rw5_history(body, missing=[5]), "INT"), "refuted")
}

///|
test "relation window v5 09 known begin after unrelated earlier loss has a known local prefix" {
  let body = [rpg_begin("N"), rpg_read("N", "1", Some("v0"))]
  rpg_commit(body, "N")
  body.push(rpg_begin("A"))
  body.push(rpg_write("A", "1", "v1", Some("v0")))
  body.push(rpg_read("A", "1", Some("v0")))
  rpg_commit(body, "A")
  assert_eq(rw5_status(rw5_history(body, missing=[3]), "INT"), "refuted")
}

///|
test "relation window v5 10 multiple lost events keep finality unknown" {
  let body = rw5_rollback_body("G1b")
  assert_eq(rw5_status(rw5_history(body, missing=[6, 10]), "G1b"), "unknown")
}

///|
test "relation window v5 11 known abort proof respects source budget zero" {
  let h = rw5_history(rw5_aborted_body(), missing=[3])
  assert_eq(rw5_status(h, "G1a", max_graph_checks=0), "unknown")
}

///|
test "relation window v5 12 new semantic identity binds caller verification" {
  let h = rw5_history(rw5_rollback_body("INT"), missing=[6])
  let report = rcl_report(h, categories=["INT"])
  assert_eq(
    relation_classification_at_v4(report, ["algorithm"]),
    Json("v4-relation-point-category-5"),
  )
  assert_eq(
    relation_classification_at_v4(report, ["inferences", "graphAlgorithm"]),
    Json("relation-point-row-graph-5"),
  )
  assert_eq(
    relation_classification_at_v4(report, ["inferences", "indexAlgorithm"]),
    Json("relation-point-local-effect-journal-4"),
  )
  assert_true(verify_relation_classification_v4(h, report, categories=["INT"]))
  object_fields_unchecked_v3(report)["algorithm"] = Json(
    "v4-relation-point-category-4",
  )
  assert_false(verify_relation_classification_v4(h, report, categories=["INT"]))
}

///|
test "relation window v5 13 unproven SQL is not erased by the partial-prefix path" {
  let body = [
    rpg_begin("A"),
    rpg_read("A", "1", Some("v0")),
    ({ "kind": "statement", "tx": "A", "sql": "SELECT unknown_effect()" } : Json),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_read("A", "1", Some("v0")),
    rpg_read("A", "1", Some("v0")),
  ]
  rpg_commit(body, "A")
  assert_eq(rw5_status(rw5_history(body, missing=[7]), "INT"), "unknown")
}

///|
test "relation window v5 14 a write predecessor mismatch never fabricates later prefix INT" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_write("A", "1", "v2", Some("v0")),
    rpg_read("A", "1", Some("v1")),
    rpg_read("A", "1", Some("v1")),
  ]
  rpg_commit(body, "A")
  assert_eq(rw5_status(rw5_history(body, missing=[6]), "INT"), "unknown")
}

///|
test "relation window v5 15 a literal unlocated gap does not pretend a known INT prefix" {
  let raw = rpg_trace([
    rpg_begin("A"),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_read("A", "1", Some("v0")),
    ({ "kind": "commit_request", "tx": "A" } : Json),
    ({ "kind": "commit_ok", "tx": "A" } : Json),
  ])
  object_fields_unchecked_v3(raw)["gaps"] = Json([
    ({ "code": "lost-events", "message": "unknown location" } : Json),
  ])
  let h = parse_history_v4(raw.stringify()).unwrap()
  assert_eq(rw5_status(h, "INT"), "unknown")
}

///|
test "relation window v5 16 direct abort proof survives later construction budget exhaustion" {
  let h = rw5_history(rw5_aborted_body(), missing=[3])
  let full = build_relation_point_graph_v4(h).unwrap()
  assert_true(!full.index.direct.get_or_default("G1a", []).is_empty())
  let mut found = false
  for budget in 1..<full.checks {
    let smaller = build_relation_point_graph_v4(h, max_checks=budget).unwrap()
    if smaller.limited &&
      !smaller.index.direct.get_or_default("G1a", []).is_empty() {
      found = true
      break
    }
  }
  // This tiny input may finish immediately after its proof; add a harmless
  // trailing read so that a later exhausted source budget is observable.
  if !found {
    let body = rw5_aborted_body()
    body.push(rpg_begin("N"))
    body.push(rpg_read("N", "1", Some("v0")))
    rpg_commit(body, "N")
    let more = rw5_history(body, missing=[3])
    let total = build_relation_point_graph_v4(more).unwrap().checks
    for budget in 1..<total {
      let smaller = build_relation_point_graph_v4(more, max_checks=budget).unwrap()
      if smaller.limited &&
        !smaller.index.direct.get_or_default("G1a", []).is_empty() {
        found = true
        break
      }
    }
  }
  assert_true(found)
}
