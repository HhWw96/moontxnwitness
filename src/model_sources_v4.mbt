///|
priv struct ModelSourceBudgetV4 {
  maximum : Int32
  mut checks : Int32
  mut limited : Bool
}

///|
priv struct ModelTxBoundaryV4 {
  id : String
  status : TxStatus
  start : Int64?
  end : Int64?
  invocation : Json
  response : Json
}

///|
priv struct ModelSourceV4 {
  nodes : Array[String]
  edges : Array[ScopedDataEdgeInputV4]
  boundaries : Array[ModelTxBoundaryV4]
  rules : Map[String, ModelRuleV4]
  gaps : Array[Json]
  ww_complete : Bool
  wr_complete : Bool
  rw_complete : Bool
  execution : Json
  profile : String
  point_program : ModelPointProgramV4?
}

///|
priv struct ModelRegisterOpV4 {
  kind : OpKind
  key : String
  version : String
  original : Json
  predecessor : String?
  revoked : Bool
  revocation_seq : Int64?
}

///|
priv struct ModelRegisterTxV4 {
  boundary : ModelTxBoundaryV4
  ops : Array[ModelRegisterOpV4]
}

///|
priv struct ModelRegisterWriteV4 {
  tx : Int32
  op : Int32
  is_final : Bool
}

///|
fn model_source_charge_v4(budget : ModelSourceBudgetV4) -> Bool {
  if budget.checks >= budget.maximum {
    budget.limited = true
    false
  } else {
    budget.checks += 1
    true
  }
}

///|
fn model_source_status_v4(proofs : Array[Json], complete : Bool) -> String {
  if !proofs.is_empty() {
    "refuted"
  } else if complete {
    "checked-compatible"
  } else {
    "unknown"
  }
}

///|
fn model_source_execution_v4(budget : ModelSourceBudgetV4) -> Json {
  {
    "counterContract": "model-source-reference-checks-1",
    "checks": Json(budget.checks),
    "limited": Json(budget.limited),
    "maxChecks": Json(budget.maximum),
  }
}

///|
fn model_raw_boundaries_v4(normalized : Json) -> Array[ModelTxBoundaryV4] {
  let n = object_fields_unchecked_v3(normalized)
  let originals : Map[Int64, Json] = Map([])
  for event in capture_source_array_v4(n.at("observations")) {
    let f = object_fields_unchecked_v3(event)
    originals[capture_source_seq_v4(f.at("seq"))] = event
  }
  capture_source_array_v4(n.at("transactions")).map(raw => {
    let tx = object_fields_unchecked_v3(raw)
    let first = originals.get_or_default(
      capture_source_seq_v4(tx.at("beginSeq")),
      Json::null(),
    )
    let last = match tx.at("endSeq") {
      Number(seq, ..) => originals.get_or_default(seq.to_int64(), Json::null())
      _ => Json::null()
    }
    let status = match capture_source_string_v4(tx.at("status")) {
      "committed" => Committed
      "aborted" => Aborted
      _ => Unknown
    }
    let start = match object_fields_unchecked_v3(first).get("time") {
      Some(Number(n, ..)) => Some(n.to_int64())
      _ => None
    }
    let end = if status == Unknown {
      None
    } else {
      match object_fields_unchecked_v3(last).get("time") {
        Some(Number(n, ..)) => Some(n.to_int64())
        _ => None
      }
    }
    (
      {
        id: capture_source_string_v4(tx.at("id")),
        status,
        start,
        end,
        invocation: first,
        response: last,
      } : ModelTxBoundaryV4)
  })
}

