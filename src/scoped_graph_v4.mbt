///|
pub(all) enum ScopedRuleSetV4 {
  Adya2000Mixed
  ElleFixed4e359e5
} derive(Eq)

///|
pub extend ScopedRuleSetV4 with Eq::{equal, not_equal}

///|
pub(all) enum ScopedCategoryV4 {
  ScopedG0
  ScopedG1c
  ScopedG2Item
  ScopedG2
  ScopedGSingleItem
  ScopedGSingle
  ScopedGNonadjacent
} derive(Eq)

///|
pub extend ScopedCategoryV4 with Eq::{equal, not_equal}

///|
pub(all) enum ScopedOrderContextV4 {
  ScopedDataOnly
  ScopedWithProcess
  ScopedWithRealtime
} derive(Eq)

///|
pub extend ScopedOrderContextV4 with Eq::{equal, not_equal}

///|
pub(all) enum ScopedDataKindV4 {
  ScopedWWItem
  ScopedWWPredicate
  ScopedWRItem
  ScopedWRPredicate
  ScopedRWItem
  ScopedRWPredicate
} derive(Eq)

///|
pub extend ScopedDataKindV4 with Eq::{equal, not_equal}

///|
pub(all) enum ScopedOrderKindV4 {
  ScopedProcess
  ScopedRealtime
} derive(Eq)

///|
pub extend ScopedOrderKindV4 with Eq::{equal, not_equal}

///|
pub(all) struct ScopedDataEdgeInputV4 {
  id : String
  from : String
  to : String
  kind : ScopedDataKindV4
  sources : Array[Json]
}

///|
pub(all) struct ScopedOriginalRefV4 {
  transaction : String
  observation : Json
}

///|
/// Order is supplied explicitly. A physical pooled connection is not a process.
pub(all) struct ScopedOrderEdgeInputV4 {
  id : String
  from : String
  to : String
  kind : ScopedOrderKindV4
  context_id : String
  from_source : ScopedOriginalRefV4
  to_source : ScopedOriginalRefV4
}

///|
priv struct ScopedIndexedEdgeV4 {
  id : String
  from : Int32
  to : Int32
  data_kind : ScopedDataKindV4?
  order_kind : ScopedOrderKindV4?
  original : Json
}

///|
pub struct ScopedDependencyGraphV4 {
  priv nodes : Array[String]
  priv edges : Array[ScopedIndexedEdgeV4]
  priv adjacency : Array[Array[Int32]]
  priv input_record : Json
  priv input_sha256 : String
  priv data_complete : Bool
  priv process_complete : Bool
  priv realtime_complete : Bool
  priv data_gaps : Array[Json]
  priv process_gaps : Array[Json]
  priv realtime_gaps : Array[Json]
}

///|
pub fn ScopedDependencyGraphV4::input_sha256(
  self : ScopedDependencyGraphV4,
) -> String {
  self.input_sha256
}

///|
fn scoped_ruleset_name_v4(value : ScopedRuleSetV4) -> String {
  match value {
    Adya2000Mixed => "adya-2000-scoped-categories-v1"
    ElleFixed4e359e5 => "elle-4e359e5-scoped-categories-v1"
  }
}

///|
fn scoped_category_name_v4(value : ScopedCategoryV4) -> String {
  match value {
    ScopedG0 => "G0"
    ScopedG1c => "G1c"
    ScopedG2Item => "G2-item"
    ScopedG2 => "G2"
    ScopedGSingleItem => "G-single-item"
    ScopedGSingle => "G-single"
    ScopedGNonadjacent => "G-nonadjacent"
  }
}

///|
fn scoped_context_name_v4(value : ScopedOrderContextV4) -> String {
  match value {
    ScopedDataOnly => "data-only"
    ScopedWithProcess => "process"
    ScopedWithRealtime => "realtime"
  }
}

///|
fn scoped_data_name_v4(value : ScopedDataKindV4) -> String {
  match value {
    ScopedWWItem => "ww-item"
    ScopedWWPredicate => "ww-predicate"
    ScopedWRItem => "wr-item"
    ScopedWRPredicate => "wr-predicate"
    ScopedRWItem => "rw-item"
    ScopedRWPredicate => "rw-predicate"
  }
}

