///|
/// Cooperative work counter for trusted local inference code. This is not a
/// wall-clock sandbox for arbitrary callbacks.
pub struct InferenceBudgetV4 {
  priv maximum : Int32
  priv mut checks : Int32
  priv mut limited : Bool
}

///|
pub fn InferenceBudgetV4::charge(self : InferenceBudgetV4) -> Bool {
  if self.checks >= self.maximum {
    self.limited = true
    false
  } else {
    self.checks += 1
    true
  }
}

///|
pub fn InferenceBudgetV4::remaining(self : InferenceBudgetV4) -> Int32 {
  self.maximum - self.checks
}

///|
/// A validated source index shared by the modules in one invocation. Public
/// accessors return detached containers, never mutable core index storage.
pub struct InferenceViewV4 {
  priv history : HistoryV4
  priv source : ModelSourceV4
  priv orders : ModelOrdersV4
}

///|
pub fn InferenceViewV4::data_model(self : InferenceViewV4) -> DataModelV4 {
  self.history.data_model
}

///|
pub fn InferenceViewV4::history_json(self : InferenceViewV4) -> Json {
  history_v4_json(self.history)
}

///|
pub fn InferenceViewV4::nodes(self : InferenceViewV4) -> Array[String] {
  self.source.nodes.copy()
}

///|
fn inference_data_copy_v4(
  edge : ScopedDataEdgeInputV4,
) -> ScopedDataEdgeInputV4 {
  { ..edge, sources: edge.sources.map(v4_json_copy), }
}

///|
fn inference_order_copy_v4(
  edge : ScopedOrderEdgeInputV4,
) -> ScopedOrderEdgeInputV4 {
  {
    ..edge,
    from_source: {
      ..edge.from_source,
      observation: v4_json_copy(edge.from_source.observation),
    },
    to_source: {
      ..edge.to_source,
      observation: v4_json_copy(edge.to_source.observation),
    },
  }
}

///|
pub fn InferenceViewV4::data_edges(
  self : InferenceViewV4,
) -> Array[ScopedDataEdgeInputV4] {
  self.source.edges.map(inference_data_copy_v4)
}

///|
pub fn InferenceViewV4::order_edges(
  self : InferenceViewV4,
) -> Array[ScopedOrderEdgeInputV4] {
  self.orders.edges.map(inference_order_copy_v4)
}

///|
/// Modules contribute constraints, not precomputed model statuses or permission
/// to claim source completeness.
pub(all) struct InferenceContributionV4 {
  data_edges : Array[ScopedDataEdgeInputV4]
  order_edges : Array[ScopedOrderEdgeInputV4]
  gaps : Array[Json]
}

///|
pub struct InferenceModuleV4 {
  priv id : String
  priv semantic_contract : String
  priv algorithm : String
  priv parameters : Json
  priv run : (InferenceViewV4, Json, InferenceBudgetV4) -> Result[
    InferenceContributionV4,
    String,
  ]
}

///|
pub fn inference_module_v4(
  id : String,
  semantic_contract : String,
  run : (InferenceViewV4, Json, InferenceBudgetV4) -> Result[
    InferenceContributionV4,
    String,
  ],
  parameters~ : Json = {},
  algorithm~ : String? = None,
) -> Result[InferenceModuleV4, String] {
  let algorithm = match algorithm {
    Some(value) => value
    None => semantic_contract
  }
  if !scoped_name_valid_v4(id) ||
    !scoped_name_valid_v4(semantic_contract) ||
    !scoped_name_valid_v4(algorithm) {
    return Err(
      "Module identity, semantic contract and algorithm must be nonempty scalar strings of at most 256 units",
    )
  }
  try {
    let _ = guarded_json(parameters.stringify(), limit=8192)
    Ok({
      id,
      semantic_contract,
      algorithm,
      parameters: v4_json_copy(parameters),
      run,
    })
  } catch {
    _ => Err("Module parameters exceed the 8192-byte JSON boundary")
  }
}

///|
pub(all) enum BuiltinInferenceModuleV4 {
  InferenceReadSources
  InferenceGivenVersions
  InferenceListPrefixes
  InferenceDeclaredOrders
} derive(Eq)

