///|
fn mlp_model_report(
  facts : ModelFactsV4,
  models~ : Array[ElleModelV4] = elle_core_models_v4(),
) -> Json {
  model_classification_v4_json(
    classify_models_v4(
      facts,
      model_options_v4(models~, list_profile=ModelListPrefixStates).unwrap(),
    ),
  )
}

///|
fn mlp_history(body : Array[Json]) -> HistoryV4 {
  parse_history_v4(classification26_test_list(body).stringify()).unwrap()
}

///|
fn mlp_project(
  body : Array[Json],
  maximum~ : Int32 = 1000000,
) -> ListPrefixProjectionV4 {
  project_list_prefix_v4(mlp_history(body), max_checks=maximum).unwrap()
}

///|
fn mlp_multi() -> Array[Json] {
  let body = [
    leg_test_begin("A"),
    leg_test_read("A", []),
    leg_test_append("A", "a1"),
    leg_test_read("A", ["a1"]),
    leg_test_append("A", "a2"),
    leg_test_read("A", ["a1", "a2"]),
  ]
  leg_test_commit(body, "A")
  body
}

///|
test "list prefix projection 01 every same-key append and intermediate own read is retained" {
  let result = mlp_project(mlp_multi())
  assert_true(result.is_projected())
  let p = result.program.unwrap()
  assert_eq(p.transactions.length(), 1)
  assert_eq(p.transactions[0].ops.length(), 5)
  assert_eq(p.version_orders.at("x").length(), 2)
  assert_true(
    p.transactions[0].ops[1].version != p.transactions[0].ops[3].version,
  )
  assert_eq(p.transactions[0].ops[2].version, p.transactions[0].ops[1].version)
  assert_eq(p.transactions[0].ops[4].version, p.transactions[0].ops[3].version)
}

///|
test "list prefix projection 02 complete observed prefix proves two writer blocks" {
  let body = mlp_multi()
  body.push(leg_test_begin("B"))
  body.push(leg_test_read("B", ["a1", "a2"]))
  body.push(leg_test_append("B", "b"))
  body.push(leg_test_read("B", ["a1", "a2", "b"]))
  leg_test_commit(body, "B")
  let result = mlp_project(body)
  assert_true(result.is_projected(), msg=result.record.stringify())
  assert_eq(result.program.unwrap().version_orders.at("x").length(), 3)
}

///|
test "list prefix projection 03 external partial producer prefix is not a final scalar source" {
  let result = mlp_project(leg_test_external(["a1"]))
  assert_false(result.is_projected())
  assert_eq(
    v4_test_at(list_prefix_projection_v4_json(result), ["status"]),
    Json("unknown"),
  )
}

///|
test "list prefix projection 04 missing external producer prefix stays unknown" {
  assert_false(mlp_project(leg_test_external(["a2"])).is_projected())
}

///|
test "list prefix projection 05 interleaved transaction append blocks are not silently serialized" {
  let body = [
    leg_test_begin("A"),
    leg_test_append("A", "a1"),
    leg_test_append("A", "a2"),
  ]
  leg_test_commit(body, "A")
  body.push(leg_test_begin("B"))
  body.push(leg_test_append("B", "b"))
  leg_test_commit(body, "B")
  body.push(leg_test_begin("R"))
  body.push(leg_test_read("R", ["a1", "b", "a2"]))
  leg_test_commit(body, "R")
  assert_false(mlp_project(body).is_projected())
}

///|
test "list prefix projection 06 incomplete writer order is not chosen by transaction id" {
  let body = [leg_test_begin("Z"), leg_test_append("Z", "z")]
  leg_test_commit(body, "Z")
  body.push(leg_test_begin("A"))
  body.push(leg_test_append("A", "a"))
  leg_test_commit(body, "A")
  assert_false(mlp_project(body).is_projected())
}

