///|
fn mls_source_v4(body : Array[Json]) -> HistoryV4 {
  let events : Array[Json] = [
    { "kind": "snapshot", "consistent": true, "initial": { "x": [] } },
  ]
  events.append(body)
  for i, raw in events {
    let fields = object_fields_unchecked_v3(raw)
    fields["seq"] = Json(i + 1)
    fields["time"] = Json(i + 1)
  }
  let source : Json = {
    "traceSchema": 3,
    "dataModel": "append-list-v1",
    "clockDomain": "author-serial-proposal",
    "scope": { "exclusiveWriters": true },
    "gaps": [],
    "events": Json(events),
  }
  parse_history_v4(source.stringify()).unwrap()
}

///|
fn mls_begin_v4(id : String) -> Json {
  { "kind": "begin", "tx": Json(id), "connection": Json("physical-" + id) }
}

///|
fn mls_append_v4(tx : String, id : String) -> Json {
  {
    "kind": "append",
    "tx": Json(tx),
    "key": "x",
    "id": Json(id),
    "value": "same",
  }
}

///|
fn mls_read_v4(tx : String, ids : Array[String]) -> Json {
  {
    "kind": "list_read",
    "tx": Json(tx),
    "key": "x",
    "items": Json(ids.map(id => ({ "id": Json(id), "value": "same" } : Json))),
  }
}

///|
fn mls_end_v4(tx : String) -> Array[Json] {
  [
    { "kind": "commit_request", "tx": Json(tx) },
    { "kind": "commit_ok", "tx": Json(tx) },
  ]
}

///|
fn mls_unordered_v4() -> HistoryV4 {
  let body = [
    mls_begin_v4("A"),
    mls_begin_v4("B"),
    mls_append_v4("A", "a"),
    mls_append_v4("B", "b"),
  ]
  body.append(mls_end_v4("A"))
  body.append(mls_end_v4("B"))
  mls_source_v4(body)
}

///|
fn mls_impossible_v4() -> HistoryV4 {
  let body = [
    mls_begin_v4("A"),
    mls_begin_v4("B"),
    mls_append_v4("A", "a1"),
    mls_append_v4("A", "a2"),
    mls_read_v4("B", ["a2"]),
  ]
  body.append(mls_end_v4("A"))
  body.append(mls_end_v4("B"))
  mls_source_v4(body)
}

///|
fn mls_options_v4() -> ModelOptionsV4 {
  model_options_v4(
    models=[ElleSerializable],
    list_profile=ModelListOriginalSerial,
  ).unwrap()
}

///|
test "author SER proposal01 unobserved WW order is a completion candidate not a fact" {
  let h = mls_unordered_v4()
  let rule = model_list_original_serial_rule_v4(h, mls_options_v4())
  assert_eq(rule.status, "checked-compatible")
  let e = object_fields_unchecked_v3(rule.evidence)
  assert_eq(e.at("sourceOrderInstalled"), Json(false))
  assert_eq(e.at("derivedOrderIsCapturedFact"), Json(false))
  assert_eq(e.at("sourceFactsProduced"), Json(false))
}

///|
test "author SER proposal02 complete exhaustion refutes only SER" {
  let rule = model_list_original_serial_rule_v4(
    mls_impossible_v4(),
    mls_options_v4(),
  )
  assert_eq(rule.status, "refuted")
  let e = object_fields_unchecked_v3(rule.evidence)
  assert_eq(e.at("canonicalModel"), Json("serializable"))
  assert_eq(e.at("otherModelVerdictsInferred"), Json(false))
}

///|
test "author SER proposal03 missing original source remains unknown" {
  let body = [mls_begin_v4("A"), mls_read_v4("A", ["missing-source"])]
  body.append(mls_end_v4("A"))
  assert_eq(
    model_list_original_serial_rule_v4(mls_source_v4(body), mls_options_v4()).status,
    "unknown",
  )
}

///|
test "author SER proposal04 unknown transaction outcome remains unknown" {
  let h = mls_source_v4([mls_begin_v4("A"), mls_append_v4("A", "a")])
  assert_eq(
    model_list_original_serial_rule_v4(h, mls_options_v4()).status,
    "unknown",
  )
}

///|
test "author SER proposal05 repeated names and distinct savepoint instances retain every read" {
  let body : Array[Json] = [
    mls_begin_v4("T"),
    { "kind": "savepoint", "tx": "T", "name": "same", "instance": "outer" },
    mls_append_v4("T", "a"),
    mls_read_v4("T", ["a"]),
    { "kind": "savepoint", "tx": "T", "name": "same", "instance": "inner" },
    mls_append_v4("T", "b"),
    mls_read_v4("T", ["a", "b"]),
    { "kind": "rollback_to", "tx": "T", "instance": "inner" },
    mls_read_v4("T", ["a"]),
    { "kind": "release", "tx": "T", "instance": "inner" },
    { "kind": "rollback_to", "tx": "T", "instance": "outer" },
    mls_read_v4("T", []),
  ]
  body.append(mls_end_v4("T"))
  assert_eq(
    model_list_original_serial_rule_v4(mls_source_v4(body), mls_options_v4()).status,
    "checked-compatible",
  )
}

