///|
/// A derived transaction selection preserving one explicit relation model refutation.
pub struct RelationModelReductionV4 {
  priv facts : ModelFactsV4
  priv record : Json
}

///|
pub fn RelationModelReductionV4::facts(
  self : RelationModelReductionV4,
) -> ModelFactsV4 {
  self.facts
}

///|
pub fn relation_model_reduction_v4_json(
  result : RelationModelReductionV4,
) -> Json {
  v4_json_copy(result.record)
}

///|
fn rmr_selected_facts_v4(
  original : ModelFactsV4,
  history : HistoryV4,
) -> ModelFactsV4 {
  let ids = v4_capture_transaction_ids(history)
  let clients = original.clients.map(client => {
    (
      {
        id: client.id,
        transactions: client.transactions.filter(tx => ids.contains(tx)),
      } : ModelClientV4)
  })
  model_facts_v4(history, clients~, clients_complete=original.clients_complete).unwrap()
}

///|
/// Dense candidate indices are derived; all non-index original facts must match.
fn rmr_original_selection_v4(
  original : HistoryV4,
  candidate : HistoryV4,
  origins : Array[Json],
) -> Bool {
  let original_root = object_fields_unchecked_v3(original.source_document)
  let candidate_root = object_fields_unchecked_v3(candidate.source_document)
  let original_events = capture_source_array_v4(original_root.at("events"))
  let candidate_events = capture_source_array_v4(candidate_root.at("events"))
  if candidate_events.length() != origins.length() ||
    original_root.length() != candidate_root.length() {
    return false
  }
  for name, value in original_root {
    if name != "events" && candidate_root.get(name) != Some(value) {
      return false
    }
  }
  let originals : Map[String, Json] = Map([])
  let positions : Map[String, Int32] = Map([])
  for i, event in original_events {
    let seq = object_fields_unchecked_v3(event).at("seq").stringify()
    originals[seq] = event
    positions[seq] = i
  }
  let references : Map[String, Json] = Map([])
  for i, event in candidate_events {
    references[object_fields_unchecked_v3(event).at("seq").stringify()] = origins[i]
  }
  let mut last = -1
  for i, event in candidate_events {
    let key = origins[i].stringify()
    let position = positions.get_or_default(key, -1)
    if position <= last {
      return false
    }
    last = position
    let restored = v4_json_copy(event)
    let fields = object_fields_unchecked_v3(restored)
    fields["seq"] = origins[i]
    match fields.get("statement") {
      Some(seq) =>
        match references.get(seq.stringify()) {
          Some(origin) => fields["statement"] = origin
          None => return false
        }
      None => ()
    }
    match fields.get("commitResponse") {
      Some(Object(response)) =>
        match references.get(response.at("request").stringify()) {
          Some(origin) => response["request"] = origin
          None => return false
        }
      Some(_) => return false
      None => ()
    }
    if originals.get(key) != Some(restored) {
      return false
    }
  }
  true
}

///|
fn rmr_classify_v4(
  facts : ModelFactsV4,
  options : ModelOptionsV4,
  realtime_known : Bool,
) -> (String, Json) {
  match classify_relation_models_v4(facts, options, realtime_known~) {
    Ok(report) =>
      (
        capture_source_string_v4(
          object_fields_unchecked_v3(report.record).at("status"),
        ),
        report.record,
      )
    Err(reason) => ("unknown", { "status": "unknown", "reason": Json(reason) })
  }
}