///|
test "list prefix projection 07 rollback preserves earlier own observations and removes only effects" {
  let body = [
    leg_test_begin("A"),
    leg_test_append("A", "a1"),
    ({ "kind": "savepoint", "tx": "A", "name": "same", "instance": "s1" } : Json),
    leg_test_append("A", "a2"),
    leg_test_read("A", ["a1", "a2"]),
    ({ "kind": "rollback_to", "tx": "A", "instance": "s1" } : Json),
    leg_test_read("A", ["a1"]),
    leg_test_append("A", "a3"),
    leg_test_read("A", ["a1", "a3"]),
  ]
  leg_test_commit(body, "A")
  let result = mlp_project(body)
  assert_true(result.is_projected())
  let ops = result.program.unwrap().transactions[0].ops
  assert_eq(ops.length(), 6)
  assert_true(ops[1].revoked)
  assert_eq(ops[2].version, ops[1].version)
  assert_eq(ops[3].version, ops[0].version)
  assert_true(
    result.program.unwrap().version_orders.at("x")[1] == ops[4].version,
  )
}

///|
test "list prefix projection 08 revoked-only own read remains a delivered legal observation" {
  let body = [
    leg_test_begin("A"),
    ({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "s1" } : Json),
    leg_test_append("A", "a"),
    leg_test_read("A", ["a"]),
    ({ "kind": "rollback_to", "tx": "A", "instance": "s1" } : Json),
    leg_test_read("A", []),
  ]
  leg_test_commit(body, "A")
  let result = mlp_project(body)
  assert_true(result.is_projected())
  assert_eq(result.program.unwrap().transactions[0].ops.length(), 3)
  assert_eq(result.program.unwrap().version_orders.at("x").length(), 1)
}

///|
test "list prefix projection 09 zero and exact caller budgets remain distinct" {
  let body = mlp_multi()
  assert_false(mlp_project(body, maximum=0).is_projected())
  let result = mlp_project(body)
  let used = rcl_number(v4_test_at(result.record, ["execution", "checks"]))
  assert_true(mlp_project(body, maximum=used).is_projected())
  assert_false(mlp_project(body, maximum=used - 1).is_projected())
}

///|
test "list prefix projection 10 verify recomputes source mapping under independent limits" {
  let h = mlp_history(mlp_multi())
  let result = project_list_prefix_v4(h).unwrap()
  let record = list_prefix_projection_v4_json(result)
  assert_true(verify_list_prefix_projection_v4(h, record))
  assert_false(verify_list_prefix_projection_v4(h, record, max_checks=0))
  object_fields_unchecked_v3(record)["derivedProjection"] = Json::null()
  assert_false(verify_list_prefix_projection_v4(h, record))
  assert_true(result.is_projected())
}

///|
test "list prefix projection 11 unknown SQL and missing event windows cannot become a point program" {
  let raw = classification26_test_list(mlp_multi())
  let events = capture_source_array_v4(
    object_fields_unchecked_v3(raw).at("events"),
  )
  object_fields_unchecked_v3(events[3])["seq"] = Json(20)
  // Keep a valid increasing sequence while preserving the actual missing window.
  for i in 4..<events.length() {
    object_fields_unchecked_v3(events[i])["seq"] = Json(20 + i)
  }
  assert_false(
    project_list_prefix_v4(parse_history_v4(raw.stringify()).unwrap())
    .unwrap()
    .is_projected(),
  )
  let body = mlp_multi()
  body.insert(
    3,
    ({ "kind": "statement", "tx": "A", "sql": "ROLLBACK TO SAVEPOINT s" } : Json),
  )
  assert_false(mlp_project(body).is_projected())
}

///|
test "list prefix projection 12 duplicate values retain distinct prefix-state identities" {
  let result = mlp_project(mlp_multi())
  assert_true(result.is_projected())
  let states = v4_test_at(result.record, [
    "derivedProjection", "originalItemIdentityAndValueStates",
  ])
  assert_true(object_fields_unchecked_v3(states).length() >= 3)
  let before = history_v4_json(mlp_history(mlp_multi()))
  let exposed = list_prefix_projection_v4_json(result)
  object_fields_unchecked_v3(exposed)["observations"] = Json::null()
  assert_eq(history_v4_json(mlp_history(mlp_multi())), before)
  assert_true(
    v4_test_at(list_prefix_projection_v4_json(result), ["observations"]) !=
    Json::null(),
  )
}

