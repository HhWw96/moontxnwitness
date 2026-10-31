///|
pub struct RelationClassificationV4 {
  priv status : String
  priv record : Json
}

///|
pub fn RelationClassificationV4::status(
  self : RelationClassificationV4,
) -> String {
  self.status
}

///|
fn relation_classification_categories_v4() -> Array[String] {
  ["G0", "G1a", "G1b", "G1c", "G2-item", "INT"]
}

///|
fn relation_classification_at_v4(value : Json, path : Array[String]) -> Json {
  let mut current = value
  for key in path {
    current = match current {
      Object(fields) => fields.get_or_default(key, Json::null())
      _ => Json::null()
    }
  }
  current
}

///|
fn relation_classification_implications_v4(specific : String) -> Array[String] {
  match specific {
    "G1a" => ["G1a", "G1"]
    "G1b" => ["G1b", "G1"]
    "INT" => ["INT"]
    _ => classification_v3_implications(specific)
  }
}

///|
/// Lifecycle and read-source validation has its own graph construction budget.
/// A later graph edge timeout is not a source timeout for these direct rules.
fn relation_classification_direct_complete_v4(
  graph : RelationPointGraphV4,
) -> Bool {
  let index = graph.index
  if !index.journal_complete || !index.reads_complete {
    return false
  }
  if relation_classification_at_v4(index.parsed.normalized, [
      "coverage", "complete",
    ]) !=
    Json(true) {
    return false
  }
  index.reads.all(read => {
    index.outcomes.get(read.tx) != Some(Committed) ||
    [
      "complete-own-at-delivery", "complete-version-bound-point-read", "unique-initial-point-absence",
      "unique-final-tombstone-absence", "aborted-or-revoked-row-read-source", "intermediate-row-read-source",
      "own-row-source-not-active-at-read",
    ].contains(read.reason)
  })
}

///|
/// Rebind derived effect audit fields after construction. Original observations
/// and source fact identities are retained without changing capture facts.
fn relation_classification_direct_proof_v4(
  graph : RelationPointGraphV4,
  proof : Json,
) -> Json {
  let result = v4_json_copy(proof)
  let fields = object_fields_unchecked_v3(result)
  for name in ["source", "expectedLocalEffect"] {
    match relation_classification_at_v4(proof, [name, "fact", "version"]) {
      String(version) =>
        match graph.index.versions.get(version) {
          Some(source) =>
            fields[name] = relation_point_source_json_v4(graph.index, source)
          _ => ()
        }
      _ => ()
    }
  }
  result
}

///|
fn relation_classification_cycle_witness_v4(
  graph : RelationPointGraphV4,
  requested : String,
  cycle : Array[Edge],
) -> Json {
  let specific = if cycle.all(edge => edge.kind == WW) {
    "G0"
  } else if cycle.any(edge => edge.kind == RW) {
    "G2-item"
  } else {
    "G1c"
  }
  {
    "kind": "source-checked-relation-point-category-cycle",
    "requestedCategory": Json(requested),
    "specificCategory": Json(specific),
    "dependencyScope": "item",
    "containsPredicateEdges": false,
    "cycleRule": Json(
      match requested {
        "G0" => "WW-only closed simple cycle"
        "G1c" => "WW/WR closed simple cycle"
        _ => "closed simple cycle containing at least one item RW"
      },
    ),
    "edges": Json(
      cycle.map(edge => {
        let proofs = graph.base.sources.get_or_default(edge, [])
        let observations = proofs.map(proof => {
          let from = match edge.kind {
            WW =>
              relation_classification_at_v4(proof, [
                "fromEffect", "fact", "sourceSeq",
              ])
            WR =>
              relation_classification_at_v4(proof, [
                "readSource", "source", "fact", "sourceSeq",
              ])
            _ => relation_classification_at_v4(proof, ["readSeq"])
          }
          let to = match edge.kind {
            WW =>
              relation_classification_at_v4(proof, [
                "toEffect", "fact", "sourceSeq",
              ])
            WR => relation_classification_at_v4(proof, ["readSeq"])
            _ =>
              relation_classification_at_v4(proof, [
                "laterEffect", "fact", "sourceSeq",
              ])
          }
          (
            {
              "fromObservationSeq": from,
              "toObservationSeq": to,
              "queryIndex": relation_classification_at_v4(proof, ["queryIndex"]),
            } : Json)
        })
        (
          {
            "edge": edge_json(edge),
            "identity": if proofs.is_empty() {
              Json::null()
            } else {
              relation_classification_at_v4(proofs[0], ["identity"])
            },
            "observationLinks": Json(observations),
            "sources": Json(proofs),
          } : Json)
      }),
    ),
    "minimality": "category-specific simple cycle; no global shortest-cycle claim",
    "sourceScope": "original relation row versions, typed primary keys, lifecycle effects and delivered primary-key query observations; no database authentication",
  }
}

