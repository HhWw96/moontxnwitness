///|
/// A derived atomic-key-slot program, never a synthetic register HistoryV4.
pub struct RelationRowProjectionV4 {
  priv program : ModelPointProgramV4?
  priv edges : Array[ScopedDataEdgeInputV4]
  priv int_rule : ModelRuleV4
  priv write_rule : ModelRuleV4
  priv record : Json
}

///|
fn model_relation_slot_v4(index : RelationPointIndexV4, key : Int32) -> String {
  let k = index.keys[key]
  let table = index.parsed.tables[k.table]
  Json([
    Json("relation-row-slot-v1"),
    Json(table.name),
    Json(table.primary),
    Json(table.primary_type),
    k.wire,
  ]).stringify()
}

///|
fn model_relation_state_v4(
  index : RelationPointIndexV4,
  key : Int32,
  source : Int32,
) -> String {
  let slot = model_relation_slot_v4(index, key)
  if source < 0 {
    Json([Json(slot), Json("initial-absent")]).stringify()
  } else {
    let s = index.parsed.sources[source]
    Json([
      Json(slot),
      Json(if s.action == "delete" { "tombstone" } else { "present" }),
      Json(s.row.version),
    ]).stringify()
  }
}

///|
fn model_relation_snapshot_applicability_v4(
  program : ModelPointProgramV4,
  budget : ModelSourceBudgetV4,
) -> ModelRuleV4 {
  let findings : Array[Json] = []
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
        findings.push({
          "actualPointQuery": op.original,
          "expectedSlotState": Json(v),
          "deliveredSlotState": Json(op.version),
        })
      }
      if stack.is_empty() {
        external[op.key] = op.version
      }
    }
  }
  model_rule_v4(
    "row-slot-single-snapshot-applicability",
    if findings.is_empty() && !budget.limited {
      "checked-compatible"
    } else {
      "unknown"
    },
    "additional snapshot premise only; whole-row own assignments do not reveal an external prefix and changing external reads do not alone invalidate RC",
    evidence={
      "diagnostics": Json(findings),
      "execution": model_mapping_counter_v4(
        budget, "row-slot-source-and-projection-reference-checks-1",
      ),
    },
  )
}

///|
/// Formal repeatable-read INT is separate from per-operation source closure.
/// An externally observed version change can be legal at RC; all other native
/// gaps, including unknown sources and capacity/budget loss, still block projection.
fn model_relation_source_closed_v4(
  graph : RelationPointGraphV4,
  budget : ModelSourceBudgetV4,
) -> Bool {
  let index = graph.index
  graph.maximum >= 0 &&
  graph.maximum <= 1000000 &&
  index.parsed.programs.length() <= 128 &&
  index.parsed.operations <= 4096 &&
  !graph.limited &&
  index.journal_complete &&
  index.reads_complete &&
  index.orders_complete &&
  index.gaps.all(gap => {
    model_source_charge_v4(budget) &&
    object_fields_unchecked_v3(gap).get("code") ==
    Some(Json("relation-external-read-state-mismatch"))
  })
}

