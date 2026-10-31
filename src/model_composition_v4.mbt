///|
priv struct ModelOrdersV4 {
  edges : Array[ScopedOrderEdgeInputV4]
  process_complete : Bool
  realtime_complete : Bool
  gaps : Array[Json]
  execution : Json
}

///|
fn model_orders_v4(
  facts : ModelFactsV4,
  source : ModelSourceV4,
  maximum : Int32,
) -> ModelOrdersV4 {
  let budget : ModelSourceBudgetV4 = { maximum, checks: 0, limited: false, }
  let edges : Array[ScopedOrderEdgeInputV4] = []
  let gaps : Array[Json] = []
  let by_id : Map[String, ModelTxBoundaryV4] = Map([])
  let mut realtime_complete = true
  let mut process_complete = facts.clients_complete
  let mut unknown = false
  for boundary in source.boundaries {
    if !model_source_charge_v4(budget) {
      break
    }
    by_id[boundary.id] = boundary
    if boundary.status == Unknown {
      unknown = true
    }
    if boundary.status == Committed &&
      (boundary.start is None || boundary.end is None) {
      realtime_complete = false
    }
  }
  let committed = source.boundaries.filter(b => b.status == Committed)
  // One confirmed transaction has no inter-transaction order relations.
  if committed.length() <= 1 && !unknown {
    process_complete = true
    realtime_complete = true
  }
  let assigned : Map[String, Bool] = Map([])
  for client in facts.clients {
    let members : Array[ModelTxBoundaryV4] = []
    for id in client.transactions {
      if !model_source_charge_v4(budget) {
        break
      }
      match by_id.get(id) {
        Some(b) => {
          assigned[id] = true
          if b.status == Committed {
            members.push(b)
          } else if b.status == Unknown {
            process_complete = false
          }
        }
        None => process_complete = false
      }
    }
    for i in 1..<members.length() {
      if !model_source_charge_v4(budget) {
        break
      }
      let a = members[i - 1]
      let b = members[i]
      match (a.end, b.start) {
        (Some(last), Some(first)) if last < first =>
          edges.push({
            id: "derived-process-" + edges.length().to_string(),
            from: a.id,
            to: b.id,
            kind: ScopedProcess,
            context_id: client.id,
            from_source: { transaction: a.id, observation: a.response, },
            to_source: { transaction: b.id, observation: b.invocation, },
          })
        _ => {
          process_complete = false
          gaps.push({
            "code": "logical-client-nonoverlap-unproved",
            "client": Json(client.id),
            "transactions": Json([a.id, b.id]),
          })
        }
      }
    }
  }
  if committed.length() > 1 {
    for tx in committed {
      if !assigned.contains(tx.id) {
        process_complete = false
      }
    }
  }
  for a in committed {
    for b in committed {
      if !model_source_charge_v4(budget) {
        break
      }
      if a.id == b.id {
        continue
      }
      match (a.end, b.start) {
        (Some(last), Some(first)) if last < first =>
          edges.push({
            id: "derived-realtime-" + edges.length().to_string(),
            from: a.id,
            to: b.id,
            kind: ScopedRealtime,
            context_id: "original-history-boundaries",
            from_source: { transaction: a.id, observation: a.response, },
            to_source: { transaction: b.id, observation: b.invocation, },
          })
        _ => ()
      }
    }
  }
  if unknown {
    process_complete = false
    realtime_complete = false
    gaps.push({ "code": "unknown-transaction-order-boundary" })
  }
  if budget.limited {
    process_complete = false
    realtime_complete = false
    gaps.push({ "code": "order-source-budget" })
  }
  if !process_complete {
    gaps.push({ "code": "process-universe-or-nonoverlap-incomplete" })
  }
  if !realtime_complete {
    gaps.push({ "code": "response-invocation-universe-incomplete" })
  }
  {
    edges,
    process_complete,
    realtime_complete,
    gaps,
    execution: model_source_execution_v4(budget),
  }
}

///|
fn model_projection_keep_v4(
  kind : ScopedDataKindV4,
  projection : String,
) -> Bool {
  match projection {
    "W" => kind == ScopedWWItem || kind == ScopedWWPredicate
    "I" => kind != ScopedRWItem && kind != ScopedRWPredicate
    "I+Ai" => kind != ScopedRWPredicate
    _ => true
  }
}

