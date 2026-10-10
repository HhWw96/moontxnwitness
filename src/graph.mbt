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
fn shortest_cycle(txs : Array[Transaction], edges : Array[Edge]) -> Array[Edge] {
  let (index, adj) = adjacency(txs, edges)
  let n = txs.length()
  let mut best : Array[Edge] = []
  let mut best_length = n + 1
  for start in 0..<n {
    if adj[start].is_empty() {
      continue
    }
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
  best
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
