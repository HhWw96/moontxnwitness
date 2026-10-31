///|
fn mct_facts(
  history : History,
  clients~ : Array[ModelClientV4] = [],
  clients_complete~ : Bool = false,
) -> ModelFactsV4 {
  model_facts_v4(
    register_history_v4(history).unwrap(),
    clients~,
    clients_complete~,
  ).unwrap()
}

///|
fn mct_report(
  facts : ModelFactsV4,
  models~ : Array[ElleModelV4] = elle_core_models_v4(),
  source~ : Int32 = 1000000,
  states~ : Int32 = 100000,
  edge_checks~ : Int32 = 1000000,
  relation~ : ModelRelationProfileV4 = ModelRelationPoint,
) -> Json {
  model_classification_v4_json(
    classify_models_v4(
      facts,
      model_options_v4(
        models~,
        max_source_checks=source,
        max_states=states,
        max_edge_checks=edge_checks,
        relation_profile=relation,
      ).unwrap(),
    ),
  )
}

///|
fn mct_model(report : Json, model : ElleModelV4) -> Json {
  capture_source_array_v4(object_fields_unchecked_v3(report).at("models")).filter(raw => {
      object_fields_unchecked_v3(raw).at("model") == Json(model_name_v4(model))
    },
  )[0]
}

///|
fn mct_status(report : Json, model : ElleModelV4) -> String {
  capture_source_string_v4(
    object_fields_unchecked_v3(mct_model(report, model)).at("status"),
  )
}

///|
fn mct_rule(report : Json, model : ElleModelV4, id : String) -> Json {
  capture_source_array_v4(
    object_fields_unchecked_v3(mct_model(report, model)).at("rules"),
  ).filter(raw => object_fields_unchecked_v3(raw).at("rule") == Json(id))[0]
}

///|
fn mct_single() -> History {
  hist(
    [tx("A", [read_op("x", "x0"), write_op("x", "x1"), read_op("x", "x1")])],
    orders={ "x": ["x0", "x1"], "y": ["y0"] },
  )
}

///|
fn mct_ww_cycle() -> History {
  hist(
    [
      tx("A", [write_op("x", "x1"), write_op("y", "y1")]),
      tx("B", [write_op("x", "x2"), write_op("y", "y2")]),
    ],
    orders={ "x": ["x0", "x1", "x2"], "y": ["y0", "y2", "y1"] },
  )
}

///|
fn mct_unknown() -> History {
  hist([tx("A", [write_op("x", "x1")]), tx("B", [write_op("x", "x2")])])
}

///|
test "model composition 01a ElleReadUncommitted wellformed history has real completed graph work" {
  let report = mct_report(mct_facts(mct_single()), models=[ElleReadUncommitted])
  assert_eq(mct_status(report, ElleReadUncommitted), "checked-compatible")
  let rule = mct_rule(
    report,
    ElleReadUncommitted,
    model_graph_key_v4(
      model_projection_v4(ElleReadUncommitted),
      model_context_v4(ElleReadUncommitted),
    ),
  )
  assert_eq(
    object_fields_unchecked_v3(rule).at("status"),
    Json("checked-compatible"),
  )
  assert_eq(
    object_fields_unchecked_v3(report).at("status"),
    Json("checked-compatible"),
  )
}

///|
test "model composition 01b ElleReadUncommitted reliable WW refutation beats unrelated pending" {
  let report = mct_report(mct_facts(mct_ww_cycle()), models=[
    ElleReadUncommitted,
  ])
  assert_eq(mct_status(report, ElleReadUncommitted), "refuted")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleReadUncommitted, "graph/W/data-only"),
    ).at("status"),
    Json("refuted"),
  )
}

///|
test "model composition 01c ElleReadUncommitted missing installed order cannot pass" {
  let report = mct_report(mct_facts(mct_unknown()), models=[ElleReadUncommitted])
  assert_eq(mct_status(report, ElleReadUncommitted), "unknown")
}

///|
test "model composition 01d ElleReadUncommitted independent verification rejects tampered model" {
  let facts = mct_facts(mct_ww_cycle())
  let options = model_options_v4(models=[ElleReadUncommitted]).unwrap()
  let supplied = model_classification_v4_json(
    classify_models_v4(facts, options),
  )
  assert_true(verify_models_v4(facts, supplied, options))
  let row = capture_source_array_v4(
      object_fields_unchecked_v3(supplied).at("models"),
    )[0]
  object_fields_unchecked_v3(row)["canonicalModel"] = Json("changed")
  assert_true(!verify_models_v4(facts, supplied, options))
}

///|
test "model composition 02a ElleReadCommitted wellformed history has real completed graph work" {
  let report = mct_report(mct_facts(mct_single()), models=[ElleReadCommitted])
  assert_eq(mct_status(report, ElleReadCommitted), "checked-compatible")
  let rule = mct_rule(
    report,
    ElleReadCommitted,
    model_graph_key_v4(
      model_projection_v4(ElleReadCommitted),
      model_context_v4(ElleReadCommitted),
    ),
  )
  assert_eq(
    object_fields_unchecked_v3(rule).at("status"),
    Json("checked-compatible"),
  )
  assert_eq(
    object_fields_unchecked_v3(report).at("status"),
    Json("checked-compatible"),
  )
}

///|
test "model composition 02b ElleReadCommitted reliable WW refutation beats unrelated pending" {
  let report = mct_report(mct_facts(mct_ww_cycle()), models=[ElleReadCommitted])
  assert_eq(mct_status(report, ElleReadCommitted), "refuted")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleReadCommitted, "graph/W/data-only"),
    ).at("status"),
    Json("refuted"),
  )
}

///|
test "model composition 02c ElleReadCommitted missing installed order cannot pass" {
  let report = mct_report(mct_facts(mct_unknown()), models=[ElleReadCommitted])
  assert_eq(mct_status(report, ElleReadCommitted), "unknown")
}

///|
test "model composition 02d ElleReadCommitted independent verification rejects tampered model" {
  let facts = mct_facts(mct_ww_cycle())
  let options = model_options_v4(models=[ElleReadCommitted]).unwrap()
  let supplied = model_classification_v4_json(
    classify_models_v4(facts, options),
  )
  assert_true(verify_models_v4(facts, supplied, options))
  let row = capture_source_array_v4(
      object_fields_unchecked_v3(supplied).at("models"),
    )[0]
  object_fields_unchecked_v3(row)["canonicalModel"] = Json("changed")
  assert_true(!verify_models_v4(facts, supplied, options))
}

///|
test "model composition 03a ElleRepeatableRead wellformed history has real completed graph work" {
  let report = mct_report(mct_facts(mct_single()), models=[ElleRepeatableRead])
  assert_eq(mct_status(report, ElleRepeatableRead), "checked-compatible")
  let rule = mct_rule(
    report,
    ElleRepeatableRead,
    model_graph_key_v4(
      model_projection_v4(ElleRepeatableRead),
      model_context_v4(ElleRepeatableRead),
    ),
  )
  assert_eq(
    object_fields_unchecked_v3(rule).at("status"),
    Json("checked-compatible"),
  )
  assert_true(
    capture_source_array_v4(
      object_fields_unchecked_v3(mct_model(report, ElleRepeatableRead)).at(
        "pendingRules",
      ),
    ).is_empty(),
  )
}

///|
test "model composition 03b ElleRepeatableRead reliable WW refutation beats unrelated pending" {
  let report = mct_report(mct_facts(mct_ww_cycle()), models=[ElleRepeatableRead])
  assert_eq(mct_status(report, ElleRepeatableRead), "refuted")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleRepeatableRead, "graph/W/data-only"),
    ).at("status"),
    Json("refuted"),
  )
}

///|
test "model composition 03c ElleRepeatableRead missing installed order cannot pass" {
  let report = mct_report(mct_facts(mct_unknown()), models=[ElleRepeatableRead])
  assert_eq(mct_status(report, ElleRepeatableRead), "unknown")
}

///|
test "model composition 03d ElleRepeatableRead independent verification rejects tampered model" {
  let facts = mct_facts(mct_ww_cycle())
  let options = model_options_v4(models=[ElleRepeatableRead]).unwrap()
  let supplied = model_classification_v4_json(
    classify_models_v4(facts, options),
  )
  assert_true(verify_models_v4(facts, supplied, options))
  let row = capture_source_array_v4(
      object_fields_unchecked_v3(supplied).at("models"),
    )[0]
  object_fields_unchecked_v3(row)["canonicalModel"] = Json("changed")
  assert_true(!verify_models_v4(facts, supplied, options))
}

///|
test "model composition 04a ElleSerializable wellformed history has real completed graph work" {
  let report = mct_report(mct_facts(mct_single()), models=[ElleSerializable])
  assert_eq(mct_status(report, ElleSerializable), "checked-compatible")
  let rule = mct_rule(
    report,
    ElleSerializable,
    model_graph_key_v4(
      model_projection_v4(ElleSerializable),
      model_context_v4(ElleSerializable),
    ),
  )
  assert_eq(
    object_fields_unchecked_v3(rule).at("status"),
    Json("checked-compatible"),
  )
  assert_true(
    capture_source_array_v4(
      object_fields_unchecked_v3(mct_model(report, ElleSerializable)).at(
        "pendingRules",
      ),
    ).is_empty(),
  )
}

///|
test "model composition 04b ElleSerializable reliable WW refutation beats unrelated pending" {
  let report = mct_report(mct_facts(mct_ww_cycle()), models=[ElleSerializable])
  assert_eq(mct_status(report, ElleSerializable), "refuted")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleSerializable, "graph/W/data-only"),
    ).at("status"),
    Json("refuted"),
  )
}

