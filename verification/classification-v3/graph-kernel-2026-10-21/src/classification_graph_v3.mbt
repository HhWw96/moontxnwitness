///|
priv struct CgEdge {
  source : Int
  target : Int
  kind : Int
  original : Json
}

///|
priv struct CgBudget {
  limit : Int
  mut scans : Int
  mut exhausted : Bool
}

///|
priv struct CgGraph {
  adj : Array[Array[Int]]
  incoming : Array[Array[Int]]
  source : Array[Int]
  target : Array[Int]
  original : Array[Int]
  product : Bool
}

///|
fn cg_tick(b : CgBudget) -> Bool {
  if b.scans >= b.limit {
    b.exhausted = true
    return false
  }
  b.scans += 1
  true
}

///|
fn cg_add(g : CgGraph, u : Int, v : Int, original : Int) -> Unit {
  let index = g.source.length()
  g.source.push(u)
  g.target.push(v)
  g.original.push(original)
  g.adj[u].push(index)
  g.incoming[v].push(index)
}

///|
fn cg_build(
  nodes : Int,
  edges : Array[CgEdge],
  mode : Int,
  b : CgBudget,
) -> CgGraph {
  // 0=WW, 1=D, 2=ordinary, 3=all, 4=RT, 5=nonadjacency product.
  let count = if mode == 5 { nodes * 2 } else { nodes }
  let adj : Array[Array[Int]] = []
  let incoming : Array[Array[Int]] = []
  for _ in 0..<count {
    adj.push([])
    incoming.push([])
  }
  let g = {
    adj,
    incoming,
    source: [],
    target: [],
    original: [],
    product: mode == 5,
  }
  for i, e in edges {
    if !cg_tick(b) {
      break
    }
    let allowed_kind = match mode {
      0 => e.kind == 0
      1 => e.kind < 2
      2 | 5 => e.kind < 4
      3 => true
      _ => e.kind == 4
    }
    if !allowed_kind {
      continue
    }
    if mode == 5 {
      if e.kind < 2 {
        cg_add(g, e.source * 2, e.target * 2, i)
        cg_add(g, e.source * 2 + 1, e.target * 2, i)
      } else {
        cg_add(g, e.source * 2, e.target * 2 + 1, i)
      }
    } else {
      cg_add(g, e.source, e.target, i)
    }
  }
  g
}

///|
fn cg_components(g : CgGraph, b : CgBudget) -> Array[Int] {
  let n = g.adj.length()
  let seen = Array::make(n, false)
  let order : Array[Int] = []
  let stack : Array[Int] = []
  let cursors : Array[Int] = []
  for start in 0..<n {
    if seen[start] {
      continue
    }
    seen[start] = true
    stack.push(start)
    cursors.push(0)
    while !stack.is_empty() {
      let top = stack.length() - 1
      let v = stack[top]
      let next = cursors[top]
      if next == g.adj[v].length() {
        ignore(stack.pop())
        ignore(cursors.pop())
        order.push(v)
      } else {
        if !cg_tick(b) {
          return []
        }
        cursors[top] = next + 1
        let w = g.target[g.adj[v][next]]
        if !seen[w] {
          seen[w] = true
          stack.push(w)
          cursors.push(0)
        }
      }
    }
  }
  let groups = Array::make(n, -1)
  let mut group = 0
  for i in 0..<order.length() {
    let start = order[order.length() - 1 - i]
    if groups[start] >= 0 {
      continue
    }
    groups[start] = group
    stack.push(start)
    while !stack.is_empty() {
      let v = stack.pop().unwrap()
      for ei in g.incoming[v] {
        if !cg_tick(b) {
          return []
        }
        let w = g.source[ei]
        if groups[w] < 0 {
          groups[w] = group
          stack.push(w)
        }
      }
    }
    group += 1
  }
  groups
}

///|
fn cg_path(
  g : CgGraph,
  groups : Array[Int],
  start : Int,
  finish : Int,
  b : CgBudget,
) -> Array[Int] {
  if start == finish {
    return []
  }
  let seen = Array::make(g.adj.length(), false)
  let parent = Array::make(g.adj.length(), -1)
  let queue : Array[Int] = [start]
  seen[start] = true
  let mut head = 0
  while head < queue.length() {
    let v = queue[head]
    head += 1
    for ei in g.adj[v] {
      if !cg_tick(b) {
        return []
      }
      let w = g.target[ei]
      if groups[w] != groups[start] || seen[w] {
        continue
      }
      seen[w] = true
      parent[w] = ei
      if w == finish {
        let out : Array[Int] = []
        let mut current = finish
        while current != start {
          if !cg_tick(b) {
            return []
          }
          let edge = parent[current]
          out.push(edge)
          current = g.source[edge]
        }
        out.rev_in_place()
        return out
      }
      queue.push(w)
    }
  }
  []
}

