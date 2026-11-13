///|
fn rmt_facts(
  body : Array[Json],
  empty~ : Bool = false,
  clients~ : Array[ModelClientV4] = [],
  clients_complete~ : Bool = false,
) -> ModelFactsV4 {
  model_facts_v4(rpred_history(body, empty~), clients~, clients_complete~).unwrap()
}

///|
fn rmt_report(
  facts : ModelFactsV4,
  models~ : Array[ElleModelV4] = elle_core_models_v4(),
  states~ : Int32 = 100000,
  operations~ : Int32 = 1000000,
  edge_checks~ : Int32 = 1000000,
) -> Json {
  relation_model_classification_v4_json(
    classify_relation_models_v4(
      facts,
      model_options_v4(
        models~,
        max_states=states,
        max_source_checks=operations,
        max_edge_checks=edge_checks,
      ).unwrap(),
    ).unwrap(),
  )
}

///|
fn rmt_single() -> Array[Json] {
  let body = [
    rpg_begin("A"),
    rpg_read("A", "1", Some("v0")),
    rpg_write("A", "1", "a1", Some("v0"), value="yes"),
    rpg_read("A", "1", Some("a1"), value="yes"),
  ]
  rpg_commit(body, "A")
  body
}

///|
test "relation models 01 all fourteen definitions construct an original-program certificate" {
  let facts = rmt_facts(rmt_single())
  let report = rmt_report(facts)
  assert_eq(
    capture_field(report, "semanticContract"),
    Json("relation-predicate-models/v1"),
  )
  for model in elle_core_models_v4() {
    assert_eq(mct_status(report, model), "checked-compatible")
  }
  assert_true(
    verify_relation_models_v4(
      facts,
      report,
      model_options_v4(models=elle_core_models_v4()).unwrap(),
    ),
  )
}

///|
test "relation models 02 predicate phantom skew refutes serial while RR and SI are constructively compatible" {
  let facts = rmt_facts(rpred_empty_skew(), empty=true)
  let report = rmt_report(facts, models=[
    ElleReadCommitted,
    ElleRepeatableRead,
    ElleSnapshotIsolation,
    ElleSerializable,
  ])
  assert_eq(mct_status(report, ElleReadCommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleRepeatableRead), "checked-compatible")
  assert_eq(mct_status(report, ElleSnapshotIsolation), "checked-compatible")
  assert_eq(mct_status(report, ElleSerializable), "refuted")
  let rule = mct_rule(report, ElleSerializable, "graph/D/data-only")
  assert_eq(capture_field(rule, "status"), Json("refuted"))
}

///|
fn rmt_changing_query() -> Array[Json] {
  let body = [
    rpg_begin("R"),
    rpg_read("R", "1", Some("v0")),
    rpg_begin("W"),
    rpg_write("W", "1", "a1", Some("v0")),
  ]
  rpg_commit(body, "W")
  body.push(rpg_read("R", "1", Some("a1")))
  rpg_commit(body, "R")
  body
}

///|
test "relation models 03 RC uses statement prefixes instead of forcing one transaction snapshot" {
  let report = rmt_report(rmt_facts(rmt_changing_query()), models=[
    ElleReadCommitted,
    ElleRepeatableRead,
    ElleSnapshotIsolation,
    ElleSerializable,
  ])
  assert_eq(mct_status(report, ElleReadCommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleRepeatableRead), "refuted")
  assert_eq(mct_status(report, ElleSnapshotIsolation), "refuted")
  assert_eq(mct_status(report, ElleSerializable), "refuted")
}

///|
test "relation models 04 aborted producer proof survives an otherwise incomplete source graph" {
  let body = [
    rpg_begin("P"),
    rpg_write("P", "1", "bad", Some("v0")),
    ({ "kind": "rollback_ok", "tx": "P" } : Json),
    rpg_begin("R"),
    rpg_read("R", "1", Some("bad")),
  ]
  rpg_commit(body, "R")
  let report = rmt_report(rmt_facts(body), models=[
    ElleReadUncommitted,
    ElleReadCommitted,
  ])
  assert_eq(mct_status(report, ElleReadUncommitted), "unknown")
  assert_eq(mct_status(report, ElleReadCommitted), "refuted")
  assert_eq(
    capture_field(mct_rule(report, ElleReadCommitted, "G1a"), "status"),
    Json("refuted"),
  )
}