///|
test "list prefix projection 13 provisional own prefix never supplies final block order" {
  let body = [leg_test_begin("A"), leg_test_append("A", "a")]
  leg_test_commit(body, "A")
  body.push(leg_test_begin("B"))
  body.push({ "kind": "savepoint", "tx": "B", "name": "s", "instance": "s1" })
  body.push(leg_test_append("B", "b"))
  body.push(leg_test_read("B", ["a", "b"]))
  body.push({ "kind": "rollback_to", "tx": "B", "instance": "s1" })
  body.push(leg_test_append("B", "c"))
  leg_test_commit(body, "B")
  assert_false(mlp_project(body).is_projected())
}

///|
test "list prefix projection 14 business value mismatch is never hidden by the item identity map" {
  let body = mlp_multi()
  body[3] = {
    "kind": "list_read",
    "tx": "A",
    "key": "x",
    "items": [{ "id": "a1", "value": "changed" }],
  }
  assert_false(mlp_project(body).is_projected())
}

///|
test "list prefix projection 15 duplicate delivered identity cannot be mapped" {
  let body = mlp_multi()
  body[3] = leg_test_read("A", ["a1", "a1"])
  assert_false(mlp_project(body).is_projected())
}

///|
test "list prefix projection 16 complete multi append programs close actual snapshot obligations" {
  let h = mlp_history(mlp_multi())
  let facts = model_facts_v4(
    h,
    clients=[{ id: "logical-A", transactions: ["A"], }],
    clients_complete=true,
  ).unwrap()
  let report = mlp_model_report(facts, models=[
    ElleReadUncommitted,
    ElleReadCommitted,
    ElleRepeatableRead,
    ElleSerializable,
    ElleSnapshotIsolation,
    ElleConsistentView,
  ])
  for
    model in [
      ElleReadUncommitted,
      ElleReadCommitted,
      ElleRepeatableRead,
      ElleSerializable,
      ElleSnapshotIsolation,
      ElleConsistentView,
    ] {
    assert_eq(mct_status(report, model), "checked-compatible")
  }
  assert_eq(
    v4_test_at(report, ["sourceProfile"]),
    Json("captured-list-prefix-state/v2"),
  )
}

///|
test "list prefix projection 17 list external reread may satisfy RC but not a prefix snapshot" {
  let body = [
    leg_test_begin("R"),
    leg_test_read("R", []),
    leg_test_begin("W"),
    leg_test_append("W", "a"),
  ]
  leg_test_commit(body, "W")
  body.push(leg_test_read("R", ["a"]))
  leg_test_commit(body, "R")
  let h = mlp_history(body)
  let result = project_list_prefix_v4(h).unwrap()
  assert_true(result.is_projected())
  assert_eq(result.int_rule.status, "unknown")
  let report = mlp_model_report(model_facts_v4(h).unwrap(), models=[
    ElleReadCommitted,
    ElleRepeatableRead,
    ElleSnapshotIsolation,
  ])
  assert_eq(mct_status(report, ElleReadCommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleRepeatableRead), "refuted")
  assert_eq(mct_status(report, ElleSnapshotIsolation), "refuted")
}

///|
test "list prefix projection 18 explicit list mapping identity and full evidence stay bound to source" {
  let h = mlp_history(mlp_multi())
  let facts = model_facts_v4(h).unwrap()
  let options = model_options_v4(
    models=[ElleSnapshotIsolation],
    list_profile=ModelListPrefixStates,
  ).unwrap()
  let report = model_classification_v4_json(classify_models_v4(facts, options))
  assert_eq(
    v4_test_at(report, ["semanticContract"]),
    Json("elle-4e359e5-captured-list-prefix-state-completion-models-2"),
  )
  assert_eq(
    v4_test_at(report, ["execution", "counterContract"]),
    Json(
      "captured-list-prefix-independent-source-and-per-rule-graph-counters-2",
    ),
  )
  assert_eq(
    v4_test_at(report, ["execution", "source", "projectionRecord", "status"]),
    Json("projected"),
  )
  assert_true(verify_models_v4(facts, report, options))
  v4_test_replace(
    report,
    ["execution", "source", "projectionRecord", "derivedProjection"],
    Json::null(),
  )
  assert_false(verify_models_v4(facts, report, options))
}

