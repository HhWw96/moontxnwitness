///|
pub(all) enum ElleModelV4 {
  ElleReadUncommitted
  ElleReadCommitted
  ElleRepeatableRead
  ElleSerializable
  ElleStrictSerializable
  ElleSnapshotIsolation
  ElleConsistentView
  ElleSessionReadUncommitted
  ElleStrongReadUncommitted
  ElleSessionReadCommitted
  ElleStrongReadCommitted
  ElleSessionSerializable
  ElleSessionSnapshotIsolation
  ElleStrongSnapshotIsolation
} derive(Eq)

///|
pub extend ElleModelV4 with Eq::{equal, not_equal}

///|
pub(all) enum ModelRelationProfileV4 {
  ModelRelationPoint
  ModelRelationPredicateKeySlots
} derive(Eq)

///|
pub extend ModelRelationProfileV4 with Eq::{equal, not_equal}

///|
pub(all) enum ModelListProfileV4 {
  ModelListNative
  ModelListPrefixStates
} derive(Eq)

///|
pub extend ModelListProfileV4 with Eq::{equal, not_equal}

///|
pub(all) enum ModelCompletionPolicyV4 {
  ModelObservationOnlyCompletion
  ModelGivenSnapshotsUnsupported
} derive(Eq)

///|
pub extend ModelCompletionPolicyV4 with Eq::{equal, not_equal}

///|
/// A declaration of logical client membership; it is not a pooled connection.
pub(all) struct ModelClientV4 {
  id : String
  transactions : Array[String]
}

///|
pub struct ModelFactsV4 {
  priv history : HistoryV4
  priv clients : Array[ModelClientV4]
  priv clients_complete : Bool
  priv source_record : Json
  priv source_sha256 : String
}

///|
pub struct ModelOptionsV4 {
  priv models : Array[ElleModelV4]
  priv max_source_checks : Int32
  priv max_states : Int32
  priv max_edge_checks : Int32
  priv relation_profile : ModelRelationProfileV4
  priv list_profile : ModelListProfileV4
  priv completion_policy : ModelCompletionPolicyV4
}

///|
pub struct ModelClassificationV4 {
  priv record : Json
}

///|
priv struct ModelRuleV4 {
  id : String
  status : String
  reason : String
  evidence : Json
  covered_by : Array[String]
}

///|
pub fn elle_core_models_v4() -> Array[ElleModelV4] {
  [
    ElleReadUncommitted,
    ElleReadCommitted,
    ElleRepeatableRead,
    ElleSerializable,
    ElleStrictSerializable,
    ElleSnapshotIsolation,
    ElleConsistentView,
    ElleSessionReadUncommitted,
    ElleStrongReadUncommitted,
    ElleSessionReadCommitted,
    ElleStrongReadCommitted,
    ElleSessionSerializable,
    ElleSessionSnapshotIsolation,
    ElleStrongSnapshotIsolation,
  ]
}

///|
fn model_name_v4(model : ElleModelV4) -> String {
  match model {
    ElleReadUncommitted => "read-uncommitted"
    ElleReadCommitted => "read-committed"
    ElleRepeatableRead => "repeatable-read"
    ElleSerializable => "serializable"
    ElleStrictSerializable => "strict-serializable"
    ElleSnapshotIsolation => "snapshot-isolation"
    ElleConsistentView => "consistent-view"
    ElleSessionReadUncommitted => "strong-session-read-uncommitted"
    ElleStrongReadUncommitted => "strong-read-uncommitted"
    ElleSessionReadCommitted => "strong-session-read-committed"
    ElleStrongReadCommitted => "strong-read-committed"
    ElleSessionSerializable => "strong-session-serializable"
    ElleSessionSnapshotIsolation => "strong-session-snapshot-isolation"
    ElleStrongSnapshotIsolation => "strong-snapshot-isolation"
  }
}

