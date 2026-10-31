///|
pub(all) enum RelationProgramReplayModeV4 {
  RelationSnapshotPrefixes
  RelationSerialOrder
} derive(Eq)

///|
pub extend RelationProgramReplayModeV4 with Eq::{equal, not_equal}

///|
pub struct RelationProgramReplayV4 {
  priv record : Json
}

///|
priv struct OriginalRowRunV4 {
  own : Map[String, Json]
  valid : Bool
}

///|
fn original_row_fields_v4(raw : Json) -> Map[String, Json] {
  match raw {
    Object(fields) => fields
    _ => Map([])
  }
}

///|
fn original_row_array_v4(raw : Json) -> Array[Json] {
  match raw {
    Array(values) => values
    _ => []
  }
}

///|
fn original_row_slot_v4(
  schema : Map[String, Json],
  table : String,
  key : Json,
) -> String {
  let definition = original_row_fields_v4(
    schema.get_or_default(table, Json::null()),
  )
  let primary = capture_source_string_v4(
    definition.get_or_default("primaryKey", Json::null()),
  )
  let columns = original_row_fields_v4(
    definition.get_or_default("columns", Json::null()),
  )
  Json([
    Json("original-relation-keyslot-v1"),
    Json(table),
    columns.get_or_default(primary, Json::null()),
    key,
  ]).stringify()
}

///|
/// Original JSON only: no normalized action, source graph, model status or inferred order is imported.
fn original_row_run_v4(
  events : Array[Json],
  snapshot : Map[String, Json],
  schema : Map[String, Json],
  effects_only : Bool,
  budget : ModelSourceBudgetV4,
  blockers : Array[Json],
) -> OriginalRowRunV4 {
  let mut own : Map[String, Json] = Map([])
  let marks : Array[(String, Map[String, Json])] = []
  let mut valid = true
  for event in events {
    if !model_source_charge_v4(budget) {
      valid = false
      break
    }
    let e = original_row_fields_v4(event)
    let kind = capture_source_string_v4(e.get_or_default("kind", Json::null()))
    if kind == "savepoint" {
      marks.push(
        (
          capture_source_string_v4(e.get_or_default("instance", Json::null())),
          own.copy(),
        ),
      )
    } else if kind == "rollback_to" || kind == "release" {
      let instance = capture_source_string_v4(
        e.get_or_default("instance", Json::null()),
      )
      let mut found = -1
      for i, mark in marks {
        if !model_source_charge_v4(budget) {
          valid = false
          break
        }
        if mark.0 == instance {
          found = i
        }
      }
      if found < 0 {
        valid = false
        break
      }
      if kind == "rollback_to" {
        own = marks[found].1.copy()
      }
      let keep = if kind == "rollback_to" { found + 1 } else { found }
      while marks.length() > keep {
        ignore(marks.pop())
      }
    } else if kind == "row_write" {
      let table = capture_source_string_v4(
        e.get_or_default("relation", Json::null()),
      )
      let slot = original_row_slot_v4(
        schema,
        table,
        e.get_or_default("key", Json::null()),
      )
      let previous = own
        .get(slot)
        .unwrap_or(snapshot.get_or_default(slot, Json::null()))
      let prior = original_row_fields_v4(previous)
      let present = prior.get("present") == Some(Json(true))
      let action = capture_source_string_v4(
        e.get_or_default("action", Json::null()),
      )
      if !["insert", "update", "delete"].contains(action) {
        valid = false
        break
      }
      if !effects_only {
        let expected_parent = prior.get_or_default("version", Json::null())
        if (action == "insert" && present) ||
          (action != "insert" && !present) ||
          e.get("predecessor") != Some(expected_parent) {
          if blockers.length() < 16 {
            blockers.push({
              "code": "original-row-write-precondition-mismatch",
              "actualWrite": event,
              "actualSlotBeforeWrite": previous,
              "sourceRole": "no SELECT synthesized",
            })
          }
          valid = false
          break
        }
      }
      own[slot] = {
        "present": Json(action != "delete"),
        "version": e.get_or_default("version", Json::null()),
        "values": e.get_or_default("values", Json::null()),
        "originalEffect": event,
      }
    } else if kind == "row_read" {
      if effects_only {
        continue
      }
      let table = capture_source_string_v4(
        e.get_or_default("relation", Json::null()),
      )
      let definition = original_row_fields_v4(
        schema.get_or_default(table, Json::null()),
      )
      let primary = definition.get_or_default("primaryKey", Json::null())
      let predicate = original_row_array_v4(
        e.get_or_default("predicate", Json::null()),
      )
      let rows = original_row_array_v4(e.get_or_default("rows", Json::null()))
      if e.get("complete") != Some(Json(true)) ||
        predicate.length() != 1 ||
        rows.length() > 1 {
        valid = false
        break
      }
      let term = original_row_fields_v4(predicate[0])
      if term.get("column") != Some(primary) ||
        term.get("op") != Some(Json("eq")) {
        valid = false
        break
      }
      let key = term.get_or_default("value", Json::null())
      let slot = original_row_slot_v4(schema, table, key)
      let actual = own
        .get(slot)
        .unwrap_or(snapshot.get_or_default(slot, Json::null()))
      let cell = original_row_fields_v4(actual)
      let present = cell.get("present") == Some(Json(true))
      let mut matches = if present {
        rows.length() == 1
      } else {
        rows.is_empty()
      }
      if matches && present {
        let row = original_row_fields_v4(rows[0])
        matches = row.get("key") == Some(key) &&
          row.get("version") == cell.get("version") &&
          row.get("values") == cell.get("values")
      }
      if !matches {
        if blockers.length() < 16 {
          blockers.push({
            "code": "original-complete-point-query-mismatch",
            "actualQuery": event,
            "actualSlotAtDelivery": actual,
          })
        }
        valid = false
        break
      }
    } else {
      valid = false
      break
    }
  }
  { own, valid: valid && !budget.limited, }
}

