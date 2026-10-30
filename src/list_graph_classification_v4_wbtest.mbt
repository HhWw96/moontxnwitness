///|
fn leg_classify_history(body : Array[Json]) -> HistoryV4 {
  parse_history_v4(classification26_test_list(body).stringify()).unwrap()
}

///|
fn leg_classify_single_body() -> Array[Json] {
  let body = [
    leg_test_begin("A"),
    leg_test_begin("B"),
    leg_test_read("B", []),
    leg_test_append("A", "a1"),
    leg_test_append("A", "a2"),
    leg_test_append("A", "ay", key="y"),
    leg_test_read("B", ["ay"], key="y"),
  ]
  leg_test_commit(body, "A")
  leg_test_commit(body, "B")
  body
}

///|
fn leg_classify_number(value : Json) -> Int32 {
  match value {
    Number(n, ..) => n.to_int()
    _ => -1
  }
}

///|
test "effective list classification 01 explicit profile leaves legacy output unchanged" {
  let snapshot = leg_classify_history(leg_test_external(["a1", "a2"]))
  let legacy = classify_v4(snapshot)
  assert_eq(
    render_classification_v4(legacy),
    render_classification_v4(classify_v4(snapshot, list_graph="legacy")),
  )
  assert_eq(
    v4_test_at(classification_v4_json(legacy), ["algorithm"]),
    Json("v4-source-bound-category-bfs-1"),
  )
  assert_false(
    object_fields_unchecked_v3(
      v4_test_at(classification_v4_json(legacy), ["execution"]),
    ).contains("listGraph"),
  )
  let result = classify_v4(snapshot, list_graph="effective-v1")
  assert_eq(result.status(), "checked-compatible")
  let report = classification_v4_json(result)
  assert_eq(
    v4_test_at(report, ["algorithm"]),
    Json("v4-source-bound-category-list-effective-1"),
  )
  assert_eq(
    v4_test_at(report, ["execution", "counterContract"]),
    Json("v4-list-effective-category-counters-1"),
  )
  assert_eq(
    v4_test_at(report, ["execution", "listGraph"]),
    Json("effective-v1"),
  )
  assert_eq(
    v4_test_at(report, ["execution", "limits", "listTransactions"]),
    Json(128),
  )
  assert_eq(
    v4_test_at(report, ["execution", "limits", "listOperations"]),
    Json(4096),
  )
  assert_eq(
    v4_test_at(report, ["execution", "limits", "listGraphChecks"]),
    Json(1000000),
  )
  assert_false(
    object_fields_unchecked_v3(v4_test_at(report, ["execution", "limits"])).contains(
      "listCommittedTransactions",
    ),
  )
  assert_true(
    verify_classification_v4(snapshot, report, list_graph="effective-v1"),
  )
  assert_false(verify_classification_v4(snapshot, report))
}

///|
test "effective list classification 02 rollback keeps delivered own reads and original facts" {
  let snapshot = leg_classify_history(leg_test_rollback_body())
  let report = classification_v4_json(
    classify_v4(snapshot, list_graph="effective-v1"),
  )
  assert_eq(
    v4_test_at(report, ["judgment", "status"]),
    Json("checked-compatible"),
  )
  assert_eq(
    v4_test_at(report, ["observations", "document"]),
    snapshot.source_document,
  )
  let reads = v3_test_items(
    v4_test_at(report, ["inferences", "listGraph"]),
    "readStates",
  )
  assert_eq(v4_test_at(reads[0], ["ownAtRead"]), Json(["a1", "a2"]))
  assert_eq(v4_test_at(reads[1], ["ownAtRead"]), Json(["a1", "a3"]))
  assert_true(reads.all(read => capture_field(read, "usable") == Json(true)))
  assert_eq(
    v3_test_items(v4_test_at(report, ["writeEffects"]), "entries").length(),
    3,
  )
}

///|
test "effective list classification 03 missing and intermediate sources stay unknown" {
  let missing = [leg_test_begin("R"), leg_test_read("R", ["absent"])]
  leg_test_commit(missing, "R")
  for body in [missing, leg_test_external(["a1"]), leg_test_external(["a2"])] {
    let snapshot = leg_classify_history(body)
    let report = classification_v4_json(
      classify_v4(
        snapshot,
        categories=["G0", "G1c", "G2-item", "G-single"],
        list_graph="effective-v1",
      ),
    )
    assert_eq(v4_test_at(report, ["judgment", "status"]), Json("inconclusive"))
    assert_false(
      v3_test_items(v4_test_at(report, ["judgment"]), "sourceOrOrderGaps").is_empty(),
    )
    for category in ["G0", "G1c", "G2-item", "G-single"] {
      assert_eq(
        capture_field(gs_test_rule(report, category), "status"),
        Json("unknown"),
      )
      assert_eq(
        capture_field(gs_test_rule(report, category), "evidence"),
        Json::null(),
      )
    }
  }
}

