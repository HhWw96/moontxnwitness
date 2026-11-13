///|
/// Predicate-model namespace; does not change fixed-Elle point-row semantics.
pub struct RelationModelClassificationV4 {
  priv record : Json
}

///|
priv enum RmModeV4 {
  RmSerial
  RmSnapshot
  RmCommittedQueries
} derive(Eq)

///|
priv struct RmSearchV4 {
  ctx : RelationV3Search
  snapshots : Array[Array[Int32]]
  order : Array[Int32]
  required : Array[(String, String)]
  mode : RmModeV4
}

///|
fn rm_mode_v4(mode : RmModeV4) -> String {
  match mode {
    RmSerial => "original-serial"
    RmSnapshot => "original-fixed-snapshot"
    RmCommittedQueries => "original-committed-query-prefixes"
  }
}

///|
fn rm_state_v4(ctx : RelationV3Search) -> Bool {
  if ctx.states >= ctx.options.max_states {
    ctx.limited = true
    ctx.reason = "state_budget"
    false
  } else {
    ctx.states += 1
    true
  }
}

///|
fn rm_execute_v4(
  ctx : RelationV3Search,
  state : Array[Int32],
  program : RelationV3Program,
) -> Bool {
  let run : RelationV3Search = { ..ctx, state, trail: [], blockers: [], }
  let valid = relation_v3_execute(run, program)
  ctx.operations = run.operations
  if run.limited {
    ctx.limited = true
    ctx.reason = run.reason
  }
  valid
}

///|
fn rm_replay_queries_v4(
  search : RmSearchV4,
  program : RelationV3Program,
  position : Int32,
  minimum : Int32,
) -> Json? {
  let ctx = search.ctx
  let own : Map[Int32, Int32] = Map([])
  let marks : Array[(String, Map[Int32, Int32])] = []
  let prefixes : Array[Json] = []
  let mut last_prefix = minimum
  for ai, action in program.actions {
    if !relation_v3_budget(ctx) {
      return None
    }
    match action {
      Mark(id) => marks.push((id, own.copy()))
      Undo(id) | Release(id) => {
        let mut found = -1
        for i, mark in marks {
          if mark.0 == id {
            found = i
          }
        }
        if found < 0 {
          return None
        }
        if action is Undo(_) {
          own.clear()
          for k, v in marks[found].1 {
            own[k] = v
          }
        }
        let keep = if action is Undo(_) { found + 1 } else { found }
        while marks.length() > keep {
          ignore(marks.pop())
        }
      }
      _ => {
        let mut selected = -1
        for prefix in last_prefix..<=position {
          if !rm_state_v4(ctx) {
            return None
          }
          let state = search.snapshots[prefix].copy()
          for key, source in own {
            state[key] = source
          }
          let one : RelationV3Program = { ..program, actions: [action], }
          if rm_execute_v4(ctx, state, one) {
            selected = prefix
            break
          }
          if ctx.limited {
            return None
          }
        }
        if selected < 0 {
          return None
        }
        last_prefix = selected
        prefixes.push({ "actionIndex": Json(ai), "prefix": Json(selected) })
        if action is WriteRow(index) {
          own[ctx.parsed.sources[index].row.key] = index
        }
      }
    }
  }
  Some({ "transaction": Json(program.id), "statementPrefixes": Json(prefixes) })
}

///|
fn rm_candidate_v4(search : RmSearchV4) -> Json? {
  let ctx = search.ctx
  let positions : Map[String, Int32] = Map([])
  for position, index in search.order {
    positions[ctx.programs[index].id] = position
  }
  let certificates : Array[Json] = []
  for position, index in search.order {
    let program = ctx.programs[index]
    let mut minimum = 0
    for (from, to) in search.required {
      if to == program.id {
        minimum = minimum.max(positions.at(from) + 1)
      }
    }
    if minimum > position {
      return None
    }
    if search.mode == RmCommittedQueries {
      match rm_replay_queries_v4(search, program, position, minimum) {
        Some(certificate) => certificates.push(certificate)
        None => return None
      }
      continue
    }
    let first = if search.mode == RmSerial { position } else { minimum }
    let mut selected = -1
    for prefix in first..<=position {
      if !rm_state_v4(ctx) {
        return None
      }
      let state = search.snapshots[prefix].copy()
      if !rm_execute_v4(ctx, state, program) {
        if ctx.limited {
          return None
        }
        continue
      }
      // Snapshot-isolation commits cannot overwrite a key changed after their
      // selected snapshot. Reverted own effects do not enter this write set.
      let mut conflict = false
      if search.mode == RmSnapshot {
        for key in 0..<state.length() {
          if !relation_v3_budget(ctx) {
            return None
          }
          if search.snapshots[position][key] ==
            search.snapshots[position + 1][key] {
            continue
          }
          for earlier in prefix..<position {
            if !relation_v3_budget(ctx) {
              return None
            }
            if search.snapshots[earlier][key] !=
              search.snapshots[earlier + 1][key] {
              conflict = true
            }
          }
        }
      }
      if !conflict {
        selected = prefix
        break
      }
    }
    if selected < 0 {
      return None
    }
    certificates.push({
      "transaction": Json(program.id),
      "snapshotPrefix": Json(selected),
    })
  }
  Some({
    "kind": Json(rm_mode_v4(search.mode)),
    "commitOrder": Json(search.order.map(i => ctx.programs[i].id)),
    "programs": Json(certificates),
    "originalProgramsReplayed": true,
    "writeEffectsValidatedAtCommit": true,
    "inferredSnapshotPromotedToObservation": false,
  })
}

