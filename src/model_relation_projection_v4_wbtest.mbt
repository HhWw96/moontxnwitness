///|
fn rmp_one() -> Array[Json] {
  let body = [
    rpg_begin("A"),
    rpg_read("A", "1", Some("v0")),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_read("A", "1", Some("v1")),
  ]
  rpg_commit(body, "A")
  body
}

///|
fn rmp_report(
  history : HistoryV4,
  models~ : Array[ElleModelV4] = elle_core_models_v4(),
  clients~ : Array[ModelClientV4] = [{ id: "logical-A", transactions: ["A"], }],
) -> Json {
  let facts = model_facts_v4(history, clients~, clients_complete=true).unwrap()
  let options = model_options_v4(
    models~,
    relation_profile=ModelRelationAtomicRows,
  ).unwrap()
  model_classification_v4_json(classify_models_v4(facts, options))
}

///|
fn rmp_project(
  body : Array[Json],
  empty~ : Bool = false,
) -> RelationRowProjectionV4 {
  project_relation_rows_v4(rcl_history(body, empty~)).unwrap()
}

///|
test "atomic rows 01 complete real row operations project without register history synthesis" {
  let h = rcl_history(rmp_one())
  let before = history_v4_json(h)
  let p = project_relation_rows_v4(h).unwrap()
  assert_true(p.is_projected())
  let report = relation_row_projection_v4_json(p)
  assert_eq(
    v4_test_at(report, ["scope", "originalHistoryRewritten"]),
    Json(false),
  )
  assert_eq(
    v4_test_at(report, ["derivedProjection", "ownAssignmentsExposeExternalBase"]),
    Json(false),
  )
  assert_eq(
    v4_test_at(report, ["derivedProjection", "programEvents"]),
    object_fields_unchecked_v3(before).at("events"),
  )
  let queries = capture_source_array_v4(
    v4_test_at(report, ["derivedProjection", "queryProjections"]),
  )
  assert_eq(queries.length(), 2)
  assert_eq(v4_test_at(queries[0], ["queryIndex"]), Json(0))
  assert_eq(v4_test_at(queries[0], ["readSeq"]), Json(3))
  assert_true(verify_relation_row_projection_v4(h, report))
  assert_eq(history_v4_json(h), before)
}

///|
test "atomic rows 02 normal point program closes all canonical definitions under explicit policy" {
  let report = rmp_report(rcl_history(rmp_one()))
  for model in elle_core_models_v4() {
    assert_eq(
      mct_status(report, model),
      "checked-compatible",
      msg=model_name_v4(model) + ": " + report.stringify(),
    )
  }
  assert_eq(
    v4_test_at(report, ["sourceProfile"]),
    Json("captured-relation-row-slots/v1"),
  )
}

///|
test "atomic rows 03 old point profile remains the default with its original pending scope" {
  let h = rcl_history(rmp_one())
  let facts = model_facts_v4(h).unwrap()
  let options = model_options_v4(models=[ElleSnapshotIsolation]).unwrap()
  let report = model_classification_v4_json(classify_models_v4(facts, options))
  assert_eq(mct_status(report, ElleSnapshotIsolation), "unknown")
  assert_eq(
    v4_test_at(report, ["options", "relationProfile"]),
    Json("relation-point-final-installed/v1"),
  )
}

///|
test "atomic rows 04 real initial empty point read and insert have an initialAbsent slot" {
  let body = [
    rpg_begin("A"),
    rpg_read("A", "1", None),
    rpg_write("A", "1", "v1", None, action="insert"),
    rpg_read("A", "1", Some("v1")),
  ]
  rpg_commit(body, "A")
  let p = rmp_project(body, empty=true)
  assert_true(p.is_projected())
  assert_eq(p.write_rule.status, "checked-compatible")
  let states = object_fields_unchecked_v3(
    v4_test_at(p.record, ["derivedProjection", "originalRowStates"]),
  )
  assert_true(
    states
    .values()
    .collect()
    .any(v => v4_test_at(v, ["state"]) == Json("initial-absent")),
  )
}

///|
test "atomic rows 05 own delete and actual empty result bind the tombstone effect" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "d1", Some("v0"), action="delete"),
    rpg_read("A", "1", None),
  ]
  rpg_commit(body, "A")
  let p = rmp_project(body)
  assert_true(p.is_projected())
  let ops = p.program.unwrap().transactions[0].ops
  assert_true(ops[0].kind == Write)
  assert_true(ops[1].kind == Read)
  assert_eq(ops[0].version, ops[1].version)
}

