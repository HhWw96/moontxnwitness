///|
priv struct WireModelOptionsV4 {
  options : ModelOptionsV4
  clients : Array[ModelClientV4]
  clients_complete : Bool
}

///|
fn wire_model_name_v4(value : Json) -> ElleModelV4 raise {
  for model in elle_core_models_v4() {
    if value == Json(model_name_v4(model)) {
      return model
    }
  }
  fail("Choose an exact supported canonical model name")
}

///|
fn wire_model_bool_v4(fields : Map[String, Json], name : String) -> Bool raise {
  match fields.get(name) {
    None | Some(False) => false
    Some(True) => true
    _ => fail(name + " must be a boolean")
  }
}

///|
fn wire_model_options_v4(text : String) -> WireModelOptionsV4 raise {
  let fields = object_fields(guarded_json(text, limit=8192), "model options v4")
  known_fields(
    fields,
    [
      "models", "maxSourceChecks", "maxStates", "maxEdgeChecks", "relationProfile",
      "listProfile", "completionPolicy", "clients", "clientsComplete",
    ],
    "model options v4",
  )
  let models = match fields.get("models") {
    None =>
      [
        ElleReadUncommitted,
        ElleReadCommitted,
        ElleRepeatableRead,
        ElleSnapshotIsolation,
        ElleSerializable,
        ElleStrictSerializable,
      ]
    Some(String("elle-core")) => elle_core_models_v4()
    Some(Array(items)) if !items.is_empty() && items.length() <= 14 =>
      items.map(wire_model_name_v4)
    _ =>
      fail(
        "models must be elle-core or one to fourteen distinct canonical model names",
      )
  }
  let list_profile = match fields.get("listProfile") {
    None | Some(String("native")) => ModelListNative
    Some(String("captured-list-prefix-state/v2")) => ModelListPrefixStates
    _ => fail("listProfile must be native or captured-list-prefix-state/v2")
  }
  let relation_profile = match fields.get("relationProfile") {
    None | Some(String("relation-point-final-installed/v1")) =>
      ModelRelationPoint
    Some(String("adya-2000-predicate-on-keyslots-v1")) =>
      ModelRelationPredicateKeySlots
    Some(String("captured-relation-row-slots/v1")) => ModelRelationAtomicRows
    _ => fail("Unknown relation model source profile")
  }
  let completion_policy = match fields.get("completionPolicy") {
    None | Some(String("transaction-observations-existential-completion/v1")) =>
      ModelObservationOnlyCompletion
    Some(String("given-logical-snapshot-assertions/unsupported")) =>
      ModelGivenSnapshotsUnsupported
    _ => fail("Unknown model completion policy")
  }
  let clients = match fields.get("clients") {
    None => []
    Some(Array(items)) if items.length() <= 128 =>
      items.map(raw => {
        let client = object_fields(raw, "logical client")
        known_fields(client, ["id", "transactions"], "logical client")
        let id = identifier(
          required(client, "id", "logical client"),
          "logical client id",
        )
        let transactions = match
          required(client, "transactions", "logical client") {
          Array(values) if values.length() <= 128 =>
            values.map(v => identifier(v, "client transaction"))
          _ => fail("logical client transactions must be a bounded array")
        }
        ({ id, transactions, } : ModelClientV4)
      })
    _ => fail("clients must be an array of at most 128 logical clients")
  }
  let options = match
    model_options_v4(
      models~,
      max_source_checks=wire_v4_int(fields, "maxSourceChecks", 1000000, 1000000),
      max_states=wire_v4_int(fields, "maxStates", 100000, 100000),
      max_edge_checks=wire_v4_int(fields, "maxEdgeChecks", 1000000, 1000000),
      list_profile~,
      relation_profile~,
      completion_policy~,
    ) {
    Ok(options) => options
    Err(reason) => fail(reason)
  }
  {
    options,
    clients,
    clients_complete: wire_model_bool_v4(fields, "clientsComplete"),
  }
}