///|
fn mlp_revoked_cross_key_body(base_read~ : Bool = false) -> Array[Json] {
  let body = [
    leg_test_begin("W"),
    leg_test_append("W", "w"),
    leg_test_append("W", "y1", key="y"),
  ]
  leg_test_commit(body, "W")
  body.push(leg_test_begin("A"))
  body.push(leg_test_read("A", ["y1"], key="y"))
  if base_read {
    body.push(leg_test_read("A", []))
  }
  body.push({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "A-s1" })
  body.push(leg_test_append("A", "a"))
  body.push(leg_test_read("A", ["a"]))
  body.push({ "kind": "rollback_to", "tx": "A", "instance": "A-s1" })
  leg_test_commit(body, "A")
  body
}

///|
test "list prefix projection 19 revoked own append cannot hide an unproved snapshot base" {
  let h = mlp_history(mlp_revoked_cross_key_body())
  let facts = model_facts_v4(h).unwrap()
  let report = mlp_model_report(facts, models=[ElleSnapshotIsolation])
  assert_true(
    mct_status(report, ElleSnapshotIsolation) != "checked-compatible",
    msg=(
      {
        "case": "revoked-only-own-append-without-real-base-read",
        "input": h.source_document,
        "actualReport": report,
      } : Json).stringify(),
  )
  let projection = project_list_prefix_v4(h).unwrap()
  assert_true(projection.is_projected())
  assert_true(
    projection.edges.any(e => {
      e.from == "A" && e.to == "W" && e.kind == ScopedRWItem
    }),
  )
  assert_eq(mct_status(report, ElleSnapshotIsolation), "refuted")
}

///|
test "list prefix projection 20 a real base read retains the constraint instead of inventing one" {
  let h = mlp_history(mlp_revoked_cross_key_body(base_read=true))
  let result = project_list_prefix_v4(h).unwrap()
  assert_true(result.is_projected())
  let witnesses = capture_source_array_v4(
    v4_test_at(result.record, ["derivedProjection", "ownBaseWitnesses"]),
  )
  assert_true(
    witnesses.any(w => {
      v4_test_at(w, ["basis"]) == Json("actual-delivered-external-base-read")
    }),
  )
  assert_eq(
    mct_status(
      mlp_model_report(model_facts_v4(h).unwrap(), models=[
        ElleSnapshotIsolation,
      ]),
      ElleSnapshotIsolation,
    ),
    "refuted",
  )
}

///|
test "list prefix projection 21 absent competing writes allow a revoked temporary own prefix" {
  let body = [leg_test_begin("W"), leg_test_append("W", "y1", key="y")]
  leg_test_commit(body, "W")
  body.push(leg_test_begin("A"))
  body.push(leg_test_read("A", ["y1"], key="y"))
  body.push({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "A-s1" })
  body.push(leg_test_append("A", "a"))
  body.push(leg_test_read("A", ["a"]))
  body.push({ "kind": "rollback_to", "tx": "A", "instance": "A-s1" })
  leg_test_commit(body, "A")
  let h = mlp_history(body)
  assert_true(project_list_prefix_v4(h).unwrap().is_projected())
  assert_eq(
    mct_status(
      mlp_model_report(model_facts_v4(h).unwrap(), models=[
        ElleSnapshotIsolation,
      ]),
      ElleSnapshotIsolation,
    ),
    "checked-compatible",
  )
}