///|
test "atomic rows 06 unique external tombstone has a precise actual WR source" {
  let body = [
    rpg_begin("P"),
    rpg_write("P", "1", "d1", Some("v0"), action="delete"),
  ]
  rpg_commit(body, "P")
  body.append([rpg_begin("R"), rpg_read("R", "1", None)])
  rpg_commit(body, "R")
  let p = rmp_project(body)
  assert_true(p.is_projected())
  assert_true(
    p.edges.any(e => e.from == "P" && e.to == "R" && e.kind == ScopedWRItem),
  )
}

///|
test "atomic rows 07 initial absence and a raw delete are not arbitrarily disambiguated" {
  let body = [
    rpg_begin("P"),
    rpg_write("P", "1", "p1", None, action="insert"),
    rpg_write("P", "1", "d1", Some("p1"), action="delete"),
  ]
  rpg_commit(body, "P")
  body.append([rpg_begin("R"), rpg_read("R", "1", None)])
  rpg_commit(body, "R")
  let p = rmp_project(body, empty=true)
  assert_false(p.is_projected())
}

///|
test "atomic rows 08 delete reinsert retains a tombstone and its exact next writer" {
  let body = [
    rpg_begin("P"),
    rpg_write("P", "1", "d1", Some("v0"), action="delete"),
  ]
  rpg_commit(body, "P")
  body.append([
    rpg_begin("R"),
    rpg_read("R", "1", None),
    rpg_begin("Q"),
    rpg_write("Q", "1", "v2", Some("d1"), action="insert"),
  ])
  rpg_commit(body, "Q")
  rpg_commit(body, "R")
  let p = rmp_project(body)
  assert_true(p.is_projected())
  assert_true(
    p.edges.any(e => e.from == "P" && e.to == "Q" && e.kind == ScopedWWItem),
  )
  assert_true(
    p.edges.any(e => e.from == "R" && e.to == "Q" && e.kind == ScopedRWItem),
  )
}

///|
test "atomic rows 09 rollback preserves already delivered own reads and restores the external slot" {
  let body = [
    rpg_begin("A"),
    rpg_read("A", "1", Some("v0")),
    ({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "a-s" } : Json),
    rpg_write("A", "1", "temp", Some("v0")),
    rpg_read("A", "1", Some("temp")),
    ({ "kind": "rollback_to", "tx": "A", "instance": "a-s" } : Json),
    rpg_read("A", "1", Some("v0")),
  ]
  rpg_commit(body, "A")
  let p = rmp_project(body)
  assert_true(p.is_projected())
  assert_eq(p.int_rule.status, "checked-compatible")
  let ops = p.program.unwrap().transactions[0].ops
  assert_true(ops[1].revoked)
  assert_eq(ops.filter(op => op.kind == Read).length(), 3)
}

///|
test "atomic rows 10 an original sequence gap cannot be healed by projection" {
  let raw = rpg_trace(rmp_one())
  let fields = object_fields_unchecked_v3(raw)
  let events = capture_source_array_v4(fields.at("events"))
  fields["events"] = Json(events.filter(e => v4_test_at(e, ["seq"]) != Json(3)))
  let h = parse_history_v4(raw.stringify()).unwrap()
  let before = history_v4_json(h)
  assert_false(project_relation_rows_v4(h).unwrap().is_projected())
  assert_eq(history_v4_json(h), before)
}

///|
test "atomic rows 11 incomplete query is not a complete singleton slot read" {
  let raw = rpg_trace(rmp_one())
  let events = capture_source_array_v4(v4_test_at(raw, ["events"]))
  object_fields_unchecked_v3(events[2])["complete"] = Json(false)
  let h = parse_history_v4(raw.stringify()).unwrap()
  assert_false(project_relation_rows_v4(h).unwrap().is_projected())
}

///|
test "atomic rows 12 ranges and extra AND terms remain outside point row projection" {
  for extra in [false, true] {
    let raw = rpg_trace(rmp_one())
    let events = capture_source_array_v4(v4_test_at(raw, ["events"]))
    let read = object_fields_unchecked_v3(events[2])
    let terms = capture_source_array_v4(read.at("predicate"))
    if extra {
      terms.push({ "column": "value", "op": "eq", "value": "same" })
    } else {
      object_fields_unchecked_v3(terms[0])["op"] = Json("ge")
    }
    read["predicate"] = Json(terms)
    let h = parse_history_v4(raw.stringify()).unwrap()
    assert_false(project_relation_rows_v4(h).unwrap().is_projected())
  }
}