///|
test "author SER proposal06 absent rollback cannot be repaired by completion" {
  let body : Array[Json] = [
    mls_begin_v4("T"),
    { "kind": "savepoint", "tx": "T", "name": "s", "instance": "s" },
    mls_append_v4("T", "a"),
    mls_read_v4("T", ["a"]),
    mls_read_v4("T", []),
  ]
  body.append(mls_end_v4("T"))
  assert_eq(
    model_list_original_serial_rule_v4(mls_source_v4(body), mls_options_v4()).status,
    "refuted",
  )
}

///|
test "author SER proposal07 independent state zero is not exhaustion proof" {
  let o = model_options_v4(
    models=[ElleSerializable],
    list_profile=ModelListOriginalSerial,
    max_states=0,
  ).unwrap()
  assert_eq(
    model_list_original_serial_rule_v4(mls_unordered_v4(), o).status,
    "unknown",
  )
}

///|
test "author SER proposal08 independent source zero is not exhaustion proof" {
  let o = model_options_v4(
    models=[ElleSerializable],
    list_profile=ModelListOriginalSerial,
    max_source_checks=0,
  ).unwrap()
  assert_eq(
    model_list_original_serial_rule_v4(mls_unordered_v4(), o).status,
    "unknown",
  )
}

///|
test "author SER proposal09 independent semantic edge zero is not exhaustion proof" {
  let o = model_options_v4(
    models=[ElleSerializable],
    list_profile=ModelListOriginalSerial,
    max_edge_checks=0,
  ).unwrap()
  assert_eq(
    model_list_original_serial_rule_v4(mls_impossible_v4(), o).status,
    "unknown",
  )
}

///|
test "author SER proposal10 given logical snapshot assertions remain unsupported" {
  let o = model_options_v4(
    models=[ElleSerializable],
    list_profile=ModelListOriginalSerial,
    completion_policy=ModelGivenSnapshotsUnsupported,
  ).unwrap()
  assert_eq(
    model_list_original_serial_rule_v4(mls_unordered_v4(), o).status,
    "unknown",
  )
}

///|
test "author SER proposal11 seven committed transactions stay outside new exact route" {
  let body : Array[Json] = []
  for i in 0..<7 {
    let id = "T" + i.to_string()
    body.push(mls_begin_v4(id))
    body.append(mls_end_v4(id))
  }
  assert_eq(
    model_list_original_serial_rule_v4(mls_source_v4(body), mls_options_v4()).status,
    "unknown",
  )
}

///|
test "author SER proposal12 more than128 program actions stay unknown" {
  let body : Array[Json] = [mls_begin_v4("T")]
  for i in 0..<129 {
    body.push(mls_append_v4("T", "i" + i.to_string()))
  }
  body.append(mls_end_v4("T"))
  assert_eq(
    model_list_original_serial_rule_v4(mls_source_v4(body), mls_options_v4()).status,
    "unknown",
  )
}

///|
test "author SER proposal13 exact semantic limit and one below" {
  let h = mls_unordered_v4()
  let full = model_list_original_serial_rule_v4(h, mls_options_v4())
  let n = capture_source_seq_v4(
    object_fields_unchecked_v3(
      object_fields_unchecked_v3(full.evidence).at("execution"),
    ).at("semanticChecks"),
  ).to_int()
  let exact = model_options_v4(
    models=[ElleSerializable],
    list_profile=ModelListOriginalSerial,
    max_source_checks=n,
    max_edge_checks=n,
  ).unwrap()
  let below = model_options_v4(
    models=[ElleSerializable],
    list_profile=ModelListOriginalSerial,
    max_source_checks=n - 1,
    max_edge_checks=n - 1,
  ).unwrap()
  assert_eq(
    model_list_original_serial_rule_v4(h, exact).status,
    "checked-compatible",
  )
  assert_eq(model_list_original_serial_rule_v4(h, below).status, "unknown")
}

///|
test "author SER proposal14 all other13 canonical model reports retain prefix baseline" {
  for h in [mls_unordered_v4(), mls_impossible_v4()] {
    let f = model_facts_v4(h).unwrap()
    let a = model_options_v4(
      models=elle_core_models_v4(),
      list_profile=ModelListPrefixStates,
    ).unwrap()
    let b = model_options_v4(
      models=elle_core_models_v4(),
      list_profile=ModelListOriginalSerial,
    ).unwrap()
    let ar = capture_source_array_v4(
      object_fields_unchecked_v3(
        model_classification_v4_json(classify_models_v4(f, a)),
      ).at("models"),
    )
    let br = capture_source_array_v4(
      object_fields_unchecked_v3(
        model_classification_v4_json(classify_models_v4(f, b)),
      ).at("models"),
    )
    for i, old in ar {
      if object_fields_unchecked_v3(old).at("model") != Json("serializable") {
        assert_eq(br[i], old)
      }
    }
  }
}
