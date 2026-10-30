///|
fn v4_model_name(model : DataModelV4) -> String {
  match model {
    RegisterV4 => "point-register-v1"
    AppendListV4 => "append-list-v1"
    RelationSetV4 => "relation-set-v1"
  }
}

///|
/// Clone containers without an encode/decode pass; scalar values are immutable.
fn v4_json_copy(value : Json) -> Json {
  match value {
    Object(fields) => {
      let copy : Map[String, Json] = Map([])
      for key, item in fields {
        copy[key] = v4_json_copy(item)
      }
      Json::object(copy)
    }
    Array(items) => Json(items.map(v4_json_copy))
    _ => value
  }
}

///|
fn v4_history_copy(history : History) -> History {
  let initial : Map[String, String] = Map([])
  let orders : Map[String, Array[String]] = Map([])
  for key, value in history.initial {
    initial[key] = value
  }
  for key, values in history.version_orders {
    orders[key] = values.copy()
  }
  {
    model: history.model,
    initial,
    version_orders: orders,
    transactions: history.transactions.map(tx => { ..tx, ops: tx.ops.copy(), }),
  }
}

///|
/// The constructor accepts a caller-declared history, not authenticated capture.
pub fn register_history_v4(history : History) -> Result[HistoryV4, String] {
  let snapshot = v4_history_copy(history)
  let errors = validate_history(snapshot)
  if !errors.is_empty() {
    return Err(errors[0].message)
  }
  let source = history_json(snapshot)
  Ok({
    data_model: RegisterV4,
    source_text: source.stringify(),
    source_document: source,
    source_format: "declared-history/v1",
    payload: RegisterSnapshot(Some(snapshot), None),
  })
}

///|
fn v4_normalized_valid(normalized : Json) -> Unit raise {
  let fields = object_fields(normalized, "normalization")
  if fields.get("status") == Some(Json("invalid")) {
    fail("Invalid captured history")
  }
}

///|
/// Parse once at the boundary, then retain model-specific validated structures.
/// Capture syntax is the existing v3 wire contract; v4 is a separate report API.
pub fn parse_history_v4(text : String) -> Result[HistoryV4, String] {
  try {
    let source = guarded_json(text, limit=8388608)
    let fields = object_fields(source, "history v4 source")
    if fields.contains("traceSchema") {
      if fields.get("traceSchema") != Some(Json(3)) {
        fail("Only traceSchema 3 captures are accepted")
      }
      match fields.get("dataModel") {
        Some(String("append-list-v1")) => {
          let parsed = list_v3_parse(text)
          v4_normalized_valid(parsed.normalized)
          Ok({
            data_model: AppendListV4,
            source_text: text,
            source_document: source,
            source_format: "capture/v3",
            payload: ListSnapshot(parsed),
          })
        }
        Some(String("relation-set-v1")) => {
          let parsed = relation_v3_parse(text, v=source)
          v4_normalized_valid(parsed.normalized)
          Ok({
            data_model: RelationSetV4,
            source_text: text,
            source_document: source,
            source_format: "capture/v3",
            payload: RelationSnapshot(parsed),
          })
        }
        None | Some(String("point-register-v1")) => {
          let normalized = guarded_json(
            normalize_register_capture_v3_json(text),
            limit=33554432,
          )
          v4_normalized_valid(normalized)
          let n = object_fields(normalized, "normalized capture")
          let projected = if n.get("status") == Some(Json("ready")) {
            match parse_history_optimized(n.at("history").stringify()) {
              Ok(history) => Some(history)
              Err(reason) => fail("Invalid register projection: " + reason)
            }
          } else {
            None
          }
          Ok({
            data_model: RegisterV4,
            source_text: text,
            source_document: source,
            source_format: "capture/v3",
            payload: RegisterSnapshot(projected, Some(normalized)),
          })
        }
        _ => fail("Unsupported or mixed v4 data model")
      }
    } else {
      match parse_history_optimized(text) {
        Ok(history) => {
          let errors = validate_history(history)
          if !errors.is_empty() {
            fail(errors[0].message)
          }
          Ok({
            data_model: RegisterV4,
            source_text: text,
            source_document: source,
            source_format: "declared-history/v1",
            payload: RegisterSnapshot(Some(history), None),
          })
        }
        Err(reason) => fail(reason)
      }
    }
  } catch {
    error => Err(error.to_string())
  }
}

///|
/// A detached JSON view; mutating it cannot change future analysis or replay.
pub fn history_v4_json(history : HistoryV4) -> Json {
  v4_json_copy(history.source_document)
}