///|
fn model_canonical_v4(model : ElleModelV4) -> String {
  match model {
    ElleReadUncommitted => "PL-1"
    ElleReadCommitted => "PL-2"
    ElleRepeatableRead => "PL-2.99"
    ElleSerializable => "PL-3"
    ElleStrictSerializable => "PL-SS"
    ElleSnapshotIsolation => "PL-SI"
    ElleConsistentView => "PL-2+"
    ElleSessionReadUncommitted => "strong-session-PL-1"
    ElleStrongReadUncommitted => "strong-PL-1"
    ElleSessionReadCommitted => "strong-session-PL-2"
    ElleStrongReadCommitted => "strong-PL-2"
    ElleSessionSerializable => "strong-session-serializable"
    ElleSessionSnapshotIsolation => "strong-session-snapshot-isolation"
    ElleStrongSnapshotIsolation => "strong-snapshot-isolation"
  }
}

///|
fn model_literal_obligations_v4(model : ElleModelV4) -> Array[String] {
  match model {
    ElleReadUncommitted =>
      ["G0", "PL-1-cycle-exists", "cyclic-versions", "duplicate-elements"]
    ElleReadCommitted =>
      [
        "G0", "G1", "PL-1-cycle-exists", "PL-2-cycle-exists", "cyclic-versions",
        "duplicate-elements",
      ]
    ElleRepeatableRead =>
      [
        "G-cursor", "G0", "G1", "G2-item", "PL-1-cycle-exists", "PL-2-cycle-exists",
        "PL-2.99-cycle-exists", "cyclic-versions", "duplicate-elements", "lost-update",
      ]
    ElleSerializable =>
      [
        "G-MSR", "G-SI", "G-SIb", "G-cursor", "G-monotonic", "G-nonadjacent", "G-single",
        "G-update", "G0", "G1", "G1a", "G2", "G2-item", "PL-1-cycle-exists", "PL-2-cycle-exists",
        "PL-2.99-cycle-exists", "PL-3-cycle-exists", "PL-SI-cycle-exists", "cyclic-versions",
        "duplicate-elements", "future-read", "internal", "lost-update", "predicate-read-miss",
      ]
    ElleStrictSerializable =>
      [
        "G-MSR", "G-SI", "G-SIb", "G-cursor", "G-monotonic", "G-nonadjacent", "G-nonadjacent-process",
        "G-nonadjacent-realtime", "G-single", "G-update", "G0", "G0-process", "G0-realtime",
        "G1", "G1-process", "G1-realtime", "G1a", "G1c-process", "G1c-realtime",
        "G2", "G2-item", "G2-process", "G2-realtime", "PL-1-cycle-exists", "PL-2-cycle-exists",
        "PL-2.99-cycle-exists", "PL-3-cycle-exists", "PL-SI-cycle-exists", "PL-SS-cycle-exists",
        "cyclic-versions", "duplicate-elements", "future-read", "internal", "lost-update",
        "predicate-read-miss", "strong-PL-1-cycle-exists", "strong-PL-2-cycle-exists",
        "strong-session-PL-1-cycle-exists", "strong-session-PL-2-cycle-exists", "strong-session-serializable-cycle-exists",
        "strong-session-snapshot-isolation-cycle-exists", "strong-snapshot-isolation-cycle-exists",
      ]
    ElleSnapshotIsolation =>
      [
        "G-MSR", "G-SI", "G-SIb", "G-cursor", "G-monotonic", "G-nonadjacent", "G-single",
        "G0", "G1", "G1a", "PL-1-cycle-exists", "PL-2-cycle-exists", "PL-SI-cycle-exists",
        "cyclic-versions", "duplicate-elements", "future-read", "internal", "lost-update",
      ]
    ElleConsistentView =>
      [
        "G-cursor", "G-monotonic", "G-single", "G0", "G1", "PL-1-cycle-exists", "PL-2-cycle-exists",
        "cyclic-versions", "duplicate-elements", "lost-update",
      ]
    ElleSessionReadUncommitted =>
      [
        "G0", "G0-process", "PL-1-cycle-exists", "cyclic-versions", "duplicate-elements",
        "strong-session-PL-1-cycle-exists",
      ]
    ElleStrongReadUncommitted =>
      [
        "G0", "G0-process", "G0-realtime", "PL-1-cycle-exists", "cyclic-versions",
        "duplicate-elements", "strong-PL-1-cycle-exists", "strong-session-PL-1-cycle-exists",
      ]
    ElleSessionReadCommitted =>
      [
        "G0", "G0-process", "G1", "G1c-process", "PL-1-cycle-exists", "PL-2-cycle-exists",
        "cyclic-versions", "duplicate-elements", "strong-session-PL-1-cycle-exists",
        "strong-session-PL-2-cycle-exists",
      ]
    ElleStrongReadCommitted =>
      [
        "G0", "G0-process", "G0-realtime", "G1", "G1c-process", "G1c-realtime", "PL-1-cycle-exists",
        "PL-2-cycle-exists", "cyclic-versions", "duplicate-elements", "strong-PL-1-cycle-exists",
        "strong-PL-2-cycle-exists", "strong-session-PL-1-cycle-exists", "strong-session-PL-2-cycle-exists",
      ]
    ElleSessionSerializable =>
      [
        "G-MSR", "G-SI", "G-SIb", "G-cursor", "G-monotonic", "G-nonadjacent", "G-nonadjacent-process",
        "G-single", "G-update", "G0", "G0-process", "G1", "G1-process", "G1a", "G1c-process",
        "G2", "G2-item", "G2-process", "PL-1-cycle-exists", "PL-2-cycle-exists",
        "PL-2.99-cycle-exists", "PL-3-cycle-exists", "PL-SI-cycle-exists", "cyclic-versions",
        "duplicate-elements", "future-read", "internal", "lost-update", "predicate-read-miss",
        "strong-session-PL-1-cycle-exists", "strong-session-PL-2-cycle-exists", "strong-session-serializable-cycle-exists",
        "strong-session-snapshot-isolation-cycle-exists",
      ]
    ElleSessionSnapshotIsolation =>
      [
        "G-MSR", "G-SI", "G-SIb", "G-cursor", "G-monotonic", "G-nonadjacent", "G-nonadjacent-process",
        "G-single", "G0", "G0-process", "G1", "G1-process", "G1a", "G1c-process",
        "PL-1-cycle-exists", "PL-2-cycle-exists", "PL-SI-cycle-exists", "cyclic-versions",
        "duplicate-elements", "future-read", "internal", "lost-update", "strong-session-PL-1-cycle-exists",
        "strong-session-PL-2-cycle-exists", "strong-session-snapshot-isolation-cycle-exists",
      ]
    ElleStrongSnapshotIsolation =>
      [
        "G-MSR", "G-SI", "G-SIb", "G-cursor", "G-monotonic", "G-nonadjacent", "G-nonadjacent-process",
        "G-nonadjacent-realtime", "G-single", "G0", "G0-process", "G0-realtime",
        "G1", "G1-process", "G1-realtime", "G1a", "G1c-process", "G1c-realtime",
        "PL-1-cycle-exists", "PL-2-cycle-exists", "PL-SI-cycle-exists", "cyclic-versions",
        "duplicate-elements", "future-read", "internal", "lost-update", "strong-PL-1-cycle-exists",
        "strong-PL-2-cycle-exists", "strong-session-PL-1-cycle-exists", "strong-session-PL-2-cycle-exists",
        "strong-session-snapshot-isolation-cycle-exists", "strong-snapshot-isolation-cycle-exists",
      ]
  }
}

