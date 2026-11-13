///|
fn im_facts() -> ModelFactsV4 {
  mraw_facts(mraw_history(mraw_simple()))
}

///|
fn im_options() -> ModelOptionsV4 {
  model_options_v4(models=[ElleSerializable]).unwrap()
}

///|
fn im_report(
  facts : ModelFactsV4,
  modules : Array[InferenceModuleV4],
  maximum~ : Int32 = 1000000,
) -> Json {
  inference_classification_v4_json(
    classify_with_inference_v4(
      facts,
      modules,
      options=im_options(),
      max_inference_checks=maximum,
    ).unwrap(),
  )
}

///|
fn im_empty(id : String, parameters~ : Json = {}) -> InferenceModuleV4 {
  inference_module_v4(
    id,
    "empty/v1",
    fn(_view, _params, _budget) {
      Ok({ data_edges: [], order_edges: [], gaps: [], })
    },
    parameters~,
  ).unwrap()
}

///|
fn im_independent() -> ModelFactsV4 {
  mct_facts(
    hist([tx("A", [write_op("x", "x1")]), tx("B", [write_op("y", "y1")])], orders={
      "x": ["x0", "x1"],
      "y": ["y0", "y1"],
    }),
  )
}

///|
fn im_constraint(id : String, from : String, to : String) -> InferenceModuleV4 {
  inference_module_v4(
    id,
    "caller-auxiliary-order/v1",
    fn(_view, params, budget) {
      if !budget.charge() {
        return Ok({ data_edges: [], order_edges: [], gaps: [], })
      }
      let p = object_fields_unchecked_v3(params)
      Ok({
        data_edges: [
          {
            id: "constraint",
            from: capture_source_string_v4(p.at("from")),
            to: capture_source_string_v4(p.at("to")),
            kind: ScopedWWItem,
            sources: [{ "auxiliaryDeclaredFact": params }],
          },
        ],
        order_edges: [],
        gaps: [],
      })
    },
    parameters={ "from": Json(from), "to": Json(to) },
  ).unwrap()
}

///|
test "inference modules 01 builtin readers and version rules compose without changing fourteen base models" {
  let facts = im_facts()
  let modules = [
    builtin_inference_module_v4(InferenceReadSources),
    builtin_inference_module_v4(InferenceGivenVersions),
  ]
  let options = model_options_v4(models=elle_core_models_v4()).unwrap()
  let r = inference_classification_v4_json(
    classify_with_inference_v4(facts, modules, options~).unwrap(),
  )
  assert_eq(v4_test_at(r, ["status"]), Json("checked-compatible"))
  assert_eq(capture_source_array_v4(v4_test_at(r, ["models"])).length(), 14)
  assert_eq(
    v4_test_at(r, ["inference", "hasAdditionalConstraints"]),
    Json(false),
  )
  assert_true(verify_with_inference_v4(facts, r, modules, options~))
  assert_eq(
    v4_test_at(r, ["baseClassification"]),
    model_classification_v4_json(classify_models_v4(facts, options)),
  )
}

///|
test "inference modules 02 removal and reordering cannot reuse evidence" {
  let facts = im_facts()
  let a = builtin_inference_module_v4(InferenceReadSources)
  let b = builtin_inference_module_v4(InferenceGivenVersions)
  let r = im_report(facts, [a, b])
  assert_false(verify_with_inference_v4(facts, r, [a], options=im_options()))
  assert_false(verify_with_inference_v4(facts, r, [b, a], options=im_options()))
}

///|
test "inference modules 03 parameters are detached and caller-selected" {
  let params : Json = { "token": "before" }
  let first = im_empty("same-identity", parameters=params)
  object_fields_unchecked_v3(params)["token"] = Json("after")
  let expected = im_empty("same-identity", parameters={ "token": "before" })
  let different = im_empty("same-identity", parameters={ "token": "after" })
  let facts = im_facts()
  let r = im_report(facts, [first])
  assert_true(
    verify_with_inference_v4(facts, r, [expected], options=im_options()),
  )
  assert_false(
    verify_with_inference_v4(facts, r, [different], options=im_options()),
  )
}

