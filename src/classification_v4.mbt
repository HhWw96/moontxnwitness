///|
priv struct V4CategoryGraph {
  base : ClassificationModelV3Graph
  inferences : Json
}

///|
fn v4_empty_category_graph(
  history : HistoryV4,
  reason : String,
) -> V4CategoryGraph {
  let normalized = match history.payload {
    RegisterSnapshot(_, Some(n)) => n
    ListSnapshot(parsed) => parsed.normalized
    RelationSnapshot(parsed) => parsed.normalized
    _ => Json::object(Map([]))
  }
  {
    base: {
      normalized,
      transactions: [],
      edges: [],
      sources: Map([]),
      validity_gaps: [],
      history: None,
      list_parsed: None,
      complete: false,
      reason,
    },
    inferences: Json::null(),
  }
}

///|
fn v4_category_graph(history : HistoryV4) -> V4CategoryGraph raise {
  match history.payload {
    RegisterSnapshot(Some(input), normalized) => {
      let raw_operations = match normalized {
        Some(Object(fields)) =>
          match fields.get("observations") {
            Some(Array(events)) =>
              events
              .filter(event => {
                let kind = object_fields_unchecked_v3(event).get("kind")
                kind == Some(Json("read")) || kind == Some(Json("write"))
              })
              .length()
            _ => count_ops(input)
          }
        _ => count_ops(input)
      }
      if input.transactions.length() > 128 || raw_operations > 4096 {
        return v4_empty_category_graph(
          history, "register-category-capacity-128-4096",
        )
      }
      // Real-time edges have their own categories; never mix them into G0/G1c/G2.
      let data_history : History = { ..input, model: Serializable, }
      let report = analyze_internal(data_history, false, complete_search=false)
      let complete = !report.graph.edge_budget_exceeded &&
        !report.findings.any(f => {
          f.severity == "error" || f.severity == "uncertainty"
        })
      {
        base: {
          normalized: normalized.unwrap_or(Json::object(Map([]))),
          transactions: data_history.transactions,
          edges: report.edges,
          sources: Map([]),
          validity_gaps: report.findings
          .filter(f => f.severity == "error" || f.severity == "uncertainty")
          .map(finding_json),
          history: Some(data_history),
          list_parsed: None,
          complete,
          reason: if complete {
            "complete"
          } else {
            "required-version-order-source-or-graph-incomplete"
          },
        },
        inferences: {
          "versionOrders": Json(report.inferred_orders),
          "versionOrderSources": Json(report.order_sources),
        },
      }
    }
    RegisterSnapshot(None, _) =>
      v4_empty_category_graph(history, "capture-coverage-incomplete")
    ListSnapshot(parsed) =>
      {
        // The source remains the original capture; no synthetic events are made.
        base: classification_models_v3_list(
          history.source_text,
          parsed.normalized,
        ),
        inferences: { "versionOrderCompletion": false },
      }
    RelationSnapshot(_) =>
      v4_empty_category_graph(
        history, "relation-category-classification-not-supported",
      )
  }
}

///|
fn v4_register_category_witness(
  graph : ClassificationModelV3Graph,
  cycle : Array[Edge],
) -> Json {
  let history = graph.history.unwrap()
  let by_id : Map[String, Transaction] = Map([])
  for tx in history.transactions {
    by_id[tx.id] = tx
  }
  let proof = cycle.map(edge => {
    let from_seq = match edge.from_op {
      Some(index) =>
        classification_v3_observation_sources(
          graph.normalized,
          edge.from,
          by_id.at(edge.from).ops[index],
        )
      None => []
    }
    let to_seq = match edge.to_op {
      Some(index) =>
        classification_v3_observation_sources(
          graph.normalized,
          edge.to,
          by_id.at(edge.to).ops[index],
        )
      None => []
    }
    let order = match edge.key {
      Some(key) =>
        match history.version_orders.get(key) {
          Some(order) => Json(order)
          None => Json::null()
        }
      None => Json::null()
    }
    (
      {
        "edge": edge_json(edge),
        "fromObservationSeq": Json(from_seq),
        "toObservationSeq": Json(to_seq),
        "inputVersionOrder": order,
      } : Json)
  })
  {
    "kind": "source-bound-register-category-cycle",
    "specificCategory": Json(
      if cycle.all(e => e.kind == WW) {
        "G0"
      } else if cycle.any(e => e.kind == RW) {
        "G2-item"
      } else {
        "G1c"
      },
    ),
    "edges": Json(proof),
    "minimality": "simple cycle for the requested category; no shortest-cycle claim",
    "sourceScope": "original capture observation identities or caller-declared transaction operation indices; input assertions do not authenticate a database",
  }
}

///|
fn v4_classification_effects(history : HistoryV4) -> Json {
  let normalized = match history.payload {
    RegisterSnapshot(Some(h), None) => return v4_declared_effects(h)
    RegisterSnapshot(_, Some(n)) => n
    ListSnapshot(parsed) => parsed.normalized
    RelationSnapshot(parsed) => parsed.normalized
    _ => return Json::null()
  }
  {
    "basis": "captured-write-effects",
    "entries": object_fields_unchecked_v3(normalized).get_or_default(
      "effects",
      Json(([] : Array[Json])),
    ),
  }
}

