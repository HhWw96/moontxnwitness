///|
priv struct ScopedSearchBudgetV4 {
  max_states : Int32
  max_edges : Int32
  mut states : Int32
  mut edge_checks : Int32
  mut limited : Bool
  mut reason : String
}

///|
priv struct ScopedCycleCountsV4 {
  steps : Int32
  ww : Int32
  wr : Int32
  rw : Int32
  item_rw : Int32
  predicate_rw : Int32
  process : Int32
  realtime : Int32
  first_rw : Bool
  last_rw : Bool
  adjacent_rw : Bool
}

///|
priv struct ScopedSearchWorkV4 {
  graph : ScopedDependencyGraphV4
  category : ScopedCategoryV4
  rule_set : ScopedRuleSetV4
  context : ScopedOrderContextV4
  budget : ScopedSearchBudgetV4
  indices : FixedArray[Int32]
  low : FixedArray[Int32]
  on_stack : FixedArray[Bool]
  stack : Array[Int32]
  component : FixedArray[Int32]
  component_sizes : Array[Int32]
  mut next_index : Int32
  mut found : Array[Int32]
}

///|
pub struct ScopedSearchResultV4 {
  priv status : String
  priv record : Json
}

///|
pub fn ScopedSearchResultV4::status(self : ScopedSearchResultV4) -> String {
  self.status
}

///|
fn scoped_budget_valid_v4(states : Int32, edges : Int32) -> Bool {
  states >= 0 && states <= 100000 && edges >= 0 && edges <= 1000000
}

///|
fn scoped_charge_state_v4(work : ScopedSearchBudgetV4) -> Bool {
  if work.limited {
    return false
  }
  if work.states >= work.max_states {
    work.limited = true
    work.reason = "scoped-state-budget"
    false
  } else {
    work.states += 1
    true
  }
}

///|
fn scoped_charge_edge_v4(work : ScopedSearchBudgetV4) -> Bool {
  if work.limited {
    return false
  }
  if work.edge_checks >= work.max_edges {
    work.limited = true
    work.reason = "scoped-edge-check-budget"
    false
  } else {
    work.edge_checks += 1
    true
  }
}

///|
fn scoped_is_ww_v4(edge : ScopedIndexedEdgeV4) -> Bool {
  edge.data_kind == Some(ScopedWWItem) ||
  edge.data_kind == Some(ScopedWWPredicate)
}

///|
fn scoped_is_wr_v4(edge : ScopedIndexedEdgeV4) -> Bool {
  edge.data_kind == Some(ScopedWRItem) ||
  edge.data_kind == Some(ScopedWRPredicate)
}

///|
fn scoped_is_rw_v4(edge : ScopedIndexedEdgeV4) -> Bool {
  edge.data_kind == Some(ScopedRWItem) ||
  edge.data_kind == Some(ScopedRWPredicate)
}

///|
fn scoped_order_allowed_v4(
  edge : ScopedIndexedEdgeV4,
  context : ScopedOrderContextV4,
) -> Bool {
  match context {
    ScopedDataOnly => false
    ScopedWithProcess => edge.order_kind == Some(ScopedProcess)
    ScopedWithRealtime => edge.order_kind == Some(ScopedRealtime)
  }
}

///|
fn scoped_allowed_v4(
  edge : ScopedIndexedEdgeV4,
  category : ScopedCategoryV4,
  rules : ScopedRuleSetV4,
  context : ScopedOrderContextV4,
) -> Bool {
  if edge.order_kind is Some(_) {
    return scoped_order_allowed_v4(edge, context)
  }
  match category {
    ScopedG0 => scoped_is_ww_v4(edge)
    ScopedG1c => scoped_is_ww_v4(edge) || scoped_is_wr_v4(edge)
    ScopedGSingleItem => edge.data_kind != Some(ScopedRWPredicate)
    ScopedG2Item if rules == ElleFixed4e359e5 =>
      edge.data_kind != Some(ScopedRWPredicate)
    _ => true
  }
}

///|
fn scoped_required_edge_v4(
  edge : ScopedIndexedEdgeV4,
  category : ScopedCategoryV4,
) -> Bool {
  match category {
    ScopedG0 => scoped_is_ww_v4(edge)
    ScopedG1c => scoped_is_ww_v4(edge) || scoped_is_wr_v4(edge)
    ScopedG2Item | ScopedGSingleItem => edge.data_kind == Some(ScopedRWItem)
    _ => scoped_is_rw_v4(edge)
  }
}