///|
test "inference modules 04 source getters do not share mutable containers between callbacks" {
  let facts = im_facts()
  let before = history_v4_json(facts.history)
  let mutate = inference_module_v4("mutator", "detached/v1", fn(view, _, _) {
    object_fields_unchecked_v3(view.history_json())["events"] = Json(
      ([] : Array[Json]),
    )
    let edges = view.data_edges()
    edges.clear()
    Ok({ data_edges: [], order_edges: [], gaps: [], })
  }).unwrap()
  let observe = inference_module_v4("observer", "detached/v1", fn(view, _, _) {
    if capture_source_array_v4(v4_test_at(view.history_json(), ["events"])).is_empty() {
      Err("The previous callback changed the source")
    } else {
      Ok({ data_edges: [], order_edges: [], gaps: [], })
    }
  }).unwrap()
  assert_eq(
    v4_test_at(im_report(facts, [mutate, observe]), ["status"]),
    Json("checked-compatible"),
  )
  assert_eq(history_v4_json(facts.history), before)
}

///|
test "inference modules 05 new acyclic constraints do not bless the old positive certificate" {
  let facts = im_independent()
  assert_eq(
    v4_test_at(
      model_classification_v4_json(classify_models_v4(facts, im_options())),
      ["status"],
    ),
    Json("checked-compatible"),
  )
  let modules = [im_constraint("extra-A-B", "A", "B")]
  let r = im_report(facts, modules)
  assert_eq(
    v4_test_at(r, ["inference", "hasAdditionalConstraints"]),
    Json(true),
  )
  assert_eq(v4_test_at(r, ["status"]), Json("unknown"))
  assert_true(verify_with_inference_v4(facts, r, modules, options=im_options()))
}

///|
test "inference modules 06 independent local modules can expose a conditional forbidden cycle" {
  let facts = im_independent()
  let modules = [
    im_constraint("extra-A-B", "A", "B"),
    im_constraint("extra-B-A", "B", "A"),
  ]
  let r = im_report(facts, modules)
  assert_eq(v4_test_at(r, ["status"]), Json("refuted"))
  assert_eq(
    v4_test_at(r, ["baseClassification", "status"]),
    Json("checked-compatible"),
  )
  let model = capture_source_array_v4(v4_test_at(r, ["models"]))[0]
  assert_false(
    capture_source_array_v4(v4_test_at(model, ["conditionalRefutations"])).is_empty(),
  )
}

///|
test "inference modules 07 independent inference budget is part of verification authority" {
  let facts = im_facts()
  let modules = [builtin_inference_module_v4(InferenceGivenVersions)]
  let good = im_report(facts, modules)
  let zero = im_report(facts, modules, maximum=0)
  assert_eq(v4_test_at(zero, ["status"]), Json("unknown"))
  assert_true(
    verify_with_inference_v4(
      facts,
      zero,
      modules,
      options=im_options(),
      max_inference_checks=0,
    ),
  )
  assert_false(
    verify_with_inference_v4(
      facts,
      good,
      modules,
      options=im_options(),
      max_inference_checks=0,
    ),
  )
}

///|
test "inference modules 08 a budget-exhausted module contributes no partial constraints" {
  let facts = im_independent()
  let busy = inference_module_v4("over-budget", "metered/v1", fn(
    _view,
    _,
    budget,
  ) {
    while budget.charge() {

    }
    Ok({
      data_edges: [
        {
          id: "a",
          from: "A",
          to: "B",
          kind: ScopedWWItem,
          sources: [Json("declared")],
        },
      ],
      order_edges: [],
      gaps: [],
    })
  }).unwrap()
  let inference = inference_v4_json(
    infer_dependencies_v4(facts, [busy], max_inference_checks=2).unwrap(),
  )
  assert_eq(v4_test_at(inference, ["hasAdditionalConstraints"]), Json(false))
  assert_eq(v4_test_at(inference, ["execution", "limited"]), Json(true))
  assert_eq(v4_test_at(inference, ["status"]), Json("unknown"))
}

///|
test "inference modules 09 duplicate identities and invalid limits fail closed" {
  let facts = im_facts()
  let first = im_empty("duplicate")
  assert_true(infer_dependencies_v4(facts, [first, first]) is Err(_))
  assert_true(
    infer_dependencies_v4(facts, [], max_inference_checks=-1) is Err(_),
  )
  assert_true(
    infer_dependencies_v4(facts, [], max_inference_checks=1000001) is Err(_),
  )
  assert_true(
    inference_module_v4("", "valid", fn(_, _, _) {
      Ok({ data_edges: [], order_edges: [], gaps: [], })
    })
    is Err(_),
  )
}