///|
test "model composition 04c ElleSerializable missing installed order cannot pass" {
  let report = mct_report(mct_facts(mct_unknown()), models=[ElleSerializable])
  assert_eq(mct_status(report, ElleSerializable), "unknown")
}

///|
test "model composition 04d ElleSerializable independent verification rejects tampered model" {
  let facts = mct_facts(mct_ww_cycle())
  let options = model_options_v4(models=[ElleSerializable]).unwrap()
  let supplied = model_classification_v4_json(
    classify_models_v4(facts, options),
  )
  assert_true(verify_models_v4(facts, supplied, options))
  let row = capture_source_array_v4(
      object_fields_unchecked_v3(supplied).at("models"),
    )[0]
  object_fields_unchecked_v3(row)["canonicalModel"] = Json("changed")
  assert_true(!verify_models_v4(facts, supplied, options))
}

///|
test "model composition 05a ElleStrictSerializable wellformed history has real completed graph work" {
  let report = mct_report(mct_facts(mct_single()), models=[
    ElleStrictSerializable,
  ])
  assert_eq(mct_status(report, ElleStrictSerializable), "checked-compatible")
  let rule = mct_rule(
    report,
    ElleStrictSerializable,
    model_graph_key_v4(
      model_projection_v4(ElleStrictSerializable),
      model_context_v4(ElleStrictSerializable),
    ),
  )
  assert_eq(
    object_fields_unchecked_v3(rule).at("status"),
    Json("checked-compatible"),
  )
  assert_true(
    capture_source_array_v4(
      object_fields_unchecked_v3(mct_model(report, ElleStrictSerializable)).at(
        "pendingRules",
      ),
    ).is_empty(),
  )
}

///|
test "model composition 05b ElleStrictSerializable reliable WW refutation beats unrelated pending" {
  let report = mct_report(mct_facts(mct_ww_cycle()), models=[
    ElleStrictSerializable,
  ])
  assert_eq(mct_status(report, ElleStrictSerializable), "refuted")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleStrictSerializable, "graph/W/data-only"),
    ).at("status"),
    Json("refuted"),
  )
}

///|
test "model composition 05c ElleStrictSerializable missing installed order cannot pass" {
  let report = mct_report(mct_facts(mct_unknown()), models=[
    ElleStrictSerializable,
  ])
  assert_eq(mct_status(report, ElleStrictSerializable), "unknown")
}

///|
test "model composition 05d ElleStrictSerializable independent verification rejects tampered model" {
  let facts = mct_facts(mct_ww_cycle())
  let options = model_options_v4(models=[ElleStrictSerializable]).unwrap()
  let supplied = model_classification_v4_json(
    classify_models_v4(facts, options),
  )
  assert_true(verify_models_v4(facts, supplied, options))
  let row = capture_source_array_v4(
      object_fields_unchecked_v3(supplied).at("models"),
    )[0]
  object_fields_unchecked_v3(row)["canonicalModel"] = Json("changed")
  assert_true(!verify_models_v4(facts, supplied, options))
}

///|
test "model composition 06a ElleSnapshotIsolation wellformed history has real completed graph work" {
  let report = mct_report(mct_facts(mct_single()), models=[
    ElleSnapshotIsolation,
  ])
  assert_eq(mct_status(report, ElleSnapshotIsolation), "checked-compatible")
  let rule = mct_rule(
    report,
    ElleSnapshotIsolation,
    model_graph_key_v4(
      model_projection_v4(ElleSnapshotIsolation),
      model_context_v4(ElleSnapshotIsolation),
    ),
  )
  assert_eq(
    object_fields_unchecked_v3(rule).at("status"),
    Json("checked-compatible"),
  )
  assert_true(
    capture_source_array_v4(
      object_fields_unchecked_v3(mct_model(report, ElleSnapshotIsolation)).at(
        "pendingRules",
      ),
    ).is_empty(),
  )
}

///|
test "model composition 06b ElleSnapshotIsolation reliable WW refutation beats unrelated pending" {
  let report = mct_report(mct_facts(mct_ww_cycle()), models=[
    ElleSnapshotIsolation,
  ])
  assert_eq(mct_status(report, ElleSnapshotIsolation), "refuted")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleSnapshotIsolation, "graph/W/data-only"),
    ).at("status"),
    Json("refuted"),
  )
}

///|
test "model composition 06c ElleSnapshotIsolation missing installed order cannot pass" {
  let report = mct_report(mct_facts(mct_unknown()), models=[
    ElleSnapshotIsolation,
  ])
  assert_eq(mct_status(report, ElleSnapshotIsolation), "unknown")
}

///|
test "model composition 06d ElleSnapshotIsolation independent verification rejects tampered model" {
  let facts = mct_facts(mct_ww_cycle())
  let options = model_options_v4(models=[ElleSnapshotIsolation]).unwrap()
  let supplied = model_classification_v4_json(
    classify_models_v4(facts, options),
  )
  assert_true(verify_models_v4(facts, supplied, options))
  let row = capture_source_array_v4(
      object_fields_unchecked_v3(supplied).at("models"),
    )[0]
  object_fields_unchecked_v3(row)["canonicalModel"] = Json("changed")
  assert_true(!verify_models_v4(facts, supplied, options))
}

///|
test "model composition 07a ElleConsistentView wellformed history has real completed graph work" {
  let report = mct_report(mct_facts(mct_single()), models=[ElleConsistentView])
  assert_eq(mct_status(report, ElleConsistentView), "checked-compatible")
  let rule = mct_rule(
    report,
    ElleConsistentView,
    model_graph_key_v4(
      model_projection_v4(ElleConsistentView),
      model_context_v4(ElleConsistentView),
    ),
  )
  assert_eq(
    object_fields_unchecked_v3(rule).at("status"),
    Json("checked-compatible"),
  )
  assert_true(
    capture_source_array_v4(
      object_fields_unchecked_v3(mct_model(report, ElleConsistentView)).at(
        "pendingRules",
      ),
    ).is_empty(),
  )
}

///|
test "model composition 07b ElleConsistentView reliable WW refutation beats unrelated pending" {
  let report = mct_report(mct_facts(mct_ww_cycle()), models=[ElleConsistentView])
  assert_eq(mct_status(report, ElleConsistentView), "refuted")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleConsistentView, "graph/W/data-only"),
    ).at("status"),
    Json("refuted"),
  )
}

///|
test "model composition 07c ElleConsistentView missing installed order cannot pass" {
  let report = mct_report(mct_facts(mct_unknown()), models=[ElleConsistentView])
  assert_eq(mct_status(report, ElleConsistentView), "unknown")
}

///|
test "model composition 07d ElleConsistentView independent verification rejects tampered model" {
  let facts = mct_facts(mct_ww_cycle())
  let options = model_options_v4(models=[ElleConsistentView]).unwrap()
  let supplied = model_classification_v4_json(
    classify_models_v4(facts, options),
  )
  assert_true(verify_models_v4(facts, supplied, options))
  let row = capture_source_array_v4(
      object_fields_unchecked_v3(supplied).at("models"),
    )[0]
  object_fields_unchecked_v3(row)["canonicalModel"] = Json("changed")
  assert_true(!verify_models_v4(facts, supplied, options))
}

///|
test "model composition 08a ElleSessionReadUncommitted wellformed history has real completed graph work" {
  let report = mct_report(mct_facts(mct_single()), models=[
    ElleSessionReadUncommitted,
  ])
  assert_eq(
    mct_status(report, ElleSessionReadUncommitted),
    "checked-compatible",
  )
  let rule = mct_rule(
    report,
    ElleSessionReadUncommitted,
    model_graph_key_v4(
      model_projection_v4(ElleSessionReadUncommitted),
      model_context_v4(ElleSessionReadUncommitted),
    ),
  )
  assert_eq(
    object_fields_unchecked_v3(rule).at("status"),
    Json("checked-compatible"),
  )
  assert_eq(
    object_fields_unchecked_v3(report).at("status"),
    Json("checked-compatible"),
  )
}

///|
test "model composition 08b ElleSessionReadUncommitted reliable WW refutation beats unrelated pending" {
  let report = mct_report(mct_facts(mct_ww_cycle()), models=[
    ElleSessionReadUncommitted,
  ])
  assert_eq(mct_status(report, ElleSessionReadUncommitted), "refuted")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleSessionReadUncommitted, "graph/W/data-only"),
    ).at("status"),
    Json("refuted"),
  )
}

///|
test "model composition 08c ElleSessionReadUncommitted missing installed order cannot pass" {
  let report = mct_report(mct_facts(mct_unknown()), models=[
    ElleSessionReadUncommitted,
  ])
  assert_eq(mct_status(report, ElleSessionReadUncommitted), "unknown")
}

///|
test "model composition 08d ElleSessionReadUncommitted independent verification rejects tampered model" {
  let facts = mct_facts(mct_ww_cycle())
  let options = model_options_v4(models=[ElleSessionReadUncommitted]).unwrap()
  let supplied = model_classification_v4_json(
    classify_models_v4(facts, options),
  )
  assert_true(verify_models_v4(facts, supplied, options))
  let row = capture_source_array_v4(
      object_fields_unchecked_v3(supplied).at("models"),
    )[0]
  object_fields_unchecked_v3(row)["canonicalModel"] = Json("changed")
  assert_true(!verify_models_v4(facts, supplied, options))
}