///|
fn model_graph_rule_v4(
  source : ModelSourceV4,
  orders : ModelOrdersV4,
  projection : String,
  context : ScopedOrderContextV4,
  options : ModelOptionsV4,
) -> ModelRuleV4 {
  let id = "graph/" + projection + "/" + scoped_context_name_v4(context)
  let complete = source.ww_complete &&
    (
      projection == "W" ||
      (source.wr_complete && (projection == "I" || source.rw_complete))
    )
  let data = source.edges.filter(edge => {
    model_projection_keep_v4(edge.kind, projection)
  })
  match
    scoped_dependency_graph_v4(
      source.nodes,
      data,
      order_edges=orders.edges,
      data_complete=complete,
      process_complete=orders.process_complete,
      realtime_complete=orders.realtime_complete,
    ) {
    Err(reason) =>
      model_rule_v4(
        id,
        "unknown",
        "source graph could not be constructed",
        evidence=Json(reason),
      )
    Ok(graph) => {
      let result = if projection == "Ext(I,A)" {
        search_si_extension_v4(
          graph,
          rule_set=ElleFixed4e359e5,
          order_context=context,
          max_states=options.max_states,
          max_edge_checks=options.max_edge_checks,
        )
      } else {
        let category = match projection {
          "W" => ScopedG0
          "I" => ScopedG1c
          "I+Ai" => ScopedG2Item
          "G-single" => ScopedGSingle
          "G-nonadjacent" => ScopedGNonadjacent
          _ => ScopedG2
        }
        search_scoped_category_v4(
          graph,
          category,
          rule_set=ElleFixed4e359e5,
          order_context=context,
          max_states=options.max_states,
          max_edge_checks=options.max_edge_checks,
        )
      }
      model_rule_v4(
        id,
        result.status,
        "actual category/Ext search from recomputed original history adapter",
        evidence=result.record,
      )
    }
  }
}

///|
fn model_graph_key_v4(
  projection : String,
  context : ScopedOrderContextV4,
) -> String {
  "graph/" + projection + "/" + scoped_context_name_v4(context)
}

///|
fn model_combine_rules_v4(
  id : String,
  rules : Array[ModelRuleV4],
  reason : String,
) -> ModelRuleV4 {
  let status = if rules.any(rule => rule.status == "refuted") {
    "refuted"
  } else if rules.all(rule => rule.status == "checked-compatible") {
    "checked-compatible"
  } else if rules.any(rule => rule.status == "pending") {
    "pending"
  } else {
    "unknown"
  }
  model_rule_v4(
    id,
    status,
    reason,
    evidence=Json(rules.map(model_rule_json_v4)),
    covered_by=rules.map(rule => rule.id),
  )
}

///|
fn model_context_for_token_v4(token : String) -> ScopedOrderContextV4 {
  if token.has_suffix("-realtime") {
    ScopedWithRealtime
  } else if token.has_suffix("-process") {
    ScopedWithProcess
  } else {
    ScopedDataOnly
  }
}

