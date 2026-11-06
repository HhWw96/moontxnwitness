///|
fn wire_relation_reduction_options_v4(
  text : String,
) -> (String, Int32, Int32, Int32, Int32, WireRelationPredicateOptionsV4?) raise {
  let fields = object_fields(
    guarded_json(text, limit=8192),
    "relation reduction options",
  )
  if fields.contains("ruleSet") {
    let max_checks = wire_v4_int(fields, "maxChecks", 256, 256)
    fields.remove("maxChecks")
    let predicate = wire_relation_predicate_options_v4(
      Json::object(fields).stringify(),
    )
    return (
      scoped_category_name_v4(predicate.category),
      max_checks,
      predicate.states,
      predicate.edges,
      predicate.graph,
      Some(predicate),
    )
  }
  known_fields(
    fields,
    ["category", "maxChecks", "maxStates", "maxEdgeChecks", "maxGraphChecks"],
    "relation reduction options",
  )
  let category = match
    required(fields, "category", "relation reduction options") {
    String(name) if relation_classification_categories_v4().contains(name) =>
      name
    _ =>
      fail(
        "category is required and must select G0, G1a, G1b, G1c, G2-item or INT",
      )
  }
  (
    category,
    wire_v4_int(fields, "maxChecks", 256, 256),
    wire_v4_int(fields, "maxStates", 100000, 100000),
    wire_v4_int(fields, "maxEdgeChecks", 1000000, 1000000),
    wire_v4_int(fields, "maxGraphChecks", 1000000, 1000000),
    None,
  )
}

///|
fn wire_relation_category_reduce_v4(
  text : String,
  options : String,
) -> RelationCategoryReductionV4 raise {
  let (category, checks, states, edges, graph, predicate) = wire_relation_reduction_options_v4(
    options,
  )
  reduce_relation_category_impl_v4(
    wire_v4_history(text),
    category,
    checks,
    states,
    edges,
    graph,
    predicate,
  )
}

///|
pub fn reduce_relation_category_v4_json(
  text : String,
  options : String,
) -> String {
  relation_category_reduction_v4_json(
    wire_relation_category_reduce_v4(text, options),
  ).stringify(indent=2) catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
pub fn verify_relation_category_reduction_v4_json(
  text : String,
  report : String,
  options : String,
) -> String {
  wire_v4_verified(
    guarded_json(report, limit=33554432) ==
    wire_relation_category_reduce_v4(text, options).record,
  ) catch {
    _ => wire_v4_verified(false)
  }
}

///|
pub fn relation_reduction_report_v4_content_json(text : String) -> String {
  try {
    let value = guarded_json(text, limit=33554432)
    let _ = object_fields(value, "relation category reduction report")
    ({ "valid": true, "value": value } : Json).stringify()
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
pub fn relation_reduction_capsule_v4_content_json(text : String) -> String {
  try {
    let value = guarded_json(text, limit=67108864)
    let fields = object_fields(value, "relation category reduction capsule")
    known_fields(
      fields,
      [
        "format", "schemaVersion", "tool", "producer", "operation", "semanticContract",
        "algorithm", "counterContract", "profile", "sourceText", "sourceSha256",
        "optionsText", "optionsSha256", "reportText", "reportSha256",
      ],
      "relation category reduction capsule",
    )
    if fields.get("format") !=
      Some(Json("moontxnwitness-relation-category-replay/v4")) ||
      fields.get("schemaVersion") != Some(Json(4)) ||
      fields.get("tool") != Some(Json("MoonTxnWitness")) {
      fail("Unsupported relation category reduction capsule")
    }
    for
      name in [
        "operation", "semanticContract", "algorithm", "counterContract", "profile",
        "sourceText", "sourceSha256", "optionsText", "optionsSha256", "reportText",
        "reportSha256",
      ] {
      match required(fields, name, "relation category reduction capsule") {
        String(_) => ()
        _ => fail("Capsule fields must be text")
      }
    }
    let producer = object_fields(
      required(fields, "producer", "relation category reduction capsule"),
      "producer",
    )
    known_fields(producer, ["version"], "producer")
    match required(producer, "version", "producer") {
      String(_) => ()
      _ => fail("Producer version must be text")
    }
    value.stringify()
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}