///|
pub extend BuiltinInferenceModuleV4 with Eq::{equal, not_equal}

///|
pub fn builtin_inference_module_v4(
  kind : BuiltinInferenceModuleV4,
) -> InferenceModuleV4 {
  let id = match kind {
    InferenceReadSources => "original-read-sources/v1"
    InferenceGivenVersions => "original-version-constraints/v1"
    InferenceListPrefixes => "observed-list-prefixes/v1"
    InferenceDeclaredOrders => "declared-transaction-orders/v1"
  }
  inference_module_v4(id, id, fn(view, _parameters, budget) {
    if kind == InferenceListPrefixes && view.history.data_model != AppendListV4 {
      return Err("The list-prefix module requires append-list-v1")
    }
    let data : Array[ScopedDataEdgeInputV4] = []
    let orders : Array[ScopedOrderEdgeInputV4] = []
    if kind == InferenceDeclaredOrders {
      for edge in view.orders.edges {
        if !budget.charge() {
          break
        }
        orders.push(inference_order_copy_v4(edge))
      }
    } else {
      for edge in view.source.edges {
        if !budget.charge() {
          break
        }
        let keep = match kind {
          InferenceReadSources =>
            edge.kind == ScopedWRItem || edge.kind == ScopedWRPredicate
          InferenceGivenVersions =>
            edge.kind != ScopedWRItem && edge.kind != ScopedWRPredicate
          InferenceListPrefixes => true
          InferenceDeclaredOrders => false
        }
        if keep {
          data.push(inference_data_copy_v4(edge))
        }
      }
    }
    Ok({ data_edges: data, order_edges: orders, gaps: [], })
  }).unwrap()
}

///|
pub struct InferenceV4 {
  priv record : Json
  priv source : ModelSourceV4
  priv orders : ModelOrdersV4
  priv complete : Bool
  priv has_new_constraints : Bool
}

///|
pub struct InferenceClassificationV4 {
  priv record : Json
}

///|
fn inference_module_identity_v4(registered : InferenceModuleV4) -> Json {
  {
    "id": Json(registered.id),
    "semanticContract": Json(registered.semantic_contract),
    "algorithm": Json(registered.algorithm),
    "parameters": v4_json_copy(registered.parameters),
    "parametersSha256": Json(model_digest_v4(registered.parameters)),
  }
}

///|
fn inference_output_ids_valid_v4(output : InferenceContributionV4) -> Bool {
  let seen : Map[String, Bool] = Map([])
  for edge in output.data_edges {
    if !scoped_name_valid_v4(edge.id) || seen.contains(edge.id) {
      return false
    }
    seen[edge.id] = true
  }
  for edge in output.order_edges {
    if !scoped_name_valid_v4(edge.id) || seen.contains(edge.id) {
      return false
    }
    seen[edge.id] = true
  }
  true
}

///|
fn inference_policy_v4(
  modules : Array[InferenceModuleV4],
  max_inference_checks : Int32,
) -> Result[Unit, String] {
  if modules.length() > 16 ||
    max_inference_checks < 0 ||
    max_inference_checks > 1000000 {
    return Err(
      "Inference supports at most 16 modules and 0..1000000 shared checks",
    )
  }
  let identities : Map[String, Bool] = Map([])
  for registered in modules {
    if identities.contains(registered.id) {
      return Err("Duplicate inference module identity")
    }
    identities[registered.id] = true
  }
  Ok(())
}

///|
/// Every callback sees the same original index. No module output is fed into
/// another callback. Output and invocation work is always charged by the core.
pub fn infer_dependencies_v4(
  facts : ModelFactsV4,
  modules : Array[InferenceModuleV4],
  options~ : ModelOptionsV4 = model_options_v4().unwrap(),
  max_inference_checks~ : Int32 = 1000000,
) -> Result[InferenceV4, String] {
  // Freeze caller policy before invoking any registered local code.
  let modules = modules.copy()
  match inference_policy_v4(modules, max_inference_checks) {
    Err(reason) => return Err(reason)
    Ok(_) => ()
  }
  infer_dependencies_from_index_v4(
    facts,
    modules,
    options,
    max_inference_checks,
    model_original_index_v4(facts, options),
  )
}

