///|
fn model_observation_premises_v4(
  source : ModelSourceV4,
  full_int : Bool,
) -> Bool {
  source.point_program is Some(_) &&
  (
    source.profile == "declared-register-full-program/v1" ||
    source.profile == "captured-register-full-program/v2" ||
    source.profile == "captured-list-prefix-state/v2"
  ) &&
  source.boundaries.all(tx => tx.status != Unknown) &&
  source.ww_complete &&
  source.wr_complete &&
  source.rw_complete &&
  [
    "source-identity-and-installation", "identity-source-applicability", "program-source-applicability",
    "G1a", "G1b", "future-source-applicability", "write-input-applicability",
  ].all(id => source.rules.at(id).status == "checked-compatible") &&
  (
    !full_int ||
    (
      source.rules.at("internal").status == "checked-compatible" &&
      (
        source.profile != "captured-list-prefix-state/v2" ||
        source.rules.at("prefix-state-internal-applicability").status ==
        "checked-compatible"
      )
    )
  )
}

///|
fn model_completion_execution_v4(budget : ScopedSearchBudgetV4) -> Json {
  {
    "counterContract": "model-completion-topology-and-visibility-counters-1",
    "states": Json(budget.states),
    "edgeChecks": Json(budget.edge_checks),
    "limited": Json(budget.limited),
    "limits": {
      "states": Json(budget.max_states),
      "edgeChecks": Json(budget.max_edges),
    },
  }
}