///|
fn scoped_counts_empty_v4() -> ScopedCycleCountsV4 {
  {
    steps: 0,
    ww: 0,
    wr: 0,
    rw: 0,
    item_rw: 0,
    predicate_rw: 0,
    process: 0,
    realtime: 0,
    first_rw: false,
    last_rw: false,
    adjacent_rw: false,
  }
}

///|
fn scoped_counts_add_v4(
  counts : ScopedCycleCountsV4,
  edge : ScopedIndexedEdgeV4,
) -> ScopedCycleCountsV4 {
  let rw = scoped_is_rw_v4(edge)
  {
    steps: counts.steps + 1,
    ww: counts.ww + (if scoped_is_ww_v4(edge) { 1 } else { 0 }),
    wr: counts.wr + (if scoped_is_wr_v4(edge) { 1 } else { 0 }),
    rw: counts.rw + (if rw { 1 } else { 0 }),
    item_rw: counts.item_rw +
    (if edge.data_kind == Some(ScopedRWItem) { 1 } else { 0 }),
    predicate_rw: counts.predicate_rw +
    (if edge.data_kind == Some(ScopedRWPredicate) { 1 } else { 0 }),
    process: counts.process +
    (if edge.order_kind == Some(ScopedProcess) { 1 } else { 0 }),
    realtime: counts.realtime +
    (if edge.order_kind == Some(ScopedRealtime) { 1 } else { 0 }),
    first_rw: if counts.steps == 0 {
      rw
    } else {
      counts.first_rw
    },
    last_rw: rw,
    adjacent_rw: counts.adjacent_rw ||
    (counts.steps > 0 && counts.last_rw && rw),
  }
}

///|
fn scoped_cycle_nonadjacent_v4(counts : ScopedCycleCountsV4) -> Bool {
  counts.rw > 0 && !counts.adjacent_rw && !(counts.first_rw && counts.last_rw)
}

///|
fn scoped_cycle_accepts_v4(
  category : ScopedCategoryV4,
  counts : ScopedCycleCountsV4,
) -> Bool {
  match category {
    ScopedG0 => counts.ww > 0 && counts.rw == 0 && counts.wr == 0
    ScopedG1c => counts.ww + counts.wr > 0 && counts.rw == 0
    ScopedG2Item => counts.item_rw > 0
    ScopedG2 => counts.rw > 0
    ScopedGSingleItem => counts.rw == 1 && counts.item_rw == 1
    ScopedGSingle => counts.rw == 1
    ScopedGNonadjacent => scoped_cycle_nonadjacent_v4(counts)
  }
}

///|
fn scoped_tarjan_v4(work : ScopedSearchWorkV4, node : Int32) -> Unit {
  if !scoped_charge_state_v4(work.budget) {
    return
  }
  work.indices[node] = work.next_index
  work.low[node] = work.next_index
  work.next_index += 1
  work.stack.push(node)
  work.on_stack[node] = true
  for index in work.graph.adjacency[node] {
    if !scoped_charge_edge_v4(work.budget) {
      return
    }
    let edge = work.graph.edges[index]
    if !scoped_allowed_v4(edge, work.category, work.rule_set, work.context) {
      continue
    }
    let next = edge.to
    if work.indices[next] < 0 {
      scoped_tarjan_v4(work, next)
      if work.budget.limited {
        return
      }
      if work.low[next] < work.low[node] {
        work.low[node] = work.low[next]
      }
    } else if work.on_stack[next] && work.indices[next] < work.low[node] {
      work.low[node] = work.indices[next]
    }
  }
  if work.low[node] == work.indices[node] {
    let component = work.component_sizes.length()
    let mut size = 0
    while true {
      let stack_node = work.stack.pop().unwrap()
      work.on_stack[stack_node] = false
      work.component[stack_node] = component
      size += 1
      if stack_node == node {
        break
      }
    }
    work.component_sizes.push(size)
  }
}

///|
fn scoped_cycle_dfs_v4(
  work : ScopedSearchWorkV4,
  start : Int32,
  node : Int32,
  visited : FixedArray[Bool],
  path : Array[Int32],
  counts : ScopedCycleCountsV4,
) -> Unit {
  if !scoped_charge_state_v4(work.budget) {
    return
  }
  for index in work.graph.adjacency[node] {
    if !scoped_charge_edge_v4(work.budget) {
      return
    }
    let edge = work.graph.edges[index]
    if !scoped_allowed_v4(edge, work.category, work.rule_set, work.context) ||
      work.component[edge.to] != work.component[start] {
      continue
    }
    let next = scoped_counts_add_v4(counts, edge)
    if (work.category == ScopedGSingle || work.category == ScopedGSingleItem) &&
      next.rw > 1 {
      continue
    }
    if work.category == ScopedGNonadjacent && next.adjacent_rw {
      continue
    }
    if edge.to == start {
      if scoped_cycle_accepts_v4(work.category, next) {
        work.found = path.copy()
        work.found.push(index)
        return
      }
    } else if edge.to > start && !visited[edge.to] {
      visited[edge.to] = true
      path.push(index)
      scoped_cycle_dfs_v4(work, start, edge.to, visited, path, next)
      let _ = path.pop()
      visited[edge.to] = false
      if work.budget.limited || !work.found.is_empty() {
        return
      }
    }
  }
}