///|
test "effective list classification 04 incompatible item orders do not become G0" {
  let snapshot = leg_classify_history(leg_test_incompatible_item_orders())
  let report = classification_v4_json(
    classify_v4(snapshot, list_graph="effective-v1"),
  )
  assert_eq(
    capture_field(gs_test_rule(report, "G0"), "status"),
    Json("unknown"),
  )
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("inconclusive"))
  assert_true(
    v3_test_items(v4_test_at(report, ["judgment"]), "dependencies").is_empty(),
  )
  assert_false(
    v3_test_items(
      v4_test_at(report, ["inferences", "listGraph"]),
      "quarantinedDependencies",
    ).is_empty(),
  )
}

///|
fn leg_classify_isolated_history() -> HistoryV4 raise {
  let body = leg_test_incompatible_item_orders()
  body.push(leg_test_begin("T"))
  body.push(leg_test_begin("U"))
  body.push(leg_test_read("U", [], key="y"))
  body.push(leg_test_append("T", "ty", key="y"))
  body.push(leg_test_append("T", "tz", key="z"))
  body.push(leg_test_read("U", ["tz"], key="z"))
  leg_test_commit(body, "T")
  leg_test_commit(body, "U")
  let trace = classification26_test_list(body)
  object_fields_unchecked_v3(v3_test_items(trace, "events")[0])["initial"] = {
    "x": [],
    "y": [],
    "z": [],
  }
  parse_history_v4(trace.stringify()).unwrap()
}

///|
test "effective list classification 05 isolated source conflict retains other key refutation" {
  let snapshot = leg_classify_isolated_history()
  let report = classification_v4_json(
    classify_v4(
      snapshot,
      categories=["G0", "G-single"],
      list_graph="effective-v1",
    ),
  )
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("refuted"))
  assert_eq(
    v4_test_at(report, ["judgment", "dependencyGraphComplete"]),
    Json(false),
  )
  assert_eq(
    capture_field(gs_test_rule(report, "G0"), "status"),
    Json("unknown"),
  )
  assert_eq(
    capture_field(gs_test_rule(report, "G-single"), "status"),
    Json("refuted"),
  )
  for
    entry in v3_test_items(
      capture_field(gs_test_rule(report, "G-single"), "evidence"),
      "edges",
    ) {
    assert_true(
      [Json("y"), Json("z")].contains(v4_test_at(entry, ["edge", "key"])),
    )
    assert_false(v3_test_items(entry, "sources").is_empty())
  }
  assert_true(
    verify_classification_v4(
      snapshot,
      report,
      categories=["G0", "G-single"],
      list_graph="effective-v1",
    ),
  )
}

///|
test "effective list classification 06 exactly one RW witness preserves raw source seq and cycle closure" {
  let snapshot = leg_classify_history(leg_classify_single_body())
  let report = classification_v4_json(
    classify_v4(snapshot, categories=["G-single"], list_graph="effective-v1"),
  )
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("refuted"))
  let evidence = capture_field(gs_test_rule(report, "G-single"), "evidence")
  assert_eq(capture_field(evidence, "specificCategory"), Json("G-single-item"))
  assert_eq(capture_field(evidence, "rwEdgeCount"), Json(1))
  let edges = v3_test_items(evidence, "edges")
  assert_eq(edges.length(), 2)
  for index, entry in edges {
    assert_eq(
      v4_test_at(entry, ["edge", "to"]),
      v4_test_at(edges[(index + 1) % edges.length()], ["edge", "from"]),
    )
    let sources = v3_test_items(entry, "sources")
    assert_false(sources.is_empty())
    for source in sources {
      let read_seq = capture_field(source, "readSeq")
      assert_true(leg_classify_number(read_seq) >= 0)
      let observations = v3_test_items(snapshot.source_document, "events")
      assert_true(
        observations.any(raw => {
          capture_field(raw, "seq") == read_seq &&
          capture_field(raw, "kind") == Json("list_read")
        }),
      )
    }
  }
  assert_true(
    verify_classification_v4(
      snapshot,
      report,
      categories=["G-single"],
      list_graph="effective-v1",
    ),
  )
}