///|
fn v4_classification_record(
  history : HistoryV4,
  status : String,
  rules : Json,
  implied : Array[String],
  graph : V4CategoryGraph,
  categories : Array[String],
  max_states : Int32,
  max_edge_checks : Int32,
) -> ClassificationV4 {
  let record : Json = {
    "format": "moontxnwitness-classification/v4",
    "schemaVersion": 4,
    "semanticContract": "moontxnwitness-category-classification-v4-1",
    "algorithm": "v4-source-bound-category-bfs-1",
    "dataModel": Json(v4_model_name(history.data_model)),
    "observations": {
      "sourceFormat": Json(history.source_format),
      "authenticityVerified": false,
      "document": history.source_document,
    },
    "writeEffects": v4_classification_effects(history),
    "inferences": graph.inferences,
    "judgment": {
      "status": Json(status),
      "acceptsIsolationModels": false,
      "scope": "requested dependency-cycle categories only; checked-compatible does not accept a complete isolation model or certify a database",
      "dependencyGraphComplete": Json(graph.base.complete),
      "dependencies": Json(graph.base.edges.map(edge_json)),
      "sourceOrOrderGaps": Json(graph.base.validity_gaps),
      "rules": rules,
      "impliedAnomalies": Json(implied),
    },
    "execution": {
      "counterContract": "v4-category-seed-bfs-counters-1",
      "categories": Json(categories.copy()),
      "versionOrderCompletion": false,
      "limits": {
        "registerTransactions": 128,
        "registerOperations": 4096,
        "listCommittedTransactions": 6,
        "listOperations": 128,
        "edges": 50000,
        "statesPerCategory": Json(max_states),
        "edgeChecksPerCategory": Json(max_edge_checks),
      },
    },
  }
  { status, record, }
}

///|
/// Each requested category has its own search and budget over one shared graph.
pub fn classify_v4(
  history : HistoryV4,
  categories~ : Array[String] = ["G0", "G1c", "G2-item"],
  max_states~ : Int32 = 100000,
  max_edge_checks~ : Int32 = 1000000,
) -> ClassificationV4 {
  let categories = categories.copy()
  let seen : Map[String, Bool] = Map([])
  let valid = !categories.is_empty() &&
    categories.all(category => {
      if !["G0", "G1c", "G2-item"].contains(category) || seen.contains(category) {
        false
      } else {
        seen[category] = true
        true
      }
    }) &&
    max_states >= 0 &&
    max_states <= 100000 &&
    max_edge_checks >= 0 &&
    max_edge_checks <= 1000000
  if !valid {
    return v4_classification_record(
      history,
      "invalid",
      Json::object(Map([])),
      [],
      v4_empty_category_graph(history, "invalid-options"),
      categories,
      max_states,
      max_edge_checks,
    )
  }
  let graph = v4_category_graph(history) catch {
    _ =>
      return v4_classification_record(
        history,
        "invalid",
        Json::object(Map([])),
        [],
        v4_empty_category_graph(history, "invalid-graph-state"),
        categories,
        max_states,
        max_edge_checks,
      )
  }
  let index = adjacency(graph.base.transactions, graph.base.edges)
  let rules : Map[String, Json] = Map([])
  let implied : Array[String] = []
  let mut status = "checked-compatible"
  for category in categories {
    let budget : ClassificationV3Budget = {
      max_states,
      max_edge_checks,
      states: 0,
      edge_checks: 0,
      limited: false,
      reason: "complete",
    }
    let cycle = classification_v3_cycle(
      graph.base.transactions,
      graph.base.edges,
      index,
      category,
      budget,
    )
    let rule_status = if history.data_model == RelationSetV4 {
      "unsupported"
    } else if !cycle.is_empty() {
      "refuted"
    } else if budget.limited || !graph.base.complete {
      "unknown"
    } else {
      "checked-compatible"
    }
    let reason = if !cycle.is_empty() {
      "source-bound-cycle"
    } else if budget.limited {
      budget.reason
    } else {
      graph.base.reason
    }
    if rule_status == "refuted" {
      status = "refuted"
      let specific = if cycle.all(edge => edge.kind == WW) {
        "G0"
      } else if cycle.any(edge => edge.kind == RW) {
        "G2-item"
      } else {
        "G1c"
      }
      for label in classification_v3_implications(specific) {
        if !implied.contains(label) {
          implied.push(label)
        }
      }
    } else if status != "refuted" {
      if rule_status == "unsupported" {
        status = "unsupported"
      } else if rule_status == "unknown" {
        status = "inconclusive"
      }
    }
    rules[category] = {
      "status": Json(rule_status),
      "reason": Json(reason),
      "states": Json(budget.states),
      "edgeChecks": Json(budget.edge_checks),
      "evidence": if cycle.is_empty() {
        Json::null()
      } else if history.data_model == RegisterV4 {
        v4_register_category_witness(graph.base, cycle)
      } else {
        classification_models_v3_witness(graph.base, cycle)
      },
    }
  }
  v4_classification_record(
    history,
    status,
    Json::object(rules),
    implied,
    graph,
    categories,
    max_states,
    max_edge_checks,
  )
}

///|
pub fn classification_v4_json(result : ClassificationV4) -> Json {
  v4_json_copy(result.record)
}

///|
pub fn render_classification_v4(result : ClassificationV4) -> String {
  result.record.stringify(indent=2)
}

///|
pub fn verify_classification_v4(
  history : HistoryV4,
  supplied : Json,
  categories~ : Array[String] = ["G0", "G1c", "G2-item"],
  max_states~ : Int32 = 100000,
  max_edge_checks~ : Int32 = 1000000,
) -> Bool {
  supplied ==
  classify_v4(history, categories~, max_states~, max_edge_checks~).record
}