///|
test "list prefix projection 22 a complete installed own block proves its external base" {
  let body = [
    leg_test_begin("W"),
    leg_test_append("W", "w"),
    leg_test_append("W", "y1", key="y"),
  ]
  leg_test_commit(body, "W")
  body.push(leg_test_begin("A"))
  body.push(leg_test_read("A", ["y1"], key="y"))
  body.push(leg_test_append("A", "a"))
  body.push(leg_test_read("A", ["w", "a"]))
  leg_test_commit(body, "A")
  let h = mlp_history(body)
  let result = project_list_prefix_v4(h).unwrap()
  assert_true(result.is_projected())
  let witnesses = capture_source_array_v4(
    v4_test_at(result.record, ["derivedProjection", "ownBaseWitnesses"]),
  )
  assert_true(
    witnesses.any(w => {
      v4_test_at(w, ["basis"]) ==
      Json("complete-installed-writer-predecessor-prefix")
    }),
  )
  assert_eq(
    mct_status(
      mlp_model_report(model_facts_v4(h).unwrap(), models=[
        ElleSnapshotIsolation,
      ]),
      ElleSnapshotIsolation,
    ),
    "checked-compatible",
  )
}

///|
test "list prefix projection 23 default list model behavior keeps its existing pending scope" {
  let h = mlp_history(mlp_multi())
  let facts = model_facts_v4(h).unwrap()
  let options = model_options_v4(models=[ElleSnapshotIsolation]).unwrap()
  let report = model_classification_v4_json(classify_models_v4(facts, options))
  assert_eq(mct_status(report, ElleSnapshotIsolation), "unknown")
  assert_eq(
    object_fields_unchecked_v3(v4_test_at(report, ["options"])).get(
      "listProfile",
    ),
    None,
  )
  assert_true(verify_models_v4(facts, report, options))
}

///|
test "list prefix projection 24 model report cannot authorize its own prefix-state applicability" {
  let h = mlp_history(mlp_multi())
  let facts = model_facts_v4(h).unwrap()
  let report = mlp_model_report(facts, models=[ElleSnapshotIsolation])
  assert_eq(mct_status(report, ElleSnapshotIsolation), "checked-compatible")
  assert_false(
    verify_models_v4(
      facts,
      report,
      model_options_v4(models=[ElleSnapshotIsolation]).unwrap(),
    ),
  )
}

///|
test "list prefix projection 25 a delivered own prefix can prove a foreign base without inventing a read" {
  let body = [leg_test_begin("W"), leg_test_append("W", "w")]
  leg_test_commit(body, "W")
  body.push(leg_test_begin("A"))
  body.push({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "A-s" })
  body.push(leg_test_append("A", "a"))
  body.push(leg_test_read("A", ["w", "a"]))
  body.push({ "kind": "rollback_to", "tx": "A", "instance": "A-s" })
  leg_test_commit(body, "A")
  let h = mlp_history(body)
  let projection = project_list_prefix_v4(h).unwrap()
  assert_true(projection.is_projected())
  assert_true(
    projection.edges.any(e => {
      e.from == "W" && e.to == "A" && e.kind == ScopedWRItem
    }),
  )
  let report = mlp_model_report(model_facts_v4(h).unwrap(), models=[
    ElleSnapshotIsolation,
  ])
  assert_eq(mct_status(report, ElleSnapshotIsolation), "checked-compatible")
  assert_eq(
    v4_test_at(
      mct_rule(report, ElleSnapshotIsolation, "completion/Ext/data-only"),
      ["evidence", "originalProgramReplay", "status"],
    ),
    Json("checked-compatible"),
  )
  assert_eq(history_v4_json(h), h.source_document)
}

///|
test "list prefix projection 26 every fixed canonical model completes on one faithful original append program" {
  let h = mlp_history(mlp_multi())
  let facts = model_facts_v4(
    h,
    clients=[{ id: "logical-A", transactions: ["A"], }],
    clients_complete=true,
  ).unwrap()
  let options = model_options_v4(
    models=elle_core_models_v4(),
    list_profile=ModelListPrefixStates,
  ).unwrap()
  let report = model_classification_v4_json(classify_models_v4(facts, options))
  for model in elle_core_models_v4() {
    assert_eq(
      mct_status(report, model),
      "checked-compatible",
      msg=model_name_v4(model) + ": " + report.stringify(),
    )
  }
  assert_true(verify_models_v4(facts, report, options))
}

