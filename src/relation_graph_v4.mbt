///|
priv struct RelationPointBudgetV4 {
  maximum : Int32
  mut checks : Int32
  mut limited : Bool
  mut reason : String
}

///|
priv struct RelationPointReadV4 {
  tx : String
  table : Int32
  key : Int32
  seq : Int64
  query_index : Int32
  rows : Array[RelationV3Row]
  own : Int32
  delivered_complete : Bool
  mut observed : Int32
  mut usable : Bool
  mut reason : String
}

///|
priv struct RelationPointIndexV4 {
  parsed : RelationV3Parsed
  keys : Array[RelationV3Key]
  key_indices : Map[String, Int32]
  versions : Map[String, Int32]
  deletes : Map[Int32, Array[Int32]]
  outcomes : Map[String, TxStatus]
  originals : Map[Int64, Json]
  uncertain_after : Map[String, Int64]
  mut window_unproven : Bool
  reads : Array[RelationPointReadV4]
  surviving : FixedArray[Bool]
  final_set : FixedArray[Bool]
  finals : Map[String, Map[Int32, Int32]]
  blocked : Map[Int32, Bool]
  ordered : Map[Int32, Bool]
  chains : Array[Array[Int32]]
  ranks : FixedArray[Int32]
  direct : Map[String, Array[Json]]
  diagnostics : Array[Json]
  gaps : Array[Json]
  mut journal_complete : Bool
  mut reads_complete : Bool
  mut orders_complete : Bool
}

///|
/// A point-row adapter. Node containers have no synthetic register operations.
pub struct RelationPointGraphV4 {
  priv base : ClassificationModelV3Graph
  priv index : RelationPointIndexV4
  priv checks : Int32
  priv maximum : Int32
  priv limited : Bool
}

///|
fn relation_point_charge_v4(budget : RelationPointBudgetV4) -> Bool {
  if budget.checks >= budget.maximum {
    budget.limited = true
    budget.reason = "relation-point-construction-budget"
    false
  } else {
    budget.checks += 1
    true
  }
}

///|
fn relation_point_key_identity_v4(
  table : RelationV3Table,
  value : Json,
) -> String {
  let framed : Json = [Json(table.name), Json(table.primary_type), value]
  framed.stringify()
}

///|
fn relation_point_key_json_v4(
  index : RelationPointIndexV4,
  key : Int32,
) -> Json {
  if key < 0 {
    return Json::null()
  }
  let identity = index.keys[key]
  let table = index.parsed.tables[identity.table]
  {
    "graphKey": Json("relation-point-key-" + key.to_string()),
    "relation": Json(table.name),
    "primaryColumn": Json(table.primary),
    "primaryType": Json(table.primary_type),
    "primaryKey": identity.wire,
  }
}

///|
fn relation_point_gap_v4(
  index : RelationPointIndexV4,
  code : String,
  key : Int32,
  seq : Int64,
  block~ : Bool = false,
) -> Unit {
  index.gaps.push({
    "code": Json(code),
    "identity": relation_point_key_json_v4(index, key),
    "observationSeq": Json(seq.to_double()),
  })
  if block && key >= 0 {
    index.blocked[key] = true
  }
}

///|
fn relation_point_source_json_v4(
  index : RelationPointIndexV4,
  source : Int32,
) -> Json {
  if source < 0 {
    return Json::null()
  }
  let row = index.parsed.sources[source]
  {
    "fact": index.parsed.source_evidence[source],
    "original": index.originals.get_or_default(row.seq, Json::null()),
    "effectAuditComplete": Json(index.journal_complete),
    "survivesSavepoints": if index.journal_complete {
      Json(index.surviving[source])
    } else {
      Json::null()
    },
    "finalCommittedEffect": if index.journal_complete {
      Json(index.final_set[source])
    } else {
      Json::null()
    },
    "writerOutcome": match row.writer {
      None => Json("initial")
      Some(tx) =>
        Json(
          match index.outcomes.get(tx) {
            Some(Committed) => "committed"
            Some(Aborted) => "aborted"
            _ => "unknown"
          },
        )
    },
  }
}

///|
fn relation_point_direct_v4(
  index : RelationPointIndexV4,
  category : String,
  code : String,
  read : RelationPointReadV4,
  source : Int32,
  expected~ : Int32 = -1,
) -> Unit {
  let proofs = index.direct.get_or_default(category, [])
  proofs.push({
    "kind": "source-checked-relation-point-direct",
    "category": Json(category),
    "code": Json(code),
    "transaction": Json(read.tx),
    "observationSeq": Json(read.seq.to_double()),
    "queryIndex": Json(read.query_index),
    "identity": relation_point_key_json_v4(index, read.key),
    "original": index.originals.get_or_default(read.seq, Json::null()),
    "source": relation_point_source_json_v4(index, source),
    "expectedLocalEffect": relation_point_source_json_v4(index, expected),
  })
  index.direct[category] = proofs
}

