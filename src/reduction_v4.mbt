///|
fn v4_reduction_target(history : HistoryV4, preserve : Model) -> String? {
  match history.payload {
    RegisterSnapshot(Some(input), None) =>
      if input.model != preserve {
        None
      } else if preserve == StrictSerializable {
        Some("declared-register-strict-serializable-v1")
      } else {
        Some("register-serializable-v1")
      }
    RegisterSnapshot(_, Some(_)) =>
      if preserve == Serializable {
        Some("register-serializable-v1")
      } else {
        None
      }
    ListSnapshot(_) =>
      if preserve == Serializable {
        Some("append-list-serializable-v1")
      } else {
        None
      }
    RelationSnapshot(_) =>
      if preserve == Serializable {
        Some("relation-set-serializable-v1")
      } else {
        None
      }
    _ => None
  }
}

///|
fn v4_reduction_record(
  original : HistoryV4,
  preserve : Model,
  current : HistoryV4,
  analysis : AnalysisV4,
  options : AnalysisOptionsV4,
  max_checks : Int32,
  status : String,
  checks : Int32,
  cached_checks : Int32,
  minimal : Bool,
  removed : Array[String],
  origins : Array[Json],
  backend : String,
  unresolved~ : Array[Json] = [],
  minimality_rechecks~ : Int32 = 0,
) -> ReductionV4 {
  let predicate = v4_reduction_target(original, preserve)
  let record : Json = {
    "format": "moontxnwitness-reduction/v4",
    "schemaVersion": 4,
    "semanticContract": "moontxnwitness-history-analysis-v4-1",
    "algorithm": "v4-fixed-model-refutation-reduction-1",
    "dataModel": Json(v4_model_name(original.data_model)),
    "status": Json(status),
    "predicate": {
      "modelDefinition": match predicate {
        Some(name) => Json(name)
        None => Json::null()
      },
      "requestedModel": Json(model_label(preserve)),
      "targetSupported": Json(predicate is Some(_)),
      "requiredOutcome": "violation",
    },
    "oneMinimal": Json(minimal),
    "oneMinimalScope": "One-minimality is relative to the fixed source-closed model-refutation predicate. A source-closed undecided candidate prevents this claim. No global or operation minimum is claimed.",
    "source": original.source_document,
    "reducedSource": current.source_document,
    "removedTransactions": Json(removed),
    "retainedOriginalSeq": Json(origins),
    "analysis": analysis.record,
    "execution": {
      "counterContract": "v4-model-reduction-checks-1",
      "backend": Json(backend),
      "maxChecks": Json(max_checks),
      "checks": Json(checks),
      "cachedCandidateChecks": Json(cached_checks),
      "minimalityRechecks": Json(minimality_rechecks),
      "unresolvedCandidates": Json(unresolved),
      "analysisOptions": v4_options_json(options),
      "limits": {
        "declaredRegisterTransactions": 512,
        "declaredRegisterOperations": 10000,
        "registerExactSearchTransactions": 12,
        "registerExactSearchOperations": 512,
        "listRelationExactSearchCommittedTransactions": 6,
        "listRelationExactSearchOperations": 128,
      },
    },
  }
  { history: current, analysis, record, status, checks, one_minimal: minimal, }
}

///|
fn v4_source_sequences(history : HistoryV4) -> Array[Json] {
  match object_fields_unchecked_v3(history.source_document).get("events") {
    Some(Array(events)) =>
      events.map(event => object_fields_unchecked_v3(event).at("seq"))
    _ => []
  }
}

///|
fn v4_capture_transaction_ids(history : HistoryV4) -> Array[String] {
  let normalized = match history.payload {
    RegisterSnapshot(_, Some(n)) => n
    ListSnapshot(parsed) => parsed.normalized
    RelationSnapshot(parsed) => parsed.normalized
    _ => Json::null()
  }
  match normalized {
    Object(fields) =>
      match fields.get("transactions") {
        Some(Array(transactions)) =>
          transactions.map(tx => {
            match object_fields_unchecked_v3(tx).at("id") {
              String(id) => id
              _ => ""
            }
          })
        _ => []
      }
    _ => []
  }
}