///|
test "effective list classification 07 graph construction budget is bound and exact" {
  let body = leg_classify_single_body()
  let needed = leg_test_graph(body).checks
  assert_true(needed > 0)
  let snapshot = leg_classify_history(body)
  let exact = classification_v4_json(
    classify_v4(
      snapshot,
      categories=["G-single"],
      list_graph="effective-v1",
      max_list_graph_checks=needed,
    ),
  )
  assert_eq(v4_test_at(exact, ["judgment", "status"]), Json("refuted"))
  assert_eq(
    v4_test_at(exact, [
      "execution", "listGraphConstruction", "constructionChecks",
    ]),
    Json(needed),
  )
  assert_eq(
    v4_test_at(exact, ["execution", "listGraphConstruction", "limited"]),
    Json(false),
  )
  assert_true(
    verify_classification_v4(
      snapshot,
      exact,
      categories=["G-single"],
      list_graph="effective-v1",
      max_list_graph_checks=needed,
    ),
  )
  assert_false(
    verify_classification_v4(
      snapshot,
      exact,
      categories=["G-single"],
      list_graph="effective-v1",
      max_list_graph_checks=needed - 1,
    ),
  )
  let limited = classification_v4_json(
    classify_v4(
      snapshot,
      categories=["G-single"],
      list_graph="effective-v1",
      max_list_graph_checks=0,
    ),
  )
  assert_eq(v4_test_at(limited, ["judgment", "status"]), Json("inconclusive"))
  assert_eq(
    v4_test_at(limited, [
      "execution", "listGraphConstruction", "constructionChecks",
    ]),
    Json(0),
  )
  assert_eq(
    v4_test_at(limited, ["execution", "listGraphConstruction", "limited"]),
    Json(true),
  )
}

///|
test "effective list classification 08 category budgets do not borrow graph construction budget" {
  let snapshot = leg_classify_history(leg_classify_single_body())
  let full = classification_v4_json(
    classify_v4(snapshot, categories=["G-single"], list_graph="effective-v1"),
  )
  let states = leg_classify_number(
    capture_field(gs_test_rule(full, "G-single"), "states"),
  )
  let edge_checks = leg_classify_number(
    capture_field(gs_test_rule(full, "G-single"), "edgeChecks"),
  )
  assert_true(states > 0 && edge_checks > 0)
  let exact = classify_v4(
    snapshot,
    categories=["G-single"],
    list_graph="effective-v1",
    max_states=states,
    max_edge_checks=edge_checks,
  )
  assert_eq(exact.status(), "refuted")
  for options in [(states - 1, edge_checks), (states, edge_checks - 1)] {
    let result = classify_v4(
      snapshot,
      categories=["G-single"],
      list_graph="effective-v1",
      max_states=options.0,
      max_edge_checks=options.1,
    )
    assert_eq(result.status(), "inconclusive")
    assert_eq(
      capture_field(
        gs_test_rule(classification_v4_json(result), "G-single"),
        "status",
      ),
      Json("unknown"),
    )
  }
}

///|
test "effective list classification 09 budgets and provenance cannot be changed by report" {
  let snapshot = leg_classify_history(leg_classify_single_body())
  let report = classification_v4_json(
    classify_v4(snapshot, categories=["G-single"], list_graph="effective-v1"),
  )
  object_fields_unchecked_v3(v4_test_at(report, ["execution", "limits"]))["listGraphChecks"] = Json(
    1000001,
  )
  assert_false(
    verify_classification_v4(
      snapshot,
      report,
      categories=["G-single"],
      list_graph="effective-v1",
    ),
  )
  let provenance = classification_v4_json(
    classify_v4(snapshot, categories=["G-single"], list_graph="effective-v1"),
  )
  let sources = v3_test_items(
    v3_test_items(
      capture_field(gs_test_rule(provenance, "G-single"), "evidence"),
      "edges",
    )[0],
    "sources",
  )
  object_fields_unchecked_v3(sources[0])["readSeq"] = Json(999)
  assert_false(
    verify_classification_v4(
      snapshot,
      provenance,
      categories=["G-single"],
      list_graph="effective-v1",
    ),
  )
  assert_true(
    verify_classification_v4(
      snapshot,
      classification_v4_json(
        classify_v4(
          snapshot,
          categories=["G-single"],
          list_graph="effective-v1",
        ),
      ),
      categories=["G-single"],
      list_graph="effective-v1",
    ),
  )
}

///|
test "effective list classification 10 wrong models are explicitly unsupported and invalid options rejected" {
  let register = register_history_v4(skew()).unwrap()
  let relation = parse_history_v4(
    v4_test_model_complete(RelationSetV4, []).stringify(),
  ).unwrap()
  for snapshot in [register, relation] {
    let result = classify_v4(snapshot, list_graph="effective-v1")
    assert_eq(result.status(), "unsupported")
    assert_eq(
      capture_field(
        gs_test_rule(classification_v4_json(result), "G0"),
        "reason",
      ),
      Json("effective-list-graph-requires-append-list-v1"),
    )
  }
  let snapshot = leg_classify_history(leg_test_external(["a1", "a2"]))
  assert_eq(classify_v4(snapshot, list_graph="guessed").status(), "invalid")
  assert_eq(classify_v4(snapshot, max_list_graph_checks=1).status(), "invalid")
  assert_eq(
    classify_v4(snapshot, list_graph="effective-v1", max_list_graph_checks=-1).status(),
    "invalid",
  )
  assert_eq(
    classify_v4(
      snapshot,
      list_graph="effective-v1",
      max_list_graph_checks=1000001,
    ).status(),
    "invalid",
  )
}