///|
test "inference modules 10 missing edge provenance cannot become a witness" {
  let facts = im_independent()
  let missing = inference_module_v4("missing-provenance", "unproved/v1", fn(
    _,
    _,
    _,
  ) {
    Ok({
      data_edges: [
        { id: "a", from: "A", to: "B", kind: ScopedWWItem, sources: [], },
        { id: "b", from: "B", to: "A", kind: ScopedWWItem, sources: [], },
      ],
      order_edges: [],
      gaps: [],
    })
  }).unwrap()
  assert_eq(
    v4_test_at(im_report(facts, [missing]), ["status"]),
    Json("unknown"),
  )
}

///|
test "inference modules 11 invalid module output is atomic even if another projection could hide the invalid edge" {
  let facts = im_independent()
  let invalid = inference_module_v4("invalid-constraints", "invalid/v1", fn(
    _,
    _,
    _,
  ) {
    Ok({
      data_edges: [
        {
          id: "a",
          from: "A",
          to: "B",
          kind: ScopedWWItem,
          sources: [Json("provided")],
        },
        {
          id: "b",
          from: "B",
          to: "A",
          kind: ScopedWWItem,
          sources: [Json("provided")],
        },
        {
          id: "bad",
          from: "A",
          to: "A",
          kind: ScopedRWItem,
          sources: [Json("provided")],
        },
      ],
      order_edges: [],
      gaps: [],
    })
  }).unwrap()
  assert_eq(
    v4_test_at(im_report(facts, [invalid]), ["status"]),
    Json("unknown"),
  )
}

///|
test "inference modules 12 caller module failures never erase an existing source refutation" {
  let facts = mct_facts(mct_ww_cycle())
  let fail = inference_module_v4("unavailable", "failure/v1", fn(_, _, _) {
    Err("unavailable")
  }).unwrap()
  assert_eq(v4_test_at(im_report(facts, [fail]), ["status"]), Json("refuted"))
}

///|
test "inference modules 13 graph/model/result tampering is independently recomputed" {
  let facts = im_facts()
  let modules = [im_empty("none")]
  let report = im_report(facts, modules)
  object_fields_unchecked_v3(report)["status"] = Json("refuted")
  assert_false(
    verify_with_inference_v4(facts, report, modules, options=im_options()),
  )
  let changed = im_report(facts, modules)
  object_fields_unchecked_v3(changed)["semanticContract"] = Json(
    "other-contract",
  )
  assert_false(
    verify_with_inference_v4(facts, changed, modules, options=im_options()),
  )
}

///|
test "inference modules 14 original model budget is independent of inference budget" {
  let facts = im_facts()
  let modules = [im_empty("no-extra-claims")]
  let options = model_options_v4(
    models=[ElleSnapshotIsolation],
    max_source_checks=0,
  ).unwrap()
  let r = inference_classification_v4_json(
    classify_with_inference_v4(facts, modules, options~).unwrap(),
  )
  assert_eq(v4_test_at(r, ["status"]), Json("unknown"))
  assert_true(verify_with_inference_v4(facts, r, modules, options~))
}

///|
test "inference modules 15 order module does not infer logical membership from connections" {
  let facts = im_facts()
  let modules = [builtin_inference_module_v4(InferenceDeclaredOrders)]
  assert_eq(
    v4_test_at(im_report(facts, modules), ["status"]),
    Json("checked-compatible"),
  )
  let run = inference_v4_json(infer_dependencies_v4(facts, modules).unwrap())
  assert_eq(capture_source_array_v4(v4_test_at(run, ["modules"])).length(), 1)
}

///|
test "inference modules 16 list module does not silently reinterpret another datatype" {
  let facts = im_facts()
  let r = im_report(facts, [builtin_inference_module_v4(InferenceListPrefixes)])
  assert_eq(v4_test_at(r, ["status"]), Json("unknown"))
  assert_eq(
    v4_test_at(r, ["inference", "moduleCompletenessCanAuthorizeModels"]),
    Json(false),
  )
}

///|
test "inference modules 17 callbacks never consume another module's newly inferred constraints" {
  let facts = im_independent()
  let observer = inference_module_v4("same-original-index", "observe/v1", fn(
    view,
    _,
    _,
  ) {
    if !view.data_edges().is_empty() {
      Err("The original index was changed by another callback")
    } else {
      Ok({ data_edges: [], order_edges: [], gaps: [], })
    }
  }).unwrap()
  let result = inference_v4_json(
    infer_dependencies_v4(facts, [im_constraint("extra", "A", "B"), observer]).unwrap(),
  )
  assert_eq(v4_test_at(result, ["status"]), Json("executed"))
}