///|
fn original_relation_program_replay_v4(
  history : HistoryV4,
  certificate : Json,
  mode : RelationProgramReplayModeV4,
  maximum : Int32,
) -> RelationProgramReplayV4 {
  let budget : ModelSourceBudgetV4 = { maximum, checks: 0, limited: false, }
  let root = original_row_fields_v4(history.source_document)
  let schema = original_row_fields_v4(
    root.get_or_default("relationSchema", Json::null()),
  )
  let scope = original_row_fields_v4(root.get_or_default("scope", Json::null()))
  let coverage = original_row_array_v4(
    scope.get_or_default("completeSnapshotTables", Json::null()),
  )
  let events = original_row_array_v4(
    root.get_or_default("events", Json::null()),
  )
  let mut valid = root.get("dataModel") == Some(Json("relation-set-v1")) &&
    scope.get("exclusiveWriters") == Some(Json(true)) &&
    original_row_array_v4(root.get_or_default("gaps", Json::null())).is_empty() &&
    !events.is_empty() &&
    !schema.is_empty()
  let blockers : Array[Json] = []
  let programs : Map[String, Array[Json]] = Map([])
  let outcomes : Map[String, String] = Map([])
  let requests : Map[String, Bool] = Map([])
  let initial : Map[String, Json] = Map([])
  let version_ids : Map[String, Bool] = Map([])
  for table, _ in schema {
    if !model_source_charge_v4(budget) {
      valid = false
      break
    }
    if !coverage.contains(Json(table)) {
      valid = false
    }
  }
  for i, event in events {
    if !model_source_charge_v4(budget) {
      valid = false
      break
    }
    let e = original_row_fields_v4(event)
    if e.get("seq") != Some(Json(i + 1)) {
      valid = false
      break
    }
    let kind = capture_source_string_v4(e.get_or_default("kind", Json::null()))
    if i == 0 {
      if kind != "snapshot" || e.get("consistent") != Some(Json(true)) {
        valid = false
        break
      }
      let tables = original_row_fields_v4(
        e.get_or_default("initial", Json::null()),
      )
      for table, _ in schema {
        let rows = match tables.get(table) {
          Some(Array(rows)) => rows
          _ => {
            valid = false
            []
          }
        }
        for row in rows {
          if !model_source_charge_v4(budget) {
            valid = false
            break
          }
          let r = original_row_fields_v4(row)
          let slot = original_row_slot_v4(
            schema,
            table,
            r.get_or_default("key", Json::null()),
          )
          let version = capture_source_string_v4(
            r.get_or_default("version", Json::null()),
          )
          if initial.contains(slot) ||
            version == "" ||
            version_ids.contains(version) {
            valid = false
            break
          }
          version_ids[version] = true
          initial[slot] = {
            "present": true,
            "version": Json(version),
            "values": r.get_or_default("values", Json::null()),
            "originalInitialRow": row,
          }
        }
      }
      continue
    }
    let tx = capture_source_string_v4(e.get_or_default("tx", Json::null()))
    if tx == "" {
      valid = false
      break
    }
    if kind == "begin" {
      if programs.contains(tx) {
        valid = false
        break
      }
      programs[tx] = []
      outcomes[tx] = "unknown"
    } else {
      if !programs.contains(tx) || outcomes.get(tx) != Some("unknown") {
        valid = false
        break
      }
      if kind == "commit_request" {
        if requests.contains(tx) {
          valid = false
          break
        }
        requests[tx] = true
      } else if kind == "commit_ok" {
        if !requests.get_or_default(tx, false) {
          valid = false
          break
        }
        outcomes[tx] = "committed"
      } else if kind == "rollback_ok" {
        outcomes[tx] = "aborted"
      } else if ["row_write", "row_read", "savepoint", "rollback_to", "release"].contains(
          kind,
        ) {
        if kind == "row_write" {
          let version = capture_source_string_v4(
            e.get_or_default("version", Json::null()),
          )
          if version == "" || version_ids.contains(version) {
            valid = false
            break
          }
          version_ids[version] = true
        }
        programs.at(tx).push(event)
      } else {
        valid = false
        blockers.push({
          "code": "unsupported-or-unprojected-original-operation",
          "event": event,
        })
        break
      }
    }
  }
  if programs.length() > 128 {
    valid = false
  }
  for _, outcome in outcomes {
    if !model_source_charge_v4(budget) {
      valid = false
      break
    }
    if outcome == "unknown" {
      valid = false
    }
  }
  let c = original_row_fields_v4(certificate)
  let order_raw = match c.get("commitOrder") {
    Some(Array(values)) => values
    _ => {
      valid = false
      []
    }
  }
  let visibility = match c.get("visibilityPrefixes") {
    Some(Array(values)) => values
    _ => {
      valid = false
      []
    }
  }
  let committed = outcomes
    .keys()
    .collect()
    .filter(tx => outcomes.at(tx) == "committed")
  let order : Array[String] = []
  let ranks : Map[String, Int32] = Map([])
  if order_raw.length() != committed.length() {
    valid = false
  }
  for i, raw in order_raw {
    if !model_source_charge_v4(budget) {
      valid = false
      break
    }
    let tx = capture_source_string_v4(raw)
    if !committed.contains(tx) || ranks.contains(tx) {
      valid = false
      break
    }
    ranks[tx] = i
    order.push(tx)
  }
  let prefixes : Map[String, Int32] = Map([])
  for raw in visibility {
    if !model_source_charge_v4(budget) {
      valid = false
      break
    }
    let v = original_row_fields_v4(raw)
    let tx = capture_source_string_v4(
      v.get_or_default("transaction", Json::null()),
    )
    let count = match v.get("visiblePrefixLength") {
      Some(Number(n, ..)) if n >= 0.0 &&
        n <= 128.0 &&
        n.to_int().to_double() == n => n.to_int()
      _ => -1
    }
    let seen = match v.get("visibleTransactions") {
      Some(Array(values)) => values
      _ => {
        valid = false
        []
      }
    }
    if !ranks.contains(tx) ||
      prefixes.contains(tx) ||
      count < 0 ||
      count > ranks.get_or_default(tx, -1) ||
      count != seen.length() ||
      (mode == RelationSerialOrder && count != ranks.get_or_default(tx, -1)) {
      valid = false
      break
    }
    for i in 0..<count {
      if !model_source_charge_v4(budget) {
        valid = false
        break
      }
      if seen[i] != Json(order[i]) {
        valid = false
      }
    }
    prefixes[tx] = count
  }
  if prefixes.length() != committed.length() {
    valid = false
  }
  let deltas : Map[String, Map[String, Json]] = Map([])
  if valid && !budget.limited {
    for tx in order {
      let effects = original_row_run_v4(
        programs.at(tx),
        Map([]),
        schema,
        true,
        budget,
        blockers,
      )
      if !effects.valid {
        valid = false
        break
      }
      deltas[tx] = effects.own
    }
  }
  let completed : Array[String] = []
  let last_writer : Map[String, String] = Map([])
  if valid && !budget.limited {
    for tx in order {
      if !model_source_charge_v4(budget) {
        valid = false
        break
      }
      let snapshot = initial.copy()
      for i in 0..<prefixes.at(tx) {
        for slot, value in deltas.at(order[i]) {
          if !model_source_charge_v4(budget) {
            valid = false
            break
          }
          snapshot[slot] = value
        }
      }
      for slot, _ in deltas.at(tx) {
        if !model_source_charge_v4(budget) {
          valid = false
          break
        }
        match last_writer.get(slot) {
          Some(writer) if ranks.at(writer) >= prefixes.at(tx) => {
            valid = false
            blockers.push({
              "code": "snapshot-row-write-conflict",
              "transaction": Json(tx),
              "previousWriter": Json(writer),
              "slot": Json(slot),
            })
          }
          _ => ()
        }
        last_writer[slot] = tx
      }
      if !valid || budget.limited {
        break
      }
      let run = original_row_run_v4(
        programs.at(tx),
        snapshot,
        schema,
        false,
        budget,
        blockers,
      )
      if !run.valid {
        valid = false
        break
      }
      completed.push(tx)
    }
  }
  {
    record: {
      "format": "moontxnwitness-original-row-program-replay/v4",
      "schemaVersion": 4,
      "semanticContract": "original-relation-point-program-CO-VIS-replay/v1",
      "algorithm": "raw-row-point-program-replay-1",
      "mode": if mode == RelationSnapshotPrefixes {
        Json("snapshot-prefixes")
      } else {
        Json("serial-full-prefix")
      },
      "status": if valid && !budget.limited {
        Json("checked-compatible")
      } else {
        Json("unknown")
      },
      "sourceSha256": Json(v3_dislock_sha256(history.source_text)),
      "originalSource": history.source_document,
      "certificate": v4_json_copy(certificate),
      "committedProgramsReplayed": Json(completed),
      "blockers": Json(blockers),
      "execution": model_mapping_counter_v4(
        budget, "original-row-program-reference-checks-1",
      ),
      "scope": {
        "acceptsIsolationModels": false,
        "originalJSONOnly": true,
        "normalizedProgramImported": false,
        "graphStatusImported": false,
        "inferredVersionOrderImported": false,
        "enumerationPerformed": false,
        "committedProgramsOnly": true,
        "opacityChecked": false,
        "serialFailureIsRCOrSIRefutation": false,
        "unknownSourceIsNotAbsence": true,
      },
    },
  }
}