///|
fn infer_dependencies_from_index_v4(
  facts : ModelFactsV4,
  modules : Array[InferenceModuleV4],
  options : ModelOptionsV4,
  max_inference_checks : Int32,
  original : ModelOriginalIndexV4,
) -> Result[InferenceV4, String] {
  let source = original.source
  let orders = original.orders
  let view : InferenceViewV4 = { history: facts.history, source, orders, }
  let known_data : Map[(String, String, String), Bool] = Map([])
  let original_data : Map[String, ScopedDataEdgeInputV4] = Map([])
  let known_orders : Map[(String, String, String, String), Bool] = Map([])
  let original_orders : Map[String, ScopedOrderEdgeInputV4] = Map([])
  for edge in source.edges {
    known_data[(edge.from, edge.to, scoped_data_name_v4(edge.kind))] = true
    original_data[edge.id] = edge
  }
  for edge in orders.edges {
    known_orders[(
      edge.from,
      edge.to,
      scoped_order_name_v4(edge.kind),
      edge.context_id,
    )] = true
    original_orders[edge.id] = edge
  }
  let budget : InferenceBudgetV4 = {
    maximum: max_inference_checks,
    checks: 0,
    limited: false,
  }
  let data = source.edges.map(inference_data_copy_v4)
  let order_edges = orders.edges.map(inference_order_copy_v4)
  let gaps : Array[Json] = []
  let runs : Array[Json] = []
  let mut new_constraints = false
  for registered in modules {
    let start = budget.checks
    let start_data = data.length()
    let start_orders = order_edges.length()
    let identity = inference_module_identity_v4(registered)
    if budget.limited || !budget.charge() {
      gaps.push({
        "code": "inference-module-budget",
        "module": Json(registered.id),
      })
      runs.push({
        "module": identity,
        "status": "unknown",
        "checks": 0,
        "reason": "shared-inference-budget",
      })
      continue
    }
    match (registered.run)(view, v4_json_copy(registered.parameters), budget) {
      Err(reason) => {
        gaps.push({
          "code": "inference-module-error",
          "module": Json(registered.id),
          "message": Json(reason),
        })
        runs.push({
          "module": identity,
          "status": "unknown",
          "checks": Json(budget.checks - start),
          "reason": Json(reason),
        })
      }
      Ok(contribution) => {
        // Do not accept a giant callback vector and only discover its size after
        // copying it. A failed module is atomic: none of its constraints survive.
        if contribution.data_edges.length() + contribution.order_edges.length() >
          50000 ||
          contribution.gaps.length() > 4096 {
          gaps.push({
            "code": "inference-module-capacity",
            "module": Json(registered.id),
          })
          runs.push({
            "module": identity,
            "status": "unknown",
            "checks": Json(budget.checks - start),
            "reason": "module-output-capacity",
          })
          continue
        }
        if !inference_output_ids_valid_v4(contribution) {
          gaps.push({
            "code": "inference-module-edge-identity",
            "module": Json(registered.id),
          })
          runs.push({
            "module": identity,
            "status": "unknown",
            "checks": Json(budget.checks - start),
            "reason": "invalid-original-edge-identity",
          })
          continue
        }
        let pending_data : Array[ScopedDataEdgeInputV4] = []
        let pending_order : Array[ScopedOrderEdgeInputV4] = []
        let mut module_new = false
        for edge in contribution.data_edges {
          if !budget.charge() {
            break
          }
          if !known_data.contains(
              (edge.from, edge.to, scoped_data_name_v4(edge.kind)),
            ) {
            module_new = true
          }
          match original_data.get(edge.id) {
            Some(original) if original.from == edge.from &&
              original.to == edge.to &&
              original.kind == edge.kind &&
              Json(original.sources) == Json(edge.sources) => continue
            _ => ()
          }
          pending_data.push({
            ..inference_data_copy_v4(edge),
            id: "module-" +
            runs.length().to_string() +
            "-" +
            v3_dislock_sha256(edge.id),
          })
        }
        for edge in contribution.order_edges {
          if !budget.charge() {
            break
          }
          if !known_orders.contains(
              (
                edge.from,
                edge.to,
                scoped_order_name_v4(edge.kind),
                edge.context_id,
              ),
            ) {
            module_new = true
          }
          match original_orders.get(edge.id) {
            Some(original) if original.from == edge.from &&
              original.to == edge.to &&
              original.kind == edge.kind &&
              original.context_id == edge.context_id &&
              original.from_source.transaction == edge.from_source.transaction &&
              original.to_source.transaction == edge.to_source.transaction &&
              original.from_source.observation == edge.from_source.observation &&
              original.to_source.observation == edge.to_source.observation =>
              continue
            _ => ()
          }
          pending_order.push({
            ..inference_order_copy_v4(edge),
            id: "module-" +
            runs.length().to_string() +
            "-" +
            v3_dislock_sha256(edge.id),
          })
        }
        let contribution_valid = !budget.limited &&
          data.length() +
          order_edges.length() +
          pending_data.length() +
          pending_order.length() <=
          50000 &&
          scoped_dependency_graph_v4(
            source.nodes,
            pending_data,
            order_edges=pending_order,
            data_complete=false,
          )
          is Ok(_)
        if budget.limited {
          gaps.push({
            "code": "inference-module-budget",
            "module": Json(registered.id),
          })
        } else if !contribution_valid {
          gaps.push({
            "code": "inference-module-invalid-constraints",
            "module": Json(registered.id),
          })
        } else {
          for edge in pending_data {
            data.push(edge)
          }
          for edge in pending_order {
            order_edges.push(edge)
          }
          for gap in contribution.gaps {
            gaps.push({
              "module": Json(registered.id),
              "gap": v4_json_copy(gap),
            })
          }
          new_constraints = new_constraints || module_new
        }
        runs.push({
          "module": identity,
          "status": if budget.limited || !contribution_valid {
            "unknown"
          } else {
            "executed"
          },
          "checks": Json(budget.checks - start),
          "dataEdges": Json(data.length() - start_data),
          "orderEdges": Json(order_edges.length() - start_orders),
          "atomicOnBudgetExhaustion": true,
          "originalDataEdgeIds": Json(
            contribution.data_edges.map(edge => edge.id),
          ),
          "originalOrderEdgeIds": Json(
            contribution.order_edges.map(edge => edge.id),
          ),
        })
      }
    }
  }
  let graph = scoped_dependency_graph_v4(
    source.nodes,
    data,
    order_edges~,
    data_complete=false,
    process_complete=false,
    realtime_complete=false,
  )
  let graph_record = match graph {
    Ok(g) => {
      let r = scoped_dependency_graph_v4_json(g)
      for gap in g.data_gaps {
        gaps.push(v4_json_copy(gap))
      }
      for gap in g.process_gaps {
        gaps.push(v4_json_copy(gap))
      }
      for gap in g.realtime_gaps {
        gaps.push(v4_json_copy(gap))
      }
      r
    }
    Err(reason) => {
      gaps.push({ "code": "inference-graph-invalid", "message": Json(reason) })
      Json::null()
    }
  }
  let complete = gaps.is_empty() && !budget.limited
  let record : Json = {
    "format": "moontxnwitness-inference/v4",
    "schemaVersion": 4,
    "semanticContract": "registered-source-inference-modules/v1",
    "algorithm": "same-original-index-single-pass-modules-1",
    "sourceSha256": Json(facts.source_sha256),
    "sourceDigestContract": "sorted-json-object-keys-v1",
    "observations": v4_json_copy(facts.source_record),
    "modules": Json(modules.map(inference_module_identity_v4)),
    "sourceOptions": model_options_record_v4(options),
    "baseSourceCoverage": {
      "ww": Json(source.ww_complete),
      "wr": Json(source.wr_complete),
      "rw": Json(source.rw_complete),
      "process": Json(orders.process_complete),
      "realtime": Json(orders.realtime_complete),
      "dataGaps": Json(source.gaps),
      "orderGaps": Json(orders.gaps),
    },
    "status": if complete {
      "executed"
    } else {
      "unknown"
    },
    "hasAdditionalConstraints": Json(new_constraints),
    "sourceAssurance": "conditional on caller-trusted deterministic registered module code; references are bound, not authenticated",
    "moduleCompletenessCanAuthorizeModels": false,
    "graph": graph_record,
    "gaps": Json(gaps),
    "execution": {
      "counterContract": "shared-module-invocations-callback-and-output-checks-1",
      "checks": Json(budget.checks),
      "maxChecks": Json(max_inference_checks),
      "limited": Json(budget.limited),
      "modules": Json(runs),
      "source": source.execution,
      "orders": orders.execution,
      "callbackMetering": "cooperative trusted code; not a wall-clock sandbox",
    },
  }
  Ok({
    record,
    source: {
      ..source,
      edges: data,
      ww_complete: false,
      wr_complete: false,
      rw_complete: false,
    },
    orders: {
      ..orders,
      edges: order_edges,
      process_complete: false,
      realtime_complete: false,
    },
    complete,
    has_new_constraints: new_constraints,
  })
}