///|
fn relation_point_empty_index_v4(
  parsed : RelationV3Parsed,
) -> RelationPointIndexV4 {
  let keys = parsed.keys.copy()
  let key_indices : Map[String, Int32] = Map([])
  for position, key in keys {
    key_indices[relation_point_key_identity_v4(
      parsed.tables[key.table],
      key.wire,
    )] = position
  }
  let versions : Map[String, Int32] = Map([])
  let deletes : Map[Int32, Array[Int32]] = Map([])
  for position, source in parsed.sources {
    versions[source.row.version] = position
    if source.action == "delete" {
      let candidates = deletes.get_or_default(source.row.key, [])
      candidates.push(position)
      deletes[source.row.key] = candidates
    }
  }
  let originals : Map[Int64, Json] = Map([])
  let uncertain_after : Map[String, Int64] = Map([])
  match object_fields_unchecked_v3(parsed.normalized).get("observations") {
    Some(Array(observations)) =>
      for raw in observations {
        match object_fields_unchecked_v3(raw).get("seq") {
          Some(Number(seq, ..)) => {
            originals[seq.to_int64()] = raw
            let fields = object_fields_unchecked_v3(raw)
            let unproved = match fields.get("kind") {
              Some(String(kind)) =>
                ["statement", "condition", "rows"].contains(kind)
              _ => false
            }
            if unproved {
              match fields.get("tx") {
                Some(String(tx)) =>
                  match uncertain_after.get(tx) {
                    Some(previous) if previous <= seq.to_int64() => ()
                    _ => uncertain_after[tx] = seq.to_int64()
                  }
                _ => ()
              }
            }
          }
          _ => ()
        }
      }
    _ => ()
  }
  let outcomes : Map[String, TxStatus] = Map([])
  for program in parsed.programs {
    outcomes[program.id] = program.status
  }
  {
    parsed,
    keys,
    key_indices,
    versions,
    deletes,
    outcomes,
    originals,
    uncertain_after,
    window_unproven: false,
    reads: [],
    surviving: FixedArray::make(parsed.sources.length(), false),
    final_set: FixedArray::make(parsed.sources.length(), false),
    finals: Map([]),
    blocked: Map([]),
    ordered: Map([]),
    chains: [],
    ranks: FixedArray::make(parsed.sources.length(), -1),
    direct: Map([]),
    diagnostics: [],
    gaps: match object_fields_unchecked_v3(parsed.normalized).get("coverage") {
      Some(Object(coverage)) =>
        match coverage.get("gaps") {
          Some(Array(gaps)) => gaps.copy()
          _ => []
        }
      _ => []
    },
    journal_complete: false,
    reads_complete: false,
    orders_complete: false,
  }
}

///|
fn relation_point_find_key_v4(
  index : RelationPointIndexV4,
  table : Int32,
  value : RelationV3Cell,
) -> Int32 {
  let wire = relation_v3_wire(value)
  let encoded = relation_point_key_identity_v4(index.parsed.tables[table], wire)
  match index.key_indices.get(encoded) {
    Some(key) => key
    None => {
      let key = index.keys.length()
      index.keys.push({ table, value, wire, })
      index.key_indices[encoded] = key
      key
    }
  }
}

///|
fn relation_point_initial_v4(
  index : RelationPointIndexV4,
  key : Int32,
) -> Int32 {
  if key >= 0 && key < index.parsed.initial.length() {
    index.parsed.initial[key]
  } else {
    -1
  }
}

///|
fn relation_point_program_known_v4(
  index : RelationPointIndexV4,
  tx : String,
  seq : Int64,
) -> Bool {
  if index.window_unproven {
    return false
  }
  match index.uncertain_after.get(tx) {
    Some(boundary) => seq < boundary
    None => true
  }
}

///|
fn relation_point_window_unproven_v4(history : HistoryV4) -> Bool {
  match history.source_document {
    Object(root) =>
      match root.get("gaps") {
        Some(Array(gaps)) => !gaps.is_empty()
        _ => false
      }
    _ => true
  }
}

///|
/// A declared write predecessor is source metadata, not a delivered SELECT.
/// Once it cannot be explained, later own-state expectations are unproven.
fn relation_point_unproven_write_v4(
  index : RelationPointIndexV4,
  source_index : Int32,
  code : String,
  expected~ : Int32 = -1,
) -> Unit {
  let source = index.parsed.sources[source_index]
  relation_point_gap_v4(index, code, source.row.key, source.seq, block=true)
  index.diagnostics.push({
    "code": "unproven-local-row-write-source",
    "reason": Json(code),
    "identity": relation_point_key_json_v4(index, source.row.key),
    "original": index.originals.get_or_default(source.seq, Json::null()),
    "declaredEffect": index.parsed.source_evidence[source_index],
    "expectedLocalEffect": if expected >= 0 {
      index.parsed.source_evidence[expected]
    } else {
      Json::null()
    },
    "establishesReadAnomaly": false,
  })
  match source.writer {
    Some(tx) =>
      match index.uncertain_after.get(tx) {
        Some(previous) if previous <= source.seq => ()
        _ => index.uncertain_after[tx] = source.seq
      }
    _ => ()
  }
}

