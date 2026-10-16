///|
priv struct GraphIndex {
  adj : Array[Array[Int]]
  sources : Array[Int]
  targets : Array[Int]
}

///|
fn adjacency(txs : Array[Transaction], edges : Array[Edge]) -> GraphIndex {
  let index : Map[String, Int] = Map([])
  let adj : Array[Array[Int]] = []
  for i, tx in txs {
    index[tx.id] = i
    adj.push([])
  }
  let sources : Array[Int] = []
  let targets : Array[Int] = []
  for ei, edge in edges {
    let source = index.at(edge.from)
    sources.push(source)
    targets.push(index.at(edge.to))
    adj[source].push(ei)
  }
  { adj, sources, targets, }
}

///| Breadth-first search from every node finds a globally shortest directed cycle.

///|
/// It minimizes dependency edges / distinct transactions, not the entire source history.
fn shortest_cycle(
  txs : Array[Transaction],
  edges : Array[Edge],
  prepared? : GraphIndex = adjacency(txs, edges),
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
  indices : Array[Int]
  low : Array[Int]
  active : Array[Bool]
  stack : Array[Int]
  groups : Array[Int]
  sizes : Array[Int]
  mut next : Int
}

///|
fn component_visit(v : Int, ctx : Components, g : GraphIndex) -> Unit {
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
fn topological_order(
  txs : Array[Transaction],
  edges : Array[Edge],
  prepared? : GraphIndex = adjacency(txs, edges),
) -> Array[String] {
  let g = prepared
  let degree = Array::make(txs.length(), 0)
  for target in g.targets {
    degree[target] += 1
  }
  let used = Array::make(txs.length(), false)
  let result : Array[String] = []
  for _i in 0..<txs.length() {
    let mut next = -1
    for i, tx in txs {
      if tx.status == Committed && !used[i] && degree[i] == 0 {
        next = i
        break
      }
    }
    if next == -1 {
      break
    }
    used[next] = true
    result.push(txs[next].id)
    for ei in g.adj[next] {
      degree[g.targets[ei]] -= 1
    }
  }
  result
}