///|
test "relation models 05 foreign intermediate producer is G1b rather than fabricated SELECT dependence" {
  let body = [
    rpg_begin("P"),
    rpg_write("P", "1", "a1", Some("v0")),
    rpg_begin("R"),
    rpg_read("R", "1", Some("a1")),
    rpg_write("P", "1", "a2", Some("a1")),
  ]
  rpg_commit(body, "P")
  rpg_commit(body, "R")
  let report = rmt_report(rmt_facts(body), models=[ElleReadCommitted])
  assert_eq(mct_status(report, ElleReadCommitted), "refuted")
  assert_eq(
    capture_field(mct_rule(report, ElleReadCommitted, "G1b"), "status"),
    Json("refuted"),
  )
}

///|
test "relation models 06 incomplete delivered query cannot authorize compatibility" {
  let body = [rpg_begin("R"), rpred_read("R", [], complete=false)]
  rpg_commit(body, "R")
  let report = rmt_report(rmt_facts(body, empty=true))
  assert_true(
    v3_test_items(report, "models").all(row => {
      capture_field(row, "status") == Json("unknown")
    }),
  )
}

///|
test "relation models 07 zero state budget is unknown rather than a negative search certificate" {
  let report = rmt_report(rmt_facts(rmt_single()), states=0)
  assert_true(
    v3_test_items(report, "models").all(row => {
      capture_field(row, "status") == Json("unknown")
    }),
  )
}

///|
test "relation models 08 zero semantic budget is explicit and never compatible" {
  let report = rmt_report(rmt_facts(rmt_single()), operations=0)
  assert_true(
    v3_test_items(report, "models").all(row => {
      capture_field(row, "status") == Json("unknown")
    }),
  )
}

///|
test "relation models 09 strong-session requires caller-declared client coverage" {
  let body = [rpg_begin("A"), rpg_read("A", "1", Some("v0"))]
  rpg_commit(body, "A")
  body.push(rpg_begin("B"))
  body.push(rpg_read("B", "2", Some("u0")))
  rpg_commit(body, "B")
  let facts = rmt_facts(body)
  let report = rmt_report(facts)
  assert_eq(mct_status(report, ElleSerializable), "checked-compatible")
  assert_eq(mct_status(report, ElleSessionSerializable), "unknown")
  assert_eq(mct_status(report, ElleStrictSerializable), "checked-compatible")
  let scoped = rmt_report(
    rmt_facts(
      body,
      clients=[{ id: "client", transactions: ["A", "B"], }],
      clients_complete=true,
    ),
  )
  assert_eq(mct_status(scoped, ElleSessionSerializable), "checked-compatible")
}

///|
test "relation models 10 stale read can serialize before a writer but violates explicit real time" {
  let body = [rpg_begin("A"), rpg_write("A", "1", "a1", Some("v0"))]
  rpg_commit(body, "A")
  body.push(rpg_begin("B"))
  body.push(rpg_read("B", "1", Some("v0")))
  rpg_commit(body, "B")
  let report = rmt_report(rmt_facts(body), models=[
    ElleSerializable,
    ElleStrictSerializable,
  ])
  assert_eq(mct_status(report, ElleSerializable), "checked-compatible")
  assert_eq(mct_status(report, ElleStrictSerializable), "refuted")
}

///|
test "relation models 11 savepoint rollback restores own writes and retains delivered queries" {
  let body = [
    rpg_begin("A"),
    ({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "s1" } : Json),
    rpg_write("A", "1", "temp", Some("v0")),
    rpg_read("A", "1", Some("temp")),
    ({ "kind": "rollback_to", "tx": "A", "instance": "s1" } : Json),
    rpg_read("A", "1", Some("v0")),
    rpg_write("A", "2", "final", Some("u0")),
  ]
  rpg_commit(body, "A")
  let report = rmt_report(rmt_facts(body))
  assert_true(
    v3_test_items(report, "models").all(row => {
      capture_field(row, "status") == Json("checked-compatible")
    }),
  )
}

///|
test "relation models 12 source and budget supplied independently reject recomputed-report tampering" {
  let facts = rmt_facts(rmt_single())
  let options = model_options_v4(models=elle_core_models_v4()).unwrap()
  let report = rmt_report(facts)
  let changed = v4_json_copy(report)
  object_fields_unchecked_v3(changed)["status"] = Json("refuted")
  assert_false(verify_relation_models_v4(facts, changed, options))
  let changed_source = rmt_single()
  object_fields_unchecked_v3(changed_source[2])["version"] = Json("other")
  assert_false(
    verify_relation_models_v4(rmt_facts(changed_source), report, options),
  )
  assert_false(
    verify_relation_models_v4(
      facts,
      report,
      model_options_v4(models=elle_core_models_v4(), max_states=99999).unwrap(),
    ),
  )
}