///|
test "model composition 09a ElleStrongReadUncommitted wellformed history has real completed graph work" {
  let report = mct_report(mct_facts(mct_single()), models=[
    ElleStrongReadUncommitted,
  ])
  assert_eq(mct_status(report, ElleStrongReadUncommitted), "checked-compatible")
  let rule = mct_rule(
    report,
    ElleStrongReadUncommitted,
    model_graph_key_v4(
      model_projection_v4(ElleStrongReadUncommitted),
      model_context_v4(ElleStrongReadUncommitted),
    ),
  )
  assert_eq(
    object_fields_unchecked_v3(rule).at("status"),
    Json("checked-compatible"),
  )
  assert_eq(
    object_fields_unchecked_v3(report).at("status"),
    Json("checked-compatible"),
  )
}

///|
test "model composition 09b ElleStrongReadUncommitted reliable WW refutation beats unrelated pending" {
  let report = mct_report(mct_facts(mct_ww_cycle()), models=[
    ElleStrongReadUncommitted,
  ])
  assert_eq(mct_status(report, ElleStrongReadUncommitted), "refuted")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleStrongReadUncommitted, "graph/W/data-only"),
    ).at("status"),
    Json("refuted"),
  )
}

///|
test "model composition 09c ElleStrongReadUncommitted missing installed order cannot pass" {
  let report = mct_report(mct_facts(mct_unknown()), models=[
    ElleStrongReadUncommitted,
  ])
  assert_eq(mct_status(report, ElleStrongReadUncommitted), "unknown")
}

///|
test "model composition 09d ElleStrongReadUncommitted independent verification rejects tampered model" {
  let facts = mct_facts(mct_ww_cycle())
  let options = model_options_v4(models=[ElleStrongReadUncommitted]).unwrap()
  let supplied = model_classification_v4_json(
    classify_models_v4(facts, options),
  )
  assert_true(verify_models_v4(facts, supplied, options))
  let row = capture_source_array_v4(
      object_fields_unchecked_v3(supplied).at("models"),
    )[0]
  object_fields_unchecked_v3(row)["canonicalModel"] = Json("changed")
  assert_true(!verify_models_v4(facts, supplied, options))
}

///|
test "model composition 10a ElleSessionReadCommitted wellformed history has real completed graph work" {
  let report = mct_report(mct_facts(mct_single()), models=[
    ElleSessionReadCommitted,
  ])
  assert_eq(mct_status(report, ElleSessionReadCommitted), "checked-compatible")
  let rule = mct_rule(
    report,
    ElleSessionReadCommitted,
    model_graph_key_v4(
      model_projection_v4(ElleSessionReadCommitted),
      model_context_v4(ElleSessionReadCommitted),
    ),
  )
  assert_eq(
    object_fields_unchecked_v3(rule).at("status"),
    Json("checked-compatible"),
  )
  assert_eq(
    object_fields_unchecked_v3(report).at("status"),
    Json("checked-compatible"),
  )
}

///|
test "model composition 10b ElleSessionReadCommitted reliable WW refutation beats unrelated pending" {
  let report = mct_report(mct_facts(mct_ww_cycle()), models=[
    ElleSessionReadCommitted,
  ])
  assert_eq(mct_status(report, ElleSessionReadCommitted), "refuted")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleSessionReadCommitted, "graph/W/data-only"),
    ).at("status"),
    Json("refuted"),
  )
}

///|
test "model composition 10c ElleSessionReadCommitted missing installed order cannot pass" {
  let report = mct_report(mct_facts(mct_unknown()), models=[
    ElleSessionReadCommitted,
  ])
  assert_eq(mct_status(report, ElleSessionReadCommitted), "unknown")
}

///|
test "model composition 10d ElleSessionReadCommitted independent verification rejects tampered model" {
  let facts = mct_facts(mct_ww_cycle())
  let options = model_options_v4(models=[ElleSessionReadCommitted]).unwrap()
  let supplied = model_classification_v4_json(
    classify_models_v4(facts, options),
  )
  assert_true(verify_models_v4(facts, supplied, options))
  let row = capture_source_array_v4(
      object_fields_unchecked_v3(supplied).at("models"),
    )[0]
  object_fields_unchecked_v3(row)["canonicalModel"] = Json("changed")
  assert_true(!verify_models_v4(facts, supplied, options))
}

///|
test "model composition 11a ElleStrongReadCommitted wellformed history has real completed graph work" {
  let report = mct_report(mct_facts(mct_single()), models=[
    ElleStrongReadCommitted,
  ])
  assert_eq(mct_status(report, ElleStrongReadCommitted), "checked-compatible")
  let rule = mct_rule(
    report,
    ElleStrongReadCommitted,
    model_graph_key_v4(
      model_projection_v4(ElleStrongReadCommitted),
      model_context_v4(ElleStrongReadCommitted),
    ),
  )
  assert_eq(
    object_fields_unchecked_v3(rule).at("status"),
    Json("checked-compatible"),
  )
  assert_eq(
    object_fields_unchecked_v3(report).at("status"),
    Json("checked-compatible"),
  )
}

///|
test "model composition 11b ElleStrongReadCommitted reliable WW refutation beats unrelated pending" {
  let report = mct_report(mct_facts(mct_ww_cycle()), models=[
    ElleStrongReadCommitted,
  ])
  assert_eq(mct_status(report, ElleStrongReadCommitted), "refuted")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleStrongReadCommitted, "graph/W/data-only"),
    ).at("status"),
    Json("refuted"),
  )
}

///|
test "model composition 11c ElleStrongReadCommitted missing installed order cannot pass" {
  let report = mct_report(mct_facts(mct_unknown()), models=[
    ElleStrongReadCommitted,
  ])
  assert_eq(mct_status(report, ElleStrongReadCommitted), "unknown")
}

///|
test "model composition 11d ElleStrongReadCommitted independent verification rejects tampered model" {
  let facts = mct_facts(mct_ww_cycle())
  let options = model_options_v4(models=[ElleStrongReadCommitted]).unwrap()
  let supplied = model_classification_v4_json(
    classify_models_v4(facts, options),
  )
  assert_true(verify_models_v4(facts, supplied, options))
  let row = capture_source_array_v4(
      object_fields_unchecked_v3(supplied).at("models"),
    )[0]
  object_fields_unchecked_v3(row)["canonicalModel"] = Json("changed")
  assert_true(!verify_models_v4(facts, supplied, options))
}

///|
test "model composition 12a ElleSessionSerializable wellformed history has real completed graph work" {
  let report = mct_report(mct_facts(mct_single()), models=[
    ElleSessionSerializable,
  ])
  assert_eq(mct_status(report, ElleSessionSerializable), "checked-compatible")
  let rule = mct_rule(
    report,
    ElleSessionSerializable,
    model_graph_key_v4(
      model_projection_v4(ElleSessionSerializable),
      model_context_v4(ElleSessionSerializable),
    ),
  )
  assert_eq(
    object_fields_unchecked_v3(rule).at("status"),
    Json("checked-compatible"),
  )
  assert_true(
    capture_source_array_v4(
      object_fields_unchecked_v3(mct_model(report, ElleSessionSerializable)).at(
        "pendingRules",
      ),
    ).is_empty(),
  )
}

///|
test "model composition 12b ElleSessionSerializable reliable WW refutation beats unrelated pending" {
  let report = mct_report(mct_facts(mct_ww_cycle()), models=[
    ElleSessionSerializable,
  ])
  assert_eq(mct_status(report, ElleSessionSerializable), "refuted")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleSessionSerializable, "graph/W/data-only"),
    ).at("status"),
    Json("refuted"),
  )
}

///|
test "model composition 12c ElleSessionSerializable missing installed order cannot pass" {
  let report = mct_report(mct_facts(mct_unknown()), models=[
    ElleSessionSerializable,
  ])
  assert_eq(mct_status(report, ElleSessionSerializable), "unknown")
}

///|
test "model composition 12d ElleSessionSerializable independent verification rejects tampered model" {
  let facts = mct_facts(mct_ww_cycle())
  let options = model_options_v4(models=[ElleSessionSerializable]).unwrap()
  let supplied = model_classification_v4_json(
    classify_models_v4(facts, options),
  )
  assert_true(verify_models_v4(facts, supplied, options))
  let row = capture_source_array_v4(
      object_fields_unchecked_v3(supplied).at("models"),
    )[0]
  object_fields_unchecked_v3(row)["canonicalModel"] = Json("changed")
  assert_true(!verify_models_v4(facts, supplied, options))
}

///|
test "model composition 13a ElleSessionSnapshotIsolation wellformed history has real completed graph work" {
  let report = mct_report(mct_facts(mct_single()), models=[
    ElleSessionSnapshotIsolation,
  ])
  assert_eq(
    mct_status(report, ElleSessionSnapshotIsolation),
    "checked-compatible",
  )
  let rule = mct_rule(
    report,
    ElleSessionSnapshotIsolation,
    model_graph_key_v4(
      model_projection_v4(ElleSessionSnapshotIsolation),
      model_context_v4(ElleSessionSnapshotIsolation),
    ),
  )
  assert_eq(
    object_fields_unchecked_v3(rule).at("status"),
    Json("checked-compatible"),
  )
  assert_true(
    capture_source_array_v4(
      object_fields_unchecked_v3(
        mct_model(report, ElleSessionSnapshotIsolation),
      ).at("pendingRules"),
    ).is_empty(),
  )
}