///|
fn scoped_order_name_v4(value : ScopedOrderKindV4) -> String {
  match value {
    ScopedProcess => "process"
    ScopedRealtime => "realtime"
  }
}

///|
fn scoped_name_valid_v4(value : String) -> Bool {
  if value.length() < 1 || value.length() > 256 {
    return false
  }
  try {
    relation_v3_scalar(value)
    true
  } catch {
    _ => false
  }
}

///|
fn scoped_ref_valid_v4(
  reference : ScopedOriginalRefV4,
  expected : String,
) -> Bool {
  if reference.transaction != expected {
    return false
  }
  match reference.observation {
    Object(fields) => {
      if fields.is_empty() {
        return false
      }
      let tx = fields.get("tx")
      let transaction = fields.get("transaction")
      if tx != Some(Json(expected)) && transaction != Some(Json(expected)) {
        return false
      }
      (tx is None || tx == Some(Json(expected))) &&
      (transaction is None || transaction == Some(Json(expected)))
    }
    _ => false
  }
}

///|
fn scoped_order_bad_nodes_v4(
  count : Int32,
  edges : Array[ScopedIndexedEdgeV4],
  kind : ScopedOrderKindV4?,
) -> FixedArray[Bool] {
  let indegree = FixedArray::make(count, 0)
  let adjacency : Array[Array[Int32]] = []
  for _ in 0..<count {
    adjacency.push([])
  }
  for edge in edges {
    if edge.order_kind is Some(_) && (kind is None || edge.order_kind == kind) {
      indegree[edge.to] += 1
      adjacency[edge.from].push(edge.to)
    }
  }
  let queue : Array[Int32] = []
  for node in 0..<count {
    if indegree[node] == 0 {
      queue.push(node)
    }
  }
  let mut position = 0
  while position < queue.length() {
    let node = queue[position]
    position += 1
    for next in adjacency[node] {
      indegree[next] -= 1
      if indegree[next] == 0 {
        queue.push(next)
      }
    }
  }
  let bad = FixedArray::make(count, false)
  for node in 0..<count {
    bad[node] = indegree[node] > 0
  }
  bad
}

///|
fn scoped_sorted_json_v4(value : Json, out : StringBuilder) -> Unit {
  match value {
    Object(fields) => {
      out.write_string("{")
      let keys = fields.keys().collect()
      keys.sort_by((a, b) => relation_v3_text_compare(a, b))
      for position, key in keys {
        if position > 0 {
          out.write_string(",")
        }
        out.write_string(Json(key).stringify())
        out.write_string(":")
        scoped_sorted_json_v4(fields.at(key), out)
      }
      out.write_string("}")
    }
    Array(items) => {
      out.write_string("[")
      for position, item in items {
        if position > 0 {
          out.write_string(",")
        }
        scoped_sorted_json_v4(item, out)
      }
      out.write_string("]")
    }
    _ => out.write_string(value.stringify())
  }
}