///|
test "relation models 13 exact transaction scope is distinct from predicate graph scope" {
  let body : Array[Json] = []
  for i in 0..<7 {
    let tx = "t" + i.to_string()
    body.push(rpg_begin(tx))
    body.push(rpg_read(tx, "1", Some("v0")))
    rpg_commit(body, tx)
  }
  let report = rmt_report(rmt_facts(body), models=[ElleSerializable])
  assert_eq(mct_status(report, ElleSerializable), "unknown")
  assert_eq(
    capture_field(
      mct_rule(report, ElleSerializable, "graph/D/data-only"),
      "status",
    ),
    Json("checked-compatible"),
  )
}

///|
test "relation models 14 source-gap witness does not become a serial failure refutation of RC" {
  let body = [rpg_begin("R"), rpg_read("R", "1", Some("missing"))]
  rpg_commit(body, "R")
  let report = rmt_report(rmt_facts(body), models=[
    ElleReadCommitted,
    ElleSnapshotIsolation,
    ElleSerializable,
  ])
  assert_true(
    v3_test_items(report, "models").all(row => {
      capture_field(row, "status") == Json("unknown")
    }),
  )
}

///|
test "relation models 15 an unconfirmed commit leaves every positive completion pending" {
  let body = [
    rpg_begin("W"),
    rpg_write("W", "1", "a1", Some("v0")),
    ({ "kind": "commit_request", "tx": "W" } : Json),
    rpg_begin("R"),
    rpg_read("R", "2", Some("u0")),
  ]
  rpg_commit(body, "R")
  let report = rmt_report(rmt_facts(body))
  assert_true(
    v3_test_items(report, "models").all(row => {
      capture_field(row, "status") == Json("unknown")
    }),
  )
}

///|
test "relation models 16 predicate source ambiguity can be discharged by complete original serial replay" {
  let facts = rmt_facts(rpred_false_true_false())
  let report = rmt_report(facts, models=[
    ElleReadCommitted,
    ElleRepeatableRead,
    ElleSnapshotIsolation,
    ElleSerializable,
  ])
  assert_eq(
    capture_field(capture_field(report, "predicateGraph"), "complete"),
    Json(false),
  )
  assert_true(
    v3_test_items(report, "models").all(row => {
      capture_field(row, "status") == Json("checked-compatible")
    }),
  )
}

///|
test "relation models 17 exact operation limit does not turn into a serial failure refutation" {
  let body = [rpg_begin("R")]
  for _ in 0..<129 {
    body.push(rpg_read("R", "1", Some("v0")))
  }
  rpg_commit(body, "R")
  let report = rmt_report(rmt_facts(body), models=[ElleSerializable])
  assert_eq(mct_status(report, ElleSerializable), "unknown")
}