///|
fn relation_point_journal_v4(
  index : RelationPointIndexV4,
  budget : RelationPointBudgetV4,
) -> Unit {
  for program in index.parsed.programs {
    let own : Map[Int32, Int32] = Map([])
    let trail : Array[(Int32, Int32, Int32)] = []
    let scopes : Array[(String, Int32)] = []
    let mut query_index = 0
    for action in program.actions {
      if !relation_point_charge_v4(budget) {
        return
      }
      match action {
        WriteRow(source_index) => {
          let source = index.parsed.sources[source_index]
          let key = source.row.key
          let previous = own.get_or_default(key, -2)
          if program.status == Committed &&
            relation_point_program_known_v4(index, program.id, source.seq) {
            if previous >= 0 {
              let prior = index.parsed.sources[previous]
              let present = prior.action != "delete"
              if source.predecessor != Some(prior.row.version) ||
                (source.action == "insert") == present {
                relation_point_unproven_write_v4(
                  index,
                  source_index,
                  "invalid-local-row-write",
                  expected=previous,
                )
              }
            } else {
              match source.predecessor {
                Some(version) =>
                  match index.versions.get(version) {
                    Some(prior) if index.parsed.sources[prior].writer ==
                      Some(program.id) &&
                      index.parsed.sources[prior].seq < source.seq =>
                      relation_point_unproven_write_v4(
                        index, source_index, "own-predecessor-not-active",
                      )
                    _ => ()
                  }
                _ => ()
              }
            }
          }
          trail.push((key, previous, source_index))
          own[key] = source_index
          index.surviving[source_index] = true
        }
        QueryRows(table, predicate, rows, seq) => {
          let key = if predicate.length() == 1 &&
            predicate[0].column == -1 &&
            predicate[0].op == "eq" {
            relation_point_find_key_v4(index, table, predicate[0].value)
          } else {
            -1
          }
          let delivered_complete = match index.originals.get(seq) {
            Some(Object(raw)) => raw.get("complete") == Some(Json(true))
            _ => false
          }
          index.reads.push({
            tx: program.id,
            table,
            key,
            seq,
            query_index,
            rows,
            own: if key >= 0 {
              own.get_or_default(key, -2)
            } else {
              -2
            },
            delivered_complete,
            observed: -3,
            usable: false,
            reason: "pending",
          })
          query_index += 1
        }
        Mark(instance) => scopes.push((instance, trail.length()))
        Undo(instance) | Release(instance) => {
          let mut found = -1
          for position, scope in scopes {
            if scope.0 == instance {
              found = position
            }
          }
          if found < 0 {
            relation_point_gap_v4(
              index, "invalid-relation-savepoint-program", -1, 0L,
            )
            return
          }
          match action {
            Undo(_) =>
              while trail.length() > scopes[found].1 {
                let (key, previous, source_index) = trail.pop().unwrap()
                index.surviving[source_index] = false
                if previous == -2 {
                  let _ = own.remove(key)
                } else {
                  own[key] = previous
                }
              }
            _ => ()
          }
          let retained = if action is Undo(_) { found + 1 } else { found }
          while scopes.length() > retained {
            let _ = scopes.pop()
          }
        }
      }
    }
    if program.status == Aborted {
      // The normalized lifecycle ledger revokes all effects on a confirmed
      // transaction rollback, while delivered read observations remain intact.
      for entry in trail {
        if !relation_point_charge_v4(budget) {
          return
        }
        index.surviving[entry.2] = false
      }
      index.finals[program.id] = Map([])
    } else {
      index.finals[program.id] = own
    }
    if program.status == Committed {
      for _, source in own {
        index.final_set[source] = true
      }
    }
  }
  for source_index, source in index.parsed.sources {
    if !relation_point_charge_v4(budget) {
      return
    }
    if source.writer is None {
      index.surviving[source_index] = true
      continue
    }
    let expected = object_fields_unchecked_v3(
        index.parsed.source_evidence[source_index],
      ).get("revertedBy") ==
      Some(Json::null())
    if expected != index.surviving[source_index] {
      relation_point_gap_v4(
        index,
        "relation-effect-ledger-mismatch",
        source.row.key,
        source.seq,
        block=true,
      )
    }
  }
  match
    object_fields_unchecked_v3(index.parsed.normalized).get("transactions") {
    Some(Array(transactions)) =>
      for tx in transactions {
        let fields = object_fields_unchecked_v3(tx)
        let id = match fields.get("id") {
          Some(String(id)) => id
          _ => ""
        }
        let finals = index.finals.get_or_default(id, Map([]))
        let computed : Array[Json] = []
        let final_sources = finals.values().collect()
        final_sources.sort()
        for source_index in final_sources {
          if !relation_point_charge_v4(budget) {
            return
          }
          computed.push(
            Json(index.parsed.sources[source_index].seq.to_double()),
          )
        }
        if fields.get("finalWrites") != Some(Json(computed)) {
          relation_point_gap_v4(
            index, "relation-final-effect-ledger-mismatch", -1, 0L,
          )
          for key, _ in finals {
            index.blocked[key] = true
          }
        }
      }
    _ =>
      relation_point_gap_v4(
        index, "missing-relation-transaction-ledger", -1, 0L,
      )
  }
  index.journal_complete = true
}

