///|
fn model_kind_from_dependency_v4(
  edge : Edge,
  predicate : Bool,
) -> ScopedDataKindV4 {
  match edge.kind {
    WW => if predicate { ScopedWWPredicate } else { ScopedWWItem }
    WR => if predicate { ScopedWRPredicate } else { ScopedWRItem }
    RW => if predicate { ScopedRWPredicate } else { ScopedRWItem }
    RT => ScopedWWItem // order edges are excluded by the caller
  }
}

///|
fn model_copy_base_edges_v4(
  base : ClassificationModelV3Graph,
) -> Array[ScopedDataEdgeInputV4] {
  let edges : Array[ScopedDataEdgeInputV4] = []
  for edge in base.edges {
    if edge.kind == RT {
      continue
    }
    edges.push({
      id: "source-edge-" + edges.length().to_string(),
      from: edge.from,
      to: edge.to,
      kind: model_kind_from_dependency_v4(edge, false),
      sources: base.sources.get_or_default(edge, []),
    })
  }
  edges
}

///|
fn model_raw_rule_v4(record : Json, name : String) -> ModelRuleV4 {
  let fields = object_fields_unchecked_v3(record)
  let findings = capture_source_array_v4(fields.at("findings")).filter(raw => {
    object_fields_unchecked_v3(raw).at("category") == Json(name)
  })
  let complete = object_fields_unchecked_v3(fields.at("coverage")).at(
      "complete",
    ) ==
    Json(true)
  model_rule_v4(
    name,
    model_source_status_v4(findings, complete),
    "fresh original-observation source helper; no supplied proof statuses accepted",
    evidence=record,
  )
}

