///|
pub struct ListPrefixProjectionV4 {
  priv program : ModelPointProgramV4?
  priv edges : Array[ScopedDataEdgeInputV4]
  priv int_rule : ModelRuleV4
  priv record : Json
}

///|
fn list_prefix_version_v4(
  parsed : ListV3Parsed,
  key : String,
  items : Array[Int32],
) -> String {
  Json([
    Json("append-prefix-state-v1"),
    Json(key),
    Json(items.map(i => parsed.items[i].id)),
  ]).stringify()
}

///|
fn list_prefix_originals_v4(parsed : ListV3Parsed) -> Map[Int64, Json] {
  let found : Map[Int64, Json] = Map([])
  for
    event in capture_source_array_v4(
      object_fields_unchecked_v3(parsed.normalized).at("observations"),
    ) {
    let e = object_fields_unchecked_v3(event)
    found[capture_source_seq_v4(e.at("seq"))] = event
  }
  found
}

///|
/// A per-key order is used only when the complete original prefix graph proves
/// every writer pair comparable. Sorting transaction identifiers is not evidence.
fn list_prefix_writer_order_v4(
  graph : EffectiveListGraphV4,
  key : String,
  writers : Array[String],
  extra : Array[(String, String, Json)],
  budget : ModelSourceBudgetV4,
) -> Array[String]? {
  let remaining = writers.copy()
  remaining.sort()
  let result : Array[String] = []
  while !remaining.is_empty() {
    let roots : Array[Int32] = []
    for i, writer in remaining {
      let mut incoming = false
      for edge in graph.base.edges {
        if !model_source_charge_v4(budget) {
          return None
        }
        if edge.kind == WW &&
          edge.key == Some(key) &&
          edge.to == writer &&
          remaining.contains(edge.from) {
          incoming = true
        }
      }
      for proof in extra {
        if !model_source_charge_v4(budget) {
          return None
        }
        if proof.1 == writer && remaining.contains(proof.0) {
          incoming = true
        }
      }
      if !incoming {
        roots.push(i)
      }
    }
    // More than one root would choose an unproved completion, not an observed order.
    if roots.length() != 1 {
      return None
    }
    result.push(remaining[roots[0]])
    ignore(remaining.remove(roots[0]))
  }
  Some(result)
}