///|
fn model_relation_projection_body_v4(
  history : HistoryV4,
  graph : RelationPointGraphV4,
  budget : ModelSourceBudgetV4,
  gaps : Array[Json],
) -> (ModelPointProgramV4, ModelRuleV4)? {
  let index = graph.index
  let parsed = index.parsed
  let window = capture_window_v5(history, parsed.normalized, fn() {
    model_source_charge_v4(budget)
  })
  if !model_relation_source_closed_v4(graph, budget) ||
    graph.limited ||
    !window.complete ||
    window.unlocated ||
    !index.journal_complete ||
    !index.uncertain_after.is_empty() ||
    index.window_unproven ||
    !parsed.findings.is_empty() {
    return None
  }
  for tx, status in index.outcomes {
    if status == Unknown || !window.closed.get_or_default(tx, false) {
      return None
    }
  }
  let initial : Map[String, String] = Map([])
  let orders : Map[String, Array[String]] = Map([])
  let states : Map[String, Json] = Map([])
  let identities : Map[String, Json] = Map([])
  let read_by_seq : Map[Int64, RelationPointReadV4] = Map([])
  let query_projections : Array[Json] = []
  for read in index.reads {
    if !model_source_charge_v4(budget) {
      return None
    }
    if read.key < 0 || !read.delivered_complete || !read.usable {
      return None
    }
    read_by_seq[read.seq] = read
    query_projections.push({
      "transaction": Json(read.tx),
      "readSeq": Json(read.seq.to_double()),
      "queryIndex": Json(read.query_index),
      "identity": relation_point_key_json_v4(index, read.key),
      "originalPointQuery": index.originals.at(read.seq),
      "derivedSlotState": Json(
        model_relation_state_v4(index, read.key, read.observed),
      ),
      "sourceProof": relation_point_read_source_v4(index, read),
    })
  }
  for key in 0..<index.keys.length() {
    if !model_source_charge_v4(budget) {
      return None
    }
    if !index.ordered.contains(key) || key >= index.chains.length() {
      return None
    }
    let slot = model_relation_slot_v4(index, key)
    let first = relation_point_initial_v4(index, key)
    let version = model_relation_state_v4(index, key, first)
    initial[slot] = version
    let chain = [version]
    for source in index.chains[key] {
      if !model_source_charge_v4(budget) {
        return None
      }
      if !index.final_set[source] || parsed.sources[source].row.key != key {
        return None
      }
      chain.push(model_relation_state_v4(index, key, source))
    }
    orders[slot] = chain
    identities[slot] = relation_point_key_json_v4(index, key)
    if first < 0 {
      states[version] = {
        "state": "initial-absent",
        "identity": identities[slot],
        "basis": "complete original table snapshot",
        "snapshot": capture_source_array_v4(
          object_fields_unchecked_v3(history.source_document).at("events"),
        )[0],
        "physicalIncarnationAsserted": false,
      }
    }
  }
  for source, s in parsed.sources {
    if !model_source_charge_v4(budget) {
      return None
    }
    let id = model_relation_state_v4(index, s.row.key, source)
    states[id] = {
      "state": Json(
        if s.action == "delete" {
          "absent-tombstone"
        } else {
          "present"
        },
      ),
      "identity": relation_point_key_json_v4(index, s.row.key),
      "originalRowVersion": Json(s.row.version),
      "source": relation_point_source_json_v4(index, source),
      "physicalIncarnationAsserted": false,
    }
  }
  let boundary_map : Map[String, ModelTxBoundaryV4] = Map([])
  for b in model_raw_boundaries_v4(parsed.normalized) {
    boundary_map[b.id] = b
  }
  let programs : Array[ModelRegisterTxV4] = []
  let precondition_records : Array[Json] = []
  let precondition_gaps : Array[Json] = []
  for raw in parsed.programs {
    let own : Map[Int32, Int32] = Map([])
    let last_external : Map[Int32, Int32] = Map([])
    let trail : Array[(Int32, Int32)] = []
    let marks : Array[(String, Int32)] = []
    let ops : Array[ModelRegisterOpV4] = []
    for action in raw.actions {
      if !model_source_charge_v4(budget) {
        return None
      }
      match action {
        WriteRow(source) => {
          let s = parsed.sources[source]
          let key = s.row.key
          let slot = model_relation_slot_v4(index, key)
          let previous = own.get_or_default(key, -2)
          let parent = match s.predecessor {
            Some(v) => index.versions.get_or_default(v, -3)
            None => -1
          }
          let parent_present = parent >= 0 &&
            parsed.sources[parent].action != "delete"
          let presence_ok = if s.action == "insert" {
            !parent_present
          } else {
            parent_present
          }
          let mut covered = false
          let mut basis = "unproved-row-write-precondition"
          if previous >= 0 {
            covered = parent == previous
            basis = "actual-active-own-row-effect"
          } else if last_external.get(key) == Some(parent) {
            covered = true
            basis = "actual-delivered-point-query"
          } else {
            match index.finals.get_or_default(raw.id, Map([])).get(key) {
              Some(terminal_source) => {
                let rank = index.ranks[terminal_source]
                let base = if rank == 1 {
                  relation_point_initial_v4(index, key)
                } else if rank > 1 {
                  index.chains[key][rank - 2]
                } else {
                  -3
                }
                if parent == base {
                  covered = true
                  basis = "installed-final-writer-block-lineage-covered-by-WW"
                }
              }
              None =>
                if index.chains[key].is_empty() &&
                  parent == relation_point_initial_v4(index, key) {
                  covered = true
                  basis = "closed-window-immutable-initial-slot"
                }
            }
          }
          covered = covered && presence_ok && parent >= -1
          if raw.status == Committed && !covered {
            precondition_gaps.push({
              "transaction": Json(raw.id),
              "actualWrite": index.originals.at(s.seq),
              "identity": relation_point_key_json_v4(index, key),
              "code": "unobserved-row-state-precondition",
              "syntheticReadCreated": false,
            })
          }
          precondition_records.push({
            "transaction": Json(raw.id),
            "actualWrite": index.originals.at(s.seq),
            "basis": Json(basis),
            "preconditionCovered": Json(covered),
            "sourceRole": "write-lineage-not-SELECT",
            "externalValueInferredFromOwnAssignment": false,
          })
          let reverted = match
            object_fields_unchecked_v3(parsed.source_evidence[source]).get(
              "revertedBy",
            ) {
            Some(Number(n, ..)) => Some(n.to_int64())
            _ => None
          }
          ops.push({
            kind: Write,
            key: slot,
            version: model_relation_state_v4(index, key, source),
            original: index.originals.at(s.seq),
            predecessor: if parent >= -1 {
              Some(model_relation_state_v4(index, key, parent))
            } else {
              None
            },
            revoked: reverted is Some(_),
            revocation_seq: reverted,
          })
          trail.push((key, previous))
          own[key] = source
        }
        QueryRows(_, _, _, seq) => {
          let read = read_by_seq.at(seq)
          if read.tx != raw.id || read.own != own.get_or_default(read.key, -2) {
            return None
          }
          let slot = model_relation_slot_v4(index, read.key)
          ops.push({
            kind: Read,
            key: slot,
            version: model_relation_state_v4(index, read.key, read.observed),
            original: index.originals.at(seq),
            predecessor: None,
            revoked: false,
            revocation_seq: None,
          })
          if read.own < 0 {
            last_external[read.key] = read.observed
          }
        }
        Mark(instance) => marks.push((instance, trail.length()))
        Undo(instance) | Release(instance) => {
          let mut found = -1
          for i, mark in marks {
            if mark.0 == instance {
              found = i
            }
          }
          if found < 0 {
            return None
          }
          if action is Undo(_) {
            while trail.length() > marks[found].1 {
              let (key, previous) = trail.pop().unwrap()
              if previous == -2 {
                ignore(own.remove(key))
              } else {
                own[key] = previous
              }
            }
          }
          let keep = if action is Undo(_) { found + 1 } else { found }
          while marks.length() > keep {
            ignore(marks.pop())
          }
        }
      }
    }
    programs.push({ boundary: boundary_map.at(raw.id), ops, })
  }
  let write_rule = model_rule_v4(
    "write-input-applicability",
    if precondition_gaps.is_empty() && !budget.limited {
      "checked-compatible"
    } else {
      "unknown"
    },
    "row-effect predecessor and presence conditions are covered by actual reads, own state, installed WW lineage or a closed immutable initial slot; no read is synthesized",
    evidence={
      "definition": "row-effect-precondition-observability/v1",
      "records": Json(precondition_records),
      "gaps": Json(precondition_gaps),
      "execution": model_mapping_counter_v4(
        budget, "row-slot-source-and-projection-reference-checks-1",
      ),
    },
  )
  gaps.append(precondition_gaps)
  let mapping = model_point_mapping_v4(
    initial,
    programs,
    orders,
    history.source_document,
  )
  let fields = object_fields_unchecked_v3(mapping)
  fields["definition"] = Json("relation-row-slot-to-point-program/v1")
  fields["slotSemantics"] = Json(
    "persistent typed primary-key slot; physical incarnation equivalence is not asserted",
  )
  fields["originalRowStates"] = Json(states)
  fields["queryProjections"] = Json(query_projections)
  fields["slotIdentities"] = Json(identities)
  fields["versionIdentifiersAreDerivedConstraints"] = Json(true)
  fields["ownAssignmentsExposeExternalBase"] = Json(false)
  fields["writePreconditionCoverage"] = model_rule_json_v4(write_rule)
  fields["sourceModel"] = Json("relation-set-v1")
  Some(
    (
      { initial, transactions: programs, version_orders: orders, mapping, },
      write_rule,
    ),
  )
}