///|
test "inference modules 18 list prefix source uses the independently selected list profile" {
  let history = mlp_history(mlp_multi())
  let facts = model_facts_v4(history).unwrap()
  let options = model_options_v4(
    models=[ElleSerializable],
    list_profile=ModelListPrefixStates,
  ).unwrap()
  let modules = [
    builtin_inference_module_v4(InferenceListPrefixes),
    builtin_inference_module_v4(InferenceReadSources),
  ]
  let result = inference_classification_v4_json(
    classify_with_inference_v4(facts, modules, options~).unwrap(),
  )
  assert_eq(v4_test_at(result, ["status"]), Json("checked-compatible"))
  assert_true(verify_with_inference_v4(facts, result, modules, options~))
}

///|
test "inference modules 19 atomic row sources stay in the original row model" {
  let history = rcl_history(rmp_one())
  let facts = model_facts_v4(history).unwrap()
  let options = model_options_v4(
    models=[ElleSerializable],
    relation_profile=ModelRelationAtomicRows,
  ).unwrap()
  let modules = [
    builtin_inference_module_v4(InferenceReadSources),
    builtin_inference_module_v4(InferenceGivenVersions),
  ]
  let result = inference_classification_v4_json(
    classify_with_inference_v4(facts, modules, options~).unwrap(),
  )
  assert_eq(v4_test_at(result, ["status"]), Json("checked-compatible"))
  assert_eq(
    v4_test_at(result, ["baseClassification", "sourceProfile"]),
    Json("captured-relation-row-slots/v1"),
  )
}

///|
test "inference modules 20 exact inference budget boundary counts attempted work" {
  let facts = im_facts()
  let modules = [im_empty("only-invocation")]
  let result = im_report(facts, modules, maximum=1)
  assert_eq(v4_test_at(result, ["status"]), Json("checked-compatible"))
  assert_eq(v4_test_at(result, ["inference", "execution", "checks"]), Json(1))
  assert_eq(
    v4_test_at(result, ["inference", "execution", "limited"]),
    Json(false),
  )
}

///|
test "inference modules 21 valid maximum-length edge IDs survive module namespacing" {
  let long = String::make(256, 'e')
  let custom = inference_module_v4("long-identities", "identity/v1", fn(
    _,
    _,
    _,
  ) {
    Ok({
      data_edges: [
        {
          id: long,
          from: "A",
          to: "B",
          kind: ScopedWWItem,
          sources: [Json("declared")],
        },
      ],
      order_edges: [],
      gaps: [],
    })
  }).unwrap()
  let result = inference_v4_json(
    infer_dependencies_v4(im_independent(), [custom]).unwrap(),
  )
  assert_eq(v4_test_at(result, ["status"]), Json("executed"))
}

///|
test "inference modules 22 duplicate edge identities within one module are rejected atomically" {
  let custom = inference_module_v4("duplicates", "identity/v1", fn(_, _, _) {
    Ok({
      data_edges: [
        {
          id: "same",
          from: "A",
          to: "B",
          kind: ScopedWWItem,
          sources: [Json("declared")],
        },
        {
          id: "same",
          from: "B",
          to: "A",
          kind: ScopedWWItem,
          sources: [Json("declared")],
        },
      ],
      order_edges: [],
      gaps: [],
    })
  }).unwrap()
  assert_eq(
    v4_test_at(im_report(im_independent(), [custom]), ["status"]),
    Json("unknown"),
  )
}

///|
test "inference modules 23 callback mutations cannot replace the caller module policy during an invocation" {
  let registrations : Array[InferenceModuleV4] = []
  let mutate = inference_module_v4("mutator", "registry-mutation/v1", fn(
    _,
    _,
    _,
  ) {
    registrations.clear()
    Ok({ data_edges: [], order_edges: [], gaps: [], })
  }).unwrap()
  let required = im_empty("required-second-module")
  registrations.push(mutate)
  registrations.push(required)
  let facts = im_facts()
  let report = im_report(facts, registrations)
  assert_true(registrations.is_empty())
  assert_eq(
    capture_source_array_v4(v4_test_at(report, ["inference", "modules"])).length(),
    2,
  )
  assert_eq(
    capture_source_array_v4(
      v4_test_at(report, ["inference", "execution", "modules"]),
    ).length(),
    2,
  )
  assert_true(
    verify_with_inference_v4(
      facts,
      report,
      [mutate, required],
      options=im_options(),
    ),
  )
  assert_false(
    verify_with_inference_v4(facts, report, registrations, options=im_options()),
  )
}

