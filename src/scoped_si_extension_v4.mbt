///|
priv struct ScopedExtensionArcV4 {
  from : Int32
  to : Int32
  path : Array[Int32]
}

///|
priv struct ScopedExtensionWorkV4 {
  arcs : Array[ScopedExtensionArcV4]
  adjacency : Array[Array[Int32]]
  budget : ScopedSearchBudgetV4
  color : FixedArray[Int32]
  stack_nodes : Array[Int32]
  stack_arcs : Array[Int32]
  mut found : Array[Int32]
}

///|
fn scoped_extension_add_v4(
  arcs : Array[ScopedExtensionArcV4],
  adjacency : Array[Array[Int32]],
  pairs : Map[(Int32, Int32), Int32],
  from : Int32,
  to : Int32,
  path : Array[Int32],
) -> Int32 {
  match pairs.get((from, to)) {
    Some(position) => {
      if path.length() < arcs[position].path.length() {
        arcs[position] = { from, to, path, }
      }
      position
    }
    None => {
      let position = arcs.length()
      arcs.push({ from, to, path, })
      adjacency[from].push(position)
      pairs[(from, to)] = position
      position
    }
  }
}

///|
fn scoped_extension_visit_v4(
  work : ScopedExtensionWorkV4,
  node : Int32,
) -> Unit {
  if !scoped_charge_state_v4(work.budget) {
    return
  }
  work.color[node] = 1
  work.stack_nodes.push(node)
  for position in work.adjacency[node] {
    if !scoped_charge_edge_v4(work.budget) {
      return
    }
    let arc = work.arcs[position]
    if work.color[arc.to] == 0 {
      work.stack_arcs.push(position)
      scoped_extension_visit_v4(work, arc.to)
      let _ = work.stack_arcs.pop()
      if work.budget.limited || !work.found.is_empty() {
        return
      }
    } else if work.color[arc.to] == 1 {
      let mut start = 0
      while work.stack_nodes[start] != arc.to {
        start += 1
      }
      for index in start..<work.stack_arcs.length() {
        work.found.push(work.stack_arcs[index])
      }
      work.found.push(position)
      return
    }
  }
  work.color[node] = 2
  let _ = work.stack_nodes.pop()
}

///|
fn scoped_extension_witness_v4(
  graph : ScopedDependencyGraphV4,
  arcs : Array[ScopedExtensionArcV4],
  cycle : Array[Int32],
  rules : ScopedRuleSetV4,
) -> Json {
  if cycle.is_empty() {
    return Json::null()
  }
  let original : Array[Int32] = []
  for position in cycle {
    for edge in arcs[position].path {
      original.push(edge)
    }
  }
  let result = scoped_cycle_witness_v4(graph, original, rules)
  let fields = object_fields_unchecked_v3(result)
  fields["kind"] = Json("source-bound-scoped-extension-cycle")
  fields["minimality"] = Json(
    "simple virtual cycle in Ext; the expanded original closed walk may repeat vertices",
  )
  fields["virtualSteps"] = Json(
    cycle.map(position => {
      let arc = arcs[position]
      (
        {
          "from": Json(graph.nodes[arc.from]),
          "to": Json(graph.nodes[arc.to]),
          "originalSteps": Json(
            arc.path.map(index => graph.edges[index].original),
          ),
          "composition": Json(if arc.path.length() == 1 { "I" } else { "I;A" }),
        } : Json)
    }),
  )
  fields["formula"] = Json(
    "Ext(I,A)=I union (I;A); each I may be an explicit process/realtime edge in the chosen context",
  )
  result
}