///|
/// A predecessor is a row effect source, never a fabricated SELECT read.
fn relation_point_parent_v4(
  index : RelationPointIndexV4,
  source_index : Int32,
  budget : RelationPointBudgetV4,
) -> Int32 {
  let target = index.parsed.sources[source_index]
  let mut current = source_index
  while true {
    if !relation_point_charge_v4(budget) {
      return -3
    }
    let source = index.parsed.sources[current]
    match source.predecessor {
      None => {
        if source.action != "insert" ||
          relation_point_initial_v4(index, source.row.key) >= 0 {
          relation_point_unproven_write_v4(
            index, current, "unlinked-row-insert-or-reinsert",
          )
          return -3
        }
        return -1
      }
      Some(version) => {
        let prior = index.versions.get_or_default(version, -1)
        if prior < 0 {
          relation_point_unproven_write_v4(
            index, current, "missing-row-predecessor-source",
          )
          return -3
        }
        let previous = index.parsed.sources[prior]
        if previous.row.key != target.row.key ||
          previous.seq >= source.seq ||
          (source.action == "insert") != (previous.action == "delete") {
          relation_point_unproven_write_v4(
            index, current, "invalid-row-predecessor-chain",
          )
          return -3
        }
        if previous.writer is None {
          return prior
        }
        if !index.surviving[prior] {
          relation_point_unproven_write_v4(
            index, current, "row-predecessor-was-revoked",
          )
          index.diagnostics.push({
            "code": "dirty-update-reverted-source",
            "original": index.originals.at(source.seq),
            "predecessor": relation_point_source_json_v4(index, prior),
          })
          return -3
        }
        if previous.writer == target.writer {
          current = prior
          continue
        }
        let outcome = index.outcomes.get(previous.writer.unwrap())
        if outcome != Some(Committed) || !index.final_set[prior] {
          relation_point_unproven_write_v4(
            index, current, "row-predecessor-not-final-committed-source",
          )
          index.diagnostics.push({
            "code": "dirty-or-intermediate-update-source",
            "original": index.originals.at(source.seq),
            "predecessor": relation_point_source_json_v4(index, prior),
          })
          return -3
        }
        return prior
      }
    }
  } nobreak {
    -3
  }
}

///|
fn relation_point_orders_v4(
  index : RelationPointIndexV4,
  budget : RelationPointBudgetV4,
) -> Unit {
  let successors : Map[Int32, Int32] = Map([])
  let roots : Map[Int32, Int32] = Map([])
  let totals = FixedArray::make(index.keys.length(), 0)
  for position, source in index.parsed.sources {
    if !relation_point_charge_v4(budget) {
      return
    }
    if !index.final_set[position] {
      continue
    }
    totals[source.row.key] += 1
    let parent = relation_point_parent_v4(index, position, budget)
    if budget.limited {
      return
    }
    if parent == -3 {
      continue
    }
    if parent == -1 {
      if roots.contains(source.row.key) {
        relation_point_gap_v4(
          index,
          "branched-row-absence-predecessor",
          source.row.key,
          source.seq,
          block=true,
        )
      } else {
        roots[source.row.key] = position
      }
    } else if successors.contains(parent) {
      relation_point_gap_v4(
        index,
        "branched-row-predecessor",
        source.row.key,
        source.seq,
        block=true,
      )
    } else {
      successors[parent] = position
    }
  }
  for key in 0..<index.keys.length() {
    if !relation_point_charge_v4(budget) {
      return
    }
    let chain : Array[Int32] = []
    index.chains.push(chain)
    if index.blocked.contains(key) {
      continue
    }
    let initial = relation_point_initial_v4(index, key)
    let mut current = if initial >= 0 {
      successors.get_or_default(initial, -1)
    } else {
      roots.get_or_default(key, -1)
    }
    let mut rank = 0
    if initial >= 0 {
      index.ranks[initial] = rank
    }
    while current >= 0 {
      if !relation_point_charge_v4(budget) {
        return
      }
      rank += 1
      index.ranks[current] = rank
      chain.push(current)
      current = successors.get_or_default(current, -1)
    }
    if chain.length() == totals[key] {
      index.ordered[key] = true
    } else {
      relation_point_gap_v4(
        index,
        "incomplete-row-version-order",
        key,
        0L,
        block=true,
      )
    }
  }
  index.orders_complete = index.blocked.is_empty()
}

///|
fn relation_point_reject_read_v4(
  index : RelationPointIndexV4,
  read : RelationPointReadV4,
  reason : String,
) -> Unit {
  read.usable = false
  read.reason = reason
  relation_point_gap_v4(index, reason, read.key, read.seq)
}

///|
fn relation_point_external_read_rule_v4(
  index : RelationPointIndexV4,
  read : RelationPointReadV4,
  source_index : Int32,
) -> String {
  let source = index.parsed.sources[source_index]
  match source.writer {
    Some(writer) if writer != read.tx => {
      if index.outcomes.get(writer) == Some(Aborted) ||
        !index.surviving[source_index] {
        relation_point_direct_v4(
          index, "G1a", "read-from-aborted-or-revoked-row-effect", read, source_index,
        )
        return "aborted-or-revoked-row-read-source"
      }
      if index.outcomes.get(writer) != Some(Committed) {
        return "unconfirmed-row-writer-outcome"
      }
      if !index.final_set[source_index] {
        relation_point_direct_v4(
          index, "G1b", "read-from-intermediate-row-effect", read, source_index,
        )
        return "intermediate-row-read-source"
      }
      ""
    }
    _ => ""
  }
}

