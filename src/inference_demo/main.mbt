///|
// A caller-owned data model; it is deliberately independent of SQL and trace JSON.
enum Observation {
  Read(String, String, String)
  Write(String, String, String, String)
}

///|
fn original(sequence : Int32, observation : Observation) -> Json {
  match observation {
    Read(tx, key, version) =>
      {
        "adapter": "example-unique-version-register/v1",
        "sequence": Json(sequence),
        "transaction": Json(tx),
        "kind": "read",
        "key": Json(key),
        "version": Json(version),
      }
    Write(tx, key, version, predecessor) =>
      {
        "adapter": "example-unique-version-register/v1",
        "sequence": Json(sequence),
        "transaction": Json(tx),
        "kind": "write",
        "key": Json(key),
        "version": Json(version),
        "predecessor": Json(predecessor),
      }
  }
}

///|
fn infer_read_sources(
  observations : Array[Observation],
) -> Array[@txn.ScopedDataEdgeInputV4] {
  let edges : Array[@txn.ScopedDataEdgeInputV4] = []
  for ri, observation in observations {
    guard observation is Read(reader, key, version) else { continue }
    for wi, candidate in observations {
      guard candidate is Write(writer, written_key, written_version, _) else {
        continue
      }
      if reader != writer && key == written_key && version == written_version {
        edges.push({
          id: "read-source-" + ri.to_string() + "-" + wi.to_string(),
          from: writer,
          to: reader,
          kind: @txn.ScopedWRItem,
          sources: [original(wi, candidate), original(ri, observation)],
        })
      }
    }
  }
  edges
}

///|
fn infer_predecessors(
  observations : Array[Observation],
) -> Array[@txn.ScopedDataEdgeInputV4] {
  let edges : Array[@txn.ScopedDataEdgeInputV4] = []
  for wi, observation in observations {
    guard observation is Write(writer, key, _, predecessor) else { continue }
    for oi, previous in observations {
      let dependency = match previous {
        Write(other, other_key, version, _) if other != writer &&
          other_key == key &&
          version == predecessor => Some((other, @txn.ScopedWWItem))
        Read(other, other_key, version) if other != writer &&
          other_key == key &&
          version == predecessor => Some((other, @txn.ScopedRWItem))
        _ => None
      }
      if dependency is Some((other, kind)) {
        edges.push({
          id: "predecessor-" + wi.to_string() + "-" + oi.to_string(),
          from: other,
          to: writer,
          kind,
          sources: [original(oi, previous), original(wi, observation)],
        })
      }
    }
  }
  edges
}

///|
fn main {
  // These are declared committed observations, with unique x0/x1 and y0/y1
  // versions and a closed initial state. This example is not a DB collector.
  let observations = [
    Read("A", "x", "x0"),
    Write("A", "y", "y1", "y0"),
    Read("B", "y", "y0"),
    Write("B", "x", "x1", "x0"),
    Read("B", "y", "y1"),
  ]
  let edges = infer_read_sources(observations)
  for edge in infer_predecessors(observations) {
    edges.push(edge)
  }
  let graph = @txn.scoped_dependency_graph_v4(
    ["A", "B"],
    edges,
    data_complete=true,
  ).unwrap()
  let result = @txn.search_scoped_category_v4(
    graph,
    @txn.ScopedG2Item,
    rule_set=@txn.ElleFixed4e359e5,
  )
  let record = @txn.scoped_search_v4_json(result)
  if result.status() != "refuted" ||
    !@txn.verify_scoped_category_v4(
      graph,
      record,
      @txn.ScopedG2Item,
      rule_set=@txn.ElleFixed4e359e5,
    ) {
    abort("Composed dependency inference must produce a verified item cycle")
  }
  let unfinished = @txn.search_scoped_category_v4(
    graph,
    @txn.ScopedG2Item,
    rule_set=@txn.ElleFixed4e359e5,
    max_states=0,
  )
  if unfinished.status() != "unknown" {
    abort("Exhausted inference/search cannot assert compatibility")
  }
  println(record.stringify())
}
