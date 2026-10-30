///|
priv struct LostUpdateCandidateV4 {
  tx : String
  key : String
  read : AnomalyV4Operation
  source : AnomalyV4Source
  final_write : AnomalyV4Source
}

///|
fn lost_update_v4_sequence(value : Json) -> Int64 {
  match value {
    Number(n, ..) => n.to_int64()
    _ => abort("Validated source sequence")
  }
}

///|
fn lost_update_v4_revoke_before(
  source : AnomalyV4Source,
  at : Int64?,
  revoked : Map[Int64, Int64],
) -> Bool {
  match (source.seq, at) {
    (Some(seq), Some(time)) =>
      match revoked.get(seq) {
        Some(undo) => undo <= time
        None => false
      }
    _ => false
  }
}

///|
fn lost_update_v4_trim(
  stack : Array[AnomalyV4Source],
  at : Int64?,
  revoked : Map[Int64, Int64],
  work : AnomalyV4Work,
) -> Unit {
  while !stack.is_empty() &&
        lost_update_v4_revoke_before(stack[stack.length() - 1], at, revoked) {
    if !anomaly_v4_charge(work) {
      return
    }
    let _ = stack.pop()
  }
}

///|
fn lost_update_v4_is_final(
  source : AnomalyV4Source,
  finals : Map[String, Map[String, AnomalyV4Source]],
) -> Bool {
  match source.tx {
    None => true
    Some(tx) =>
      match finals.get_or_default(tx, Map([])).get(source.key) {
        Some(last) =>
          last.item.id == source.item.id && last.position == source.position
        None => false
      }
  }
}

///|
fn lost_update_v4_candidate_json(candidate : LostUpdateCandidateV4) -> Json {
  {
    "transaction": Json(candidate.tx),
    "key": Json(candidate.key),
    "firstExternalRead": anomaly_v4_operation_json(candidate.read),
    "readSource": anomaly_v4_source_json(candidate.source),
    "finalEffectiveWrite": anomaly_v4_source_json(candidate.final_write),
    "readBeforeFinalWrite": Json(
      candidate.read.position < candidate.final_write.position,
    ),
  }
}