///|
pub fn inference_v4_json(inference : InferenceV4) -> Json {
  v4_json_copy(inference.record)
}

///|
// Model evaluation also computes auxiliary graphs for absence arguments. A
// refutation of such a stronger graph is not itself a model refutation: SI and
// consistent-view can admit an adjacent two-RW cycle even though their
// lost-update absence helper inspects I+Ai. Select only forbidden obligations.
fn inference_forbidden_graph_rules_v4(
  models : Array[ElleModelV4],
) -> Map[String, Bool] {
  let forbidden : Map[String, Bool] = Map([])
  let mark = fn(projection, context) {
    forbidden[model_graph_key_v4(projection, context)] = true
  }
  for model in models {
    let projection = model_projection_v4(model)
    let own_context = model_context_v4(model)
    mark("W", ScopedDataOnly)
    mark(projection, own_context)
    if projection != "W" {
      mark("I", ScopedDataOnly)
    }
    if projection == "Ext(I,A)" || projection == "D" {
      mark("Ext(I,A)", own_context)
    }
    for token in model_literal_obligations_v4(model) {
      let context = model_context_for_token_v4(token)
      match token {
        "G0" | "G0-process" | "G0-realtime" | "PL-1-cycle-exists" =>
          mark("W", context)
        "G1"
        | "G1-process"
        | "G1-realtime"
        | "G1c"
        | "G1c-process"
        | "G1c-realtime"
        | "PL-2-cycle-exists" => mark("I", context)
        "G2-item" | "PL-2.99-cycle-exists" => mark("I+Ai", ScopedDataOnly)
        "G2" | "G2-process" | "G2-realtime" | "PL-3-cycle-exists" =>
          mark("D", context)
        "G-single" => mark("G-single", ScopedDataOnly)
        "G-nonadjacent" | "G-nonadjacent-process" | "G-nonadjacent-realtime" =>
          mark("G-nonadjacent", context)
        "PL-SI-cycle-exists" => mark("Ext(I,A)", ScopedDataOnly)
        "PL-SS-cycle-exists" => mark("D", ScopedWithRealtime)
        "strong-session-PL-1-cycle-exists" => mark("W", ScopedWithProcess)
        "strong-PL-1-cycle-exists" => mark("W", ScopedWithRealtime)
        "strong-session-PL-2-cycle-exists" => mark("I", ScopedWithProcess)
        "strong-PL-2-cycle-exists" => mark("I", ScopedWithRealtime)
        "strong-session-serializable-cycle-exists" =>
          mark("D", ScopedWithProcess)
        "strong-session-snapshot-isolation-cycle-exists" =>
          mark("Ext(I,A)", ScopedWithProcess)
        "strong-snapshot-isolation-cycle-exists" =>
          mark("Ext(I,A)", ScopedWithRealtime)
        _ => ()
      }
    }
  }
  forbidden
}

