///|
fn v3_analysis(text : String, options_text : String) -> Json raise {
  if v3_is_relation_capture(text) {
    return relation_v3_analysis(text, options_text)
  }
  if v3_is_list_capture(text) {
    return list_v3_analysis(text, options_text)
  }
  let (options, sql_proof) = v3_register_options(options_text)
  let normalized = guarded_json(
    normalize_register_capture_v3_json(text, use_sql_proof=sql_proof),
    limit=33554432,
  )
  let n = object_fields(normalized, "normalized")
  let mut evidence : Json = Json::null()
  let mut status = required(n, "status", "normalized")
  let mut metrics : Json = Json::null()
  if status == Json("ready") {
    match
      parse_history_optimized(required(n, "history", "normalized").stringify()) {
      Ok(h) => {
        let result = analyze_with_options(h, options~)
        evidence = analysis_result_json(result)
        status = object_fields(evidence, "evidence").at("status")
        metrics = object_fields(evidence, "evidence").at("metrics")
      }
      Err(message) => fail("Invalid v3 projection: " + message)
    }
  }
  let recorded_options : Json = {
    "maxAttempts": Json(options.max_attempts),
    "maxOperationChecks": Json(options.max_operation_checks),
    "maxCachedStates": Json(options.max_cached_states),
  }
  if sql_proof {
    object_fields_unchecked_v3(recorded_options)["sqlProof"] = Json(
      "dislock-f9946f0-sql-proof-1",
    )
  }
  {
    "schemaVersion": 3,
    "tool": "MoonTxnWitness",
    "version": Json(version()),
    "algorithm": Json(
      if sql_proof {
        "v3-register-sql-1"
      } else {
        "v3-register-1"
      },
    ),
    "status": status,
    "modelDefinition": {
      "id": "register-serializable-v1",
      "scope": "unique-version point read/write; no real-time order inferred from event timestamps",
    },
    "coverage": n.at("coverage"),
    "normalized": normalized,
    "evidence": evidence,
    "execution": {
      "analysisOptions": recorded_options,
      "effectiveLimits": effective_limits(options),
      "metrics": metrics,
    },
  }
}

///|
fn v3_failure(message : String) -> Json {
  {
    "schemaVersion": 3,
    "tool": "MoonTxnWitness",
    "version": Json(version()),
    "algorithm": "v3-register-1",
    "status": "invalid",
    "coverage": { "complete": false, "gaps": [] },
    "error": Json(message),
  }
}

///|
pub fn analyze_v3_json(text : String, options_text : String) -> String {
  v3_analysis(text, options_text).stringify(indent=2) catch {
    e => v3_failure(e.to_string()).stringify(indent=2)
  }
}

///|
fn compatible_v3_engine(v : Json?) -> Bool {
  match v {
    Some(String(s)) =>
      s == version() ||
      [
        "0.1.1", "0.1.2", "0.1.3", "0.1.4", "0.1.5", "0.1.6", "0.1.7", "0.1.8", "0.2.0",
        "0.2.1", "0.2.2", "0.2.3", "0.2.4", "0.2.5", "0.2.6", "0.2.7", "0.2.8",
      ].contains(s)
    _ => false
  }
}

///|
pub fn verify_v3_json(text : String, report_text : String) -> String {
  try {
    let supplied = guarded_json(report_text, limit=33554432)
    let fields = object_fields(supplied, "report")
    let recorded_engine = fields.get("version")
    if !compatible_v3_engine(recorded_engine) {
      fail("Unsupported v3 report engine")
    }
    let execution = object_fields(
      required(fields, "execution", "report"),
      "execution",
    )
    let options = required(execution, "analysisOptions", "execution").stringify()
    let expected = v3_analysis(text, options)
    // v0.2.4 preserves the released v0.1.1/v0.1.2/v0.1.3/v0.1.4/v0.1.5/v0.1.6/v0.1.7/v0.1.8 algorithms. Compare every recomputed field;
    // translate only the two engine headers, never observed version identities.
    let expected_fields = object_fields(expected, "expected report")
    expected_fields["version"] = fields.at("version")
    match expected_fields.get("evidence") {
      Some(Object(evidence)) =>
        if evidence.get("tool") == Some(Json("MoonTxnWitness")) &&
          evidence.get("schemaVersion") == Some(Json(2)) {
          evidence["version"] = fields.at("version")
        }
      _ => ()
    }
    let valid = supplied == expected
    let result : Json = {
      "valid": Json(valid),
      "schemaVersion": 3,
      "reason": Json(
        if valid {
          "Every v3 field was independently recomputed, including observations, effects, coverage, budgets and evidence."
        } else {
          "Recomputed v3 report differs."
        },
      ),
      "scope": "semantic reproduction; hashes do not authenticate source observations",
    }
    result.stringify(indent=2)
  } catch {
    _ => {
      let result : Json = {
        "valid": false,
        "reason": "Malformed, unsupported or oversized v3 report",
      }
      result.stringify(indent=2)
    }
  }
}

