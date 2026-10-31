///|
/// Internal, reconstructed from original observations. It is never a caller proof.
priv struct ModelPointProgramV4 {
  initial : Map[String, String]
  transactions : Array[ModelRegisterTxV4]
  version_orders : Map[String, Array[String]]
  mapping : Json
}

///|
fn model_mapping_counter_v4(
  budget : ModelSourceBudgetV4,
  counter : String,
) -> Json {
  let fields = object_fields_unchecked_v3(model_source_execution_v4(budget))
  fields["counterContract"] = Json(counter)
  Json(fields)
}

///|
fn model_op_seq_v4(op : ModelRegisterOpV4) -> Int64 {
  capture_source_seq_v4(
    object_fields_unchecked_v3(op.original).get_or_default("seq", Json::null()),
  )
}

///|
fn model_pop_revoked_v4(
  txs : Array[ModelRegisterTxV4],
  ti : Int32,
  stack : Array[Int32],
  at : Int64,
  budget : ModelSourceBudgetV4,
) -> Unit {
  while !stack.is_empty() {
    let op = txs[ti].ops[stack[stack.length() - 1]]
    match op.revocation_seq {
      Some(end) if end <= at => {
        if !model_source_charge_v4(budget) {
          break
        }
        ignore(stack.pop())
      }
      _ => break
    }
  }
}

///|
/// A write predecessor is a version-lineage observation, never a fabricated read.
fn model_raw_write_lineage_v4(
  initial : Map[String, String],
  txs : Array[ModelRegisterTxV4],
  sources : Map[String, Map[String, ModelRegisterWriteV4]],
  window : CaptureWindowV5?,
  budget : ModelSourceBudgetV4,
) -> ModelRuleV4 {
  let records : Array[Json] = []
  let diagnostics : Array[Json] = []
  let mut valid = window is Some(w) && w.complete
  for ti, tx in txs {
    let stacks : Map[String, Array[Int32]] = Map([])
    for oi, op in tx.ops {
      if !model_source_charge_v4(budget) {
        valid = false
        break
      }
      if op.kind != Write {
        continue
      }
      let stack = stacks.get_or_default(op.key, [])
      model_pop_revoked_v4(txs, ti, stack, model_op_seq_v4(op), budget)
      let known = capture_prefix_known_v5(
        window,
        tx.boundary.id,
        model_op_seq_v4(op),
      )
      let mut source_ok = false
      let mut basis = "unproven"
      match op.predecessor {
        Some(v) =>
          if !stack.is_empty() {
            source_ok = tx.ops[stack[stack.length() - 1]].version == v
            basis = "active-own-predecessor"
          } else if initial.get(op.key) == Some(v) {
            source_ok = true
            basis = "initial-version"
          } else {
            match sources.get_or_default(op.key, Map([])).get(v) {
              Some(w) if w.tx != ti &&
                w.is_final &&
                txs[w.tx].boundary.status == Committed => {
                source_ok = true
                basis = "unique-external-installed-final"
              }
              _ => ()
            }
          }
        None => ()
      }
      let closed = match window {
        Some(w) => w.closed.get_or_default(tx.boundary.id, false)
        _ => false
      }
      if !known || !closed || !source_ok || budget.limited {
        valid = false
        diagnostics.push({
          "transaction": Json(tx.boundary.id),
          "actualWrite": op.original,
          "knownPrefix": Json(known),
          "closedProducerWindow": Json(closed),
          "lineageSourceProved": Json(source_ok),
        })
      }
      records.push({
        "transaction": Json(tx.boundary.id),
        "actualWrite": op.original,
        "lineageRole": "write-predecessor-only",
        "syntheticReadCreated": false,
        "basis": Json(basis),
        "effectiveAtCommit": Json(
          !op.revoked &&
          sources.get_or_default(op.key, Map([])).get(op.version) is Some(w) &&
          w.is_final,
        ),
      })
      stack.push(oi)
      stacks[op.key] = stack
    }
  }
  model_rule_v4(
    "write-input-applicability",
    if valid && !budget.limited {
      "checked-compatible"
    } else {
      "unknown"
    },
    "captured version assignments retain every original write and independently proved predecessor lineage; no SQL expression input or SELECT is synthesized",
    evidence={
      "definition": "captured-register-write-lineage-and-overlay/v1",
      "records": Json(records),
      "diagnostics": Json(diagnostics),
      "execution": model_mapping_counter_v4(
        budget, "model-captured-register-window-and-source-checks-2",
      ),
    },
  )
}

///|
fn model_point_mapping_v4(
  initial : Map[String, String],
  txs : Array[ModelRegisterTxV4],
  orders : Map[String, Array[String]],
  original : Json,
) -> Json {
  {
    "definition": "captured-register-program-projection/v1",
    "readWriteOperationsRetained": true,
    "inferredOperationsCreated": false,
    "programEvents": object_fields_unchecked_v3(original).at("events"),
    "initialVersions": Json(initial),
    "installedFinalVersionOrders": Json(orders),
    "transactions": Json(
      txs.map(tx => {
        (
          {
            "transaction": Json(tx.boundary.id),
            "outcome": Json(status_label(tx.boundary.status)),
            "operations": Json(
              tx.ops.map(op => {
                (
                  {
                    "kind": Json(op_label(op.kind)),
                    "key": Json(op.key),
                    "version": Json(op.version),
                    "original": op.original,
                    "revokedAt": match op.revocation_seq {
                      Some(seq) => Json(seq.to_double())
                      None => Json::null()
                    },
                  } : Json)
              }),
            ),
          } : Json)
      }),
    ),
  }
}

