///|
fn compatible_evidence_version(v : Json?) -> Bool {
  match v {
    Some(String(s)) =>
      s == version() ||
      [
        "0.0.1", "0.0.2", "0.0.3", "0.0.4", "0.0.5", "0.0.6", "0.0.7", "0.0.8", "0.0.9",
        "0.0.10", "0.0.11", "0.1.0",
      ].contains(s)
    _ => false
  }
}

///|
fn replay_failure(message : String) -> String {
  let result : Json = {
    "valid": false,
    "reason": message.to_json(),
    "scope": "semantic result reproduction; not a signature or source authenticity check",
  }
  result.stringify(indent=2)
}

///|
/// Recompute semantic fields. Supplemental presentation/coverage fields are not authenticated.
pub fn replay_report_json(
  history_text : String,
  report_text : String,
) -> String {
  try {
    let root = object_fields(
      guarded_json(report_text, limit=33554432),
      "report",
    )
    if root.get("schemaVersion") == Some((2).to_json()) {
      return replay_report_v2(history_text, root)
    }
    if root.get("tool") != Some("MoonTxnWitness".to_json()) ||
      root.get("schemaVersion") != Some((1).to_json()) ||
      !compatible_evidence_version(root.get("version")) {
      return replay_failure("Unsupported report header")
    }
    let expected = object_fields(
      guarded_json(analyze_json(history_text), limit=33554432),
      "recomputed",
    )
    let checked = [
      "status", "model", "complete", "stats", "findings", "edges", "witness", "serialOrder",
      "versionOrders",
    ]
    for name in checked {
      if root.get(name) != expected.get(name) {
        return replay_failure("Recomputed semantic field differs: " + name)
      }
    }
    for name in ["search", "versionOrderSources"] {
      if root.contains(name) && root.get(name) != expected.get(name) {
        return replay_failure("Recomputed semantic field differs: " + name)
      }
    }
    let result : Json = {
      "valid": true,
      "reason": "The current engine reproduces every checked semantic field.",
      "status": expected.at("status"),
      "model": expected.at("model"),
      "checkedFields": checked.to_json(),
      "currentEngine": version().to_json(),
      "recordedEngine": root.at("version"),
      "scope": "semantic result reproduction; supplemental presentation fields and source authenticity are not checked",
    }
    result.stringify(indent=2)
  } catch {
    _ => replay_failure("Malformed or oversized report JSON")
  }
}

///|
/// Parse a capsule with duplicate-key/depth limits. Cryptographic hashes belong to the host.
pub fn capsule_content_json(text : String) -> String {
  try {
    let root = object_fields(guarded_json(text, limit=33554432), "capsule")
    known_fields(
      root,
      [
        "format", "schemaVersion", "tool", "engineVersion", "historyText", "historySha256",
        "reportText", "reportSha256",
      ],
      "capsule",
    )
    let v1 = root.get("format") == Some("moontxnwitness-replay/v1".to_json()) &&
      root.get("schemaVersion") == Some((1).to_json())
    let v2 = root.get("format") == Some("moontxnwitness-replay/v2".to_json()) &&
      root.get("schemaVersion") == Some((2).to_json()) &&
      compatible_v2_version(root.get("engineVersion"))
    if (!v1 && !v2) ||
      root.get("tool") != Some("MoonTxnWitness".to_json()) ||
      !compatible_evidence_version(root.get("engineVersion")) {
      fail("Unsupported capsule header")
    }
    for field in ["historyText", "reportText"] {
      match required(root, field, "capsule") {
        String(s) =>
          if (field == "historyText" && s.length() > 1048576) ||
            s.length() > 33554432 {
            fail("Capsule text exceeds limits")
          }
        _ => fail("Capsule text must be a string")
      }
    }
    for field in ["historySha256", "reportSha256"] {
      match required(root, field, "capsule") {
        String(s) =>
          if s.length() != 64 ||
            !s.iter().all(c => (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) {
            fail("Invalid SHA-256 spelling")
          }
        _ => fail("Missing SHA-256 string")
      }
    }
    let report_text = match root.at("reportText") {
      String(s) => s
      _ => abort("checked")
    }
    let report = object_fields(
      guarded_json(report_text, limit=33554432),
      "report",
    )
    if report.get("version") != root.get("engineVersion") ||
      report.get("tool") != root.get("tool") ||
      report.get("schemaVersion") != root.get("schemaVersion") {
      fail("Capsule and report headers differ")
    }
    let result : Json = {
      "valid": true,
      "historyText": root.at("historyText"),
      "historySha256": root.at("historySha256"),
      "reportText": root.at("reportText"),
      "reportSha256": root.at("reportSha256"),
      "scope": "capsule structure only; caller must verify both hashes and reproduce semantic fields",
    }
    result.stringify()
  } catch {
    _ =>
      replay_failure("Malformed, duplicated, unsupported or oversized capsule")
  }
}

///|
pub fn compare_models(h : History) -> Json {
  let writes = collect_writes(h)
  let serial = analyze_internal({ ..h, model: Serializable, }, true, writes~)
  let strict = analyze_internal(
    { ..h, model: StrictSerializable, },
    true,
    writes~,
  )
  let category = if serial.outcome == Invalid || strict.outcome == Invalid {
    "invalid"
  } else if serial.outcome == Violation {
    "data-order-violation"
  } else if serial.outcome == Consistent && strict.outcome == Violation {
    "realtime-only-violation"
  } else if serial.outcome == Consistent && strict.outcome == Consistent {
    "compatible-with-both"
  } else if strict.outcome == Violation {
    "strict-violation-data-incomplete"
  } else {
    "inconclusive"
  }
  {
    "tool": "MoonTxnWitness",
    "version": version().to_json(),
    "valid": (category != "invalid").to_json(),
    "classification": category.to_json(),
    "inputModel": model_label(h.model).to_json(),
    "serializable": report_json(serial),
    "strictSerializable": report_json(strict),
    "realtimeEdges": strict.edges
    .filter(e => e.kind == RT)
    .map(edge_json)
    .to_json(),
    "scope": "same observations under two models; no database-wide guarantee",
  }
}

///|
pub fn compare_models_json(text : String) -> String {
  match parse_history(text) {
    Ok(h) => compare_models(h).stringify(indent=2)
    Err(e) => {
      let result : Json = {
        "valid": false,
        "classification": "invalid",
        "reason": e.to_json(),
      }
      result.stringify(indent=2)
    }
  }
}