///|
test "model composition 13b ElleSessionSnapshotIsolation reliable WW refutation beats unrelated pending" {
  let report = mct_report(mct_facts(mct_ww_cycle()), models=[
    ElleSessionSnapshotIsolation,
  ])
  assert_eq(mct_status(report, ElleSessionSnapshotIsolation), "refuted")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleSessionSnapshotIsolation, "graph/W/data-only"),
    ).at("status"),
    Json("refuted"),
  )
}

///|
test "model composition 13c ElleSessionSnapshotIsolation missing installed order cannot pass" {
  let report = mct_report(mct_facts(mct_unknown()), models=[
    ElleSessionSnapshotIsolation,
  ])
  assert_eq(mct_status(report, ElleSessionSnapshotIsolation), "unknown")
}

///|
test "model composition 13d ElleSessionSnapshotIsolation independent verification rejects tampered model" {
  let facts = mct_facts(mct_ww_cycle())
  let options = model_options_v4(models=[ElleSessionSnapshotIsolation]).unwrap()
  let supplied = model_classification_v4_json(
    classify_models_v4(facts, options),
  )
  assert_true(verify_models_v4(facts, supplied, options))
  let row = capture_source_array_v4(
      object_fields_unchecked_v3(supplied).at("models"),
    )[0]
  object_fields_unchecked_v3(row)["canonicalModel"] = Json("changed")
  assert_true(!verify_models_v4(facts, supplied, options))
}

///|
test "model composition 14a ElleStrongSnapshotIsolation wellformed history has real completed graph work" {
  let report = mct_report(mct_facts(mct_single()), models=[
    ElleStrongSnapshotIsolation,
  ])
  assert_eq(
    mct_status(report, ElleStrongSnapshotIsolation),
    "checked-compatible",
  )
  let rule = mct_rule(
    report,
    ElleStrongSnapshotIsolation,
    model_graph_key_v4(
      model_projection_v4(ElleStrongSnapshotIsolation),
      model_context_v4(ElleStrongSnapshotIsolation),
    ),
  )
  assert_eq(
    object_fields_unchecked_v3(rule).at("status"),
    Json("checked-compatible"),
  )
  assert_true(
    capture_source_array_v4(
      object_fields_unchecked_v3(mct_model(report, ElleStrongSnapshotIsolation)).at(
        "pendingRules",
      ),
    ).is_empty(),
  )
}

///|
test "model composition 14b ElleStrongSnapshotIsolation reliable WW refutation beats unrelated pending" {
  let report = mct_report(mct_facts(mct_ww_cycle()), models=[
    ElleStrongSnapshotIsolation,
  ])
  assert_eq(mct_status(report, ElleStrongSnapshotIsolation), "refuted")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleStrongSnapshotIsolation, "graph/W/data-only"),
    ).at("status"),
    Json("refuted"),
  )
}

///|
test "model composition 14c ElleStrongSnapshotIsolation missing installed order cannot pass" {
  let report = mct_report(mct_facts(mct_unknown()), models=[
    ElleStrongSnapshotIsolation,
  ])
  assert_eq(mct_status(report, ElleStrongSnapshotIsolation), "unknown")
}

///|
test "model composition 14d ElleStrongSnapshotIsolation independent verification rejects tampered model" {
  let facts = mct_facts(mct_ww_cycle())
  let options = model_options_v4(models=[ElleStrongSnapshotIsolation]).unwrap()
  let supplied = model_classification_v4_json(
    classify_models_v4(facts, options),
  )
  assert_true(verify_models_v4(facts, supplied, options))
  let row = capture_source_array_v4(
      object_fields_unchecked_v3(supplied).at("models"),
    )[0]
  object_fields_unchecked_v3(row)["canonicalModel"] = Json("changed")
  assert_true(!verify_models_v4(facts, supplied, options))
}

///|
test "model composition 15 RU permits known aborted reads while RC refutes G1a" {
  let a : Transaction = {
    id: "A",
    status: Aborted,
    ops: [write_op("x", "a")],
    start: None,
    end: None,
  }
  let report = mct_report(mct_facts(hist([a, tx("B", [read_op("x", "a")])])), models=[
    ElleReadUncommitted,
    ElleReadCommitted,
  ])
  assert_eq(mct_status(report, ElleReadUncommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleReadCommitted), "refuted")
  assert_eq(v4_test_at(report, ["sourceCoverage", "ww"]), Json(true))
  assert_eq(
    object_fields_unchecked_v3(mct_rule(report, ElleReadCommitted, "G1a")).at(
      "status",
    ),
    Json("refuted"),
  )
}

///|
test "model composition 16 intermediate actual read is G1b but not G1a" {
  let report = mct_report(
    mct_facts(
      hist([
        tx("A", [write_op("x", "a1"), write_op("x", "a2")]),
        tx("B", [read_op("x", "a1")]),
      ]),
    ),
    models=[ElleReadUncommitted, ElleReadCommitted],
  )
  assert_eq(mct_status(report, ElleReadUncommitted), "checked-compatible")
  assert_eq(
    object_fields_unchecked_v3(mct_rule(report, ElleReadCommitted, "G1a")).at(
      "status",
    ),
    Json("checked-compatible"),
  )
  assert_eq(
    object_fields_unchecked_v3(mct_rule(report, ElleReadCommitted, "G1b")).at(
      "status",
    ),
    Json("refuted"),
  )
}

///|
test "model composition 17 INT is nearest actual delivered read not an order predecessor" {
  let report = mct_report(
    mct_facts(
      hist([
        tx("W", [write_op("x", "x1")]),
        tx("R", [read_op("x", "x0"), read_op("x", "x1")]),
      ]),
    ),
    models=[ElleReadCommitted, ElleSerializable],
  )
  assert_eq(mct_status(report, ElleReadCommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleSerializable), "refuted")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleSerializable, "literal/internal"),
    ).at("status"),
    Json("refuted"),
  )
}

///|
test "model composition 18 own future source is pending applicability not fabricated G1c" {
  let report = mct_report(
    mct_facts(hist([tx("A", [read_op("x", "later"), write_op("x", "later")])])),
    models=[ElleReadCommitted],
  )
  assert_eq(mct_status(report, ElleReadCommitted), "unknown")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleReadCommitted, "future-source-applicability"),
    ).at("status"),
    Json("pending"),
  )
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleReadCommitted, "graph/I/data-only"),
    ).at("status"),
    Json("unknown"),
  )
}

///|
test "model composition 19 missing read source leaves model unknown while WW itself completes" {
  let report = mct_report(
    mct_facts(hist([tx("A", [read_op("x", "unobserved")])])),
    models=[ElleReadUncommitted, ElleReadCommitted],
  )
  assert_eq(mct_status(report, ElleReadUncommitted), "unknown")
  assert_eq(mct_status(report, ElleReadCommitted), "unknown")
  assert_eq(v4_test_at(report, ["sourceCoverage", "ww"]), Json(true))
}

///|
fn mct_reversed_time() -> History {
  let a : Transaction = {
    id: "A",
    status: Committed,
    ops: [write_op("x", "x1")],
    start: Some(3L),
    end: Some(4L),
  }
  let b : Transaction = {
    id: "B",
    status: Committed,
    ops: [write_op("x", "x2")],
    start: Some(1L),
    end: Some(2L),
  }
  hist([a, b], orders={ "x": ["x0", "x1", "x2"], "y": ["y0"] })
}

///|
test "model composition 20 actual RT cycle refutes strong RU while base RU passes" {
  let report = mct_report(mct_facts(mct_reversed_time()), models=[
    ElleReadUncommitted,
    ElleStrongReadUncommitted,
  ])
  assert_eq(mct_status(report, ElleReadUncommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleStrongReadUncommitted), "refuted")
}

///|
test "model composition 21 explicit nonoverlapping logical process cycle is source-bound" {
  let facts = mct_facts(
    mct_reversed_time(),
    clients=[{ id: "client", transactions: ["B", "A"], }],
    clients_complete=true,
  )
  let report = mct_report(facts, models=[
    ElleReadUncommitted,
    ElleSessionReadUncommitted,
  ])
  assert_eq(mct_status(report, ElleReadUncommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleSessionReadUncommitted), "refuted")
}

///|
test "model composition 22 missing clients does not create pooled sessions" {
  let report = mct_report(mct_facts(mct_unknown()), models=[
    ElleSessionReadUncommitted,
  ])
  assert_eq(v4_test_at(report, ["sourceCoverage", "process"]), Json(false))
  assert_eq(mct_status(report, ElleSessionReadUncommitted), "unknown")
}

///|
test "model composition 23 a declared client alone cannot prove nonoverlap" {
  let input = hist([
    tx("A", [write_op("x", "x1")]),
    tx("B", [write_op("y", "y1")]),
  ])
  let facts = mct_facts(
    input,
    clients=[{ id: "client", transactions: ["A", "B"], }],
    clients_complete=true,
  )
  let report = mct_report(facts, models=[
    ElleReadUncommitted,
    ElleSessionReadUncommitted,
    ElleStrongReadUncommitted,
  ])
  assert_eq(mct_status(report, ElleReadUncommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleSessionReadUncommitted), "unknown")
  assert_eq(mct_status(report, ElleStrongReadUncommitted), "unknown")
}