///|
/// A constructive certificate, not a check of an arbitrary supplied snapshot graph.
/// X=I+context, CO is an Ext(X,A) topological total order and VIS=CO?;X.
fn model_si_completion_v4(
  history : HistoryV4,
  source : ModelSourceV4,
  orders : ModelOrdersV4,
  context : ScopedOrderContextV4,
  options : ModelOptionsV4,
  graph_rule : ModelRuleV4,
) -> ModelRuleV4 {
  let id = "completion/Ext/" + scoped_context_name_v4(context)
  if options.completion_policy != ModelObservationOnlyCompletion ||
    !model_observation_premises_v4(source, true) ||
    graph_rule.status != "checked-compatible" {
    return model_rule_v4(
      id,
      "pending",
      "requires transaction-observation scope without given logical snapshots, full INT, unique final read sources, all external reads and complete installed writer orders",
      evidence={
        "sourceProfile": Json(source.profile),
        "sourcePremisesSatisfied": Json(
          model_observation_premises_v4(source, true),
        ),
        "extensionStatus": Json(graph_rule.status),
        "givenSnapshotAssertionsSupported": false,
      },
    )
  }
  let graph = match
    scoped_dependency_graph_v4(
      source.nodes,
      source.edges,
      order_edges=orders.edges,
      data_complete=true,
      process_complete=orders.process_complete,
      realtime_complete=orders.realtime_complete,
    ) {
    Ok(g) => g
    Err(reason) => return model_rule_v4(id, "unknown", reason)
  }
  if !scoped_context_complete_v4(graph, context) {
    return model_rule_v4(
      id, "unknown", "necessary process/realtime source universe is incomplete",
    )
  }
  let budget : ScopedSearchBudgetV4 = {
    max_states: options.max_states,
    max_edges: options.max_edge_checks,
    states: 0,
    edge_checks: 0,
    limited: false,
    reason: "complete",
  }
  let arcs : Array[ScopedExtensionArcV4] = []
  let adjacency : Array[Array[Int32]] = Array::makei(graph.nodes.length(), _ => {
    []
  })
  let pairs : Map[(Int32, Int32), Int32] = Map([])
  let incoming : Array[Array[Int32]] = Array::makei(graph.nodes.length(), _ => {
    []
  })
  for position, edge in graph.edges {
    if !scoped_charge_edge_v4(budget) {
      break
    }
    if !(scoped_is_ww_v4(edge) ||
      scoped_is_wr_v4(edge) ||
      scoped_order_allowed_v4(edge, context)) {
      continue
    }
    incoming[edge.to].push(edge.from)
    let _ = scoped_extension_add_v4(
      arcs,
      adjacency,
      pairs,
      edge.from,
      edge.to,
      [position],
    )
    for next in graph.adjacency[edge.to] {
      if !scoped_charge_edge_v4(budget) {
        break
      }
      let target = graph.edges[next]
      if !scoped_is_rw_v4(target) {
        continue
      }
      let _ = scoped_extension_add_v4(
        arcs,
        adjacency,
        pairs,
        edge.from,
        target.to,
        [position, next],
      )
    }
  }
  let indegree = FixedArray::make(graph.nodes.length(), 0)
  for arc in arcs {
    if !scoped_charge_edge_v4(budget) {
      break
    }
    indegree[arc.to] += 1
  }
  let queue : Array[Int32] = []
  for node in 0..<graph.nodes.length() {
    if indegree[node] == 0 {
      queue.push(node)
    }
  }
  let order : Array[Int32] = []
  let mut cursor = 0
  while cursor < queue.length() && !budget.limited {
    if !scoped_charge_state_v4(budget) {
      break
    }
    let node = queue[cursor]
    cursor += 1
    order.push(node)
    for position in adjacency[node] {
      if !scoped_charge_edge_v4(budget) {
        break
      }
      let arc = arcs[position]
      indegree[arc.to] -= 1
      if indegree[arc.to] == 0 {
        queue.push(arc.to)
      }
    }
  }
  let ranks = FixedArray::make(graph.nodes.length(), -1)
  for i, node in order {
    ranks[node] = i
  }
  let prefix = FixedArray::make(graph.nodes.length(), -1)
  let visibility : Array[Json] = []
  let mut valid = order.length() == graph.nodes.length() && !budget.limited
  if valid {
    for node in 0..<graph.nodes.length() {
      if !scoped_charge_state_v4(budget) {
        break
      }
      let mut maximum = -1
      for previous in incoming[node] {
        if !scoped_charge_edge_v4(budget) {
          break
        }
        if ranks[previous] > maximum {
          maximum = ranks[previous]
        }
      }
      prefix[node] = maximum
      if maximum >= ranks[node] {
        valid = false
      }
      let visible : Array[String] = []
      for i in 0..<(maximum + 1) {
        if !scoped_charge_edge_v4(budget) {
          break
        }
        visible.push(graph.nodes[order[i]])
      }
      visibility.push({
        "transaction": Json(graph.nodes[node]),
        "commitRank": Json(ranks[node]),
        "visiblePrefixLength": Json(maximum + 1),
        "visibleTransactions": Json(visible),
      })
    }
    for edge in graph.edges {
      if !scoped_charge_edge_v4(budget) {
        break
      }
      if scoped_is_wr_v4(edge) && ranks[edge.from] > prefix[edge.to] {
        valid = false
      }
      if scoped_is_rw_v4(edge) && ranks[edge.to] <= prefix[edge.from] {
        valid = false
      }
      if scoped_is_ww_v4(edge) && ranks[edge.from] > prefix[edge.to] {
        valid = false
      }
      if scoped_order_allowed_v4(edge, context) &&
        ranks[edge.from] > prefix[edge.to] {
        valid = false
      }
    }
  }
  valid = valid && !budget.limited
  let original_program = if source.profile == "captured-list-prefix-state/v2" {
    match history.payload {
      ListSnapshot(parsed) =>
        Some(
          model_list_certificate_replay_v4(
            parsed,
            order.map(i => graph.nodes[i]),
            visibility,
            options.max_source_checks,
          ),
        )
      _ => None
    }
  } else {
    None
  }
  match original_program {
    Some(check) if check.status != "checked-compatible" => valid = false
    _ => ()
  }
  let result = model_rule_v4(
    id,
    if valid {
      "checked-compatible"
    } else {
      "unknown"
    },
    "constructive existential generalized-SI completion; this does not validate an arbitrary given SSG or a database BEGIN snapshot",
    covered_by=if valid {
      [
        graph_rule.id,
        "internal",
        "program-source-applicability",
        "identity-source-applicability",
      ]
    } else {
      []
    },
    evidence={
      "theorem": "cerone-gotsman-2016-theorems-9-10/transaction-observation-completion",
      "coverage": "exists-generalized-si-completion",
      "primaryReference": {
        "url": "https://software.imdea.org/~gotsman/papers/si-podc16.pdf",
        "section": "Definition 6 and Theorems 9/10",
        "downloadSha256": "66e9a09029080af4935417a1c8207affa7e73de7b75455a855a4057b991c59cf",
      },
      "scope": if source.profile == "captured-list-prefix-state/v2" {
        Json(
          "unique-identity append programs embedded in proven prefix states; original reads/appends/rollback preserved; derived scalar states are constraints, not collected observations; no given logical snapshot assertions",
        )
      } else {
        Json(
          "unique-version point registers, blind assignments, every actual external read, no additional logical snapshot assertions",
        )
      },
      "context": Json(scoped_context_name_v4(context)),
      "sourceGraphSha256": Json(graph.input_sha256),
      "sourceProjection": match source.point_program {
        Some(p) => p.mapping
        None => Json::null()
      },
      "formula": "X=WW union WR union selected-order; Ext=X union (X;RW); VIS=CO?;X",
      "commitOrder": Json(order.map(i => graph.nodes[i])),
      "visibilityPrefixes": Json(visibility),
      "initialVersionsVisibleByDefault": true,
      "checks": {
        "allWRVisible": Json(valid),
        "allRWImmediateSuccessorsInvisible": Json(valid),
        "allWWPredecessorsVisible": Json(valid),
        "selectedOrderVisible": Json(valid),
        "writerTotalOrderAndTransitiveRWExpansion": "proved from the same complete installed chains; own successor stops the external-read RW chain",
      },
      "logicalStartFactsAccepted": false,
      "transactionBeginUsedAsSnapshot": false,
      "execution": model_completion_execution_v4(budget),
    },
  )
  match original_program {
    Some(check) =>
      object_fields_unchecked_v3(result.evidence)["originalProgramReplay"] = model_rule_json_v4(
        check,
      )
    None => ()
  }
  result
}