///|
fn relation_classification_inferences_v4(graph : RelationPointGraphV4) -> Json {
  let index = graph.index
  {
    "graphAlgorithm": "relation-point-row-graph-5",
    "indexAlgorithm": "relation-point-local-effect-journal-4",
    "internalConsistencyRule": "delivered-point-read-versus-known-nearest-read-or-own-write; write-source-mismatch-is-not-a-read/v1",
    "itemAntiDependencyRule": "external-read-to-next-installed-row-version; never skip own successor/v1",
    "versionOrderCompletion": false,
    "predicateDependencyClassification": false,
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
    "readSourceResolutions": Json(
      index.reads.map(read => {
        (
          {
            "transaction": Json(read.tx),
            "identity": relation_point_key_json_v4(index, read.key),
            "readSeq": Json(read.seq.to_double()),
            "queryIndex": Json(read.query_index),
            "usable": Json(read.usable),
            "reason": Json(read.reason),
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
          } : Json)
      }),
    ),
    "sourceAudit": Json(
      index.parsed.sources.mapi((source, _) => {
        relation_point_source_json_v4(index, source)
      }),
    ),
    "diagnostics": Json(index.diagnostics),
  }
}

///|
fn relation_classification_record_v4(
  history : HistoryV4,
  graph : RelationPointGraphV4?,
  status : String,
  categories : Array[String],
  rules : Map[String, Json],
  implied : Array[String],
  max_states : Int32,
  max_edge_checks : Int32,
  max_graph_checks : Int32,
) -> RelationClassificationV4 {
  let record : Json = {
    "format": "moontxnwitness-relation-classification/v4",
    "schemaVersion": 4,
    "semanticContract": "moontxnwitness-relation-point-category-classification-v4-5",
    "algorithm": "v4-relation-point-category-5",
    "dataModel": Json(v4_model_name(history.data_model)),
    "observations": {
      "sourceFormat": Json(history.source_format),
      "authenticityVerified": false,
      "document": history.source_document,
    },
    "writeEffects": match graph {
      Some(g) =>
        relation_classification_at_v4(g.index.parsed.normalized, ["effects"])
      None => Json::null()
    },
    "inferences": match graph {
      Some(g) => relation_classification_inferences_v4(g)
      None => Json::null()
    },
    "judgment": {
      "status": Json(status),
      "acceptsIsolationModels": false,
      "scope": "requested single-primary-key-equality relation row and item-dependency categories only; no predicate classification or complete isolation-model acceptance",
      "dependencyGraphComplete": Json(
        match graph {
          Some(g) => g.base.complete
          None => false
        },
      ),
      "dependencyGraphReason": Json(
        match graph {
          Some(g) => g.base.reason
          None =>
            if status == "invalid" {
              "invalid-options"
            } else {
              "requires-relation-set-v1"
            }
        },
      ),
      "dependencies": Json(
        match graph {
          Some(g) => g.base.edges.map(edge_json)
          None => []
        },
      ),
      "sourceOrOrderGaps": Json(
        match graph {
          Some(g) => g.index.gaps
          None => []
        },
      ),
      "rules": Json::object(rules),
      "impliedAnomalies": Json(implied),
    },
    "execution": {
      "counterContract": "v4-relation-point-category-counters-5",
      "categories": Json(categories.copy()),
      "graphCounterContract": "relation-point-construction-checks-5",
      "graphChecks": Json(
        match graph {
          Some(g) => g.checks
          None => 0
        },
      ),
      "graphLimited": Json(
        match graph {
          Some(g) => g.limited
          None => false
        },
      ),
      "sourceJournalComplete": Json(
        match graph {
          Some(g) => g.index.journal_complete
          None => false
        },
      ),
      "readSourceChecksComplete": Json(
        match graph {
          Some(g) => g.index.reads_complete
          None => false
        },
      ),
      "directProofAccounting": "direct proofs are verified within graphChecks and are not charged again to cycle search budgets",
      "limits": {
        "transactions": 128,
        "operations": 4096,
        "edges": 50000,
        "graphChecks": Json(max_graph_checks),
        "statesPerCycleCategory": Json(max_states),
        "edgeChecksPerCycleCategory": Json(max_edge_checks),
      },
    },
  }
  { status, record, }
}