///|
fn model_pending_markers_v4(model : ElleModelV4) -> Array[String] {
  match model {
    ElleReadUncommitted => []
    ElleReadCommitted => []
    ElleRepeatableRead => ["G-cursor"]
    ElleSerializable =>
      ["G-MSR", "G-SI", "G-SIb", "G-cursor", "G-monotonic", "G-update"]
    ElleStrictSerializable =>
      ["G-MSR", "G-SI", "G-SIb", "G-cursor", "G-monotonic", "G-update"]
    ElleSnapshotIsolation =>
      ["G-MSR", "G-SI", "G-SIb", "G-cursor", "G-monotonic"]
    ElleConsistentView => ["G-cursor", "G-monotonic"]
    ElleSessionReadUncommitted => []
    ElleStrongReadUncommitted => []
    ElleSessionReadCommitted => []
    ElleStrongReadCommitted => []
    ElleSessionSerializable =>
      ["G-MSR", "G-SI", "G-SIb", "G-cursor", "G-monotonic", "G-update"]
    ElleSessionSnapshotIsolation =>
      ["G-MSR", "G-SI", "G-SIb", "G-cursor", "G-monotonic"]
    ElleStrongSnapshotIsolation =>
      ["G-MSR", "G-SI", "G-SIb", "G-cursor", "G-monotonic"]
  }
}

