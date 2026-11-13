///|
fn mix_profiles_v4() -> Array[
  (ModelFactsV4, ModelRelationProfileV4, ModelListProfileV4),
] {
  [
    (im_facts(), ModelRelationPoint, ModelListNative),
    (
      model_facts_v4(mlp_history(mlp_multi())).unwrap(),
      ModelRelationPoint,
      ModelListPrefixStates,
    ),
    (
      model_facts_v4(rcl_history(rmp_one())).unwrap(),
      ModelRelationAtomicRows,
      ModelListNative,
    ),
  ]
}

///|
test "model index sharing 01 original classifier report bytes and counters remain unchanged across profiles and budgets" {
  for (facts, relation_profile, list_profile) in mix_profiles_v4() {
    for
      (source, states, edges) in [
        (0, 100000, 1000000),
        (1, 100000, 1000000),
        (8, 100000, 1000000),
        (1000000, 0, 1000000),
        (1000000, 1, 1000000),
        (1000000, 100000, 0),
        (1000000, 100000, 1),
        (1000000, 100000, 1000000),
      ] {
      let options = model_options_v4(
        models=elle_core_models_v4(),
        relation_profile~,
        list_profile~,
        max_source_checks=source,
        max_states=states,
        max_edge_checks=edges,
      ).unwrap()
      let original = model_original_index_v4(facts, options)
      let indexed = model_classification_v4_json(
        classify_models_from_index_v4(facts, options, original),
      )
      let standalone = model_classification_v4_json(
        classify_models_v4(facts, options),
      )
      assert_eq(indexed.stringify(), standalone.stringify())
      assert_eq(
        v4_test_at(indexed, ["execution", "source"]),
        original.source.execution,
      )
      assert_eq(
        v4_test_at(indexed, ["execution", "order"]),
        original.orders.execution,
      )
    }
  }
}

///|
test "model index sharing 02 inference report bytes are independent of fresh or shared index construction" {
  for (facts, relation_profile, list_profile) in mix_profiles_v4() {
    let options = model_options_v4(
      models=elle_core_models_v4(),
      relation_profile~,
      list_profile~,
    ).unwrap()
    let modules = [
      builtin_inference_module_v4(InferenceReadSources),
      builtin_inference_module_v4(InferenceGivenVersions),
      builtin_inference_module_v4(InferenceDeclaredOrders),
    ]
    let original = model_original_index_v4(facts, options)
    for maximum in [0, 1, 2, 8, 1000000] {
      let indexed = inference_v4_json(
        infer_dependencies_from_index_v4(
          facts, modules, options, maximum, original,
        ).unwrap(),
      )
      let fresh = inference_v4_json(
        infer_dependencies_v4(
          facts,
          modules,
          options~,
          max_inference_checks=maximum,
        ).unwrap(),
      )
      assert_eq(indexed.stringify(), fresh.stringify())
    }
  }
}

///|
test "model index sharing 03 registered constraints never enter the original completion index" {
  let facts = im_independent()
  let options = im_options()
  let original = model_original_index_v4(facts, options)
  let before = model_classification_v4_json(
    classify_models_from_index_v4(facts, options, original),
  ).stringify()
  let modules = [
    im_constraint("extra-A-B", "A", "B"),
    im_constraint("extra-B-A", "B", "A"),
  ]
  let extended = infer_dependencies_from_index_v4(
    facts, modules, options, 1000000, original,
  ).unwrap()
  assert_eq(original.source.edges.length(), 0)
  assert_eq(extended.source.edges.length(), 2)
  assert_false(extended.source.ww_complete)
  assert_eq(
    model_classification_v4_json(
      classify_models_from_index_v4(facts, options, original),
    ).stringify(),
    before,
  )
  let composed = inference_classification_v4_json(
    classify_with_inference_v4(facts, modules, options~).unwrap(),
  )
  assert_eq(v4_test_at(composed, ["baseClassification"]).stringify(), before)
  assert_eq(v4_test_at(composed, ["status"]), Json("refuted"))
  assert_eq(
    v4_test_at(composed, ["baseClassification", "status"]),
    Json("checked-compatible"),
  )
}

///|
test "model index sharing 04 module output cannot mutate the shared original source provenance" {
  let facts = im_facts()
  let options = im_options()
  let original = model_original_index_v4(facts, options)
  let before = classify_models_from_index_v4(facts, options, original).record.stringify()
  let mutate = inference_module_v4("mutate-detached", "detached/v1", fn(
    view,
    _,
    _,
  ) {
    let edges = view.data_edges()
    for edge in edges {
      edge.sources.clear()
    }
    Ok({ data_edges: [], order_edges: [], gaps: [], })
  }).unwrap()
  let _ = infer_dependencies_from_index_v4(
    facts,
    [mutate],
    options,
    1000000,
    original,
  ).unwrap()
  assert_eq(
    classify_models_from_index_v4(facts, options, original).record.stringify(),
    before,
  )
}
