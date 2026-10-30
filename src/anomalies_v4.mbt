///|
priv struct AnomalyV4Item {
  id : String
  value : Json
}

///|
priv struct AnomalyV4Operation {
  tx : String
  position : Int32
  key : String
  write : Bool
  items : Array[AnomalyV4Item]
  original : Json
  seq : Int64?
}

///|
priv struct AnomalyV4Source {
  tx : String?
  position : Int32
  key : String
  item : AnomalyV4Item
  outcome : TxStatus
  reverted : Bool
  original : Json
  seq : Int64?
}

///|
priv struct AnomalyV4Constraint {
  key : String
  before : String
  after : String
  evidence : Json
}

///|
priv struct AnomalyV4Work {
  maximum : Int32
  mut checks : Int32
  mut limited : Bool
  mut truncated : Bool
  mut witness_constraints : Int32
  findings : Array[Json]
  gaps : Array[Json]
  constraints : Array[AnomalyV4Constraint]
  adjacency : Map[String, Map[String, Array[Int32]]]
}

///|
fn anomaly_v4_charge(work : AnomalyV4Work) -> Bool {
  if work.checks >= work.maximum {
    work.limited = true
    false
  } else {
    work.checks += 1
    true
  }
}

///|
fn anomaly_v4_emit(
  work : AnomalyV4Work,
  kind : String,
  status : String,
  evidence : Json,
) -> Unit {
  if work.findings.length() + work.gaps.length() >= 256 {
    work.truncated = true
    // A reported unknown must never crowd out a subsequently proved witness.
    // Eviction stays explicit through findingsTruncated and incomplete coverage.
    if status == "proved" && !work.gaps.is_empty() {
      let _ = work.gaps.pop()
    } else {
      return
    }
  }
  let item : Json = {
    "kind": Json(kind),
    "status": Json(status),
    "evidence": evidence,
    "impliedAnomalies": if kind == "future-read" {
      Json(["G1c", "G1"])
    } else if kind == "lost-update" {
      Json(["lost-update", "write-skew", "G2-item", "G2"])
    } else {
      Json(([] : Array[String]))
    },
  }
  if status == "proved" {
    work.findings.push(item)
  } else {
    work.gaps.push(item)
  }
}

///|
fn anomaly_v4_operation_json(op : AnomalyV4Operation) -> Json {
  {
    "transaction": Json(op.tx),
    "operationIndex": Json(op.position),
    "eventSeq": match op.seq {
      Some(seq) => Json(seq.to_double())
      None => Json::null()
    },
    "key": Json(op.key),
    "kind": object_fields_unchecked_v3(op.original).get_or_default(
      "kind",
      object_fields_unchecked_v3(op.original).get_or_default(
        "type",
        Json::null(),
      ),
    ),
    "originalOperationReference": true,
  }
}

///|
fn anomaly_v4_source_json(source : AnomalyV4Source) -> Json {
  {
    "transaction": match source.tx {
      Some(tx) => Json(tx)
      None => Json::null()
    },
    "operationIndex": if source.position < 0 {
      Json::null()
    } else {
      Json(source.position)
    },
    "eventSeq": match source.seq {
      Some(seq) => Json(seq.to_double())
      None => Json::null()
    },
    "key": Json(source.key),
    "identity": Json(source.item.id),
    "originalValueReference": true,
    "sourceKind": object_fields_unchecked_v3(source.original).get_or_default(
      "kind",
      Json(if source.tx == None { "initial" } else { "write" }),
    ),
    "outcome": Json(status_label(source.outcome)),
    "reverted": Json(source.reverted),
    "sourceReference": {
      "transaction": match source.tx {
        Some(tx) => Json(tx)
        None => Json::null()
      },
      "operationIndex": if source.position < 0 {
        Json::null()
      } else {
        Json(source.position)
      },
      "eventSeq": match source.seq {
        Some(seq) => Json(seq.to_double())
        None => Json::null()
      },
      "initialKey": if source.tx == None {
        Json(source.key)
      } else {
        Json::null()
      },
    },
  }
}

///|
fn anomaly_v4_constraint_json(c : AnomalyV4Constraint) -> Json {
  {
    "key": Json(c.key),
    "before": Json(c.before),
    "after": Json(c.after),
    "source": c.evidence,
  }
}