///|
/// Host transports bytes and SHA-256; bounded duplicate-key parsing stays in MoonBit.
pub fn capsule_v3_content_json(text : String) -> String {
  try {
    let value = guarded_json(text, limit=33554432)
    let root = object_fields(value, "capsule")
    known_fields(
      root,
      [
        "format", "schemaVersion", "tool", "engineVersion", "traceText", "traceSha256",
        "normalizedText", "normalizedSha256", "reportText", "reportSha256", "evidenceText",
        "evidenceSha256",
      ],
      "capsule",
    )
    if root.get("format") != Some(Json("moontxnwitness-replay/v3")) ||
      root.get("schemaVersion") != Some(Json(3)) ||
      root.get("tool") != Some(Json("MoonTxnWitness")) ||
      !compatible_v3_engine(root.get("engineVersion")) {
      fail("Unsupported v3 capsule header")
    }
    for key in ["traceText", "normalizedText", "reportText", "evidenceText"] {
      match required(root, key, "capsule") {
        String(_) => ()
        _ => fail("Capsule content must be text")
      }
    }
    let report_text = match required(root, "reportText", "capsule") {
      String(s) => s
      _ => fail("Capsule report must be text")
    }
    let report = object_fields(
      guarded_json(report_text, limit=33554432),
      "capsule report",
    )
    if report.get("version") != root.get("engineVersion") {
      fail("Capsule and report engine headers differ")
    }
    for
      key in [
        "traceSha256", "normalizedSha256", "reportSha256", "evidenceSha256",
      ] {
      match required(root, key, "capsule") {
        String(s) if s.length() == 64 &&
          s.iter().all(c => (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) =>
          ()
        _ => fail("Capsule digest must be lower-case SHA-256")
      }
    }
    let result : Json = { "valid": true, "content": value }
    result.stringify()
  } catch {
    _ => {
      let result : Json = {
        "valid": false,
        "reason": "Malformed, unsupported or oversized v3 capsule",
      }
      result.stringify()
    }
  }
}

///|
fn v3_without_transaction(
  trace : Json,
  removed : String,
  prune_sql_ledger~ : Bool = false,
) -> (Json, Array[Json]) raise {
  let root = object_fields(trace, "trace")
  let events = match required(root, "events", "trace") {
    Array(items) => items
    _ => fail("events must be an array")
  }
  let kept : Array[Json] = []
  let origins : Array[Json] = []
  let sequence : Map[String, Json] = Map([])
  let removed_versions : Map[String, Bool] = Map([])
  for raw in events {
    let event = object_fields(raw, "event")
    if prune_sql_ledger &&
      event.get("tx") == Some(Json(removed)) &&
      event.get("kind") == Some(Json("write")) {
      removed_versions[identifier(
        required(event, "version", "write"),
        "write.version",
      )] = true
    }
    if event.get("tx") != Some(Json(removed)) {
      let copy : Map[String, Json] = Map([])
      for key, value in event {
        copy[key] = value
      }
      let next = Json(kept.length() + 1)
      let original = required(event, "seq", "event")
      sequence[original.stringify()] = next
      copy["seq"] = next
      if event.contains("statement") {
        let statement = event.at("statement")
        copy["statement"] = match sequence.get(statement.stringify()) {
          Some(value) => value
          None => fail("Missing retained statement")
        }
      }
      if event.contains("commitResponse") {
        let response = object_fields(
          event.at("commitResponse"),
          "commitResponse",
        )
        let remapped : Map[String, Json] = Map([])
        for key, value in response {
          remapped[key] = value
        }
        let request = required(response, "request", "commitResponse")
        remapped["request"] = match sequence.get(request.stringify()) {
          Some(value) => value
          None => fail("Missing retained COMMIT request")
        }
        copy["commitResponse"] = Json::object(remapped)
      }
      origins.push(original)
      kept.push(Json::object(copy))
    }
  }
  let copy : Map[String, Json] = Map([])
  for key, value in root {
    copy[key] = value
  }
  copy["events"] = Json(kept)
  if prune_sql_ledger {
    match root.get("sqlProfiles") {
      Some(Array(profiles)) => {
        let pruned : Array[Json] = []
        for raw in profiles {
          let fields = object_fields(raw, "SQL profile")
          let profile : Map[String, Json] = Map([])
          for key, value in fields {
            profile[key] = value
          }
          match fields.get("effectLedger") {
            Some(Array(rows)) =>
              profile["effectLedger"] = Json(
                rows.filter(row => {
                  let version = identifier(
                    required(
                      object_fields(row, "effect ledger"),
                      "version",
                      "effect ledger",
                    ),
                    "effect ledger.version",
                  )
                  !removed_versions.contains(version)
                }),
              )
            _ => ()
          }
          pruned.push(Json::object(profile))
        }
        copy["sqlProfiles"] = Json(pruned)
      }
      _ => ()
    }
  }
  (Json::object(copy), origins)
}

///|
/// Every candidate is source-validated again. No searched orders become capture facts.
pub fn reduce_v3_json(text : String, options_text : String) -> String {
  try {
    let options = object_fields(
      guarded_json(options_text, limit=4096),
      "options",
    )
    known_fields(options, ["maxChecks", "analysisOptions"], "options")
    let max_checks = match options.get("maxChecks") {
      None => 256
      Some(Number(n, ..)) if n >= 0.0 &&
        n <= 256.0 &&
        n.to_int().to_double() == n => n.to_int()
      _ => fail("maxChecks must be an integer in 0..256")
    }
    let analysis_options = options
      .get_or_default("analysisOptions", Json::object(Map([])))
      .stringify()
    let prune_sql_ledger = if v3_is_list_capture(text) ||
      v3_is_relation_capture(text) {
      false
    } else {
      let (_, requested) = v3_register_options(analysis_options)
      requested
    }
    let mut trace = guarded_json(text, limit=8388608)
    let mut report = v3_analysis(text, analysis_options)
    let removed : Array[String] = []
    let mut checks = 0
    let mut minimal = false
    let mut origins : Array[Json] = []
    let source_events = match object_fields(trace, "trace").get("events") {
      Some(Array(items)) => items
      _ => []
    }
    for event in source_events {
      origins.push(object_fields(event, "event").at("seq"))
    }
    let eligible = object_fields(report, "report").get("status") ==
      Some(Json("violation"))
    if eligible {
      let mut changed = true
      while changed && checks < max_checks {
        changed = false
        let n = object_fields(
          object_fields(report, "report").at("normalized"),
          "normalized",
        )
        let transactions = match n.at("transactions") {
          Array(items) => items
          _ => []
        }
        let mut completed_pass = true
        for transaction in transactions {
          if checks >= max_checks {
            completed_pass = false
            break
          }
          let id = identifier(
            object_fields(transaction, "transaction").at("id"),
            "transaction.id",
          )
          let (candidate, relative_origins) = v3_without_transaction(
            trace,
            id,
            prune_sql_ledger~,
          )
          checks += 1
          let candidate_report = v3_relation_reduction_candidate(
            candidate, analysis_options,
          )
          if object_fields(candidate_report, "report").get("status") ==
            Some(Json("violation")) {
            let old_events = match object_fields(trace, "trace").at("events") {
              Array(items) => items
              _ => []
            }
            let old_origin : Map[String, Json] = Map([])
            for index, event in old_events {
              old_origin[object_fields(event, "event").at("seq").stringify()] = origins[index]
            }
            origins = relative_origins.map(seq => old_origin.at(seq.stringify()))
            trace = candidate
            report = candidate_report
            removed.push(id)
            changed = true
            completed_pass = false
            break
          }
        }
        if completed_pass {
          minimal = true
        }
      }
    }
    let result : Json = {
      "schemaVersion": 3,
      "algorithm": "v3-source-checked-single-delete-1",
      "predicate": Json(
        if v3_is_relation_capture(text) {
          "definite relation-set serializability violation with complete capture coverage"
        } else if v3_is_list_capture(text) {
          "definite append-list serializability violation with complete capture coverage"
        } else {
          "definite register serializability violation with complete capture coverage"
        },
      ),
      "status": Json(
        if !eligible {
          "not-violation"
        } else if !minimal {
          "budget"
        } else if removed.is_empty() {
          "unchanged"
        } else {
          "reduced"
        },
      ),
      "maxChecks": Json(max_checks),
      "checks": Json(checks),
      "oneMinimal": Json(minimal),
      "removed": Json(removed),
      "retainedOriginalSeq": Json(origins),
      "reducedCapture": trace,
      "report": report,
    }
    result.stringify(indent=2)
  } catch {
    e => v3_failure(e.to_string()).stringify(indent=2)
  }
}

///|
// Only relation-set reduction candidates reuse the already guarded JSON value.
// Other data models retain the original complete textual analysis path.
fn v3_relation_reduction_candidate(
  candidate : Json,
  analysis_options : String,
) -> Json raise {
  let text = candidate.stringify()
  if text.length() > 8388608 {
    return v3_analysis(text, analysis_options)
  }
  match candidate {
    Object(root) =>
      match root.get("dataModel") {
        Some(String("relation-set-v1")) =>
          relation_v3_analysis(text, analysis_options, v=candidate)
        _ => v3_analysis(text, analysis_options)
      }
    _ => v3_analysis(text, analysis_options)
  }
}

///|
// Private structured values come only from the original guarded capture.
// Textual calls keep their original duplicate-key, depth and size validation.
fn v3_guarded_candidate(text : String, value : Json?) -> Json raise {
  match value {
    Some(value) => value
    None => guarded_json(text, limit=8388608)
  }
}