///|
/// Unique version identities, actual read operations and effective final writes
/// establish Elle's direct lost-update pattern without guessing a WW order.
fn lost_update_v4_check(
  history : HistoryV4,
  normalized : Json?,
  sources : Map[String, Map[String, AnomalyV4Source]],
  outcomes : Map[String, TxStatus],
  operations : Array[AnomalyV4Operation],
  work : AnomalyV4Work,
) -> Unit {
  let revoked : Map[Int64, Int64] = Map([])
  let confirmed_finals : Map[String, Map[Int64, Bool]] = Map([])
  let mut capture = false
  match normalized {
    Some(value) => {
      capture = true
      let n = object_fields_unchecked_v3(value)
      let root = object_fields_unchecked_v3(history.source_document)
      let original_gaps = anomaly_v4_array(
        root.get_or_default("gaps", Json::null()),
      )
      let coverage = object_fields_unchecked_v3(n.at("coverage"))
      let allowed = [
        "version_order_gap", "unknown_commit", "outstanding_transaction", "unsafe_read_source",
        "missing_version_source", "own_read_mismatch", "own_write_predecessor_mismatch",
        "unsafe_write_source",
      ]
      let unresolved : Array[String] = []
      for gap in anomaly_v4_array(coverage.at("gaps")) {
        if !anomaly_v4_charge(work) {
          return
        }
        let code = object_fields_unchecked_v3(gap).get_or_default(
          "code",
          Json::null(),
        )
        match code {
          String(name) =>
            if !allowed.contains(name) && unresolved.length() < 256 {
              unresolved.push(name)
            }
          _ =>
            if unresolved.length() < 256 {
              unresolved.push("invalid-gap-code")
            }
        }
      }
      if !original_gaps.is_empty() || !unresolved.is_empty() {
        anomaly_v4_emit(work, "lost-update-source-window-unproven", "gap", {
          "reason": "Missing capture records, unproven writer scope, snapshot or statement coverage prevent a complete unique-writer source proof",
          "originalGapCount": Json(original_gaps.length()),
          "normalizationGapCodes": Json(unresolved),
        })
        return
      }
      for raw in anomaly_v4_array(n.at("effects")) {
        if !anomaly_v4_charge(work) {
          return
        }
        let effect = object_fields_unchecked_v3(raw)
        match effect.get("revertedBy") {
          Some(Number(undo, ..)) =>
            revoked[lost_update_v4_sequence(effect.at("seq"))] = undo.to_int64()
          _ => ()
        }
      }
      for raw in anomaly_v4_array(n.at("transactions")) {
        if !anomaly_v4_charge(work) {
          return
        }
        let tx = object_fields_unchecked_v3(raw)
        let items : Map[Int64, Bool] = Map([])
        for seq in anomaly_v4_array(tx.at("finalWrites")) {
          if !anomaly_v4_charge(work) {
            return
          }
          items[lost_update_v4_sequence(seq)] = true
        }
        confirmed_finals[anomaly_v4_string(tx.at("id"))] = items
      }
    }
    None => ()
  }
  let finals : Map[String, Map[String, AnomalyV4Source]] = Map([])
  for op in operations {
    if !anomaly_v4_charge(work) {
      return
    }
    if !op.write || outcomes.get(op.tx) != Some(Committed) {
      continue
    }
    let source = sources.at(op.key).at(op.items[0].id)
    let undone = match source.seq {
      Some(seq) => revoked.contains(seq)
      None => source.reverted
    }
    if undone {
      continue
    }
    let last = finals.get_or_default(op.tx, Map([]))
    last[op.key] = source
    finals[op.tx] = last
  }
  let first_reads : Map[String, Map[String, AnomalyV4Operation]] = Map([])
  let own : Map[String, Map[String, Array[AnomalyV4Source]]] = Map([])
  let final_bases : Map[String, Map[String, AnomalyV4Source?]] = Map([])
  for op in operations {
    if !anomaly_v4_charge(work) {
      return
    }
    if outcomes.get(op.tx) != Some(Committed) {
      continue
    }
    let keys = own.get_or_default(op.tx, Map([]))
    let stack = keys.get_or_default(op.key, [])
    lost_update_v4_trim(stack, op.seq, revoked, work)
    if work.limited {
      return
    }
    if op.write {
      let source = sources.at(op.key).at(op.items[0].id)
      if lost_update_v4_is_final(source, finals) {
        let bases = final_bases.get_or_default(op.tx, Map([]))
        bases[op.key] = if stack.is_empty() {
          None
        } else {
          Some(stack[stack.length() - 1])
        }
        final_bases[op.tx] = bases
      }
      stack.push(source)
    } else if stack.is_empty() {
      let reads = first_reads.get_or_default(op.tx, Map([]))
      if !reads.contains(op.key) {
        reads[op.key] = op
      }
      first_reads[op.tx] = reads
    }
    keys[op.key] = stack
    own[op.tx] = keys
  }
  let groups : Map[String, Map[String, LostUpdateCandidateV4]] = Map([])
  // Iterate original programs, rather than hash-map order, for stable witnesses.
  let handled : Map[String, Map[String, Bool]] = Map([])
  for op in operations {
    if !anomaly_v4_charge(work) {
      return
    }
    if op.write || outcomes.get(op.tx) != Some(Committed) {
      continue
    }
    let once = handled.get_or_default(op.tx, Map([]))
    if once.contains(op.key) {
      continue
    }
    let read = match first_reads.get_or_default(op.tx, Map([])).get(op.key) {
      Some(read) => read
      None => continue
    }
    once[op.key] = true
    handled[op.tx] = once
    let final_write = match finals.get_or_default(op.tx, Map([])).get(op.key) {
      Some(write) if write.position > read.position => write
      _ => continue
    }
    let identity = read.items[0].id
    let source = match sources.get_or_default(op.key, Map([])).get(identity) {
      Some(source) if source.outcome == Committed &&
        !source.reverted &&
        source.tx != Some(op.tx) &&
        lost_update_v4_is_final(source, finals) => source
      _ => {
        anomaly_v4_emit(work, "lost-update-read-source-unconfirmed", "gap", {
          "read": anomaly_v4_operation_json(read),
          "key": Json(op.key),
          "identity": Json(identity),
          "reason": "First external read requires an initial identity or a confirmed external final effective version; missing, own, unknown, aborted or intermediate sources do not establish this pattern",
        })
        continue
      }
    }
    if source.tx != None &&
      source.seq is Some(write_seq) &&
      read.seq is Some(read_seq) &&
      write_seq >= read_seq {
      anomaly_v4_emit(work, "lost-update-read-source-unconfirmed", "gap", {
        "read": anomaly_v4_operation_json(read),
        "source": anomaly_v4_source_json(source),
        "reason": "The external source operation was not observed before the read; collection seq is not proof of a future-read anomaly",
      })
      continue
    }
    if capture {
      let final_confirmed = match final_write.seq {
        Some(seq) =>
          confirmed_finals.get_or_default(op.tx, Map([])).contains(seq)
        None => false
      }
      if !final_confirmed {
        anomaly_v4_emit(work, "lost-update-final-write-unconfirmed", "gap", {
          "write": anomaly_v4_source_json(final_write),
        })
        continue
      }
      let write = object_fields_unchecked_v3(final_write.original)
      let base = match write.get("predecessor") {
        Some(String(version)) =>
          sources.get_or_default(op.key, Map([])).get(version)
        _ => None
      }
      let own_base = final_bases
        .get_or_default(op.tx, Map([]))
        .get_or_default(op.key, None)
      let valid_base = match base {
        Some(base) if base.tx == Some(op.tx) =>
          own_base is Some(current) && current.item.id == base.item.id
        Some(base) =>
          own_base is None &&
          base.outcome == Committed &&
          !base.reverted &&
          lost_update_v4_is_final(base, finals)
        None => false
      }
      if !valid_base {
        anomaly_v4_emit(work, "lost-update-write-source-unconfirmed", "gap", {
          "write": anomaly_v4_source_json(final_write),
          "reason": "The actual final write requires its captured initial/external final source or current own overlay; no read operation is synthesized from a predecessor",
        })
        continue
      }
    }
    let candidate : LostUpdateCandidateV4 = {
      tx: op.tx,
      key: op.key,
      read,
      source,
      final_write,
    }
    let by_source = groups.get_or_default(op.key, Map([]))
    match by_source.get(identity) {
      Some(previous) if previous.tx != candidate.tx &&
        previous.final_write.item.id != final_write.item.id =>
        anomaly_v4_emit(work, "lost-update", "proved", {
          "definition": "elle-4e359e597c52938b0afebb8bc42273914d68a424/txn.clj:191-282/unique-register-version",
          "key": Json(op.key),
          "readVersionIdentity": Json(identity),
          "readSource": anomaly_v4_source_json(source),
          "transactions": Json([
            lost_update_v4_candidate_json(previous),
            lost_update_v4_candidate_json(candidate),
          ]),
          "versionOrderRequired": false,
          "scope": "Two distinct committed transactions actually read the same proven external version identity before distinct final effective writes of the same key; business-value equality and list prefixes are not used",
        })
      None => by_source[identity] = candidate
      _ => ()
    }
    groups[op.key] = by_source
  }
}

///|
/// Explicit profile: source inspection plus proven register lost-update pairs.
pub fn inspect_lost_updates_v4(
  history : HistoryV4,
  max_checks~ : Int32 = 1000000,
) -> Json {
  anomaly_v4_inspect(history, max_checks, lost_updates=true)
}

///|
pub fn verify_lost_updates_v4(
  history : HistoryV4,
  supplied : Json,
  max_checks~ : Int32 = 1000000,
) -> Bool {
  supplied == anomaly_v4_inspect(history, max_checks, lost_updates=true)
}