///|
test "inference modules 24 algorithm revisions are independent verifier policy" {
  let run = fn(_, _, _) { Ok({ data_edges: [], order_edges: [], gaps: [], }) }
  let first = inference_module_v4(
    "same-module",
    "same-contract/v1",
    run,
    algorithm=Some("implementation-1"),
  ).unwrap()
  let changed = inference_module_v4(
    "same-module",
    "same-contract/v1",
    run,
    algorithm=Some("implementation-2"),
  ).unwrap()
  let facts = im_facts()
  let report = im_report(facts, [first])
  assert_false(
    verify_with_inference_v4(facts, report, [changed], options=im_options()),
  )
}

///|
test "inference modules 25 verifier reruns actual local code rather than accepting matching module labels" {
  let facts = im_independent()
  let first = im_constraint("same-module", "A", "B")
  let changed = im_constraint("same-module", "B", "A")
  let report = im_report(facts, [first])
  assert_false(
    verify_with_inference_v4(facts, report, [changed], options=im_options()),
  )
}

///|
test "inference modules 26 added cycles respect independent model state and edge budgets" {
  let facts = im_independent()
  let modules = [
    im_constraint("extra-A-B", "A", "B"),
    im_constraint("extra-B-A", "B", "A"),
  ]
  for
    options in [
      model_options_v4(models=[ElleSerializable], max_states=0).unwrap(),
      model_options_v4(models=[ElleSerializable], max_edge_checks=0).unwrap(),
    ] {
    let report = inference_classification_v4_json(
      classify_with_inference_v4(facts, modules, options~).unwrap(),
    )
    assert_eq(v4_test_at(report, ["status"]), Json("unknown"))
    let model = capture_source_array_v4(v4_test_at(report, ["models"]))[0]
    assert_true(
      capture_source_array_v4(v4_test_at(model, ["conditionalRefutations"])).is_empty(),
    )
    assert_true(verify_with_inference_v4(facts, report, modules, options~))
    assert_false(
      verify_with_inference_v4(facts, report, modules, options=im_options()),
    )
  }
}

///|
test "inference modules 27 exhausted module work cannot erase an independently proved base refutation" {
  let facts = mct_facts(mct_ww_cycle())
  let modules = [im_empty("skipped-by-budget")]
  let report = im_report(facts, modules, maximum=0)
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
  assert_eq(v4_test_at(report, ["inference", "status"]), Json("unknown"))
  assert_true(
    verify_with_inference_v4(
      facts,
      report,
      modules,
      options=im_options(),
      max_inference_checks=0,
    ),
  )
}

///|
test "inference modules 28 a stronger auxiliary graph cannot falsely refute SI or consistent-view" {
  let facts = im_independent()
  let custom = inference_module_v4("adjacent-rw", "caller-rw/v1", fn(_, _, _) {
    Ok({
      data_edges: [
        {
          id: "rw-a",
          from: "A",
          to: "B",
          kind: ScopedRWItem,
          sources: [Json("caller-bound-source")],
        },
        {
          id: "rw-b",
          from: "B",
          to: "A",
          kind: ScopedRWItem,
          sources: [Json("caller-bound-source")],
        },
      ],
      order_edges: [],
      gaps: [],
    })
  }).unwrap()
  let options = model_options_v4(models=[
    ElleSnapshotIsolation,
    ElleConsistentView,
    ElleRepeatableRead,
    ElleSerializable,
  ]).unwrap()
  let report = inference_classification_v4_json(
    classify_with_inference_v4(facts, [custom], options~).unwrap(),
  )
  let models = capture_source_array_v4(v4_test_at(report, ["models"]))
  for position in 0..<2 {
    assert_eq(v4_test_at(models[position], ["status"]), Json("unknown"))
    assert_true(
      capture_source_array_v4(
        v4_test_at(models[position], ["conditionalRefutations"]),
      ).is_empty(),
    )
  }
  for position in 2..<4 {
    assert_eq(v4_test_at(models[position], ["status"]), Json("refuted"))
  }
  assert_true(verify_with_inference_v4(facts, report, [custom], options~))
}