///|
fn model_relation_edge_sources_v4(
  index : RelationPointIndexV4,
  program : ModelPointProgramV4,
  edges : Array[ScopedDataEdgeInputV4],
  budget : ModelSourceBudgetV4,
) -> Array[ScopedDataEdgeInputV4]? {
  let read_by_seq : Map[Int64, RelationPointReadV4] = Map([])
  for read in index.reads {
    if !model_source_charge_v4(budget) {
      return None
    }
    read_by_seq[read.seq] = read
  }
  let identities = object_fields_unchecked_v3(
    object_fields_unchecked_v3(program.mapping).at("slotIdentities"),
  )
  let result : Array[ScopedDataEdgeInputV4] = []
  for edge in edges {
    if !model_source_charge_v4(budget) {
      return None
    }
    let sources = edge.sources.copy()
    for raw in edge.sources {
      if !model_source_charge_v4(budget) {
        return None
      }
      let fields = object_fields_unchecked_v3(raw)
      if fields.get("kind") == Some(Json("row_read")) {
        let seq = capture_source_seq_v4(fields.at("seq"))
        let read = read_by_seq.at(seq)
        sources.push({
          "basis": "atomic-row-actual-point-query-source",
          "dependencyScope": "item",
          "identity": relation_point_key_json_v4(index, read.key),
          "readSeq": Json(seq.to_double()),
          "queryIndex": Json(read.query_index),
          "originalPointQuery": raw,
          "readSource": relation_point_read_source_v4(index, read),
        })
      } else if fields.get("basis") ==
        Some(Json("derived-point-state-projection")) {
        let slot = capture_source_string_v4(fields.at("originalKey"))
        sources.push({
          "basis": "atomic-row-typed-slot-identity",
          "identity": identities.at(slot),
          "derivedSlot": Json(slot),
          "physicalIncarnationAsserted": false,
        })
      }
    }
    result.push({ ..edge, sources, })
  }
  Some(result)
}