///|
fn relation_point_reads_v4(
  index : RelationPointIndexV4,
  budget : RelationPointBudgetV4,
) -> Unit {
  for read in index.reads {
    if !relation_point_charge_v4(budget) {
      return
    }
    if index.outcomes.get(read.tx) != Some(Committed) {
      read.reason = "reader-not-committed"
      continue
    }
    if read.key < 0 {
      relation_point_reject_read_v4(
        index, read, "relation-predicate-outside-single-primary-eq",
      )
      continue
    }
    if !read.delivered_complete {
      relation_point_reject_read_v4(
        index, read, "relation-point-result-not-completely-delivered",
      )
      continue
    }
    if read.rows.length() > 1 || read.rows.any(row => row.key != read.key) {
      relation_point_reject_read_v4(
        index, read, "relation-point-result-key-or-uniqueness-mismatch",
      )
      continue
    }
    if !relation_point_program_known_v4(index, read.tx, read.seq) {
      relation_point_reject_read_v4(
        index, read, "relation-unproved-program-prefix",
      )
      continue
    }
    if read.own >= 0 {
      let expected = index.parsed.sources[read.own]
      let matches = if expected.action == "delete" {
        read.rows.is_empty()
      } else {
        read.rows.length() == 1 &&
        read.rows[0].version == expected.row.version &&
        read.rows[0].values == expected.row.values
      }
      if !matches {
        let observed = if read.rows.length() == 1 {
          index.versions.get_or_default(read.rows[0].version, -1)
        } else {
          -1
        }
        if observed >= 0 && read.rows.length() == 1 {
          let source = index.parsed.sources[observed]
          if source.seq < read.seq &&
            source.row.key == read.key &&
            source.row.values == read.rows[0].values &&
            source.action != "delete" {
            let _ = relation_point_external_read_rule_v4(index, read, observed)
          }
        }
        relation_point_direct_v4(
          index,
          "INT",
          "point-read-does-not-reflect-current-own-effect",
          read,
          observed,
          expected=read.own,
        )
        relation_point_reject_read_v4(
          index, read, "relation-local-read-state-mismatch",
        )
      } else {
        read.observed = read.own
        read.usable = true
        read.reason = "complete-own-at-delivery"
      }
      continue
    }
    if read.rows.length() == 1 {
      let row = read.rows[0]
      let source_index = index.versions.get_or_default(row.version, -1)
      if source_index < 0 {
        relation_point_reject_read_v4(
          index, read, "missing-relation-point-row-source",
        )
        continue
      }
      let source = index.parsed.sources[source_index]
      if source.seq >= read.seq ||
        source.row.key != read.key ||
        source.row.values != row.values ||
        source.action == "delete" {
        relation_point_reject_read_v4(
          index, read, "invalid-relation-point-row-source",
        )
        continue
      }
      read.observed = source_index
      match source.writer {
        Some(writer) if writer == read.tx => {
          relation_point_direct_v4(
            index, "INT", "own-row-source-not-active-at-read", read, source_index,
          )
          relation_point_reject_read_v4(
            index, read, "own-row-source-not-active-at-read",
          )
          continue
        }
        Some(_) => {
          let reason = relation_point_external_read_rule_v4(
            index, read, source_index,
          )
          if reason != "" {
            relation_point_reject_read_v4(index, read, reason)
            continue
          }
        }
        _ => ()
      }
      read.usable = true
      read.reason = "complete-version-bound-point-read"
      continue
    }
    if index.blocked.contains(read.key) {
      relation_point_reject_read_v4(
        index, read, "absence-has-no-complete-row-version-order",
      )
      continue
    }
    // An empty row set carries no tombstone identity. Resolve it only when one
    // absence state is possible, never by the nearest time or commit response.
    let mut count = 0
    let mut observed = -3
    if relation_point_initial_v4(index, read.key) < 0 {
      count += 1
      observed = -1
    }
    // Every raw delete remains a candidate, including aborted, revoked,
    // intermediate and unknown effects. Cross-connection event order is not
    // used to discard a competing absence producer.
    for source_index in index.deletes.get_or_default(read.key, []) {
      if !relation_point_charge_v4(budget) {
        return
      }
      count += 1
      observed = source_index
    }
    if count != 1 {
      relation_point_reject_read_v4(
        index,
        read,
        if count == 0 {
          "unexplained-point-absence"
        } else {
          "ambiguous-point-absence"
        },
      )
      continue
    }
    let coverage = object_fields_unchecked_v3(index.parsed.normalized).get(
      "coverage",
    )
    let snapshot_complete = match coverage {
      Some(Object(fields)) => fields.get("complete") == Some(Json(true))
      _ => false
    }
    if !snapshot_complete {
      relation_point_reject_read_v4(
        index, read, "absence-requires-complete-source-window",
      )
      continue
    }
    if observed >= 0 && !index.final_set[observed] {
      relation_point_reject_read_v4(
        index, read, "point-absence-source-not-final-committed",
      )
      continue
    }
    if observed >= 0 && index.parsed.sources[observed].seq >= read.seq {
      relation_point_reject_read_v4(
        index, read, "absence-source-was-not-observed-before-query",
      )
      continue
    }
    read.observed = observed
    read.usable = true
    read.reason = if observed == -1 {
      "unique-initial-point-absence"
    } else {
      "unique-final-tombstone-absence"
    }
  }
  index.reads_complete = relation_point_external_expectations_v4(index, budget)
}

///|
fn relation_point_internal_read_known_v4(read : RelationPointReadV4) -> Bool {
  read.key >= 0 &&
  read.delivered_complete &&
  read.rows.length() <= 1 &&
  (if read.rows.is_empty() { read.usable } else { read.observed >= 0 })
}

