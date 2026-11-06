///|
/// Transaction deletion with a fixed, independently selected relation category.
pub struct RelationCategoryReductionV4 {
  priv history : HistoryV4
  priv record : Json
}

///|
pub fn RelationCategoryReductionV4::history(
  self : RelationCategoryReductionV4,
) -> HistoryV4 {
  self.history
}

///|
pub fn relation_category_reduction_v4_json(
  result : RelationCategoryReductionV4,
) -> Json {
  v4_json_copy(result.record)
}

///|
fn relation_category_rule_status_v4(
  report : RelationClassificationV4,
  category : String,
) -> String {
  match
    relation_classification_at_v4(report.record, [
      "judgment", "rules", category, "status",
    ]) {
    String(status) => status
    _ => report.status
  }
}

///|
/// Deletion renumbers retained records; it cannot heal pre-existing lost events.
fn relation_reduction_sequence_window_v4(history : HistoryV4) -> Bool {
  let events = v4_source_sequences(history)
  for i, seq in events {
    if seq != Json(i + 1) {
      return false
    }
  }
  true
}

///|
/// Missing sources and unfinished checks prevent a single-minimality claim.
/// Final evidence is recomputed even after the candidate budget is exhausted.
pub fn reduce_relation_category_v4(
  history : HistoryV4,
  category~ : String,
  max_checks~ : Int32 = 256,
  max_states~ : Int32 = 100000,
  max_edge_checks~ : Int32 = 1000000,
  max_graph_checks~ : Int32 = 1000000,
) -> RelationCategoryReductionV4 {
  reduce_relation_category_impl_v4(
    history,
    category,
    max_checks,
    max_states,
    max_edge_checks,
    max_graph_checks,
    None,
  )
}

///|
/// Reduces a relation trace under the same scoped predicate rule on every deletion.
pub fn reduce_relation_predicate_v4(
  history : HistoryV4,
  category : ScopedCategoryV4,
  rule_set~ : ScopedRuleSetV4,
  max_checks~ : Int32 = 256,
  max_states~ : Int32 = 100000,
  max_edge_checks~ : Int32 = 1000000,
  max_graph_checks~ : Int32 = 1000000,
  max_predicate_checks~ : Int32 = 1000000,
  max_candidate_visits~ : Int32 = 100000,
) -> RelationCategoryReductionV4 {
  reduce_relation_category_impl_v4(
    history,
    scoped_category_name_v4(category),
    max_checks,
    max_states,
    max_edge_checks,
    max_graph_checks,
    Some({
      category,
      rules: rule_set,
      graph: max_graph_checks,
      predicates: max_predicate_checks,
      candidates: max_candidate_visits,
      states: max_states,
      edges: max_edge_checks,
    }),
  )
}