///|
fn model_register_input_v4(
  history : HistoryV4,
) -> (
  Map[String, String],
  Array[ModelRegisterTxV4],
  Map[String, Array[String]],
  Array[Json],
  Bool,
) {
  match history.payload {
    RegisterSnapshot(Some(h), None) => {
      let txs = h.transactions.map(tx => {
        let boundary : ModelTxBoundaryV4 = {
          id: tx.id,
          status: tx.status,
          start: tx.start,
          end: tx.end,
          invocation: {
            "tx": Json(tx.id),
            "boundary": "invocation",
            "time": match tx.start {
              Some(t) => Json(t.to_double())
              None => Json::null()
            },
          },
          response: {
            "tx": Json(tx.id),
            "boundary": "response",
            "status": Json(status_label(tx.status)),
            "time": match tx.end {
              Some(t) => Json(t.to_double())
              None => Json::null()
            },
          },
        }
        let ops = tx.ops.mapi((i, op) => {
          (
            {
              kind: op.kind,
              key: op.key,
              version: op.version,
              original: {
                "tx": Json(tx.id),
                "operationIndex": Json(i),
                "operation": (
                  {
                    "kind": Json(op_label(op.kind)),
                    "key": Json(op.key),
                    "version": Json(op.version),
                  } : Json),
              },
              predecessor: None,
              revoked: false,
              revocation_seq: None,
            } : ModelRegisterOpV4)
        })
        ({ boundary, ops, } : ModelRegisterTxV4)
      })
      (h.initial, txs, h.version_orders, [], true)
    }
    RegisterSnapshot(_, Some(normalized)) => {
      let n = object_fields_unchecked_v3(normalized)
      let initial : Map[String, String] = Map([])
      let effects : Map[Int64, Json] = Map([])
      for raw in capture_source_array_v4(n.at("effects")) {
        let e = object_fields_unchecked_v3(raw)
        effects[capture_source_seq_v4(e.at("seq"))] = raw
      }
      let by_tx : Map[String, Array[ModelRegisterOpV4]] = Map([])
      for raw in capture_source_array_v4(n.at("observations")) {
        let e = object_fields_unchecked_v3(raw)
        let kind = capture_source_string_v4(e.at("kind"))
        if kind == "snapshot" {
          for key, value in object_fields_unchecked_v3(e.at("initial")) {
            initial[key] = capture_source_string_v4(value)
          }
        }
        if kind != "read" && kind != "write" {
          continue
        }
        let tx = capture_source_string_v4(e.at("tx"))
        let ops = by_tx.get_or_default(tx, [])
        let effect = object_fields_unchecked_v3(
          effects.get_or_default(
            capture_source_seq_v4(e.at("seq")),
            Json::null(),
          ),
        )
        ops.push({
          kind: if kind == "read" {
            Read
          } else {
            Write
          },
          key: capture_source_string_v4(e.at("key")),
          version: capture_source_string_v4(e.at("version")),
          original: raw,
          predecessor: match e.get("predecessor") {
            Some(String(v)) => Some(v)
            _ => None
          },
          revoked: kind == "write" && effect.at("revertedBy") != Json::null(),
          revocation_seq: match
            effect.get_or_default("revertedBy", Json::null()) {
            Number(n, ..) => Some(n.to_int64())
            _ => None
          },
        })
        by_tx[tx] = ops
      }
      let txs = model_raw_boundaries_v4(normalized).map(boundary => {
        (
          { ops: by_tx.get_or_default(boundary.id, []), boundary, } :
          ModelRegisterTxV4)
      })
      let gaps = capture_source_array_v4(
        object_fields_unchecked_v3(n.at("coverage")).at("gaps"),
      ).copy()
      (initial, txs, Map([]), gaps, false)
    }
    _ =>
      (
        Map([]),
        [],
        Map([]),
        [{ "code": "register-source-not-available" }],
        false,
      )
  }
}

///|
fn model_register_edge_v4(
  edges : Array[ScopedDataEdgeInputV4],
  txs : Array[ModelRegisterTxV4],
  first : Int32,
  last : Int32,
  kind : ScopedDataKindV4,
  sources : Array[Json],
) -> Unit {
  if first == last || edges.length() >= 50000 {
    return
  }
  edges.push({
    id: "source-edge-" + edges.length().to_string(),
    from: txs[first].boundary.id,
    to: txs[last].boundary.id,
    kind,
    sources,
  })
}

