///|
priv struct ModelProgramAuditV4 {
  rule : ModelRuleV4
  invalid_reads : Map[String, Map[String, Bool]]
  admitted_reads : Map[String, Map[String, Bool]]
}

///|
fn model_operation_identity_v4(original : Json) -> String {
  let fields = object_fields_unchecked_v3(original)
  match fields.get("operationIndex") {
    Some(Number(n, ..)) => "index:" + n.to_int().to_string()
    _ =>
      match fields.get("seq") {
        Some(Number(n, ..)) => "seq:" + n.to_int64().to_string()
        _ => ""
      }
  }
}

///|
fn model_register_program_audit_v4(
  txs : Array[ModelRegisterTxV4],
  maximum : Int32,
) -> ModelProgramAuditV4 {
  let budget : ModelSourceBudgetV4 = { maximum, checks: 0, limited: false, }
  let bad : Map[String, Map[String, Bool]] = Map([])
  let diagnostics : Array[Json] = []
  let admitted : Map[String, Map[String, Bool]] = Map([])
  for tx in txs {
    if tx.boundary.status != Committed {
      continue
    }
    let produced : Map[String, Map[String, Bool]] = Map([])
    for op in tx.ops {
      if !model_source_charge_v4(budget) {
        break
      }
      if op.kind == Write {
        let versions = produced.get_or_default(op.key, Map([]))
        versions[op.version] = true
        produced[op.key] = versions
      }
    }
    let stacks : Map[String, Array[Int32]] = Map([])
    for oi, op in tx.ops {
      if !model_source_charge_v4(budget) {
        break
      }
      let stack = stacks.get_or_default(op.key, [])
      let seq = match object_fields_unchecked_v3(op.original).get("seq") {
        Some(Number(n, ..)) => Some(n.to_int64())
        _ => None
      }
      while !stack.is_empty() {
        let earlier = tx.ops[stack[stack.length() - 1]]
        match (earlier.revocation_seq, seq) {
          (Some(rollback), Some(current)) if rollback <= current => {
            if !model_source_charge_v4(budget) {
              break
            }
            let _ = stack.pop()
          }
          _ => break
        }
      }
      if op.kind == Write {
        stack.push(oi)
        stacks[op.key] = stack
        continue
      }
      stacks[op.key] = stack
      let expected = if stack.is_empty() {
        None
      } else {
        Some(tx.ops[stack[stack.length() - 1]].version)
      }
      let violation = match expected {
        Some(version) => version != op.version
        None => produced.get_or_default(op.key, Map([])).contains(op.version)
      }
      if !violation {
        let reads = admitted.get_or_default(tx.boundary.id, Map([]))
        reads[model_operation_identity_v4(op.original)] = true
        admitted[tx.boundary.id] = reads
      }
      if violation {
        let reads = bad.get_or_default(tx.boundary.id, Map([]))
        reads[model_operation_identity_v4(op.original)] = true
        bad[tx.boundary.id] = reads
        diagnostics.push({
          "code": "read-own-latest-or-own-source-not-active",
          "transaction": Json(tx.boundary.id),
          "key": Json(op.key),
          "actualRead": op.original,
          "expectedOwnVersion": match expected {
            Some(v) => Json(v)
            None => Json::null()
          },
          "meaning": "workload applicability failure; not automatically a formal G1c witness",
        })
      }
    }
  }
  {
    rule: model_rule_v4(
      "program-source-applicability",
      if budget.limited || !diagnostics.is_empty() {
        "unknown"
      } else {
        "checked-compatible"
      },
      "every delivered read respects the active own-write overlay; external repeatable-read INT is a separate obligation",
      evidence={
        "diagnostics": Json(diagnostics),
        "execution": model_source_execution_v4(budget),
      },
    ),
    invalid_reads: bad,
    admitted_reads: admitted,
  }
}