///|
fn rm_search_v4(search : RmSearchV4, selected : Int32) -> Json? {
  let ctx = search.ctx
  if search.order.length() == ctx.programs.length() {
    return rm_candidate_v4(search)
  }
  for i, program in ctx.programs {
    let bit = 1 << i
    if (selected & bit) != 0 {
      continue
    }
    let mut ready = true
    for (from, to) in search.required {
      if to == program.id && !ctx.prefix.contains(from) {
        ready = false
      }
    }
    if !ready {
      continue
    }
    if !rm_state_v4(ctx) {
      return None
    }
    let effects : RelationV3Program = {
      ..program,
      actions: program.actions.filter(action => {
        match action {
          QueryRows(_, _, _, _) => false
          _ => true
        }
      }),
    }
    let mark = ctx.trail.length()
    if relation_v3_execute(ctx, effects) {
      ctx.prefix.push(program.id)
      search.order.push(i)
      search.snapshots.push(ctx.state.copy())
      let candidate = rm_search_v4(search, selected | bit)
      ignore(search.snapshots.pop())
      ignore(search.order.pop())
      ignore(ctx.prefix.pop())
      relation_v3_undo(ctx, mark)
      if candidate is Some(_) {
        return candidate
      }
    } else {
      relation_v3_undo(ctx, mark)
    }
    if ctx.limited {
      return None
    }
  }
  None
}

///|
fn rm_completion_v4(
  parsed : RelationV3Parsed,
  orders : ModelOrdersV4,
  context : ScopedOrderContextV4,
  mode : RmModeV4,
  options : ModelOptionsV4,
) -> ModelRuleV4 {
  let id = "completion/" +
    rm_mode_v4(mode) +
    "/" +
    scoped_context_name_v4(context)
  let programs = parsed.programs.filter(p => p.status == Committed)
  let mut original_actions = 0
  for program in parsed.programs {
    original_actions += program.actions.length()
  }
  let order_complete = match context {
    ScopedDataOnly => true
    ScopedWithProcess => orders.process_complete
    ScopedWithRealtime => orders.realtime_complete
  }
  if programs.length() > 6 ||
    original_actions > 128 ||
    !order_complete ||
    !parsed.findings.is_empty() ||
    object_fields_unchecked_v3(parsed.normalized).at("status") != Json("ready") ||
    parsed.programs.any(p => p.status == Unknown) ||
    options.completion_policy != ModelObservationOnlyCompletion {
    return model_rule_v4(
      id, "pending", "requires a closed original program, confirmed outcomes, selected order facts and the 6 transaction / 128 original-action exact scope including savepoint controls",
    )
  }
  let sorted_keys : Array[Array[Int32]] = parsed.tables.map(_ => [])
  for i, key in parsed.keys {
    sorted_keys[key.table].push(i)
  }
  for keys in sorted_keys {
    keys.sort_by((a, b) => {
      relation_v3_compare(parsed.keys[a].value, parsed.keys[b].value)
    })
  }
  let ctx : RelationV3Search = {
    parsed,
    programs,
    state: parsed.initial.copy(),
    sorted_keys,
    trail: [],
    prefix: [],
    blockers: [],
    options: {
      max_states: options.max_states,
      max_operations: options.max_source_checks,
    },
    states: 0,
    operations: 0,
    limited: false,
    reason: "exhausted",
  }
  let required = orders.edges.filter_map(edge => {
    let keep = match context {
      ScopedDataOnly => false
      ScopedWithProcess => edge.kind == ScopedProcess
      ScopedWithRealtime => edge.kind == ScopedRealtime
    }
    if keep {
      Some((edge.from, edge.to))
    } else {
      None
    }
  })
  let search : RmSearchV4 = {
    ctx,
    snapshots: [parsed.initial.copy()],
    order: [],
    required,
    mode,
  }
  let certificate = rm_search_v4(search, 0)
  model_rule_v4(
    id,
    if certificate is Some(_) {
      "checked-compatible"
    } else {
      "unknown"
    },
    "constructive replay of complete original predicate queries, full row values, write predecessors, own overlays and savepoints; failed stronger completion never refutes a weaker model",
    evidence={
      "certificate": certificate.unwrap_or(Json::null()),
      "complete": Json(!ctx.limited),
      "reason": Json(
        if certificate is Some(_) {
          "constructive-certificate"
        } else {
          ctx.reason
        },
      ),
      "execution": {
        "counterContract": "relation-model-original-program-prefix-search-1",
        "states": Json(ctx.states),
        "operationChecks": Json(ctx.operations),
        "limited": Json(ctx.limited),
        "limits": {
          "states": Json(options.max_states),
          "operationChecks": Json(options.max_source_checks),
        },
      },
    },
  )
}

