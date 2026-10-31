///|
fn sgto_kind(code : Int32) -> ScopedDataKindV4 {
  match code {
    0 => ScopedWWItem
    1 => ScopedWRPredicate
    2 => ScopedRWItem
    _ => ScopedRWPredicate
  }
}

///|
fn sgto_graph(raw : Array[(Int32, Int32, Int32)]) -> ScopedDependencyGraphV4 {
  let names = ["A", "B", "C"]
  sgt_graph(raw.map(edge => (names[edge.0], names[edge.1], sgto_kind(edge.2))))
}

///|
/// Independent finite reference: inspect complete edge-label sequences rather
/// than SCC state, rank pruning, or the production cycle-count structure.
fn sgto_accept(
  kinds : Array[Int32],
  category : ScopedCategoryV4,
  rule : ScopedRuleSetV4,
) -> Bool {
  let rw = kinds.filter(kind => kind >= 2).length()
  let item = kinds.filter(kind => kind == 2).length()
  let predicate = kinds.filter(kind => kind == 3).length()
  let mut adjacent = false
  for i in 0..<kinds.length() {
    if kinds[i] >= 2 && kinds[(i + 1) % kinds.length()] >= 2 {
      adjacent = true
    }
  }
  match category {
    ScopedG0 => kinds.all(kind => kind == 0)
    ScopedG1c => kinds.all(kind => kind < 2)
    ScopedG2Item => item > 0 && (rule == Adya2000Mixed || predicate == 0)
    ScopedG2 => rw > 0
    ScopedGSingleItem => rw == 1 && item == 1
    ScopedGSingle => rw == 1
    ScopedGNonadjacent => rw > 0 && !adjacent
  }
}

///|
fn sgto_exists(
  raw : Array[(Int32, Int32, Int32)],
  category : ScopedCategoryV4,
  rule : ScopedRuleSetV4,
) -> Bool {
  let cycles : Array[Array[Int32]] = [
    [0, 1, 0],
    [0, 2, 0],
    [1, 2, 1],
    [0, 1, 2, 0],
    [0, 2, 1, 0],
  ]
  for cycle in cycles {
    for first in raw {
      if first.0 != cycle[0] || first.1 != cycle[1] {
        continue
      }
      for second in raw {
        if second.0 != cycle[1] || second.1 != cycle[2] {
          continue
        }
        if cycle.length() == 3 {
          if sgto_accept([first.2, second.2], category, rule) {
            return true
          }
        } else {
          for third in raw {
            if third.0 == cycle[2] &&
              third.1 == cycle[3] &&
              sgto_accept([first.2, second.2, third.2], category, rule) {
              return true
            }
          }
        }
      }
    }
  }
  false
}

///|
fn sgto_extension_exists(raw : Array[(Int32, Int32, Int32)]) -> Bool {
  let information = FixedArray::make(9, false)
  let anti = FixedArray::make(9, false)
  let extended = FixedArray::make(9, false)
  for edge in raw {
    if edge.2 < 2 {
      information[edge.0 * 3 + edge.1] = true
    } else {
      anti[edge.0 * 3 + edge.1] = true
    }
  }
  for from in 0..<3 {
    for to in 0..<3 {
      extended[from * 3 + to] = information[from * 3 + to]
      for middle in 0..<3 {
        if information[from * 3 + middle] && anti[middle * 3 + to] {
          extended[from * 3 + to] = true
        }
      }
    }
  }
  for node in 0..<3 {
    if extended[node * 3 + node] {
      return true
    }
  }
  for from in 0..<3 {
    for to in (from + 1)..<3 {
      if extended[from * 3 + to] && extended[to * 3 + from] {
        return true
      }
    }
  }
  (extended[1] && extended[5] && extended[6]) ||
  (extended[2] && extended[7] && extended[3])
}

///|
fn sgto_check_original_witness(
  raw : Array[(Int32, Int32, Int32)],
  result : ScopedSearchResultV4,
  category : ScopedCategoryV4,
  rule : ScopedRuleSetV4,
) -> Unit raise {
  let names = ["A", "B", "C"]
  let steps = v3_test_items(v4_test_at(result.record, ["witness"]), "steps")
  let kinds : Array[Int32] = []
  assert_true(steps.length() >= 2 && steps.length() <= 3)
  for position, step in steps {
    let reference = v3_test_items(step, "sources")[0]
    let index = match capture_field(reference, "originalEdge") {
      Number(number, ..) => number.to_int()
      _ => -1
    }
    assert_true(index >= 0 && index < raw.length())
    let edge = raw[index]
    kinds.push(edge.2)
    assert_eq(capture_field(step, "id"), Json("e" + index.to_string()))
    assert_eq(capture_field(step, "from"), Json(names[edge.0]))
    assert_eq(capture_field(step, "to"), Json(names[edge.1]))
    assert_eq(
      capture_field(step, "kind"),
      Json(["ww-item", "wr-predicate", "rw-item", "rw-predicate"][edge.2]),
    )
    assert_eq(
      capture_field(step, "to"),
      capture_field(steps[(position + 1) % steps.length()], "from"),
    )
  }
  assert_true(sgto_accept(kinds, category, rule))
  let rw = kinds.filter(kind => kind >= 2).length()
  let item = kinds.filter(kind => kind == 2).length()
  assert_eq(
    v4_test_at(result.record, ["witness", "antiDependencies", "total"]),
    Json(rw),
  )
  assert_eq(
    v4_test_at(result.record, ["witness", "antiDependencies", "item"]),
    Json(item),
  )
}