///|
fn model_literal_rule_v4(
  token : String,
  model : ElleModelV4,
  rules : Map[String, ModelRuleV4],
  source : ModelSourceV4,
  completions : Map[String, ModelRuleV4],
) -> ModelRuleV4 {
  let context = model_context_for_token_v4(token)
  let graph = fn(projection, ctx) {
    rules.at(model_graph_key_v4(projection, ctx))
  }
  let dependencies : Array[ModelRuleV4] = match token {
    "duplicate-elements" => [source.rules.at("duplicate-elements")]
    "cyclic-versions" => [source.rules.at("source-cyclic-versions")]
    "G0" | "G0-process" | "G0-realtime" | "PL-1-cycle-exists" =>
      [graph("W", context)]
    "G1" | "G1-process" | "G1-realtime" =>
      [source.rules.at("G1a"), source.rules.at("G1b"), graph("I", context)]
    "G1c" | "G1c-process" | "G1c-realtime" | "PL-2-cycle-exists" =>
      [graph("I", context)]
    "G2-item" => [graph("I+Ai", ScopedDataOnly)]
    "PL-2.99-cycle-exists" =>
      [graph("I", ScopedDataOnly), graph("I+Ai", ScopedDataOnly)]
    "G2" | "G2-process" | "G2-realtime" => [graph("D", context)]
    "PL-3-cycle-exists" => [graph("I", context), graph("D", context)]
    "G1a" | "G1b" => [source.rules.at(token)]
    "G-single" => [graph("G-single", ScopedDataOnly)]
    "G-nonadjacent" | "G-nonadjacent-process" | "G-nonadjacent-realtime" =>
      [graph("G-nonadjacent", context)]
    "future-read" => [source.rules.at("future-source-applicability")]
    "internal" => [source.rules.at("internal")]
    "PL-SS-cycle-exists" =>
      [graph("I", ScopedWithRealtime), graph("D", ScopedWithRealtime)]
    "PL-SI-cycle-exists" => [graph("Ext(I,A)", ScopedDataOnly)]
    "strong-session-PL-1-cycle-exists" => [graph("W", ScopedWithProcess)]
    "strong-PL-1-cycle-exists" => [graph("W", ScopedWithRealtime)]
    "strong-session-PL-2-cycle-exists" => [graph("I", ScopedWithProcess)]
    "strong-PL-2-cycle-exists" => [graph("I", ScopedWithRealtime)]
    "strong-session-serializable-cycle-exists" =>
      [graph("I", ScopedWithProcess), graph("D", ScopedWithProcess)]
    "strong-session-snapshot-isolation-cycle-exists" =>
      [graph("Ext(I,A)", ScopedWithProcess)]
    "strong-snapshot-isolation-cycle-exists" =>
      [graph("Ext(I,A)", ScopedWithRealtime)]
    _ => []
  }
  if !dependencies.is_empty() {
    let direct = model_combine_rules_v4(
      "literal/" + token,
      dependencies,
      "literal requirement discharged by the explicitly named source checker or identical graph obligation; no process-to-realtime promotion",
    )
    if direct.status == "checked-compatible" || direct.status == "refuted" {
      return direct
    }
    if token == "G-single" || token.has_prefix("G-nonadjacent") {
      let completion = completions.at(
        "completion/Ext/" + scoped_context_name_v4(context),
      )
      if completion.status == "checked-compatible" {
        return model_rule_v4(
          "literal/" + token,
          "checked-compatible",
          "an I/RW cycle with no cyclically adjacent RW edges contracts to an Ext cycle; the constructed complete Ext order excludes it",
          covered_by=[completion.id],
          evidence=completion.evidence,
        )
      }
    }
    return direct
  }
  if token == "G-SI" || token == "G-SIb" || token == "G-MSR" {
    let completion = completions.at("completion/Ext/data-only")
    return model_rule_v4(
      "literal/" + token,
      completion.status,
      "literal spelling is retained; generalized transaction observations admit the explicitly constructed SI execution, rather than checking an arbitrary given SSG",
      covered_by=[completion.id],
      evidence=completion.evidence,
    )
  }
  if token == "G-update" {
    let completion = completions.at("completion/update")
    return model_rule_v4(
      "literal/" + token,
      completion.status,
      completion.reason,
      covered_by=[completion.id],
      evidence=completion.evidence,
    )
  }
  if token == "G-monotonic" {
    let completion = completions.at("completion/monotonic")
    return model_rule_v4(
      "literal/" + token,
      completion.status,
      completion.reason,
      covered_by=[completion.id],
      evidence=completion.evidence,
    )
  }
  if token == "G-cursor" || token == "lost-update" {
    let rr = completions.at("completion/RR-cursor")
    let cv = completions.at("completion/CV-per-key-ranks")
    let completion = if rr.status == "checked-compatible" { rr } else { cv }
    if completion.status == "checked-compatible" {
      return model_rule_v4(
        "literal/" + token,
        "checked-compatible",
        completion.reason,
        covered_by=[completion.id],
        evidence=completion.evidence,
      )
    }
  }
  if token == "predicate-read-miss" &&
    source.profile == "captured-relation-row-slots/v1" {
    let point = source.rules.at("row-slot-point-query-coverage")
    return model_rule_v4(
      "literal/predicate-read-miss",
      point.status,
      "complete singleton primary-key queries map to one proved slot state; this is not arbitrary predicate coverage",
      covered_by=[point.id],
      evidence=point.evidence,
    )
  }
  if token == "predicate-read-miss" &&
    !source.profile.has_prefix("relation-") &&
    source.profile != "adya-2000-predicate-on-keyslots-v1" {
    return model_rule_v4(
      "literal/predicate-read-miss",
      "checked-compatible",
      "point register/list workload contract has no relation predicate query primitive",
      covered_by=["validated-workload-applicability"],
    )
  }
  if token == "lost-update" &&
    model_observation_premises_v4(source, false) &&
    (model_projection_v4(model) == "D" || model == ElleRepeatableRead) {
    let projection = if model == ElleRepeatableRead { "I+Ai" } else { "D" }
    let parent = graph(projection, ScopedDataOnly)
    // Fixed anomaly DAG has lost-update -> G2-item -> G2. This is absence
    // coverage only: an unrelated G2 witness is not relabelled as lost-update.
    if parent.status == "checked-compatible" {
      return model_rule_v4(
        "literal/lost-update",
        "checked-compatible",
        "absence via fixed lost-update -> G2-item -> G2 implication on the same closed source profile",
        covered_by=[parent.id, "source-identity-and-installation"],
      )
    }
  }
  model_rule_v4(
    "literal/" + token,
    "pending",
    "fixed literal obligation has no implemented checker or independently justified complete coverage here",
  )
}