///|
pub fn replay_relation_program_v4(
  history : HistoryV4,
  certificate : Json,
  mode~ : RelationProgramReplayModeV4,
  max_checks~ : Int32 = 1000000,
) -> Result[RelationProgramReplayV4, String] {
  if max_checks < 0 || max_checks > 1000000 {
    return Err("original row replay maxChecks must be within 0..1000000")
  }
  match history.payload {
    RelationSnapshot(_) =>
      Ok(
        original_relation_program_replay_v4(
          history, certificate, mode, max_checks,
        ),
      )
    _ => Err("original row replay requires relation-set-v1")
  }
}

///|
pub fn relation_program_replay_v4_json(value : RelationProgramReplayV4) -> Json {
  v4_json_copy(value.record)
}

///|
pub fn RelationProgramReplayV4::status(
  self : RelationProgramReplayV4,
) -> String {
  capture_source_string_v4(original_row_fields_v4(self.record).at("status"))
}

///|
fn model_relation_certificate_replay_v4(
  history : HistoryV4,
  order : Array[String],
  visibility : Array[Json],
  maximum : Int32,
) -> ModelRuleV4 {
  let replay = original_relation_program_replay_v4(
    history,
    { "commitOrder": Json(order), "visibilityPrefixes": Json(visibility) },
    RelationSnapshotPrefixes,
    maximum,
  )
  model_rule_v4(
    "original-row-program-prefix-replay",
    replay.status(),
    "independent original-JSON point-row program replay; an unsuccessful candidate is unknown and never a proof of RC or SI unsatisfiability",
    evidence=replay.record,
  )
}

///|
pub fn verify_relation_program_replay_v4(
  history : HistoryV4,
  report : Json,
  certificate : Json,
  mode~ : RelationProgramReplayModeV4,
  max_checks~ : Int32 = 1000000,
) -> Bool {
  match replay_relation_program_v4(history, certificate, mode~, max_checks~) {
    Ok(replayed) => report == replayed.record
    Err(_) => false
  }
}