///|
/// A bounded path search proves a cycle in the explicitly supplied order facts.
/// This is not a dependency-cycle or isolation-model classification.
fn anomaly_v4_constraint(
  work : AnomalyV4Work,
  candidate : AnomalyV4Constraint,
) -> Unit {
  if !anomaly_v4_charge(work) {
    return
  }
  if work.constraints.length() >= 10000 {
    work.limited = true
    return
  }
  let graph = work.adjacency.get_or_default(candidate.key, Map([]))
  let existing = graph.get_or_default(candidate.before, [])
  for index in existing {
    if !anomaly_v4_charge(work) {
      return
    }
    if work.constraints[index].after == candidate.after {
      return
    }
  }
  let parents : Map[String, Int32] = Map([])
  let seen : Map[String, Bool] = Map([])
  let queue : Array[String] = [candidate.after]
  seen[candidate.after] = true
  let mut head = 0
  let mut found = candidate.before == candidate.after
  while head < queue.length() && !found {
    if !anomaly_v4_charge(work) {
      return
    }
    let current = queue[head]
    head += 1
    for index in graph.get_or_default(current, []) {
      if !anomaly_v4_charge(work) {
        return
      }
      let edge = work.constraints[index]
      if !seen.contains(edge.after) {
        seen[edge.after] = true
        parents[edge.after] = index
        queue.push(edge.after)
      }
      if edge.after == candidate.before {
        found = true
        break
      }
    }
  }
  if found {
    if work.witness_constraints >= 4096 {
      work.truncated = true
      return
    }
    let cycle : Array[Json] = [anomaly_v4_constraint_json(candidate)]
    let backwards : Array[Json] = []
    let mut current = candidate.before
    while current != candidate.after {
      let index = parents.at(current)
      if work.witness_constraints + backwards.length() + 2 > 4096 {
        work.truncated = true
        return
      }
      backwards.push(anomaly_v4_constraint_json(work.constraints[index]))
      current = work.constraints[index].before
    }
    backwards.rev_in_place()
    for edge in backwards {
      cycle.push(edge)
    }
    work.witness_constraints += cycle.length()
    anomaly_v4_emit(work, "version-order-conflict", "proved", {
      "key": Json(candidate.key),
      "constraints": Json(cycle),
      "scope": "The supplied strict version-order facts form a directed cycle; no automatic G0/G1a or isolation-model claim is made.",
    })
  }
  let edges = existing.copy()
  edges.push(work.constraints.length())
  graph[candidate.before] = edges
  work.adjacency[candidate.key] = graph
  work.constraints.push(candidate)
}

///|
fn anomaly_v4_status(value : Json) -> TxStatus {
  match value {
    String("committed") => Committed
    String("aborted") => Aborted
    _ => Unknown
  }
}

///|
fn anomaly_v4_string(value : Json) -> String {
  match value {
    String(text) => text
    _ => abort("Validated anomaly identity")
  }
}

///|
fn anomaly_v4_array(value : Json) -> Array[Json] {
  match value {
    Array(items) => items
    _ => []
  }
}

///|
fn anomaly_v4_index_source(
  sources : Map[String, Map[String, AnomalyV4Source]],
  source : AnomalyV4Source,
) -> Unit {
  let by_identity = sources.get_or_default(source.key, Map([]))
  by_identity[source.item.id] = source
  sources[source.key] = by_identity
}