///|
test "atomic rows 13 changing external reads may satisfy RC while violating full INT" {
  let body = [
    rpg_begin("R"),
    rpg_read("R", "1", Some("v0")),
    rpg_begin("P"),
    rpg_write("P", "1", "v1", Some("v0")),
  ]
  rpg_commit(body, "P")
  body.push(rpg_read("R", "1", Some("v1")))
  rpg_commit(body, "R")
  let report = rmp_report(
    rcl_history(body),
    models=[ElleReadCommitted, ElleSnapshotIsolation],
    clients=[],
  )
  assert_eq(
    mct_status(report, ElleReadCommitted),
    "checked-compatible",
    msg=report.stringify(),
  )
  assert_eq(mct_status(report, ElleSnapshotIsolation), "refuted")
}

///|
fn rmp_skew() -> Array[Json] {
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
test "atomic rows 14 write skew is an actual SER refutation but is allowed by SI" {
  let report = rmp_report(
    rcl_history(rmp_skew()),
    models=[ElleReadCommitted, ElleSerializable, ElleSnapshotIsolation],
    clients=[],
  )
  assert_eq(mct_status(report, ElleReadCommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleSerializable), "refuted")
  assert_eq(mct_status(report, ElleSnapshotIsolation), "checked-compatible")
}

///|
fn rmp_unobserved_temporary_preconditions() -> Array[Json] {
  let body = [
    rpg_begin("A"),
    rpg_begin("B"),
    ({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "a-s" } : Json),
    rpg_write("A", "2", "u-temp", Some("u0")),
    ({ "kind": "rollback_to", "tx": "A", "instance": "a-s" } : Json),
    ({ "kind": "savepoint", "tx": "B", "name": "s", "instance": "b-s" } : Json),
    rpg_write("B", "1", "v-temp", Some("v0")),
    ({ "kind": "rollback_to", "tx": "B", "instance": "b-s" } : Json),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_write("B", "2", "u1", Some("u0")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  body
}

///|
test "atomic rows 15 unobserved temporary row preconditions are not manufactured SELECTs" {
  let h = rcl_history(rmp_unobserved_temporary_preconditions())
  let p = project_relation_rows_v4(h).unwrap()
  assert_true(p.is_projected())
  assert_eq(p.write_rule.status, "unknown")
  assert_false(
    p.program.unwrap().transactions.any(tx => tx.ops.any(op => op.kind == Read)),
  )
  let report = rmp_report(h, models=[ElleSerializable, ElleSnapshotIsolation], clients=[])
  assert_eq(mct_status(report, ElleSerializable), "unknown")
  assert_eq(mct_status(report, ElleSnapshotIsolation), "unknown")
}

///|
test "atomic rows 16 no own read can reveal an external overwritten row value" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_read("A", "1", Some("v1")),
  ]
  rpg_commit(body, "A")
  let p = rmp_project(body)
  assert_true(p.is_projected())
  assert_false(
    p.edges.any(e => e.kind == ScopedWRItem || e.kind == ScopedRWItem),
  )
  assert_eq(
    v4_test_at(p.record, [
      "derivedProjection", "ownAssignmentsExposeExternalBase",
    ]),
    Json(false),
  )
}

///|
test "atomic rows 17 required original writer is not deleted from proof source" {
  let h = rcl_history(rmp_one())
  let p = project_relation_rows_v4(h).unwrap()
  let json = relation_row_projection_v4_json(p)
  object_fields_unchecked_v3(json)["observations"] = Json::null()
  assert_false(verify_relation_row_projection_v4(h, json))
  assert_true(
    verify_relation_row_projection_v4(h, relation_row_projection_v4_json(p)),
  )
}

///|
test "atomic rows 18 caller zero and exact budgets do not authorize each other" {
  let h = rcl_history(rmp_one())
  let p = project_relation_rows_v4(h).unwrap()
  let checks = capture_source_seq_v4(
    v4_test_at(p.record, ["execution", "checks"]),
  ).to_int()
  assert_true(
    project_relation_rows_v4(h, max_checks=checks).unwrap().is_projected(),
  )
  let zero = project_relation_rows_v4(h, max_checks=0).unwrap()
  assert_false(zero.is_projected())
  assert_true(verify_relation_row_projection_v4(h, zero.record, max_checks=0))
  assert_false(verify_relation_row_projection_v4(h, zero.record))
}

///|
test "atomic rows 19 old relation options cannot verify an opted in model report" {
  let h = rcl_history(rmp_one())
  let facts = model_facts_v4(h).unwrap()
  let options = model_options_v4(
    models=[ElleSnapshotIsolation],
    relation_profile=ModelRelationAtomicRows,
  ).unwrap()
  let report = model_classification_v4_json(classify_models_v4(facts, options))
  assert_true(verify_models_v4(facts, report, options))
  assert_false(
    verify_models_v4(
      facts,
      report,
      model_options_v4(models=[ElleSnapshotIsolation]).unwrap(),
    ),
  )
}

///|
test "atomic rows 20 raw G1a G1b and actual INT proofs survive unsupported complete projection" {
  for category in ["G1a", "G1b", "INT"] {
    let h = rcl_history(rcl_direct_body(category))
    let before = history_v4_json(h)
    let report = rmp_report(h, models=[ElleSerializable], clients=[])
    assert_eq(mct_status(report, ElleSerializable), "refuted")
    assert_eq(history_v4_json(h), before)
  }
}

///|
test "atomic rows 21 type and category scope do not silently accept list history" {
  assert_true(project_relation_rows_v4(mlp_history(mlp_multi())) is Err(_))
}

///|
test "atomic rows 22 opaque getters cannot mutate later projections or source" {
  let h = rcl_history(rmp_one())
  let p = project_relation_rows_v4(h).unwrap()
  let one = relation_row_projection_v4_json(p)
  object_fields_unchecked_v3(one)["derivedProjection"] = Json::null()
  assert_true(
    v4_test_at(relation_row_projection_v4_json(p), ["derivedProjection"]) !=
    Json::null(),
  )
  assert_true(
    verify_relation_row_projection_v4(h, relation_row_projection_v4_json(p)),
  )
}

///|
test "atomic rows 23 explicit profile preserves complete original source identities" {
  let p = rmp_project(rmp_one())
  let ops = p.program.unwrap().transactions[0].ops
  assert_eq(v4_test_at(ops[0].original, ["kind"]), Json("row_read"))
  assert_eq(v4_test_at(ops[1].original, ["kind"]), Json("row_write"))
  assert_eq(v4_test_at(ops[2].original, ["kind"]), Json("row_read"))
  assert_eq(v4_test_at(ops[0].original, ["seq"]), Json(3))
  assert_eq(v4_test_at(ops[1].original, ["seq"]), Json(4))
}

///|
test "atomic rows 24 own immediate installed successor stops RW before later external writers" {
  let body = [
    rpg_begin("A"),
    rpg_begin("B"),
    rpg_read("A", "1", Some("v0")),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_write("B", "1", "v2", Some("v1")),
    rpg_write("B", "2", "u1", Some("u0")),
    rpg_read("A", "2", Some("u1")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  let p = rmp_project(body)
  assert_true(p.is_projected())
  assert_false(
    p.edges.any(e => e.from == "A" && e.to == "B" && e.kind == ScopedRWItem),
  )
  assert_true(
    p.edges.any(e => e.from == "A" && e.to == "B" && e.kind == ScopedWWItem),
  )
  assert_true(
    p.edges.any(e => e.from == "B" && e.to == "A" && e.kind == ScopedWRItem),
  )
}

///|
test "atomic rows 25 later external reads retain the RC WR cycle" {
  let body = [
    rpg_begin("A"),
    rpg_begin("B"),
    rpg_read("A", "1", Some("v0")),
    rpg_read("B", "2", Some("u0")),
    rpg_write("A", "2", "u1", Some("u0")),
    rpg_write("B", "1", "v1", Some("v0")),
    rpg_read("A", "1", Some("v1")),
    rpg_read("B", "2", Some("u1")),
  ]
  rpg_commit(body, "A")
  rpg_commit(body, "B")
  let h = rcl_history(body)
  let projection = project_relation_rows_v4(h).unwrap()
  assert_true(projection.is_projected())
  assert_true(
    projection.edges.any(e => {
      e.from == "A" && e.to == "B" && e.kind == ScopedWRItem
    }),
  )
  assert_true(
    projection.edges.any(e => {
      e.from == "B" && e.to == "A" && e.kind == ScopedWRItem
    }),
  )
  let report = rmp_report(h, models=[ElleReadCommitted], clients=[])
  assert_eq(
    mct_status(report, ElleReadCommitted),
    "refuted",
    msg=report.stringify(),
  )
}