///|
/// This certificate is also useful when RC allows external rereads. Full INT
/// is deliberately not a premise for the CV per-key graph argument.
fn model_cv_rank_certificate_v4(
  facts : ModelFactsV4,
  source : ModelSourceV4,
  options : ModelOptionsV4,
  i_rule : ModelRuleV4,
  single_rule : ModelRuleV4,
) -> ModelRuleV4 {
  let id = "completion/CV-per-key-ranks"
  if source.profile == "captured-register-full-program/v2" ||
    source.profile == "captured-list-prefix-state/v2" {
    return model_cv_mapped_rank_v4(source, options, i_rule, single_rule)
  }
  if !model_observation_premises_v4(source, false) ||
    i_rule.status != "checked-compatible" ||
    single_rule.status != "checked-compatible" {
    return model_rule_v4(
      id, "pending", "requires complete point-register I and G-single absence plus all external sources and legal own reads",
    )
  }
  let history = match facts.history.payload {
    RegisterSnapshot(Some(h), None) => h
    _ =>
      return model_rule_v4(
        id, "pending", "CV rank certificate currently applies only to declared point registers",
      )
  }
  let budget : ModelSourceBudgetV4 = {
    maximum: options.max_source_checks,
    checks: 0,
    limited: false,
  }
  let finals : Map[String, Map[String, String]] = Map([])
  let by_key : Map[String, Array[String]] = Map([])
  for tx in history.transactions {
    if tx.status != Committed {
      continue
    }
    let last : Map[String, String] = Map([])
    for op in tx.ops {
      if !model_source_charge_v4(budget) {
        break
      }
      if op.kind == Write {
        last[op.key] = op.version
      }
    }
    finals[tx.id] = last
    for key, v in last {
      if !model_source_charge_v4(budget) {
        break
      }
      let versions = by_key.get_or_default(key, [])
      versions.push(v)
      by_key[key] = versions
    }
  }
  let ranks : Map[String, Map[String, Int32]] = Map([])
  let mut valid = true
  for key, initial in history.initial {
    if !model_source_charge_v4(budget) {
      break
    }
    let committed = by_key.get_or_default(key, [])
    let order = match history.version_orders.get(key) {
      Some(given) => given.copy()
      None =>
        if committed.length() <= 1 {
          let values = [initial]
          values.append(committed)
          values
        } else {
          valid = false
          []
        }
    }
    if order.length() != committed.length() + 1 ||
      order.is_empty() ||
      order[0] != initial {
      valid = false
    }
    let positions : Map[String, Int32] = Map([])
    for i, v in order {
      if !model_source_charge_v4(budget) {
        break
      }
      if positions.contains(v) || (i > 0 && !committed.contains(v)) {
        valid = false
      }
      positions[v] = i
    }
    ranks[key] = positions
  }
  let records : Array[Json] = []
  for tx in history.transactions {
    if tx.status != Committed {
      continue
    }
    let final_writes = finals.get_or_default(tx.id, Map([]))
    let own : Map[String, String] = Map([])
    let previous : Map[String, Int32] = Map([])
    for oi, op in tx.ops {
      if !model_source_charge_v4(budget) {
        break
      }
      if op.kind == Write {
        own[op.key] = op.version
        continue
      }
      if own.contains(op.key) {
        continue
      }
      let read_rank = ranks
        .get_or_default(op.key, Map([]))
        .get_or_default(op.version, -1)
      let write_rank = match final_writes.get(op.key) {
        Some(v) => ranks.get_or_default(op.key, Map([])).get_or_default(v, -1)
        None => -1
      }
      if read_rank < 0 {
        valid = false
      }
      if write_rank >= 0 {
        if read_rank != write_rank - 1 {
          valid = false
        }
      } else {
        match previous.get(op.key) {
          Some(v) if v != read_rank => valid = false
          _ => ()
        }
        previous[op.key] = read_rank
      }
      records.push({
        "transaction": Json(tx.id),
        "key": Json(op.key),
        "operationIndex": Json(oi),
        "readVersion": Json(op.version),
        "readRank": Json(read_rank),
        "finalWriteRank": Json(write_rank),
      })
    }
  }
  model_rule_v4(
    id,
    if valid && !budget.limited {
      "checked-compatible"
    } else {
      "unknown"
    },
    "every external read by a writer sees its immediate predecessor rank; nonwriters read a single rank per key; absence covers cursor and fixed unique-write lost-update",
    covered_by=[i_rule.id, single_rule.id, "program-source-applicability"],
    evidence={
      "definition": "fixed-elle-point-register-CV-rank-certificate/v1",
      "readRanks": Json(records),
      "allRanksValid": Json(valid && !budget.limited),
      "fullRepeatableReadINTRequired": false,
      "execution": model_source_execution_v4(budget),
    },
  )
}