///|
/// The snapshot binds caller-declared graph facts. It does not authenticate a DB.
/// Missing edge provenance is excluded and makes only its required context unknown.
pub fn scoped_dependency_graph_v4(
  nodes : Array[String],
  data_edges : Array[ScopedDataEdgeInputV4],
  order_edges~ : Array[ScopedOrderEdgeInputV4] = [],
  data_complete~ : Bool = true,
  process_complete~ : Bool = false,
  realtime_complete~ : Bool = false,
  gaps~ : Array[Json] = [],
) -> Result[ScopedDependencyGraphV4, String] {
  if nodes.length() > 128 ||
    data_edges.length() + order_edges.length() > 50000 ||
    gaps.length() > 4096 {
    return Err(
      "scoped graph capacity is 128 nodes, 50000 edges, 4096 coverage gaps",
    )
  }
  let node_indices : Map[String, Int32] = Map([])
  for position, node in nodes {
    if !scoped_name_valid_v4(node) || node_indices.contains(node) {
      return Err(
        "node identities must be unique nonempty Unicode scalar strings of at most 256 UTF-16 units",
      )
    }
    node_indices[node] = position
  }
  let edge_ids : Map[String, Bool] = Map([])
  let indexed : Array[ScopedIndexedEdgeV4] = []
  let raw_data : Array[Json] = []
  let raw_order : Array[Json] = []
  let data_gaps = gaps.map(v4_json_copy)
  let process_gaps : Array[Json] = []
  let realtime_gaps : Array[Json] = []
  for edge in data_edges {
    if !scoped_name_valid_v4(edge.id) ||
      edge_ids.contains(edge.id) ||
      !node_indices.contains(edge.from) ||
      !node_indices.contains(edge.to) ||
      edge.from == edge.to {
      return Err(
        "edge IDs must be unique, endpoints must name distinct declared nodes",
      )
    }
    edge_ids[edge.id] = true
    let record : Json = {
      "id": Json(edge.id),
      "from": Json(edge.from),
      "to": Json(edge.to),
      "kind": Json(scoped_data_name_v4(edge.kind)),
      "sources": Json(edge.sources.map(v4_json_copy)),
    }
    raw_data.push(record)
    if edge.sources.is_empty() ||
      edge.sources.any(source => source == Json::null()) {
      data_gaps.push({
        "code": "missing-scoped-data-edge-source",
        "edgeId": Json(edge.id),
      })
      continue
    }
    indexed.push({
      id: edge.id,
      from: node_indices.at(edge.from),
      to: node_indices.at(edge.to),
      data_kind: Some(edge.kind),
      order_kind: None,
      original: record,
    })
  }
  let process_membership : Map[String, String] = Map([])
  let process_conflicts : Map[Int32, Bool] = Map([])
  for edge in order_edges {
    if !scoped_name_valid_v4(edge.id) ||
      edge_ids.contains(edge.id) ||
      !node_indices.contains(edge.from) ||
      !node_indices.contains(edge.to) ||
      edge.from == edge.to {
      return Err(
        "edge IDs must be unique, endpoints must name distinct declared nodes",
      )
    }
    edge_ids[edge.id] = true
    let record : Json = {
      "id": Json(edge.id),
      "from": Json(edge.from),
      "to": Json(edge.to),
      "kind": Json(scoped_order_name_v4(edge.kind)),
      "contextId": Json(edge.context_id),
      "fromOriginal": {
        "transaction": Json(edge.from_source.transaction),
        "observation": v4_json_copy(edge.from_source.observation),
      },
      "toOriginal": {
        "transaction": Json(edge.to_source.transaction),
        "observation": v4_json_copy(edge.to_source.observation),
      },
    }
    raw_order.push(record)
    let valid = scoped_name_valid_v4(edge.context_id) &&
      scoped_ref_valid_v4(edge.from_source, edge.from) &&
      scoped_ref_valid_v4(edge.to_source, edge.to)
    if !valid {
      let target = if edge.kind == ScopedProcess {
        process_gaps
      } else {
        realtime_gaps
      }
      target.push({
        "code": "unbound-scoped-order-source",
        "edgeId": Json(edge.id),
        "original": record,
      })
      continue
    }
    if edge.kind == ScopedProcess {
      for node in [edge.from, edge.to] {
        match process_membership.get(node) {
          Some(previous) if previous != edge.context_id =>
            process_conflicts[node_indices.at(node)] = true
          _ => process_membership[node] = edge.context_id
        }
      }
    }
    indexed.push({
      id: edge.id,
      from: node_indices.at(edge.from),
      to: node_indices.at(edge.to),
      data_kind: None,
      order_kind: Some(edge.kind),
      original: record,
    })
  }
  let bad_process_nodes = scoped_order_bad_nodes_v4(
    nodes.length(),
    indexed,
    Some(ScopedProcess),
  )
  let bad_realtime_nodes = scoped_order_bad_nodes_v4(
    nodes.length(),
    indexed,
    Some(ScopedRealtime),
  )
  let bad_process_ids : Array[Json] = []
  let bad_realtime_ids : Array[Json] = []
  for node in 0..<nodes.length() {
    if process_conflicts.contains(node) {
      bad_process_nodes[node] = true
    }
    if bad_process_nodes[node] {
      bad_process_ids.push(Json(nodes[node]))
    }
    if bad_realtime_nodes[node] {
      bad_realtime_ids.push(Json(nodes[node]))
    }
  }
  if !bad_process_ids.is_empty() {
    process_gaps.push({
      "code": "inconsistent-process-order-sources",
      "quarantinedTransactions": Json(bad_process_ids),
      "isolation": "unresolved cycle or ambiguous identity nodes; unrelated components retained",
    })
  }
  if !bad_realtime_ids.is_empty() {
    realtime_gaps.push({
      "code": "cyclic-realtime-order-sources",
      "quarantinedTransactions": Json(bad_realtime_ids),
      "isolation": "unresolved order-cycle or downstream nodes; unrelated components retained",
    })
  }
  let edges = indexed.filter(edge => {
    !(edge.order_kind == Some(ScopedProcess) &&
    (bad_process_nodes[edge.from] || bad_process_nodes[edge.to])) &&
    !(edge.order_kind == Some(ScopedRealtime) &&
    (bad_realtime_nodes[edge.from] || bad_realtime_nodes[edge.to]))
  })
  let adjacency : Array[Array[Int32]] = []
  for _ in nodes {
    adjacency.push([])
  }
  for position, edge in edges {
    adjacency[edge.from].push(position)
  }
  let input_record : Json = {
    "format": "moontxnwitness-declared-scoped-graph/v1",
    "nodes": Json(nodes.copy()),
    "dataEdges": Json(raw_data),
    "orderEdges": Json(raw_order),
    "coverage": {
      "dataComplete": Json(data_complete),
      "processComplete": Json(process_complete),
      "realtimeComplete": Json(realtime_complete),
    },
    "gaps": Json(gaps.map(v4_json_copy)),
  }
  let encoded = StringBuilder()
  scoped_sorted_json_v4(input_record, encoded)
  Ok({
    nodes: nodes.copy(),
    edges,
    adjacency,
    input_sha256: v3_dislock_sha256(encoded.to_string()),
    input_record,
    data_complete: data_complete && data_gaps.is_empty(),
    process_complete: process_complete && process_gaps.is_empty(),
    realtime_complete: realtime_complete && realtime_gaps.is_empty(),
    data_gaps,
    process_gaps,
    realtime_gaps,
  })
}