///|
fn reduce_relation_category_impl_v4(
  history : HistoryV4,
  category : String,
  max_checks : Int32,
  max_states : Int32,
  max_edge_checks : Int32,
  max_graph_checks : Int32,
  predicate : WireRelationPredicateOptionsV4?,
) -> RelationCategoryReductionV4 {
  fn classify(input : HistoryV4) -> (String, Json, Bool) {
    match predicate {
      None => {
        let report = classify_relation_point_v4(
          input,
          categories=[category],
          max_states~,
          max_edge_checks~,
          max_graph_checks~,
        )
        (
          relation_category_rule_status_v4(report, category),
          report.record,
          true,
        )
      }
      Some(options) =>
        match
          classify_relation_predicate_v4(
            input,
            options.category,
            rule_set=options.rules,
            max_graph_checks~,
            max_predicate_checks=options.predicates,
            max_candidate_visits=options.candidates,
            max_states~,
            max_edge_checks~,
          ) {
          Ok(report) =>
            (
              report.status,
              report.record,
              relation_classification_at_v4(report.record, [
                "predicateGraph", "complete",
              ]) ==
              Json(true),
            )
          Err(reason) =>
            ("unknown", { "status": "unknown", "reason": Json(reason) }, false)
        }
    }
  }
  let original_sequence_window_closed = relation_reduction_sequence_window_v4(
    history,
  )
  let original_source_closed = v4_reduction_source_closed(history)
  let mut current = history
  let removed : Array[String] = []
  let mut origins = v4_source_sequences(history)
  let mut checks = 0
  let mut passes = 0
  let mut one_minimal = false
  let mut unresolved : Array[Json] = []
  let audit : Array[Json] = []
  let mut budget_exhausted = false
  let valid_category = match predicate {
    None => relation_classification_categories_v4().contains(category)
    Some(options) =>
      options.predicates >= 0 &&
      options.predicates <= 1000000 &&
      options.candidates >= 0 &&
      options.candidates <= 100000
  }
  let valid = valid_category &&
    max_checks >= 0 &&
    max_checks <= 256 &&
    max_states >= 0 &&
    max_states <= 100000 &&
    max_edge_checks >= 0 &&
    max_edge_checks <= 1000000 &&
    max_graph_checks >= 0 &&
    max_graph_checks <= 1000000
  let (initial_status, _, initial_graph_complete) = classify(history)
  let mut status = if !valid {
    "invalid"
  } else if history.data_model != RelationSetV4 {
    "unsupported"
  } else if initial_status == "refuted" {
    "budget"
  } else if initial_status == "checked-compatible" && initial_graph_complete {
    "not-refuted"
  } else {
    "undetermined"
  }
  let mut changed = valid &&
    original_source_closed &&
    initial_graph_complete &&
    original_sequence_window_closed &&
    history.data_model == RelationSetV4 &&
    initial_status == "refuted"
  while changed && checks < max_checks {
    passes += 1
    changed = false
    unresolved = []
    let mut complete_pass = true
    for id in v4_capture_transaction_ids(current) {
      if checks >= max_checks {
        complete_pass = false
        budget_exhausted = true
        break
      }
      checks += 1
      let candidate = try {
        let (source, relative_origins) = v3_without_transaction(
          current.source_document,
          id,
        )
        match parse_history_v4(source.stringify()) {
          Ok(next) => Some((next, relative_origins))
          Err(_) => None
        }
      } catch {
        _ => None
      }
      match candidate {
        None => {
          let fact : Json = {
            "transaction": Json(id),
            "reason": "candidate-invalid-or-source-unavailable",
            "sourceClosed": false,
          }
          unresolved.push(fact)
          audit.push({
            "check": Json(checks),
            "transaction": Json(id),
            "accepted": false,
            "result": fact,
          })
        }
        Some((next, relative_origins)) => {
          let (result_status, _, graph_complete) = classify(next)
          let source_closed = original_source_closed &&
            original_sequence_window_closed &&
            graph_complete &&
            v4_reduction_source_closed(next)
          audit.push({
            "check": Json(checks),
            "transaction": Json(id),
            "accepted": Json(result_status == "refuted" && source_closed),
            "classificationStatus": Json(result_status),
            "sourceClosed": Json(source_closed),
          })
          if !source_closed {
            unresolved.push({
              "transaction": Json(id),
              "reason": "candidate-source-open",
              "classificationStatus": Json(result_status),
              "sourceClosed": false,
            })
          } else if result_status == "refuted" {
            let old_sequences = v4_source_sequences(current)
            let old_origins : Map[String, Json] = Map([])
            for index, sequence in old_sequences {
              old_origins[sequence.stringify()] = origins[index]
            }
            origins = relative_origins.map(sequence => {
              old_origins.at(sequence.stringify())
            })
            current = next
            removed.push(id)
            changed = true
            complete_pass = false
            unresolved = []
            break
          } else if result_status != "checked-compatible" {
            unresolved.push({
              "transaction": Json(id),
              "reason": Json(result_status),
              "sourceClosed": Json(v4_reduction_source_closed(next)),
            })
          }
        }
      }
    }
    one_minimal = complete_pass && unresolved.is_empty()
  }
  if changed && checks >= max_checks {
    budget_exhausted = true
  }
  let (final_status, final_report, final_graph_complete) = classify(current)
  let final_source_closed = original_sequence_window_closed &&
    final_graph_complete &&
    v4_reduction_source_closed(current)
  one_minimal = one_minimal && final_source_closed
  if valid && history.data_model == RelationSetV4 && initial_status == "refuted" {
    if final_status != "refuted" {
      status = "invalid"
      one_minimal = false
    } else if one_minimal {
      status = if removed.is_empty() { "unchanged" } else { "reduced" }
    } else if budget_exhausted {
      status = "budget"
    } else {
      status = "undetermined"
    }
  }
  let (semantic, algorithm, profile, counter) = if predicate is Some(_) {
    (
      "relation-predicate-category-transaction-reduction-1", "relation-predicate-single-delete-1",
      "relation-predicate-category-reduction/v4-1", "relation-predicate-candidate-checks-1",
    )
  } else {
    (
      "relation-point-category-transaction-reduction-2", "relation-category-single-delete-2",
      "relation-point-category-reduction/v4-2", "relation-category-candidate-checks-1",
    )
  }
  let record : Json = {
    "format": "moontxnwitness-relation-category-reduction/v4",
    "schemaVersion": 4,
    "semanticContract": Json(semantic),
    "algorithm": Json(algorithm),
    "profile": Json(profile),
    "dataModel": Json(v4_model_name(history.data_model)),
    "preserveCategory": Json(category),
    "status": Json(status),
    "sourceDocument": history.source_document,
    "sourceSha256": Json(v3_dislock_sha256(history.source_text)),
    "history": current.source_document,
    "originalEventSequence": Json(origins),
    "removedTransactions": Json(removed),
    "oneMinimal": Json(one_minimal),
    "oneMinimalScope": "All remaining transaction single deletions completed for the selected source-checked category; unknown, invalid or source-open candidates prevent this claim. No operation or global minimum is claimed.",
    "unresolvedCandidates": Json(unresolved),
    "sourceCoverage": {
      "originalSourceClosed": Json(original_source_closed),
      "originalSequenceWindowClosed": Json(original_sequence_window_closed),
      "reducedSourceClosed": Json(final_source_closed),
    },
    "classification": final_report,
    "execution": {
      "counterContract": Json(counter),
      "candidateChecks": Json(checks),
      "passes": Json(passes),
      "candidateAudit": Json(audit),
      "candidateLimitReached": Json(checks == max_checks),
      "candidateBudgetExhausted": Json(budget_exhausted),
      "initialClassification": true,
      "finalRevalidation": true,
      "limits": {
        "candidateChecks": Json(max_checks),
        "statesPerCandidate": Json(max_states),
        "edgeChecksPerCandidate": Json(max_edge_checks),
        "graphChecksPerCandidate": Json(max_graph_checks),
      },
    },
  }
  if predicate is Some(options) {
    let fields = object_fields_unchecked_v3(record)
    fields["ruleSet"] = Json(scoped_ruleset_name_v4(options.rules))
    let execution = object_fields_unchecked_v3(fields.at("execution"))
    let limits = object_fields_unchecked_v3(execution.at("limits"))
    limits["predicateChecksPerCandidate"] = Json(options.predicates)
    limits["candidateVisitsPerCandidate"] = Json(options.candidates)
    let coverage = object_fields_unchecked_v3(fields.at("sourceCoverage"))
    coverage["originalPredicateGraphComplete"] = Json(initial_graph_complete)
  }
  { history: current, record, }
}

///|
pub fn verify_relation_category_reduction_v4(
  history : HistoryV4,
  supplied : Json,
  category~ : String,
  max_checks~ : Int32 = 256,
  max_states~ : Int32 = 100000,
  max_edge_checks~ : Int32 = 1000000,
  max_graph_checks~ : Int32 = 1000000,
) -> Bool {
  supplied ==
  reduce_relation_category_v4(
    history,
    category~,
    max_checks~,
    max_states~,
    max_edge_checks~,
    max_graph_checks~,
  ).record
}