///|
/// Independent relation category entry. It does not change classify_v4 defaults.
pub fn classify_relation_point_v4(
  history : HistoryV4,
  categories~ : Array[String] = ["G0", "G1a", "G1b", "G1c", "G2-item", "INT"],
  max_states~ : Int32 = 100000,
  max_edge_checks~ : Int32 = 1000000,
  max_graph_checks~ : Int32 = 1000000,
) -> RelationClassificationV4 {
  let categories = categories.copy()
  let seen : Map[String, Bool] = Map([])
  let valid = !categories.is_empty() &&
    categories.all(category => {
      if !relation_classification_categories_v4().contains(category) ||
        seen.contains(category) {
        false
      } else {
        seen[category] = true
        true
      }
    }) &&
    max_states >= 0 &&
    max_states <= 100000 &&
    max_edge_checks >= 0 &&
    max_edge_checks <= 1000000 &&
    max_graph_checks >= 0 &&
    max_graph_checks <= 1000000
  if !valid {
    return relation_classification_record_v4(
      history,
      None,
      "invalid",
      categories,
      Map([]),
      [],
      max_states,
      max_edge_checks,
      max_graph_checks,
    )
  }
  let graph = match history.payload {
    RelationSnapshot(parsed) =>
      relation_graph_point_v4(
        parsed,
        max_checks=max_graph_checks,
        window_unproven=relation_point_window_unproven_v4(history),
      )
    _ => {
      let rules : Map[String, Json] = Map([])
      for category in categories {
        rules[category] = {
          "status": "unsupported",
          "reason": "requires-relation-set-v1",
          "states": 0,
          "edgeChecks": 0,
          "directProofs": 0,
          "evidence": Json::null(),
        }
      }
      return relation_classification_record_v4(
        history,
        None,
        "unsupported",
        categories,
        rules,
        [],
        max_states,
        max_edge_checks,
        max_graph_checks,
      )
    }
  }
  let adjacency = adjacency(graph.base.transactions, graph.base.edges)
  let direct_complete = relation_classification_direct_complete_v4(graph)
  let rules : Map[String, Json] = Map([])
  let implied : Array[String] = []
  let mut status = "checked-compatible"
  for category in categories {
    let budget : ClassificationV3Budget = {
      max_states,
      max_edge_checks,
      states: 0,
      edge_checks: 0,
      limited: false,
      reason: "complete",
    }
    let direct_rule = ["G1a", "G1b", "INT"].contains(category)
    let proofs = if direct_rule {
      graph.index.direct.get_or_default(category, [])
    } else {
      []
    }
    let cycle = if direct_rule {
      []
    } else {
      classification_v3_cycle(
        graph.base.transactions,
        graph.base.edges,
        adjacency,
        category,
        budget,
      )
    }
    let refuted = !proofs.is_empty() || !cycle.is_empty()
    let complete = if direct_rule {
      direct_complete
    } else {
      graph.base.complete && !budget.limited
    }
    let rule_status = if refuted {
      "refuted"
    } else if complete {
      "checked-compatible"
    } else {
      "unknown"
    }
    let reason = if refuted {
      if direct_rule {
        "source-bound-direct-proof"
      } else {
        "source-bound-category-cycle"
      }
    } else if direct_rule {
      if complete {
        "complete-direct-source-checks"
      } else {
        "required-direct-source-checks-incomplete"
      }
    } else if budget.limited {
      budget.reason
    } else {
      graph.base.reason
    }
    let specific = if direct_rule {
      category
    } else if cycle.all(edge => edge.kind == WW) {
      "G0"
    } else if cycle.any(edge => edge.kind == RW) {
      "G2-item"
    } else {
      "G1c"
    }
    if refuted {
      status = "refuted"
      for label in relation_classification_implications_v4(specific) {
        if !implied.contains(label) {
          implied.push(label)
        }
      }
    } else if rule_status == "unknown" && status != "refuted" {
      status = "inconclusive"
    }
    rules[category] = {
      "status": Json(rule_status),
      "reason": Json(reason),
      "states": Json(budget.states),
      "edgeChecks": Json(budget.edge_checks),
      "directProofs": Json(proofs.length()),
      "sourceChecksComplete": Json(
        if direct_rule {
          direct_complete
        } else {
          graph.base.complete
        },
      ),
      "evidence": if !proofs.is_empty() {
        (
          {
            "kind": "source-checked-relation-point-direct-witness",
            "requestedCategory": Json(category),
            "specificCategory": Json(category),
            "proofs": Json(
              proofs.map(proof => {
                relation_classification_direct_proof_v4(graph, proof)
              }),
            ),
            "sourceScope": "original relation effects and delivered point-query observations; no database authentication",
          } : Json)
      } else if !cycle.is_empty() {
        relation_classification_cycle_witness_v4(graph, category, cycle)
      } else {
        Json::null()
      },
    }
  }
  relation_classification_record_v4(
    history,
    Some(graph),
    status,
    categories,
    rules,
    implied,
    max_states,
    max_edge_checks,
    max_graph_checks,
  )
}

///|
pub fn relation_classification_v4_json(
  result : RelationClassificationV4,
) -> Json {
  v4_json_copy(result.record)
}

///|
pub fn render_relation_classification_v4(
  result : RelationClassificationV4,
) -> String {
  result.record.stringify(indent=2)
}

///|
pub fn verify_relation_classification_v4(
  history : HistoryV4,
  supplied : Json,
  categories~ : Array[String] = ["G0", "G1a", "G1b", "G1c", "G2-item", "INT"],
  max_states~ : Int32 = 100000,
  max_edge_checks~ : Int32 = 1000000,
  max_graph_checks~ : Int32 = 1000000,
) -> Bool {
  supplied ==
  classify_relation_point_v4(
    history,
    categories~,
    max_states~,
    max_edge_checks~,
    max_graph_checks~,
  ).record
}