///|
test "model composition 24 client identities are validated and not aliases" {
  let h = register_history_v4(mct_single()).unwrap()
  assert_true(
    model_facts_v4(h, clients=[{ id: "c", transactions: ["missing"], }])
    is Err(_),
  )
  assert_true(
    model_facts_v4(h, clients=[{ id: "c", transactions: ["A", "A"], }])
    is Err(_),
  )
  let members = ["A"]
  let clients = [{ id: "c", transactions: members, }]
  let facts = model_facts_v4(h, clients~, clients_complete=true).unwrap()
  let before = mct_report(facts)
  members.push("missing")
  clients.clear()
  assert_eq(mct_report(facts), before)
}

///|
test "model composition 25 model enums prevent alias duplication and reject invalid budgets" {
  assert_eq(elle_core_models_v4().length(), 14)
  assert_true(
    model_options_v4(models=[ElleReadCommitted, ElleReadCommitted]) is Err(_),
  )
  assert_true(model_options_v4(models=[]) is Err(_))
  assert_true(model_options_v4(max_states=100001) is Err(_))
  assert_true(model_options_v4(max_source_checks=1000001) is Err(_))
}

///|
test "model composition 26 source budget zero never means a completed model" {
  let report = mct_report(
    mct_facts(mct_single()),
    models=[ElleReadUncommitted, ElleReadCommitted],
    source=0,
  )
  assert_eq(mct_status(report, ElleReadUncommitted), "unknown")
  assert_eq(mct_status(report, ElleReadCommitted), "unknown")
}

///|
test "model composition 27 caller budget cannot be elevated by a report" {
  let facts = mct_facts(mct_ww_cycle())
  let high = model_options_v4(models=[ElleReadUncommitted]).unwrap()
  let low = model_options_v4(models=[ElleReadUncommitted], max_edge_checks=0).unwrap()
  let report = model_classification_v4_json(classify_models_v4(facts, high))
  assert_true(!verify_models_v4(facts, report, low))
  assert_eq(
    mct_status(
      mct_report(facts, models=[ElleReadUncommitted], edge_checks=0),
      ElleReadUncommitted,
    ),
    "unknown",
  )
}

///|
test "model composition 28 returned JSON does not alias retained originals" {
  let facts = mct_facts(mct_single())
  let options = model_options_v4(models=[ElleReadCommitted]).unwrap()
  let result = classify_models_v4(facts, options)
  let original = model_classification_v4_json(result)
  let copy = model_classification_v4_json(result)
  v4_test_replace(
    copy,
    ["observations", "history", "initial", "x"],
    Json("changed"),
  )
  assert_true(!verify_models_v4(facts, copy, options))
  assert_eq(model_classification_v4_json(result), original)
  assert_eq(mct_report(facts, models=[ElleReadCommitted]), original)
}

///|
test "model composition 29 declared status source tampering is rejected" {
  let facts = mct_facts(mct_single())
  let options = model_options_v4(models=[ElleReadCommitted]).unwrap()
  let report = model_classification_v4_json(classify_models_v4(facts, options))
  v4_test_replace(report, ["sourceCoverage", "ww"], Json(false))
  assert_true(!verify_models_v4(facts, report, options))
}

///|
test "model composition 30 normalized raw register has fresh G1a and RU write closure" {
  let trace : Json = {
    "traceSchema": 3,
    "dataModel": "point-register-v1",
    "clockDomain": "models-test",
    "scope": { "exclusiveWriters": true },
    "gaps": [],
    "events": [
      {
        "seq": 1,
        "time": 0,
        "kind": "snapshot",
        "initial": { "x": "x0" },
        "consistent": true,
      },
      { "seq": 2, "time": 1, "kind": "begin", "tx": "W", "connection": "w" },
      {
        "seq": 3,
        "time": 2,
        "kind": "write",
        "tx": "W",
        "key": "x",
        "version": "a",
        "predecessor": "x0",
      },
      { "seq": 4, "time": 3, "kind": "rollback_ok", "tx": "W" },
      { "seq": 5, "time": 4, "kind": "begin", "tx": "R", "connection": "r" },
      {
        "seq": 6,
        "time": 5,
        "kind": "read",
        "tx": "R",
        "key": "x",
        "version": "a",
      },
      { "seq": 7, "time": 6, "kind": "commit_request", "tx": "R" },
      { "seq": 8, "time": 7, "kind": "commit_ok", "tx": "R" },
    ],
  }
  let facts = model_facts_v4(parse_history_v4(trace.stringify()).unwrap()).unwrap()
  let report = mct_report(facts, models=[ElleReadUncommitted, ElleReadCommitted])
  assert_eq(mct_status(report, ElleReadUncommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleReadCommitted), "refuted")
}

///|
test "model composition 31 list actual multi append raw source uses effective index" {
  let trace = v4_test_model_complete(AppendListV4, [
    leg_test_append("A", "a1"),
    leg_test_append("A", "a2"),
    leg_test_read("A", ["a1", "a2"]),
  ])
  let facts = model_facts_v4(parse_history_v4(trace.stringify()).unwrap()).unwrap()
  let report = mct_report(facts, models=[ElleReadUncommitted, ElleReadCommitted])
  assert_eq(mct_status(report, ElleReadUncommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleReadCommitted), "checked-compatible")
}

///|
test "model composition 32 relation point read uses original row sources" {
  let body = [rpg_begin("A"), rpg_read("A", "1", Some("v0"))]
  rpg_commit(body, "A")
  let facts = model_facts_v4(
    parse_history_v4(rpg_trace(body).stringify()).unwrap(),
  ).unwrap()
  let report = mct_report(facts, models=[ElleReadUncommitted, ElleReadCommitted])
  assert_eq(mct_status(report, ElleReadUncommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleReadCommitted), "checked-compatible")
}

///|
test "model composition 33 predicate key-slot profile does not fake fixed Elle equivalence" {
  let body = [rpg_begin("A"), rpg_read("A", "1", Some("v0"))]
  rpg_commit(body, "A")
  let facts = model_facts_v4(
    parse_history_v4(rpg_trace(body).stringify()).unwrap(),
  ).unwrap()
  let report = mct_report(
    facts,
    models=[ElleReadCommitted],
    relation=ModelRelationPredicateKeySlots,
  )
  assert_eq(mct_status(report, ElleReadCommitted), "unknown")
  assert_true(
    !capture_source_array_v4(v4_test_at(report, ["sourceCoverage", "dataGaps"])).is_empty(),
  )
}

///|
test "model composition 34 unknown producer identity never fabricates INT" {
  let source = model_register_source_v4(
    register_history_v4(
      hist([tx("A", [write_op("x", "x1"), read_op("x", "missing")])]),
    ).unwrap(),
    1000000,
  )
  assert_eq(source.rules.at("internal").status, "unknown")
  assert_eq(source.rules.at("internal").evidence, Json(([] : Array[Json])))
}

///|
test "model composition 35 actual known identity with unknown outcome still permits INT proof" {
  let w : Transaction = {
    id: "W",
    status: Unknown,
    ops: [write_op("x", "w")],
    start: None,
    end: None,
  }
  let source = model_register_source_v4(
    register_history_v4(
      hist([w, tx("A", [read_op("x", "x0"), read_op("x", "w")])]),
    ).unwrap(),
    1000000,
  )
  assert_eq(source.rules.at("internal").status, "refuted")
  assert_eq(source.rules.at("G1a").status, "unknown")
}

///|
test "model composition 36 source budget exact exhaustion boundary is independent" {
  let facts = mct_facts(mct_single())
  let first = mct_report(facts, models=[ElleReadCommitted])
  let used = capture_source_seq_v4(
    v4_test_at(first, ["execution", "source", "checks"]),
  ).to_int()
  let exact = mct_report(facts, models=[ElleReadCommitted], source=used)
  let less = mct_report(facts, models=[ElleReadCommitted], source=used - 1)
  assert_eq(mct_status(exact, ElleReadCommitted), "checked-compatible")
  assert_eq(v4_test_at(exact, ["execution", "source", "limited"]), Json(false))
  assert_eq(mct_status(less, ElleReadCommitted), "unknown")
  assert_eq(v4_test_at(less, ["execution", "source", "checks"]), Json(used - 1))
}

///|
test "model composition 37 graph exact edge budget preserves proof and never overruns" {
  let facts = mct_facts(mct_ww_cycle())
  let first = mct_report(facts, models=[ElleReadUncommitted])
  let graph = object_fields_unchecked_v3(
    mct_rule(first, ElleReadUncommitted, "graph/W/data-only"),
  ).at("evidence")
  let used = capture_source_seq_v4(
    v4_test_at(graph, ["execution", "edgeChecks"]),
  ).to_int()
  let exact = mct_report(facts, models=[ElleReadUncommitted], edge_checks=used)
  assert_eq(mct_status(exact, ElleReadUncommitted), "refuted")
  let less = mct_report(
    facts,
    models=[ElleReadUncommitted],
    edge_checks=used - 1,
  )
  assert_eq(mct_status(less, ElleReadUncommitted), "unknown")
  let lowgraph = object_fields_unchecked_v3(
    mct_rule(less, ElleReadUncommitted, "graph/W/data-only"),
  ).at("evidence")
  assert_eq(v4_test_at(lowgraph, ["execution", "edgeChecks"]), Json(used - 1))
}

///|
test "model composition 38 source G1a refutation survives zero graph budgets" {
  let a : Transaction = {
    id: "A",
    status: Aborted,
    ops: [write_op("x", "a")],
    start: None,
    end: None,
  }
  let report = mct_report(
    mct_facts(hist([a, tx("B", [read_op("x", "a")])])),
    models=[ElleReadCommitted],
    states=0,
    edge_checks=0,
  )
  assert_eq(mct_status(report, ElleReadCommitted), "refuted")
}