///|
test "effective list classification 11 text API and verifier bind explicit profile" {
  let source = classification26_test_list(leg_classify_single_body()).stringify()
  let options : Json = {
    "listGraph": "effective-v1",
    "categories": ["G-single"],
    "maxListGraphChecks": 1000000,
  }
  let text = classify_v4_json(source, options.stringify())
  let report = @json.parse(text)
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("refuted"))
  assert_eq(
    capture_field(
      @json.parse(
        verify_classification_v4_json(source, text, options.stringify()),
      ),
      "valid",
    ),
    Json(true),
  )
  assert_eq(
    capture_field(
      @json.parse(verify_classification_v4_json(source, text, "{}")),
      "valid",
    ),
    Json(false),
  )
  for
    invalid in [
      ({ "listGraph": "bad" } : Json),
      { "maxListGraphChecks": 0 },
      { "listGraph": "effective-v1", "maxListGraphChecks": 1000001 },
      { "listGraph": "effective-v1", "maxListGraphChecks": 1.5 },
      { "listGraph": "effective-v1", "categories": ["G-single", "G-single"] },
    ] {
    assert_eq(
      capture_field(
        @json.parse(classify_v4_json(source, invalid.stringify())),
        "format",
      ),
      Json("moontxnwitness-wire-error/v4"),
    )
  }
}

///|
test "effective list classification 12 graph capacity is independent from exact search limits" {
  let body : Array[Json] = []
  let ids : Array[String] = []
  for number in 0..<7 {
    let tx = "T" + number.to_string()
    let item = "i" + number.to_string()
    body.push(leg_test_begin(tx))
    body.push(leg_test_append(tx, item))
    leg_test_commit(body, tx)
    ids.push(item)
  }
  body.push(leg_test_begin("R"))
  body.push(leg_test_read("R", ids))
  leg_test_commit(body, "R")
  let snapshot = leg_classify_history(body)
  assert_true(analyze_v4(snapshot).outcome() == Inconclusive)
  assert_eq(
    classify_v4(snapshot, list_graph="effective-v1").status(),
    "checked-compatible",
  )
  assert_eq(classify_v4(snapshot).status(), "inconclusive")
}

///|
test "effective list classification 13 incompatible transaction blocks remain genuine WW cycle" {
  let body = [
    leg_test_begin("A"),
    leg_test_begin("B"),
    leg_test_append("A", "a1"),
    leg_test_append("B", "b"),
    leg_test_append("A", "a2"),
  ]
  leg_test_commit(body, "A")
  leg_test_commit(body, "B")
  body.push(leg_test_begin("R"))
  body.push(leg_test_read("R", ["a1", "b", "a2"]))
  leg_test_commit(body, "R")
  let snapshot = leg_classify_history(body)
  let report = classification_v4_json(
    classify_v4(snapshot, categories=["G0"], list_graph="effective-v1"),
  )
  assert_eq(v4_test_at(report, ["judgment", "status"]), Json("refuted"))
  assert_eq(
    v4_test_at(report, ["judgment", "dependencyGraphComplete"]),
    Json(false),
  )
  assert_eq(
    v3_test_items(
      capture_field(gs_test_rule(report, "G0"), "evidence"),
      "edges",
    ).length(),
    2,
  )
}

///|
test "effective list classification 14 returned report mutation cannot change snapshot or future result" {
  let snapshot = leg_classify_history(leg_classify_single_body())
  let result = classify_v4(
    snapshot,
    categories=["G-single"],
    list_graph="effective-v1",
  )
  let original = render_classification_v4(result)
  let view = classification_v4_json(result)
  object_fields_unchecked_v3(v4_test_at(view, ["observations", "document"]))["name"] = Json(
    "changed",
  )
  object_fields_unchecked_v3(v4_test_at(view, ["inferences", "listGraph"]))["quarantinedDependencies"] = Json([
      "fake",
    ],
  )
  assert_eq(render_classification_v4(result), original)
  assert_eq(
    render_classification_v4(
      classify_v4(snapshot, categories=["G-single"], list_graph="effective-v1"),
    ),
    original,
  )
}
