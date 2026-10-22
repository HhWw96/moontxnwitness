///|
fn compatible_v2_version(v : Json?) -> Bool {
  match v {
    Some(String(s)) =>
      s == version() ||
      ["0.0.9", "0.0.10", "0.0.11", "0.1.0", "0.1.1", "0.1.2", "0.1.3", "0.1.4"].contains(
        s,
      )
    _ => false
  }
}

///|
fn replay_report_v2(
  history_text : String,
  root : Map[String, Json],
) -> String raise {
  if root.get("tool") != Some("MoonTxnWitness".to_json()) ||
    root.get("algorithm") != Some("bounded-register-v2.1".to_json()) ||
    !compatible_v2_version(root.get("version")) {
    return replay_failure("Unsupported v2 algorithm or engine header")
  }
  let options = parse_analysis_options(
    required(root, "analysisOptions", "report").stringify(),
  )
  if root.get("effectiveLimits") != Some(effective_limits(options)) {
    return replay_failure(
      "Recorded effective limits differ from analysis options",
    )
  }
  let expected = object_fields(
    analysis_result_json(
      options_input(history_text, root.at("analysisOptions").stringify()),
    ),
    "recomputed",
  )
  let checked = [
    "status", "model", "complete", "stats", "findings", "edges", "witness", "serialOrder",
    "versionOrders", "versionOrderSources", "search", "effectiveLimits", "analysisOptions",
    "algorithm",
  ]
  for name in checked {
    if root.get(name) != expected.get(name) {
      return replay_failure("Recomputed v2 semantic field differs: " + name)
    }
  }
  let result : Json = {
    "valid": true,
    "reason": "The bounded v2 algorithm reproduces the semantic result under the recorded effective budgets.",
    "status": expected.at("status"),
    "checkedFields": checked.to_json(),
    "currentEngine": version().to_json(),
    "recordedEngine": root.at("version"),
    "scope": "semantic replay; runtime metrics, presentation and source identity are not authenticated",
  }
  result.stringify()
}