///|
fn scoped_witness_counts_v4(
  graph : ScopedDependencyGraphV4,
  indices : Array[Int32],
) -> ScopedCycleCountsV4 {
  let mut counts = scoped_counts_empty_v4()
  for index in indices {
    counts = scoped_counts_add_v4(counts, graph.edges[index])
  }
  counts
}

///|
fn scoped_specific_v4(
  counts : ScopedCycleCountsV4,
  rules : ScopedRuleSetV4,
) -> String {
  let item = counts.item_rw > 0 &&
    (rules == Adya2000Mixed || counts.predicate_rw == 0)
  let base = if counts.rw == 0 {
    if counts.wr == 0 {
      "G0"
    } else {
      "G1c"
    }
  } else if counts.rw == 1 {
    if counts.item_rw == 1 {
      "G-single-item"
    } else {
      "G-single"
    }
  } else if scoped_cycle_nonadjacent_v4(counts) {
    "G-nonadjacent"
  } else if item {
    "G2-item"
  } else {
    "G2"
  }
  base +
  (if counts.realtime > 0 {
    "-realtime"
  } else if counts.process > 0 {
    "-process"
  } else {
    ""
  })
}

///|
fn scoped_implied_v4(
  counts : ScopedCycleCountsV4,
  rules : ScopedRuleSetV4,
) -> Array[String] {
  let base : Array[String] = []
  if counts.rw == 0 {
    if counts.wr == 0 {
      base.push("G0")
    }
    base.push("G1c")
    base.push("G1")
  } else {
    if counts.rw == 1 {
      if counts.item_rw == 1 {
        base.push("G-single-item")
      }
      base.push("G-single")
    }
    if scoped_cycle_nonadjacent_v4(counts) {
      base.push("G-nonadjacent")
    }
    if counts.item_rw > 0 &&
      (rules == Adya2000Mixed || counts.predicate_rw == 0) {
      base.push("G2-item")
    }
    base.push("G2")
  }
  let result : Array[String] = []
  for name in base {
    if counts.realtime > 0 {
      result.push(name + "-realtime")
    } else if counts.process > 0 {
      result.push(name + "-process")
    } else {
      result.push(name)
      result.push(name + "-process")
      result.push(name + "-realtime")
    }
  }
  result
}

///|
fn scoped_cycle_witness_v4(
  graph : ScopedDependencyGraphV4,
  indices : Array[Int32],
  rules : ScopedRuleSetV4,
) -> Json {
  if indices.is_empty() {
    return Json::null()
  }
  let counts = scoped_witness_counts_v4(graph, indices)
  let vertices = [Json(graph.nodes[graph.edges[indices[0]].from])]
  for index in indices {
    vertices.push(Json(graph.nodes[graph.edges[index].to]))
  }
  {
    "kind": "source-bound-scoped-simple-cycle",
    "vertices": Json(vertices),
    "steps": Json(indices.map(index => graph.edges[index].original)),
    "specificCategory": Json(scoped_specific_v4(counts, rules)),
    "impliedPhenomena": Json(scoped_implied_v4(counts, rules)),
    "antiDependencies": {
      "total": Json(counts.rw),
      "item": Json(counts.item_rw),
      "predicate": Json(counts.predicate_rw),
      "cyclicallyAdjacent": Json(
        counts.adjacent_rw || (counts.first_rw && counts.last_rw),
      ),
    },
    "minimality": "a category-specific simple cycle; not a global shortest-cycle claim",
  }
}