///|
fn cg_category(
  g : CgGraph,
  groups : Array[Int],
  edges : Array[CgEdge],
  marked : Int,
  b : CgBudget,
  complete : Bool,
) -> Json {
  if b.exhausted {
    return { "status": "inconclusive", "reason": "edge_scan_budget" }
  }
  for i, original in g.original {
    if !cg_tick(b) {
      return { "status": "inconclusive", "reason": "edge_scan_budget" }
    }
    let kind = edges[original].kind
    let is_marked = marked < 0 ||
      (marked == 2 && kind == 2) ||
      (marked == 3 && (kind == 2 || kind == 3))
    if !is_marked || groups[g.source[i]] != groups[g.target[i]] {
      continue
    }
    let tail = cg_path(g, groups, g.target[i], g.source[i], b)
    if b.exhausted {
      return { "status": "inconclusive", "reason": "edge_scan_budget" }
    }
    let arcs = [i]
    for edge in tail {
      arcs.push(edge)
    }
    let walk : Array[Json] = []
    let states : Array[Int] = [g.source[i]]
    for arc in arcs {
      if !cg_tick(b) {
        return { "status": "inconclusive", "reason": "edge_scan_budget" }
      }
      walk.push(edges[g.original[arc]].original)
      states.push(g.target[arc])
    }
    let macros : Array[Json] = []
    if g.product {
      let mut rotation = 0
      for j in 0..<arcs.length() {
        if !cg_tick(b) {
          return { "status": "inconclusive", "reason": "edge_scan_budget" }
        }
        if edges[g.original[arcs[j]]].kind < 2 {
          rotation = j
          break
        }
      }
      let mut j = 0
      while j < arcs.length() {
        if !cg_tick(b) {
          return { "status": "inconclusive", "reason": "edge_scan_budget" }
        }
        let first = edges[g.original[arcs[(rotation + j) % arcs.length()]]]
        let parts = [first.original]
        j += 1
        if j < arcs.length() {
          if !cg_tick(b) {
            return { "status": "inconclusive", "reason": "edge_scan_budget" }
          }
          let second = edges[g.original[arcs[(rotation + j) % arcs.length()]]]
          if second.kind == 2 || second.kind == 3 {
            parts.push(second.original)
            j += 1
          }
        }
        macros.push({ "parts": parts.to_json() })
      }
    }
    return {
      "status": "cycle",
      "edges": walk.to_json(),
      "states": states.to_json(),
      "productGraph": g.product.to_json(),
      "shortest": false,
      "expandedClosedWalk": g.product.to_json(),
      "macroSteps": macros.to_json(),
    }
  }
  if complete {
    {
      "status": "acyclic",
      "componentByState": groups.to_json(),
      "productGraph": g.product.to_json(),
    }
  } else {
    { "status": "inconclusive", "reason": "incomplete_supplied_graph" }
  }
}

///|
fn cg_run(
  nodes : Int,
  edges : Array[CgEdge],
  mode : Int,
  marked : Int,
  b : CgBudget,
  complete : Bool,
) -> Json {
  if b.exhausted {
    return { "status": "inconclusive", "reason": "edge_scan_budget" }
  }
  let g = cg_build(nodes, edges, mode, b)
  let groups = cg_components(g, b)
  cg_category(g, groups, edges, marked, b, complete)
}

///|
fn cg_status(result : Json) -> String {
  match result {
    Object(m) =>
      match m.get("status") {
        Some(String(s)) => s
        _ => "inconclusive"
      }
    _ => "inconclusive"
  }
}

///|
fn cg_combined(a : Json, b : Json) -> String {
  if cg_status(a) == "cycle" || cg_status(b) == "cycle" {
    "cycle"
  } else if cg_status(a) == "acyclic" && cg_status(b) == "acyclic" {
    "acyclic"
  } else {
    "inconclusive"
  }
}