///|
fn list_prefix_body_v4(
  history : HistoryV4,
  parsed : ListV3Parsed,
  graph : EffectiveListGraphV4,
  budget : ModelSourceBudgetV4,
  projection_gaps : Array[Json],
) -> ModelPointProgramV4? {
  if !parsed.findings.is_empty() {
    return None
  }
  let window = capture_window_v5(history, parsed.normalized, fn() {
    model_source_charge_v4(budget)
  })
  if !window.complete ||
    budget.limited ||
    window.unlocated ||
    !graph.index.journal_complete ||
    !graph.index.reads_complete ||
    !graph.item_order_validated ||
    !graph.quarantined.is_empty() {
    return None
  }
  if graph.index.reads.any(r => !r.usable) ||
    graph.index.gaps.any(g => {
      object_fields_unchecked_v3(g).get("code") !=
      Some(Json("missing-effective-transaction-order"))
    }) {
    return None
  }
  let extra : Map[String, Array[(String, String, Json)]] = Map([])
  for read in graph.index.reads {
    if !model_source_charge_v4(budget) {
      return None
    }
    let final_own = graph.index.groups
      .get_or_default(read.key, Map([]))
      .get_or_default(read.tx, [])
    if final_own.is_empty() ||
      read.own_at_read != final_own ||
      graph.index.outcomes.get(read.tx) != Some(Committed) {
      continue
    }
    let seen : Map[String, Bool] = Map([])
    for item in read.observed {
      if !model_source_charge_v4(budget) {
        return None
      }
      match parsed.items[item].tx {
        Some(writer) if writer != read.tx && !seen.contains(writer) => {
          seen[writer] = true
          let proofs = extra.get_or_default(read.key, [])
          proofs.push(
            (
              writer,
              read.tx,
              (
                {
                  "basis": "delivered-complete-final-own-prefix",
                  "derivedConstraint": true,
                  "readSeq": Json(read.seq.to_double()),
                  "writer": Json(writer),
                  "finalOwnWriter": Json(read.tx),
                  "observedItemIds": Json(
                    list_effective_item_ids_v4(parsed, read.observed),
                  ),
                  "ownFinalItemIds": Json(
                    list_effective_item_ids_v4(parsed, final_own),
                  ),
                  "ownFinalAppendSequences": Json(
                    final_own.map(i => Json(parsed.items[i].seq.to_double())),
                  ),
                } : Json),
            ),
          )
          extra[read.key] = proofs
        }
        _ => ()
      }
    }
  }
  for id, _ in graph.index.outcomes {
    if !window.closed.get_or_default(id, false) {
      return None
    }
  }
  let initial : Map[String, String] = Map([])
  let orders : Map[String, Array[String]] = Map([])
  let bases : Map[String, Map[String, Array[Int32]]] = Map([])
  let boundaries = model_raw_boundaries_v4(parsed.normalized)
  let boundary_map : Map[String, ModelTxBoundaryV4] = Map([])
  for boundary in boundaries {
    boundary_map[boundary.id] = boundary
  }
  let prefix_states : Map[String, Json] = Map([])
  let writer_proofs : Array[Json] = []
  for key, items in parsed.initial {
    if !model_source_charge_v4(budget) {
      return None
    }
    let first = list_prefix_version_v4(parsed, key, items)
    initial[key] = first
    prefix_states[first] = Json(
      items.map(i => {
        (
          {
            "id": Json(parsed.items[i].id),
            "value": Json(parsed.items[i].value),
          } : Json)
      }),
    )
    let versions = [first]
    let groups = graph.index.groups.get_or_default(key, Map([]))
    let ordered = match
      list_prefix_writer_order_v4(
        graph,
        key,
        groups.keys().collect(),
        extra.get_or_default(key, []),
        budget,
      ) {
      Some(v) => v
      None => return None
    }
    let prefix = items.copy()
    for writer in ordered {
      if !model_source_charge_v4(budget) {
        return None
      }
      let per_key = bases.get_or_default(writer, Map([]))
      per_key[key] = prefix.copy()
      bases[writer] = per_key
      let group = groups.at(writer)
      if group.is_empty() {
        return None
      }
      prefix.append(group)
      let terminal = list_prefix_version_v4(parsed, key, prefix)
      versions.push(terminal)
      prefix_states[terminal] = Json(
        prefix.map(i => {
          (
            {
              "id": Json(parsed.items[i].id),
              "value": Json(parsed.items[i].value),
            } : Json)
        }),
      )
      let source_proofs : Array[Json] = []
      for edge in graph.base.edges {
        if !model_source_charge_v4(budget) {
          return None
        }
        if edge.kind == WW && edge.key == Some(key) && edge.to == writer {
          source_proofs.append(graph.base.sources.get_or_default(edge, []))
        }
      }
      for proof in extra.get_or_default(key, []) {
        if !model_source_charge_v4(budget) {
          return None
        }
        if proof.1 == writer {
          source_proofs.push(proof.2)
        }
      }
      writer_proofs.push({
        "key": Json(key),
        "writer": Json(writer),
        "terminalVersion": Json(terminal),
        "originalAppendSequences": Json(
          group.map(i => Json(parsed.items[i].seq.to_double())),
        ),
        "orderSources": Json(source_proofs),
      })
    }
    orders[key] = versions
  }
  let originals = list_prefix_originals_v4(parsed)
  let revoked : Map[Int64, Int64] = Map([])
  for
    raw in capture_source_array_v4(
      object_fields_unchecked_v3(parsed.normalized).at("effects"),
    ) {
    if !model_source_charge_v4(budget) {
      return None
    }
    let e = object_fields_unchecked_v3(raw)
    match e.at("revertedBy") {
      Number(n, ..) =>
        revoked[capture_source_seq_v4(e.at("seq"))] = n.to_int64()
      _ => ()
    }
  }
  let base_witnesses : Array[Json] = []
  let components : Array[Json] = []
  let first_base : Map[String, Map[String, Json]] = Map([])
  let snapshot_diagnostics : Array[Json] = []
  for read in graph.index.reads {
    if !model_source_charge_v4(budget) {
      return None
    }
    if graph.index.outcomes.get(read.tx) != Some(Committed) {
      continue
    }
    let base : Array[Int32] = []
    for i in 0..<(read.observed.length() - read.own_at_read.length()) {
      base.push(read.observed[i])
    }
    let base_version = list_prefix_version_v4(parsed, read.key, base)
    if !orders.get_or_default(read.key, []).contains(base_version) {
      projection_gaps.push({
        "code": "unproved-external-prefix-terminal",
        "transaction": Json(read.tx),
        "key": Json(read.key),
        "originalRead": originals.at(read.seq),
        "baseItemIds": Json(list_effective_item_ids_v4(parsed, base)),
      })
      return None
    }
    let component : Json = {
      "transaction": Json(read.tx),
      "key": Json(read.key),
      "readSeq": Json(read.seq.to_double()),
      "originalRead": originals.at(read.seq),
      "derivedBaseVersion": Json(base_version),
      "baseItemIds": Json(list_effective_item_ids_v4(parsed, base)),
      "ownItemIds": Json(list_effective_item_ids_v4(parsed, read.own_at_read)),
      "inferenceRule": if read.own_at_read.is_empty() {
        Json("exact-original-list-read-value")
      } else {
        Json("complete-returned-prefix-minus-active-own-suffix/v2")
      },
      "syntheticSelectCreated": false,
    }
    components.push(component)
    let per_key = first_base.get_or_default(read.tx, Map([]))
    match per_key.get(read.key) {
      Some(first) if object_fields_unchecked_v3(first).at("derivedBaseVersion") !=
        Json(base_version) =>
        snapshot_diagnostics.push({
          "firstBaseObservation": first,
          "laterBaseObservation": component,
          "claim": "additional single-snapshot applicability; not a universal RC/RU rule",
        })
      None => {
        per_key[read.key] = component
        first_base[read.tx] = per_key
      }
      _ => ()
    }
    if read.own_at_read.is_empty() {
      continue
    }
    let mut basis = "delivered-own-read-external-prefix-component"
    if bases.get_or_default(read.tx, Map([])).contains(read.key) {
      basis = "complete-installed-writer-predecessor-prefix"
    } else if graph.index.groups.get_or_default(read.key, Map([])).is_empty() &&
      base == parsed.initial.get_or_default(read.key, []) {
      basis = "complete-window-no-installed-writer-for-key"
    } else {
      let first_append = parsed.items[read.own_at_read[0]].seq
      let mut nearest : EffectiveListReadV4? = None
      for earlier in graph.index.reads {
        if !model_source_charge_v4(budget) {
          return None
        }
        if earlier.tx == read.tx &&
          earlier.key == read.key &&
          earlier.own_at_read.is_empty() &&
          earlier.seq < first_append &&
          (nearest is None || earlier.seq > nearest.unwrap().seq) {
          nearest = Some(earlier)
        }
      }
      match nearest {
        Some(w) if w.usable && w.observed == base =>
          basis = "actual-delivered-external-base-read"
        _ => ()
      }
    }
    base_witnesses.push({
      "basis": Json(basis),
      "component": component,
      "inferenceIsNotCollectedFact": true,
    })
  }
  let programs : Array[ModelRegisterTxV4] = []
  for raw_program in parsed.programs {
    let own : Map[String, Array[Int32]] = Map([])
    let selected = bases.get_or_default(raw_program.id, Map([])).copy()
    // A revoked-only writer may reveal its base in a delivered own-prefix read.
    for read in graph.index.reads {
      if !model_source_charge_v4(budget) {
        return None
      }
      if read.tx != raw_program.id ||
        read.own_at_read.is_empty() ||
        selected.contains(read.key) {
        continue
      }
      if read.observed.length() < read.own_at_read.length() {
        return None
      }
      let base : Array[Int32] = []
      for i in 0..<(read.observed.length() - read.own_at_read.length()) {
        base.push(read.observed[i])
      }
      selected[read.key] = base
    }
    let trail : Array[(String, Int32)] = []
    let marks : Array[(String, Int32)] = []
    let ops : Array[ModelRegisterOpV4] = []
    for action in raw_program.actions {
      if !model_source_charge_v4(budget) {
        return None
      }
      match action {
        Append(key, item) => {
          let active = own.get_or_default(key, [])
          active.push(item)
          own[key] = active
          trail.push((key, item))
          let prefix = selected
            .get_or_default(key, parsed.initial.get_or_default(key, []))
            .copy()
          prefix.append(active)
          let state = list_prefix_version_v4(parsed, key, prefix)
          prefix_states[state] = Json(
            prefix.map(i => {
              (
                {
                  "id": Json(parsed.items[i].id),
                  "value": Json(parsed.items[i].value),
                } : Json)
            }),
          )
          let seq = parsed.items[item].seq
          ops.push({
            kind: Write,
            key,
            version: state,
            original: originals.at(seq),
            predecessor: None,
            revoked: revoked.contains(seq),
            revocation_seq: revoked.get(seq),
          })
        }
        ReadList(key, observed, seq) => {
          if observed.any(i => i < 0) {
            return None
          }
          let active = own.get_or_default(key, [])
          if !active.is_empty() {
            let expected = selected
              .get_or_default(key, parsed.initial.get_or_default(key, []))
              .copy()
            expected.append(active)
            if expected != observed {
              return None
            }
          } else if !orders
            .get_or_default(key, [])
            .contains(list_prefix_version_v4(parsed, key, observed)) {
            return None
          }
          let state = list_prefix_version_v4(parsed, key, observed)
          prefix_states[state] = Json(
            observed.map(i => {
              (
                {
                  "id": Json(parsed.items[i].id),
                  "value": Json(parsed.items[i].value),
                } : Json)
            }),
          )
          ops.push({
            kind: Read,
            key,
            version: state,
            original: originals.at(seq),
            predecessor: None,
            revoked: false,
            revocation_seq: None,
          })
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
            let start = marks[found].1
            while trail.length() > start {
              let (key, item) = trail.pop().unwrap()
              let active = own.get_or_default(key, [])
              if active.is_empty() || active[active.length() - 1] != item {
                return None
              }
              ignore(active.pop())
              own[key] = active
            }
          }
          let keep = if action is Undo(_) { found + 1 } else { found }
          while marks.length() > keep {
            ignore(marks.pop())
          }
        }
      }
    }
    programs.push({ boundary: boundary_map.at(raw_program.id), ops, })
  }
  let mapping = model_point_mapping_v4(
    initial,
    programs,
    orders,
    history.source_document,
  )
  let fields = object_fields_unchecked_v3(mapping)
  fields["definition"] = Json("append-list-prefix-state-register-projection/v2")
  fields["versionIdentifiersAreDerivedConstraints"] = Json(true)
  fields["originalItemIdentityAndValueStates"] = Json(prefix_states)
  fields["writerBlockProofs"] = Json(writer_proofs)
  fields["ownBaseWitnesses"] = Json(base_witnesses)
  fields["externalBaseComponents"] = Json(components)
  fields["singleSnapshotBaseCheck"] = {
    "status": if snapshot_diagnostics.is_empty() {
      Json("checked-compatible")
    } else {
      Json("unknown")
    },
    "diagnostics": Json(snapshot_diagnostics),
    "appliesTo": "hypothetical single-snapshot completion only; RC/RU use their own obligations",
  }
  fields["intermediateOwnReadsPreserved"] = Json(true)
  fields["sourceModel"] = Json("append-list-v1")
  Some({
    initial,
    transactions: programs,
    version_orders: orders,
    mapping: Json(fields),
  })
}