///|
/// The model composition always starts from HistoryV4, never trusted proof JSON.
pub fn classify_models_v4(
  facts : ModelFactsV4,
  options : ModelOptionsV4,
) -> ModelClassificationV4 {
  let source = model_source_applicability_v4(
    facts.history,
    model_other_source_v4(facts.history, options),
  )
  let orders = model_orders_v4(facts, source, options.max_source_checks)
  let graph_rules : Map[String, ModelRuleV4] = Map([])
  let needed = model_needed_graph_rules_v4(options.models)
  let evaluated : Array[String] = []
  // Distinct projections carry independent completeness; W is not poisoned by
  // allowed read anomalies, and I does not require RW construction to finish.
  for context in [ScopedDataOnly, ScopedWithProcess, ScopedWithRealtime] {
    for
      projection in [
        "W", "I", "I+Ai", "D", "G-single", "G-nonadjacent", "Ext(I,A)",
      ] {
      let key = model_graph_key_v4(projection, context)
      let rule = if needed.contains(key) {
        evaluated.push(key)
        model_graph_rule_v4(source, orders, projection, context, options)
      } else {
        model_rule_v4(
          key, "pending", "not required by the requested canonical definitions",
        )
      }
      graph_rules[rule.id] = rule
    }
  }
  let completions = model_completion_rules_v4(
    facts, source, orders, options, graph_rules,
  )
  let reports : Array[Json] = []
  for model in options.models {
    let projection = model_projection_v4(model)
    let context = model_context_v4(model)
    let necessary : Array[ModelRuleV4] = [
      source.rules.at("source-identity-and-installation"),
      source.rules.at("program-source-applicability"),
      source.rules.at("identity-source-applicability"),
      model_rule_v4(
        "confirmed-transaction-outcomes",
        if source.boundaries.all(tx => tx.status != Unknown) {
          "checked-compatible"
        } else {
          "unknown"
        },
        "unconfirmed COMMIT or retry outcomes do not become a completed model conclusion",
      ),
      graph_rules.at(model_graph_key_v4("W", ScopedDataOnly)),
      graph_rules.at(model_graph_key_v4(projection, context)),
    ]
    match source.rules.get("row-slot-projection-applicability") {
      Some(rule) => necessary.push(rule)
      None => ()
    }
    if source.profile == "captured-relation-row-slots/v1" && projection == "D" {
      necessary.push(
        completions.at(
          "completion/original-row-serial/" + scoped_context_name_v4(context),
        ),
      )
    }
    if projection != "W" {
      necessary.push(graph_rules.at(model_graph_key_v4("I", ScopedDataOnly)))
      for
        name in [
          "G1a", "G1b", "future-source-applicability", "write-input-applicability",
        ] {
        necessary.push(source.rules.at(name))
      }
    }
    if projection == "Ext(I,A)" || projection == "D" {
      necessary.push(
        completions.at("completion/Ext/" + scoped_context_name_v4(context)),
      )
    }
    let literals = model_literal_obligations_v4(model).map(token => {
      model_literal_rule_v4(token, model, graph_rules, source, completions)
    })
    necessary.append(literals)
    // No literal marker typo or alias repair is performed. This list makes the
    // exact fixed-catalogue pending obligations visible alongside actual work.
    for marker in model_pending_markers_v4(model) {
      if !necessary.any(rule => rule.id == "literal/" + marker) {
        necessary.push(
          model_rule_v4(
            "literal/" + marker,
            "pending",
            "fixed literal definition remains unimplemented",
          ),
        )
      }
    }
    let combined = model_combine_rules_v4(
      model_name_v4(model),
      necessary,
      "reliable forbidden evidence wins; every necessary rule must finish for compatibility",
    )
    let status = if combined.status == "pending" {
      "unknown"
    } else {
      combined.status
    }
    reports.push({
      "model": Json(model_name_v4(model)),
      "canonicalModel": Json(model_canonical_v4(model)),
      "status": Json(status),
      "requiredGraph": Json(projection),
      "orderContext": Json(scoped_context_name_v4(context)),
      "rules": Json(necessary.map(model_rule_json_v4)),
      "pendingRules": Json(
        necessary.filter(r => r.status == "pending").map(r => r.id),
      ),
      "unknownRules": Json(
        necessary
        .filter(r => r.status == "unknown" || r.status == "unsupported")
        .map(r => r.id),
      ),
      "proofPolicy": "most specific source or scoped-graph evidence retained; pending checks cannot erase refutation",
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
  {
    record: {
      "format": "moontxnwitness-model-composition/v4",
      "schemaVersion": 4,
      "semanticContract": if source.profile == "captured-relation-row-slots/v1" {
        Json("elle-4e359e5-captured-relation-row-slot-completion-models-1")
      } else if source.profile == "captured-list-prefix-state/v2" {
        Json("elle-4e359e5-captured-list-prefix-state-completion-models-2")
      } else if source.profile == "captured-register-full-program/v2" {
        Json("elle-4e359e5-captured-register-observation-completion-models-2")
      } else {
        Json("elle-4e359e5-transaction-observation-completion-models-1")
      },
      "algorithm": if source.profile == "captured-relation-row-slots/v1" {
        Json("captured-row-slot-obligations-and-original-program-completion-1")
      } else if source.profile == "captured-list-prefix-state/v2" {
        Json("captured-list-prefix-obligations-and-completion-2")
      } else if source.profile == "captured-register-full-program/v2" {
        Json("captured-point-source-obligations-and-prefix-completion-2")
      } else {
        Json("history-source-obligations-scoped-graph-and-prefix-completion-1")
      },
      "referenceCommit": "4e359e597c52938b0afebb8bc42273914d68a424",
      "status": Json(status),
      "sourceSha256": Json(facts.source_sha256),
      "sourceDigestContract": "sorted-json-object-keys-v1",
      "sourceProfile": Json(source.profile),
      "completionScope": "fixed Elle transaction-observation models; generalized existential SI completion; no given logical SSG or database snapshot assertion is checked",
      "sourceAssurance": "conditional on original declared/captured facts; no database authenticity or product isolation level assertion",
      "observations": facts.source_record,
      "options": model_options_record_v4(options),
      "models": Json(reports),
      "sourceCoverage": {
        "ww": Json(source.ww_complete),
        "wr": Json(source.wr_complete),
        "rw": Json(source.rw_complete),
        "process": Json(orders.process_complete),
        "realtime": Json(orders.realtime_complete),
        "dataGaps": Json(source.gaps),
        "orderGaps": Json(orders.gaps),
      },
      "execution": {
        "counterContract": if source.profile == "captured-relation-row-slots/v1" {
          Json(
            "captured-row-slot-independent-source-and-per-rule-graph-counters-1",
          )
        } else if source.profile == "captured-list-prefix-state/v2" {
          Json(
            "captured-list-prefix-independent-source-and-per-rule-graph-counters-2",
          )
        } else if source.profile == "captured-register-full-program/v2" {
          Json(
            "captured-point-independent-source-and-per-rule-graph-counters-2",
          )
        } else {
          Json("model-independent-source-and-per-rule-graph-counters-1")
        },
        "source": source.execution,
        "order": orders.execution,
        "limits": model_options_record_v4(options),
        "graphRulesEvaluated": Json(evaluated),
      },
      "scope": {
        "oldSixDefinitionIdsUnchanged": true,
        "allProfilesComplete": false,
        "fourteenDefinitionsHaveObligationComposition": true,
        "completionProfiles": {
          "declaredRegister": "constructive CO/VIS or per-key graph proof when every premise and budget completes",
          "rawRegister": "constructive CO/VIS and per-key rank proofs only after every captured source, predecessor-lineage, effective-overlay and complete-window premise is revalidated",
          "listAndRelation": if source.profile ==
            "captured-relation-row-slots/v1" {
            Json(
              "atomic singleton-key row programs have explicit source, snapshot and serial certificate premises; relation predicates and physical incarnation equivalence remain pending",
            )
          } else if source.profile == "captured-list-prefix-state/v2" {
            Json(
              "explicit list prefix-state mapping and original-program completion replay checked under recorded premises; relation completion remains pending",
            )
          } else {
            Json(
              "direct source/category checks available; theorem mapping to this generalized SI profile remains pending",
            )
          },
        },
        "pendingLiteralTokensPreserved": true,
        "poolConnectionCreatesLogicalClient": false,
        "processAutomaticallyPromotedToRealtime": false,
      },
    },
  }
}

///|
pub fn verify_models_v4(
  facts : ModelFactsV4,
  supplied : Json,
  options : ModelOptionsV4,
) -> Bool {
  supplied == classify_models_v4(facts, options).record
}
