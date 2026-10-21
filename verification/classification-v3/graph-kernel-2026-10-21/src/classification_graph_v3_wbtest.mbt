///|
fn cg_test_doc(
  edges : Array[(String, String, String)],
  complete? : Bool = true,
  limit? : Int = 1000000,
) -> Json {
  let raw : Array[Json] = []
  for i, (from, to, kind) in edges {
    raw.push({
      "id": ("e" + i.to_string()).to_json(),
      "from": from.to_json(),
      "to": to.to_json(),
      "kind": kind.to_json(),
      "source": { "observation": (i + 10).to_json() },
    })
  }
  {
    "nodes": ["A", "B", "C", "D", "E"],
    "edges": raw.to_json(),
    "complete": complete.to_json(),
    "budgets": { "maxEdgeScans": limit.to_json() },
  }
}

///|
fn cg_test_result(doc : Json) -> Map[String, Json] raise {
  object_fields(
    guarded_json(classification_graph_v3_json(doc.stringify())),
    "result",
  )
}

///|
fn cg_test_model(doc : Json, model : String) -> Json raise {
  let r = cg_test_result(doc)
  object_fields(r.at("graphConstraints"), "constraints").at(model)
}

///|
test "classification WW-only cycle also refutes RC graph constraint" {
  let d = cg_test_doc([("A", "B", "ww"), ("B", "A", "ww")])
  assert_eq(cg_test_model(d, "adya-pl-1-v1"), "cycle".to_json())
  assert_eq(cg_test_model(d, "adya-pl-2-v1"), "cycle".to_json())
}

///|
test "classification WR cycle preserves weaker WW absence" {
  let d = cg_test_doc([("A", "B", "wr"), ("B", "A", "wr")])
  assert_eq(cg_test_model(d, "adya-pl-1-v1"), "acyclic".to_json())
  assert_eq(cg_test_model(d, "adya-pl-2-v1"), "cycle".to_json())
}

///|
test "classification adjacent item RW cycle allowed by SI graph constraint" {
  let d = cg_test_doc([("A", "B", "rw-item"), ("B", "A", "rw-item")])
  assert_eq(cg_test_model(d, "adya-pl-2.99-v1"), "cycle".to_json())
  assert_eq(cg_test_model(d, "elle-generalized-si-v1"), "acyclic".to_json())
  assert_eq(cg_test_model(d, "adya-pl-3-v1"), "cycle".to_json())
}

///|
test "classification predicate-only cycle does not invent an item edge" {
  let d = cg_test_doc([("A", "B", "rw-predicate"), ("B", "A", "rw-predicate")])
  assert_eq(cg_test_model(d, "adya-pl-2.99-v1"), "acyclic".to_json())
  assert_eq(cg_test_model(d, "adya-pl-3-v1"), "cycle".to_json())
}

///|
test "classification item category retains mixed predicate return path" {
  let d = cg_test_doc([("A", "B", "rw-item"), ("B", "A", "rw-predicate")])
  assert_eq(cg_test_model(d, "adya-pl-2.99-v1"), "cycle".to_json())
  assert_eq(cg_test_model(d, "elle-generalized-si-v1"), "acyclic".to_json())
}

///|
test "classification separated RW steps refute SI graph constraint" {
  let d = cg_test_doc([
    ("A", "B", "rw-item"),
    ("B", "C", "wr"),
    ("C", "D", "rw-predicate"),
    ("D", "A", "ww"),
  ])
  assert_eq(cg_test_model(d, "elle-generalized-si-v1"), "cycle".to_json())
  let cats = object_fields(cg_test_result(d).at("categories"), "categories")
  let proof = object_fields(cats.at("nonadjacent-rw"), "proof")
  assert_eq(proof.at("expandedClosedWalk"), true.to_json())
  match proof.at("macroSteps") {
    Array(a) => assert_eq(a.length(), 2)
    _ => fail("macro steps missing")
  }
}

///|
test "classification allowed shortest cycle does not hide longer forbidden SI cycle" {
  let d = cg_test_doc([
    ("A", "B", "rw-item"),
    ("B", "A", "rw-item"),
    ("A", "C", "rw-item"),
    ("C", "D", "wr"),
    ("D", "E", "rw-item"),
    ("E", "A", "wr"),
  ])
  assert_eq(cg_test_model(d, "elle-generalized-si-v1"), "cycle".to_json())
}

///|
test "classification RT only strengthens strict graph constraint" {
  let d = cg_test_doc([("A", "B", "rt"), ("B", "A", "wr")])
  assert_eq(cg_test_model(d, "adya-pl-3-v1"), "acyclic".to_json())
  assert_eq(cg_test_model(d, "elle-generalized-si-v1"), "acyclic".to_json())
  assert_eq(cg_test_model(d, "strict-pl-ss-v1"), "cycle".to_json())
}

///|
test "classification cyclic RT relation is invalid" {
  let d = cg_test_doc([("A", "B", "rt"), ("B", "A", "rt")])
  assert_eq(cg_test_result(d).at("valid"), false.to_json())
}

///|
test "classification hand counted exact edge scan budget" {
  let d = cg_test_doc([("A", "B", "ww")], limit=25)
  let r = cg_test_result(d)
  let execution = object_fields(r.at("execution"), "execution")
  assert_eq(execution.at("edgeScans"), (25 : Int).to_json())
  assert_eq(execution.at("budgetExhausted"), false.to_json())
  assert_eq(cg_test_model(d, "strict-pl-ss-v1"), "acyclic".to_json())
}