///|
fn sgto_check_extension_witness(
  raw : Array[(Int32, Int32, Int32)],
  result : ScopedSearchResultV4,
) -> Unit raise {
  let names = ["A", "B", "C"]
  let witness = v4_test_at(result.record, ["witness"])
  let arcs = v3_test_items(witness, "virtualSteps")
  let flattened : Array[Json] = []
  let kinds : Array[Int32] = []
  assert_true(arcs.length() >= 1 && arcs.length() <= 3)
  for arc_position, arc in arcs {
    let steps = v3_test_items(arc, "originalSteps")
    assert_true(steps.length() == 1 || steps.length() == 2)
    for position, step in steps {
      let reference = v3_test_items(step, "sources")[0]
      let index = match capture_field(reference, "originalEdge") {
        Number(n, ..) => n.to_int()
        _ => -1
      }
      assert_true(index >= 0 && index < raw.length())
      let edge = raw[index]
      assert_eq(capture_field(step, "id"), Json("e" + index.to_string()))
      assert_eq(capture_field(step, "from"), Json(names[edge.0]))
      assert_eq(capture_field(step, "to"), Json(names[edge.1]))
      if position == 0 {
        assert_true(edge.2 < 2)
      } else {
        assert_true(edge.2 >= 2)
      }
      if position + 1 < steps.length() {
        assert_eq(
          capture_field(step, "to"),
          capture_field(steps[position + 1], "from"),
        )
      }
      flattened.push(step)
      kinds.push(edge.2)
    }
    assert_eq(capture_field(arc, "from"), capture_field(steps[0], "from"))
    assert_eq(
      capture_field(arc, "to"),
      capture_field(steps[steps.length() - 1], "to"),
    )
    assert_eq(
      capture_field(arc, "to"),
      capture_field(arcs[(arc_position + 1) % arcs.length()], "from"),
    )
  }
  assert_eq(Json(flattened), capture_field(witness, "steps"))
  for i in 0..<kinds.length() {
    assert_false(kinds[i] >= 2 && kinds[(i + 1) % kinds.length()] >= 2)
  }
}

///|
fn sgto_verify_all(raw : Array[(Int32, Int32, Int32)]) -> Unit raise {
  let graph = sgto_graph(raw)
  for category in sgt_categories() {
    for rule in [Adya2000Mixed, ElleFixed4e359e5] {
      let result = search_scoped_category_v4(graph, category, rule_set=rule)
      let expected = sgto_exists(raw, category, rule)
      assert_eq(
        result.status(),
        if expected {
          "refuted"
        } else {
          "checked-compatible"
        },
      )
      if expected {
        sgto_check_original_witness(raw, result, category, rule)
      }
    }
  }
  let extension = search_si_extension_v4(graph, rule_set=ElleFixed4e359e5)
  assert_eq(
    extension.status(),
    if sgto_extension_exists(raw) {
      "refuted"
    } else {
      "checked-compatible"
    },
  )
  if extension.status() == "refuted" {
    sgto_check_extension_witness(raw, extension)
  }
}

///|
test "scoped36 oracle 15625 three node WW WR itemRW predicateRW graphs match complete simple cycle and Ext references" {
  let mut checked = 0
  for mask in 0..<15625 {
    let raw : Array[(Int32, Int32, Int32)] = []
    let mut divisor = 1
    for from in 0..<3 {
      for to in 0..<3 {
        if from == to {
          continue
        }
        let color = mask / divisor % 5
        divisor *= 5
        if color > 0 {
          raw.push((from, to, color - 1))
        }
      }
    }
    sgto_verify_all(raw)
    checked += 1
  }
  assert_eq(checked, 15625)
}

///|
test "scoped36 oracle 4096 parallel information and mixed anti scope graphs retain every relationship choice" {
  let mut checked = 0
  for mask in 0..<4096 {
    let raw : Array[(Int32, Int32, Int32)] = []
    let mut divisor = 1
    let mut pair = 0
    for from in 0..<3 {
      for to in 0..<3 {
        if from == to {
          continue
        }
        let color = mask / divisor % 4
        divisor *= 4
        if color % 2 == 1 {
          raw.push((from, to, if pair % 2 == 0 { 0 } else { 1 }))
        }
        if color / 2 == 1 {
          raw.push((from, to, if pair % 2 == 0 { 2 } else { 3 }))
        }
        pair += 1
      }
    }
    sgto_verify_all(raw)
    checked += 1
  }
  assert_eq(checked, 4096)
}
