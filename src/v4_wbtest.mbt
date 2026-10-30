///|
fn v4_test_at(value : Json, path : Array[String]) -> Json {
  let mut current = value
  for key in path {
    current = object_fields_unchecked_v3(current).at(key)
  }
  current
}

///|
fn v4_test_replace(
  value : Json,
  path : Array[String],
  replacement : Json,
) -> Unit {
  let mut current = value
  for index in 0..<(path.length() - 1) {
    current = object_fields_unchecked_v3(current).at(path[index])
  }
  object_fields_unchecked_v3(current)[path[path.length() - 1]] = replacement
}

///|
fn v4_test_model_trace(model : DataModelV4, body : Array[Json]) -> Json {
  let initial : Json = if model == AppendListV4 {
    { "x": [] }
  } else {
    { "r": [] }
  }
  let events : Array[Json] = [
    { "kind": "snapshot", "initial": initial, "consistent": true },
  ]
  for event in body {
    events.push(event)
  }
  for index, event in events {
    let fields = object_fields_unchecked_v3(event)
    fields["seq"] = Json(index + 1)
    fields["time"] = Json(index)
  }
  let result : Json = {
    "traceSchema": 3,
    "dataModel": Json(v4_model_name(model)),
    "clockDomain": "v4-test",
    "scope": { "exclusiveWriters": true },
    "events": Json(events),
    "gaps": [],
  }
  if model == RelationSetV4 {
    object_fields_unchecked_v3(result)["relationSchema"] = {
      "r": { "primaryKey": "id", "columns": { "id": "int64", "n": "int64" } },
    }
    v4_test_replace(result, ["scope"], {
      "exclusiveWriters": true,
      "completeSnapshotTables": ["r"],
    })
  }
  result
}

///|
fn v4_test_model_complete(model : DataModelV4, steps : Array[Json]) -> Json {
  let events : Array[Json] = [{ "kind": "begin", "tx": "A", "connection": "c" }]
  for step in steps {
    events.push(step)
  }
  events.push({ "kind": "commit_request", "tx": "A" })
  events.push({ "kind": "commit_ok", "tx": "A" })
  v4_test_model_trace(model, events)
}

///|
test "v4 01 declared register source and analysis have independent identities" {
  let input = hist([tx("A", [write_op("x", "x1")])], orders={
    "x": ["x0", "x1"],
    "y": ["y0"],
  })
  let snapshot = register_history_v4(input).unwrap()
  let before = render_analysis_v4(analyze_v4(snapshot))
  input.initial["x"] = "mutated"
  input.version_orders.at("x").push("mutated")
  input.transactions[0].ops.push(read_op("missing", "mutated"))
  input.transactions.push(tx("duplicate", []))
  assert_eq(render_analysis_v4(analyze_v4(snapshot)), before)
  assert_true(analyze_v4(snapshot).outcome() == Consistent)
  assert_true(snapshot.data_model() == RegisterV4)
}

///|
test "v4 02 exported source does not alias retained declared programs" {
  let snapshot = register_history_v4(skew()).unwrap()
  let exported = history_v4_json(snapshot)
  v4_test_replace(exported, ["initial", "x"], Json("changed"))
  assert_eq(v4_test_at(history_v4_json(snapshot), ["initial", "x"]), Json("x0"))
  assert_true(analyze_v4(snapshot).outcome() == Violation)
}

///|
test "v4 03 exported report source and evidence cannot mutate later reports" {
  let snapshot = register_history_v4(skew()).unwrap()
  let artifact = analyze_v4(snapshot)
  let original = render_analysis_v4(artifact)
  let detached = analysis_v4_json(artifact)
  v4_test_replace(
    detached,
    ["observations", "document", "initial", "x"],
    Json("changed"),
  )
  v4_test_replace(
    detached,
    ["judgment", "evidence", "witness"],
    Json(([] : Array[Json])),
  )
  assert_eq(render_analysis_v4(artifact), original)
  assert_eq(render_analysis_v4(analyze_v4(snapshot)), original)
  assert_false(verify_v4(snapshot, detached))
}

///|
test "v4 04 register defaults preserve balanced results and actual limits" {
  let input = completion_noise(8)
  let snapshot = register_history_v4(input).unwrap()
  let result = analyze_v4(snapshot)
  let legacy = analysis_result_json(analyze_with_options(input))
  let report = analysis_v4_json(result)
  assert_true(result.outcome() == Violation)
  for
    field in [
      "stats", "findings", "edges", "witness", "serialOrder", "graph", "coverage",
      "search",
    ] {
    assert_eq(
      v4_test_at(report, ["judgment", "evidence", field]),
      capture_field(legacy, field),
    )
  }
  for field in ["metrics", "analysisOptions", "effectiveLimits"] {
    assert_eq(
      v4_test_at(report, ["execution", field]),
      capture_field(legacy, field),
    )
  }
  assert_eq(
    v4_test_at(report, ["execution", "effectiveLimits", "transactions"]),
    Json(12),
  )
  assert_eq(
    v4_test_at(report, ["execution", "counterContract"]),
    Json("bounded-register-v2.1-counters"),
  )
}

///|
test "v4 05 twelve writer support does not change the legacy entry point" {
  let input = hist(
    Array::makei(12, i => {
      tx("T" + i.to_string(), [write_op("x", "v" + i.to_string())])
    }),
  )
  assert_true(analyze(input).outcome == Inconclusive)
  let report = analysis_v4_json(analyze_v4(register_history_v4(input).unwrap()))
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("consistent"))
  assert_eq(
    v4_test_at(report, ["inferences", "versionOrderSources", "x"]),
    Json("searched"),
  )
  assert_eq(
    v4_test_at(report, ["observations", "authenticityVerified"]),
    Json(false),
  )
  assert_eq(
    v4_test_at(report, ["observations", "document", "versionOrders"]),
    Json::object(Map([])),
  )
}

