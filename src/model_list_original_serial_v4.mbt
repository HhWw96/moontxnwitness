///|
/// Explicit whole-model SER alternative. It does not install a writer order in
/// ModelSourceV4 and is never consulted by another canonical model.
fn model_list_original_serial_policy_v4(
  history : HistoryV4,
  options : ModelOptionsV4,
) -> Bool {
  if options.list_profile != ModelListOriginalSerial {
    return false
  }
  match history.payload {
    ListSnapshot(_) => true
    _ => false
  }
}

///|
fn model_list_original_serial_record_v4(
  history : HistoryV4,
  options : ModelOptionsV4,
  status : String,
  reason : String,
  source_checks : Int32,
  search_states : Int32,
  search_checks : Int32,
  replay_checks : Int32,
  proof : Json,
) -> ModelRuleV4 {
  model_rule_v4("whole-model/original-list-serializable", status, reason, evidence={
    "format": "moontxnwitness-original-list-serial-decision/v4",
    "semanticContract": "closed-original-list-serializable-bounded-decision/v1",
    "algorithm": "original-list-serial-enumeration-and-replay-1",
    "originalHistorySha256": Json(v3_dislock_sha256(history.source_text)),
    "originalHistoryLocation": "observations.history",
    "canonicalModel": "serializable",
    "sourceOrderInstalled": false,
    "derivedOrderIsCapturedFact": false,
    "otherModelVerdictsInferred": false,
    "sourceFactsProduced": false,
    "sourceAuthenticated": false,
    "proof": proof,
    "execution": {
      "counterContract": "original-list-source-search-replay-semantic-checks-1",
      "sourceChecks": Json(source_checks),
      "searchStates": Json(search_states),
      "searchOperationChecks": Json(search_checks),
      "replayChecks": Json(replay_checks),
      "semanticChecks": Json(source_checks + search_checks + replay_checks),
      "maxStates": Json(options.max_states),
      "maxSourceChecks": Json(options.max_source_checks),
      "maxEdgeChecks": Json(options.max_edge_checks),
      "semanticLimit": Json(
        if options.max_source_checks < options.max_edge_checks {
          options.max_source_checks
        } else {
          options.max_edge_checks
        },
      ),
      "committedTransactionCapacity": 6,
      "programActionCapacity": 128,
    },
    "scope": "one bounded, complete committed original append/read/savepoint program SER decision; no SI, weaker-model, real-time, physical database or observer-authenticity conclusion",
  })
}

