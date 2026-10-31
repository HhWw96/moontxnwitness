///|
/// A concrete original-row serial certificate, not a relabelled SI certificate.
fn model_relation_serial_completion_v4(
  history : HistoryV4,
  source : ModelSourceV4,
  orders : ModelOrdersV4,
  context : ScopedOrderContextV4,
  options : ModelOptionsV4,
  d_rule : ModelRuleV4,
) -> ModelRuleV4 {
  let id = "completion/original-row-serial/" + scoped_context_name_v4(context)
  if source.profile != "captured-relation-row-slots/v1" ||
    options.completion_policy != ModelObservationOnlyCompletion ||
    !model_observation_premises_v4(source, true) ||
    d_rule.status != "checked-compatible" {
    return model_rule_v4(
      id, "pending", "requires a closed atomic-row program, checked snapshot/own overlay premises and an acyclic complete D in the selected original-order context",
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
      id, "unknown", "necessary original order context is incomplete",
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
  let indegree = FixedArray::make(graph.nodes.length(), 0)
  let adjacency : Array[Array[Int32]] = Array::makei(graph.nodes.length(), _ => {
    []
  })
  for position, edge in graph.edges {
    if !scoped_charge_edge_v4(budget) {
      break
    }
    if edge.data_kind is Some(_) || scoped_order_allowed_v4(edge, context) {
      adjacency[edge.from].push(position)
      indegree[edge.to] += 1
    }
  }
  let queue : Array[Int32] = []
  for node in 0..<graph.nodes.length() {
    if indegree[node] == 0 {
      queue.push(node)
    }
  }
  let order : Array[String] = []
  let visibility : Array[Json] = []
  let mut cursor = 0
  while cursor < queue.length() && !budget.limited {
    if !scoped_charge_state_v4(budget) {
      break
    }
    let node = queue[cursor]
    cursor += 1
    let visible : Array[String] = []
    for tx in order {
      if !scoped_charge_edge_v4(budget) {
        break
      }
      visible.push(tx)
    }
    if budget.limited {
      break
    }
    visibility.push({
      "transaction": Json(graph.nodes[node]),
      "visiblePrefixLength": Json(order.length()),
      "visibleTransactions": Json(visible),
    })
    order.push(graph.nodes[node])
    for position in adjacency[node] {
      if !scoped_charge_edge_v4(budget) {
        break
      }
      let edge = graph.edges[position]
      indegree[edge.to] -= 1
      if indegree[edge.to] == 0 {
        queue.push(edge.to)
      }
    }
  }
  let certificate : Json = {
    "commitOrder": Json(order),
    "visibilityPrefixes": Json(visibility),
  }
  let replay = original_relation_program_replay_v4(
    history,
    certificate,
    RelationSerialOrder,
    options.max_source_checks,
  )
  let valid = order.length() == graph.nodes.length() &&
    !budget.limited &&
    replay.status() == "checked-compatible"
  let execution = object_fields_unchecked_v3(
    model_completion_execution_v4(budget),
  )
  execution["counterContract"] = Json(
    "row-serial-topology-and-prefix-reference-checks-1",
  )
  model_rule_v4(
    id,
    if valid {
      "checked-compatible"
    } else {
      "unknown"
    },
    "one D-topological serial order is independently replayed from the original row program; failed or incomplete candidates are unknown, never a serial-unsatisfiability or weaker-model refutation",
    covered_by=[
      d_rule.id,
      "row-slot-projection-applicability",
      "write-input-applicability",
    ],
    evidence={
      "definition": "source-bound-original-row-serial-certificate/v1",
      "sourceGraphSha256": Json(graph.input_sha256),
      "orderContext": Json(scoped_context_name_v4(context)),
      "certificate": certificate,
      "originalProgramReplay": replay.record,
      "execution": Json(execution),
    },
  )
}
