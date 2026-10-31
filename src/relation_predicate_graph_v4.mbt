///|
/// Scope is part of identity even if item and predicate edges share endpoints.
pub struct RelationScopedEdgeV4 {
  priv dependency : Edge
  priv scope : String
} derive(Eq, Hash)

///|
pub extend RelationScopedEdgeV4 with Eq::{equal, not_equal}

///|
pub extend RelationScopedEdgeV4 with Hash::{hash, hash_combine}

///|
pub fn RelationScopedEdgeV4::scope(self : RelationScopedEdgeV4) -> String {
  self.scope
}

///|
pub fn RelationScopedEdgeV4::dependency(self : RelationScopedEdgeV4) -> Edge {
  self.dependency
}

///|
priv struct RelationPredicateBudgetV4 {
  max_evaluations : Int32
  max_candidates : Int32
  mut evaluations : Int32
  mut candidates : Int32
  mut limited : Bool
  mut reason : String
}

///|
priv struct RelationPredicateQueryV4 {
  tx : String
  table : Int32
  predicate : Array[RelationV3Predicate]
  rows : Array[RelationV3Row]
  seq : Int64
  query_index : Int32
  own : Map[Int32, Int32]
  mut complete : Bool
  domains : Array[Json]
}

///|
/// Persistent primary-key slots are the objects of this explicit adapter.
/// Original tuple incarnations are retained; their physical equivalence is not claimed.
pub struct RelationPredicateGraphV4 {
  priv index : RelationPointIndexV4
  priv input_contract : Json
  priv queries : Array[RelationPredicateQueryV4]
  priv scoped_edges : Array[RelationScopedEdgeV4]
  priv sources : Map[RelationScopedEdgeV4, Array[Json]]
  priv diagnostics : Array[Json]
  priv gaps : Array[Json]
  priv graph_checks : Int32
  priv graph_limit : Int32
  priv graph_limited : Bool
  priv predicate_budget : RelationPredicateBudgetV4
  priv complete : Bool
}

///|
pub fn RelationPredicateGraphV4::edges(
  self : RelationPredicateGraphV4,
) -> Array[RelationScopedEdgeV4] {
  self.scoped_edges.copy()
}

///|
fn relation_predicate_charge_v4(
  budget : RelationPredicateBudgetV4,
  candidate~ : Bool = false,
) -> Bool {
  if budget.limited {
    return false
  }
  if candidate {
    if budget.candidates >= budget.max_candidates {
      budget.limited = true
      budget.reason = "predicate-candidate-visit-budget"
      return false
    }
    budget.candidates += 1
  } else {
    if budget.evaluations >= budget.max_evaluations {
      budget.limited = true
      budget.reason = "predicate-evaluation-budget"
      return false
    }
    budget.evaluations += 1
  }
  true
}

///|
fn relation_predicate_gap_v4(
  gaps : Array[Json],
  code : String,
  index : RelationPointIndexV4,
  query : RelationPredicateQueryV4,
  key : Int32,
) -> Unit {
  query.complete = false
  gaps.push({
    "code": Json(code),
    "transaction": Json(query.tx),
    "readSeq": Json(query.seq.to_double()),
    "queryIndex": Json(query.query_index),
    "identity": relation_point_key_json_v4(index, key),
    "original": index.originals.get_or_default(query.seq, Json::null()),
  })
}

///|
fn relation_predicate_query_json_v4(
  index : RelationPointIndexV4,
  query : RelationPredicateQueryV4,
) -> Json {
  {
    "transaction": Json(query.tx),
    "relation": Json(index.parsed.tables[query.table].name),
    "readSeq": Json(query.seq.to_double()),
    "queryIndex": Json(query.query_index),
    "original": index.originals.get_or_default(query.seq, Json::null()),
  }
}