///|
fn scoped_context_complete_v4(
  graph : ScopedDependencyGraphV4,
  context : ScopedOrderContextV4,
) -> Bool {
  graph.data_complete &&
  (match context {
    ScopedDataOnly => true
    ScopedWithProcess => graph.process_complete
    ScopedWithRealtime => graph.realtime_complete
  })
}

///|
fn scoped_context_gaps_v4(
  graph : ScopedDependencyGraphV4,
  context : ScopedOrderContextV4,
) -> Array[Json] {
  let gaps = graph.data_gaps.copy()
  let specific = match context {
    ScopedDataOnly => []
    ScopedWithProcess => graph.process_gaps
    ScopedWithRealtime => graph.realtime_gaps
  }
  for gap in specific {
    gaps.push(gap)
  }
  if !scoped_context_complete_v4(graph, context) {
    gaps.push({
      "code": "scoped-graph-context-not-proved-complete",
      "context": Json(scoped_context_name_v4(context)),
    })
  }
  gaps
}

///|
pub fn scoped_dependency_graph_v4_json(graph : ScopedDependencyGraphV4) -> Json {
  v4_json_copy({
    "input": graph.input_record,
    "inputSha256": Json(graph.input_sha256),
    "inputEncoding": "sorted-json-object-keys-v1; array order and primitive encodings retained",
    "sourceAssurance": "caller-declared scoped relations with structurally bound original references; no database authentication",
    "effectiveEdgeIds": Json(graph.edges.map(edge => Json(edge.id))),
    "derivedCoverage": {
      "dataComplete": Json(graph.data_complete),
      "processComplete": Json(graph.process_complete),
      "realtimeComplete": Json(graph.realtime_complete),
    },
    "dataGaps": Json(graph.data_gaps),
    "processGaps": Json(graph.process_gaps),
    "realtimeGaps": Json(graph.realtime_gaps),
  })
}
