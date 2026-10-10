///|
fn adjacency(
  txs : Array[Transaction],
  edges : Array[Edge],
) -> (Map[String, Int], Array[Array[Int]]) {
  let index : Map[String, Int] = Map([])
  let adj : Array[Array[Int]] = []
  for i, tx in txs {
    index[tx.id] = i
    adj.push([])
  }
  for ei, edge in edges {
    adj[index.at(edge.from)].push(ei)
  }
  (index, adj)
}

///| Breadth-first search from every node finds a globally shortest directed cycle.

///|
/// It minimizes dependency edges / distinct transactions, not the entire source history.
fn shortest_cycle(
  txs : Array[Transaction],
  edges : Array[Edge],
) -> (Array[Edge], GraphInfo) {
  let (index, adj) = adjacency(txs, edges)
  let n = txs.length()
  let components = strongly_connected(txs, edges, index, adj)
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
  for start in 0..<n {
    let component = components.groups[start]
    if component < 0 || components.sizes[component] < 2 {
      continue
    }
    bfs_roots += 1
    let distance = Array::make(n, -1)
    let parent = Array::make(n, -1)
    let queue = [start]
    distance[start] = 0
    let mut head = 0
    let mut found = false
    while head < queue.length() && !found {
      let v = queue[head]
      head += 1
      if distance[v] + 1 >= best_length {
        break
      }
      for ei in adj[v] {
        let w = index.at(edges[ei].to)
        if components.groups[w] != component {
          continue
        }
        if w == start {
          let path = [edges[ei]]
          let mut current = v
          while current != start {
            let p = parent[current]
            path.push(edges[p])
            current = index.at(edges[p].from)
          }
          path.rev_in_place()
          best = path
          best_length = path.length()
          found = true
          break
        }
        if distance[w] == -1 {
          distance[w] = distance[v] + 1
          parent[w] = ei
          queue.push(w)
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
fn component_visit(
  v : Int,
  ctx : Components,
  edges : Array[Edge],
  index : Map[String, Int],
  adj : Array[Array[Int]],
) -> Unit {
  ctx.indices[v] = ctx.next
  ctx.low[v] = ctx.next
  ctx.next += 1
  ctx.stack.push(v)
  ctx.active[v] = true
  for ei in adj[v] {
    let w = index.at(edges[ei].to)
    if ctx.indices[w] < 0 {
      component_visit(w, ctx, edges, index, adj)
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
fn strongly_connected(
  txs : Array[Transaction],
  edges : Array[Edge],
  index : Map[String, Int],
  adj : Array[Array[Int]],
) -> Components {
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
      component_visit(i, ctx, edges, index, adj)
    }
  }
  ctx
}

///|
fn topological_order(
  txs : Array[Transaction],
  edges : Array[Edge],
) -> Array[String] {
  let (index, adj) = adjacency(txs, edges)
  let degree = Array::make(txs.length(), 0)
  for e in edges {
    degree[index.at(e.to)] += 1
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
    for ei in adj[next] {
      degree[index.at(edges[ei].to)] -= 1
    }
  }
  result
}