///|
fn model_list_original_serial_rule_v4(
  history : HistoryV4,
  options : ModelOptionsV4,
) -> ModelRuleV4 {
  let maximum = if options.max_source_checks < options.max_edge_checks {
    options.max_source_checks
  } else {
    options.max_edge_checks
  }
  let budget : ModelSourceBudgetV4 = { maximum, checks: 0, limited: false, }
  let unknown = fn(reason : String, proof : Json) {
    model_list_original_serial_record_v4(
      history,
      options,
      "unknown",
      reason,
      budget.checks,
      0,
      0,
      0,
      proof,
    )
  }
  if !model_list_original_serial_policy_v4(history, options) ||
    options.completion_policy != ModelObservationOnlyCompletion {
    return unknown(
      "explicit original-list serial policy and transaction-observation completion are required; given logical snapshots remain unsupported",
      Json::null(),
    )
  }
  let parsed = match history.payload {
    ListSnapshot(p) => p
    _ =>
      return unknown(
        "only original append-list programs are supported",
        Json::null(),
      )
  }
  let n = object_fields_unchecked_v3(parsed.normalized)
  let coverage = object_fields_unchecked_v3(n.at("coverage"))
  if n.at("status") != Json("ready") ||
    coverage.at("complete") != Json(true) ||
    !capture_source_array_v4(coverage.at("gaps")).is_empty() ||
    !parsed.findings.is_empty() {
    return unknown(
      "complete identity-valid original source is required; existing direct source findings remain in the graph route",
      { "coverage": Json(coverage), "findings": Json(parsed.findings) },
    )
  }
  // Never delete an unknown statement and relabel the remaining capture closed.
  // The raw-event check is deliberately stricter than SQL-adapter applicability.
  let root = object_fields_unchecked_v3(history.source_document)
  let events = capture_source_array_v4(root.at("events"))
  let mut expected_seq = 1L
  let mut actions = 0
  for raw in events {
    if !model_source_charge_v4(budget) {
      return unknown(
        "original source scan exhausted the semantic budget",
        Json::null(),
      )
    }
    let e = object_fields_unchecked_v3(raw)
    if capture_source_seq_v4(e.at("seq")) != expected_seq {
      return unknown("original sequence window is not contiguous", Json::null())
    }
    expected_seq += 1L
    let kind = capture_source_string_v4(e.at("kind"))
    if ![
        "snapshot", "begin", "append", "list_read", "savepoint", "rollback_to", "release",
        "commit_request", "commit_ok", "rollback_ok",
      ].contains(kind) {
      return unknown(
        "unsupported original operation cannot be erased by a serial completion",
        { "actualEvent": raw },
      )
    }
    if ["append", "list_read", "savepoint", "rollback_to", "release"].contains(
        kind,
      ) {
      actions += 1
    }
  }
  let window = capture_window_v5(history, parsed.normalized, fn() {
    model_source_charge_v4(budget)
  })
  if !window.complete || window.unlocated || budget.limited {
    return unknown(
      "original capture window is not proved complete",
      Json::null(),
    )
  }
  let committed = parsed.programs.filter(p => p.status == Committed)
  for program in parsed.programs {
    if !model_source_charge_v4(budget) ||
      program.status == Unknown ||
      !window.closed.get_or_default(program.id, false) {
      return unknown(
        "every original transaction needs a closed confirmed outcome",
        Json::null(),
      )
    }
  }
  // Count savepoint actions as well as data actions for this new exact route.
  if committed.length() > 6 || actions > 128 || parsed.operations > 128 {
    return unknown("original-list exact capacity exceeded", {
      "committedTransactions": Json(committed.length()),
      "programActions": Json(actions),
      "dataOperations": Json(parsed.operations),
    })
  }
  if maximum - budget.checks <= 0 {
    return unknown(
      "no semantic budget remains for original-list search",
      Json::null(),
    )
  }
  let source_checks = budget.checks
  // Reuse the unchanged bounded raw-program interpreter/search. It imports no
  // native graph, inferred WW order, prefix-state projection or supplied report.
  let searched = list_v3_analyze_parsed(parsed, {
    max_states: options.max_states,
    max_operations: maximum - source_checks,
  }) catch {
    error =>
      return unknown(
        "original-list search rejected input: " + error.to_string(),
        Json::null(),
      )
  }
  let search = object_fields_unchecked_v3(searched)
  let metrics = object_fields_unchecked_v3(
    object_fields_unchecked_v3(search.at("execution")).at("metrics"),
  )
  let states = capture_source_seq_v4(metrics.at("states")).to_int()
  let checks = capture_source_seq_v4(metrics.at("operationChecks")).to_int()
  let evidence = object_fields_unchecked_v3(search.at("evidence"))
  let complete = metrics.at("complete") == Json(true)
  if !complete || source_checks + checks > maximum {
    return model_list_original_serial_record_v4(
      history,
      options,
      "unknown",
      "original-list serial search is incomplete; no unsatisfiability claim",
      source_checks,
      states,
      checks,
      0,
      {
        "searchReason": metrics.at("reason"),
        "sampleBlockers": evidence.get_or_default(
          "sampleBlockers",
          Json::null(),
        ),
      },
    )
  }
  if search.at("status") == Json("violation") &&
    metrics.at("reason") == Json("exhausted") &&
    evidence.at("kind") == Json("bounded-serial-exhaustion") {
    return model_list_original_serial_record_v4(
      history,
      options,
      "refuted",
      "complete bounded enumeration found no serial execution of these original committed list programs; only canonical serializable is refuted",
      source_checks,
      states,
      checks,
      0,
      {
        "kind": "complete-original-program-serial-exhaustion",
        "legacySearchAlgorithm": "v3-list-1",
        "sampleBlockers": evidence.get_or_default(
          "sampleBlockers",
          Json::null(),
        ),
      },
    )
  }
  if search.at("status") != Json("consistent") ||
    metrics.at("reason") != Json("found") ||
    evidence.at("kind") != Json("serial-list-replay") {
    return model_list_original_serial_record_v4(
      history,
      options,
      "unknown",
      "no complete original-list serial decision was produced",
      source_checks,
      states,
      checks,
      0,
      Json::null(),
    )
  }
  let order = capture_source_array_v4(evidence.at("serialOrder")).map(raw => {
    capture_source_string_v4(raw)
  })
  budget.checks = source_checks + checks
  let visibility : Array[Json] = []
  for rank, tx in order {
    let seen : Array[String] = []
    for i in 0..<rank {
      if !model_source_charge_v4(budget) {
        return model_list_original_serial_record_v4(
          history,
          options,
          "unknown",
          "serial certificate construction exhausted semantic budget",
          budget.checks - checks,
          states,
          checks,
          0,
          Json::null(),
        )
      }
      seen.push(order[i])
    }
    visibility.push({
      "transaction": Json(tx),
      "visiblePrefixLength": Json(rank),
      "visibleTransactions": Json(seen),
    })
  }
  let certificate_checks = budget.checks - source_checks - checks
  let remaining = maximum - source_checks - checks - certificate_checks
  if remaining <= 0 {
    return model_list_original_serial_record_v4(
      history,
      options,
      "unknown",
      "no semantic budget remains for fresh original-program serial certificate replay",
      source_checks + certificate_checks,
      states,
      checks,
      0,
      Json::null(),
    )
  }
  let replay = model_list_certificate_replay_v4(
    parsed, order, visibility, remaining,
  )
  let replay_execution = object_fields_unchecked_v3(
    object_fields_unchecked_v3(replay.evidence).at("execution"),
  )
  let replay_checks = capture_source_seq_v4(replay_execution.at("checks")).to_int()
  let valid = replay.status == "checked-compatible" &&
    source_checks + certificate_checks + checks + replay_checks <= maximum
  model_list_original_serial_record_v4(
    history,
    options,
    if valid {
      "checked-compatible"
    } else {
      "unknown"
    },
    if valid {
      "one complete serial order is freshly replayed against every original append/read/savepoint; its full CO/VIS prefixes are derived proof, never observed writer-order facts"
    } else {
      "serial certificate did not replay completely under remaining independent semantic budget"
    },
    source_checks + certificate_checks,
    states,
    checks,
    replay_checks,
    {
      "kind": "fresh-original-list-serial-certificate",
      "certificate": {
        "commitOrder": Json(order),
        "visibilityPrefixes": Json(visibility),
      },
      "originalProgramReplay": model_rule_json_v4(replay),
      "legacySearchAlgorithm": "v3-list-1",
      "captureFactsAdded": false,
    },
  )
}
