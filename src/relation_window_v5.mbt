///|
fn relation_point_sequence_loss_v5(parsed : RelationV3Parsed) -> Bool {
  match relation_classification_at_v4(parsed.normalized, ["coverage", "gaps"]) {
    Array(gaps) =>
      gaps.any(g => {
        relation_classification_at_v4(g, ["code"]) == Json("sequence_gap")
      })
    _ => true
  }
}

///|
/// A hole may contain an operation on any transaction active across it. An
/// observed begin after that hole starts an independently known local program.
fn relation_point_missing_boundaries_v5(
  index : RelationPointIndexV4,
  budget : RelationPointBudgetV4,
) -> Array[Int64] {
  let missing : Array[Int64] = []
  let mut expected = 1L
  match
    relation_classification_at_v4(index.parsed.normalized, ["observations"]) {
    Array(events) =>
      for raw in events {
        if !relation_point_charge_v4(budget) {
          return missing
        }
        match relation_classification_at_v4(raw, ["seq"]) {
          Number(n, ..) => {
            let seq = n.to_int64()
            if seq != expected {
              missing.push(expected)
            }
            expected = seq + 1L
          }
          _ => ()
        }
      }
    _ => ()
  }
  missing
}

///|
/// Known aborted outcomes and actual reads are original observations. Their
/// G1a proof does not assert survival, finality, or an inferred missing rollback.
/// INT uses only an actually gap-free local prefix, never an invented journal.
fn relation_point_window_direct_v5(
  index : RelationPointIndexV4,
  budget : RelationPointBudgetV4,
  allow_prefix : Bool,
) -> Unit {
  let missing = relation_point_missing_boundaries_v5(index, budget)
  if budget.limited {
    return
  }
  let begins : Map[String, Int64] = Map([])
  for
    raw in capture_source_array_v4(
      relation_classification_at_v4(index.parsed.normalized, ["transactions"]),
    ) {
    if !relation_point_charge_v4(budget) {
      return
    }
    let f = object_fields_unchecked_v3(raw)
    begins[capture_source_string_v4(f.at("id"))] = capture_source_seq_v4(
      f.at("beginSeq"),
    )
  }
  for program in index.parsed.programs {
    let start = begins.get_or_default(program.id, 0L)
    let mut cutoff : Int64? = index.uncertain_after.get(program.id)
    for hole in missing {
      if !relation_point_charge_v4(budget) {
        return
      }
      if hole > start && (cutoff is None || hole < cutoff.unwrap()) {
        cutoff = Some(hole)
      }
    }
    let own : Map[Int32, Int32] = Map([])
    let base : Map[Int32, Int32] = Map([])
    let trail : Array[(Int32, Int32)] = []
    let scopes : Array[(String, Int32)] = []
    let mut prefix_known = allow_prefix
    let mut query_index = 0
    for action in program.actions {
      if !relation_point_charge_v4(budget) {
        return
      }
      let seq = match action {
        WriteRow(i) => index.parsed.sources[i].seq
        QueryRows(_, _, _, seq) => seq
        Mark(_) | Undo(_) | Release(_) => 0L
      }
      if cutoff is Some(hole) && seq > 0L && seq >= hole {
        prefix_known = false
      }
      match action {
        WriteRow(i) if prefix_known => {
          let source = index.parsed.sources[i]
          let previous = own.get_or_default(source.row.key, -2)
          let predecessor = match source.predecessor {
            Some(v) => index.versions.get_or_default(v, -1)
            None => -1
          }
          let valid_source = if previous >= 0 {
            source.predecessor ==
            Some(index.parsed.sources[previous].row.version) &&
            (source.action == "insert") ==
            (index.parsed.sources[previous].action == "delete")
          } else if predecessor >= 0 {
            let prior = index.parsed.sources[predecessor]
            prior.writer is None &&
            prior.row.key == source.row.key &&
            prior.seq < source.seq &&
            (source.action == "insert") == (prior.action == "delete")
          } else {
            source.predecessor is None &&
            source.action == "insert" &&
            relation_point_initial_v4(index, source.row.key) < 0
          }
          if !valid_source {
            prefix_known = false
            relation_point_gap_v4(
              index,
              "relation-window-prefix-write-source-unproven",
              source.row.key,
              source.seq,
            )
            continue
          }
          trail.push((source.row.key, previous))
          own[source.row.key] = i
        }
        Mark(instance) if prefix_known =>
          scopes.push((instance, trail.length()))
        Undo(instance) | Release(instance) if prefix_known => {
          let mut found = -1
          for i, scope in scopes {
            if scope.0 == instance {
              found = i
            }
          }
          if found < 0 {
            prefix_known = false
            continue
          }
          match action {
            Undo(_) =>
              while trail.length() > scopes[found].1 {
                let (key, previous) = trail.pop().unwrap()
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
        QueryRows(table, predicate, rows, read_seq) => {
          let position = query_index
          query_index += 1
          if program.status != Committed ||
            predicate.length() != 1 ||
            predicate[0].column != -1 ||
            predicate[0].op != "eq" {
            continue
          }
          let key = relation_point_find_key_v4(index, table, predicate[0].value)
          if key < 0 ||
            relation_classification_at_v4(
              index.originals.get_or_default(read_seq, Json::null()),
              ["complete"],
            ) !=
            Json(true) {
            continue
          }
          let current_own = if prefix_known {
            own.get_or_default(key, -2)
          } else {
            -2
          }
          let mut observed = -3
          if rows.length() == 1 {
            match index.versions.get(rows[0].version) {
              Some(i) if index.parsed.sources[i].row.key == key &&
                index.parsed.sources[i].action != "delete" &&
                index.parsed.sources[i].row.values == rows[0].values =>
                observed = i
              _ => ()
            }
          } else if rows.is_empty() &&
            current_own >= 0 &&
            index.parsed.sources[current_own].action == "delete" {
            observed = current_own
          }
          let read : RelationPointReadV4 = {
            tx: program.id,
            table,
            key,
            seq: read_seq,
            query_index: position,
            rows,
            own: current_own,
            delivered_complete: true,
            observed,
            usable: false,
            reason: "partial-window-must-direct-only",
          }
          index.reads.push(read)
          if observed < 0 {
            let _ = base.remove(key)
            continue
          }
          let source = index.parsed.sources[observed]
          match source.writer {
            Some(writer) if writer != program.id &&
              index.outcomes.get(writer) == Some(Aborted) =>
              relation_point_direct_v4(
                index, "G1a", "external-confirmed-abort-independent-of-missing-journal",
                read, observed,
              )
            _ => ()
          }
          if !prefix_known {
            continue
          }
          let expected = if current_own >= 0 {
            current_own
          } else {
            base.get_or_default(key, -3)
          }
          if expected >= 0 && expected != observed {
            relation_point_direct_v4(
              index,
              "INT",
              "actual-gap-free-prefix-read-differs-from-nearest-read-or-own-write",
              read,
              observed,
              expected~,
            )
          }
          // A future or already revoked own identity cannot establish a new
          // external baseline. Earlier fully proved direct evidence survives.
          if source.writer == Some(program.id) && current_own != observed {
            let _ = base.remove(key)
          } else if current_own < 0 {
            base[key] = observed
          }
        }
        _ => ()
      }
    }
  }
}