///|
fn rm_source_rules_v4(
  predicate : RelationPredicateGraphV4,
  maximum : Int32,
) -> Map[String, ModelRuleV4] {
  let index = predicate.index
  let proofs : Map[String, Array[Json]] = Map([
    ("G1a", []),
    ("G1b", []),
    ("internal", []),
  ])
  let budget : ModelSourceBudgetV4 = { maximum, checks: 0, limited: false, }
  let mut complete = predicate.complete
  for query in predicate.queries {
    if index.outcomes.get(query.tx) != Some(Committed) {
      continue
    }
    for row in query.rows {
      if !model_source_charge_v4(budget) {
        complete = false
        break
      }
      match index.versions.get(row.version) {
        Some(si) => {
          let source = index.parsed.sources[si]
          if source.row.key != row.key ||
            source.row.values != row.values ||
            source.action == "delete" {
            complete = false
            continue
          }
          match source.writer {
            Some(writer) if writer != query.tx => {
              let category = if index.outcomes.get(writer) == Some(Aborted) ||
                !index.surviving[si] {
                "G1a"
              } else if index.outcomes.get(writer) == Some(Committed) &&
                !index.final_set[si] {
                "G1b"
              } else {
                ""
              }
              if category != "" {
                proofs
                .at(category)
                .push({
                  "querySeq": Json(query.seq.to_double()),
                  "transaction": Json(query.tx),
                  "source": relation_point_source_json_v4(index, si),
                  "originalQuery": index.originals.get_or_default(
                    query.seq,
                    Json::null(),
                  ),
                })
              }
            }
            _ => ()
          }
        }
        None => complete = false
      }
    }
    for key, si in query.own {
      if index.parsed.keys[key].table != query.table {
        continue
      }
      if !model_source_charge_v4(budget) {
        complete = false
        break
      }
      let source = index.parsed.sources[si]
      let mut expected = source.action != "delete"
      for term in query.predicate {
        if !expected {
          break
        }
        if !model_source_charge_v4(budget) {
          complete = false
          break
        }
        expected = relation_v3_predicate_matches(
          term,
          source.row,
          index.parsed.keys,
        )
      }
      let observed : Array[RelationV3Row] = []
      for row in query.rows {
        if !model_source_charge_v4(budget) {
          complete = false
          break
        }
        if row.key == key {
          observed.push(row)
        }
      }
      if budget.limited {
        break
      }
      let valid = if expected {
        observed.length() == 1 &&
        observed[0].version == source.row.version &&
        observed[0].values == source.row.values
      } else {
        observed.is_empty()
      }
      if !valid && query.complete {
        proofs
        .at("internal")
        .push({
          "querySeq": Json(query.seq.to_double()),
          "transaction": Json(query.tx),
          "activeOwnEffect": relation_point_source_json_v4(index, si),
          "originalQuery": index.originals.get_or_default(
            query.seq,
            Json::null(),
          ),
        })
      }
    }
  }
  let rules : Map[String, ModelRuleV4] = Map([])
  for id in ["G1a", "G1b", "internal"] {
    rules[id] = model_rule_v4(
      id,
      model_source_status_v4(proofs.at(id), complete && !budget.limited),
      "actual complete relation query sources and active own effects; write predecessors are not SELECT observations",
      evidence={
        "findings": Json(proofs.at(id)),
        "execution": model_source_execution_v4(budget),
      },
    )
  }
  rules
}