///|
/// Base compatibility is retained only for replayed, already-proved graph
/// constraints. New constraints require a separate completion certificate;
/// until then the extension route can refute or remain unknown.
pub fn classify_with_inference_v4(
  facts : ModelFactsV4,
  modules : Array[InferenceModuleV4],
  options~ : ModelOptionsV4 = model_options_v4().unwrap(),
  max_inference_checks~ : Int32 = 1000000,
) -> Result[InferenceClassificationV4, String] {
  // Preserve independently validated original facts for the base completion.
  // Module constraints only enter the separate extended graph below.
  let modules = modules.copy()
  match inference_policy_v4(modules, max_inference_checks) {
    Err(reason) => return Err(reason)
    Ok(_) => ()
  }
  let original = model_original_index_v4(facts, options)
  let inference = match
    infer_dependencies_from_index_v4(
      facts, modules, options, max_inference_checks, original,
    ) {
    Ok(value) => value
    Err(reason) => return Err(reason)
  }
  let base = classify_models_from_index_v4(facts, options, original).record
  let base_models = capture_source_array_v4(
    object_fields_unchecked_v3(base).at("models"),
  )
  let rules : Array[ModelRuleV4] = []
  let needed = inference_forbidden_graph_rules_v4(options.models)
  for context in [ScopedDataOnly, ScopedWithProcess, ScopedWithRealtime] {
    for
      projection in [
        "W", "I", "I+Ai", "D", "G-single", "G-nonadjacent", "Ext(I,A)",
      ] {
      let id = model_graph_key_v4(projection, context)
      if needed.contains(id) {
        rules.push(
          model_graph_rule_v4(
            inference.source,
            inference.orders,
            projection,
            context,
            options,
          ),
        )
      }
    }
  }
  let models : Array[Json] = []
  for model in options.models {
    let name = model_name_v4(model)
    let original = base_models.filter(raw => {
        object_fields_unchecked_v3(raw).at("model") == Json(name)
      })[0]
    let base_status = object_fields_unchecked_v3(original).at("status")
    let own_needed = inference_forbidden_graph_rules_v4([model])
    let witnesses = rules.filter(rule => {
      own_needed.contains(rule.id) && rule.status == "refuted"
    })
    let status = if base_status == Json("refuted") || !witnesses.is_empty() {
      "refuted"
    } else if base_status == Json("checked-compatible") &&
      inference.complete &&
      !inference.has_new_constraints {
      "checked-compatible"
    } else {
      "unknown"
    }
    models.push({
      "model": Json(name),
      "status": Json(status),
      "baseStatus": base_status,
      "conditionalRefutations": Json(witnesses.map(model_rule_json_v4)),
      "additionalConstraintCompletionImplemented": false,
    })
  }
  let status = if models.any(r => {
      object_fields_unchecked_v3(r).at("status") == Json("refuted")
    }) {
    "refuted"
  } else if models.all(r => {
      object_fields_unchecked_v3(r).at("status") == Json("checked-compatible")
    }) {
    "checked-compatible"
  } else {
    "unknown"
  }
  Ok({
    record: {
      "format": "moontxnwitness-model-inference-composition/v4",
      "schemaVersion": 4,
      "semanticContract": "registered-inference-and-model-refutations/v1",
      "algorithm": "base-models-and-conditional-module-refutations-1",
      "status": Json(status),
      "sourceSha256": Json(facts.source_sha256),
      "sourceDigestContract": "sorted-json-object-keys-v1",
      "options": model_options_record_v4(options),
      "inference": inference.record,
      "baseClassification": base,
      "models": Json(models),
      "sourceAssurance": "original core source checks plus caller-trusted registered inference code; no automatic new-constraint completion",
    },
  })
}

///|
pub fn inference_classification_v4_json(
  value : InferenceClassificationV4,
) -> Json {
  v4_json_copy(value.record)
}

///|
pub fn verify_with_inference_v4(
  facts : ModelFactsV4,
  supplied : Json,
  modules : Array[InferenceModuleV4],
  options~ : ModelOptionsV4 = model_options_v4().unwrap(),
  max_inference_checks~ : Int32 = 1000000,
) -> Bool {
  match
    classify_with_inference_v4(facts, modules, options~, max_inference_checks~) {
    Ok(actual) => supplied == actual.record
    Err(_) => false
  }
}