///|
fn model_completion_rules_v4(
  facts : ModelFactsV4,
  source : ModelSourceV4,
  orders : ModelOrdersV4,
  options : ModelOptionsV4,
  rules : Map[String, ModelRuleV4],
) -> Map[String, ModelRuleV4] {
  let result : Map[String, ModelRuleV4] = Map([])
  for context in [ScopedDataOnly, ScopedWithProcess, ScopedWithRealtime] {
    let certificate = model_si_completion_v4(
      facts.history,
      source,
      orders,
      context,
      options,
      rules.at(model_graph_key_v4("Ext(I,A)", context)),
    )
    result[certificate.id] = certificate
  }
  let rank = model_cv_rank_certificate_v4(
    facts,
    source,
    options,
    rules.at(model_graph_key_v4("I", ScopedDataOnly)),
    rules.at(model_graph_key_v4("G-single", ScopedDataOnly)),
  )
  result[rank.id] = rank
  let prerequisites = model_observation_premises_v4(source, false)
  let item = rules.at(model_graph_key_v4("I+Ai", ScopedDataOnly))
  let i = rules.at(model_graph_key_v4("I", ScopedDataOnly))
  result["completion/RR-cursor"] = model_rule_v4(
    "completion/RR-cursor",
    if prerequisites &&
      item.status == "checked-compatible" &&
      i.status == "checked-compatible" {
      "checked-compatible"
    } else {
      "pending"
    },
    "Adya cursor cycle is a subgraph of complete I union item-RW on this validated point-register workload",
    covered_by=[item.id, i.id, "program-source-applicability"],
  )
  let d = rules.at(model_graph_key_v4("D", ScopedDataOnly))
  result["completion/update"] = model_rule_v4(
    "completion/update",
    if prerequisites &&
      d.status == "checked-compatible" &&
      i.status == "checked-compatible" {
      "checked-compatible"
    } else {
      "pending"
    },
    "G-update restricts the complete DSG to an induced transaction subgraph; acyclic D excludes every such cycle",
    covered_by=[d.id, i.id],
  )
  result["completion/monotonic"] = model_rule_v4(
    "completion/monotonic",
    rank.status,
    "USG split operation order collapses to identities; a one-RW closed walk reduces to a G-single cycle under the same all-read/own-overlay premises",
    covered_by=[
      rank.id,
      rules.at(model_graph_key_v4("G-single", ScopedDataOnly)).id,
    ],
    evidence=rank.evidence,
  )
  result
}