///|
test "model composition 39 early direct refutation survives later source exhaustion" {
  let a : Transaction = {
    id: "A",
    status: Aborted,
    ops: [write_op("x", "a")],
    start: None,
    end: None,
  }
  let reads = Array::make(20, read_op("y", "y0"))
  let facts = mct_facts(hist([a, tx("B", [read_op("x", "a")]), tx("C", reads)]))
  let full = mct_report(facts, models=[ElleReadCommitted])
  let used = capture_source_seq_v4(
    v4_test_at(full, ["execution", "source", "checks"]),
  ).to_int()
  let limited = mct_report(facts, models=[ElleReadCommitted], source=used - 1)
  assert_eq(v4_test_at(limited, ["execution", "source", "limited"]), Json(true))
  assert_eq(mct_status(limited, ElleReadCommitted), "refuted")
}

///|
test "model composition 40 original source snapshot includes otherwise unused facts" {
  let a = mct_single()
  let changed : History = { ..a, model: StrictSerializable, }
  let first = mct_facts(a)
  let other = mct_facts(changed)
  let options = model_options_v4(models=[ElleReadCommitted]).unwrap()
  let report = model_classification_v4_json(classify_models_v4(first, options))
  assert_true(!verify_models_v4(other, report, options))
  assert_true(first.source_sha256 != other.source_sha256)
}

///|
test "model composition 41 strong process inheritance is not automatically repaired from RT" {
  let a : Transaction = {
    id: "A",
    status: Committed,
    ops: [],
    start: Some(1L),
    end: Some(2L),
  }
  let b : Transaction = {
    id: "B",
    status: Committed,
    ops: [],
    start: Some(3L),
    end: Some(4L),
  }
  let facts = mct_facts(hist([a, b]))
  let report = mct_report(facts, models=[
    ElleReadUncommitted,
    ElleStrongReadUncommitted,
  ])
  assert_eq(mct_status(report, ElleReadUncommitted), "checked-compatible")
  assert_eq(v4_test_at(report, ["sourceCoverage", "realtime"]), Json(true))
  assert_eq(v4_test_at(report, ["sourceCoverage", "process"]), Json(false))
  assert_eq(mct_status(report, ElleStrongReadUncommitted), "unknown")
}

///|
test "model composition 42 known process order is not inferred from transaction array order" {
  let facts = mct_facts(mct_reversed_time())
  let source = model_register_source_v4(facts.history, 1000000)
  let orders = model_orders_v4(facts, source, 1000000)
  assert_true(orders.edges.all(e => e.kind != ScopedProcess))
  assert_true(
    orders.edges.any(e => {
      e.kind == ScopedRealtime && e.from == "B" && e.to == "A"
    }),
  )
}

///|
test "model composition 43 raw commit request without acknowledgement stays unknown" {
  let trace : Json = {
    "traceSchema": 3,
    "dataModel": "point-register-v1",
    "clockDomain": "models-test",
    "scope": { "exclusiveWriters": true },
    "gaps": [],
    "events": [
      {
        "seq": 1,
        "time": 0,
        "kind": "snapshot",
        "initial": { "x": "x0" },
        "consistent": true,
      },
      { "seq": 2, "time": 1, "kind": "begin", "tx": "A", "connection": "c" },
      {
        "seq": 3,
        "time": 2,
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "a",
        "predecessor": "x0",
      },
      { "seq": 4, "time": 3, "kind": "commit_request", "tx": "A" },
    ],
  }
  let facts = model_facts_v4(parse_history_v4(trace.stringify()).unwrap()).unwrap()
  let report = mct_report(facts, models=[
    ElleReadUncommitted,
    ElleStrongReadUncommitted,
  ])
  assert_eq(mct_status(report, ElleReadUncommitted), "unknown")
  assert_eq(v4_test_at(report, ["sourceCoverage", "realtime"]), Json(false))
}

///|
test "model composition 44 row INT source proof coexists with unrelated gaps" {
  let body = [rpg_begin("W"), rpg_write("W", "1", "v1", Some("v0"))]
  rpg_commit(body, "W")
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "1", Some("v0")))
  body.push(rpg_read("R", "1", Some("v1")))
  rpg_commit(body, "R")
  let facts = model_facts_v4(
    parse_history_v4(rpg_trace(body).stringify()).unwrap(),
  ).unwrap()
  let report = mct_report(facts, models=[ElleSerializable])
  assert_eq(mct_status(report, ElleSerializable), "refuted")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleSerializable, "literal/internal"),
    ).at("status"),
    Json("refuted"),
  )
}

///|
test "model composition 45 typed identity index does not join legal delimiters" {
  let a : History = {
    model: Serializable,
    initial: { "a|b": "c", "a": "b|c" },
    version_orders: {},
    transactions: [
      {
        id: "T|1",
        status: Committed,
        ops: [write_op("a|b", "v"), read_op("a", "b|c")],
        start: None,
        end: None,
      },
    ],
  }
  let report = mct_report(mct_facts(a), models=[ElleReadCommitted])
  assert_eq(mct_status(report, ElleReadCommitted), "checked-compatible")
}

///|
test "model composition 46 list aborted source does not poison zero-WW RU" {
  let body = [
    leg_test_begin("W"),
    leg_test_append("W", "a"),
    ({ "kind": "rollback_ok", "tx": "W" } : Json),
    leg_test_begin("R"),
    leg_test_read("R", ["a"]),
  ]
  leg_test_commit(body, "R")
  let trace = classification26_test_list(body)
  let facts = model_facts_v4(parse_history_v4(trace.stringify()).unwrap()).unwrap()
  let report = mct_report(facts, models=[ElleReadUncommitted, ElleReadCommitted])
  assert_eq(mct_status(report, ElleReadUncommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleReadCommitted), "refuted")
}

///|
test "model composition 47 delivered duplicate identity refutes RU without a fake WW cycle" {
  let body = [leg_test_begin("W"), leg_test_append("W", "a")]
  leg_test_commit(body, "W")
  body.push(leg_test_begin("R"))
  body.push(leg_test_read("R", ["a", "a"]))
  leg_test_commit(body, "R")
  let facts = model_facts_v4(
    parse_history_v4(classification26_test_list(body).stringify()).unwrap(),
  ).unwrap()
  let report = mct_report(facts, models=[ElleReadUncommitted])
  assert_eq(mct_status(report, ElleReadUncommitted), "refuted")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleReadUncommitted, "literal/duplicate-elements"),
    ).at("status"),
    Json("refuted"),
  )
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleReadUncommitted, "graph/W/data-only"),
    ).at("status"),
    Json("checked-compatible"),
  )
}

///|
test "model composition 48 RC uses every valid external read including later same-key reads" {
  let input = hist([
    tx("A", [read_op("x", "x0"), read_op("x", "x1"), write_op("y", "y1")]),
    tx("B", [read_op("y", "y0"), read_op("y", "y1"), write_op("x", "x1")]),
  ])
  let facts = mct_facts(input)
  let source = model_register_source_v4(facts.history, 1000000)
  let wr = source.edges.filter(e => e.kind == ScopedWRItem)
  assert_eq(wr.length(), 2)
  assert_true(
    wr.all(e => {
      e.sources.any(raw => {
        object_fields_unchecked_v3(raw).at("operationIndex") == Json(1)
      })
    }),
  )
  let report = mct_report(facts, models=[ElleReadUncommitted, ElleReadCommitted])
  assert_eq(mct_status(report, ElleReadUncommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleReadCommitted), "refuted")
  let witness = v4_test_at(
    object_fields_unchecked_v3(
      mct_rule(report, ElleReadCommitted, "graph/I/data-only"),
    ).at("evidence"),
    ["witness"],
  )
  assert_true(witness != Json::null())
}

///|
test "model composition 49 first-read-only control is ordinary two-RW skew allowed by RC" {
  let input = hist([
    tx("A", [read_op("x", "x0"), write_op("y", "y1")]),
    tx("B", [read_op("y", "y0"), write_op("x", "x1")]),
  ])
  let report = mct_report(mct_facts(input), models=[
    ElleReadCommitted,
    ElleSerializable,
  ])
  assert_eq(mct_status(report, ElleReadCommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleSerializable), "refuted")
}

///|
test "model composition 50 own-at-delivery reads do not create WR or anti-dependency edges" {
  let input = hist([
    tx("A", [write_op("x", "x1"), read_op("x", "x1")]),
    tx("B", [write_op("y", "y1"), read_op("y", "y1")]),
  ])
  let source = model_register_source_v4(
    register_history_v4(input).unwrap(),
    1000000,
  )
  assert_true(source.edges.all(e => e.kind == ScopedWWItem))
  let report = mct_report(mct_facts(input), models=[ElleReadCommitted])
  assert_eq(mct_status(report, ElleReadCommitted), "checked-compatible")
}

///|
test "model composition 51 full PL3 cycle obligation includes a zero-RW WR cycle" {
  let input = hist([
    tx("A", [read_op("x", "x1"), write_op("y", "y1")]),
    tx("B", [read_op("y", "y1"), write_op("x", "x1")]),
  ])
  let report = mct_report(mct_facts(input), models=[
    ElleSerializable,
    ElleStrictSerializable,
  ])
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleSerializable, "literal/PL-3-cycle-exists"),
    ).at("status"),
    Json("refuted"),
  )
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleStrictSerializable, "literal/PL-SS-cycle-exists"),
    ).at("status"),
    Json("refuted"),
  )
}

