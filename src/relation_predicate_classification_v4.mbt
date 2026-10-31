///|
/// A bounded graph-category result, separate from an isolation-model judgment.
pub struct RelationPredicateClassificationV4 {
  priv status : String
  priv record : Json
}

///|
pub fn RelationPredicateClassificationV4::status(
  self : RelationPredicateClassificationV4,
) -> String {
  self.status
}

///|
fn relation_predicate_scoped_graph_v4(
  source : RelationPredicateGraphV4,
) -> Result[ScopedDependencyGraphV4, String] {
  let nodes = source.index.parsed.programs.filter_map(program => {
    if program.status == Committed {
      Some(program.id)
    } else {
      None
    }
  })
  let edges : Array[ScopedDataEdgeInputV4] = []
  for index, scoped in source.scoped_edges {
    let edge = scoped.dependency
    let kind = match (edge.kind, scoped.scope) {
      (WW, "item") => ScopedWWItem
      (WW, "predicate") => ScopedWWPredicate
      (WR, "item") => ScopedWRItem
      (WR, "predicate") => ScopedWRPredicate
      (RW, "item") => ScopedRWItem
      (RW, "predicate") => ScopedRWPredicate
      _ => return Err("unsupported relation scoped dependency")
    }
    edges.push({
      id: "relation-edge-" + index.to_string(),
      from: edge.from,
      to: edge.to,
      kind,
      sources: source.sources.get_or_default(scoped, []).map(v4_json_copy),
    })
  }
  scoped_dependency_graph_v4(
    nodes,
    edges,
    data_complete=source.complete,
    process_complete=false,
    realtime_complete=false,
    gaps=source.gaps.map(v4_json_copy),
  )
}

///|
/// Rules are required: Adya mixed-item/predicate and fixed Elle scopes differ.
/// Process and real-time edges are never inferred from physical connections.
pub fn classify_relation_predicate_v4(
  history : HistoryV4,
  category : ScopedCategoryV4,
  rule_set~ : ScopedRuleSetV4,
  max_graph_checks~ : Int32 = 1000000,
  max_predicate_checks~ : Int32 = 1000000,
  max_candidate_visits~ : Int32 = 100000,
  max_states~ : Int32 = 100000,
  max_edge_checks~ : Int32 = 1000000,
) -> Result[RelationPredicateClassificationV4, String] {
  let predicate = match
    build_relation_predicate_graph_v4(
      history,
      max_graph_checks~,
      max_predicate_checks~,
      max_candidate_visits~,
    ) {
    Ok(value) => value
    Err(reason) => return Err(reason)
  }
  let scoped = match relation_predicate_scoped_graph_v4(predicate) {
    Ok(value) => value
    Err(reason) => return Err(reason)
  }
  let result = search_scoped_category_v4(
    scoped,
    category,
    rule_set~,
    order_context=ScopedDataOnly,
    max_states~,
    max_edge_checks~,
  )
  let status = result.status()
  Ok({
    status,
    record: {
      "format": "moontxnwitness-relation-predicate-category/v4",
      "schemaVersion": 4,
      "dataModel": "relation-set-v1",
      "profile": "relation-predicate-categories/v4-1",
      "execution": {
        "counterContract": "relation-predicate-category-composite-counters-1",
        "limits": {
          "maxGraphChecks": Json(max_graph_checks),
          "maxPredicateChecks": Json(max_predicate_checks),
          "maxCandidateVisits": Json(max_candidate_visits),
          "maxStates": Json(max_states),
          "maxEdgeChecks": Json(max_edge_checks),
        },
        "counts": "predicateGraph.execution and search.execution retain their independent counter contracts",
      },
      "semanticContract": "relation-predicate-category-on-keyslots-v1",
      "algorithm": "relation-predicate-scoped-category-1",
      "sourceSha256": Json(v3_dislock_sha256(history.source_text)),
      "sourceEncoding": "exact validated history source UTF-8 bytes",
      "category": Json(scoped_category_name_v4(category)),
      "ruleSet": Json(scoped_ruleset_name_v4(rule_set)),
      "orderContext": "data-only",
      "acceptsIsolationModels": false,
      "status": Json(status),
      "predicateGraph": relation_predicate_graph_v4_json(predicate),
      "scopedGraph": scoped_dependency_graph_v4_json(scoped),
      "search": scoped_search_v4_json(result),
      "sourceAssurance": "derived from supplied original relation observations and checked effect journals; no database authentication",
      "scope": "one explicitly selected dependency category; no complete isolation-model or global shortest-cycle claim",
    },
  })
}

///|
pub fn relation_predicate_classification_v4_json(
  result : RelationPredicateClassificationV4,
) -> Json {
  v4_json_copy(result.record)
}

///|
/// The caller independently supplies every category/ruleset/budget selector.
pub fn verify_relation_predicate_classification_v4(
  history : HistoryV4,
  supplied : Json,
  category : ScopedCategoryV4,
  rule_set~ : ScopedRuleSetV4,
  max_graph_checks~ : Int32 = 1000000,
  max_predicate_checks~ : Int32 = 1000000,
  max_candidate_visits~ : Int32 = 100000,
  max_states~ : Int32 = 100000,
  max_edge_checks~ : Int32 = 1000000,
) -> Bool {
  match
    classify_relation_predicate_v4(
      history,
      category,
      rule_set~,
      max_graph_checks~,
      max_predicate_checks~,
      max_candidate_visits~,
      max_states~,
      max_edge_checks~,
    ) {
    Ok(actual) => supplied == relation_predicate_classification_v4_json(actual)
    Err(_) => false
  }
}