///|
test "list prefix projection 27 CV rank checks the external component of delivered own reads" {
  let h = mlp_history(mlp_multi())
  let facts = model_facts_v4(h).unwrap()
  let options = model_options_v4(
    models=[ElleConsistentView],
    list_profile=ModelListPrefixStates,
  ).unwrap()
  let source = model_source_applicability_v4(
    h,
    model_other_source_v4(h, options),
  )
  let orders = model_orders_v4(facts, source, options.max_source_checks)
  let i = model_graph_rule_v4(source, orders, "I", ScopedDataOnly, options)
  let single = model_graph_rule_v4(
    source,
    orders,
    "G-single",
    ScopedDataOnly,
    options,
  )
  let rank = model_cv_mapped_rank_v4(source, options, i, single)
  assert_eq(rank.status, "checked-compatible")
  let rows = capture_source_array_v4(v4_test_at(rank.evidence, ["readRanks"]))
  assert_eq(rows.length(), 3)
  assert_eq(
    rows
    .filter(r => {
      object_fields_unchecked_v3(r).get("readComponent") ==
      Some(Json("external-prefix-before-active-own-suffix"))
    })
    .length(),
    2,
  )
  assert_eq(
    v4_test_at(rank.evidence, ["execution", "counterContract"]),
    Json("mapped-list-prefix-rank-reference-checks-2"),
  )
}

///|
test "list prefix projection 28 an own immediate installed successor stops component RW" {
  let body = [
    leg_test_begin("A"),
    leg_test_begin("B"),
    leg_test_append("B", "yb", key="y"),
    leg_test_read("A", []),
    leg_test_append("A", "a"),
    leg_test_read("A", ["a"]),
    leg_test_read("A", ["yb"], key="y"),
    leg_test_append("B", "b"),
    leg_test_read("B", ["a", "b"]),
  ]
  leg_test_commit(body, "A")
  leg_test_commit(body, "B")
  let p = project_list_prefix_v4(mlp_history(body)).unwrap()
  assert_true(p.is_projected(), msg=p.record.stringify())
  assert_true(
    p.edges.any(e => e.from == "A" && e.to == "B" && e.kind == ScopedWWItem),
  )
  assert_true(
    p.edges.any(e => e.from == "B" && e.to == "A" && e.kind == ScopedWRItem),
  )
  assert_false(
    p.edges.any(e => e.from == "A" && e.to == "B" && e.kind == ScopedRWItem),
  )
}

///|
test "list prefix projection 29 original program certificate replay respects exact independent budget" {
  let h = mlp_history(mlp_multi())
  let parsed = match h.payload {
    ListSnapshot(p) => p
    _ => abort("expected list")
  }
  let visibility : Array[Json] = [
    { "transaction": "A", "visiblePrefixLength": 0, "visibleTransactions": [] },
  ]
  let full = model_list_certificate_replay_v4(
    parsed,
    ["A"],
    visibility,
    1000000,
  )
  assert_eq(full.status, "checked-compatible")
  let checks = capture_source_seq_v4(
    v4_test_at(full.evidence, ["execution", "checks"]),
  ).to_int()
  assert_true(checks > 0)
  assert_eq(
    model_list_certificate_replay_v4(parsed, ["A"], visibility, checks).status,
    "checked-compatible",
  )
  let short = model_list_certificate_replay_v4(
    parsed,
    ["A"],
    visibility,
    checks - 1,
  )
  assert_eq(short.status, "unknown")
  assert_true(
    capture_source_seq_v4(v4_test_at(short.evidence, ["execution", "checks"])) <=
    (checks - 1).to_int64(),
  )
  let zero = model_list_certificate_replay_v4(parsed, ["A"], visibility, 0)
  assert_eq(zero.status, "unknown")
  assert_eq(v4_test_at(zero.evidence, ["execution", "checks"]), Json(0))
}