///|
fn relation_point_external_observation_v4(
  index : RelationPointIndexV4,
  read : RelationPointReadV4,
) -> Json {
  {
    "transaction": Json(read.tx),
    "identity": relation_point_key_json_v4(index, read.key),
    "readSeq": Json(read.seq.to_double()),
    "queryIndex": Json(read.query_index),
    "rowPresent": Json(!read.rows.is_empty()),
    "original": index.originals.at(read.seq),
    "readSource": relation_point_read_source_v4(index, read),
  }
}

///|
/// Delivered external reads persist across rollback. Own-at-delivery reads use
/// only their captured local overlay and never replace the external base.
fn relation_point_external_expectations_v4(
  index : RelationPointIndexV4,
  budget : RelationPointBudgetV4,
) -> Bool {
  let bases : Map[String, Map[Int32, RelationPointReadV4]] = Map([])
  for read in index.reads {
    if !relation_point_charge_v4(budget) {
      return false
    }
    if index.outcomes.get(read.tx) != Some(Committed) ||
      !relation_point_program_known_v4(index, read.tx, read.seq) {
      continue
    }
    if read.key < 0 {
      let _ = bases.remove(read.tx)
      continue
    }
    if read.own >= 0 {
      continue
    }
    let base = bases.get_or_default(read.tx, Map([]))
    bases[read.tx] = base
    if !relation_point_internal_read_known_v4(read) {
      let _ = base.remove(read.key)
      continue
    }
    match base.get(read.key) {
      Some(previous) => {
        let changed = previous.rows.is_empty() != read.rows.is_empty() ||
          (!read.rows.is_empty() && previous.observed != read.observed)
        if changed {
          relation_point_direct_v4(
            index,
            "INT",
            "external-point-read-differs-from-last-delivered-base",
            read,
            read.observed,
          )
          let proofs = index.direct.at("INT")
          let fields = object_fields_unchecked_v3(proofs[proofs.length() - 1])
          fields["expectedExternalObservation"] = relation_point_external_observation_v4(
            index, previous,
          )
          fields["actualExternalObservation"] = relation_point_external_observation_v4(
            index, read,
          )
          fields["rule"] = Json(
            "nearest-delivered-external-point-read-or-current-effective-own-write; rollback-revokes-writes-only",
          )
          relation_point_gap_v4(
            index,
            "relation-external-read-state-mismatch",
            read.key,
            read.seq,
          )
        }
      }
      None => ()
    }
    base[read.key] = read
  }
  true
}

///|
fn relation_point_edge_v4(
  _index : RelationPointIndexV4,
  from : String,
  to : String,
  kind : Dependency,
  key : Int32,
  first : String?,
  last : String?,
) -> Edge {
  {
    from,
    to,
    kind,
    key: Some("relation-point-key-" + key.to_string()),
    from_op: None,
    to_op: None,
    from_version: first,
    to_version: last,
    reason: match kind {
      WW =>
        "The captured row predecessor chain orders final committed row effects"
      WR => "The complete primary-key read has this unique committed row source"
      _ =>
        "The external primary-key read precedes the next installed row version in the verified chain"
    },
  }
}

///|
fn relation_point_emit_v4(
  edges : Array[Edge],
  sources : Map[Edge, Array[Json]],
  budget : RelationPointBudgetV4,
  edge : Edge,
  proof : Json,
) -> Bool {
  if edge.from == edge.to {
    return true
  }
  if !relation_point_charge_v4(budget) {
    return false
  }
  match sources.get(edge) {
    Some(proofs) => {
      proofs.push(proof)
      true
    }
    None =>
      if edges.length() >= 50000 {
        budget.limited = true
        budget.reason = "relation-point-edge-budget-50000"
        false
      } else {
        edges.push(edge)
        sources[edge] = [proof]
        true
      }
  }
}

///|
fn relation_point_read_source_v4(
  index : RelationPointIndexV4,
  read : RelationPointReadV4,
) -> Json {
  if read.observed == -1 {
    {
      "kind": "initial-absence",
      "basis": "complete declared initial relation snapshot and unique possible absence state",
      "identity": relation_point_key_json_v4(index, read.key),
      "writer": Json::null(),
      "version": Json::null(),
    }
  } else {
    {
      "kind": Json(
        if read.rows.is_empty() {
          "uniquely-resolved-tombstone-absence"
        } else {
          "returned-row-version"
        },
      ),
      "source": relation_point_source_json_v4(index, read.observed),
      "tombstoneIdentityInferred": Json(read.rows.is_empty()),
    }
  }
}

