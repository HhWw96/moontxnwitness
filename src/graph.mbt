///|
priv struct GraphIndex {
  adj : FixedArray[FixedArray[Int32]]
  sources : FixedArray[Int32]
  targets : FixedArray[Int32]
}

///|
// Internal empty neighbors have no writable index and never hold input data.
let empty_graph_neighbors : FixedArray[Int32] = FixedArray::make(0, 0)

///|
fn adjacency(txs : Array[Transaction], edges : Array[Edge]) -> GraphIndex {
  let index : Map[String, Int32] = Map([])
  for i, tx in txs {
    index[tx.id] = i
  }
  let sizes = FixedArray::make(txs.length(), 0)
  let sources = FixedArray::make(edges.length(), 0)
  let targets = FixedArray::make(edges.length(), 0)
  for ei, edge in edges {
    let source = index.at(edge.from)
    sources[ei] = source
    targets[ei] = index.at(edge.to)
    sizes[source] += 1
  }
  let adj = FixedArray::makei(txs.length(), i => {
    if sizes[i] == 0 {
      empty_graph_neighbors
    } else {
      FixedArray::make(sizes[i], 0)
    }
  })
  let used = FixedArray::make(txs.length(), 0)
  // Fill in the same original edge order as append-based adjacency. Each edge
  // occurs once with identical sources/targets, preserving Tarjan/BFS/topology
  // traversal, ties, counters and complete provenance. Exact capacities avoid
  // dynamic backing-array growth; no typed-array representation is assumed.
  for ei, source in sources {
    adj[source][used[source]] = ei
    used[source] += 1
  }
  { adj, sources, targets, }
}

///| Breadth-first search from every node finds a globally shortest directed cycle.

///|
/// It minimizes dependency edges / distinct transactions, not the entire source history.
fn shortest_cycle(
  txs : Array[Transaction],
  edges : Array[Edge],
  prepared~ : GraphIndex = adjacency(txs, edges),
) -> (Array[Edge], GraphInfo) {
  let g = prepared
  let n = txs.length()
  let components = strongly_connected(txs, g)
  let mut cyclic_components = 0
  let mut cyclic_transactions = 0
  for size in components.sizes {
    if size > 1 {
      cyclic_components += 1
      cyclic_transactions += size
    }
  }
  let mut bfs_roots = 0
  let mut best : Array[Edge] = []
  let mut best_length = n + 1
  let distance = Array::make(n, 0)
  let parent = Array::make(n, -1)
  let seen = Array::make(n, 0)
  let queue = Array::make(n, 0)
  for start in 0..<n {
    let component = components.groups[start]
    if component < 0 || components.sizes[component] < 2 {
      continue
    }
    bfs_roots += 1
    let epoch = start + 1
    queue[0] = start
    let mut tail = 1
    seen[start] = epoch
    distance[start] = 0
    let mut head = 0
    let mut found = false
    while head < tail && !found {
      let v = queue[head]
      head += 1
      if distance[v] + 1 >= best_length {
        break
      }
      for ei in g.adj[v] {
        let w = g.targets[ei]
        if components.groups[w] != component {
          continue
        }
        if w == start {
          let path = [edges[ei]]
          let mut current = v
          while current != start {
            let p = parent[current]
            path.push(edges[p])
            current = g.sources[p]
          }
          path.rev_in_place()
          best = path
          best_length = path.length()
          found = true
          break
        }
        if seen[w] != epoch {
          seen[w] = epoch
          distance[w] = distance[v] + 1
          parent[w] = ei
          queue[tail] = w
          tail += 1
        }
      }
    }
    if best_length == 2 {
      break
    }
  }
  (
    best,
    {
      analyzed: true,
      components: components.sizes.length(),
      cyclic_components,
      cyclic_transactions,
      bfs_roots,
      edge_budget_exceeded: false,
    },
  )
}

///|
priv struct Components {
  indices : Array[Int32]
  low : Array[Int32]
  active : Array[Bool]
  stack : Array[Int32]
  groups : Array[Int32]
  sizes : Array[Int32]
  mut next : Int32
}

///|
fn component_visit(v : Int32, ctx : Components, g : GraphIndex) -> Unit {
  ctx.indices[v] = ctx.next
  ctx.low[v] = ctx.next
  ctx.next += 1
  ctx.stack.push(v)
  ctx.active[v] = true
  for ei in g.adj[v] {
    let w = g.targets[ei]
    if ctx.indices[w] < 0 {
      component_visit(w, ctx, g)
      if ctx.low[w] < ctx.low[v] {
        ctx.low[v] = ctx.low[w]
      }
    } else if ctx.active[w] && ctx.indices[w] < ctx.low[v] {
      ctx.low[v] = ctx.indices[w]
    }
  }
  if ctx.low[v] == ctx.indices[v] {
    let mut count = 0
    while true {
      let w = match ctx.stack.pop() {
        Some(w) => w
        None => abort("component stack")
      }
      ctx.active[w] = false
      ctx.groups[w] = ctx.sizes.length()
      count += 1
      if w == v {
        break
      }
    }
    ctx.sizes.push(count)
  }
}

///|
fn strongly_connected(txs : Array[Transaction], g : GraphIndex) -> Components {
  let n = txs.length()
  let ctx : Components = {
    indices: Array::make(n, -1),
    low: Array::make(n, -1),
    active: Array::make(n, false),
    stack: [],
    groups: Array::make(n, -1),
    sizes: [],
    next: 0,
  }
  for i, tx in txs {
    if tx.status == Committed && ctx.indices[i] < 0 {
      component_visit(i, ctx, g)
    }
  }
  ctx
}

///|
fn topology_ready_push(ready : Array[Int32], value : Int32) -> Unit {
  let mut child = ready.length()
  ready.push(value)
  while child > 0 {
    let parent = (child - 1) / 2
    if ready[parent] <= value {
      break
    }
    ready[child] = ready[parent]
    child = parent
  }
  ready[child] = value
}

///|
fn topology_ready_pop(ready : Array[Int32]) -> Int32 {
  let next = ready[0]
  let last = match ready.pop() {
    Some(value) => value
    None => abort("Empty topology ready queue")
  }
  if !ready.is_empty() {
    let mut parent = 0
    while parent * 2 + 1 < ready.length() {
      let left = parent * 2 + 1
      let right = left + 1
      let child = if right < ready.length() && ready[right] < ready[left] {
        right
      } else {
        left
      }
      if last <= ready[child] {
        break
      }
      ready[parent] = ready[child]
      parent = child
    }
    ready[parent] = last
  }
  next
}

///|
fn topological_order(
  txs : Array[Transaction],
  edges : Array[Edge],
  prepared~ : GraphIndex = adjacency(txs, edges),
) -> Array[String] {
  let g = prepared
  let degree = Array::make(txs.length(), 0)
  for target in g.targets {
    degree[target] += 1
  }
  // Original array indices define the existing deterministic tie order. A
  // min-heap selects that same first ready transaction without rescanning all
  // previously emitted transactions for every result element.
  let ready : Array[Int32] = []
  for i, tx in txs {
    if tx.status == Committed && degree[i] == 0 {
      topology_ready_push(ready, i)
    }
  }
  let result : Array[String] = []
  while !ready.is_empty() {
    let next = topology_ready_pop(ready)
    result.push(txs[next].id)
    for ei in g.adj[next] {
      let target = g.targets[ei]
      degree[target] -= 1
      if degree[target] == 0 && txs[target].status == Committed {
        topology_ready_push(ready, target)
      }
    }
  }
  result
}