///|
pub fn reduce_relation_models_v4(
  facts : ModelFactsV4,
  target : ElleModelV4,
  options : ModelOptionsV4,
  max_checks~ : Int32 = 256,
  realtime_known~ : Bool = true,
) -> RelationModelReductionV4 {
  let selected_options : ModelOptionsV4 = { ..options, models: [target], }
  let original = facts.history
  let original_closed = original.data_model == RelationSetV4 &&
    v4_reduction_source_closed(original)
  let sequence_closed = original.data_model == RelationSetV4 &&
    relation_reduction_sequence_window_v4(original)
  let valid = max_checks >= 0 && max_checks <= 256
  let (initial_status, initial_report) = rmr_classify_v4(
    facts, selected_options, realtime_known,
  )
  let mut current = facts
  let mut origins = v4_source_sequences(original)
  let removed : Array[String] = []
  let audit : Array[Json] = []
  let mut unresolved : Array[Json] = []
  let mut checks = 0
  let mut passes = 0
  let mut one_minimal = false
  let mut budget_exhausted = false
  let mut changed = valid &&
    original_closed &&
    sequence_closed &&
    initial_status == "refuted"
  while changed {
    if checks >= max_checks {
      budget_exhausted = true
      break
    }
    changed = false
    passes += 1
    unresolved = []
    let mut full_pass = true
    for id in v4_capture_transaction_ids(current.history) {
      if checks >= max_checks {
        full_pass = false
        budget_exhausted = true
        break
      }
      checks += 1
      let candidate = try {
        let (view, relative_origins) = v3_without_transaction(
          current.history.source_document,
          id,
        )
        match parse_history_v4(view.stringify()) {
          Err(_) => None
          Ok(history) => {
            let by_seq : Map[String, Json] = Map([])
            for i, seq in v4_source_sequences(current.history) {
              by_seq[seq.stringify()] = origins[i]
            }
            let candidate_origins = relative_origins.map(seq => {
              by_seq.at(seq.stringify())
            })
            Some((rmr_selected_facts_v4(facts, history), candidate_origins))
          }
        }
      } catch {
        _ => None
      }
      match candidate {
        None => {
          let finding : Json = {
            "transaction": Json(id),
            "reason": "invalid-derived-selection",
            "sourceClosed": false,
          }
          unresolved.push(finding)
          audit.push({
            "check": Json(checks),
            "transaction": Json(id),
            "accepted": false,
            "result": finding,
          })
        }
        Some((next, candidate_origins)) => {
          let origins_checked = rmr_original_selection_v4(
            original,
            next.history,
            candidate_origins,
          )
          let source_closed = original_closed &&
            sequence_closed &&
            origins_checked &&
            v4_reduction_source_closed(next.history)
          let (status, _) = rmr_classify_v4(
            next, selected_options, realtime_known,
          )
          let accept = source_closed && status == "refuted"
          audit.push({
            "check": Json(checks),
            "transaction": Json(id),
            "accepted": Json(accept),
            "targetModel": Json(model_name_v4(target)),
            "classificationStatus": Json(status),
            "sourceClosed": Json(source_closed),
            "originalFactsChecked": Json(origins_checked),
          })
          if accept {
            current = next
            origins = candidate_origins
            removed.push(id)
            changed = true
            full_pass = false
            unresolved = []
            break
          }
          if !source_closed || status != "checked-compatible" {
            unresolved.push({
              "transaction": Json(id),
              "reason": Json(
                if !source_closed {
                  "source-open"
                } else {
                  status
                },
              ),
              "classificationStatus": Json(status),
              "sourceClosed": Json(source_closed),
            })
          }
        }
      }
    }
    one_minimal = full_pass && unresolved.is_empty()
  }
  // Initial and final validation do not spend the transaction-deletion budget.
  // The final report is always recomputed, including zero/exhausted budgets.
  let (final_status, final_report) = rmr_classify_v4(
    current, selected_options, realtime_known,
  )
  let final_closed = original_closed &&
    sequence_closed &&
    v4_reduction_source_closed(current.history) &&
    rmr_original_selection_v4(original, current.history, origins)
  one_minimal = one_minimal &&
    valid &&
    final_closed &&
    final_status == "refuted"
  let status = if !valid {
    "invalid"
  } else if original.data_model != RelationSetV4 {
    "unsupported"
  } else if initial_status != "refuted" {
    if initial_status == "checked-compatible" {
      "not-refuted"
    } else {
      "unknown"
    }
  } else if final_status != "refuted" {
    "invalid"
  } else if one_minimal {
    if removed.is_empty() {
      "unchanged"
    } else {
      "reduced"
    }
  } else if budget_exhausted {
    "budget"
  } else {
    "undetermined"
  }
  let original_events = capture_source_array_v4(
    object_fields_unchecked_v3(original.source_document).get_or_default(
      "events",
      Json(([] : Array[Json])),
    ),
  )
  let selected_original_events = original_events.filter(event => {
    origins.contains(object_fields_unchecked_v3(event).at("seq"))
  })
  {
    facts: current,
    record: {
      "format": "moontxnwitness-relation-model-reduction/v4",
      "schemaVersion": 4,
      "semanticContract": "relation-predicate-model-reduction/v1",
      "classificationContract": "relation-predicate-models/v1",
      "algorithm": "source-closed-single-delete-fixed-relation-model-1",
      "status": Json(status),
      "preserveModel": Json(model_name_v4(target)),
      "requiredOutcome": "refuted",
      "sourceSha256": Json(facts.source_sha256),
      "sourcePolicy": { "realtimeKnown": Json(realtime_known) },
      "originalFacts": facts.source_record,
      "selectedTransactions": Json(v4_capture_transaction_ids(current.history)),
      "selectedOriginalEvents": Json(selected_original_events),
      "originalEventSequence": Json(origins),
      "analysisView": current.source_record,
      "analysisViewSemantics": "derived dense event indices with checked original references; never new capture facts, version orders or inferred snapshots",
      "removedTransactions": Json(removed),
      "oneMinimal": Json(one_minimal),
      "oneMinimalScope": "Every remaining transaction single deletion completed with closed original sources and the selected model; unknown, source-open or invalid candidates prevent one-minimality. No operation or global minimum is claimed.",
      "unresolvedCandidates": Json(unresolved),
      "sourceCoverage": {
        "originalSourceClosed": Json(original_closed),
        "originalSequenceWindowClosed": Json(sequence_closed),
        "reducedSourceClosed": Json(final_closed),
      },
      "initialClassification": initial_report,
      "classification": final_report,
      "execution": {
        "counterContract": "relation-model-single-delete-candidate-checks-1",
        "candidateChecks": Json(checks),
        "passes": Json(passes),
        "maxChecks": Json(max_checks),
        "candidateLimitReached": Json(checks == max_checks),
        "candidateBudgetExhausted": Json(budget_exhausted),
        "candidateAudit": Json(audit),
        "finalRevalidation": true,
        "suppliedOptions": model_options_record_v4(options),
        "classificationOptions": model_options_record_v4(selected_options),
      },
    },
  }
}

///|
pub fn verify_relation_model_reduction_v4(
  facts : ModelFactsV4,
  supplied : Json,
  target : ElleModelV4,
  options : ModelOptionsV4,
  max_checks~ : Int32 = 256,
  realtime_known~ : Bool = true,
) -> Bool {
  supplied ==
  reduce_relation_models_v4(
    facts,
    target,
    options,
    max_checks~,
    realtime_known~,
  ).record
}