///|
fn relation_point_edges_v4(
  index : RelationPointIndexV4,
  budget : RelationPointBudgetV4,
  edges : Array[Edge],
  sources : Map[Edge, Array[Json]],
) -> Unit {
  for key, chain in index.chains {
    if index.blocked.contains(key) {
      continue
    }
    for position in 1..<chain.length() {
      let previous = index.parsed.sources[chain[position - 1]]
      let source = index.parsed.sources[chain[position]]
      let path : Array[Json] = []
      let mut current = chain[position]
      while current != chain[position - 1] {
        if !relation_point_charge_v4(budget) {
          return
        }
        path.push(relation_point_source_json_v4(index, current))
        let predecessor = index.parsed.sources[current].predecessor.unwrap()
        current = index.versions.at(predecessor)
      }
      path.push(relation_point_source_json_v4(index, current))
      if !relation_point_emit_v4(
          edges,
          sources,
          budget,
          relation_point_edge_v4(
            index,
            previous.writer.unwrap(),
            source.writer.unwrap(),
            WW,
            key,
            Some(previous.row.version),
            Some(source.row.version),
          ),
          {
            "basis": "original-row-predecessor-chain",
            "dependencyScope": "item",
            "identity": relation_point_key_json_v4(index, key),
            "fromEffect": relation_point_source_json_v4(
              index,
              chain[position - 1],
            ),
            "toEffect": relation_point_source_json_v4(index, chain[position]),
            "predecessorPath": Json(path),
          },
        ) {
        return
      }
    }
  }
  for read in index.reads {
    if !relation_point_charge_v4(budget) {
      return
    }
    if !read.usable || read.own >= 0 {
      continue
    }
    let observed = if read.observed >= 0 {
      Some(index.parsed.sources[read.observed].row.version)
    } else {
      None
    }
    if read.observed >= 0 {
      match index.parsed.sources[read.observed].writer {
        Some(writer) if writer != read.tx =>
          if !relation_point_emit_v4(
              edges,
              sources,
              budget,
              relation_point_edge_v4(
                index,
                writer,
                read.tx,
                WR,
                read.key,
                observed,
                if read.rows.is_empty() {
                  None
                } else {
                  observed
                },
              ),
              {
                "basis": "complete-primary-key-read-source",
                "dependencyScope": "item",
                "identity": relation_point_key_json_v4(index, read.key),
                "readSeq": Json(read.seq.to_double()),
                "queryIndex": Json(read.query_index),
                "queryObservation": index.originals.at(read.seq),
                "readSource": relation_point_read_source_v4(index, read),
              },
            ) {
            return
          }
        _ => ()
      }
    }
    if index.blocked.contains(read.key) {
      continue
    }
    let rank = if read.observed == -1 { 0 } else { index.ranks[read.observed] }
    if rank < 0 {
      continue
    }
    let chain = index.chains[read.key]
    if rank >= chain.length() {
      continue
    }
    if !relation_point_charge_v4(budget) {
      return
    }
    // rank zero is the initial row/absence state; chain[rank] is exactly
    // its next installed version. An own successor stops this read's RW
    // relation rather than permitting a shortcut past it to another writer.
    let later = chain[rank]
    let source = index.parsed.sources[later]
    if source.writer == Some(read.tx) {
      continue
    }
    if !relation_point_emit_v4(
        edges,
        sources,
        budget,
        relation_point_edge_v4(
          index,
          read.tx,
          source.writer.unwrap(),
          RW,
          read.key,
          observed,
          Some(source.row.version),
        ),
        {
          "basis": "complete-primary-key-read-before-next-installed-row-version",
          "dependencyScope": "item",
          "directSuccessor": true,
          "sourceRank": Json(rank),
          "targetRank": Json(rank + 1),
          "identity": relation_point_key_json_v4(index, read.key),
          "readSeq": Json(read.seq.to_double()),
          "queryIndex": Json(read.query_index),
          "queryObservation": index.originals.at(read.seq),
          "readSource": relation_point_read_source_v4(index, read),
          "laterEffect": relation_point_source_json_v4(index, later),
        },
      ) {
      return
    }
  }
}

///|
fn relation_graph_point_v4(
  parsed : RelationV3Parsed,
  max_checks~ : Int32 = 1000000,
  window_unproven~ : Bool = false,
) -> RelationPointGraphV4 {
  let budget : RelationPointBudgetV4 = {
    maximum: max_checks,
    checks: 0,
    limited: false,
    reason: "complete",
  }
  let index = relation_point_empty_index_v4(parsed)
  let sequence_loss = relation_point_sequence_loss_v5(parsed)
  index.window_unproven = window_unproven || sequence_loss
  let capacity = parsed.programs.length() <= 128 && parsed.operations <= 4096
  let valid = max_checks >= 0 && max_checks <= 1000000
  let edges : Array[Edge] = []
  let sources : Map[Edge, Array[Json]] = Map([])
  if valid && capacity && index.window_unproven {
    // Incomplete windows cannot establish absence of rollback or final effects.
    // Build only independent must-direct proofs; no completed journal/graph.
    relation_point_window_direct_v5(index, budget, !window_unproven)
    relation_point_gap_v4(
      index, "relation-original-event-window-incomplete", -1, 0L,
    )
  } else if valid && capacity {
    relation_point_journal_v4(index, budget)
    if index.journal_complete && !budget.limited {
      relation_point_orders_v4(index, budget)
    }
    if index.journal_complete && !budget.limited {
      relation_point_reads_v4(index, budget)
    }
    if index.reads_complete && !budget.limited {
      relation_point_edges_v4(index, budget, edges, sources)
    }
  }
  let complete = valid &&
    capacity &&
    !budget.limited &&
    index.journal_complete &&
    index.reads_complete &&
    index.orders_complete &&
    index.gaps.is_empty()
  let reason = if !valid {
    "invalid-relation-point-budget"
  } else if !capacity {
    "relation-point-capacity-128-4096"
  } else if budget.limited {
    budget.reason
  } else if complete {
    "complete"
  } else {
    "relation-point-source-order-or-read-incomplete"
  }
  {
    base: {
      normalized: parsed.normalized,
      transactions: parsed.programs.map(program => {
        id: program.id,
        status: program.status,
        ops: [],
        start: None,
        end: None,
      }),
      edges,
      sources,
      validity_gaps: index.gaps,
      history: None,
      list_parsed: None,
      complete,
      reason,
    },
    index,
    checks: budget.checks,
    maximum: max_checks,
    limited: budget.limited,
  }
}

