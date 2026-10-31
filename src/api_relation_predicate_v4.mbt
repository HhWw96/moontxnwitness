///|
priv struct WireRelationPredicateOptionsV4 {
  category : ScopedCategoryV4
  rules : ScopedRuleSetV4
  graph : Int32
  predicates : Int32
  candidates : Int32
  states : Int32
  edges : Int32
}

///|
fn wire_relation_predicate_options_v4(
  text : String,
) -> WireRelationPredicateOptionsV4 raise {
  let fields = object_fields(
    guarded_json(text, limit=8192),
    "relation predicate options v4",
  )
  known_fields(
    fields,
    [
      "category", "ruleSet", "maxGraphChecks", "maxPredicateChecks", "maxCandidateVisits",
      "maxStates", "maxEdgeChecks",
    ],
    "relation predicate options v4",
  )
  let category = match
    required(fields, "category", "relation predicate options v4") {
    String("G0") => ScopedG0
    String("G1c") => ScopedG1c
    String("G2-item") => ScopedG2Item
    String("G2") => ScopedG2
    String("G-single-item") => ScopedGSingleItem
    String("G-single") => ScopedGSingle
    String("G-nonadjacent") => ScopedGNonadjacent
    _ =>
      fail("category must explicitly select a supported scoped graph category")
  }
  let rules = match
    required(fields, "ruleSet", "relation predicate options v4") {
    String("adya-2000-scoped-categories-v1") => Adya2000Mixed
    String("elle-4e359e5-scoped-categories-v1") => ElleFixed4e359e5
    _ =>
      fail(
        "ruleSet must explicitly select the Adya or fixed Elle category definition",
      )
  }
  {
    category,
    rules,
    graph: wire_v4_int(fields, "maxGraphChecks", 1000000, 1000000),
    predicates: wire_v4_int(fields, "maxPredicateChecks", 1000000, 1000000),
    candidates: wire_v4_int(fields, "maxCandidateVisits", 100000, 100000),
    states: wire_v4_int(fields, "maxStates", 100000, 100000),
    edges: wire_v4_int(fields, "maxEdgeChecks", 1000000, 1000000),
  }
}

///|
pub fn classify_relation_predicate_v4_json(
  text : String,
  options_text : String,
) -> String {
  try {
    let opts = wire_relation_predicate_options_v4(options_text)
    match
      classify_relation_predicate_v4(
        wire_v4_history(text),
        opts.category,
        rule_set=opts.rules,
        max_graph_checks=opts.graph,
        max_predicate_checks=opts.predicates,
        max_candidate_visits=opts.candidates,
        max_states=opts.states,
        max_edge_checks=opts.edges,
      ) {
      Ok(result) =>
        relation_predicate_classification_v4_json(result).stringify(indent=2)
      Err(reason) => wire_v4_failure(reason)
    }
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
pub fn verify_relation_predicate_classification_v4_json(
  text : String,
  report_text : String,
  options_text : String,
) -> String {
  try {
    let opts = wire_relation_predicate_options_v4(options_text)
    wire_v4_verified(
      verify_relation_predicate_classification_v4(
        wire_v4_history(text),
        guarded_json(report_text, limit=33554432),
        opts.category,
        rule_set=opts.rules,
        max_graph_checks=opts.graph,
        max_predicate_checks=opts.predicates,
        max_candidate_visits=opts.candidates,
        max_states=opts.states,
        max_edge_checks=opts.edges,
      ),
    )
  } catch {
    _ => wire_v4_verified(false)
  }
}