///|
fn project_relation_rows_core_v4(
  history : HistoryV4,
  graph : RelationPointGraphV4,
  maximum : Int32,
) -> RelationRowProjectionV4 {
  let budget : ModelSourceBudgetV4 = {
    maximum,
    checks: graph.checks,
    limited: graph.limited,
  }
  let gaps : Array[Json] = []
  let candidate = model_relation_projection_body_v4(
    history, graph, budget, gaps,
  )
  let projected = match candidate {
    Some((program, write_rule)) =>
      match model_projected_point_edges_v4(program, budget) {
        Some(edges) =>
          model_relation_edge_sources_v4(graph.index, program, edges, budget).map(annotated => {
              (program, write_rule, annotated)
            },
          )
        None => None
      }
    None => None
  }
  let int_rule = match projected {
    Some((program, _, _)) =>
      model_relation_snapshot_applicability_v4(program, budget)
    None =>
      model_rule_v4(
        "row-slot-single-snapshot-applicability", "unknown", "no complete original point-row projection",
      )
  }
  let program = if budget.limited { None } else { projected.map(p => p.0) }
  let edges = if budget.limited {
    []
  } else {
    projected.map(p => p.2).unwrap_or([])
  }
  let write_rule = projected
    .map(p => p.1)
    .unwrap_or(
      model_rule_v4(
        "write-input-applicability", "unknown", "row program not projected",
      ),
    )
  {
    program,
    edges,
    int_rule,
    write_rule,
    record: {
      "format": "moontxnwitness-relation-row-projection/v4",
      "schemaVersion": 4,
      "semanticContract": "relation-row-slot-to-point-program/v1",
      "algorithm": "source-closed-row-slot-projection-1",
      "status": if program is Some(_) {
        Json("projected")
      } else {
        Json("unknown")
      },
      "sourceSha256": Json(v3_dislock_sha256(history.source_text)),
      "observations": history.source_document,
      "derivedProjection": match program {
        Some(p) => p.mapping
        None => Json::null()
      },
      "dependencyEdges": model_projected_edges_json_v4(edges),
      "singleSnapshotApplicability": model_rule_json_v4(int_rule),
      "writePreconditionApplicability": model_rule_json_v4(write_rule),
      "gaps": Json(gaps),
      "nativePointGraph": relation_point_graph_v4_json(graph),
      "execution": model_mapping_counter_v4(
        budget, "row-slot-source-and-projection-reference-checks-1",
      ),
      "scope": {
        "acceptsIsolationModels": false,
        "originalHistoryRewritten": false,
        "singlePrimaryKeyEqualityOnly": true,
        "ambiguousEmptySource": "unknown",
        "predicateCompletion": "pending",
        "ownAssignmentExternalBaseInferred": false,
      },
    },
  }
}