///|
test "model composition 52 fixed literal SI names are retained with explicit constructive coverage" {
  let report = mct_report(mct_facts(mct_single()), models=[
    ElleSnapshotIsolation,
  ])
  let si = mct_rule(report, ElleSnapshotIsolation, "literal/G-SI")
  let sib = mct_rule(report, ElleSnapshotIsolation, "literal/G-SIb")
  assert_eq(
    object_fields_unchecked_v3(si).at("status"),
    Json("checked-compatible"),
  )
  assert_eq(
    object_fields_unchecked_v3(sib).at("status"),
    Json("checked-compatible"),
  )
  assert_eq(
    v4_test_at(si, ["evidence", "coverage"]),
    Json("exists-generalized-si-completion"),
  )
  assert_eq(
    v4_test_at(si, ["evidence", "transactionBeginUsedAsSnapshot"]),
    Json(false),
  )
}

///|
test "model composition 53 raw unresolved-order calls never mutate the retained normalized snapshot" {
  let trace : Json = {
    "traceSchema": 3,
    "dataModel": "point-register-v1",
    "clockDomain": "models-test",
    "scope": { "exclusiveWriters": true },
    "gaps": [],
    "events": [
      {
        "seq": 1,
        "time": 0,
        "kind": "snapshot",
        "initial": { "x": "x0" },
        "consistent": true,
      },
      { "seq": 2, "time": 1, "kind": "begin", "tx": "A", "connection": "a" },
      {
        "seq": 3,
        "time": 2,
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "a",
        "predecessor": "x0",
      },
      { "seq": 4, "time": 3, "kind": "commit_request", "tx": "A" },
      { "seq": 5, "time": 4, "kind": "commit_ok", "tx": "A" },
      { "seq": 6, "time": 5, "kind": "begin", "tx": "B", "connection": "b" },
      {
        "seq": 7,
        "time": 6,
        "kind": "write",
        "tx": "B",
        "key": "x",
        "version": "b",
        "predecessor": "x0",
      },
      { "seq": 8, "time": 7, "kind": "commit_request", "tx": "B" },
      { "seq": 9, "time": 8, "kind": "commit_ok", "tx": "B" },
    ],
  }
  let history = parse_history_v4(trace.stringify()).unwrap()
  let normalized = match history.payload {
    RegisterSnapshot(_, Some(n)) => n
    _ => Json::null()
  }
  let before = v4_json_copy(normalized)
  let facts = model_facts_v4(history).unwrap()
  let first = mct_report(facts)
  assert_eq(mct_report(facts), first)
  assert_eq(normalized, before)
}

///|
test "model composition 54 unproven relation SQL cannot complete RU installed-write coverage" {
  let body = [
    rpg_begin("A"),
    ({ "kind": "statement", "tx": "A", "sql": "SELECT unknown_effect()" } : Json),
  ]
  rpg_commit(body, "A")
  let facts = model_facts_v4(
    parse_history_v4(rpg_trace(body).stringify()).unwrap(),
  ).unwrap()
  let report = mct_report(facts, models=[ElleReadUncommitted])
  assert_eq(mct_status(report, ElleReadUncommitted), "unknown")
  assert_eq(v4_test_at(report, ["sourceCoverage", "ww"]), Json(false))
}

///|
test "model composition 55 incomplete relation SELECT does not by itself invalidate closed WW" {
  let query = rpg_read("A", "1", Some("v0"))
  object_fields_unchecked_v3(query)["complete"] = Json(false)
  let body = [rpg_begin("A"), query]
  rpg_commit(body, "A")
  let facts = model_facts_v4(
    parse_history_v4(rpg_trace(body).stringify()).unwrap(),
  ).unwrap()
  let report = mct_report(facts, models=[ElleReadUncommitted, ElleReadCommitted])
  assert_eq(mct_status(report, ElleReadUncommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleReadCommitted), "unknown")
}

///|
test "model composition 56 unknown raw SQL cannot create an assumed-final WW cycle witness" {
  let source : ModelSourceV4 = {
    point_program: None,
    nodes: ["A", "B"],
    edges: [
      {
        id: "e1",
        from: "A",
        to: "B",
        kind: ScopedWWItem,
        sources: [({ "raw": true } : Json)],
      },
      {
        id: "e2",
        from: "B",
        to: "A",
        kind: ScopedWWItem,
        sources: [({ "raw": true } : Json)],
      },
    ],
    boundaries: [],
    rules: Map([]),
    gaps: [],
    ww_complete: true,
    wr_complete: true,
    rw_complete: true,
    execution: Json::null(),
    profile: "test",
  }
  let body = [
    rpg_begin("A"),
    ({ "kind": "statement", "tx": "A", "sql": "SELECT unknown_effect()" } : Json),
  ]
  rpg_commit(body, "A")
  let history = parse_history_v4(rpg_trace(body).stringify()).unwrap()
  let actual = model_source_applicability_v4(history, source)
  assert_true(actual.edges.is_empty())
  assert_false(actual.ww_complete)
}

///|
test "model composition 57 read-own-latest is distinct from full repeatable external INT" {
  let facts = mct_facts(
    hist([tx("A", [write_op("x", "x1"), read_op("x", "x0")])]),
  )
  let report = mct_report(facts, models=[
    ElleReadUncommitted,
    ElleReadCommitted,
    ElleSerializable,
  ])
  assert_eq(mct_status(report, ElleReadUncommitted), "unknown")
  assert_eq(mct_status(report, ElleReadCommitted), "unknown")
  assert_eq(mct_status(report, ElleSerializable), "refuted")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleReadCommitted, "program-source-applicability"),
    ).at("status"),
    Json("unknown"),
  )
}

///|
test "model composition 58 own overlay mismatch read cannot create a fabricated WR model witness" {
  let input = hist(
    [
      tx("A", [write_op("x", "x1"), read_op("x", "x2"), write_op("y", "y1")]),
      tx("B", [write_op("x", "x2"), read_op("y", "y1")]),
    ],
    orders={ "x": ["x0", "x1", "x2"], "y": ["y0", "y1"] },
  )
  let source = model_register_source_v4(
    register_history_v4(input).unwrap(),
    1000000,
  )
  assert_true(
    !source.edges.any(e => {
      e.kind == ScopedWRItem && e.from == "B" && e.to == "A"
    }),
  )
  assert_eq(source.rules.at("program-source-applicability").status, "unknown")
}

///|
test "model composition 59 raw read before later savepoint rollback remains valid own read" {
  let trace : Json = {
    "traceSchema": 3,
    "dataModel": "point-register-v1",
    "clockDomain": "models-test",
    "scope": { "exclusiveWriters": true },
    "gaps": [],
    "events": [
      {
        "seq": 1,
        "time": 0,
        "kind": "snapshot",
        "initial": { "x": "x0" },
        "consistent": true,
      },
      { "seq": 2, "time": 1, "kind": "begin", "tx": "A", "connection": "c" },
      {
        "seq": 3,
        "time": 2,
        "kind": "savepoint",
        "tx": "A",
        "name": "s",
        "instance": "s1",
      },
      {
        "seq": 4,
        "time": 3,
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "a",
        "predecessor": "x0",
      },
      {
        "seq": 5,
        "time": 4,
        "kind": "read",
        "tx": "A",
        "key": "x",
        "version": "a",
      },
      {
        "seq": 6,
        "time": 5,
        "kind": "rollback_to",
        "tx": "A",
        "instance": "s1",
      },
      {
        "seq": 7,
        "time": 6,
        "kind": "read",
        "tx": "A",
        "key": "x",
        "version": "x0",
      },
      { "seq": 8, "time": 7, "kind": "commit_request", "tx": "A" },
      { "seq": 9, "time": 8, "kind": "commit_ok", "tx": "A" },
    ],
  }
  let h = parse_history_v4(trace.stringify()).unwrap()
  let source = model_register_source_v4(h, 1000000)
  assert_eq(
    source.rules.at("program-source-applicability").status,
    "checked-compatible",
  )
  assert_true(source.edges.is_empty())
}

///|
test "model composition 60 raw read of an already revoked own effect is unknown applicability" {
  let trace : Json = {
    "traceSchema": 3,
    "dataModel": "point-register-v1",
    "clockDomain": "models-test",
    "scope": { "exclusiveWriters": true },
    "gaps": [],
    "events": [
      {
        "seq": 1,
        "time": 0,
        "kind": "snapshot",
        "initial": { "x": "x0" },
        "consistent": true,
      },
      { "seq": 2, "time": 1, "kind": "begin", "tx": "A", "connection": "c" },
      {
        "seq": 3,
        "time": 2,
        "kind": "savepoint",
        "tx": "A",
        "name": "s",
        "instance": "s1",
      },
      {
        "seq": 4,
        "time": 3,
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "a",
        "predecessor": "x0",
      },
      {
        "seq": 5,
        "time": 4,
        "kind": "rollback_to",
        "tx": "A",
        "instance": "s1",
      },
      {
        "seq": 6,
        "time": 5,
        "kind": "read",
        "tx": "A",
        "key": "x",
        "version": "a",
      },
      { "seq": 7, "time": 6, "kind": "commit_request", "tx": "A" },
      { "seq": 8, "time": 7, "kind": "commit_ok", "tx": "A" },
    ],
  }
  let h = parse_history_v4(trace.stringify()).unwrap()
  let report = mct_report(model_facts_v4(h).unwrap(), models=[
    ElleReadUncommitted,
    ElleReadCommitted,
  ])
  assert_eq(mct_status(report, ElleReadUncommitted), "unknown")
  assert_eq(mct_status(report, ElleReadCommitted), "unknown")
}