///|
fn model_register_audited_edges_v4(
  edges : Array[ScopedDataEdgeInputV4],
  audit : ModelProgramAuditV4,
) -> Array[ScopedDataEdgeInputV4] {
  edges.filter(edge => {
    if edge.kind == ScopedWWItem {
      return true
    }
    !edge.sources.any(raw => {
      let fields = object_fields_unchecked_v3(raw)
      let operation = object_fields_unchecked_v3(
        fields.get_or_default("operation", Json::null()),
      )
      let read = fields.get("kind") == Some(Json("read")) ||
        operation.get("kind") == Some(Json("read"))
      if !read {
        return false
      }
      match fields.get("tx") {
        Some(String(tx)) =>
          !audit.admitted_reads
          .get_or_default(tx, Map([]))
          .contains(model_operation_identity_v4(raw)) ||
          audit.invalid_reads
          .get_or_default(tx, Map([]))
          .contains(model_operation_identity_v4(raw))
        _ => true
      }
    })
  })
}

///|
fn model_list_program_rule_v4(graph : EffectiveListGraphV4) -> ModelRuleV4 {
  let diagnostics : Array[Json] = []
  let mut complete = graph.index.journal_complete && !graph.limited
  for read in graph.index.reads {
    if graph.index.outcomes.get(read.tx) != Some(Committed) {
      continue
    }
    let own = read.own_at_read
    let mut valid = read.observed.length() >= own.length()
    if valid {
      let start = read.observed.length() - own.length()
      for i in 0..<own.length() {
        if own[i] != read.observed[start + i] {
          valid = false
        }
      }
    }
    for item in read.observed {
      if item >= 0 &&
        graph.index.parsed.items[item].tx == Some(read.tx) &&
        !own.contains(item) {
        valid = false
      }
    }
    if !valid {
      complete = false
      diagnostics.push({
        "transaction": Json(read.tx),
        "readSeq": Json(read.seq.to_double()),
        "ownAtDelivery": Json(
          list_effective_item_ids_v4(graph.index.parsed, own),
        ),
        "observed": Json(
          list_effective_item_ids_v4(graph.index.parsed, read.observed),
        ),
      })
    }
  }
  model_rule_v4(
    "program-source-applicability",
    if complete {
      "checked-compatible"
    } else {
      "unknown"
    },
    "actual list reads must include exactly the active own suffix; earlier legal own observations survive later rollback",
    evidence=Json(diagnostics),
  )
}

///|
fn model_relation_program_rule_v4(graph : RelationPointGraphV4) -> ModelRuleV4 {
  let diagnostics : Array[Json] = []
  let index = graph.index
  let mut complete = index.journal_complete &&
    !graph.limited &&
    index.uncertain_after.is_empty() &&
    !index.window_unproven
  for read in index.reads {
    if index.outcomes.get(read.tx) != Some(Committed) || read.key < 0 {
      continue
    }
    let mut valid = true
    if read.own >= 0 {
      let expected = index.parsed.sources[read.own]
      valid = if expected.action == "delete" {
        read.rows.is_empty()
      } else {
        read.rows.length() == 1 &&
        read.rows[0].version == expected.row.version &&
        read.rows[0].values == expected.row.values
      }
    } else {
      for row in read.rows {
        match index.versions.get(row.version) {
          Some(i) if index.parsed.sources[i].writer == Some(read.tx) =>
            valid = false
          _ => ()
        }
      }
    }
    if !valid {
      complete = false
      diagnostics.push({
        "transaction": Json(read.tx),
        "readSeq": Json(read.seq.to_double()),
        "queryIndex": Json(read.query_index),
        "actualRead": index.originals.get_or_default(read.seq, Json::null()),
        "expectedOwnEffect": relation_point_source_json_v4(index, read.own),
      })
    }
  }
  model_rule_v4(
    "program-source-applicability",
    if complete {
      "checked-compatible"
    } else {
      "unknown"
    },
    "point delivered reads respect the active row/tombstone overlay; scalar source changes without own writes do not invalidate RC",
    evidence=Json(diagnostics),
  )
}