///|
pub fn project_relation_rows_v4(
  history : HistoryV4,
  max_checks~ : Int32 = 1000000,
) -> Result[RelationRowProjectionV4, String] {
  match build_relation_point_graph_v4(history, max_checks~) {
    Ok(graph) => Ok(project_relation_rows_core_v4(history, graph, max_checks))
    Err(reason) => Err(reason)
  }
}

///|
pub fn relation_row_projection_v4_json(value : RelationRowProjectionV4) -> Json {
  v4_json_copy(value.record)
}

///|
pub fn RelationRowProjectionV4::is_projected(
  self : RelationRowProjectionV4,
) -> Bool {
  self.program is Some(_)
}

///|
pub fn verify_relation_row_projection_v4(
  history : HistoryV4,
  report : Json,
  max_checks~ : Int32 = 1000000,
) -> Bool {
  match project_relation_rows_v4(history, max_checks~) {
    Ok(value) => report == value.record
    Err(_) => false
  }
}

///|
fn model_relation_projected_source_v4(
  history : HistoryV4,
  base : ModelSourceV4,
  graph : RelationPointGraphV4,
  maximum : Int32,
) -> ModelSourceV4 {
  let projection = project_relation_rows_core_v4(history, graph, maximum)
  let rules = base.rules.copy()
  let applicability = model_rule_v4(
    "row-slot-projection-applicability",
    if projection.program is Some(_) {
      "checked-compatible"
    } else {
      "unknown"
    },
    "explicit atomic row interpretation requires every original point query and effect to have a closed typed-key source",
    evidence=projection.record,
  )
  rules[applicability.id] = applicability
  let program = match projection.program {
    Some(p) => p
    None =>
      return {
        ..base,
        rules,
        execution: {
          "native": base.execution,
          "rowProjectionAttempt": projection.record,
        },
      }
  }
  rules["row-slot-point-query-coverage"] = model_rule_v4(
    "row-slot-point-query-coverage",
    "checked-compatible",
    "every original complete singleton-primary-key query is represented by exactly one proved slot value; range and extra predicates are unsupported",
    evidence=projection.record,
  )
  // Every actual read has now been rechecked against a unique installed final
  // source or its exact active own effect. Preserve any reliable raw refutation;
  // external repeatable-read INT stays a separate rule for the models requiring it.
  for id in ["G1a", "G1b", "future-source-applicability"] {
    if rules.at(id).status != "refuted" {
      rules[id] = model_rule_v4(
        id,
        "checked-compatible",
        "every original singleton read has a validated final/initial source or active own effect; changing external reads do not alone make RC source-incomplete",
        evidence=projection.record,
      )
    }
  }
  rules[projection.int_rule.id] = projection.int_rule
  rules[projection.write_rule.id] = projection.write_rule
  {
    ..base,
    rules,
    edges: projection.edges,
    profile: "captured-relation-row-slots/v1",
    point_program: Some(program),
    ww_complete: true,
    wr_complete: true,
    rw_complete: true,
    gaps: [],
    execution: {
      "counterContract": "row-slot-source-and-graph-counters-1",
      "sharedNativePointIndex": true,
      "projectionRecord": projection.record,
    },
  }
}