///|
fn v4_options_json(options : AnalysisOptionsV4) -> Json {
  {
    "maxAttempts": Json(options.max_attempts),
    "maxStates": Json(options.max_states),
    "maxOperationChecks": Json(options.max_operation_checks),
    "maxCachedStates": Json(options.max_cached_states),
  }
}

///|
fn v4_options_valid(options : AnalysisOptionsV4) -> Bool {
  options.max_states >= 0 &&
  options.max_states <= 100000 &&
  valid_analysis_options({
    max_attempts: options.max_attempts,
    max_operation_checks: options.max_operation_checks,
    max_cached_states: options.max_cached_states,
  })
}

///|
fn v4_outcome(value : Json) -> Outcome {
  match value {
    String("consistent") => Consistent
    String("violation") => Violation
    String("inconclusive") => Inconclusive
    _ => Invalid
  }
}

///|
fn v4_select(fields : Map[String, Json], names : Array[String]) -> Json {
  let result : Map[String, Json] = Map([])
  for name in names {
    match fields.get(name) {
      Some(value) => result[name] = value
      None => ()
    }
  }
  Json::object(result)
}

///|
fn v4_declared_effects(history : History) -> Json {
  let writes : Array[Json] = []
  for tx in history.transactions {
    for index, op in tx.ops {
      if op.kind == Write {
        writes.push({
          "transaction": Json(tx.id),
          "operation": Json(index),
          "key": Json(op.key),
          "version": Json(op.version),
          "outcome": Json(status_label(tx.status)),
        })
      }
    }
  }
  { "basis": "caller-declared-programs", "entries": Json(writes) }
}

///|
fn v4_record(
  history : HistoryV4,
  options : AnalysisOptionsV4,
  outcome : Outcome,
  effects : Json,
  inferences : Json,
  judgment : Json,
  execution : Json,
) -> AnalysisV4 {
  let execution = object_fields_unchecked_v3(execution)
  execution["requestedOptions"] = v4_options_json(options)
  execution["counterContract"] = Json(
    match history.data_model {
      RegisterV4 => "bounded-register-v2.1-counters"
      AppendListV4 => "v3-list-1-counters"
      RelationSetV4 => "v3-relation-1-counters"
    },
  )
  let record : Json = {
    "format": "moontxnwitness-analysis/v4",
    "schemaVersion": 4,
    "tool": "MoonTxnWitness",
    "semanticContract": "moontxnwitness-history-analysis-v4-1",
    "algorithm": "typed-snapshot-analysis-1",
    "dataModel": Json(v4_model_name(history.data_model)),
    "observations": {
      "sourceFormat": Json(history.source_format),
      "authenticityVerified": false,
      "document": history.source_document,
    },
    "writeEffects": effects,
    "inferences": inferences,
    "judgment": judgment,
    "execution": Json::object(execution),
  }
  { data_model: history.data_model, outcome, record, }
}

///|
fn v4_register_analysis(
  history : HistoryV4,
  input : History?,
  normalized : Json?,
  options : AnalysisOptionsV4,
) -> AnalysisV4 {
  let actual : AnalysisOptions = {
    max_attempts: options.max_attempts,
    max_operation_checks: options.max_operation_checks,
    max_cached_states: options.max_cached_states,
  }
  let effects : Json = match normalized {
    Some(n) =>
      {
        "basis": "captured-write-effects",
        "entries": object_fields_unchecked_v3(n).get_or_default(
          "effects",
          Json(([] : Array[Json])),
        ),
      }
    None =>
      match input {
        Some(h) => v4_declared_effects(h)
        None => Json::null()
      }
  }
  let coverage : Json = match normalized {
    Some(n) =>
      object_fields_unchecked_v3(n).get_or_default("coverage", Json::null())
    None =>
      {
        "basis": "caller-declared-history",
        "externalCompletenessVerified": false,
        "gaps": [],
      }
  }
  match input {
    None => {
      let n = object_fields_unchecked_v3(normalized.unwrap())
      let outcome = v4_outcome(n.get_or_default("status", Json("invalid")))
      v4_record(
        history,
        options,
        outcome,
        effects,
        Json::null(),
        {
          "status": Json(outcome_label(outcome)),
          "coverage": coverage,
          "evidence": Json::null(),
        },
        {
          "analysisOptions": {
            "maxAttempts": Json(actual.max_attempts),
            "maxOperationChecks": Json(actual.max_operation_checks),
            "maxCachedStates": Json(actual.max_cached_states),
          },
          "effectiveLimits": effective_limits(actual),
          "metrics": { "attempts": 0, "operationChecks": 0 },
          "reason": "coverage_gap",
        },
      )
    }
    Some(h) => {
      let result = analyze_with_options(h, options=actual)
      let report = object_fields_unchecked_v3(analysis_result_json(result))
      v4_record(
        history,
        options,
        result.report.outcome,
        effects,
        v4_select(report, ["versionOrders", "versionOrderSources"]),
        {
          "status": Json(outcome_label(result.report.outcome)),
          "modelDefinition": {
            "id": Json(
              if h.model == StrictSerializable {
                "declared-register-strict-serializable-v1"
              } else {
                "register-serializable-v1"
              },
            ),
            "scope": "supplied unique-version point-read/write facts and declared order constraints",
          },
          "coverage": coverage,
          "evidence": v4_select(report, [
            "complete", "stats", "findings", "edges", "witness", "serialOrder", "graph",
            "coverage", "search",
          ]),
        },
        {
          "analysisOptions": report.at("analysisOptions"),
          "effectiveLimits": report.at("effectiveLimits"),
          "metrics": report.at("metrics"),
        },
      )
    }
  }
}