///|
fn v4_reduction_source_closed(history : HistoryV4) -> Bool {
  let normalized = match history.payload {
    RegisterSnapshot(Some(input), None) => {
      let writes = collect_writes(input)
      for tx in input.transactions {
        for op in tx.ops {
          if op.kind == Read &&
            input.initial.get(op.key) != Some(op.version) &&
            !writes.get_or_default(op.key, Map([])).contains(op.version) {
            return false
          }
        }
      }
      return true
    }
    RegisterSnapshot(_, Some(n)) => n
    ListSnapshot(parsed) => parsed.normalized
    RelationSnapshot(parsed) => parsed.normalized
    _ => return false
  }
  match object_fields_unchecked_v3(normalized).get("coverage") {
    Some(Object(coverage)) => coverage.get("complete") == Some(Json(true))
    _ => false
  }
}

///|
fn v4_reduction_undecided(id : String, analysis : AnalysisV4) -> Json {
  let fields = object_fields_unchecked_v3(analysis.record)
  let execution = object_fields_unchecked_v3(fields.at("execution"))
  {
    "transaction": Json(id),
    "outcome": Json(outcome_label(analysis.outcome)),
    "sourceClosed": true,
    "execution": v4_select(execution, ["metrics", "reason"]),
  }
}

///|
/// Deletes transactions while preserving raw capture facts and source closure.
/// The predicate is a refutation of the original model, not a selected anomaly.
pub fn reduce_v4(
  history : HistoryV4,
  preserve~ : Model,
  max_checks~ : Int32 = 256,
  options~ : AnalysisOptionsV4 = analysis_options_v4(),
) -> ReductionV4 {
  let mut origins = v4_source_sequences(history)
  let removed : Array[String] = []
  if max_checks < 0 || max_checks > 256 || !v4_options_valid(options) {
    return v4_reduction_record(
      history,
      preserve,
      history,
      analyze_v4(history, options~),
      options,
      max_checks,
      "invalid",
      0,
      0,
      false,
      removed,
      origins,
      "none",
    )
  }
  if v4_reduction_target(history, preserve) is None {
    return v4_reduction_record(
      history,
      preserve,
      history,
      analyze_v4(history, options~),
      options,
      max_checks,
      "unsupported",
      0,
      0,
      false,
      removed,
      origins,
      "none",
    )
  }
  match history.payload {
    RegisterSnapshot(Some(h), None) => {
      let result = reduce_with_options(
        h,
        options=reduction_options(
          max_checks~,
          analysis=analysis_options(
            max_attempts=options.max_attempts,
            max_operation_checks=options.max_operation_checks,
            max_cached_states=options.max_cached_states,
          ),
        ),
      )
      match register_history_v4(result.reduction.history) {
        Ok(reduced) => {
          let verified = analyze_v4(reduced, options~)
          let mut minimal = result.reduction.one_minimal &&
            verified.outcome == Violation
          let mut checks = result.reduction.checks
          let mut rechecks = 0
          let mut contradicted = result.reduction.one_minimal &&
            verified.outcome != Violation
          let unresolved : Array[Json] = []
          if minimal {
            let retained = result.reduction.history
            for index in 0..<retained.transactions.length() {
              if checks >= max_checks {
                minimal = false
                break
              }
              checks += 1
              rechecks += 1
              let candidate_input = without_chunk(retained, index, 1)
              match register_history_v4(candidate_input) {
                Ok(candidate) => {
                  if !v4_reduction_source_closed(candidate) {
                    continue
                  }
                  let outcome = analyze_v4(candidate, options~)
                  if outcome.outcome == Violation {
                    contradicted = true
                    minimal = false
                    break
                  } else if outcome.outcome == Inconclusive ||
                    outcome.outcome == Invalid {
                    unresolved.push(
                      v4_reduction_undecided(
                        retained.transactions[index].id,
                        outcome,
                      ),
                    )
                    minimal = false
                    break
                  }
                }
                Err(_) => ()
              }
            }
          }
          let status = if contradicted {
            "invalid"
          } else if result.reduction.one_minimal && !minimal {
            "budget"
          } else {
            result.reduction.status
          }
          return v4_reduction_record(
            history,
            preserve,
            reduced,
            verified,
            options,
            max_checks,
            status,
            checks,
            result.cached_checks,
            minimal,
            result.reduction.removed,
            [],
            "balanced-register-reducer",
            unresolved~,
            minimality_rechecks=rechecks,
          )
        }
        Err(_) =>
          return v4_reduction_record(
            history,
            preserve,
            history,
            analyze_v4(history, options~),
            options,
            max_checks,
            "invalid",
            result.reduction.checks,
            result.cached_checks,
            false,
            removed,
            origins,
            "balanced-register-reducer",
          )
      }
    }
    _ => ()
  }
  let mut current = history
  let mut analysis = analyze_v4(history, options~)
  if analysis.outcome != Violation {
    return v4_reduction_record(
      history, preserve, current, analysis, options, max_checks, "not-violation",
      0, 0, false, removed, origins, "source-checked-single-delete",
    )
  }
  let mut checks = 0
  let mut minimal = false
  let mut failed = false
  let mut changed = true
  let mut unresolved : Array[Json] = []
  while changed && checks < max_checks {
    changed = false
    unresolved = []
    let ids = v4_capture_transaction_ids(current)
    let mut completed_pass = true
    for id in ids {
      if checks >= max_checks {
        completed_pass = false
        break
      }
      checks += 1
      let candidate = try {
        let (source, relative_origins) = v3_without_transaction(
          current.source_document,
          id,
        )
        match parse_history_v4(source.stringify()) {
          Ok(candidate) => Some((candidate, relative_origins))
          Err(_) => None
        }
      } catch {
        _ => None
      }
      match candidate {
        Some((candidate, relative_origins)) => {
          let result = analyze_v4(candidate, options~)
          if result.outcome == Violation {
            let old_sequences = v4_source_sequences(current)
            let old_origins : Map[String, Json] = Map([])
            for index, sequence in old_sequences {
              old_origins[sequence.stringify()] = origins[index]
            }
            let next_origins = relative_origins.map(sequence => {
              old_origins.at(sequence.stringify())
            })
            origins = next_origins
            current = candidate
            analysis = result
            removed.push(id)
            changed = true
            completed_pass = false
            unresolved = []
            break
          } else if v4_reduction_source_closed(candidate) &&
            (result.outcome == Inconclusive || result.outcome == Invalid) {
            unresolved.push(v4_reduction_undecided(id, result))
          }
        }
        None => ()
      }
    }
    if completed_pass && unresolved.is_empty() {
      minimal = true
    }
  }
  // Revalidation is mandatory even when no candidate could be accepted.
  let verified = analyze_v4(current, options~)
  if verified.outcome != Violation {
    failed = true
    minimal = false
  }
  analysis = verified
  let status = if failed {
    "invalid"
  } else if !minimal {
    "budget"
  } else if removed.is_empty() {
    "unchanged"
  } else {
    "reduced"
  }
  v4_reduction_record(
    history,
    preserve,
    current,
    analysis,
    options,
    max_checks,
    status,
    checks,
    0,
    minimal,
    removed,
    origins,
    "source-checked-single-delete",
    unresolved~,
  )
}

///|
pub fn reduction_v4_json(result : ReductionV4) -> Json {
  v4_json_copy(result.record)
}

///|
pub fn render_reduction_v4(result : ReductionV4) -> String {
  result.record.stringify(indent=2)
}

///|
pub fn verify_reduction_v4(
  history : HistoryV4,
  supplied : Json,
  preserve~ : Model,
  max_checks~ : Int32 = 256,
  options~ : AnalysisOptionsV4 = analysis_options_v4(),
) -> Bool {
  supplied == reduce_v4(history, preserve~, max_checks~, options~).record
}