///|
test "model composition 61 single writer does not discharge contradictory multi-item read order" {
  let body = [
    leg_test_begin("W"),
    leg_test_append("W", "a1"),
    leg_test_append("W", "a2"),
  ]
  leg_test_commit(body, "W")
  body.push(leg_test_begin("R"))
  body.push(leg_test_read("R", ["a2", "a1"]))
  leg_test_commit(body, "R")
  let facts = model_facts_v4(
    parse_history_v4(classification26_test_list(body).stringify()).unwrap(),
  ).unwrap()
  let report = mct_report(facts, models=[ElleReadUncommitted])
  assert_eq(mct_status(report, ElleReadUncommitted), "unknown")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleReadUncommitted, "literal/cyclic-versions"),
    ).at("status"),
    Json("unknown"),
  )
}

///|
test "model composition 62 list own suffix is a weak-model applicability premise" {
  let trace = v4_test_model_complete(AppendListV4, [
    leg_test_append("A", "a1"),
    leg_test_read("A", []),
  ])
  let facts = model_facts_v4(parse_history_v4(trace.stringify()).unwrap()).unwrap()
  let report = mct_report(facts, models=[ElleReadUncommitted, ElleReadCommitted])
  assert_eq(mct_status(report, ElleReadUncommitted), "unknown")
  assert_eq(mct_status(report, ElleReadCommitted), "unknown")
}

///|
test "model composition 63 point row own-write mismatch never completes RC" {
  let body = [
    rpg_begin("A"),
    rpg_write("A", "1", "v1", Some("v0")),
    rpg_read("A", "1", Some("v0")),
  ]
  rpg_commit(body, "A")
  let facts = model_facts_v4(
    parse_history_v4(rpg_trace(body).stringify()).unwrap(),
  ).unwrap()
  let report = mct_report(facts, models=[ElleReadUncommitted, ElleReadCommitted])
  assert_eq(mct_status(report, ElleReadUncommitted), "unknown")
  assert_eq(mct_status(report, ElleReadCommitted), "unknown")
}

///|
test "model composition 64 known list identity with changed value cannot complete RU" {
  let body = [leg_test_begin("W"), leg_test_append("W", "a")]
  leg_test_commit(body, "W")
  body.push(leg_test_begin("R"))
  body.push({
    "kind": "list_read",
    "tx": "R",
    "key": "x",
    "items": [{ "id": "a", "value": "changed" }],
  })
  leg_test_commit(body, "R")
  let facts = model_facts_v4(
    parse_history_v4(classification26_test_list(body).stringify()).unwrap(),
  ).unwrap()
  let report = mct_report(facts, models=[ElleReadUncommitted])
  assert_eq(mct_status(report, ElleReadUncommitted), "unknown")
  assert_eq(v4_test_at(report, ["sourceCoverage", "ww"]), Json(true))
}

///|
test "model composition 65 relation source identity values cannot silently change under RU" {
  let body = [rpg_begin("R"), rpg_read("R", "1", Some("v0"), value="changed")]
  rpg_commit(body, "R")
  let facts = model_facts_v4(
    parse_history_v4(rpg_trace(body).stringify()).unwrap(),
  ).unwrap()
  let report = mct_report(facts, models=[ElleReadUncommitted])
  assert_eq(mct_status(report, ElleReadUncommitted), "unknown")
}

///|
test "model composition 66 an externally given snapshot requires unsupported facts instead of existential coverage" {
  let facts = mct_facts(mct_single())
  let options = model_options_v4(
    models=[ElleSnapshotIsolation],
    completion_policy=ModelGivenSnapshotsUnsupported,
  ).unwrap()
  let report = model_classification_v4_json(classify_models_v4(facts, options))
  assert_eq(mct_status(report, ElleSnapshotIsolation), "unknown")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleSnapshotIsolation, "literal/G-SIb"),
    ).at("status"),
    Json("pending"),
  )
}

///|
test "model composition 67 write skew has a valid generalized SI prefix completion but is not serializable" {
  let facts = mct_facts(skew())
  let report = mct_report(facts, models=[
    ElleSnapshotIsolation,
    ElleSerializable,
    ElleConsistentView,
  ])
  assert_eq(mct_status(report, ElleSnapshotIsolation), "checked-compatible")
  assert_eq(mct_status(report, ElleConsistentView), "checked-compatible")
  assert_eq(mct_status(report, ElleSerializable), "refuted")
  let completion = mct_rule(
    report,
    ElleSnapshotIsolation,
    "completion/Ext/data-only",
  )
  assert_eq(
    v4_test_at(completion, ["evidence", "checks", "allWRVisible"]),
    Json(true),
  )
  assert_eq(
    v4_test_at(completion, [
      "evidence", "checks", "allRWImmediateSuccessorsInvisible",
    ]),
    Json(true),
  )
}

///|
test "model composition 68 SI prefix certificate respects actual process and realtime context separately" {
  let base = skew()
  let a : Transaction = {
    ..base.transactions[0],
    start: Some(1L),
    end: Some(2L),
  }
  let b : Transaction = {
    ..base.transactions[1],
    start: Some(3L),
    end: Some(4L),
  }
  let facts = mct_facts(
    { ..base, transactions: [a, b], },
    clients=[{ id: "client", transactions: [a.id, b.id], }],
    clients_complete=true,
  )
  let report = mct_report(facts, models=[
    ElleSnapshotIsolation,
    ElleSessionSnapshotIsolation,
    ElleStrongSnapshotIsolation,
  ])
  assert_eq(mct_status(report, ElleSnapshotIsolation), "checked-compatible")
  assert_eq(mct_status(report, ElleSessionSnapshotIsolation), "refuted")
  assert_eq(mct_status(report, ElleStrongSnapshotIsolation), "refuted")
}

///|
test "model composition 69 completion evidence tampering is rejected from caller facts and budgets" {
  let facts = mct_facts(skew())
  let options = model_options_v4(models=[ElleSnapshotIsolation]).unwrap()
  let report = model_classification_v4_json(classify_models_v4(facts, options))
  let rule = mct_rule(report, ElleSnapshotIsolation, "completion/Ext/data-only")
  v4_test_replace(rule, ["evidence", "commitOrder"], Json(["invented"]))
  assert_true(!verify_models_v4(facts, report, options))
}

///|
test "model composition 70 no source profile silently acquires a register SI theorem" {
  let trace = v4_test_model_complete(AppendListV4, [leg_test_append("A", "a")])
  let facts = model_facts_v4(parse_history_v4(trace.stringify()).unwrap()).unwrap()
  let report = mct_report(facts, models=[ElleSnapshotIsolation])
  assert_eq(mct_status(report, ElleSnapshotIsolation), "unknown")
  assert_eq(
    object_fields_unchecked_v3(
      mct_rule(report, ElleSnapshotIsolation, "completion/Ext/data-only"),
    ).at("status"),
    Json("pending"),
  )
}

///|
test "model composition 71 unknown empty transaction still cannot complete a model" {
  let unknown : Transaction = {
    id: "U",
    status: Unknown,
    ops: [],
    start: None,
    end: None,
  }
  let facts = mct_facts(hist([unknown, tx("A", [read_op("x", "x0")])]))
  let report = mct_report(facts, models=[
    ElleReadUncommitted,
    ElleReadCommitted,
    ElleSnapshotIsolation,
  ])
  assert_eq(mct_status(report, ElleReadUncommitted), "unknown")
  assert_eq(mct_status(report, ElleReadCommitted), "unknown")
  assert_eq(mct_status(report, ElleSnapshotIsolation), "unknown")
}

///|
test "model composition 72 own-audit budget exhaustion cannot admit unchecked external read edges" {
  let h = register_history_v4(
    hist([
      tx("A", [read_op("x", "x0"), write_op("y", "y1")]),
      tx("B", [read_op("y", "y1"), write_op("x", "x1")]),
    ]),
  ).unwrap()
  let (_, txs, _, _, _) = model_register_input_v4(h)
  let full = model_register_source_v4(h, 1000000)
  let audit = model_register_program_audit_v4(txs, 0)
  assert_eq(audit.rule.status, "unknown")
  assert_true(
    model_register_audited_edges_v4(full.edges, audit).all(e => {
      e.kind == ScopedWWItem
    }),
  )
}

///|
test "model composition 73 RU never runs irrelevant anti-dependency or SI graph searches" {
  let report = mct_report(mct_facts(skew()), models=[ElleReadUncommitted])
  assert_eq(mct_status(report, ElleReadUncommitted), "checked-compatible")
  assert_eq(
    v4_test_at(report, ["execution", "graphRulesEvaluated"]),
    Json(["graph/W/data-only"]),
  )
}

///|
test "model composition 74 actual prefix construction has an independent exact state boundary" {
  let facts = mct_facts(mct_single())
  let enough = mct_report(facts, models=[ElleSnapshotIsolation], states=2)
  assert_eq(mct_status(enough, ElleSnapshotIsolation), "checked-compatible")
  let short = mct_report(facts, models=[ElleSnapshotIsolation], states=1)
  assert_eq(mct_status(short, ElleSnapshotIsolation), "unknown")
  let certificate = object_fields_unchecked_v3(
    mct_rule(short, ElleSnapshotIsolation, "completion/Ext/data-only"),
  ).at("evidence")
  assert_eq(v4_test_at(certificate, ["execution", "states"]), Json(1))
  assert_eq(v4_test_at(certificate, ["execution", "limited"]), Json(true))
}