///|
pub fn project_list_prefix_v4(
  history : HistoryV4,
  max_checks~ : Int32 = 1000000,
) -> Result[ListPrefixProjectionV4, String] {
  if max_checks < 0 || max_checks > 1000000 {
    return Err("list prefix maxChecks must be in 0..1000000")
  }
  let parsed = match history.payload {
    ListSnapshot(parsed) => parsed
    _ => return Err("list prefix projection requires append-list-v1")
  }
  let graph = list_graph_effective_v4(parsed, max_checks~)
  Ok(project_list_prefix_core_v4(history, parsed, graph, max_checks))
}

///|
fn project_list_prefix_core_v4(
  history : HistoryV4,
  parsed : ListV3Parsed,
  graph : EffectiveListGraphV4,
  max_checks : Int32,
) -> ListPrefixProjectionV4 {
  let budget : ModelSourceBudgetV4 = {
    maximum: max_checks,
    checks: graph.checks,
    limited: graph.limited,
  }
  let projection_gaps : Array[Json] = []
  let candidate = list_prefix_body_v4(
    history, parsed, graph, budget, projection_gaps,
  )
  let projected = match candidate {
    Some(p) =>
      match model_projected_point_edges_v4(p, budget) {
        Some(edges) =>
          if model_list_component_edges_v4(p, edges, budget) {
            Some((p, edges))
          } else {
            None
          }
        None => None
      }
    None => None
  }
  let int_rule = match projected {
    Some(pair) => {
      let scalar = model_projected_internal_v4(pair.0, budget)
      let original = object_fields_unchecked_v3(pair.0.mapping).at(
        "singleSnapshotBaseCheck",
      )
      if scalar.status == "checked-compatible" &&
        object_fields_unchecked_v3(original).at("status") ==
        Json("checked-compatible") {
        scalar
      } else {
        model_rule_v4(
          "prefix-state-internal-applicability",
          "unknown",
          "additional original-list external-base and scalar overlay premises for single-snapshot completion",
          evidence={
            "scalarOverlay": model_rule_json_v4(scalar),
            "originalListBaseComponents": original,
          },
        )
      }
    }
    None =>
      model_rule_v4(
        "prefix-state-internal-applicability", "unknown", "no complete point-state projection",
      )
  }
  let program = if budget.limited {
    None
  } else {
    projected.map(pair => pair.0)
  }
  let edges = if budget.limited {
    []
  } else {
    projected.map(pair => pair.1).unwrap_or([])
  }
  let record : Json = {
    "format": "moontxnwitness-list-prefix-projection/v4",
    "schemaVersion": 4,
    "semanticContract": "append-list-prefix-state-register-projection/v2",
    "algorithm": "list-prefix-block-and-external-component-projection-2",
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
    "pointStateInternal": model_rule_json_v4(int_rule),
    "execution": model_mapping_counter_v4(
      budget, "list-prefix-projection-reference-checks-2",
    ),
    "nativeSourceGraph": list_graph_effective_v4_summary_json(graph),
    "theoremApplicabilityGaps": Json(projection_gaps),
    "scope": {
      "modelAcceptanceAsserted": false,
      "originalHistoryRewritten": false,
      "requiresCompleteWriterBlocks": true,
      "ambiguousOrIntermediateExternalPrefixes": "unknown; native source findings remain separate",
    },
  }
  { program, edges, int_rule, record, }
}