///|
pub fn classification_graph_v3_json(text : String) -> String {
  try {
    let root = object_fields(guarded_json(text, limit=8388608), "graph")
    known_fields(root, ["nodes", "edges", "complete", "budgets"], "graph")
    let nodes = match required(root, "nodes", "graph") {
      Array(a) => a
      _ => fail("nodes must be array")
    }
    if nodes.length() > 512 {
      fail("at most 512 nodes")
    }
    let index : Map[String, Int] = Map([])
    for i, node in nodes {
      let id = identifier(node, "node")
      if index.contains(id) {
        fail("duplicate node")
      }
      index[id] = i
    }
    let complete = match required(root, "complete", "graph") {
      True => true
      False => false
      _ => fail("complete must be boolean")
    }
    let raw = match required(root, "edges", "graph") {
      Array(a) => a
      _ => fail("edges must be array")
    }
    if raw.length() > 100000 {
      fail("at most 100000 original edges")
    }
    let edge_ids : Map[String, Bool] = Map([])
    let edges : Array[CgEdge] = []
    for value in raw {
      let e = object_fields(value, "edge")
      known_fields(e, ["id", "from", "to", "kind", "source"], "edge")
      let id = identifier(required(e, "id", "edge"), "edge.id")
      if edge_ids.contains(id) {
        fail("duplicate edge identity")
      }
      edge_ids[id] = true
      let from = identifier(required(e, "from", "edge"), "edge.from")
      let to = identifier(required(e, "to", "edge"), "edge.to")
      let source = match index.get(from) {
        Some(i) => i
        None => fail("unknown source node")
      }
      let target = match index.get(to) {
        Some(i) => i
        None => fail("unknown target node")
      }
      if source == target {
        fail("self dependency is invalid")
      }
      let kind = match required(e, "kind", "edge") {
        String("ww") => 0
        String("wr") => 1
        String("rw-item") => 2
        String("rw-predicate") => 3
        String("rt") => 4
        _ => fail("unsupported dependency kind")
      }
      edges.push({ source, target, kind, original: value, })
    }
    let mut limit = 1000000
    match root.get("budgets") {
      None => ()
      Some(j) => {
        let m = object_fields(j, "budgets")
        known_fields(m, ["maxEdgeScans"], "budgets")
        match required(m, "maxEdgeScans", "budgets") {
          Number(n, ..) if n >= 0.0 &&
            n <= 1000000.0 &&
            n.to_int().to_double() == n => limit = n.to_int()
          _ => fail("maxEdgeScans must be integer 0..1000000")
        }
      }
    }
    let budget = { limit, scans: 0, exhausted: false, }
    let rt = cg_run(nodes.length(), edges, 4, -1, budget, true)
    if cg_status(rt) == "cycle" {
      fail("RT must be a strict acyclic relation")
    }
    let ww = cg_run(nodes.length(), edges, 0, -1, budget, complete)
    let dependency = cg_run(nodes.length(), edges, 1, -1, budget, complete)
    let ordinary = cg_build(nodes.length(), edges, 2, budget)
    let components = cg_components(ordinary, budget)
    let item = cg_category(ordinary, components, edges, 2, budget, complete)
    let any_rw = cg_category(ordinary, components, edges, 3, budget, complete)
    let nonadjacent = cg_run(nodes.length(), edges, 5, 3, budget, complete)
    let strict = cg_run(nodes.length(), edges, 3, -1, budget, complete)
    let constraints : Json = {
      "adya-pl-1-v1": cg_status(ww).to_json(),
      "adya-pl-2-v1": cg_status(dependency).to_json(),
      "adya-pl-2.99-v1": cg_combined(dependency, item).to_json(),
      "elle-generalized-si-v1": cg_combined(dependency, nonadjacent).to_json(),
      "adya-pl-3-v1": cg_combined(dependency, any_rw).to_json(),
      "strict-pl-ss-v1": cg_status(strict).to_json(),
    }
    (
      {
        "schemaVersion": 3,
        "algorithm": "typed-dependency-product-draft-1",
        "valid": true,
        "graphOnly": true,
        "modelCoverageAccepted": false,
        "databaseAuthenticityVerified": false,
        "suppliedGraphComplete": complete.to_json(),
        "sourceDerivationVerified": false,
        "directSourceAndIntChecked": false,
        "definitionsFrozen": false,
        "categories": {
          "ww": ww,
          "wr-ww": dependency,
          "item-rw": item,
          "any-rw": any_rw,
          "nonadjacent-rw": nonadjacent,
          "strict-graph": strict,
        },
        "graphConstraints": constraints,
        "execution": {
          "maxEdgeScans": limit.to_json(),
          "edgeScans": budget.scans.to_json(),
          "budgetExhausted": budget.exhausted.to_json(),
          "scope": "filter, traversal, parent/proof-edge recovery and macro visits; excludes input parsing and final JSON encoding",
        },
      } : Json).stringify()
  } catch {
    error =>
      (
        {
          "schemaVersion": 3,
          "algorithm": "typed-dependency-product-draft-1",
          "valid": false,
          "reason": error.to_string().to_json(),
          "modelCoverageAccepted": false,
        } : Json).stringify()
  }
}