///|
fn rm_graph_rule_v4(
  predicate : RelationPredicateGraphV4,
  source : ModelSourceV4,
  orders : ModelOrdersV4,
  projection : String,
  context : ScopedOrderContextV4,
  options : ModelOptionsV4,
) -> ModelRuleV4 {
  let original = relation_predicate_scoped_graph_v4(predicate).unwrap()
  let data = if projection == "W" {
    source.edges.filter(edge => {
      edge.kind == ScopedWWItem || edge.kind == ScopedWWPredicate
    })
  } else {
    original.edges.filter_map(edge => {
      match edge.data_kind {
        Some(kind) if model_projection_keep_v4(kind, projection) =>
          Some(
            (
              {
                id: edge.id,
                from: original.nodes[edge.from],
                to: original.nodes[edge.to],
                kind,
                sources: capture_source_array_v4(
                  object_fields_unchecked_v3(edge.original).at("sources"),
                ),
              } : ScopedDataEdgeInputV4),
          )
        _ => None
      }
    })
  }
  let graph = scoped_dependency_graph_v4(
    source.nodes,
    data,
    order_edges=orders.edges,
    data_complete=if projection == "W" {
      source.ww_complete
    } else {
      predicate.complete
    },
    process_complete=orders.process_complete,
    realtime_complete=orders.realtime_complete,
  ).unwrap()
  let result = if projection == "Ext(I,A)" {
    search_si_extension_v4(
      graph,
      rule_set=Adya2000Mixed,
      order_context=context,
      max_states=options.max_states,
      max_edge_checks=options.max_edge_checks,
    )
  } else {
    let category = match projection {
      "W" => ScopedG0
      "I" => ScopedG1c
      "I+Ai" | "D-item-mixed" => ScopedG2Item
      "G-single" => ScopedGSingle
      "G-nonadjacent" => ScopedGNonadjacent
      _ => ScopedG2
    }
    search_scoped_category_v4(
      graph,
      category,
      rule_set=Adya2000Mixed,
      order_context=context,
      max_states=options.max_states,
      max_edge_checks=options.max_edge_checks,
    )
  }
  model_rule_v4(
    model_graph_key_v4(projection, context),
    result.status,
    "independent predicate/item scoped search under the relation definition",
    evidence=result.record,
  )
}