///|
/// The CV rank argument replays the original active overlay, including rollback.
fn model_cv_mapped_rank_v4(
  source : ModelSourceV4,
  options : ModelOptionsV4,
  i_rule : ModelRuleV4,
  single_rule : ModelRuleV4,
) -> ModelRuleV4 {
  let id = "completion/CV-per-key-ranks"
  if !model_observation_premises_v4(source, false) ||
    i_rule.status != "checked-compatible" ||
    single_rule.status != "checked-compatible" {
    return model_rule_v4(
      id, "pending", "requires a verified point-program mapping, complete I/G-single absence and legal active own overlays",
    )
  }
  let program = source.point_program.unwrap()
  let budget : ModelSourceBudgetV4 = {
    maximum: options.max_source_checks,
    checks: 0,
    limited: false,
  }
  let ranks : Map[String, Map[String, Int32]] = Map([])
  let finals : Map[String, Map[String, String]] = Map([])
  let own_components : Map[Int64, Json] = Map([])
  let mut valid = true
  if source.profile == "captured-list-prefix-state/v2" {
    for
      raw in capture_source_array_v4(
        object_fields_unchecked_v3(program.mapping).at("externalBaseComponents"),
      ) {
      if !model_source_charge_v4(budget) {
        valid = false
        break
      }
      let component = object_fields_unchecked_v3(raw)
      if !capture_source_array_v4(component.at("ownItemIds")).is_empty() {
        own_components[capture_source_seq_v4(component.at("readSeq"))] = raw
      }
    }
  }
  for key, order in program.version_orders {
    if order.is_empty() || program.initial.get(key) != Some(order[0]) {
      valid = false
    }
    let r : Map[String, Int32] = Map([])
    for i, v in order {
      if !model_source_charge_v4(budget) {
        valid = false
        break
      }
      r[v] = i
    }
    ranks[key] = r
  }
  for tx in program.transactions {
    let last : Map[String, String] = Map([])
    if tx.boundary.status == Committed {
      for op in tx.ops {
        if !model_source_charge_v4(budget) {
          valid = false
          break
        }
        if op.kind == Write && !op.revoked {
          last[op.key] = op.version
        }
      }
    }
    finals[tx.boundary.id] = last
  }
  let records : Array[Json] = []
  for ti, tx in program.transactions {
    if tx.boundary.status != Committed {
      continue
    }
    let own : Map[String, Array[Int32]] = Map([])
    let previous : Map[String, Int32] = Map([])
    for oi, op in tx.ops {
      if !model_source_charge_v4(budget) {
        valid = false
        break
      }
      let stack = own.get_or_default(op.key, [])
      model_pop_revoked_v4(
        program.transactions,
        ti,
        stack,
        model_op_seq_v4(op),
        budget,
      )
      if op.kind == Write {
        stack.push(oi)
        own[op.key] = stack
        continue
      }
      own[op.key] = stack
      let mut read_version = op.version
      let mut component : Json? = None
      if !stack.is_empty() {
        if tx.ops[stack[stack.length() - 1]].version != op.version {
          valid = false
        }
        if source.profile != "captured-list-prefix-state/v2" {
          continue
        }
        match own_components.get(model_op_seq_v4(op)) {
          Some(raw) => {
            component = Some(raw)
            read_version = capture_source_string_v4(
              object_fields_unchecked_v3(raw).at("derivedBaseVersion"),
            )
          }
          None => {
            valid = false
            continue
          }
        }
      }
      let rank = ranks
        .get_or_default(op.key, Map([]))
        .get_or_default(read_version, -1)
      let write_rank = match
        finals.get_or_default(tx.boundary.id, Map([])).get(op.key) {
        Some(v) => ranks.get_or_default(op.key, Map([])).get_or_default(v, -1)
        None => -1
      }
      if rank < 0 {
        valid = false
      }
      if write_rank >= 0 {
        if rank != write_rank - 1 {
          valid = false
        }
      } else {
        match previous.get(op.key) {
          Some(v) if v != rank => valid = false
          _ => ()
        }
        previous[op.key] = rank
      }
      let row : Json = {
        "transaction": Json(tx.boundary.id),
        "key": Json(op.key),
        "operationIndex": Json(oi),
        "originalRead": op.original,
        "readVersion": Json(read_version),
        "readRank": Json(rank),
        "finalWriteRank": Json(write_rank),
      }
      match component {
        Some(raw) => {
          let fields = object_fields_unchecked_v3(row)
          fields["readComponent"] = Json(
            "external-prefix-before-active-own-suffix",
          )
          fields["actualWholeDerivedState"] = Json(op.version)
          fields["componentInference"] = raw
        }
        None => ()
      }
      records.push(row)
    }
  }
  model_rule_v4(
    id,
    if valid && !budget.limited {
      "checked-compatible"
    } else {
      "unknown"
    },
    "mapped original point reads satisfy per-key ranks after actual savepoint effects; no external read or revoked own read is discarded",
    covered_by=[
      i_rule.id,
      single_rule.id,
      "program-source-applicability",
      "write-input-applicability",
    ],
    evidence={
      "definition": if source.profile == "captured-list-prefix-state/v2" {
        Json("append-list-prefix-state-CV-rank-certificate/v2")
      } else {
        Json("captured-point-register-CV-rank-certificate/v1")
      },
      "sourceProjection": program.mapping,
      "readRanks": Json(records),
      "allRanksValid": Json(valid && !budget.limited),
      "fullRepeatableReadINTRequired": false,
      "execution": model_mapping_counter_v4(
        budget,
        if source.profile == "captured-list-prefix-state/v2" {
          "mapped-list-prefix-rank-reference-checks-2"
        } else {
          "mapped-point-rank-reference-checks-1"
        },
      ),
    },
  )
}