///|
pub fn list_prefix_projection_v4_json(result : ListPrefixProjectionV4) -> Json {
  v4_json_copy(result.record)
}

///|
pub fn verify_list_prefix_projection_v4(
  history : HistoryV4,
  supplied : Json,
  max_checks~ : Int32 = 1000000,
) -> Bool {
  match project_list_prefix_v4(history, max_checks~) {
    Ok(result) => supplied == result.record
    Err(_) => false
  }
}

///|
pub fn ListPrefixProjectionV4::is_projected(
  self : ListPrefixProjectionV4,
) -> Bool {
  self.program is Some(_)
}

///|
pub fn ListPrefixProjectionV4::dependency_edge_count(
  self : ListPrefixProjectionV4,
) -> Int32 {
  self.edges.length()
}

///|
fn model_list_projected_source_v4(
  history : HistoryV4,
  base : ModelSourceV4,
  native : EffectiveListGraphV4,
  maximum : Int32,
) -> ModelSourceV4 {
  let parsed = match history.payload {
    ListSnapshot(p) => p
    _ => return base
  }
  let projection = project_list_prefix_core_v4(history, parsed, native, maximum)
  let program = match projection.program {
    Some(p) => p
    None => {
      let diagnostic = object_fields_unchecked_v3(base.execution)
      diagnostic["prefixStateProjectionAttempt"] = {
        "status": "unknown",
        "theoremApplicabilityGaps": object_fields_unchecked_v3(
          projection.record,
        ).at("theoremApplicabilityGaps"),
        "execution": object_fields_unchecked_v3(projection.record).at(
          "execution",
        ),
        "nativeGraphCoverageUnchanged": true,
      }
      return { ..base, execution: Json(diagnostic), }
    }
  }
  if base.rules.at("identity-source-applicability").status !=
    "checked-compatible" ||
    base.rules.at("program-source-applicability").status != "checked-compatible" {
    return base
  }
  let rules = base.rules.copy()
  rules[projection.int_rule.id] = projection.int_rule
  for
    id in [
      "G1a", "G1b", "source-cyclic-versions", "source-identity-and-installation",
      "future-source-applicability",
    ] {
    if rules.at(id).status == "refuted" {
      return base
    }
    rules[id] = model_rule_v4(
      id,
      "checked-compatible",
      "complete original producer prefixes, final own blocks, immutable identities and effective journal are revalidated by the explicit list-prefix-state mapping",
      covered_by=["append-list-prefix-state-register-projection/v2"],
      evidence={
        "definition": "append-list-prefix-state-register-projection/v2",
        "sourceSha256": object_fields_unchecked_v3(projection.record).at(
          "sourceSha256",
        ),
        "evidenceLocation": "execution.source.projectionRecord",
        "checkedReadCount": Json(native.index.reads.length()),
        "unprovenWindowAccepted": false,
      },
    )
  }
  {
    ..base,
    edges: projection.edges,
    ww_complete: true,
    wr_complete: true,
    rw_complete: true,
    gaps: [],
    rules,
    profile: "captured-list-prefix-state/v2",
    point_program: Some(program),
    execution: {
      "counterContract": "model-list-prefix-source-and-graph-counters-2",
      "projection": object_fields_unchecked_v3(projection.record).at(
        "execution",
      ),
      "sharedNativeIndex": true,
      "projectionRecord": projection.record,
    },
  }
}