///|
pub fn build_relation_point_graph_v4(
  history : HistoryV4,
  max_checks~ : Int32 = 1000000,
) -> Result[RelationPointGraphV4, String] {
  if max_checks < 0 || max_checks > 1000000 {
    return Err("Relation point graph budget must be within 0..1000000")
  }
  match history.payload {
    RelationSnapshot(parsed) =>
      Ok(
        relation_graph_point_v4(
          parsed,
          max_checks~,
          window_unproven=relation_point_window_unproven_v4(history),
        ),
      )
    _ => Err("Relation point graph requires a relation-set-v1 capture")
  }
}

///|
pub fn relation_point_graph_v4_json(result : RelationPointGraphV4) -> Json {
  let index = result.index
  let direct : Map[String, Json] = Map([])
  for category in ["G1a", "G1b", "INT"] {
    let proofs = index.direct.get_or_default(category, [])
    direct[category] = {
      "status": Json(
        if !proofs.is_empty() {
          "refuted"
        } else if result.base.complete {
          "checked-compatible"
        } else {
          "unknown"
        },
      ),
      "evidence": Json(proofs),
    }
  }
  let record : Json = {
    "format": "moontxnwitness-relation-point-graph/v4",
    "schemaVersion": 4,
    "semanticContract": "moontxnwitness-relation-point-source-graph-v4-5",
    "dataModel": "relation-set-v1",
    "acceptsIsolationModels": false,
    "scope": "single-primary-key equality row effects and item dependencies only; no predicate classification or database authentication",
    "algorithm": "relation-point-row-graph-5",
    "indexAlgorithm": "relation-point-local-effect-journal-4",
    "internalConsistencyRule": "delivered-point-read-versus-known-nearest-read-or-own-write; write-source-mismatch-is-not-a-read/v1",
    "itemAntiDependencyRule": "external-read-to-next-installed-row-version; never skip own successor/v1",
    "complete": Json(result.base.complete),
    "reason": Json(result.base.reason),
    "journalComplete": Json(index.journal_complete),
    "inputWindowUnproven": Json(index.window_unproven),
    "readsComplete": Json(index.reads_complete),
    "ordersComplete": Json(index.orders_complete),
    "observations": object_fields_unchecked_v3(index.parsed.normalized).at(
      "observations",
    ),
    "writeEffects": object_fields_unchecked_v3(index.parsed.normalized).at(
      "effects",
    ),
    "identities": Json(
      index.keys.mapi((key, _) => relation_point_key_json_v4(index, key)),
    ),
    "sourceAudit": Json(
      index.parsed.sources.mapi((source, _) => {
        relation_point_source_json_v4(index, source)
      }),
    ),
    "rowVersionOrders": Json(
      index.chains.mapi((key, chain) => {
        (
          {
            "identity": relation_point_key_json_v4(index, key),
            "complete": Json(index.ordered.contains(key)),
            "initial": relation_point_source_json_v4(
              index,
              relation_point_initial_v4(index, key),
            ),
            "finalCommittedEffects": Json(
              chain.map(source => relation_point_source_json_v4(index, source)),
            ),
          } : Json)
      }),
    ),
    "readStates": Json(
      index.reads.map(read => {
        (
          {
            "transaction": Json(read.tx),
            "relation": Json(index.parsed.tables[read.table].name),
            "identity": relation_point_key_json_v4(index, read.key),
            "readSeq": Json(read.seq.to_double()),
            "queryIndex": Json(read.query_index),
            "ownOverlayProven": Json(
              relation_point_program_known_v4(index, read.tx, read.seq),
            ),
            "ownAtDelivery": if relation_point_program_known_v4(
                index,
                read.tx,
                read.seq,
              ) {
              relation_point_source_json_v4(index, read.own)
            } else {
              Json::null()
            },
            "resolvedSource": if read.usable {
              relation_point_read_source_v4(index, read)
            } else {
              Json::null()
            },
            "usable": Json(read.usable),
            "reason": Json(read.reason),
          } : Json)
      }),
    ),
    "directChecks": Json::object(direct),
    "diagnostics": Json(index.diagnostics),
    "gaps": Json(index.gaps),
    "edges": Json(result.base.edges.map(edge_json)),
    "edgeSources": Json(
      result.base.edges.map(edge => {
        (
          {
            "edge": edge_json(edge),
            "sources": Json(result.base.sources.at(edge)),
          } : Json)
      }),
    ),
    "execution": {
      "constructionChecks": Json(result.checks),
      "limited": Json(result.limited),
      "counterContract": "relation-point-construction-checks-5",
      "limits": {
        "transactions": 128,
        "operations": 4096,
        "edges": 50000,
        "constructionChecks": Json(result.maximum),
      },
    },
  }
  v4_json_copy(record)
}