///|
/// Fixed Elle sequential-extension is one I step, optionally one A step, not
/// I union A and not a transitive closure. Derived self-loops are retained.
pub fn search_si_extension_v4(
  graph : ScopedDependencyGraphV4,
  rule_set~ : ScopedRuleSetV4,
  order_context~ : ScopedOrderContextV4 = ScopedDataOnly,
  max_states~ : Int32 = 100000,
  max_edge_checks~ : Int32 = 1000000,
) -> ScopedSearchResultV4 {
  let budget : ScopedSearchBudgetV4 = {
    max_states,
    max_edges: max_edge_checks,
    states: 0,
    edge_checks: 0,
    limited: false,
    reason: "complete",
  }
  let valid = scoped_budget_valid_v4(max_states, max_edge_checks)
  let arcs : Array[ScopedExtensionArcV4] = []
  let adjacency : Array[Array[Int32]] = []
  for _ in graph.nodes {
    adjacency.push([])
  }
  let pairs : Map[(Int32, Int32), Int32] = Map([])
  let mut composed = 0
  let work : ScopedExtensionWorkV4 = {
    arcs,
    adjacency,
    budget,
    color: FixedArray::make(graph.nodes.length(), 0),
    stack_nodes: [],
    stack_arcs: [],
    found: [],
  }
  if valid {
    for position, edge in graph.edges {
      if !scoped_charge_edge_v4(budget) {
        break
      }
      if !(scoped_is_ww_v4(edge) ||
        scoped_is_wr_v4(edge) ||
        scoped_order_allowed_v4(edge, order_context)) {
        continue
      }
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
        composed += 1
        let index = scoped_extension_add_v4(
          arcs,
          adjacency,
          pairs,
          edge.from,
          target.to,
          [position, next],
        )
        if edge.from == target.to {
          work.found = [index]
          break
        }
      }
      if budget.limited || !work.found.is_empty() {
        break
      }
    }
    if !budget.limited && work.found.is_empty() {
      for node in 0..<graph.nodes.length() {
        if work.color[node] == 0 && !adjacency[node].is_empty() {
          scoped_extension_visit_v4(work, node)
        }
        if budget.limited || !work.found.is_empty() {
          break
        }
      }
    }
  }
  let status = if !valid {
    "unsupported"
  } else if !work.found.is_empty() {
    "refuted"
  } else if budget.limited || !scoped_context_complete_v4(graph, order_context) {
    "unknown"
  } else {
    "checked-compatible"
  }
  let record : Json = {
    "format": "moontxnwitness-scoped-si-extension/v4",
    "schemaVersion": 4,
    "semanticContract": Json(scoped_ruleset_name_v4(rule_set)),
    "ruleSet": Json(scoped_ruleset_name_v4(rule_set)),
    "extensionDefinition": "elle-4e359e5-sequential-extension-v1",
    "algorithm": "scoped-si-extension-composition-dfs-1",
    "formula": "X union (X;A), X=I with only the caller-selected order context",
    "orderContext": Json(scoped_context_name_v4(order_context)),
    "sourceGraphSha256": Json(graph.input_sha256),
    "sourceDigestContract": "sorted-json-object-keys-v1",
    "sourceAssurance": "conditional on the supplied scoped graph; original references are bound, not database-authenticated",
    "acceptsIsolationModels": false,
    "status": Json(status),
    "reason": Json(
      if !valid {
        "invalid-scoped-search-budget"
      } else if !work.found.is_empty() {
        "source-bound-extension-cycle"
      } else if budget.limited {
        budget.reason
      } else if !scoped_context_complete_v4(graph, order_context) {
        "scoped-source-context-incomplete"
      } else {
        "complete-extension-acyclicity-check"
      },
    ),
    "witness": scoped_extension_witness_v4(graph, arcs, work.found, rule_set),
    "sourceGaps": Json(scoped_context_gaps_v4(graph, order_context)),
    "execution": {
      "counterContract": "scoped-si-one-step-composition-dfs-counters-1",
      "states": Json(budget.states),
      "edgeChecks": Json(budget.edge_checks),
      "compositionPairs": Json(composed),
      "virtualArcs": Json(arcs.length()),
      "limited": Json(budget.limited),
      "stateUnit": "virtual DFS vertex expansions",
      "edgeUnit": "every native I scan, candidate second step and virtual DFS edge check",
      "limits": {
        "states": Json(max_states),
        "edgeChecks": Json(max_edge_checks),
      },
    },
  }
  { status, record, }
}

///|
pub fn verify_si_extension_v4(
  graph : ScopedDependencyGraphV4,
  supplied : Json,
  rule_set~ : ScopedRuleSetV4,
  order_context~ : ScopedOrderContextV4 = ScopedDataOnly,
  max_states~ : Int32 = 100000,
  max_edge_checks~ : Int32 = 1000000,
) -> Bool {
  supplied ==
  search_si_extension_v4(
    graph,
    rule_set~,
    order_context~,
    max_states~,
    max_edge_checks~,
  ).record
}
