///|
fn model_projected_emit_v4(
  edges : Array[ScopedDataEdgeInputV4],
  program : ModelPointProgramV4,
  from : String,
  to : String,
  kind : ScopedDataKindV4,
  key : String,
  basis : Array[Json],
  budget : ModelSourceBudgetV4,
) -> Bool {
  if from == to {
    return true
  }
  if !model_source_charge_v4(budget) || edges.length() >= 50000 {
    return false
  }
  let sources = basis.copy()
  let proofs = capture_source_array_v4(
    object_fields_unchecked_v3(program.mapping).get_or_default(
      "writerBlockProofs",
      Json::null(),
    ),
  )
  for proof in proofs {
    if !model_source_charge_v4(budget) {
      return false
    }
    let fields = object_fields_unchecked_v3(proof)
    if fields.get("key") == Some(Json(key)) &&
      (
        fields.get("writer") == Some(Json(from)) ||
        fields.get("writer") == Some(Json(to))
      ) {
      sources.push(proof)
    }
  }
  sources.push({
    "basis": "derived-point-state-projection",
    "definition": object_fields_unchecked_v3(program.mapping).at("definition"),
    "originalKey": Json(key),
    "observationsRewritten": false,
  })
  edges.push({
    id: "projected-edge-" + edges.length().to_string(),
    from,
    to,
    kind,
    sources,
  })
  true
}

///|
/// Build exact installed-final dependencies from a proven derived state program.
/// This does not parse or manufacture a register HistoryV4.
fn model_projected_point_edges_v4(
  program : ModelPointProgramV4,
  budget : ModelSourceBudgetV4,
) -> Array[ScopedDataEdgeInputV4]? {
  let sources : Map[String, Map[String, ModelRegisterWriteV4]] = Map([])
  let final_counts : Map[String, Int32] = Map([])
  let edges : Array[ScopedDataEdgeInputV4] = []
  let txs = program.transactions
  for ti, tx in txs {
    let final_installed : Map[String, Int32] = Map([])
    for oi, op in tx.ops {
      if !model_source_charge_v4(budget) {
        return None
      }
      if op.kind == Write && !op.revoked {
        final_installed[op.key] = oi
      }
    }
    for oi, op in tx.ops {
      if !model_source_charge_v4(budget) {
        return None
      }
      if op.kind != Write {
        continue
      }
      let versions = sources.get_or_default(op.key, Map([]))
      if versions.contains(op.version) ||
        program.initial.get(op.key) == Some(op.version) {
        return None
      }
      let is_final = tx.boundary.status == Committed &&
        !op.revoked &&
        final_installed.get(op.key) == Some(oi)
      versions[op.version] = { tx: ti, op: oi, is_final, }
      sources[op.key] = versions
      if is_final {
        final_counts[op.key] = final_counts.get_or_default(op.key, 0) + 1
      }
    }
  }
  for key, initial in program.initial {
    if !model_source_charge_v4(budget) {
      return None
    }
    let order = program.version_orders.get_or_default(key, [])
    if order.is_empty() ||
      order[0] != initial ||
      order.length() != final_counts.get_or_default(key, 0) + 1 {
      return None
    }
    let seen : Map[String, Bool] = Map([])
    for i, version in order {
      if !model_source_charge_v4(budget) {
        return None
      }
      if seen.contains(version) {
        return None
      }
      seen[version] = true
      if i == 0 {
        continue
      }
      let writer = match sources.get_or_default(key, Map([])).get(version) {
        Some(w) if w.is_final => w
        _ => return None
      }
      if i > 1 {
        let previous = sources.at(key).at(order[i - 1])
        if !model_projected_emit_v4(
            edges,
            program,
            txs[previous.tx].boundary.id,
            txs[writer.tx].boundary.id,
            ScopedWWItem,
            key,
            [
              txs[previous.tx].ops[previous.op].original,
              txs[writer.tx].ops[writer.op].original,
              { "completeDerivedVersionOrder": Json(order) },
            ],
            budget,
          ) {
          return None
        }
      }
    }
  }
  for ti, tx in txs {
    if tx.boundary.status != Committed {
      continue
    }
    let own : Map[String, Array[Int32]] = Map([])
    for oi, op in tx.ops {
      if !model_source_charge_v4(budget) {
        return None
      }
      let stack = own.get_or_default(op.key, [])
      model_pop_revoked_v4(txs, ti, stack, model_op_seq_v4(op), budget)
      if budget.limited {
        return None
      }
      if op.kind == Write {
        stack.push(oi)
        own[op.key] = stack
        continue
      }
      own[op.key] = stack
      if !stack.is_empty() {
        if tx.ops[stack[stack.length() - 1]].version != op.version {
          return None
        }
        continue
      }
      let order = program.version_orders.get_or_default(op.key, [])
      let mut position = -1
      for i, v in order {
        if !model_source_charge_v4(budget) {
          return None
        }
        if v == op.version {
          position = i
          break
        }
      }
      if position < 0 {
        return None
      }
      if position > 0 {
        let writer = sources.at(op.key).at(op.version)
        if !writer.is_final || writer.tx == ti {
          return None
        }
        if !model_projected_emit_v4(
            edges,
            program,
            txs[writer.tx].boundary.id,
            tx.boundary.id,
            ScopedWRItem,
            op.key,
            [txs[writer.tx].ops[writer.op].original, op.original],
            budget,
          ) {
          return None
        }
      }
      if position + 1 < order.length() {
        let successor = sources.at(op.key).at(order[position + 1])
        // An own immediate successor stops the external RW chain.
        if successor.tx != ti &&
          !model_projected_emit_v4(
            edges,
            program,
            tx.boundary.id,
            txs[successor.tx].boundary.id,
            ScopedRWItem,
            op.key,
            [
              op.original,
              txs[successor.tx].ops[successor.op].original,
              {
                "immediateDerivedSuccessor": Json(order[position + 1]),
                "completeDerivedVersionOrder": Json(order),
              },
            ],
            budget,
          ) {
          return None
        }
      }
    }
  }
  Some(edges)
}