///|
test "relation models 18 an actual G1c remains refuted when completion has no budget" {
  let body = [
    rpg_begin("A"),
    rpg_begin("B"),
    rpg_write("A", "1", "a1", Some("v0")),
    rpg_write("B", "2", "b1", Some("u0")),
    rpg_read("A", "2", Some("b1")),
    rpg_read("B", "1", Some("a1")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  let report = rmt_report(
    rmt_facts(body),
    models=[ElleReadCommitted],
    states=10,
  )
  assert_eq(mct_status(report, ElleReadCommitted), "refuted")
}

///|
test "relation models 19 snapshot write conflict is not accepted from two identical stale predecessors" {
  let body = [
    rpg_begin("A"),
    rpg_begin("B"),
    rpg_read("A", "1", Some("v0")),
    rpg_read("B", "1", Some("v0")),
    rpg_write("A", "1", "a1", Some("v0")),
    rpg_write("B", "1", "b1", Some("v0")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  let report = rmt_report(rmt_facts(body), models=[ElleSnapshotIsolation])
  assert_true(mct_status(report, ElleSnapshotIsolation) != "checked-compatible")
}

///|
test "relation models 20 a non-relation history is rejected by the independent namespace" {
  assert_true(
    classify_relation_models_v4(
      mct_facts(mct_single()),
      model_options_v4().unwrap(),
    )
    is Err(_),
  )
}

///|
test "relation models 21 savepoint controls count toward the exact original action limit" {
  let body = [rpg_begin("R")]
  for i in 0..<64 {
    let instance = "scope" + i.to_string()
    body.push({
      "kind": "savepoint",
      "tx": "R",
      "name": Json(instance),
      "instance": Json(instance),
    })
    body.push({ "kind": "release", "tx": "R", "instance": Json(instance) })
  }
  body.push(rpg_read("R", "1", Some("v0")))
  rpg_commit(body, "R")
  let report = rmt_report(rmt_facts(body), models=[ElleSerializable])
  assert_eq(mct_status(report, ElleSerializable), "unknown")
}

///|
test "relation models 22 Adya RR checks a mixed item and predicate RW cycle" {
  let body = [
    rpg_begin("A"),
    rpg_begin("B"),
    rpg_begin("C"),
    rpg_write("C", "3", "c1", Some("z0")),
    rpg_read("A", "1", Some("v0")),
    rpred_read("B", []),
    rpg_write("B", "1", "b1", Some("v0")),
    rpg_write("C", "4", "c2", None, action="insert", value="yes"),
    rpg_read("A", "3", Some("c1")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  rpg_commit(body, "C")
  let facts = rmt_facts(body)
  let graph = build_relation_predicate_graph_v4(facts.history).unwrap()
  assert_true(rpred_has(graph, "item", RW, "A", "B"))
  assert_true(rpred_has(graph, "predicate", RW, "B", "C"))
  assert_true(rpred_has(graph, "item", WR, "C", "A"))
  let report = rmt_report(facts, models=[
    ElleReadCommitted,
    ElleRepeatableRead,
    ElleSerializable,
  ])
  assert_eq(mct_status(report, ElleRepeatableRead), "refuted")
  assert_eq(
    capture_field(
      mct_rule(report, ElleRepeatableRead, "graph/D-item-mixed/data-only"),
      "status",
    ),
    Json("refuted"),
  )
}

///|
fn rmt_stale_external() -> Array[Json] {
  let body = [rpg_begin("W"), rpg_write("W", "1", "w1", Some("v0"))]
  rpg_commit(body, "W")
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "1", Some("v0")))
  rpg_commit(body, "R")
  body
}

///|
test "relation models 23 missing caller real-time assurance removes RT-only refutation" {
  let facts = rmt_facts(rmt_stale_external())
  let options = model_options_v4(models=[
    ElleSerializable,
    ElleStrictSerializable,
  ]).unwrap()
  let report = relation_model_classification_v4_json(
    classify_relation_models_v4(facts, options, realtime_known=false).unwrap(),
  )
  assert_eq(mct_status(report, ElleSerializable), "checked-compatible")
  assert_eq(mct_status(report, ElleStrictSerializable), "unknown")
  assert_eq(
    capture_field(capture_field(report, "orderFacts"), "realtimeComplete"),
    Json(false),
  )
  assert_eq(
    capture_field(report, "sourcePolicy"),
    ({ "realtimeKnown": false } : Json),
  )
  assert_true(
    verify_relation_models_v4(facts, report, options, realtime_known=false),
  )
  assert_false(verify_relation_models_v4(facts, report, options))
}

///|
test "relation models 24 real-time unknown never hides an independent data G2 witness" {
  let facts = rmt_facts(rrt_g2_body())
  let options = model_options_v4(models=[
    ElleSerializable,
    ElleStrictSerializable,
  ]).unwrap()
  let report = relation_model_classification_v4_json(
    classify_relation_models_v4(facts, options, realtime_known=false).unwrap(),
  )
  assert_eq(mct_status(report, ElleSerializable), "refuted")
  assert_eq(mct_status(report, ElleStrictSerializable), "refuted")
  assert_true(
    verify_relation_models_v4(facts, report, options, realtime_known=false),
  )
}

///|
test "relation models 25 disabling real time retains separately declared logical client order" {
  let facts = rmt_facts(
    rmt_stale_external(),
    clients=[{ id: "logical", transactions: ["W", "R"], }],
    clients_complete=true,
  )
  let options = model_options_v4(models=[
    ElleSessionSerializable,
    ElleStrictSerializable,
  ]).unwrap()
  let report = relation_model_classification_v4_json(
    classify_relation_models_v4(facts, options, realtime_known=false).unwrap(),
  )
  assert_eq(mct_status(report, ElleSessionSerializable), "refuted")
  assert_eq(mct_status(report, ElleStrictSerializable), "unknown")
  assert_eq(
    capture_field(capture_field(report, "orderFacts"), "processComplete"),
    Json(true),
  )
}

///|
test "relation models 26 default real-time policy is explicit in the new report" {
  let facts = rmt_facts(rmt_stale_external())
  let options = model_options_v4(models=[ElleStrictSerializable]).unwrap()
  let report = relation_model_classification_v4_json(
    classify_relation_models_v4(facts, options).unwrap(),
  )
  assert_eq(mct_status(report, ElleStrictSerializable), "refuted")
  assert_eq(
    capture_field(report, "sourcePolicy"),
    ({ "realtimeKnown": true } : Json),
  )
}