///|
test "v4 06 capture programs do not infer realtime from client event ticks" {
  let input = v3_test_completed([
    { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
  ])
  let source = input.stringify()
  let snapshot = parse_history_v4(source).unwrap()
  let result = analysis_v4_json(analyze_v4(snapshot))
  let legacy = @json.parse(analyze_v3_json(source, "{}"))
  assert_eq(v4_test_at(result, ["judgment", "status"]), Json("consistent"))
  assert_eq(
    v4_test_at(result, ["judgment", "evidence", "edges"]),
    v4_test_at(legacy, ["evidence", "edges"]),
  )
  assert_eq(v4_test_at(result, ["observations", "document"]), input)
  assert_eq(snapshot.source_text(), source)
  assert_true(verify_v4(snapshot, result))
}

///|
test "v4 07 disconnect after commit request preserves unknown outcome" {
  let input = v3_test_trace([
    { "kind": "begin", "tx": "A", "connection": "c" },
    {
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "x1",
      "predecessor": "x0",
    },
    { "kind": "commit_request", "tx": "A" },
    { "kind": "disconnect", "tx": "A" },
  ])
  let snapshot = parse_history_v4(input.stringify()).unwrap()
  let report = analysis_v4_json(analyze_v4(snapshot))
  assert_true(analyze_v4(snapshot).outcome() == Inconclusive)
  assert_eq(
    v4_test_at(report, ["judgment", "coverage", "complete"]),
    Json(false),
  )
  assert_eq(v4_test_at(report, ["judgment", "evidence"]), Json::null())
  assert_eq(v4_test_at(report, ["execution", "reason"]), Json("coverage_gap"))
  assert_true(verify_v4(snapshot, report))
}

///|
test "v4 08 savepoint rollback preserves observations and original write effects" {
  let input = v3_test_completed([
    { "kind": "savepoint", "tx": "A", "name": "s", "instance": "i" },
    {
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "x1",
      "predecessor": "x0",
    },
    { "kind": "read", "tx": "A", "key": "x", "version": "x1" },
    { "kind": "rollback_to", "tx": "A", "instance": "i" },
    { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
  ])
  let normalized = @json.parse(normalize_capture_v3_json(input.stringify()))
  let snapshot = parse_history_v4(input.stringify()).unwrap()
  let report = analysis_v4_json(analyze_v4(snapshot))
  assert_true(analyze_v4(snapshot).outcome() == Consistent)
  assert_eq(
    v4_test_at(report, ["writeEffects", "entries"]),
    capture_field(normalized, "effects"),
  )
  assert_eq(v4_test_at(report, ["observations", "document"]), input)
}

///|
test "v4 09 declared strict order is retained without capture authentication" {
  let input = hist(
    [tx("A", [], start=Some(1L), end=Some(2L))],
    model=StrictSerializable,
  )
  let report = analysis_v4_json(analyze_v4(register_history_v4(input).unwrap()))
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("consistent"))
  assert_eq(
    v4_test_at(report, ["judgment", "modelDefinition", "id"]),
    Json("declared-register-strict-serializable-v1"),
  )
  assert_eq(
    v4_test_at(report, ["judgment", "coverage", "externalCompletenessVerified"]),
    Json(false),
  )
}

///|
test "v4 10 invalid options fail without granting search work" {
  let snapshot = register_history_v4(skew()).unwrap()
  for
    options in [
      analysis_options_v4(max_attempts=-1),
      analysis_options_v4(max_states=100001),
      analysis_options_v4(max_operation_checks=1000001),
      analysis_options_v4(max_cached_states=50001),
    ] {
    let result = analyze_v4(snapshot, options~)
    assert_true(result.outcome() == Invalid)
    let report = analysis_v4_json(result)
    assert_eq(v4_test_at(report, ["judgment", "code"]), Json("invalid_options"))
    assert_eq(
      v4_test_at(report, ["execution", "effectiveLimits"]),
      Json::null(),
    )
  }
}

///|
test "v4 11 register exhausted budgets remain inconclusive and repeatable" {
  let snapshot = register_history_v4(completion_noise(8)).unwrap()
  for
    options in [
      analysis_options_v4(max_attempts=0),
      analysis_options_v4(max_operation_checks=0),
      analysis_options_v4(max_attempts=1),
    ] {
    let first = analyze_v4(snapshot, options~)
    assert_true(first.outcome() == Inconclusive)
    assert_eq(
      render_analysis_v4(first),
      render_analysis_v4(analyze_v4(snapshot, options~)),
    )
    assert_true(verify_v4(snapshot, analysis_v4_json(first), options~))
    assert_false(verify_v4(snapshot, analysis_v4_json(first)))
  }
}

///|
test "v4 12 caller budget cannot be elevated by changing the supplied report" {
  let snapshot = register_history_v4(completion_noise(3)).unwrap()
  let options = analysis_options_v4(max_attempts=0)
  let altered = analysis_v4_json(analyze_v4(snapshot, options~))
  v4_test_replace(
    altered,
    ["execution", "effectiveLimits", "attempts"],
    Json(100000),
  )
  v4_test_replace(
    altered,
    ["execution", "requestedOptions", "maxAttempts"],
    Json(100000),
  )
  assert_false(verify_v4(snapshot, altered, options~))
}

///|
test "v4 13 report verifier binds every section and semantic identifier" {
  let snapshot = register_history_v4(skew()).unwrap()
  let artifact = analyze_v4(snapshot)
  for
    path in [
      ["format"],
      ["schemaVersion"],
      ["semanticContract"],
      ["algorithm"],
      ["dataModel"],
      ["observations", "sourceFormat"],
      ["observations", "authenticityVerified"],
      ["observations", "document", "initial", "x"],
      ["writeEffects", "entries"],
      ["inferences", "versionOrderSources"],
      ["judgment", "status"],
      ["judgment", "modelDefinition"],
      ["judgment", "evidence", "witness"],
      ["execution", "counterContract"],
      ["execution", "analysisOptions"],
      ["execution", "metrics"],
      ["execution", "requestedOptions"],
    ] {
    let altered = analysis_v4_json(artifact)
    v4_test_replace(altered, path, Json("tampered"))
    assert_false(verify_v4(snapshot, altered))
  }
}

///|
test "v4 14 observed version identities are retained and product version is separate" {
  let input = hist([tx("A", [write_op("x", "version")])])
  let snapshot = parse_history_v4(history_json(input).stringify()).unwrap()
  let report = analysis_v4_json(analyze_v4(snapshot))
  assert_false(object_fields_unchecked_v3(report).contains("version"))
  let source_tx = v3_test_items(
      v4_test_at(report, ["observations", "document"]),
      "transactions",
    )[0]
  let operation = v3_test_items(source_tx, "ops")[0]
  assert_eq(capture_field(operation, "version"), Json("version"))
  assert_true(verify_v4(snapshot, report))
}

///|
test "v4 15 malformed and unsupported source models are rejected at the boundary" {
  for
    input in [
      "{", "[]", "{\"traceSchema\":4}", "{\"traceSchema\":3,\"dataModel\":\"mixed\"}",
      "{\"schemaVersion\":100}",
    ] {
    assert_true(parse_history_v4(input) is Err(_))
  }
  assert_true(register_history_v4(hist([tx("A", []), tx("A", [])])) is Err(_))
  assert_true(
    register_history_v4(
      hist([tx("A", [write_op("x", "same")]), tx("B", [write_op("x", "same")])]),
    )
    is Err(_),
  )
}

///|
test "v4 16 list empty transaction preserves state budget and v3 counters" {
  let input = v4_test_model_complete(AppendListV4, [])
  let source = input.stringify()
  let snapshot = parse_history_v4(source).unwrap()
  assert_true(snapshot.data_model() == AppendListV4)
  let normal = analysis_v4_json(analyze_v4(snapshot))
  let legacy = list_v3_analysis(source, "{}")
  assert_eq(v4_test_at(normal, ["judgment", "status"]), Json("consistent"))
  assert_eq(
    v4_test_at(normal, ["execution", "metrics"]),
    v4_test_at(legacy, ["execution", "metrics"]),
  )
  assert_eq(
    v4_test_at(normal, ["execution", "effectiveLimits"]),
    v4_test_at(legacy, ["execution", "effectiveLimits"]),
  )
  assert_true(
    analyze_v4(snapshot, options=analysis_options_v4(max_states=0)).outcome() ==
    Inconclusive,
  )
  assert_eq(
    v4_test_at(analysis_v4_json(analyze_v4(snapshot)), [
      "execution", "metrics", "states",
    ]),
    Json(1),
  )
}

///|
test "v4 17 relation empty transaction preserves state budget and v3 counters" {
  let source = v4_test_model_complete(RelationSetV4, []).stringify()
  let snapshot = parse_history_v4(source).unwrap()
  assert_true(snapshot.data_model() == RelationSetV4)
  let normal = analysis_v4_json(analyze_v4(snapshot))
  let legacy = relation_v3_analysis(source, "{}")
  assert_eq(v4_test_at(normal, ["judgment", "status"]), Json("consistent"))
  assert_eq(
    v4_test_at(normal, ["judgment", "evidence"]),
    capture_field(legacy, "evidence"),
  )
  assert_eq(
    v4_test_at(normal, ["execution", "metrics"]),
    v4_test_at(legacy, ["execution", "metrics"]),
  )
  assert_eq(
    v4_test_at(normal, ["execution", "effectiveLimits"]),
    v4_test_at(legacy, ["execution", "effectiveLimits"]),
  )
  assert_true(
    analyze_v4(snapshot, options=analysis_options_v4(max_states=0)).outcome() ==
    Inconclusive,
  )
}

///|
test "v4 18 list operation budget does not report exhaustive failure" {
  let source = v4_test_model_complete(AppendListV4, [
    { "kind": "append", "tx": "A", "key": "x", "id": "i", "value": "same" },
  ]).stringify()
  let snapshot = parse_history_v4(source).unwrap()
  let options = analysis_options_v4(max_operation_checks=0)
  let limited = analyze_v4(snapshot, options~)
  assert_true(limited.outcome() == Inconclusive)
  assert_true(analyze_v4(snapshot).outcome() == Consistent)
  assert_true(verify_v4(snapshot, analysis_v4_json(limited), options~))
}

///|
test "v4 19 relation operation budget does not report exhaustive failure" {
  let source = v4_test_model_complete(RelationSetV4, [
    {
      "kind": "row_read",
      "tx": "A",
      "relation": "r",
      "predicate": [],
      "rows": [],
      "complete": true,
    },
  ]).stringify()
  let snapshot = parse_history_v4(source).unwrap()
  assert_true(
    analyze_v4(snapshot, options=analysis_options_v4(max_operation_checks=0)).outcome() ==
    Inconclusive,
  )
  assert_true(analyze_v4(snapshot).outcome() == Consistent)
}

///|
test "v4 20 list and relation snapshots reject cross-model operations" {
  let list = v4_test_model_complete(AppendListV4, [
    {
      "kind": "row_read",
      "tx": "A",
      "relation": "r",
      "predicate": [],
      "rows": [],
      "complete": true,
    },
  ])
  let relation = v4_test_model_complete(RelationSetV4, [
    { "kind": "append", "tx": "A", "key": "x", "id": "i", "value": "same" },
  ])
  assert_true(parse_history_v4(list.stringify()) is Err(_))
  assert_true(parse_history_v4(relation.stringify()) is Err(_))
}

///|
test "v4 21 missing list or relation commit response remains a coverage gap" {
  for model in [AppendListV4, RelationSetV4] {
    let input = v4_test_model_trace(model, [
      { "kind": "begin", "tx": "A", "connection": "c" },
      { "kind": "commit_request", "tx": "A" },
      { "kind": "disconnect", "tx": "A" },
    ])
    let snapshot = parse_history_v4(input.stringify()).unwrap()
    let report = analysis_v4_json(analyze_v4(snapshot))
    assert_true(analyze_v4(snapshot).outcome() == Inconclusive)
    assert_eq(
      v4_test_at(report, ["judgment", "coverage", "complete"]),
      Json(false),
    )
  }
}

///|
test "v4 22 exported capture events do not alias parsed list or relation state" {
  for model in [AppendListV4, RelationSetV4] {
    let source = v4_test_model_complete(model, []).stringify()
    let snapshot = parse_history_v4(source).unwrap()
    let first = analyze_v4(snapshot)
    let exported = analysis_v4_json(first)
    let events = v3_test_items(
      v4_test_at(exported, ["observations", "document"]),
      "events",
    )
    object_fields_unchecked_v3(events[0])["consistent"] = Json(false)
    assert_eq(
      render_analysis_v4(first),
      render_analysis_v4(analyze_v4(snapshot)),
    )
    assert_false(verify_v4(snapshot, exported))
    assert_eq(snapshot.source_text(), source)
  }
}

///|
test "v4 23 AppendListV4 source-closure counterexample matches all legacy evidence" {
  let source = v4_test_fixture(AppendListV4)
  let snapshot = parse_history_v4(source).unwrap()
  let first = analyze_v4(snapshot)
  let report = analysis_v4_json(first)
  let legacy = list_v3_analysis(source, "{}")
  assert_true(snapshot.data_model() == AppendListV4)
  assert_true(first.outcome() == Violation)
  for field in ["status", "modelDefinition", "coverage", "evidence"] {
    assert_eq(
      v4_test_at(report, ["judgment", field]),
      capture_field(legacy, field),
    )
  }
  for field in ["analysisOptions", "effectiveLimits", "metrics"] {
    assert_eq(
      v4_test_at(report, ["execution", field]),
      v4_test_at(legacy, ["execution", field]),
    )
  }
  assert_eq(render_analysis_v4(first), render_analysis_v4(analyze_v4(snapshot)))
  assert_eq(
    v4_test_at(report, ["writeEffects", "entries"]),
    v4_test_at(legacy, ["normalized", "effects"]),
  )
  assert_true(verify_v4(snapshot, report))
  for
    path in [
      ["writeEffects", "entries"],
      ["judgment", "evidence"],
      ["execution", "counterContract"],
      ["execution", "metrics"],
    ] {
    let altered = analysis_v4_json(first)
    v4_test_replace(altered, path, Json("tampered"))
    assert_false(verify_v4(snapshot, altered))
  }
}

///|
test "v4 24 RelationSetV4 source-closure counterexample matches all legacy evidence" {
  let source = v4_test_fixture(RelationSetV4)
  let snapshot = parse_history_v4(source).unwrap()
  let first = analyze_v4(snapshot)
  let report = analysis_v4_json(first)
  let legacy = relation_v3_analysis(source, "{}")
  assert_true(snapshot.data_model() == RelationSetV4)
  assert_true(first.outcome() == Violation)
  for field in ["status", "modelDefinition", "coverage", "evidence"] {
    assert_eq(
      v4_test_at(report, ["judgment", field]),
      capture_field(legacy, field),
    )
  }
  for field in ["analysisOptions", "effectiveLimits", "metrics"] {
    assert_eq(
      v4_test_at(report, ["execution", field]),
      v4_test_at(legacy, ["execution", field]),
    )
  }
  assert_eq(render_analysis_v4(first), render_analysis_v4(analyze_v4(snapshot)))
  assert_eq(
    v4_test_at(report, ["writeEffects", "entries"]),
    v4_test_at(legacy, ["normalized", "effects"]),
  )
  assert_true(verify_v4(snapshot, report))
  for
    path in [
      ["writeEffects", "entries"],
      ["judgment", "evidence"],
      ["execution", "counterContract"],
      ["execution", "metrics"],
    ] {
    let altered = analysis_v4_json(first)
    v4_test_replace(altered, path, Json("tampered"))
    assert_false(verify_v4(snapshot, altered))
  }
}

///|
fn v4_test_fixture(model : DataModelV4) -> String {
  match model {
    AppendListV4 =>
      "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"independent-list-clock\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"x0\",\"value\":\"same\"}],\"y\":[{\"id\":\"y0\",\"value\":\"same\"}]},\"consistent\":true},{\"kind\":\"begin\",\"tx\":\"noise\",\"connection\":\"noise\",\"seq\":2,\"time\":1},{\"kind\":\"list_read\",\"tx\":\"noise\",\"key\":\"y\",\"items\":[{\"id\":\"y0\",\"value\":\"same\"}],\"seq\":3,\"time\":2},{\"kind\":\"commit_request\",\"tx\":\"noise\",\"seq\":4,\"time\":3},{\"kind\":\"commit_ok\",\"tx\":\"noise\",\"seq\":5,\"time\":4},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"T\",\"connection\":\"C\"},{\"seq\":7,\"time\":6,\"kind\":\"begin\",\"tx\":\"U\",\"connection\":\"D\"},{\"seq\":8,\"time\":7,\"kind\":\"list_read\",\"tx\":\"T\",\"key\":\"x\",\"items\":[{\"id\":\"x0\",\"value\":\"same\"}]},{\"seq\":9,\"time\":8,\"kind\":\"list_read\",\"tx\":\"U\",\"key\":\"y\",\"items\":[{\"id\":\"y0\",\"value\":\"same\"}]},{\"seq\":10,\"time\":9,\"kind\":\"append\",\"tx\":\"T\",\"key\":\"y\",\"id\":\"y1\",\"value\":\"same\"},{\"seq\":11,\"time\":10,\"kind\":\"append\",\"tx\":\"U\",\"key\":\"x\",\"id\":\"x1\",\"value\":\"same\"},{\"seq\":12,\"time\":11,\"kind\":\"commit_request\",\"tx\":\"T\"},{\"seq\":13,\"time\":12,\"kind\":\"commit_ok\",\"tx\":\"T\"},{\"seq\":14,\"time\":13,\"kind\":\"commit_request\",\"tx\":\"U\"},{\"seq\":15,\"time\":14,\"kind\":\"commit_ok\",\"tx\":\"U\"}],\"gaps\":[]}"
    RelationSetV4 =>
      "{\"traceSchema\":3,\"dataModel\":\"relation-set-v1\",\"clockDomain\":\"independent-synthetic-relation-source-closure\",\"relationSchema\":{\"r\":{\"primaryKey\":\"id\",\"columns\":{\"id\":\"int64\",\"n\":\"int64\",\"b\":\"bool\",\"t\":\"text\"}},\"noise\":{\"primaryKey\":\"id\",\"columns\":{\"id\":\"int64\",\"n\":\"int64\",\"b\":\"bool\",\"t\":\"text\"}}},\"scope\":{\"exclusiveWriters\":true,\"completeSnapshotTables\":[\"r\",\"noise\"]},\"events\":[{\"seq\":1,\"time\":1,\"kind\":\"snapshot\",\"initial\":{\"r\":[{\"key\":\"0\",\"version\":\"p0\",\"values\":{\"n\":\"0\",\"b\":true,\"t\":\"\"}}],\"noise\":[]},\"consistent\":true},{\"seq\":2,\"time\":2,\"kind\":\"begin\",\"tx\":\"P\",\"connection\":\"connection-P\"},{\"seq\":3,\"time\":3,\"kind\":\"row_write\",\"tx\":\"P\",\"relation\":\"r\",\"key\":\"0\",\"action\":\"update\",\"version\":\"p1\",\"predecessor\":\"p0\",\"values\":{\"n\":\"1\",\"b\":true,\"t\":\"\"}},{\"seq\":4,\"time\":4,\"kind\":\"commit_request\",\"tx\":\"P\"},{\"seq\":5,\"time\":5,\"kind\":\"commit_ok\",\"tx\":\"P\"},{\"seq\":6,\"time\":6,\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"connection-A\"},{\"seq\":7,\"time\":7,\"kind\":\"row_read\",\"tx\":\"A\",\"relation\":\"r\",\"predicate\":[],\"rows\":[{\"key\":\"0\",\"version\":\"p1\",\"values\":{\"n\":\"1\",\"b\":true,\"t\":\"\"}}],\"complete\":true},{\"seq\":8,\"time\":8,\"kind\":\"begin\",\"tx\":\"B\",\"connection\":\"connection-B\"},{\"seq\":9,\"time\":9,\"kind\":\"row_read\",\"tx\":\"B\",\"relation\":\"r\",\"predicate\":[],\"rows\":[{\"key\":\"0\",\"version\":\"p1\",\"values\":{\"n\":\"1\",\"b\":true,\"t\":\"\"}}],\"complete\":true},{\"seq\":10,\"time\":10,\"kind\":\"row_write\",\"tx\":\"A\",\"relation\":\"r\",\"key\":\"1\",\"action\":\"insert\",\"version\":\"a1\",\"predecessor\":null,\"values\":{\"n\":\"2\",\"b\":true,\"t\":\"\"}},{\"seq\":11,\"time\":11,\"kind\":\"commit_request\",\"tx\":\"A\"},{\"seq\":12,\"time\":12,\"kind\":\"commit_ok\",\"tx\":\"A\"},{\"seq\":13,\"time\":13,\"kind\":\"row_write\",\"tx\":\"B\",\"relation\":\"r\",\"key\":\"2\",\"action\":\"insert\",\"version\":\"b1\",\"predecessor\":null,\"values\":{\"n\":\"3\",\"b\":true,\"t\":\"\"}},{\"seq\":14,\"time\":14,\"kind\":\"commit_request\",\"tx\":\"B\"},{\"seq\":15,\"time\":15,\"kind\":\"commit_ok\",\"tx\":\"B\"},{\"seq\":16,\"time\":16,\"kind\":\"begin\",\"tx\":\"N\",\"connection\":\"connection-N\"},{\"seq\":17,\"time\":17,\"kind\":\"row_write\",\"tx\":\"N\",\"relation\":\"noise\",\"key\":\"9\",\"action\":\"insert\",\"version\":\"n1\",\"predecessor\":null,\"values\":{\"n\":\"9\",\"b\":true,\"t\":\"\"}},{\"seq\":18,\"time\":18,\"kind\":\"commit_request\",\"tx\":\"N\"},{\"seq\":19,\"time\":19,\"kind\":\"commit_ok\",\"tx\":\"N\"}],\"gaps\":[]}"
    RegisterV4 => ""
  }
}

///|
fn v4_test_masked_categories() -> History {
  {
    model: Serializable,
    initial: { "x": "x0", "y": "y0", "u": "u0", "v": "v0", "w": "w0" },
    version_orders: {
      "x": ["x0", "x1", "x2"],
      "y": ["y0", "y1", "y2"],
      "u": ["u0", "u1"],
      "v": ["v0", "v1"],
      "w": ["w0", "w1"],
    },
    transactions: [
      tx("A", [write_op("x", "x1"), write_op("y", "y2")]),
      tx("B", [write_op("y", "y1"), write_op("x", "x2")]),
      tx("C", [read_op("u", "u0"), write_op("v", "v1")]),
      tx("D", [read_op("v", "v0"), write_op("w", "w1")]),
      tx("E", [read_op("w", "w0"), write_op("u", "u1")]),
    ],
  }
}

///|
test "v4 25 declared reduction preserves searched orders as inferences only" {
  let snapshot = register_history_v4(completion_noise(8)).unwrap()
  let result = reduce_v4(snapshot, preserve=Serializable)
  assert_true(result.analysis().outcome() == Violation)
  assert_true(result.one_minimal())
  let report = reduction_v4_json(result)
  assert_eq(
    v4_test_at(report, ["reducedSource", "versionOrders"]),
    Json::object(Map([])),
  )
  assert_eq(v4_test_at(report, ["source"]), history_v4_json(snapshot))
  assert_eq(
    v4_test_at(report, ["retainedOriginalSeq"]),
    Json(([] : Array[Json])),
  )
  assert_true(verify_reduction_v4(snapshot, report, preserve=Serializable))
}

///|
test "v4 26 capture reduction preserves original sequence provenance" {
  let source = classification_test_cycle_trace("G2-item", noise=true)
  let snapshot = parse_history_v4(source.stringify()).unwrap()
  let result = reduce_v4(snapshot, preserve=Serializable)
  assert_eq(result.status(), "reduced")
  assert_true(result.one_minimal())
  assert_true(result.analysis().outcome() == Violation)
  let report = reduction_v4_json(result)
  assert_eq(capture_field(report, "removedTransactions"), Json(["N"]))
  let old_events = v3_test_items(source, "events")
  let events = v3_test_items(capture_field(report, "reducedSource"), "events")
  let origins = v3_test_items(report, "retainedOriginalSeq")
  assert_eq(events.length(), origins.length())
  for index, event in events {
    let original = old_events.filter(old => {
        capture_field(old, "seq") == origins[index]
      })[0]
    let expected = v4_json_copy(original)
    object_fields_unchecked_v3(expected)["seq"] = capture_field(event, "seq")
    assert_eq(event, expected)
  }
  assert_true(verify_reduction_v4(snapshot, report, preserve=Serializable))
}

///|
test "v4 27 candidate exhaustion never claims transaction minimality" {
  let snapshot = parse_history_v4(
    classification_test_cycle_trace("G2-item", noise=true).stringify(),
  ).unwrap()
  for max_checks in [0, 1] {
    let result = reduce_v4(snapshot, max_checks~, preserve=Serializable)
    assert_eq(result.status(), "budget")
    assert_eq(result.checks(), max_checks)
    assert_false(result.one_minimal())
    assert_true(result.analysis().outcome() == Violation)
    assert_true(
      verify_reduction_v4(
        snapshot,
        reduction_v4_json(result),
        max_checks~,
        preserve=Serializable,
      ),
    )
  }
}

///|
test "v4 28 list and relation reduction retain required writer source closure" {
  for model in [AppendListV4, RelationSetV4] {
    let snapshot = parse_history_v4(v4_test_fixture(model)).unwrap()
    let result = reduce_v4(snapshot, preserve=Serializable)
    assert_true(result.one_minimal())
    assert_true(result.analysis().outcome() == Violation)
    let report = reduction_v4_json(result)
    let ids = v4_capture_transaction_ids(result.history())
    assert_eq(ids.length(), if model == RelationSetV4 { 3 } else { 2 })
    if model == RelationSetV4 {
      assert_true(ids.contains("P"))
    }
    assert_eq(v4_test_at(report, ["source"]), history_v4_json(snapshot))
    assert_true(verify_reduction_v4(snapshot, report, preserve=Serializable))
  }
}

///|
test "v4 29 reduction views and caller budgets are independently bound" {
  let snapshot = register_history_v4(skew()).unwrap()
  let result = reduce_v4(snapshot, preserve=Serializable)
  let original = render_reduction_v4(result)
  let altered = reduction_v4_json(result)
  v4_test_replace(altered, ["reducedSource", "initial", "x"], Json("changed"))
  assert_false(verify_reduction_v4(snapshot, altered, preserve=Serializable))
  assert_eq(render_reduction_v4(result), original)
  assert_true(result.analysis().outcome() == Violation)
  for
    path in [
      ["oneMinimal"],
      ["predicate"],
      ["retainedOriginalSeq"],
      ["execution", "maxChecks"],
      ["analysis", "judgment", "status"],
    ] {
    let tampered = reduction_v4_json(result)
    v4_test_replace(tampered, path, Json("tampered"))
    assert_false(verify_reduction_v4(snapshot, tampered, preserve=Serializable))
  }
}

///|
test "v4 30 reduction rejects invalid budgets and keeps nonviolations explicit" {
  let snapshot = register_history_v4(hist([])).unwrap()
  assert_eq(
    reduce_v4(snapshot, preserve=Serializable).status(),
    "not-violation",
  )
  assert_false(reduce_v4(snapshot, preserve=Serializable).one_minimal())
  for max_checks in [-1, 257] {
    assert_eq(
      reduce_v4(snapshot, max_checks~, preserve=Serializable).status(),
      "invalid",
    )
  }
  assert_eq(
    reduce_v4(
      snapshot,
      options=analysis_options_v4(max_attempts=-1),
      preserve=Serializable,
    ).status(),
    "invalid",
  )
}

///|
test "v4 31 each register category has operation provenance and a real witness" {
  for category in ["G0", "G1c", "G2-item"] {
    let snapshot = parse_history_v4(
      classification_test_cycle_trace(category).stringify(),
    ).unwrap()
    let result = classify_v4(snapshot)
    let report = classification_v4_json(result)
    assert_eq(result.status(), "refuted")
    assert_eq(
      v4_test_at(report, ["judgment", "rules", category, "status"]),
      Json("refuted"),
    )
    assert_eq(
      v4_test_at(report, [
        "judgment", "rules", category, "evidence", "specificCategory",
      ]),
      Json(category),
    )
    assert_eq(
      v4_test_at(report, ["judgment", "acceptsIsolationModels"]),
      Json(false),
    )
    let edges = v3_test_items(
      v4_test_at(report, ["judgment", "rules", category, "evidence"]),
      "edges",
    )
    assert_eq(edges.length(), 2)
    assert_true(
      edges.any(edge => !v3_test_items(edge, "fromObservationSeq").is_empty()),
    )
    assert_true(verify_classification_v4(snapshot, report))
  }
}

///|
test "v4 32 category search finds long RW cycle behind shorter pure WW cycle" {
  let input = v4_test_masked_categories()
  let ordinary = analyze_with_options(input).report
  assert_eq(ordinary.witness.length(), 2)
  assert_true(ordinary.witness.all(edge => edge.kind == WW))
  let snapshot = register_history_v4(input).unwrap()
  let result = classification_v4_json(classify_v4(snapshot))
  let g0 = v4_test_at(result, ["judgment", "rules", "G0", "evidence"])
  let g2 = v4_test_at(result, ["judgment", "rules", "G2-item", "evidence"])
  assert_eq(v3_test_items(g0, "edges").length(), 2)
  assert_eq(v3_test_items(g2, "edges").length(), 3)
  assert_eq(capture_field(g2, "specificCategory"), Json("G2-item"))
  assert_true(verify_classification_v4(snapshot, result))
}

///|
test "v4 33 realtime edges never count as G2 item data dependencies" {
  let input = hist(
    [
      tx("A", [read_op("x", "x0")], start=Some(3L), end=Some(4L)),
      tx("B", [write_op("x", "x1")], start=Some(1L), end=Some(2L)),
    ],
    model=StrictSerializable,
  )
  assert_true(analyze(input).outcome == Violation)
  let snapshot = register_history_v4(input).unwrap()
  let result = classify_v4(snapshot)
  assert_eq(result.status(), "checked-compatible")
  let report = classification_v4_json(result)
  assert_eq(
    v4_test_at(report, ["judgment", "rules", "G2-item", "status"]),
    Json("checked-compatible"),
  )
  let edges = v3_test_items(capture_field(report, "judgment"), "dependencies")
  assert_false(edges.any(edge => capture_field(edge, "kind") == Json("rt")))
}

///|
test "v4 34 classification never invents a missing version order" {
  let snapshot = register_history_v4(completion_noise(3)).unwrap()
  assert_true(analyze_v4(snapshot).outcome() == Violation)
  let result = classify_v4(snapshot)
  assert_eq(result.status(), "inconclusive")
  let report = classification_v4_json(result)
  assert_eq(
    v4_test_at(report, ["judgment", "dependencyGraphComplete"]),
    Json(false),
  )
  assert_eq(
    v4_test_at(report, ["execution", "versionOrderCompletion"]),
    Json(false),
  )
  assert_eq(
    v4_test_at(report, ["observations", "document", "versionOrders"]),
    Json::object(Map([])),
  )
  for category in ["G0", "G1c", "G2-item"] {
    assert_eq(
      v4_test_at(report, ["judgment", "rules", category, "status"]),
      Json("unknown"),
    )
  }
}

///|
test "v4 35 reliable known category refutation survives incomplete unrelated facts" {
  let input = skew()
  input.transactions.push(tx("unknown", [], status=Unknown))
  let snapshot = register_history_v4(input).unwrap()
  let result = classify_v4(snapshot)
  assert_eq(result.status(), "refuted")
  let report = classification_v4_json(result)
  assert_eq(
    v4_test_at(report, ["judgment", "dependencyGraphComplete"]),
    Json(false),
  )
  assert_eq(
    v4_test_at(report, ["judgment", "rules", "G2-item", "status"]),
    Json("refuted"),
  )
  assert_eq(
    v4_test_at(report, ["judgment", "rules", "G0", "status"]),
    Json("unknown"),
  )
}

///|
test "v4 36 category budget exhaustion does not erase another category proof" {
  let snapshot = register_history_v4(v4_test_masked_categories()).unwrap()
  let result = classify_v4(snapshot, max_states=1)
  let report = classification_v4_json(result)
  assert_eq(result.status(), "refuted")
  assert_eq(
    v4_test_at(report, ["judgment", "rules", "G0", "status"]),
    Json("refuted"),
  )
  assert_eq(
    v4_test_at(report, ["judgment", "rules", "G2-item", "status"]),
    Json("unknown"),
  )
  assert_true(verify_classification_v4(snapshot, report, max_states=1))
  assert_false(verify_classification_v4(snapshot, report))
}

///|
test "v4 37 list categories use original complete list observation identities" {
  let source = classification26_test_list_skew()
  let snapshot = parse_history_v4(source.stringify()).unwrap()
  let result = classify_v4(snapshot)
  assert_eq(result.status(), "refuted")
  let report = classification_v4_json(result)
  assert_eq(
    v4_test_at(report, ["judgment", "rules", "G2-item", "status"]),
    Json("refuted"),
  )
  assert_eq(v4_test_at(report, ["observations", "document"]), source)
  assert_true(verify_classification_v4(snapshot, report))
}

///|
test "v4 38 relation category classification remains explicitly unsupported" {
  let snapshot = parse_history_v4(
    v4_test_model_complete(RelationSetV4, []).stringify(),
  ).unwrap()
  let result = classify_v4(snapshot)
  assert_eq(result.status(), "unsupported")
  let report = classification_v4_json(result)
  for category in ["G0", "G1c", "G2-item"] {
    assert_eq(
      v4_test_at(report, ["judgment", "rules", category, "status"]),
      Json("unsupported"),
    )
  }
  assert_true(verify_classification_v4(snapshot, report))
}

///|
test "v4 39 category options and JSON views cannot authorize changed evidence" {
  let snapshot = register_history_v4(skew()).unwrap()
  let categories = ["G0", "G1c", "G2-item"]
  let result = classify_v4(snapshot, categories~)
  let original = render_classification_v4(result)
  categories[0] = "tampered"
  assert_eq(render_classification_v4(result), original)
  for
    path in [
      ["algorithm"],
      ["semanticContract"],
      ["judgment", "rules", "G2-item", "evidence"],
      ["execution", "counterContract"],
      ["execution", "limits", "statesPerCategory"],
    ] {
    let altered = classification_v4_json(result)
    v4_test_replace(altered, path, Json("tampered"))
    assert_false(verify_classification_v4(snapshot, altered))
  }
  for categories in [["G0", "G0"], ["unknown"], []] {
    assert_eq(classify_v4(snapshot, categories~).status(), "invalid")
  }
  assert_eq(classify_v4(snapshot, max_states=-1).status(), "invalid")
  assert_eq(classify_v4(snapshot, max_edge_checks=1000001).status(), "invalid")
}

///|
test "v4 40 capture unknown outcome cannot become checked-compatible classification" {
  let source = v3_test_trace([
    { "kind": "begin", "tx": "A", "connection": "c" },
    { "kind": "commit_request", "tx": "A" },
    { "kind": "disconnect", "tx": "A" },
  ])
  let snapshot = parse_history_v4(source.stringify()).unwrap()
  let result = classify_v4(snapshot)
  assert_eq(result.status(), "inconclusive")
  let report = classification_v4_json(result)
  assert_eq(v4_test_at(report, ["observations", "document"]), source)
  for category in ["G0", "G1c", "G2-item"] {
    assert_eq(
      v4_test_at(report, ["judgment", "rules", category, "status"]),
      Json("unknown"),
    )
  }
}

///|
test "v4 41 classification capacity remains separate from exact enumeration" {
  let snapshot = register_history_v4(
    hist(Array::makei(129, i => tx("T" + i.to_string(), []))),
  ).unwrap()
  let result = classify_v4(snapshot)
  assert_eq(result.status(), "inconclusive")
  let report = classification_v4_json(result)
  assert_eq(
    v4_test_at(report, ["judgment", "rules", "G0", "reason"]),
    Json("register-category-capacity-128-4096"),
  )
  assert_true(verify_classification_v4(snapshot, report))
  let many_operations = register_history_v4(
    hist([tx("R", Array::make(4097, read_op("x", "x0")))]),
  ).unwrap()
  assert_eq(classify_v4(many_operations).status(), "inconclusive")
}

///|
test "v4 42 zero classification edge budget requires unknown only when work remains" {
  let snapshot = register_history_v4(skew()).unwrap()
  let limited = classify_v4(snapshot, max_edge_checks=0)
  assert_eq(limited.status(), "inconclusive")
  let report = classification_v4_json(limited)
  for category in ["G0", "G1c", "G2-item"] {
    assert_eq(
      v4_test_at(report, ["judgment", "rules", category, "status"]),
      Json("unknown"),
    )
    assert_eq(
      v4_test_at(report, ["judgment", "rules", category, "edgeChecks"]),
      Json(0),
    )
  }
  assert_true(verify_classification_v4(snapshot, report, max_edge_checks=0))
  let empty = register_history_v4(hist([])).unwrap()
  assert_eq(
    classify_v4(empty, max_states=0, max_edge_checks=0).status(),
    "checked-compatible",
  )
}

///|
test "v4 43 reduction requires an explicit matching model-refutation target" {
  let strict = register_history_v4(
    hist(
      [
        tx("A", [read_op("x", "x0")], start=Some(3L), end=Some(4L)),
        tx("B", [write_op("x", "x1")], start=Some(1L), end=Some(2L)),
      ],
      model=StrictSerializable,
    ),
  ).unwrap()
  let matched = reduce_v4(strict, preserve=StrictSerializable)
  assert_true(matched.one_minimal())
  assert_true(matched.analysis().outcome() == Violation)
  let report = reduction_v4_json(matched)
  assert_eq(
    v4_test_at(report, ["predicate", "modelDefinition"]),
    Json("declared-register-strict-serializable-v1"),
  )
  assert_eq(
    v4_test_at(report, ["predicate", "requestedModel"]),
    Json("strict-serializable"),
  )
  assert_true(verify_reduction_v4(strict, report, preserve=StrictSerializable))
  assert_false(verify_reduction_v4(strict, report, preserve=Serializable))
  let mismatched = reduce_v4(strict, preserve=Serializable)
  assert_eq(mismatched.status(), "unsupported")
  assert_eq(mismatched.checks(), 0)
  assert_false(mismatched.one_minimal())
  assert_eq(
    v4_test_at(reduction_v4_json(mismatched), ["predicate", "targetSupported"]),
    Json(false),
  )
  for
    snapshot in [
      register_history_v4(skew()).unwrap(),
      parse_history_v4(v3_test_completed([]).stringify()).unwrap(),
      parse_history_v4(v4_test_model_complete(AppendListV4, []).stringify()).unwrap(),
      parse_history_v4(v4_test_model_complete(RelationSetV4, []).stringify()).unwrap(),
    ] {
    let result = reduce_v4(snapshot, preserve=StrictSerializable)
    assert_eq(result.status(), "unsupported")
    assert_eq(result.checks(), 0)
    assert_false(result.one_minimal())
    let json = reduction_v4_json(result)
    assert_eq(v4_test_at(json, ["predicate", "modelDefinition"]), Json::null())
    assert_eq(v4_test_at(json, ["source"]), history_v4_json(snapshot))
  }
}

///|
fn v4_test_source_mismatch_minimality(model : DataModelV4) -> Unit raise {
  let write : Json = if model == AppendListV4 {
    { "kind": "append", "tx": "P", "key": "x", "id": "p", "value": "original" }
  } else {
    {
      "kind": "row_write",
      "tx": "P",
      "relation": "r",
      "key": "1",
      "action": "insert",
      "version": "p",
      "predecessor": Json::null(),
      "values": { "n": "1" },
    }
  }
  let read : Json = if model == AppendListV4 {
    {
      "kind": "list_read",
      "tx": "A",
      "key": "x",
      "items": [{ "id": "p", "value": "changed" }],
    }
  } else {
    {
      "kind": "row_read",
      "tx": "A",
      "relation": "r",
      "predicate": [],
      "rows": [{ "key": "1", "version": "p", "values": { "n": "2" } }],
      "complete": true,
    }
  }
  let source = v4_test_model_trace(model, [
    { "kind": "begin", "tx": "P", "connection": "p" },
    write,
    { "kind": "commit_request", "tx": "P" },
    { "kind": "commit_ok", "tx": "P" },
    { "kind": "begin", "tx": "A", "connection": "a" },
    read,
    { "kind": "commit_request", "tx": "A" },
    { "kind": "commit_ok", "tx": "A" },
  ])
  let snapshot = parse_history_v4(source.stringify()).unwrap()
  let options = analysis_options_v4(max_states=0)
  assert_true(analyze_v4(snapshot, options~).outcome() == Violation)
  let (without_reader, _) = v3_without_transaction(source, "A")
  let candidate = parse_history_v4(without_reader.stringify()).unwrap()
  let candidate_report = analysis_v4_json(analyze_v4(candidate, options~))
  assert_eq(
    v4_test_at(candidate_report, ["judgment", "status"]),
    Json("inconclusive"),
  )
  assert_eq(
    v4_test_at(candidate_report, ["judgment", "coverage", "complete"]),
    Json(true),
  )
  let limited = reduce_v4(snapshot, preserve=Serializable, options~)
  assert_false(limited.one_minimal())
  assert_eq(limited.status(), "budget")
  assert_true(limited.analysis().outcome() == Violation)
  assert_eq(limited.checks(), 2)
  let report = reduction_v4_json(limited)
  let unresolved = v3_test_items(
    capture_field(report, "execution"),
    "unresolvedCandidates",
  )
  assert_eq(unresolved.length(), 1)
  assert_eq(capture_field(unresolved[0], "transaction"), Json("A"))
  assert_true(
    verify_reduction_v4(snapshot, report, preserve=Serializable, options~),
  )
  assert_false(verify_reduction_v4(snapshot, report, preserve=Serializable))
  // A missing producer is outside the source-closed predicate; a completed
  // reader deletion can finish this pass once its actual search budget permits.
  let completed = reduce_v4(snapshot, preserve=Serializable)
  assert_true(completed.one_minimal())
  assert_eq(completed.status(), "unchanged")
}

///|
test "v4 44 list source-closed undecided deletion prevents a minimality claim" {
  v4_test_source_mismatch_minimality(AppendListV4)
}

///|
test "v4 45 relation source-closed undecided deletion prevents a minimality claim" {
  v4_test_source_mismatch_minimality(RelationSetV4)
}

///|
test "v4 46 declared register search unknown cannot prove transaction minimality" {
  let input : History = {
    model: Serializable,
    initial: { "x": "x0", "y": "y0", "u": "u0", "z": "z0" },
    version_orders: { "x": ["x0", "x1"], "y": ["y0", "y1"], "u": ["u0", "u1"] },
    transactions: [
      tx("A", [read_op("x", "x0"), write_op("y", "y1"), write_op("z", "zA")]),
      tx("B", [read_op("y", "y0"), write_op("u", "u1"), write_op("z", "zB")]),
      tx("C", [read_op("u", "u0"), write_op("x", "x1"), write_op("z", "zC")]),
    ],
  }
  let snapshot = register_history_v4(input).unwrap()
  let options = analysis_options_v4(max_attempts=0)
  assert_true(analyze_v4(snapshot, options~).outcome() == Violation)
  for index in 0..<3 {
    let candidate = register_history_v4(without_chunk(input, index, 1)).unwrap()
    assert_true(analyze_v4(candidate, options~).outcome() == Inconclusive)
  }
  let limited = reduce_v4(snapshot, preserve=Serializable, options~)
  assert_false(limited.one_minimal())
  assert_eq(limited.status(), "budget")
  assert_true(limited.analysis().outcome() == Violation)
  let report = reduction_v4_json(limited)
  assert_false(
    v3_test_items(capture_field(report, "execution"), "unresolvedCandidates").is_empty(),
  )
  assert_true(
    verify_reduction_v4(snapshot, report, preserve=Serializable, options~),
  )
  assert_true(reduce_v4(snapshot, preserve=Serializable).one_minimal())
}

///|
test "v4 47 final declared minimality rechecks never exceed maxChecks" {
  let input = skew()
  let legacy = reduce_with_options(input)
  assert_true(legacy.reduction.one_minimal)
  let snapshot = register_history_v4(input).unwrap()
  let remaining = legacy.reduction.history.transactions.length()
  for added in 0..<=remaining {
    let max_checks = legacy.reduction.checks + added
    let result = reduce_v4(snapshot, preserve=Serializable, max_checks~)
    assert_true(result.checks() <= max_checks)
    assert_eq(result.checks(), max_checks)
    assert_eq(result.one_minimal(), added == remaining)
    let report = reduction_v4_json(result)
    assert_eq(
      v4_test_at(report, ["execution", "minimalityRechecks"]),
      Json(added),
    )
    assert_true(
      verify_reduction_v4(snapshot, report, preserve=Serializable, max_checks~),
    )
  }
}