///|
fn relation_predicate_matches_v4(
  index : RelationPointIndexV4,
  query : RelationPredicateQueryV4,
  source : Int32,
  budget : RelationPredicateBudgetV4,
) -> Bool? {
  if !relation_predicate_charge_v4(budget) {
    return None
  }
  if source < 0 || index.parsed.sources[source].action == "delete" {
    return Some(false)
  }
  let row = index.parsed.sources[source].row
  for predicate in query.predicate {
    if !relation_predicate_charge_v4(budget) {
      return None
    }
    if !relation_v3_predicate_matches(predicate, row, index.keys) {
      return Some(false)
    }
  }
  Some(true)
}

///|
fn relation_predicate_queries_v4(
  index : RelationPointIndexV4,
  budget : RelationPointBudgetV4,
) -> Array[RelationPredicateQueryV4] {
  let result : Array[RelationPredicateQueryV4] = []
  for program in index.parsed.programs {
    let own : Map[Int32, Int32] = Map([])
    let trail : Array[(Int32, Int32)] = []
    let scopes : Array[(String, Int32)] = []
    let mut query_index = 0
    for action in program.actions {
      if !relation_point_charge_v4(budget) {
        return result
      }
      match action {
        WriteRow(source) => {
          let key = index.parsed.sources[source].row.key
          trail.push((key, own.get_or_default(key, -2)))
          own[key] = source
        }
        QueryRows(table, predicate, rows, seq) => {
          result.push({
            tx: program.id,
            table,
            predicate,
            rows,
            seq,
            query_index,
            own: own.copy(),
            complete: false,
            domains: [],
          })
          query_index += 1
        }
        Mark(instance) => scopes.push((instance, trail.length()))
        Undo(instance) | Release(instance) => {
          let mut found = -1
          for position, scope in scopes {
            if scope.0 == instance {
              found = position
            }
          }
          if found < 0 {
            return result
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
      }
    }
  }
  result
}

///|
fn relation_predicate_emit_v4(
  edges : Array[RelationScopedEdgeV4],
  sources : Map[RelationScopedEdgeV4, Array[Json]],
  graph_budget : RelationPointBudgetV4,
  dependency : Edge,
  scope : String,
  proof : Json,
) -> Bool {
  if dependency.from == dependency.to {
    return true
  }
  if !relation_point_charge_v4(graph_budget) {
    return false
  }
  let edge : RelationScopedEdgeV4 = { dependency, scope, }
  match sources.get(edge) {
    Some(proofs) => proofs.push(proof)
    None => {
      if edges.length() >= 50000 {
        graph_budget.limited = true
        graph_budget.reason = "relation-predicate-edge-budget-50000"
        return false
      }
      edges.push(edge)
      sources[edge] = [proof]
    }
  }
  true
}

///|
fn relation_predicate_edge_v4(
  index : RelationPointIndexV4,
  query : RelationPredicateQueryV4,
  key : Int32,
  source : Int32,
  selected : Int32,
  kind : Dependency,
  scope : String,
) -> Edge {
  let writer = index.parsed.sources[source].writer.unwrap()
  let version = index.parsed.sources[source].row.version
  let selected_version = if selected >= 0 {
    Some(index.parsed.sources[selected].row.version)
  } else {
    None
  }
  {
    from: if kind == WR {
      writer
    } else {
      query.tx
    },
    to: if kind == WR {
      query.tx
    } else {
      writer
    },
    kind,
    key: Some("relation-point-key-" + key.to_string()),
    from_op: if kind == WR {
      None
    } else {
      Some(query.query_index)
    },
    to_op: if kind == WR {
      Some(query.query_index)
    } else {
      None
    },
    from_version: if kind == WR {
      Some(version)
    } else {
      selected_version
    },
    to_version: if kind == WR {
      selected_version
    } else {
      Some(version)
    },
    reason: if scope == "predicate" {
      if kind == WR {
        "Every remaining selected slot version is at or after this installed membership toggle"
      } else {
        "Every remaining selected slot version precedes this installed membership toggle"
      }
    } else if kind == WR {
      "The actual returned row identifies this external installed-final item version"
    } else {
      "This is the next installed version of the actual external returned item; own successor stops"
    },
  }
}

///|
fn relation_predicate_source_v4(
  index : RelationPointIndexV4,
  source : Int32,
) -> Json {
  if source < 0 {
    {
      "kind": "initial-absent-key-slot",
      "writer": Json::null(),
      "version": Json::null(),
    }
  } else {
    relation_point_source_json_v4(index, source)
  }
}

///|
fn relation_predicate_query_valid_v4(
  index : RelationPointIndexV4,
  query : RelationPredicateQueryV4,
  gaps : Array[Json],
) -> Bool {
  if index.outcomes.get(query.tx) != Some(Committed) {
    query.complete = false
    return false
  }
  let raw = index.originals.get_or_default(query.seq, Json::null())
  if relation_classification_at_v4(raw, ["kind"]) != Json("row_read") ||
    relation_classification_at_v4(raw, ["complete"]) != Json(true) {
    relation_predicate_gap_v4(
      gaps, "predicate-result-not-completely-delivered", index, query, -1,
    )
    return false
  }
  if !relation_point_program_known_v4(index, query.tx, query.seq) {
    relation_predicate_gap_v4(
      gaps, "predicate-unproved-program-prefix", index, query, -1,
    )
    return false
  }
  let seen : Map[Int32, Bool] = Map([])
  for row in query.rows {
    if seen.contains(row.key) || index.keys[row.key].table != query.table {
      relation_predicate_gap_v4(
        gaps,
        "predicate-result-key-or-uniqueness-mismatch",
        index,
        query,
        row.key,
      )
      return false
    }
    seen[row.key] = true
  }
  query.complete = true
  true
}

///|
fn relation_predicate_positive_v4(
  index : RelationPointIndexV4,
  query : RelationPredicateQueryV4,
  key : Int32,
  row : RelationV3Row,
  gaps : Array[Json],
  diagnostics : Array[Json],
  predicate_budget : RelationPredicateBudgetV4,
) -> Int32 {
  let source_index = index.versions.get_or_default(row.version, -1)
  if source_index < 0 {
    relation_predicate_gap_v4(
      gaps, "predicate-returned-row-source-missing", index, query, key,
    )
    return -3
  }
  let source = index.parsed.sources[source_index]
  if source.row.key != key ||
    source.row.values != row.values ||
    source.action == "delete" ||
    source.seq >= query.seq {
    relation_predicate_gap_v4(
      gaps, "predicate-returned-row-source-mismatch", index, query, key,
    )
    return -3
  }
  if relation_predicate_matches_v4(index, query, source_index, predicate_budget) !=
    Some(true) {
    relation_predicate_gap_v4(
      gaps, "returned-row-does-not-prove-predicate-membership", index, query, key,
    )
    return -3
  }
  if query.own.contains(key) {
    if query.own.at(key) != source_index {
      relation_predicate_gap_v4(
        gaps, "predicate-own-delivered-row-state-mismatch", index, query, key,
      )
      return -3
    }
    return source_index
  }
  match source.writer {
    None => source_index
    Some(writer) => {
      let code = if writer == query.tx {
        "predicate-own-returned-row-not-active"
      } else if index.outcomes.get(writer) == Some(Aborted) ||
        !index.surviving[source_index] {
        "G1a"
      } else if index.outcomes.get(writer) != Some(Committed) {
        "predicate-returned-row-writer-outcome-unknown"
      } else if !index.final_set[source_index] {
        "G1b"
      } else {
        ""
      }
      if code != "" {
        relation_predicate_gap_v4(
          gaps, "predicate-returned-row-not-installed-final", index, query, key,
        )
        diagnostics.push({
          "code": Json(code),
          "observation": relation_predicate_query_json_v4(index, query),
          "identity": relation_point_key_json_v4(index, key),
          "actualReturnedSource": relation_point_source_json_v4(
            index, source_index,
          ),
          "basis": "actual returned row identity, not a guessed negative or predicate-write result",
        })
        -3
      } else {
        source_index
      }
    }
  }
}

///|
fn relation_predicate_closed_window_v4(index : RelationPointIndexV4) -> Bool {
  !index.window_unproven &&
  relation_classification_at_v4(index.parsed.normalized, [
    "coverage", "complete",
  ]) ==
  Json(true)
}

///|
fn relation_predicate_domain_v4(
  index : RelationPointIndexV4,
  query : RelationPredicateQueryV4,
  key : Int32,
  source_indices : Array[Int32],
  gaps : Array[Json],
  budget : RelationPredicateBudgetV4,
) -> (Array[Int32], Bool) {
  let candidates : Array[Int32] = []
  let closed = relation_predicate_closed_window_v4(index)
  if !closed {
    relation_predicate_gap_v4(
      gaps, "predicate-negative-window-not-closed", index, query, key,
    )
  }
  if relation_point_initial_v4(index, key) < 0 {
    if !relation_predicate_charge_v4(budget, candidate=true) {
      return (candidates, false)
    }
    candidates.push(-1)
  }
  for source in source_indices {
    if !relation_predicate_charge_v4(budget, candidate=true) {
      return (candidates, false)
    }
    match relation_predicate_matches_v4(index, query, source, budget) {
      Some(false) => candidates.push(source)
      Some(true) => ()
      None => return (candidates, false)
    }
  }
  if candidates.is_empty() {
    relation_predicate_gap_v4(
      gaps, "predicate-negative-has-no-observed-source", index, query, key,
    )
  }
  (candidates, closed)
}

///|
fn relation_predicate_toggles_v4(
  index : RelationPointIndexV4,
  query : RelationPredicateQueryV4,
  key : Int32,
  budget : RelationPredicateBudgetV4,
) -> Array[Int32]? {
  let initial = relation_point_initial_v4(index, key)
  let mut previous = match
    relation_predicate_matches_v4(index, query, initial, budget) {
    Some(value) => value
    None => return None
  }
  let toggles : Array[Int32] = []
  for source in index.chains[key] {
    let current = match
      relation_predicate_matches_v4(index, query, source, budget) {
      Some(value) => value
      None => return None
    }
    if previous != current {
      toggles.push(source)
    }
    previous = current
  }
  Some(toggles)
}

///|
fn relation_predicate_key_edges_v4(
  index : RelationPointIndexV4,
  query : RelationPredicateQueryV4,
  key : Int32,
  candidates : Array[Int32],
  positive : Bool,
  candidate_closed : Bool,
  edges : Array[RelationScopedEdgeV4],
  sources : Map[RelationScopedEdgeV4, Array[Json]],
  gaps : Array[Json],
  graph_budget : RelationPointBudgetV4,
  budget : RelationPredicateBudgetV4,
) -> Unit {
  let selected = if candidates.length() == 1 { candidates[0] } else { -1 }
  // Positive item WR requires no version order, but it does require the exact
  // externally returned installed-final row; own-at-delivery is not external.
  if positive && selected >= 0 && !query.own.contains(key) {
    match index.parsed.sources[selected].writer {
      Some(writer) if writer != query.tx => {
        let _ = relation_predicate_emit_v4(
          edges,
          sources,
          graph_budget,
          relation_predicate_edge_v4(
            index,
            query,
            key,
            selected,
            selected,
            WR,
            "item",
          ),
          "item",
          {
            "basis": "actual-returned-row-version",
            "query": relation_predicate_query_json_v4(index, query),
            "identity": relation_point_key_json_v4(index, key),
            "itemSource": relation_point_source_json_v4(index, selected),
          },
        )
      }
      _ => ()
    }
  }
  if candidates.is_empty() {
    return
  }
  if query.own.contains(key) {
    // The local overlay is a proved observation, including a later-rolled-back
    // write, but its placement in installed predicate version order is separate.
    relation_predicate_gap_v4(
      gaps, "predicate-own-view-needs-installed-order-proof", index, query, key,
    )
    return
  }
  if index.blocked.contains(key) || !index.ordered.contains(key) {
    relation_predicate_gap_v4(
      gaps, "predicate-version-order-not-complete", index, query, key,
    )
    return
  }
  let mut minimum = 2147483647
  let mut maximum = -1
  let mut ranked = true
  for source in candidates {
    let rank = if source < 0 { 0 } else { index.ranks[source] }
    if rank < 0 {
      ranked = false
    } else {
      minimum = if rank < minimum { rank } else { minimum }
      maximum = if rank > maximum { rank } else { maximum }
    }
  }
  if !ranked {
    relation_predicate_gap_v4(
      gaps, "predicate-candidate-source-not-installed", index, query, key,
    )
    return
  }
  if !candidate_closed {
    return
  }
  let toggles = match relation_predicate_toggles_v4(index, query, key, budget) {
    Some(value) => value
    None => return
  }
  // Different unobserved negative versions need not imply different predicate
  // dependencies. A membership toggle between two candidates is the boundary
  // that changes a WR/RW relation. Preserve every candidate; never pick a read.
  let predicate_equivalent = !toggles.any(source => {
    let rank = index.ranks[source]
    rank > minimum && rank <= maximum
  })
  if !predicate_equivalent {
    relation_predicate_gap_v4(
      gaps, "predicate-negative-source-ambiguous", index, query, key,
    )
  }
  let candidate_facts = candidates.map(source => {
    relation_predicate_source_v4(index, source)
  })
  let universal : Json = {
    "basis": "all-remaining-candidates; no selected negative version is asserted as observed",
    "query": relation_predicate_query_json_v4(index, query),
    "identity": relation_point_key_json_v4(index, key),
    "actualReturnedRow": Json(positive),
    "candidateDomainClosed": true,
    "candidatePositionsArePredicateEquivalent": Json(predicate_equivalent),
    "candidateSources": Json(candidate_facts),
    "minimumInstalledRank": Json(minimum),
    "maximumInstalledRank": Json(maximum),
  }
  for source in toggles {
    let rank = index.ranks[source]
    let kind = if rank <= minimum {
      WR
    } else if rank > maximum {
      RW
    } else {
      continue
    }
    // Shared evidence is private and immutable; only the public JSON exit
    // deep-copies it. Do not copy the entire delivered result for every edge.
    let fields = object_fields_unchecked_v3(universal).copy()
    let proof = Json::object(fields)
    fields["rule"] = Json(
      if kind == WR {
        "adya-2000-definition-3-all-prior-or-equal-toggles"
      } else {
        "adya-2000-definitions-4-5-any-later-toggle"
      },
    )
    fields["toggleRank"] = Json(rank)
    fields["installedToggle"] = relation_point_source_json_v4(index, source)
    let previous = if rank == 1 {
      relation_point_initial_v4(index, key)
    } else {
      index.chains[key][rank - 2]
    }
    fields["directPreviousSlotVersion"] = relation_predicate_source_v4(
      index, previous,
    )
    if !relation_predicate_emit_v4(
        edges,
        sources,
        graph_budget,
        relation_predicate_edge_v4(
          index, query, key, source, selected, kind, "predicate",
        ),
        "predicate",
        proof,
      ) {
      return
    }
  }
  if positive && selected >= 0 {
    let rank = index.ranks[selected]
    let chain = index.chains[key]
    if rank >= 0 && rank < chain.length() {
      let next = chain[rank]
      if index.parsed.sources[next].writer != Some(query.tx) {
        let _ = relation_predicate_emit_v4(
          edges,
          sources,
          graph_budget,
          relation_predicate_edge_v4(
            index,
            query,
            key,
            next,
            selected,
            RW,
            "item",
          ),
          "item",
          {
            "basis": "actual-external-returned-item-to-direct-installed-successor",
            "directSuccessor": true,
            "query": relation_predicate_query_json_v4(index, query),
            "identity": relation_point_key_json_v4(index, key),
            "itemSource": relation_point_source_json_v4(index, selected),
            "nextInstalledEffect": relation_point_source_json_v4(index, next),
          },
        )
      }
    }
  }
}

///|
fn relation_predicate_graph_parsed_v4(
  parsed : RelationV3Parsed,
  input_contract : Json,
  window_unproven : Bool,
  max_graph_checks : Int32,
  max_predicate_checks : Int32,
  max_candidate_visits : Int32,
) -> RelationPredicateGraphV4 {
  let graph_budget : RelationPointBudgetV4 = {
    maximum: max_graph_checks,
    checks: 0,
    limited: false,
    reason: "complete",
  }
  let budget : RelationPredicateBudgetV4 = {
    max_evaluations: max_predicate_checks,
    max_candidates: max_candidate_visits,
    evaluations: 0,
    candidates: 0,
    limited: false,
    reason: "complete",
  }
  let index = relation_point_empty_index_v4(parsed)
  index.window_unproven = window_unproven
  let edges : Array[RelationScopedEdgeV4] = []
  let sources : Map[RelationScopedEdgeV4, Array[Json]] = Map([])
  let diagnostics : Array[Json] = []
  let gaps : Array[Json] = []
  let mut queries : Array[RelationPredicateQueryV4] = []
  let valid = max_graph_checks >= 0 &&
    max_graph_checks <= 1000000 &&
    max_predicate_checks >= 0 &&
    max_predicate_checks <= 1000000 &&
    max_candidate_visits >= 0 &&
    max_candidate_visits <= 100000
  let capacity = parsed.programs.length() <= 128 && parsed.operations <= 4096
  if valid && capacity {
    relation_point_journal_v4(index, graph_budget)
    if index.journal_complete && !graph_budget.limited {
      relation_point_orders_v4(index, graph_budget)
    }
    if index.journal_complete && !graph_budget.limited {
      queries = relation_predicate_queries_v4(index, graph_budget)
    }
    // Raw delete/reinsert tuple identities cannot silently become a claim of
    // equivalence with physical entity-incarnation Adya histories.
    let incarnation_keys : Map[Int32, Bool] = Map([])
    let by_key : Map[Int32, Array[Int32]] = Map([])
    for position, source in parsed.sources {
      if !relation_point_charge_v4(graph_budget) {
        break
      }
      let items = by_key.get_or_default(source.row.key, [])
      items.push(position)
      by_key[source.row.key] = items
      if source.action == "insert" {
        match source.predecessor {
          Some(version) =>
            match index.versions.get(version) {
              Some(previous) if parsed.sources[previous].action == "delete" => {
                incarnation_keys[source.row.key] = true
                gaps.push({
                  "code": "physical-incarnation-equivalence-unproven",
                  "identity": relation_point_key_json_v4(index, source.row.key),
                  "original": index.originals.at(source.seq),
                  "adapter": "persistent-primary-key-slot",
                })
              }
              _ => ()
            }
          _ => ()
        }
      }
    }
    // Complete WW paths use final installed effects, never intermediate writes.
    for key, chain in index.chains {
      if index.blocked.contains(key) || incarnation_keys.contains(key) {
        continue
      }
      for rank in 1..<chain.length() {
        let previous = chain[rank - 1]
        let source = chain[rank]
        let path : Array[Json] = []
        let mut current = source
        while current != previous {
          if !relation_point_charge_v4(graph_budget) {
            break
          }
          path.push(relation_point_source_json_v4(index, current))
          current = index.versions.at(
            parsed.sources[current].predecessor.unwrap(),
          )
        }
        if graph_budget.limited {
          break
        }
        path.push(relation_point_source_json_v4(index, previous))
        if !relation_predicate_emit_v4(
            edges,
            sources,
            graph_budget,
            relation_point_edge_v4(
              index,
              parsed.sources[previous].writer.unwrap(),
              parsed.sources[source].writer.unwrap(),
              WW,
              key,
              Some(parsed.sources[previous].row.version),
              Some(parsed.sources[source].row.version),
            ),
            "item",
            {
              "basis": "adjacent-installed-final-slot-writes",
              "identity": relation_point_key_json_v4(index, key),
              "fromEffect": relation_point_source_json_v4(index, previous),
              "toEffect": relation_point_source_json_v4(index, source),
              "predecessorPath": Json(path),
            },
          ) {
          break
        }
      }
    }
    for query in queries {
      if !relation_point_charge_v4(graph_budget) {
        break
      }
      if !relation_predicate_query_valid_v4(index, query, gaps) {
        continue
      }
      let returned : Map[Int32, RelationV3Row] = Map([])
      for row in query.rows {
        returned[row.key] = row
      }
      for key, identity in index.keys {
        if identity.table != query.table {
          continue
        }
        if budget.limited || graph_budget.limited {
          break
        }
        if incarnation_keys.contains(key) {
          relation_predicate_gap_v4(
            gaps, "predicate-incarnation-source-unproven", index, query, key,
          )
          continue
        }
        let positive = returned.contains(key)
        let mut candidates : Array[Int32] = []
        let mut closed = true
        if positive {
          let selected = relation_predicate_positive_v4(
            index,
            query,
            key,
            returned.at(key),
            gaps,
            diagnostics,
            budget,
          )
          if selected == -3 {
            continue
          }
          candidates = [selected]
        } else if query.own.contains(key) {
          let selected = query.own.at(key)
          match relation_predicate_matches_v4(index, query, selected, budget) {
            Some(false) => candidates = [selected]
            Some(true) => {
              relation_predicate_gap_v4(
                gaps, "predicate-own-matching-row-not-delivered", index, query, key,
              )
              continue
            }
            None => closed = false
          }
        } else {
          let domain = relation_predicate_domain_v4(
            index,
            query,
            key,
            by_key.get_or_default(key, []),
            gaps,
            budget,
          )
          candidates = domain.0
          closed = domain.1
        }
        query.domains.push({
          "identity": relation_point_key_json_v4(index, key),
          "actualReturnedRow": Json(positive),
          "ownAtDelivery": Json(query.own.contains(key)),
          "closed": Json(closed),
          "candidateSources": Json(
            candidates.map(source => relation_predicate_source_v4(index, source)),
          ),
          "inferredConstraintOnly": Json(!positive && !query.own.contains(key)),
          "wildcardSource": Json(!closed),
        })
        relation_predicate_key_edges_v4(
          index, query, key, candidates, positive, closed, edges, sources, gaps,
          graph_budget, budget,
        )
      }
      if budget.limited || graph_budget.limited {
        query.complete = false
      }
    }
  } else {
    gaps.push({
      "code": Json(
        if valid {
          "relation-predicate-capacity-128-4096"
        } else {
          "invalid-relation-predicate-budget"
        },
      ),
    })
  }
  for tx, boundary in index.uncertain_after {
    gaps.push({
      "code": "predicate-program-prefix-unproven",
      "transaction": Json(tx),
      "firstUnknownSeq": Json(boundary.to_double()),
    })
  }
  for tx, status in index.outcomes {
    if status == Unknown {
      gaps.push({
        "code": "predicate-transaction-outcome-unconfirmed",
        "transaction": Json(tx),
      })
    }
  }
  if index.window_unproven {
    gaps.push({ "code": "predicate-input-window-unproven" })
  }
  for gap in index.gaps {
    gaps.push(gap)
  }
  if budget.limited || graph_budget.limited {
    gaps.push({
      "code": Json(
        if budget.limited {
          budget.reason
        } else {
          graph_budget.reason
        },
      ),
    })
  }
  let complete = valid &&
    capacity &&
    index.journal_complete &&
    index.orders_complete &&
    !graph_budget.limited &&
    !budget.limited &&
    gaps.is_empty() &&
    queries.all(query => {
      query.complete || index.outcomes.get(query.tx) != Some(Committed)
    })
  {
    index,
    input_contract,
    queries,
    scoped_edges: edges,
    sources,
    diagnostics,
    gaps,
    graph_checks: graph_budget.checks,
    graph_limit: max_graph_checks,
    graph_limited: graph_budget.limited,
    predicate_budget: budget,
    complete,
  }
}

///|
pub fn build_relation_predicate_graph_v4(
  history : HistoryV4,
  max_graph_checks~ : Int32 = 1000000,
  max_predicate_checks~ : Int32 = 1000000,
  max_candidate_visits~ : Int32 = 100000,
) -> Result[RelationPredicateGraphV4, String] {
  let metadata = object_fields_unchecked_v3(history.source_document).copy()
  let _ = metadata.remove("events")
  match history.payload {
    RelationSnapshot(parsed) =>
      Ok(
        relation_predicate_graph_parsed_v4(
          parsed,
          Json::object(metadata),
          relation_point_window_unproven_v4(history),
          max_graph_checks,
          max_predicate_checks,
          max_candidate_visits,
        ),
      )
    _ =>
      Err(
        "relation-predicate graph requires relation-set-v1 original capture facts",
      )
  }
}

///|
pub fn relation_predicate_graph_v4_json(
  result : RelationPredicateGraphV4,
) -> Json {
  let index = result.index
  let budget = result.predicate_budget
  let record : Json = {
    "format": "moontxnwitness-relation-predicate-graph/v4",
    "schemaVersion": 4,
    "semanticContract": "adya-2000-predicate-on-keyslots-v1",
    "algorithm": "relation-predicate-must-edges-3",
    "indexAlgorithm": "relation-point-local-effect-journal-4",
    "acceptsIsolationModels": false,
    "dataModel": "relation-set-v1",
    "objectAdapter": {
      "kind": "persistent-primary-key-slot",
      "deleteState": "Absent",
      "insertState": "Present",
      "physicalEntityIncarnationEquivalence": "not-claimed",
      "crossIncarnationUnproven": "explicit-source-gap",
    },
    "complete": Json(result.complete),
    "inputContract": result.input_contract,
    "observations": object_fields_unchecked_v3(index.parsed.normalized).at(
      "observations",
    ),
    "writeEffects": object_fields_unchecked_v3(index.parsed.normalized).at(
      "effects",
    ),
    "inferences": {
      "negativeSelection": "constraint candidates, never a fabricated observed negative version",
      "dependencyStrength": "must edge shared by every closed candidate interpretation",
      "versionOrderCompletion": false,
      "predicateReadRule": "Def3: all installed equal-or-prior local membership toggles",
      "predicateAntiRule": "Def4/5: any installed later local membership toggle",
      "itemAntiRule": "external actual returned item to next installed successor; own successor stops",
      "queries": Json(
        result.queries.map(query => {
          (
            {
              "observation": relation_predicate_query_json_v4(index, query),
              "complete": Json(query.complete),
              "candidateDomains": Json(query.domains),
            } : Json)
        }),
      ),
      "sourceAudit": Json(
        index.parsed.sources.mapi((source, _) => {
          relation_point_source_json_v4(index, source)
        }),
      ),
    },
    "scopedEdges": Json(
      result.scoped_edges.map(edge => {
        (
          {
            "scope": Json(edge.scope),
            "dependency": edge_json(edge.dependency),
            "sources": Json(result.sources.at(edge)),
          } : Json)
      }),
    ),
    "gaps": Json(result.gaps),
    "diagnostics": Json(result.diagnostics),
    "execution": {
      "counterContract": "relation-predicate-source-evaluation-candidates-2",
      "predicateEvaluationUnit": "one membership probe plus each evaluated typed AND term; short-circuit stops remaining terms",
      "candidateVisitUnit": "one known raw source examined or one possible initial-absent slot considered",
      "graphChecks": Json(result.graph_checks),
      "graphLimited": Json(result.graph_limited),
      "predicateEvaluations": Json(budget.evaluations),
      "candidateVisits": Json(budget.candidates),
      "predicateLimited": Json(budget.limited),
      "limits": {
        "transactions": 128,
        "operations": 4096,
        "edges": 50000,
        "graphChecks": Json(result.graph_limit),
        "predicateEvaluations": Json(budget.max_evaluations),
        "candidateVisits": Json(budget.max_candidates),
      },
    },
  }
  v4_json_copy(record)
}

///|
pub fn verify_relation_predicate_graph_v4(
  history : HistoryV4,
  supplied : Json,
  max_graph_checks~ : Int32 = 1000000,
  max_predicate_checks~ : Int32 = 1000000,
  max_candidate_visits~ : Int32 = 100000,
) -> Bool {
  match
    build_relation_predicate_graph_v4(
      history,
      max_graph_checks~,
      max_predicate_checks~,
      max_candidate_visits~,
    ) {
    Ok(result) => supplied == relation_predicate_graph_v4_json(result)
    Err(_) => false
  }
}
