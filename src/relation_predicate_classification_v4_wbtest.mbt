///|
test "relation predicate category 01 empty-result skew refutes predicate G2 but not item G2" {
  let history = rpred_history(rpred_empty_skew(), empty=true)
  let general = classify_relation_predicate_v4(
    history,
    ScopedG2,
    rule_set=Adya2000Mixed,
  ).unwrap()
  let item = classify_relation_predicate_v4(
    history,
    ScopedG2Item,
    rule_set=Adya2000Mixed,
  ).unwrap()
  assert_eq(general.status(), "refuted")
  assert_eq(item.status(), "checked-compatible")
  let record = relation_predicate_classification_v4_json(general)
  assert_eq(v4_test_at(record, ["category"]), Json("G2"))
  assert_eq(
    v4_test_at(record, ["predicateGraph", "indexAlgorithm"]),
    Json("relation-point-local-effect-journal-4"),
  )
  assert_true(
    verify_relation_predicate_classification_v4(
      history,
      record,
      ScopedG2,
      rule_set=Adya2000Mixed,
    ),
  )
  assert_false(
    verify_relation_predicate_classification_v4(
      history,
      record,
      ScopedG2Item,
      rule_set=Adya2000Mixed,
    ),
  )
  assert_false(
    verify_relation_predicate_classification_v4(
      history,
      record,
      ScopedG2,
      rule_set=ElleFixed4e359e5,
    ),
  )
}

///|
test "relation predicate category 02 zero search budget cannot be no-cycle proof" {
  let history = rpred_history(rpred_empty_skew(), empty=true)
  let result = classify_relation_predicate_v4(
    history,
    ScopedG2,
    rule_set=Adya2000Mixed,
    max_states=0,
  ).unwrap()
  assert_eq(result.status(), "unknown")
  let record = relation_predicate_classification_v4_json(result)
  assert_true(
    verify_relation_predicate_classification_v4(
      history,
      record,
      ScopedG2,
      rule_set=Adya2000Mixed,
      max_states=0,
    ),
  )
  assert_false(
    verify_relation_predicate_classification_v4(
      history,
      record,
      ScopedG2,
      rule_set=Adya2000Mixed,
    ),
  )
}

///|
test "relation predicate category 03 incomplete delivered query is not an empty-set proof" {
  let body = [rpg_begin("R"), rpred_read("R", [], complete=false)]
  rpg_commit(body, "R")
  let result = classify_relation_predicate_v4(
    rpred_history(body, empty=true),
    ScopedG2,
    rule_set=Adya2000Mixed,
  ).unwrap()
  assert_eq(result.status(), "unknown")
}

///|
test "relation predicate category 04 modified conclusion and source digest are rejected" {
  let history = rpred_history(rpred_empty_skew(), empty=true)
  let result = classify_relation_predicate_v4(
    history,
    ScopedG2,
    rule_set=Adya2000Mixed,
  ).unwrap()
  let record = relation_predicate_classification_v4_json(result)
  object_fields_unchecked_v3(record)["status"] = Json("checked-compatible")
  assert_false(
    verify_relation_predicate_classification_v4(
      history,
      record,
      ScopedG2,
      rule_set=Adya2000Mixed,
    ),
  )
  let changed = relation_predicate_classification_v4_json(result)
  object_fields_unchecked_v3(changed)["sourceSha256"] = Json("forged")
  assert_false(
    verify_relation_predicate_classification_v4(
      history,
      changed,
      ScopedG2,
      rule_set=Adya2000Mixed,
    ),
  )
  assert_eq(result.status(), "refuted")
}

///|
test "relation predicate category 05 no-op committed transactions and graph budgets remain explicit" {
  let body = [rpg_begin("R")]
  rpg_commit(body, "R")
  let history = rpred_history(body, empty=true)
  let complete = classify_relation_predicate_v4(
    history,
    ScopedG0,
    rule_set=Adya2000Mixed,
  ).unwrap()
  assert_eq(complete.status(), "checked-compatible")
  let required_work = rpred_history(rpred_empty_skew(), empty=true)
  let limited = classify_relation_predicate_v4(
    required_work,
    ScopedG0,
    rule_set=Adya2000Mixed,
    max_graph_checks=0,
  ).unwrap()
  assert_eq(limited.status(), "unknown")
}

///|
test "relation predicate category 06 nonadjacent search counts ring wraparound" {
  let history = rpred_history(rpred_empty_skew(), empty=true)
  let result = classify_relation_predicate_v4(
    history,
    ScopedGNonadjacent,
    rule_set=Adya2000Mixed,
  ).unwrap()
  assert_eq(result.status(), "checked-compatible")
  let single = classify_relation_predicate_v4(
    history,
    ScopedGSingle,
    rule_set=Adya2000Mixed,
  ).unwrap()
  assert_eq(single.status(), "checked-compatible")
}