///|
/// Reuses retained parsed programs and creates fresh reversible search state.
pub fn analyze_v4(
  history : HistoryV4,
  options~ : AnalysisOptionsV4 = analysis_options_v4(),
) -> AnalysisV4 {
  if !v4_options_valid(options) {
    return v4_record(
      history,
      options,
      Invalid,
      Json::null(),
      Json::null(),
      {
        "status": "invalid",
        "code": "invalid_options",
        "evidence": Json::null(),
      },
      {
        "effectiveLimits": Json::null(),
        "metrics": { "states": 0, "operationChecks": 0 },
      },
    )
  }
  try {
    match history.payload {
      RegisterSnapshot(input, normalized) =>
        v4_register_analysis(history, input, normalized, options)
      ListSnapshot(parsed) =>
        v4_model_analysis(
          history,
          list_v3_analyze_parsed(parsed, {
            max_states: options.max_states,
            max_operations: options.max_operation_checks,
          }),
          parsed.normalized,
          options,
        )
      RelationSnapshot(parsed) =>
        v4_model_analysis(
          history,
          relation_v3_analyze_parsed(parsed, {
            max_states: options.max_states,
            max_operations: options.max_operation_checks,
          }),
          parsed.normalized,
          options,
        )
    }
  } catch {
    _ =>
      v4_record(
        history,
        options,
        Invalid,
        Json::null(),
        Json::null(),
        {
          "status": "invalid",
          "code": "invalid_analysis_state",
          "evidence": Json::null(),
        },
        {
          "effectiveLimits": Json::null(),
          "metrics": { "states": 0, "operationChecks": 0 },
        },
      )
  }
}

///|
fn v4_model_analysis(
  history : HistoryV4,
  report : Json,
  normalized : Json,
  options : AnalysisOptionsV4,
) -> AnalysisV4 {
  let report = object_fields_unchecked_v3(report)
  let n = object_fields_unchecked_v3(normalized)
  let evidence = report.at("evidence")
  let inferred = match evidence {
    Object(fields) => fields.get_or_default("serialOrder", Json::null())
    _ => Json::null()
  }
  v4_record(
    history,
    options,
    v4_outcome(report.at("status")),
    {
      "basis": "captured-write-effects",
      "entries": n.get_or_default("effects", Json(([] : Array[Json]))),
    },
    { "serialOrder": inferred, "versionOrderCompletion": false },
    {
      "status": report.at("status"),
      "modelDefinition": report.at("modelDefinition"),
      "coverage": report.at("coverage"),
      "evidence": evidence,
    },
    report.at("execution"),
  )
}

///|
/// Returns a detached structured view, without parsing or encoding it again.
pub fn analysis_v4_json(analysis : AnalysisV4) -> Json {
  v4_json_copy(analysis.record)
}

///|
/// The transport boundary performs its only report serialization here.
pub fn render_analysis_v4(analysis : AnalysisV4) -> String {
  analysis.record.stringify(indent=2)
}

///|
/// Caller-supplied budgets are trusted context, not authority taken from a report.
pub fn verify_v4(
  history : HistoryV4,
  supplied : Json,
  options~ : AnalysisOptionsV4 = analysis_options_v4(),
) -> Bool {
  supplied == analyze_v4(history, options~).record
}