///|
fn model_projection_v4(model : ElleModelV4) -> String {
  match model {
    ElleReadUncommitted
    | ElleSessionReadUncommitted
    | ElleStrongReadUncommitted => "W"
    ElleReadCommitted | ElleSessionReadCommitted | ElleStrongReadCommitted =>
      "I"
    ElleRepeatableRead => "I+Ai"
    ElleConsistentView => "G-single"
    ElleSnapshotIsolation
    | ElleSessionSnapshotIsolation
    | ElleStrongSnapshotIsolation => "Ext(I,A)"
    _ => "D"
  }
}

///|
fn model_context_v4(model : ElleModelV4) -> ScopedOrderContextV4 {
  match model {
    ElleSessionReadUncommitted
    | ElleSessionReadCommitted
    | ElleSessionSerializable
    | ElleSessionSnapshotIsolation => ScopedWithProcess
    ElleStrongReadUncommitted
    | ElleStrongReadCommitted
    | ElleStrictSerializable
    | ElleStrongSnapshotIsolation => ScopedWithRealtime
    _ => ScopedDataOnly
  }
}

///|
fn model_options_record_v4(options : ModelOptionsV4) -> Json {
  let record : Json = {
    "models": Json(options.models.map(model_name_v4)),
    "maxSourceChecksPerModule": Json(options.max_source_checks),
    "maxStatesPerGraphRule": Json(options.max_states),
    "maxEdgeChecksPerGraphRule": Json(options.max_edge_checks),
    "completionPolicy": Json(
      match options.completion_policy {
        ModelObservationOnlyCompletion =>
          "transaction-observations-existential-completion/v1"
        ModelGivenSnapshotsUnsupported =>
          "given-logical-snapshot-assertions/unsupported"
      },
    ),
    "relationProfile": Json(
      match options.relation_profile {
        ModelRelationPoint => "relation-point-final-installed/v1"
        ModelRelationPredicateKeySlots => "adya-2000-predicate-on-keyslots-v1"
      },
    ),
  }
  if options.list_profile == ModelListPrefixStates {
    object_fields_unchecked_v3(record)["listProfile"] = Json(
      "captured-list-prefix-state/v2",
    )
  }
  record
}