///|
fn model_register_source_v4(
  history : HistoryV4,
  maximum : Int32,
) -> ModelSourceV4 {
  let (initial, txs, declared, gaps, is_declared) = model_register_input_v4(
    history,
  )
  let budget : ModelSourceBudgetV4 = { maximum, checks: 0, limited: false, }
  let window = if is_declared {
    None
  } else {
    match history.payload {
      RegisterSnapshot(_, Some(n)) =>
        Some(
          capture_window_v5(history, n, fn() { model_source_charge_v4(budget) }),
        )
      _ => None
    }
  }
  let sources : Map[String, Map[String, ModelRegisterWriteV4]] = Map([])
  let finals : Map[String, Array[String]] = Map([])
  let nodes : Array[String] = []
  let aborted_reads : Array[Json] = []
  let intermediate_reads : Array[Json] = []
  let internal : Array[Json] = []
  let future : Array[Json] = []
  let edges : Array[ScopedDataEdgeInputV4] = []
  let mut ww_complete = true
  let mut wr_complete = true
  let mut rw_complete = true
  let mut direct_complete = true
  let mut int_complete = is_declared
  let mut identity_complete = true
  if txs.length() > 128 ||
    txs.fold(init=0, (n, tx) => n + tx.ops.length()) > 4096 {
    ww_complete = false
    wr_complete = false
    rw_complete = false
    direct_complete = false
    int_complete = false
    identity_complete = false
    gaps.push({ "code": "model-source-size-limit" })
  }
  for gap in gaps {
    let g = object_fields_unchecked_v3(gap)
    let code = capture_source_string_v4(g.at("code"))
    let message = capture_source_string_v4(g.at("message"))
    let read_only = code == "unsafe_read_source" ||
      code == "own_read_mismatch" ||
      (code == "missing_version_source" && message.has_prefix("A read"))
    if !read_only {
      ww_complete = false
    }
    wr_complete = false
    rw_complete = false
    direct_complete = false
  }
  for ti, tx in txs {
    if !model_source_charge_v4(budget) {
      break
    }
    if tx.boundary.status == Committed {
      nodes.push(tx.boundary.id)
    }
    let last : Map[String, Int32] = Map([])
    for oi, op in tx.ops {
      if !model_source_charge_v4(budget) {
        break
      }
      if op.kind == Write && !op.revoked {
        last[op.key] = oi
      }
      if tx.boundary.status == Unknown {
        if op.kind == Write {
          ww_complete = false
        }
        wr_complete = false
        rw_complete = false
        direct_complete = false
      }
    }
    for oi, op in tx.ops {
      if !model_source_charge_v4(budget) {
        break
      }
      if op.kind != Write {
        continue
      }
      let versions = sources.get_or_default(op.key, Map([]))
      let producer_closed = is_declared ||
        (match window {
          Some(w) => w.closed.get_or_default(tx.boundary.id, false)
          _ => false
        })
      let is_final = producer_closed &&
        last.get(op.key) == Some(oi) &&
        !op.revoked
      versions[op.version] = { tx: ti, op: oi, is_final, }
      sources[op.key] = versions
      if is_final && tx.boundary.status == Committed {
        let values = finals.get_or_default(op.key, [])
        values.push(op.version)
        finals[op.key] = values
      }
    }
  }
  let orders : Map[String, Array[String]] = Map([])
  let keys = initial.keys().collect()
  keys.sort()
  for key in keys {
    if !model_source_charge_v4(budget) {
      break
    }
    let init = initial.at(key)
    let final_versions = finals.get_or_default(key, [])
    let versions = sources.get_or_default(key, Map([]))
    let mut order : Array[String] = [init]
    let mut valid = true
    if is_declared {
      match declared.get(key) {
        Some(given) => {
          order = given.copy()
          valid = order.length() == final_versions.length() + 1 &&
            order[0] == init
          let seen : Map[String, Bool] = Map([])
          for version in order {
            if !model_source_charge_v4(budget) {
              valid = false
              break
            }
            if seen.contains(version) ||
              (version != init && !final_versions.contains(version)) {
              valid = false
            }
            seen[version] = true
          }
          for version in final_versions {
            if !seen.contains(version) {
              valid = false
            }
          }
        }
        None =>
          if final_versions.length() <= 1 {
            order.append(final_versions)
          } else {
            valid = false
          }
      }
    } else {
      let successors : Map[String, Array[String]] = Map([])
      for version in final_versions {
        if !model_source_charge_v4(budget) {
          valid = false
          break
        }
        let current = versions.at(version)
        let mut predecessor = txs[current.tx].ops[current.op].predecessor
        let mut attempts = 0
        while predecessor is Some(v) && v != init {
          if !model_source_charge_v4(budget) {
            valid = false
            break
          }
          attempts += 1
          if attempts > txs[current.tx].ops.length() {
            valid = false
            break
          }
          match versions.get(v) {
            Some(previous) if previous.is_final &&
              txs[previous.tx].boundary.status == Committed => break
            Some(previous) if previous.tx == current.tx &&
              !txs[previous.tx].ops[previous.op].revoked &&
              previous.op < current.op =>
              predecessor = txs[previous.tx].ops[previous.op].predecessor
            _ => {
              valid = false
              break
            }
          }
        }
        match predecessor {
          Some(v) => {
            let next = successors.get_or_default(v, [])
            next.push(version)
            successors[v] = next
          }
          None => valid = false
        }
      }
      let mut cursor = init
      while order.length() <= final_versions.length() {
        if !model_source_charge_v4(budget) {
          valid = false
          break
        }
        match successors.get(cursor) {
          None => break
          Some(next) if next.length() == 1 && !order.contains(next[0]) => {
            cursor = next[0]
            order.push(cursor)
          }
          _ => {
            valid = false
            break
          }
        }
      }
      if order.length() != final_versions.length() + 1 {
        valid = false
      }
    }
    if !valid || budget.limited {
      ww_complete = false
      rw_complete = false
      gaps.push({
        "code": "installed-version-order-unresolved",
        "key": Json(key),
      })
      continue
    }
    orders[key] = order
    for i in 1..<order.length() {
      if !model_source_charge_v4(budget) {
        break
      }
      if i == 1 {
        continue
      }
      let a = versions.at(order[i - 1])
      let b = versions.at(order[i])
      model_register_edge_v4(edges, txs, a.tx, b.tx, ScopedWWItem, [
        txs[a.tx].ops[a.op].original,
        txs[b.tx].ops[b.op].original,
        {
          "kind": "complete-installed-version-order",
          "key": Json(key),
          "order": Json(order),
        },
      ])
    }
  }
  for ti, tx in txs {
    if tx.boundary.status != Committed {
      continue
    }
    let known : Map[String, String] = Map([])
    for oi, op in tx.ops {
      if !model_source_charge_v4(budget) {
        break
      }
      if !is_declared &&
        !capture_prefix_known_v5(window, tx.boundary.id, model_op_seq_v4(op)) {
        wr_complete = false
        rw_complete = false
        continue
      }
      if op.revoked {
        continue
      }
      if op.kind == Write {
        if is_declared {
          known[op.key] = op.version
        }
        continue
      }
      let expected = known.get(op.key)
      let versions = sources.get_or_default(op.key, Map([]))
      let source = versions.get(op.version)
      if op.version != initial.get_or_default(op.key, "") && source is None {
        direct_complete = false
        int_complete = false
        wr_complete = false
        rw_complete = false
        identity_complete = false
        let _ = known.remove(op.key)
        gaps.push({ "code": "read-source-missing", "read": op.original })
        continue
      }
      if is_declared && expected is Some(v) && v != op.version {
        internal.push({
          "category": "internal",
          "tx": Json(tx.boundary.id),
          "operationIndex": Json(oi),
          "read": op.original,
          "expectedVersion": Json(v),
          "actualVersion": Json(op.version),
        })
      }
      if is_declared {
        known[op.key] = op.version
      }
      match source {
        Some(writer) if writer.tx == ti => {
          if writer.op > oi {
            future.push({
              "code": "same-program-future-source",
              "read": op.original,
              "write": txs[writer.tx].ops[writer.op].original,
              "mapping": "source applicability failure; not asserted as a multi-transaction G1c witness",
            })
          }
          continue
        }
        Some(writer) => {
          let producer = txs[writer.tx]
          let proof : Json = {
            "reader": op.original,
            "writer": producer.ops[writer.op].original,
            "writerOutcome": Json(status_label(producer.boundary.status)),
            "finalWrite": Json(writer.is_final),
          }
          if producer.boundary.status == Aborted ||
            producer.ops[writer.op].revoked {
            aborted_reads.push(proof)
            wr_complete = false
            rw_complete = false
            continue
          }
          if producer.boundary.status == Unknown {
            direct_complete = false
            wr_complete = false
            rw_complete = false
            continue
          }
          if !writer.is_final {
            intermediate_reads.push(proof)
            wr_complete = false
            rw_complete = false
            continue
          }
          model_register_edge_v4(edges, txs, writer.tx, ti, ScopedWRItem, [
            producer.ops[writer.op].original,
            op.original,
          ])
        }
        None => ()
      }
      match orders.get(op.key) {
        Some(order) => {
          let mut position = -1
          for i, v in order {
            if !model_source_charge_v4(budget) {
              break
            }
            if v == op.version {
              position = i
              break
            }
          }
          if position < 0 {
            rw_complete = false
            continue
          }
          if position + 1 < order.length() {
            let successor = versions.at(order[position + 1])
            model_register_edge_v4(edges, txs, ti, successor.tx, ScopedRWItem, [
              op.original,
              txs[successor.tx].ops[successor.op].original,
              {
                "kind": "immediate-installed-successor",
                "order": Json(order),
                "fromIndex": Json(position),
              },
            ])
          }
        }
        None => rw_complete = false
      }
    }
  }
  if edges.length() >= 50000 {
    ww_complete = false
    wr_complete = false
    rw_complete = false
    gaps.push({ "code": "model-edge-limit" })
  }
  if budget.limited {
    ww_complete = false
    wr_complete = false
    rw_complete = false
    direct_complete = false
    int_complete = false
    gaps.push({ "code": "model-source-budget" })
  }
  if !future.is_empty() {
    wr_complete = false
    rw_complete = false
  }
  let audit = model_register_program_audit_v4(txs, maximum)
  let safe_edges = model_register_audited_edges_v4(edges, audit)
  if audit.rule.status != "checked-compatible" {
    wr_complete = false
    rw_complete = false
  }
  let rules : Map[String, ModelRuleV4] = Map([])
  rules["source-identity-and-installation"] = model_rule_v4(
    "source-identity-and-installation",
    if ww_complete {
      "checked-compatible"
    } else {
      "unknown"
    },
    "write identities and complete installed-final version order; read anomalies are not write gaps",
    evidence=Json(gaps),
  )
  for (name, proofs) in [("G1a", aborted_reads), ("G1b", intermediate_reads)] {
    rules[name] = model_rule_v4(
      name,
      model_source_status_v4(proofs, direct_complete),
      "actual committed reads checked against original producer outcome and final effect",
      evidence=Json(proofs),
    )
  }
  rules["future-source-applicability"] = model_rule_v4(
    "future-source-applicability",
    if !future.is_empty() {
      "pending"
    } else if direct_complete {
      "checked-compatible"
    } else {
      "unknown"
    },
    "same-program future-source diagnostic is not automatically mapped to the fixed Elle G1c checker",
    evidence=Json(future),
  )
  rules["internal"] = model_rule_v4(
    "internal",
    model_source_status_v4(internal, int_complete),
    "nearest actual read or own write; version predecessor is never fabricated as a read",
    evidence=Json(internal),
  )
  rules["identity-source-applicability"] = model_rule_v4(
    "identity-source-applicability",
    if identity_complete && !budget.limited {
      "checked-compatible"
    } else {
      "unknown"
    },
    "every delivered scalar version identity has a unique original initial/write source; known aborted sources remain distinct from missing sources",
  )
  rules["program-source-applicability"] = audit.rule
  rules["source-cyclic-versions"] = model_rule_v4(
    "source-cyclic-versions",
    if ww_complete {
      "checked-compatible"
    } else {
      "unknown"
    },
    "strict installed-final scalar version orders contain no cycle",
  )
  rules["duplicate-elements"] = model_rule_v4(
    "duplicate-elements", "checked-compatible", "register version assignments contain no append-element multiplicity primitive",
  )
  rules["write-input-applicability"] = if is_declared {
    model_rule_v4(
      "write-input-applicability", "checked-compatible", "declared register writes are blind version assignments, not read-modify-write input observations",
    )
  } else {
    model_raw_write_lineage_v4(initial, txs, sources, window, budget)
  }
  if !is_declared {
    let direct = object_fields_unchecked_v3(
      inspect_capture_anomalies_v4(history, max_checks=maximum).record,
    )
    for name in ["G1a", "G1b"] {
      let findings = capture_source_array_v4(direct.at("findings")).filter(f => {
        let fields = object_fields_unchecked_v3(f)
        fields.at("category") == Json(name) ||
        (
          name == "G1a" &&
          fields.at("category") == Json("dirty-update") &&
          capture_source_array_v4(
            fields.get_or_default("impliedAnomalies", Json::null()),
          ).contains(Json("G1a"))
        )
      })
      rules[name] = model_rule_v4(
        name,
        model_source_status_v4(
          findings,
          object_fields_unchecked_v3(direct.at("coverage")).at("complete") ==
          Json(true),
        ),
        "fresh raw capture source helper with complete-window or known-prefix source guarantees",
        evidence=Json(direct),
      )
    }
    let int = object_fields_unchecked_v3(
      inspect_internal_consistency_v4(history, max_checks=maximum).record,
    )
    rules["internal"] = model_rule_v4(
      "internal",
      if int.at("status") == Json("checked") {
        "checked-compatible"
      } else {
        capture_source_string_v4(int.at("status"))
      },
      "fresh raw capture effective-overlay INT helper",
      evidence=Json(int),
    )
  }
  {
    nodes,
    edges: safe_edges,
    boundaries: txs.map(tx => tx.boundary),
    rules,
    gaps,
    ww_complete,
    wr_complete,
    rw_complete,
    execution: if is_declared {
      model_source_execution_v4(budget)
    } else {
      model_mapping_counter_v4(
        budget, "model-captured-register-window-and-source-checks-2",
      )
    },
    profile: if is_declared {
      "declared-register-full-program/v1"
    } else {
      "captured-register-full-program/v2"
    },
    point_program: Some({
      initial,
      transactions: txs,
      version_orders: orders,
      mapping: if is_declared {
        Json::null()
      } else {
        model_point_mapping_v4(initial, txs, orders, history.source_document)
      },
    }),
  }
}