///|
fn anomaly_v4_declared(
  history : History,
  sources : Map[String, Map[String, AnomalyV4Source]],
  outcomes : Map[String, TxStatus],
  operations : Array[AnomalyV4Operation],
  work : AnomalyV4Work,
) -> Unit {
  for key, identity in history.initial {
    if !anomaly_v4_charge(work) {
      return
    }
    anomaly_v4_index_source(sources, {
      tx: None,
      position: -1,
      key,
      item: { id: identity, value: Json::null(), },
      outcome: Committed,
      reverted: false,
      original: { "initialKey": Json(key), "version": Json(identity) },
      seq: None,
    })
  }
  for tx in history.transactions {
    if !anomaly_v4_charge(work) {
      return
    }
    outcomes[tx.id] = tx.status
    for position, op in tx.ops {
      if !anomaly_v4_charge(work) {
        return
      }
      let original : Json = {
        "type": Json(op_label(op.kind)),
        "key": Json(op.key),
        "version": Json(op.version),
      }
      let item : AnomalyV4Item = { id: op.version, value: Json::null(), }
      operations.push({
        tx: tx.id,
        position,
        key: op.key,
        write: op.kind == Write,
        items: [item],
        original,
        seq: None,
      })
      if op.kind == Write {
        anomaly_v4_index_source(sources, {
          tx: Some(tx.id),
          position,
          key: op.key,
          item,
          outcome: tx.status,
          reverted: false,
          original,
          seq: None,
        })
      }
    }
  }
  let keys = history.version_orders.keys().collect()
  keys.sort()
  for key in keys {
    let order = history.version_orders.at(key)
    for index in 1..<order.length() {
      anomaly_v4_constraint(work, {
        key,
        before: order[index - 1],
        after: order[index],
        evidence: {
          "basis": "caller-declared-version-order",
          "key": Json(key),
          "positions": Json([index - 1, index]),
          "declaredOrder": Json(order),
        },
      })
      if work.limited {
        return
      }
    }
  }
}

///|
fn anomaly_v4_capture(
  history : HistoryV4,
  normalized : Json,
  sources : Map[String, Map[String, AnomalyV4Source]],
  outcomes : Map[String, TxStatus],
  operations : Array[AnomalyV4Operation],
  work : AnomalyV4Work,
) -> Unit {
  let n = object_fields_unchecked_v3(normalized)
  for raw in anomaly_v4_array(n.get_or_default("transactions", Json::null())) {
    if !anomaly_v4_charge(work) {
      return
    }
    let tx = object_fields_unchecked_v3(raw)
    outcomes[anomaly_v4_string(tx.at("id"))] = anomaly_v4_status(
      tx.at("status"),
    )
  }
  let revoked : Map[String, Bool] = Map([])
  for raw in anomaly_v4_array(n.get_or_default("effects", Json::null())) {
    if !anomaly_v4_charge(work) {
      return
    }
    let effect = object_fields_unchecked_v3(raw)
    revoked[effect.at("seq").stringify()] = effect.get("revertedBy") !=
      Some(Json::null())
  }
  let positions : Map[String, Int32] = Map([])
  let root = object_fields_unchecked_v3(history.source_document)
  for raw in anomaly_v4_array(root.at("events")) {
    if !anomaly_v4_charge(work) {
      return
    }
    let event = object_fields_unchecked_v3(raw)
    let kind = event.get("kind")
    if kind == Some(Json("snapshot")) && history.data_model == RegisterV4 {
      let initial = object_fields_unchecked_v3(event.at("initial"))
      for key, version in initial {
        if !anomaly_v4_charge(work) {
          return
        }
        anomaly_v4_index_source(sources, {
          tx: None,
          position: -1,
          key,
          item: { id: anomaly_v4_string(version), value: Json::null(), },
          outcome: Committed,
          reverted: false,
          original: { "snapshot": raw, "initialKey": Json(key) },
          seq: None,
        })
      }
    }
    let is_write = kind == Some(Json("write")) || kind == Some(Json("append"))
    if !is_write &&
      kind != Some(Json("read")) &&
      kind != Some(Json("list_read")) {
      continue
    }
    let tx = anomaly_v4_string(event.at("tx"))
    let key = anomaly_v4_string(event.at("key"))
    let position = positions.get_or_default(tx, 0)
    positions[tx] = position + 1
    let seq = match event.at("seq") {
      Number(n, ..) => Some(n.to_int64())
      _ => None
    }
    let items : Array[AnomalyV4Item] = if history.data_model == RegisterV4 {
      [{ id: anomaly_v4_string(event.at("version")), value: Json::null(), }]
    } else if is_write {
      [{ id: anomaly_v4_string(event.at("id")), value: event.at("value"), }]
    } else {
      anomaly_v4_array(event.at("items")).map(raw => {
        let item = object_fields_unchecked_v3(raw)
        { id: anomaly_v4_string(item.at("id")), value: item.at("value"), }
      })
    }
    operations.push({
      tx,
      position,
      key,
      write: is_write,
      items,
      original: raw,
      seq,
    })
    if is_write {
      anomaly_v4_index_source(sources, {
        tx: Some(tx),
        position,
        key,
        item: items[0],
        outcome: outcomes.get_or_default(tx, Unknown),
        reverted: revoked.get_or_default(event.at("seq").stringify(), false),
        original: raw,
        seq,
      })
    }
    if operations.length() > 10000 {
      work.limited = true
      return
    }
  }
  match history.payload {
    ListSnapshot(parsed) => {
      let keys = parsed.initial.keys().collect()
      keys.sort()
      for key in keys {
        let initial = parsed.initial.at(key)
        for index in 1..<initial.length() {
          anomaly_v4_constraint(work, {
            key,
            before: parsed.items[initial[index - 1]].id,
            after: parsed.items[initial[index]].id,
            evidence: {
              "basis": "captured-initial-list-order",
              "initialKey": Json(key),
              "positions": Json([index - 1, index]),
            },
          })
          if work.limited {
            return
          }
        }
      }
      for item in parsed.items {
        if item.tx != None {
          continue
        }
        if !anomaly_v4_charge(work) {
          return
        }
        anomaly_v4_index_source(sources, {
          tx: None,
          position: -1,
          key: item.key,
          item: { id: item.id, value: Json(item.value), },
          outcome: Committed,
          reverted: false,
          original: {
            "snapshotIdentity": Json(item.id),
            "initialKey": Json(item.key),
            "value": Json(item.value),
          },
          seq: Some(item.seq),
        })
      }
    }
    _ => ()
  }
}