///|
test "classification final required scan cannot exceed budget" {
  let d = cg_test_doc([("A", "B", "ww")], limit=24)
  let r = cg_test_result(d)
  let execution = object_fields(r.at("execution"), "execution")
  assert_eq(execution.at("edgeScans"), (24 : Int).to_json())
  assert_eq(execution.at("budgetExhausted"), true.to_json())
  assert_eq(cg_test_model(d, "strict-pl-ss-v1"), "inconclusive".to_json())
}

///|
test "classification zero scan budget does not claim nonempty graph absence" {
  let d = cg_test_doc([("A", "B", "ww")], limit=0)
  let m = object_fields(cg_test_result(d).at("graphConstraints"), "models")
  for _, value in m {
    assert_eq(value, "inconclusive".to_json())
  }
}

///|
test "classification empty supplied graph needs no edge scans" {
  let d = cg_test_doc([], limit=0)
  assert_eq(cg_test_model(d, "strict-pl-ss-v1"), "acyclic".to_json())
}

///|
test "classification incomplete graph has no absence claim" {
  let d = cg_test_doc([("A", "B", "ww")], complete=false)
  let m = object_fields(cg_test_result(d).at("graphConstraints"), "models")
  for _, value in m {
    assert_eq(value, "inconclusive".to_json())
  }
}

///|
test "classification parallel edge types retain source records" {
  let d = cg_test_doc([
    ("A", "B", "rw-predicate"),
    ("A", "B", "ww"),
    ("B", "A", "rw-item"),
  ])
  let cats = object_fields(cg_test_result(d).at("categories"), "categories")
  let proof = object_fields(cats.at("item-rw"), "proof")
  match proof.at("edges") {
    Array(a) => {
      assert_eq(a.length(), 2)
      for edge in a {
        let e = object_fields(edge, "edge")
        assert_true(e.contains("source"))
      }
    }
    _ => fail("source path missing")
  }
}

///|
test "classification duplicate node identity rejected" {
  let d : Json = { "nodes": ["A", "A"], "edges": [], "complete": true }
  assert_eq(cg_test_result(d).at("valid"), false.to_json())
}

///|
test "classification self dependency rejected" {
  assert_eq(
    cg_test_result(cg_test_doc([("A", "A", "ww")])).at("valid"),
    false.to_json(),
  )
}

///|
test "classification unknown endpoint rejected" {
  assert_eq(
    cg_test_result(cg_test_doc([("A", "Z", "ww")])).at("valid"),
    false.to_json(),
  )
}

///|
test "classification unknown dependency rejected" {
  assert_eq(
    cg_test_result(cg_test_doc([("A", "B", "unknown")])).at("valid"),
    false.to_json(),
  )
}

///|
test "classification does not certify full model source obligations" {
  let r = cg_test_result(cg_test_doc([]))
  assert_eq(r.at("modelCoverageAccepted"), false.to_json())
  assert_eq(r.at("sourceDerivationVerified"), false.to_json())
  assert_eq(r.at("directSourceAndIntChecked"), false.to_json())
  assert_eq(r.at("definitionsFrozen"), false.to_json())
}

///|
test "classification 512 vertex chain uses bounded iterative traversal" {
  let nodes : Array[String] = []
  let edges : Array[Json] = []
  for i in 0..<512 {
    nodes.push("T" + i.to_string())
    if i > 0 {
      edges.push({
        "id": ("e" + i.to_string()).to_json(),
        "from": ("T" + (i - 1).to_string()).to_json(),
        "to": ("T" + i.to_string()).to_json(),
        "kind": "wr",
      })
    }
  }
  let d : Json = {
    "nodes": nodes.to_json(),
    "edges": edges.to_json(),
    "complete": true,
  }
  assert_eq(cg_test_model(d, "strict-pl-ss-v1"), "acyclic".to_json())
}

///|
test "classification cycle certificate recovery charges every parent and proof edge" {
  let edges = [("A", "B", "ww"), ("B", "A", "ww")]
  let sufficient = cg_test_result(cg_test_doc(edges, limit=13))
  let sufficient_cats = object_fields(sufficient.at("categories"), "categories")
  assert_eq(cg_status(sufficient_cats.at("ww")), "cycle")
  let insufficient = cg_test_result(cg_test_doc(edges, limit=12))
  let insufficient_cats = object_fields(
    insufficient.at("categories"),
    "categories",
  )
  let proof = object_fields(insufficient_cats.at("ww"), "ww")
  assert_eq(proof.at("status"), "inconclusive".to_json())
  assert_true(!proof.contains("edges"))
}

///|
test "classification macro materialization budget cannot publish a partial certificate" {
  let edges = [("A", "B", "wr"), ("B", "A", "rw-item")]
  let sufficient = cg_test_doc(edges, limit=46)
  assert_eq(
    cg_test_model(sufficient, "elle-generalized-si-v1"),
    "cycle".to_json(),
  )
  let insufficient = cg_test_doc(edges, limit=45)
  let cats = object_fields(
    cg_test_result(insufficient).at("categories"),
    "categories",
  )
  let proof = object_fields(cats.at("nonadjacent-rw"), "proof")
  assert_eq(proof.at("status"), "inconclusive".to_json())
  assert_true(!proof.contains("macroSteps"))
  assert_eq(
    cg_test_model(insufficient, "elle-generalized-si-v1"),
    "inconclusive".to_json(),
  )
}
