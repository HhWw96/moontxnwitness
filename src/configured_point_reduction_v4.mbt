///|
fn configured_point_reduction_v4(
  before : String,
  after : String,
  session : String,
  options : String,
) -> Json raise {
  let fields = source_object_v4(sql_json_v1(options, 8192))
  known_fields(
    fields,
    [
      "category", "windowOptions", "maxChecks", "maxStates", "maxEdgeChecks", "maxGraphChecks",
    ],
    "configured-point-reduction-options",
  )
  match fields.get("category") {
    Some(String("G2-item")) => ()
    _ => fail("unsupported:configured-point-reduction-requires-G2-item")
  }
  let window_options = match fields.get("windowOptions") {
    Some(value) => {
      let _ = source_object_v4(value)
      value.stringify()
    }
    None => "{}"
  }
  let max_checks = wire_v4_int(fields, "maxChecks", 256, 256)
  let max_states = wire_v4_int(fields, "maxStates", 100000, 100000)
  let max_edges = source_wire_limit_v4(fields, "maxEdgeChecks", 1000000)
  let max_graph = source_wire_limit_v4(fields, "maxGraphChecks", 1000000)
  let window = source_object_v4(
    sql_json_v1(
      analyze_configured_point_window_v4_json(
        before, after, session, window_options,
      ),
      33554432,
    ),
  )
  let mut reduction : Json = Json::null()
  let mut status = match window.at("status") {
    String("checked-compatible") => "not-refuted"
    String("invalid") => "invalid"
    _ => "unknown"
  }
  let mut one_minimal = false
  if window.at("coverageComplete") == Json(true) &&
    window.at("status") == Json("refuted") &&
    source_object_v4(source_object_v4(window.at("itemCategory")).at("judgment")).at(
      "status",
    ) ==
    Json("refuted") {
    // The immutable window is verified once. Every candidate still traverses
    // the existing source-closure checks, and final evidence is recomputed.
    let history = wire_v4_history(window.at("history").stringify())
    let reduced = reduce_relation_category_v4(
      history,
      category="G2-item",
      max_checks~,
      max_states~,
      max_edge_checks=max_edges,
      max_graph_checks=max_graph,
    )
    reduction = relation_category_reduction_v4_json(reduced)
    let record = source_object_v4(reduction)
    status = sql_string_v1(record.at("status"))
    one_minimal = record.at("oneMinimal") == Json(true)
  }
  {
    "format": "moontxnwitness-configured-point-reduction/v1",
    "semanticContract": "verified-point-window-category-selection/v1",
    "preserveCategory": "G2-item",
    "status": Json(status),
    "oneMinimal": Json(one_minimal),
    "sourceAuthenticated": false,
    "originalWindowRetained": true,
    "startSha256": Json(v3_dislock_sha256(before)),
    "endSha256": Json(v3_dislock_sha256(after)),
    "sessionSha256": Json(v3_dislock_sha256(session)),
    "optionsSha256": Json(v3_dislock_sha256(options)),
    "window": Json(window),
    "reduction": reduction,
  }
}

///|
/// Selects transactions from a verified immutable PostgreSQL point window.
pub fn reduce_configured_point_window_v4_json(
  before : String,
  after : String,
  session : String,
  options : String,
) -> String {
  configured_point_reduction_v4(before, after, session, options).stringify() catch {
    error =>
      (
        {
          "format": "moontxnwitness-configured-point-reduction/v1",
          "semanticContract": "verified-point-window-category-selection/v1",
          "status": "invalid",
          "oneMinimal": false,
          "sourceAuthenticated": false,
          "originalWindowRetained": true,
          "startSha256": Json(v3_dislock_sha256(before)),
          "endSha256": Json(v3_dislock_sha256(after)),
          "sessionSha256": Json(v3_dislock_sha256(session)),
          "optionsSha256": Json(v3_dislock_sha256(options)),
          "reason": Json(error.to_string()),
        } : Json).stringify()
  }
}

///|
/// Recomputes source verification and every candidate under independent options.
pub fn verify_configured_point_reduction_v4_json(
  before : String,
  after : String,
  session : String,
  report : String,
  options : String,
) -> Bool {
  try {
    let supplied = sql_json_v1(report, 67108864)
    let expected = sql_json_v1(
      reduce_configured_point_window_v4_json(before, after, session, options),
      67108864,
    )
    supplied == expected
  } catch {
    _ => false
  }
}