///|
fn anomaly_v4_inspect(
  history : HistoryV4,
  maximum : Int32,
  lost_updates~ : Bool = false,
) -> Json {
  let work : AnomalyV4Work = {
    maximum,
    checks: 0,
    limited: false,
    truncated: false,
    witness_constraints: 0,
    findings: [],
    gaps: [],
    constraints: [],
    adjacency: Map([]),
  }
  let supported = if lost_updates {
    history.data_model == RegisterV4
  } else {
    history.data_model != RelationSetV4
  }
  let valid_options = maximum >= 0 && maximum <= 1000000
  let sources : Map[String, Map[String, AnomalyV4Source]] = Map([])
  let outcomes : Map[String, TxStatus] = Map([])
  let operations : Array[AnomalyV4Operation] = []
  let normalized = match history.payload {
    RegisterSnapshot(_, n) => n
    ListSnapshot(parsed) => Some(parsed.normalized)
    RelationSnapshot(parsed) => Some(parsed.normalized)
  }
  if valid_options && supported {
    match history.payload {
      RegisterSnapshot(Some(h), None) =>
        anomaly_v4_declared(h, sources, outcomes, operations, work)
      _ =>
        anomaly_v4_capture(
          history,
          normalized.unwrap(),
          sources,
          outcomes,
          operations,
          work,
        )
    }
  }
  if normalized == None && supported && valid_options {
    for tx, outcome in outcomes {
      if outcome == Unknown {
        anomaly_v4_emit(work, "unknown-transaction-outcome", "gap", {
          "transaction": Json(tx),
        })
      }
    }
  }
  let list_sources : Map[String, AnomalyV4Source] = Map([])
  if history.data_model == AppendListV4 {
    for _, by_identity in sources {
      for identity, source in by_identity {
        list_sources[identity] = source
      }
    }
  }
  let own_append_tails : Map[String, Map[String, AnomalyV4Operation]] = Map([])
  if !work.limited && valid_options && supported {
    for op in operations {
      if !anomaly_v4_charge(work) {
        break
      }
      if op.write {
        let source = sources.at(op.key).at(op.items[0].id)
        if source.outcome == Committed &&
          !source.reverted &&
          history.data_model == RegisterV4 {
          match object_fields_unchecked_v3(op.original).get("predecessor") {
            Some(String(before)) =>
              anomaly_v4_constraint(work, {
                key: op.key,
                before,
                after: op.items[0].id,
                evidence: {
                  "basis": "explicit-captured-predecessor",
                  "write": anomaly_v4_operation_json(op),
                },
              })
            _ => ()
          }
        }
        if history.data_model == AppendListV4 &&
          source.outcome == Committed &&
          !source.reverted {
          let tails = own_append_tails.get_or_default(op.tx, Map([]))
          match tails.get(op.key) {
            Some(previous) =>
              anomaly_v4_constraint(work, {
                key: op.key,
                before: previous.items[0].id,
                after: op.items[0].id,
                evidence: {
                  "basis": "same-transaction-effective-append-program-order",
                  "beforeAppend": anomaly_v4_operation_json(previous),
                  "afterAppend": anomaly_v4_operation_json(op),
                },
              })
            None => ()
          }
          tails[op.key] = op
          own_append_tails[op.tx] = tails
        }
        if work.limited {
          break
        }
        continue
      }
      if outcomes.get(op.tx) != Some(Committed) {
        continue
      }
      let seen : Map[String, Bool] = Map([])
      let mut ordered = true
      for item_index, item in op.items {
        if !anomaly_v4_charge(work) {
          break
        }
        let source = sources.get_or_default(op.key, Map([])).get(item.id)
        let evidence : Map[String, Json] = {
          "read": anomaly_v4_operation_json(op),
          "key": Json(op.key),
          "identity": Json(item.id),
          "returnedItemIndex": Json(item_index),
          "originalValueReference": true,
        }
        if seen.contains(item.id) {
          anomaly_v4_emit(work, "identity-conflict", "proved", {
            "reason": "duplicate-identity-in-one-list-value",
            "observation": Json::object(evidence),
          })
          ordered = false
        }
        seen[item.id] = true
        match source {
          None => {
            ordered = false
            match list_sources.get(item.id) {
              Some(other) =>
                anomaly_v4_emit(work, "identity-conflict", "proved", {
                  "reason": "list-identity-key-mismatch",
                  "read": Json::object(evidence),
                  "source": anomaly_v4_source_json(other),
                })
              None =>
                anomaly_v4_emit(
                  work,
                  "missing-source",
                  "gap",
                  Json::object(evidence),
                )
            }
          }
          Some(source) => {
            evidence["source"] = anomaly_v4_source_json(source)
            if source.item.value != item.value {
              anomaly_v4_emit(work, "identity-conflict", "proved", {
                "reason": "list-identity-value-mismatch",
                "observation": Json::object(evidence),
              })
              ordered = false
              continue
            }
            if source.tx == Some(op.tx) && source.position > op.position {
              anomaly_v4_emit(
                work,
                "future-read",
                "proved",
                Json::object(evidence),
              )
              ordered = false
            } else if source.tx != Some(op.tx) && source.outcome == Unknown {
              anomaly_v4_emit(
                work,
                "unknown-writer",
                "gap",
                Json::object(evidence),
              )
              ordered = false
            } else if source.tx != Some(op.tx) &&
              source.seq is Some(writer_seq) &&
              op.seq is Some(read_seq) &&
              writer_seq >= read_seq {
              anomaly_v4_emit(work, "source-observation-order", "gap", {
                "reason": "Cross-transaction event order does not prove a future read",
                "observation": Json::object(evidence),
              })
            }
            if source.reverted || source.outcome == Aborted {
              anomaly_v4_emit(
                work,
                "source-effect-not-committed",
                "gap",
                Json::object(evidence),
              )
            }
            if source.reverted || source.outcome != Committed {
              ordered = false
            }
          }
        }
      }
      if work.limited {
        break
      }
      if history.data_model == AppendListV4 && ordered {
        for index in 1..<op.items.length() {
          anomaly_v4_constraint(work, {
            key: op.key,
            before: op.items[index - 1].id,
            after: op.items[index].id,
            evidence: {
              "basis": "complete-source-valid-list-observation",
              "read": anomaly_v4_operation_json(op),
              "positions": Json([index - 1, index]),
            },
          })
          if work.limited {
            break
          }
        }
      }
      if work.limited {
        break
      }
    }
  }
  if lost_updates && supported && valid_options && !work.limited {
    lost_update_v4_check(
      history, normalized, sources, outcomes, operations, work,
    )
  }
  let input_coverage = match normalized {
    Some(n) =>
      object_fields_unchecked_v3(n).get_or_default("coverage", Json::null())
    None =>
      {
        "complete": true,
        "gaps": [],
        "basis": "caller-declared-history; no capture completeness authentication",
      }
  }
  let input_complete = object_fields_unchecked_v3(input_coverage).get(
      "complete",
    ) ==
    Some(Json(true))
  let complete = valid_options &&
    supported &&
    input_complete &&
    !work.limited &&
    !work.truncated &&
    work.gaps.is_empty()
  let status = if !valid_options {
    "invalid"
  } else if !supported {
    "unsupported"
  } else if !work.findings.is_empty() {
    "findings"
  } else if complete {
    "checked"
  } else {
    "inconclusive"
  }
  let report : Json = {
    "format": "moontxnwitness-anomaly-inspection/v4",
    "schemaVersion": 4,
    "semanticContract": "moontxnwitness-source-anomalies-v4-1",
    "algorithm": Json(
      if lost_updates {
        "v4-register-source-lost-update-1"
      } else {
        "v4-source-index-and-order-witness-1"
      },
    ),
    "dataModel": Json(v4_model_name(history.data_model)),
    "status": Json(status),
    "scope": {
      "diagnosticOnly": true,
      "coverageMeaning": "Completion of the supported source/identity/order checks plus supplied capture coverage; not validation of every consistency rule",
      "acceptedInput": "Validated HistoryV4 only; malformed structures and duplicate write identities rejected by its constructor are outside this diagnostic entry point",
      "acceptsIsolationModels": false,
      "authenticityVerified": false,
      "crossTransactionEventOrderProvesFutureRead": false,
      "operationIndex": "zero-based point/list data-operation position within its transaction; control events retain their original seq",
      "sourceReferences": "Original operations and business values are retained once in observations.document. Transaction/operationIndex/eventSeq and returnedItemIndex resolve evidence references.",
      "orderConflict": "contradictory supplied strict version-order facts only; not automatic G1a or G0",
      "missingSource": "coverage gap; not an unwritten-read or G1a proof",
    },
    "observations": {
      "sourceFormat": Json(history.source_format),
      "document": history.source_document,
    },
    "coverage": {
      "complete": Json(complete),
      "inputCoverage": input_coverage,
      "diagnosticGaps": Json(work.gaps),
      "budgetExhausted": Json(work.limited),
      "findingsTruncated": Json(work.truncated),
    },
    "findings": Json(work.findings),
    "execution": {
      "counterContract": Json(
        if lost_updates {
          "v4-register-source-lost-update-checks-1"
        } else {
          "v4-anomaly-source-checks-1"
        },
      ),
      "maxChecks": Json(maximum),
      "checks": Json(work.checks),
      "indexedOperations": Json(operations.length()),
      "orderConstraints": Json(work.constraints.length()),
      "limits": {
        "operations": 10000,
        "orderConstraints": 10000,
        "reportedFindingsAndGaps": 256,
        "witnessConstraints": 4096,
        "maxChecks": 1000000,
      },
    },
  }
  if lost_updates {
    let root = object_fields_unchecked_v3(report)
    root["profile"] = Json("register-source-lost-update/v1")
    let scope = object_fields_unchecked_v3(root.at("scope"))
    scope["dirtyUpdateSupported"] = Json(false)
    scope["dirtyUpdateReason"] = Json(
      "This inspection profile does not implement dirty-update checks; version adjacency alone is not an observed write base or a read",
    )
    scope["lostUpdateSupport"] = Json(
      "Unique-version point registers only; actual first external reads, confirmed source identity and final effective writes; no list-prefix or business-value comparison",
    )
  }
  v4_json_copy(report)
}

///|
/// Inspect validated register/list observations without changing analysis semantics.
pub fn inspect_anomalies_v4(
  history : HistoryV4,
  max_checks~ : Int32 = 1000000,
) -> Json {
  anomaly_v4_inspect(history, max_checks)
}

///|
/// Expected work budget comes from the caller, not from the supplied artifact.
pub fn verify_anomalies_v4(
  history : HistoryV4,
  supplied : Json,
  max_checks~ : Int32 = 1000000,
) -> Bool {
  supplied == anomaly_v4_inspect(history, max_checks)
}