///|
fn scoped_result_record_v4(
  graph : ScopedDependencyGraphV4,
  category : ScopedCategoryV4,
  rules : ScopedRuleSetV4,
  context : ScopedOrderContextV4,
  budget : ScopedSearchBudgetV4,
  indices : Array[Int32],
  valid : Bool,
) -> ScopedSearchResultV4 {
  let status = if !valid {
    "unsupported"
  } else if !indices.is_empty() {
    "refuted"
  } else if budget.limited || !scoped_context_complete_v4(graph, context) {
    "unknown"
  } else {
    "checked-compatible"
  }
  let reason = if !valid {
    "invalid-scoped-search-budget"
  } else if !indices.is_empty() {
    "source-bound-category-cycle"
  } else if budget.limited {
    budget.reason
  } else if !scoped_context_complete_v4(graph, context) {
    "scoped-source-context-incomplete"
  } else {
    "complete-category-search"
  }
  let record : Json = {
    "format": "moontxnwitness-scoped-category-search/v4",
    "schemaVersion": 4,
    "semanticContract": Json(scoped_ruleset_name_v4(rules)),
    "algorithm": "scoped-scc-simple-cycle-1",
    "ruleSet": Json(scoped_ruleset_name_v4(rules)),
    "requestedCategory": Json(scoped_category_name_v4(category)),
    "orderContext": Json(scoped_context_name_v4(context)),
    "sourceGraphSha256": Json(graph.input_sha256),
    "sourceDigestContract": "sorted-json-object-keys-v1",
    "sourceAssurance": "conditional on the supplied scoped graph; original references are bound, not database-authenticated",
    "acceptsIsolationModels": false,
    "status": Json(status),
    "reason": Json(reason),
    "witness": scoped_cycle_witness_v4(graph, indices, rules),
    "sourceGaps": Json(scoped_context_gaps_v4(graph, context)),
    "execution": {
      "counterContract": "scoped-scc-prefix-edge-checks-1",
      "states": Json(budget.states),
      "edgeChecks": Json(budget.edge_checks),
      "limited": Json(budget.limited),
      "stateUnit": "SCC vertex visits and simple-path prefix expansions",
      "edgeUnit": "each SCC, component-requirement or path edge examination, including filtered edges",
      "limits": {
        "states": Json(budget.max_states),
        "edgeChecks": Json(budget.max_edges),
      },
    },
  }
  { status, record, }
}

///|
/// Rules are mandatory caller input. Missing-source edges never become witnesses.
pub fn search_scoped_category_v4(
  graph : ScopedDependencyGraphV4,
  category : ScopedCategoryV4,
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
  let work : ScopedSearchWorkV4 = {
    graph,
    category,
    rule_set,
    context: order_context,
    budget,
    indices: FixedArray::make(graph.nodes.length(), -1),
    low: FixedArray::make(graph.nodes.length(), -1),
    on_stack: FixedArray::make(graph.nodes.length(), false),
    stack: [],
    component: FixedArray::make(graph.nodes.length(), -1),
    component_sizes: [],
    next_index: 0,
    found: [],
  }
  if valid {
    for node in 0..<graph.nodes.length() {
      if work.indices[node] < 0 {
        scoped_tarjan_v4(work, node)
      }
      if budget.limited {
        break
      }
    }
    let required = FixedArray::make(work.component_sizes.length(), false)
    if !budget.limited {
      for edge in graph.edges {
        if !scoped_charge_edge_v4(budget) {
          break
        }
        if scoped_allowed_v4(edge, category, rule_set, order_context) &&
          work.component[edge.from] == work.component[edge.to] &&
          scoped_required_edge_v4(edge, category) {
          required[work.component[edge.from]] = true
        }
      }
    }
    if !budget.limited {
      let visited = FixedArray::make(graph.nodes.length(), false)
      let path : Array[Int32] = []
      for start in 0..<graph.nodes.length() {
        let component = work.component[start]
        if work.component_sizes[component] < 2 || !required[component] {
          continue
        }
        visited[start] = true
        scoped_cycle_dfs_v4(
          work,
          start,
          start,
          visited,
          path,
          scoped_counts_empty_v4(),
        )
        visited[start] = false
        if budget.limited || !work.found.is_empty() {
          break
        }
      }
    }
  }
  scoped_result_record_v4(
    graph,
    category,
    rule_set,
    order_context,
    budget,
    work.found,
    valid,
  )
}

///|
pub fn scoped_search_v4_json(result : ScopedSearchResultV4) -> Json {
  v4_json_copy(result.record)
}

///|
pub fn verify_scoped_category_v4(
  graph : ScopedDependencyGraphV4,
  supplied : Json,
  category : ScopedCategoryV4,
  rule_set~ : ScopedRuleSetV4,
  order_context~ : ScopedOrderContextV4 = ScopedDataOnly,
  max_states~ : Int32 = 100000,
  max_edge_checks~ : Int32 = 1000000,
) -> Bool {
  supplied ==
  search_scoped_category_v4(
    graph,
    category,
    rule_set~,
    order_context~,
    max_states~,
    max_edge_checks~,
  ).record
}