///|
fn model_other_source_v4(
  history : HistoryV4,
  options : ModelOptionsV4,
) -> ModelSourceV4 {
  let rules : Map[String, ModelRuleV4] = Map([])
  let maximum = options.max_source_checks
  match history.payload {
    ListSnapshot(parsed) => {
      let result = list_graph_effective_v4(parsed, max_checks=maximum)
      let direct = inspect_capture_anomalies_v4(history, max_checks=maximum).record
      for name in ["G1a", "G1b"] {
        let raw_rule = model_raw_rule_v4(direct, name)
        rules[name] = if raw_rule.status != "refuted" && result.base.complete {
          model_rule_v4(
            name,
            "checked-compatible",
            "effective list validates every delivered read against its own-at-delivery overlay, committed producer identities and complete producer prefixes",
            evidence=list_graph_effective_v4_summary_json(result),
            covered_by=["effective-list-complete-source-and-prefix-validation"],
          )
        } else {
          raw_rule
        }
      }
      let int = inspect_internal_consistency_v4(history, max_checks=maximum).record
      let fields = object_fields_unchecked_v3(int)
      rules["internal"] = model_rule_v4(
        "internal",
        if fields.at("status") == Json("checked") {
          "checked-compatible"
        } else {
          capture_source_string_v4(fields.at("status"))
        },
        "fresh effective append overlay and external-prefix checker",
        evidence=int,
      )
      let normalization = object_fields_unchecked_v3(parsed.normalized)
      let normalized_gaps = capture_source_array_v4(
        object_fields_unchecked_v3(normalization.at("coverage")).at("gaps"),
      )
      let mut write_only_complete = result.index.journal_complete &&
        !result.limited &&
        normalized_gaps.all(gap => {
          object_fields_unchecked_v3(gap).at("code") ==
          Json("missing_item_source")
        })
      for _, writers in result.index.groups {
        if writers.length() > 1 {
          write_only_complete = false
        }
      }
      for program in parsed.programs {
        if program.status == Unknown &&
          program.actions.any(action => {
            match action {
              Append(_, _) => true
              _ => false
            }
          }) {
          write_only_complete = false
        }
      }
      let ww_complete = result.base.complete || write_only_complete
      let duplicates = parsed.findings.filter(f => {
        object_fields_unchecked_v3(f).at("code") == Json("duplicate_list_item")
      })
      rules["duplicate-elements"] = model_rule_v4(
        "duplicate-elements",
        model_source_status_v4(
          duplicates,
          result.index.journal_complete && !result.limited,
        ),
        "actual delivered duplicate append identity; repeated business values with distinct identities are allowed",
        evidence=Json(duplicates),
      )
      let identity_findings = parsed.findings.filter(f => {
        let code = object_fields_unchecked_v3(f).at("code")
        code == Json("item_value_mismatch") || code == Json("item_key_mismatch")
      })
      rules["identity-source-applicability"] = model_rule_v4(
        "identity-source-applicability",
        if identity_findings.is_empty() &&
          !result.limited &&
          !normalized_gaps.any(g => {
            object_fields_unchecked_v3(g).at("code") ==
            Json("missing_item_source")
          }) {
          "checked-compatible"
        } else {
          "unknown"
        },
        "observed item identities retain their original key and business value; absence of a producer is not an aborted-source proof",
        evidence=Json(identity_findings),
      )
      rules["program-source-applicability"] = model_list_program_rule_v4(result)
      let trivial_order = write_only_complete &&
        result.index.reads.all(read => read.observed.length() <= 1)
      rules["source-cyclic-versions"] = model_rule_v4(
        "source-cyclic-versions",
        if result.base.complete || trivial_order {
          "checked-compatible"
        } else {
          "unknown"
        },
        "complete effective order, or one writer per key with no multi-identity read-order constraints",
      )
      rules["source-identity-and-installation"] = model_rule_v4(
        "source-identity-and-installation",
        if ww_complete {
          "checked-compatible"
        } else {
          "unknown"
        },
        "validated item identities and closed append writer journal; with at most one committed writer per key there is no inter-transaction WW order to infer",
        evidence=list_graph_effective_v4_summary_json(result),
      )
      rules["future-source-applicability"] = model_rule_v4(
        "future-source-applicability",
        if result.base.complete {
          "checked-compatible"
        } else {
          "unknown"
        },
        "only full source-valid effective append graph discharges source applicability",
      )
      rules["write-input-applicability"] = model_rule_v4(
        "write-input-applicability", "checked-compatible", "append effects do not expose a read-modify-write input primitive",
      )
      let base : ModelSourceV4 = {
        nodes: parsed.programs.filter(p => p.status == Committed).map(p => p.id),
        edges: model_copy_base_edges_v4(result.base),
        boundaries: model_raw_boundaries_v4(parsed.normalized),
        rules,
        gaps: result.index.gaps.copy(),
        ww_complete,
        wr_complete: result.base.complete,
        rw_complete: result.base.complete,
        execution: list_graph_effective_v4_summary_json(result),
        profile: "effective-list-appends/v1",
        point_program: None,
      }
      if options.list_profile == ModelListPrefixStates {
        model_list_projected_source_v4(history, base, result, maximum)
      } else {
        base
      }
    }
    RelationSnapshot(parsed) => {
      let result = relation_graph_point_v4(
        parsed,
        max_checks=maximum,
        window_unproven=relation_point_window_unproven_v4(history),
      )
      let index = result.index
      let edges = model_copy_base_edges_v4(result.base)
      // WW is independently reconstructed from installed chains: bad reads do not
      // remove a complete write journal or turn RU into a read-source checker.
      let budget : ModelSourceBudgetV4 = { maximum, checks: 0, limited: false, }
      let normalized_gaps = capture_source_array_v4(
        object_fields_unchecked_v3(
          object_fields_unchecked_v3(parsed.normalized).at("coverage"),
        ).at("gaps"),
      )
      let mut ww_complete = index.journal_complete &&
        index.orders_complete &&
        !index.window_unproven &&
        index.uncertain_after.is_empty() &&
        !result.limited &&
        normalized_gaps.all(raw => {
          let code = object_fields_unchecked_v3(raw).at("code")
          code == Json("missing_row_source") || code == Json("incomplete_query")
        })
      for key, chain in index.chains {
        if !index.ordered.contains(key) {
          continue
        }
        for position in 1..<chain.length() {
          if !model_source_charge_v4(budget) {
            break
          }
          let a = parsed.sources[chain[position - 1]]
          let b = parsed.sources[chain[position]]
          match (a.writer, b.writer) {
            (Some(first), Some(last)) if first != last =>
              edges.push({
                id: "independent-write-edge-" + edges.length().to_string(),
                from: first,
                to: last,
                kind: ScopedWWItem,
                sources: [
                  relation_point_source_json_v4(index, chain[position - 1]),
                  relation_point_source_json_v4(index, chain[position]),
                  relation_point_key_json_v4(index, key),
                ],
              })
            _ => ()
          }
        }
      }
      if budget.limited {
        ww_complete = false
      }
      let mut complete = result.base.complete
      let mut gaps = index.gaps.copy()
      let mut profile = "relation-point-final-installed/v1"
      let mut execution = relation_point_graph_v4_json(result)
      if options.relation_profile == ModelRelationPredicateKeySlots {
        match
          build_relation_predicate_graph_v4(
            history,
            max_graph_checks=maximum,
            max_predicate_checks=maximum,
            max_candidate_visits=options.max_states,
          ) {
          Ok(predicate) => {
            // Keep only the independent, source-checked point/item graph for
            // fixed-Elle witnesses. Predicate edges remain in the attached
            // original-profile diagnostic until cross-definition mapping is proved.
            complete = predicate.complete
            gaps = predicate.gaps.copy()
            profile = "adya-2000-predicate-on-keyslots-v1"
            execution = relation_predicate_graph_v4_json(predicate)
            // This profile's all-prior/all-later predicate dependencies are not
            // silently reused as a complete fixed-Elle graph definition.
            complete = false
            gaps.push({
              "code": "fixed-elle-predicate-profile-equivalence-pending",
            })
          }
          Err(reason) => {
            complete = false
            gaps.push({
              "code": "predicate-adapter-failure",
              "reason": Json(reason),
            })
          }
        }
      }
      for name in ["G1a", "G1b", "INT"] {
        let proofs = index.direct.get_or_default(name, [])
        let id = if name == "INT" { "internal" } else { name }
        rules[id] = model_rule_v4(
          id,
          model_source_status_v4(proofs, result.base.complete),
          "fresh relation actual delivered row-read source; write predecessors are not reads",
          evidence=Json(proofs),
        )
      }
      rules["source-identity-and-installation"] = model_rule_v4(
        "source-identity-and-installation",
        if ww_complete {
          "checked-compatible"
        } else {
          "unknown"
        },
        "independent row-effect journal and complete installed-final chains",
        evidence=relation_point_graph_v4_json(result),
      )
      rules["future-source-applicability"] = model_rule_v4(
        "future-source-applicability",
        if complete {
          "checked-compatible"
        } else {
          "unknown"
        },
        "all delivered row sources must be applicable to the selected explicit relation profile",
      )
      let identity_findings = parsed.findings.filter(f => {
        let code = object_fields_unchecked_v3(f).at("code")
        code == Json("row_relation_mismatch") ||
        code == Json("row_key_mismatch") ||
        code == Json("row_value_mismatch") ||
        code == Json("duplicate_result_key") ||
        code == Json("row_predicate_mismatch") ||
        code == Json("read_from_tombstone")
      })
      rules["identity-source-applicability"] = model_rule_v4(
        "identity-source-applicability",
        if identity_findings.is_empty() &&
          !result.limited &&
          !normalized_gaps.any(g => {
            object_fields_unchecked_v3(g).at("code") ==
            Json("missing_row_source")
          }) {
          "checked-compatible"
        } else {
          "unknown"
        },
        "returned row identity, typed key, values and predicate membership must agree with the original source; source rollback is checked separately",
        evidence=Json(identity_findings),
      )
      rules["program-source-applicability"] = model_relation_program_rule_v4(
        result,
      )
      rules["source-cyclic-versions"] = model_rule_v4(
        "source-cyclic-versions",
        if ww_complete {
          "checked-compatible"
        } else {
          "unknown"
        },
        "closed installed row-version chains are strict and acyclic",
      )
      rules["duplicate-elements"] = model_rule_v4(
        "duplicate-elements", "checked-compatible", "relation point row identities are unique; this profile has no append-element multiplicity primitive",
      )
      rules["write-input-applicability"] = model_rule_v4(
        "write-input-applicability", "checked-compatible", "point row effects and predecessor provenance do not imply a predicate or read-modify-write observation",
      )
      {
        nodes: parsed.programs.filter(p => p.status == Committed).map(p => p.id),
        edges,
        boundaries: model_raw_boundaries_v4(parsed.normalized),
        rules,
        gaps,
        ww_complete,
        wr_complete: complete,
        rw_complete: complete,
        execution,
        profile,
        point_program: None,
      }
    }
    _ => model_register_source_v4(history, maximum)
  }
}