///|
pub fn model_options_v4(
  models~ : Array[ElleModelV4] = [
    ElleReadUncommitted,
    ElleReadCommitted,
    ElleRepeatableRead,
    ElleSnapshotIsolation,
    ElleSerializable,
    ElleStrictSerializable,
  ],
  max_source_checks~ : Int32 = 1000000,
  max_states~ : Int32 = 100000,
  max_edge_checks~ : Int32 = 1000000,
  relation_profile~ : ModelRelationProfileV4 = ModelRelationPoint,
  list_profile~ : ModelListProfileV4 = ModelListNative,
  completion_policy~ : ModelCompletionPolicyV4 = ModelObservationOnlyCompletion,
) -> Result[ModelOptionsV4, String] {
  if models.is_empty() || models.length() > 14 {
    return Err("Choose one to fourteen distinct canonical models")
  }
  let unique : Array[ElleModelV4] = []
  for model in models {
    if unique.contains(model) {
      return Err("Duplicate canonical model")
    }
    unique.push(model)
  }
  if max_source_checks < 0 ||
    max_source_checks > 1000000 ||
    max_states < 0 ||
    max_states > 100000 ||
    max_edge_checks < 0 ||
    max_edge_checks > 1000000 {
    return Err("Model source/state/edge budgets exceed the supported bounds")
  }
  Ok({
    models: unique,
    max_source_checks,
    max_states,
    max_edge_checks,
    relation_profile,
    list_profile,
    completion_policy,
  })
}

///|
fn model_digest_v4(document : Json) -> String {
  let builder = StringBuilder()
  scoped_sorted_json_v4(document, builder)
  v3_dislock_sha256(builder.to_string())
}

///|
pub fn model_facts_v4(
  history : HistoryV4,
  clients~ : Array[ModelClientV4] = [],
  clients_complete~ : Bool = false,
) -> Result[ModelFactsV4, String] {
  if clients.length() > 128 {
    return Err("At most 128 logical clients are supported")
  }
  let identities : Map[String, Bool] = Map([])
  match history.payload {
    RegisterSnapshot(Some(h), _) =>
      for tx in h.transactions {
        identities[tx.id] = true
      }
    RegisterSnapshot(None, Some(n)) =>
      for
        raw in capture_source_array_v4(
          object_fields_unchecked_v3(n).at("transactions"),
        ) {
        identities[capture_source_string_v4(
          object_fields_unchecked_v3(raw).at("id"),
        )] = true
      }
    RegisterSnapshot(None, None) => ()
    ListSnapshot(p) =>
      for tx in p.programs {
        identities[tx.id] = true
      }
    RelationSnapshot(p) =>
      for tx in p.programs {
        identities[tx.id] = true
      }
  }
  let client_ids : Map[String, Bool] = Map([])
  let members : Map[String, Bool] = Map([])
  let copied : Array[ModelClientV4] = []
  for client in clients {
    if !scoped_name_valid_v4(client.id) || client_ids.contains(client.id) {
      return Err("Logical client identities must be valid and unique")
    }
    client_ids[client.id] = true
    for tx in client.transactions {
      if !identities.contains(tx) || members.contains(tx) {
        return Err(
          "Each client member must name a distinct original transaction",
        )
      }
      members[tx] = true
    }
    copied.push({ id: client.id, transactions: client.transactions.copy(), })
  }
  let source_record : Json = {
    "history": history.source_document,
    "clients": Json(
      copied.map(client => {
        (
          { "id": Json(client.id), "transactions": Json(client.transactions) } :
          Json)
      }),
    ),
    "clientsComplete": Json(clients_complete),
    "membershipAssurance": "caller-declared logical clients; every derived order is independently checked against original transaction boundaries",
  }
  Ok({
    history,
    clients: copied,
    clients_complete,
    source_record,
    source_sha256: model_digest_v4(source_record),
  })
}

///|
pub fn model_classification_v4_json(result : ModelClassificationV4) -> Json {
  v4_json_copy(result.record)
}

///|
fn model_rule_v4(
  id : String,
  status : String,
  reason : String,
  evidence~ : Json = Json::null(),
  covered_by~ : Array[String] = [],
) -> ModelRuleV4 {
  { id, status, reason, evidence, covered_by, }
}

///|
fn model_rule_json_v4(rule : ModelRuleV4) -> Json {
  {
    "rule": Json(rule.id),
    "status": Json(rule.status),
    "reason": Json(rule.reason),
    "evidence": rule.evidence,
    "coveredBy": Json(rule.covered_by),
  }
}
