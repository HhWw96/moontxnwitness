///|
/// A G-single witness has one item anti-dependency and otherwise only WW/WR.
/// This entry point accepts only point-register/append-list item graphs.
/// Seed each RW independently, then find a WW/WR path back to its source.
/// The path search cannot traverse a second RW or a real-time edge.
fn g_single_cycle_v4(
  node_count : Int32,
  edges : Array[Edge],
  graph : GraphIndex,
  budget : ClassificationV3Budget,
) -> Array[Edge] {
  let seen = FixedArray::make(node_count, 0)
  let parent = FixedArray::make(node_count, -1)
  let queue = FixedArray::make(node_count, 0)
  let mut epoch = 0
  for seed_index, seed in edges {
    if !classification_v3_charge_edge(budget) {
      return []
    }
    if seed.kind != RW {
      continue
    }
    let start = graph.targets[seed_index]
    let target = graph.sources[seed_index]
    // Own-transaction effects are handled by internal-consistency checks.
    if start == target {
      continue
    }
    epoch += 1
    queue[0] = start
    seen[start] = epoch
    let mut head = 0
    let mut tail = 1
    while head < tail {
      if !classification_v3_charge_state(budget) {
        return []
      }
      let vertex = queue[head]
      head += 1
      for edge_index in graph.adj[vertex] {
        if !classification_v3_charge_edge(budget) {
          return []
        }
        let edge = edges[edge_index]
        if edge.kind != WW && edge.kind != WR {
          continue
        }
        let next = graph.targets[edge_index]
        if next == target {
          let backward = [edge]
          let mut current = vertex
          while current != start {
            let previous = parent[current]
            backward.push(edges[previous])
            current = graph.sources[previous]
          }
          backward.rev_in_place()
          let cycle = [seed]
          for edge in backward {
            cycle.push(edge)
          }
          return cycle
        }
        if seen[next] != epoch {
          seen[next] = epoch
          parent[next] = edge_index
          queue[tail] = next
          tail += 1
        }
      }
    }
  }
  []
}

///|
fn g_single_category_witness_v4(witness : Json, cycle : Array[Edge]) -> Json {
  let fields = object_fields_unchecked_v3(witness)
  fields["specificCategory"] = Json("G-single-item")
  fields["requestedCategory"] = Json("G-single")
  fields["rwScope"] = Json("item")
  fields["rwEdgeCount"] = Json(cycle.filter(edge => edge.kind == RW).length())
  fields["cycleRule"] = Json("exactly-one-item-rw-and-only-ww-wr-remainder/v1")
  witness
}