///|
/// A missing program segment can change the supposedly final write overlay.
/// Such derived edges cannot become reliable model witnesses merely because
/// their former helper retained a partial source index for diagnostics.
fn model_source_applicability_v4(
  history : HistoryV4,
  source : ModelSourceV4,
) -> ModelSourceV4 {
  if history.source_format == "declared-history/v1" {
    return source
  }
  let root = object_fields_unchecked_v3(history.source_document)
  let bad : Map[String, Bool] = Map([])
  let mut unlocated = !capture_source_array_v4(root.at("gaps")).is_empty() ||
    object_fields_unchecked_v3(root.at("scope")).at("exclusiveWriters") !=
    Json(true)
  for event in capture_source_array_v4(root.at("events")) {
    let e = object_fields_unchecked_v3(event)
    let kind = e.at("kind")
    if kind == Json("snapshot") && e.at("consistent") != Json(true) {
      unlocated = true
    }
    if kind == Json("statement") ||
      kind == Json("condition") ||
      kind == Json("rows") {
      match e.at("tx") {
        String(tx) => bad[tx] = true
        _ => unlocated = true
      }
    }
  }
  if !unlocated && bad.is_empty() {
    return source
  }
  let safe = source.edges.filter(edge => {
    !unlocated && !bad.contains(edge.from) && !bad.contains(edge.to)
  })
  let gaps = source.gaps.copy()
  gaps.push({
    "code": "model-source-graph-applicability-barrier",
    "unlocated": Json(unlocated),
    "transactions": Json(bad.keys().collect()),
    "quarantinedEdges": Json(source.edges.length() - safe.length()),
  })
  let rules = source.rules.copy()
  rules["source-identity-and-installation"] = model_rule_v4(
    "source-identity-and-installation",
    "unknown",
    "incomplete source window or program may change installed-final effects; known direct aborted/internal read evidence is evaluated independently",
    evidence=Json(gaps),
  )
  {
    ..source,
    edges: safe,
    rules,
    gaps,
    ww_complete: false,
    wr_complete: false,
    rw_complete: false,
  }
}