///|
fn wire_model_options_record_v4(wire : WireModelOptionsV4) -> Json {
  let o = wire.options
  {
    "models": Json(o.models.map(model_name_v4)),
    "maxSourceChecks": Json(o.max_source_checks),
    "maxStates": Json(o.max_states),
    "maxEdgeChecks": Json(o.max_edge_checks),
    "listProfile": if o.list_profile == ModelListNative {
      Json("native")
    } else {
      Json("captured-list-prefix-state/v2")
    },
    "relationProfile": match o.relation_profile {
      ModelRelationPoint => Json("relation-point-final-installed/v1")
      ModelRelationPredicateKeySlots =>
        Json("adya-2000-predicate-on-keyslots-v1")
      ModelRelationAtomicRows => Json("captured-relation-row-slots/v1")
    },
    "completionPolicy": if o.completion_policy == ModelObservationOnlyCompletion {
      Json("transaction-observations-existential-completion/v1")
    } else {
      Json("given-logical-snapshot-assertions/unsupported")
    },
    "clients": Json(
      wire.clients.map(c => {
        ({ "id": Json(c.id), "transactions": Json(c.transactions) } : Json)
      }),
    ),
    "clientsComplete": Json(wire.clients_complete),
  }
}

///|
fn wire_model_facts_v4(
  text : String,
  wire : WireModelOptionsV4,
) -> ModelFactsV4 raise {
  match
    model_facts_v4(
      wire_v4_history(text),
      clients=wire.clients,
      clients_complete=wire.clients_complete,
    ) {
    Ok(facts) => facts
    Err(reason) => fail(reason)
  }
}

///|
/// Model obligations are independent of existing graph-category APIs.
pub fn classify_models_v4_json(text : String, options_text : String) -> String {
  try {
    let wire = wire_model_options_v4(options_text)
    model_classification_v4_json(
      classify_models_v4(wire_model_facts_v4(text, wire), wire.options),
    ).stringify(indent=2)
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
/// Recompute from original source and independently supplied policy and limits.
pub fn verify_model_classification_v4_json(
  text : String,
  report_text : String,
  expected_options_text : String,
) -> String {
  try {
    let wire = wire_model_options_v4(expected_options_text)
    wire_v4_verified(
      verify_models_v4(
        wire_model_facts_v4(text, wire),
        guarded_json(report_text, limit=33554432),
        wire.options,
      ),
    )
  } catch {
    _ => wire_v4_verified(false)
  }
}

///|
pub fn model_options_v4_content_json(text : String) -> String {
  (
    {
      "valid": true,
      "options": wire_model_options_record_v4(wire_model_options_v4(text)),
    } : Json).stringify() catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
pub fn model_report_v4_content_json(text : String) -> String {
  try {
    let value = guarded_json(text, limit=33554432)
    let fields = object_fields(value, "model report v4")
    if fields.get("format") != Some(Json("moontxnwitness-model-composition/v4")) ||
      fields.get("schemaVersion") != Some(Json(4)) {
      fail("Unsupported model report")
    }
    ({ "valid": true, "value": value } : Json).stringify()
  } catch {
    error => wire_v4_failure(error.to_string())
  }
}

///|
/// Version is descriptive metadata; it cannot select a verifier or grant budget.
pub fn model_capsule_v4_content_json(text : String) -> String {
  try {
    let value = guarded_json(text, limit=67108864)
    let fields = object_fields(value, "model capsule v4")
    known_fields(
      fields,
      [
        "format", "schemaVersion", "tool", "producer", "operation", "semanticContract",
        "algorithm", "counterContract", "sourceProfile", "sourceText", "sourceSha256",
        "optionsText", "optionsSha256", "reportText", "reportSha256",
      ],
      "model capsule v4",
    )
    if fields.get("format") !=
      Some(Json("moontxnwitness-model-obligations-replay/v4")) ||
      fields.get("schemaVersion") != Some(Json(4)) ||
      fields.get("tool") != Some(Json("MoonTxnWitness")) ||
      fields.get("operation") != Some(Json("classify-models")) {
      fail("Unsupported model capsule")
    }
    for
      name in [
        "semanticContract", "algorithm", "counterContract", "sourceProfile", "sourceText",
        "sourceSha256", "optionsText", "optionsSha256", "reportText", "reportSha256",
      ] {
      match required(fields, name, "model capsule v4") {
        String(_) => ()
        _ => fail("Model capsule content fields must be text")
      }
    }
    let producer = object_fields(
      required(fields, "producer", "model capsule v4"),
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