///|
fn model_projected_edges_json_v4(edges : Array[ScopedDataEdgeInputV4]) -> Json {
  Json(
    edges.map(e => {
      (
        {
          "id": Json(e.id),
          "from": Json(e.from),
          "to": Json(e.to),
          "kind": Json(scoped_data_name_v4(e.kind)),
          "sources": Json(e.sources),
        } : Json)
    }),
  )
}

///|
/// The prefix embedding has a stronger scalar-INT premise than a native list
/// check may provide. It is an applicability check, not a relabelled anomaly.
fn model_projected_internal_v4(
  program : ModelPointProgramV4,
  budget : ModelSourceBudgetV4,
) -> ModelRuleV4 {
  let diagnostics : Array[Json] = []
  for ti, tx in program.transactions {
    if tx.boundary.status != Committed {
      continue
    }
    let own : Map[String, Array[Int32]] = Map([])
    let external : Map[String, String] = Map([])
    for oi, op in tx.ops {
      if !model_source_charge_v4(budget) {
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
      let expected = if stack.is_empty() {
        external.get(op.key)
      } else {
        Some(tx.ops[stack[stack.length() - 1]].version)
      }
      if expected is Some(v) && v != op.version {
        diagnostics.push({
          "actualRead": op.original,
          "expectedDerivedState": Json(v),
          "actualDerivedState": Json(op.version),
        })
      }
      if stack.is_empty() {
        external[op.key] = op.version
      }
    }
  }
  model_rule_v4(
    "prefix-state-internal-applicability",
    if diagnostics.is_empty() && !budget.limited {
      "checked-compatible"
    } else {
      "unknown"
    },
    "every derived scalar read respects the active own state or nearest delivered external base; this additional theorem premise does not relabel native list INT",
    evidence={
      "diagnostics": Json(diagnostics),
      "execution": model_mapping_counter_v4(
        budget, "list-prefix-projection-reference-checks-2",
      ),
    },
  )
}

///|
/// A component of an already delivered list read, never a fabricated SELECT.
/// Own effects stay in the original program; their external prefix constrains
/// snapshot visibility even if the own appends are later rolled back.
fn model_list_component_edges_v4(
  program : ModelPointProgramV4,
  edges : Array[ScopedDataEdgeInputV4],
  budget : ModelSourceBudgetV4,
) -> Bool {
  let finals : Map[String, Map[String, (String, Json)]] = Map([])
  for tx in program.transactions {
    if tx.boundary.status != Committed {
      continue
    }
    let last : Map[String, ModelRegisterOpV4] = Map([])
    for op in tx.ops {
      if !model_source_charge_v4(budget) {
        return false
      }
      if op.kind == Write && !op.revoked {
        last[op.key] = op
      }
    }
    for key, op in last {
      let versions = finals.get_or_default(key, Map([]))
      versions[op.version] = (tx.boundary.id, op.original)
      finals[key] = versions
    }
  }
  let components = capture_source_array_v4(
    object_fields_unchecked_v3(program.mapping).at("externalBaseComponents"),
  )
  for raw in components {
    if !model_source_charge_v4(budget) {
      return false
    }
    let c = object_fields_unchecked_v3(raw)
    if capture_source_array_v4(c.at("ownItemIds")).is_empty() {
      continue
    }
    let key = capture_source_string_v4(c.at("key"))
    let reader = capture_source_string_v4(c.at("transaction"))
    let base = capture_source_string_v4(c.at("derivedBaseVersion"))
    let order = program.version_orders.get_or_default(key, [])
    let mut position = -1
    for i, v in order {
      if !model_source_charge_v4(budget) {
        return false
      }
      if v == base {
        position = i
        break
      }
    }
    if position < 0 {
      return false
    }
    if position > 0 {
      let writer = finals.at(key).at(base)
      if writer.0 == reader {
        return false
      }
      if !model_projected_emit_v4(
          edges,
          program,
          writer.0,
          reader,
          ScopedWRItem,
          key,
          [
            writer.1,
            c.at("originalRead"),
            raw,
            {
              "basis": "delivered-list-read-external-prefix-component",
              "syntheticSelectCreated": false,
            },
          ],
          budget,
        ) {
        return false
      }
    }
    if position + 1 < order.length() {
      let successor = finals.at(key).at(order[position + 1])
      if successor.0 != reader &&
        !model_projected_emit_v4(
          edges,
          program,
          reader,
          successor.0,
          ScopedRWItem,
          key,
          [
            c.at("originalRead"),
            successor.1,
            raw,
            {
              "basis": "delivered-list-read-external-prefix-immediate-successor",
              "syntheticSelectCreated": false,
              "completeDerivedVersionOrder": Json(order),
            },
          ],
          budget,
        ) {
        return false
      }
    }
  }
  true
}