///|
pub fn classify_relation_models_v4(
  facts : ModelFactsV4,
  options : ModelOptionsV4,
  realtime_known~ : Bool = true,
) -> Result[RelationModelClassificationV4, String] {
  let history = facts.history
  let parsed = match history.payload {
    RelationSnapshot(parsed) => parsed
    _ => return Err("relation models require relation-set-v1")
  }
  let predicate = match
    build_relation_predicate_graph_v4(
      history,
      max_graph_checks=options.max_source_checks,
      max_predicate_checks=options.max_source_checks,
      max_candidate_visits=options.max_states,
    ) {
    Ok(value) => value
    Err(reason) => return Err(reason)
  }
  let source = model_other_source_v4(history, options)
  let original_orders = model_orders_v4(
    facts,
    source,
    options.max_source_checks,
  )
  let orders = if !realtime_known ||
    (
      parsed.programs.filter(p => p.status == Committed).length() > 1 &&
      capture_source_string_v4(
        object_fields_unchecked_v3(history.source_document).get_or_default(
          "clockDomain",
          Json::null(),
        ),
      ) ==
      ""
    ) {
    // BEGIN is not a logical snapshot and incomparable clocks do not create RT.
    // Keep data witnesses independently usable.
    {
      ..original_orders,
      realtime_complete: false,
      edges: original_orders.edges.filter(e => e.kind != ScopedRealtime),
    }
  } else {
    original_orders
  }
  let source_rules = rm_source_rules_v4(predicate, options.max_source_checks)
  let graph_rules : Map[String, ModelRuleV4] = Map([])
  let completions : Map[String, ModelRuleV4] = Map([])
  let reports : Array[Json] = []
  for model in options.models {
    let projection = if model == ElleRepeatableRead {
      "D-item-mixed"
    } else {
      model_projection_v4(model)
    }
    let context = model_context_v4(model)
    let key = model_graph_key_v4(projection, context)
    if !graph_rules.contains(key) {
      graph_rules[key] = rm_graph_rule_v4(
        predicate, source, orders, projection, context, options,
      )
    }
    let rules : Array[ModelRuleV4] = [graph_rules.at(key)]
    if projection != "W" {
      let ikey = model_graph_key_v4("I", ScopedDataOnly)
      if !graph_rules.contains(ikey) {
        graph_rules[ikey] = rm_graph_rule_v4(
          predicate,
          source,
          orders,
          "I",
          ScopedDataOnly,
          options,
        )
      }
      rules.push(graph_rules.at(ikey))
      rules.push(source_rules.at("G1a"))
      rules.push(source_rules.at("G1b"))
    }
    if projection != "W" && projection != "I" {
      rules.push(source_rules.at("internal"))
    }
    let mode = if projection == "D" {
      RmSerial
    } else if projection == "Ext(I,A)" {
      RmSnapshot
    } else {
      RmCommittedQueries
    }
    let completion_key = rm_mode_v4(mode) +
      "/" +
      scoped_context_name_v4(context)
    if !completions.contains(completion_key) {
      completions[completion_key] = rm_completion_v4(
        parsed, orders, context, mode, options,
      )
    }
    let completion = completions.at(completion_key)
    let serial_key = rm_mode_v4(RmSerial) +
      "/" +
      scoped_context_name_v4(context)
    if !completions.contains(serial_key) {
      completions[serial_key] = rm_completion_v4(
        parsed,
        orders,
        context,
        RmSerial,
        options,
      )
    }
    let serial_completion = completions.at(serial_key)
    // A constructive execution can establish missing-edge absence without
    // rewriting captured facts. A genuine forbidden witness always wins.
    let forbidden = rules.any(r => r.status == "refuted")
    let graph_complete = rules.all(r => r.status == "checked-compatible")
    let positive = serial_completion.status == "checked-compatible" ||
      (
        completion.status == "checked-compatible" &&
        (mode == RmSnapshot || graph_complete)
      )
    let status = if forbidden {
      "refuted"
    } else if positive {
      "checked-compatible"
    } else {
      "unknown"
    }
    rules.push(completion)
    if completion_key != serial_key {
      rules.push(serial_completion)
    }
    reports.push({
      "model": Json(model_name_v4(model)),
      "canonicalModel": Json(model_canonical_v4(model)),
      "requiredGraph": Json(projection),
      "orderContext": Json(scoped_context_name_v4(context)),
      "status": Json(status),
      "rules": Json(rules.map(model_rule_json_v4)),
      "compatibilityPolicy": "original predicate program completion and all required model rules; reliable refutations survive pending work",
    })
  }
  let status = if reports.any(r => {
      object_fields_unchecked_v3(r).at("status") == Json("refuted")
    }) {
    "refuted"
  } else if reports.all(r => {
      object_fields_unchecked_v3(r).at("status") == Json("checked-compatible")
    }) {
    "checked-compatible"
  } else {
    "unknown"
  }
  Ok({
    record: {
      "format": "moontxnwitness-relation-model-composition/v4",
      "schemaVersion": 4,
      "semanticContract": "relation-predicate-models/v1",
      "algorithm": "predicate-source-scoped-graph-and-original-prefix-search-1",
      "definition": "Adya scoped predicate/item dependencies with explicit fixed-reference model order contexts; separate from fixed Elle register/list equivalence",
      "referenceCommit": "4e359e597c52938b0afebb8bc42273914d68a424",
      "status": Json(status),
      "sourceSha256": Json(facts.source_sha256),
      "sourcePolicy": { "realtimeKnown": Json(realtime_known) },
      "observations": facts.source_record,
      "options": model_options_record_v4(options),
      "models": Json(reports),
      "predicateGraph": relation_predicate_graph_v4_json(predicate),
      "orderFacts": {
        "processComplete": Json(orders.process_complete),
        "realtimeComplete": Json(orders.realtime_complete),
        "execution": orders.execution,
      },
      "execution": {
        "counterContract": "relation-model-independent-source-scoped-graph-and-prefix-counters-1",
        "exactLimits": {
          "committedTransactions": 6,
          "operations": 128,
          "operationScope": "all original read, write and savepoint-control actions",
          "states": Json(options.max_states),
          "operationChecks": Json(options.max_source_checks),
        },
        "graphLimits": {
          "transactions": 128,
          "operations": 4096,
          "edges": 50000,
        },
        "graphRules": Json(
          graph_rules.values().map(model_rule_json_v4).collect(),
        ),
      },
      "sourceAssurance": "conditional on supplied original facts; does not authenticate a collector or assert a database product isolation level",
    },
  })
}

///|
pub fn relation_model_classification_v4_json(
  result : RelationModelClassificationV4,
) -> Json {
  v4_json_copy(result.record)
}

///|
pub fn verify_relation_models_v4(
  facts : ModelFactsV4,
  report : Json,
  options : ModelOptionsV4,
  realtime_known~ : Bool = true,
) -> Bool {
  match classify_relation_models_v4(facts, options, realtime_known~) {
    Ok(actual) => report == actual.record
    Err(_) => false
  }
}
