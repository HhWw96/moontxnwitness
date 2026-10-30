///|
fn anomaly_test_report(source : Json) -> Json raise {
  match parse_history_v4(source.stringify()) {
    Ok(history) => inspect_anomalies_v4(history)
    Err(reason) => fail(reason)
  }
}

///|
fn anomaly_test_entries(report : Json, field : String) -> Array[Json] {
  anomaly_v4_array(object_fields_unchecked_v3(report).at(field))
}

///|
fn anomaly_test_has(report : Json, kind : String) -> Bool raise {
  anomaly_test_entries(report, "findings").any(item => {
    capture_field(item, "kind") == Json(kind)
  }) ||
  anomaly_v4_array(v4_test_at(report, ["coverage", "diagnosticGaps"])).any(item => {
    capture_field(item, "kind") == Json(kind)
  })
}

///|
fn anomaly_test_finding(report : Json, kind : String) -> Json raise {
  for finding in anomaly_test_entries(report, "findings") {
    if capture_field(finding, "kind") == Json(kind) {
      return finding
    }
  }
  Json::null()
}

///|
fn anomaly_test_list(body : Array[Json]) -> Json {
  v4_test_model_trace(AppendListV4, body)
}

///|
fn anomaly_test_list_order(reverse~ : Bool = true) -> Json {
  let body : Array[Json] = [
    { "kind": "begin", "tx": "A", "connection": "a" },
    { "kind": "append", "tx": "A", "key": "x", "id": "a", "value": "same" },
    { "kind": "commit_request", "tx": "A" },
    { "kind": "commit_ok", "tx": "A" },
    { "kind": "begin", "tx": "B", "connection": "b" },
    { "kind": "append", "tx": "B", "key": "x", "id": "b", "value": "same" },
    { "kind": "commit_request", "tx": "B" },
    { "kind": "commit_ok", "tx": "B" },
    { "kind": "begin", "tx": "C", "connection": "c" },
    {
      "kind": "list_read",
      "tx": "C",
      "key": "x",
      "items": [{ "id": "a", "value": "same" }, { "id": "b", "value": "same" }],
    },
    { "kind": "commit_request", "tx": "C" },
    { "kind": "commit_ok", "tx": "C" },
  ]
  if reverse {
    body.push({ "kind": "begin", "tx": "D", "connection": "d" })
    body.push({
      "kind": "list_read",
      "tx": "D",
      "key": "x",
      "items": [{ "id": "b", "value": "same" }, { "id": "a", "value": "same" }],
    })
    body.push({ "kind": "commit_request", "tx": "D" })
    body.push({ "kind": "commit_ok", "tx": "D" })
  }
  anomaly_test_list(body)
}

///|
test "anomalies v4 01 separate contract never accepts an isolation model" {
  let h = register_history_v4(hist([tx("A", [read_op("x", "x0")])])).unwrap()
  let report = inspect_anomalies_v4(h)
  assert_eq(
    capture_field(report, "format"),
    Json("moontxnwitness-anomaly-inspection/v4"),
  )
  assert_eq(capture_field(report, "status"), Json("checked"))
  assert_eq(
    v4_test_at(report, ["scope", "acceptsIsolationModels"]),
    Json(false),
  )
  assert_eq(v4_test_at(report, ["scope", "authenticityVerified"]), Json(false))
  assert_true(verify_anomalies_v4(h, report))
}

///|
test "anomalies v4 02 declared own future write has program-position witness" {
  let h = register_history_v4(
    hist([tx("A", [read_op("x", "x1"), write_op("x", "x1")])]),
  ).unwrap()
  let report = inspect_anomalies_v4(h)
  let evidence = capture_field(
    anomaly_test_finding(report, "future-read"),
    "evidence",
  )
  assert_eq(v4_test_at(evidence, ["read", "operationIndex"]), Json(0))
  assert_eq(v4_test_at(evidence, ["source", "operationIndex"]), Json(1))
  assert_eq(
    capture_field(
      anomaly_test_finding(report, "future-read"),
      "impliedAnomalies",
    ),
    Json(["G1c", "G1"]),
  )
  assert_eq(capture_field(report, "status"), Json("findings"))
}

///|
test "anomalies v4 03 prior own write is not a future read" {
  let h = register_history_v4(
    hist([tx("A", [write_op("x", "x1"), read_op("x", "x1")])]),
  ).unwrap()
  assert_false(anomaly_test_has(inspect_anomalies_v4(h), "future-read"))
}

///|
test "anomalies v4 04 captured own future read survives projection gap" {
  let source = v3_test_completed([
    { "kind": "read", "tx": "A", "key": "x", "version": "x1" },
    {
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "x1",
      "predecessor": "x0",
    },
  ])
  let report = anomaly_test_report(source)
  assert_true(anomaly_test_has(report, "future-read"))
  assert_eq(
    v4_test_at(report, ["coverage", "inputCoverage", "complete"]),
    Json(false),
  )
  assert_eq(v4_test_at(report, ["observations", "document"]), source)
}

///|
test "anomalies v4 05 cross-client later write observation does not prove future" {
  let source = v3_test_trace([
    { "kind": "begin", "tx": "A", "connection": "a" },
    { "kind": "read", "tx": "A", "key": "x", "version": "x1" },
    { "kind": "begin", "tx": "B", "connection": "b" },
    {
      "kind": "write",
      "tx": "B",
      "key": "x",
      "version": "x1",
      "predecessor": "x0",
    },
    { "kind": "commit_request", "tx": "A" },
    { "kind": "commit_ok", "tx": "A" },
    { "kind": "commit_request", "tx": "B" },
    { "kind": "commit_ok", "tx": "B" },
  ])
  let report = anomaly_test_report(source)
  assert_false(anomaly_test_has(report, "future-read"))
  assert_true(anomaly_test_has(report, "source-observation-order"))
}

///|
test "anomalies v4 06 missing register source is not G1a" {
  let report = inspect_anomalies_v4(
    register_history_v4(hist([tx("A", [read_op("x", "missing")])])).unwrap(),
  )
  assert_true(anomaly_test_has(report, "missing-source"))
  assert_eq(capture_field(report, "findings"), Json(([] : Array[Json])))
  for
    gap in anomaly_v4_array(v4_test_at(report, ["coverage", "diagnosticGaps"])) {
    assert_eq(
      capture_field(gap, "impliedAnomalies"),
      Json(([] : Array[String])),
    )
  }
  assert_eq(capture_field(report, "status"), Json("inconclusive"))
}

///|
test "anomalies v4 07 unknown writer differs from absent source" {
  let report = inspect_anomalies_v4(
    register_history_v4(
      hist([
        tx("W", [write_op("x", "x1")], status=Unknown),
        tx("R", [read_op("x", "x1")]),
      ]),
    ).unwrap(),
  )
  assert_true(anomaly_test_has(report, "unknown-writer"))
  assert_true(anomaly_test_has(report, "unknown-transaction-outcome"))
  assert_false(anomaly_test_has(report, "missing-source"))
  assert_eq(v4_test_at(report, ["coverage", "complete"]), Json(false))
}

///|
test "anomalies v4 08 register version identities are scoped by key" {
  let input : History = {
    model: Serializable,
    initial: { "x": "zero", "y": "zero" },
    version_orders: Map([]),
    transactions: [
      tx("A", [write_op("x", "one")]),
      tx("B", [write_op("y", "one")]),
      tx("C", [read_op("x", "one"), read_op("y", "one")]),
    ],
  }
  let report = inspect_anomalies_v4(register_history_v4(input).unwrap())
  assert_false(anomaly_test_has(report, "identity-conflict"))
  assert_false(anomaly_test_has(report, "missing-source"))
  assert_false(anomaly_test_has(report, "future-read"))
}

///|
test "anomalies v4 09 aborted reader does not establish a future-read anomaly" {
  let h = register_history_v4(
    hist([tx("A", [read_op("x", "x1"), write_op("x", "x1")], status=Aborted)]),
  ).unwrap()
  assert_false(anomaly_test_has(inspect_anomalies_v4(h), "future-read"))
}

///|
test "anomalies v4 10 list own future append uses transaction program order" {
  let source = v4_test_model_complete(AppendListV4, [
    {
      "kind": "list_read",
      "tx": "A",
      "key": "x",
      "items": [{ "id": "later", "value": "same" }],
    },
    { "kind": "append", "tx": "A", "key": "x", "id": "later", "value": "same" },
  ])
  let report = anomaly_test_report(source)
  assert_true(anomaly_test_has(report, "future-read"))
  assert_eq(
    v4_test_at(
      capture_field(anomaly_test_finding(report, "future-read"), "evidence"),
      ["read", "operationIndex"],
    ),
    Json(0),
  )
}

///|
test "anomalies v4 11 list cross-client logging order stays a gap" {
  let source = anomaly_test_list([
    { "kind": "begin", "tx": "A", "connection": "a" },
    {
      "kind": "list_read",
      "tx": "A",
      "key": "x",
      "items": [{ "id": "later", "value": "same" }],
    },
    { "kind": "begin", "tx": "B", "connection": "b" },
    { "kind": "append", "tx": "B", "key": "x", "id": "later", "value": "same" },
    { "kind": "commit_request", "tx": "A" },
    { "kind": "commit_ok", "tx": "A" },
    { "kind": "commit_request", "tx": "B" },
    { "kind": "commit_ok", "tx": "B" },
  ])
  let report = anomaly_test_report(source)
  assert_false(anomaly_test_has(report, "future-read"))
  assert_true(anomaly_test_has(report, "source-observation-order"))
}

///|
test "anomalies v4 12 list missing identity is coverage only" {
  let report = anomaly_test_report(
    v4_test_model_complete(AppendListV4, [
      {
        "kind": "list_read",
        "tx": "A",
        "key": "x",
        "items": [{ "id": "unknown", "value": "same" }],
      },
    ]),
  )
  assert_true(anomaly_test_has(report, "missing-source"))
  assert_eq(capture_field(report, "findings"), Json(([] : Array[Json])))
}

///|
test "anomalies v4 13 same list identity with different business value is conflict" {
  let report = anomaly_test_report(
    v4_test_model_complete(AppendListV4, [
      {
        "kind": "append",
        "tx": "A",
        "key": "x",
        "id": "a",
        "value": "original",
      },
      {
        "kind": "list_read",
        "tx": "A",
        "key": "x",
        "items": [{ "id": "a", "value": "changed" }],
      },
    ]),
  )
  assert_true(anomaly_test_has(report, "identity-conflict"))
  assert_false(anomaly_test_has(report, "missing-source"))
  assert_eq(
    capture_field(
      anomaly_test_finding(report, "identity-conflict"),
      "impliedAnomalies",
    ),
    Json(([] : Array[String])),
  )
}

///|
test "anomalies v4 14 list identity returned from a different key is conflict" {
  let source = v4_test_model_complete(AppendListV4, [
    {
      "kind": "list_read",
      "tx": "A",
      "key": "x",
      "items": [{ "id": "other", "value": "same" }],
    },
  ])
  let events = anomaly_v4_array(capture_field(source, "events"))
  object_fields_unchecked_v3(events[0])["initial"] = {
    "x": [],
    "y": [{ "id": "other", "value": "same" }],
  }
  let report = anomaly_test_report(source)
  assert_true(anomaly_test_has(report, "identity-conflict"))
  assert_false(anomaly_test_has(report, "missing-source"))
}

///|
test "anomalies v4 15 duplicate returned identity is distinct from duplicate business values" {
  let source = v4_test_model_complete(AppendListV4, [
    { "kind": "append", "tx": "A", "key": "x", "id": "a", "value": "same" },
    {
      "kind": "list_read",
      "tx": "A",
      "key": "x",
      "items": [{ "id": "a", "value": "same" }, { "id": "a", "value": "same" }],
    },
  ])
  assert_true(
    anomaly_test_has(anomaly_test_report(source), "identity-conflict"),
  )
  assert_false(
    anomaly_test_has(
      anomaly_test_report(anomaly_test_list_order(reverse=false)),
      "identity-conflict",
    ),
  )
}

///|
test "anomalies v4 16 two complete list observations provide a version-order cycle" {
  let source = anomaly_test_list_order()
  let report = anomaly_test_report(source)
  let proof = capture_field(
    anomaly_test_finding(report, "version-order-conflict"),
    "evidence",
  )
  let edges = anomaly_v4_array(capture_field(proof, "constraints"))
  assert_eq(edges.length(), 2)
  assert_eq(capture_field(edges[0], "before"), capture_field(edges[1], "after"))
  assert_eq(capture_field(edges[0], "after"), capture_field(edges[1], "before"))
  assert_eq(
    capture_field(
      anomaly_test_finding(report, "version-order-conflict"),
      "impliedAnomalies",
    ),
    Json(([] : Array[String])),
  )
  assert_eq(v4_test_at(report, ["observations", "document"]), source)
}

///|
test "anomalies v4 17 compatible list order does not produce a conflict" {
  assert_false(
    anomaly_test_has(
      anomaly_test_report(anomaly_test_list_order(reverse=false)),
      "version-order-conflict",
    ),
  )
}

///|
test "anomalies v4 18 invalid captured predecessor cycle is rejected before typed inspection" {
  let source = v3_test_trace([
    { "kind": "begin", "tx": "A", "connection": "a" },
    {
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "x1",
      "predecessor": "x2",
    },
    { "kind": "commit_request", "tx": "A" },
    { "kind": "commit_ok", "tx": "A" },
    { "kind": "begin", "tx": "B", "connection": "b" },
    {
      "kind": "write",
      "tx": "B",
      "key": "x",
      "version": "x2",
      "predecessor": "x1",
    },
    { "kind": "commit_request", "tx": "B" },
    { "kind": "commit_ok", "tx": "B" },
  ])
  assert_true(parse_history_v4(source.stringify()) is Err(_))
}

///|
test "anomalies v4 19 a valid declared chain stays acyclic" {
  let h = register_history_v4(
    hist([tx("A", [write_op("x", "x1")]), tx("B", [write_op("x", "x2")])], orders={
      "x": ["x0", "x1", "x2"],
    }),
  ).unwrap()
  assert_false(
    anomaly_test_has(inspect_anomalies_v4(h), "version-order-conflict"),
  )
}

///|
test "anomalies v4 20 invalid list identity values cannot provide order constraints" {
  let source = anomaly_test_list_order()
  let events = anomaly_v4_array(capture_field(source, "events"))
  for event in events {
    let fields = object_fields_unchecked_v3(event)
    if fields.get("kind") == Some(Json("list_read")) &&
      fields.get("tx") == Some(Json("D")) {
      fields["items"] = [
        { "id": "b", "value": "wrong" },
        { "id": "a", "value": "same" },
      ]
    }
  }
  let report = anomaly_test_report(source)
  assert_true(anomaly_test_has(report, "identity-conflict"))
  assert_false(anomaly_test_has(report, "version-order-conflict"))
}

///|
test "anomalies v4 21 reverted append retains its read but is not a committed order source" {
  let source = v4_test_model_complete(AppendListV4, [
    { "kind": "savepoint", "tx": "A", "name": "s", "instance": "s1" },
    { "kind": "append", "tx": "A", "key": "x", "id": "a", "value": "same" },
    {
      "kind": "list_read",
      "tx": "A",
      "key": "x",
      "items": [{ "id": "a", "value": "same" }],
    },
    { "kind": "rollback_to", "tx": "A", "instance": "s1" },
  ])
  let report = anomaly_test_report(source)
  assert_true(anomaly_test_has(report, "source-effect-not-committed"))
  assert_false(anomaly_test_has(report, "future-read"))
  assert_eq(v4_test_at(report, ["observations", "document"]), source)
}

///|
test "anomalies v4 22 zero and oversized work budgets never report checked" {
  let h = register_history_v4(skew()).unwrap()
  let empty = inspect_anomalies_v4(h, max_checks=0)
  assert_eq(capture_field(empty, "status"), Json("inconclusive"))
  assert_eq(v4_test_at(empty, ["execution", "checks"]), Json(0))
  assert_eq(v4_test_at(empty, ["coverage", "budgetExhausted"]), Json(true))
  for max_checks in [-1, 1000001] {
    assert_eq(
      capture_field(inspect_anomalies_v4(h, max_checks~), "status"),
      Json("invalid"),
    )
  }
}

///|
test "anomalies v4 23 exact work boundary completes and preceding boundary does not" {
  let h = register_history_v4(hist([tx("A", [read_op("x", "x0")])])).unwrap()
  let full = inspect_anomalies_v4(h)
  let count = match v4_test_at(full, ["execution", "checks"]) {
    Number(n, ..) => n.to_int()
    _ => 0
  }
  assert_eq(
    capture_field(inspect_anomalies_v4(h, max_checks=count), "status"),
    Json("checked"),
  )
  assert_eq(
    v4_test_at(inspect_anomalies_v4(h, max_checks=count - 1), [
      "coverage", "complete",
    ]),
    Json(false),
  )
}

///|
test "anomalies v4 24 verification binds all report sections and caller budget" {
  let h = parse_history_v4(anomaly_test_list_order().stringify()).unwrap()
  let report = inspect_anomalies_v4(h)
  for
    path in [
      ["algorithm"],
      ["semanticContract"],
      ["status"],
      ["execution", "counterContract"],
      ["execution", "maxChecks"],
      ["coverage", "complete"],
      ["observations", "document", "dataModel"],
    ] {
    let altered = v4_json_copy(report)
    v4_test_replace(altered, path, Json("forged"))
    assert_false(verify_anomalies_v4(h, altered))
  }
  let limited = inspect_anomalies_v4(h, max_checks=0)
  assert_true(verify_anomalies_v4(h, limited, max_checks=0))
  assert_false(verify_anomalies_v4(h, limited))
}

///|
test "anomalies v4 25 returned artifact cannot mutate a retained history" {
  let h = register_history_v4(skew()).unwrap()
  let report = inspect_anomalies_v4(h)
  let before = inspect_anomalies_v4(h)
  v4_test_replace(
    report,
    ["observations", "document", "initial", "x"],
    Json("changed"),
  )
  assert_eq(inspect_anomalies_v4(h), before)
}

///|
test "anomalies v4 26 report finding cap remains visible" {
  let h = register_history_v4(
    hist([
      tx("A", Array::makei(300, i => read_op("x", "missing-" + i.to_string()))),
    ]),
  ).unwrap()
  let report = inspect_anomalies_v4(h)
  assert_eq(v4_test_at(report, ["coverage", "findingsTruncated"]), Json(true))
  assert_eq(
    anomaly_v4_array(v4_test_at(report, ["coverage", "diagnosticGaps"])).length(),
    256,
  )
  assert_eq(v4_test_at(report, ["coverage", "complete"]), Json(false))
}

///|
test "anomalies v4 27 relation inspection is explicitly unsupported" {
  let source = v4_test_model_complete(RelationSetV4, [
    {
      "kind": "row_read",
      "tx": "A",
      "relation": "r",
      "predicate": [],
      "rows": [],
      "complete": true,
    },
  ])
  assert_eq(
    capture_field(anomaly_test_report(source), "status"),
    Json("unsupported"),
  )
}

///|
test "anomalies v4 28 constructor-rejected duplicate append identities stay outside typed diagnostic" {
  let source = v4_test_model_complete(AppendListV4, [
    { "kind": "append", "tx": "A", "key": "x", "id": "a", "value": "one" },
    { "kind": "append", "tx": "A", "key": "x", "id": "a", "value": "two" },
  ])
  assert_true(parse_history_v4(source.stringify()) is Err(_))
}

///|
test "anomalies v4 29 captured initial list order supplies an independent contradiction" {
  let source = v4_test_model_complete(AppendListV4, [
    {
      "kind": "list_read",
      "tx": "A",
      "key": "x",
      "items": [{ "id": "b", "value": "same" }, { "id": "a", "value": "same" }],
    },
  ])
  object_fields_unchecked_v3(
    anomaly_v4_array(capture_field(source, "events"))[0],
  )["initial"] = {
    "x": [{ "id": "a", "value": "same" }, { "id": "b", "value": "same" }],
  }
  assert_true(
    anomaly_test_has(anomaly_test_report(source), "version-order-conflict"),
  )
}

///|
test "anomalies v4 30 same-transaction append program order is an independent fact" {
  let source = v4_test_model_complete(AppendListV4, [
    { "kind": "append", "tx": "A", "key": "x", "id": "a", "value": "same" },
    { "kind": "append", "tx": "A", "key": "x", "id": "b", "value": "same" },
    {
      "kind": "list_read",
      "tx": "A",
      "key": "x",
      "items": [{ "id": "b", "value": "same" }, { "id": "a", "value": "same" }],
    },
  ])
  let report = anomaly_test_report(source)
  assert_true(anomaly_test_has(report, "version-order-conflict"))
  assert_false(anomaly_test_has(report, "future-read"))
}

///|
test "anomalies v4 31 valid internal intermediate list read does not conflict with later append" {
  let source = v4_test_model_complete(AppendListV4, [
    { "kind": "append", "tx": "A", "key": "x", "id": "a", "value": "same" },
    {
      "kind": "list_read",
      "tx": "A",
      "key": "x",
      "items": [{ "id": "a", "value": "same" }],
    },
    { "kind": "append", "tx": "A", "key": "x", "id": "b", "value": "same" },
    {
      "kind": "list_read",
      "tx": "A",
      "key": "x",
      "items": [{ "id": "a", "value": "same" }, { "id": "b", "value": "same" }],
    },
  ])
  let report = anomaly_test_report(source)
  assert_false(anomaly_test_has(report, "version-order-conflict"))
  assert_false(anomaly_test_has(report, "future-read"))
}

///|
test "anomalies v4 32 reverted append cannot impose a committed program-order constraint" {
  let source = v4_test_model_complete(AppendListV4, [
    { "kind": "append", "tx": "A", "key": "x", "id": "a", "value": "same" },
    { "kind": "savepoint", "tx": "A", "name": "s", "instance": "s" },
    { "kind": "append", "tx": "A", "key": "x", "id": "b", "value": "same" },
    { "kind": "rollback_to", "tx": "A", "instance": "s" },
    { "kind": "append", "tx": "A", "key": "x", "id": "c", "value": "same" },
    {
      "kind": "list_read",
      "tx": "A",
      "key": "x",
      "items": [{ "id": "a", "value": "same" }, { "id": "c", "value": "same" }],
    },
  ])
  assert_false(
    anomaly_test_has(anomaly_test_report(source), "version-order-conflict"),
  )
}

///|
test "anomalies v4 33 register scoped identities cannot collide through separators" {
  for
    separator in [
      "|", ":", "/", "::", "->", "[]", "{}", "\\", "\"", " # ", " / ",
    ] {
    let left = "a" + separator + "b"
    let right_identity = "b" + separator + "c"
    let initial : Map[String, String] = Map([])
    initial[left] = "left-initial"
    initial["a"] = "right-initial"
    let history : History = {
      model: Serializable,
      initial,
      version_orders: Map([]),
      transactions: [
        tx("W" + separator + "known", [write_op(left, "c")]),
        tx(
          "W" + separator + "unknown",
          [write_op("a", right_identity)],
          status=Unknown,
        ),
        tx("R" + separator, [read_op(left, "c"), read_op("a", right_identity)]),
      ],
    }
    let report = inspect_anomalies_v4(register_history_v4(history).unwrap())
    assert_false(anomaly_test_has(report, "identity-conflict"))
    assert_false(anomaly_test_has(report, "missing-source"))
    let writers = anomaly_v4_array(
      v4_test_at(report, ["coverage", "diagnosticGaps"]),
    ).filter(gap => {
      object_fields_unchecked_v3(gap).get("kind") ==
      Some(Json("unknown-writer"))
    })
    assert_eq(writers.length(), 1)
    assert_eq(v4_test_at(writers[0], ["evidence", "key"]), Json("a"))
    assert_eq(
      v4_test_at(writers[0], ["evidence", "identity"]),
      Json(right_identity),
    )
  }
}

///|
test "anomalies v4 34 list tx-key append tails cannot collide through separators" {
  for separator in ["|", ":", "/", "::", "->", "[]", "\\", "\""] {
    let first_tx = "t" + separator + "a"
    let second_key = "a" + separator + "k"
    let source = anomaly_test_list([
      { "kind": "begin", "tx": Json(first_tx), "connection": "c1" },
      {
        "kind": "append",
        "tx": Json(first_tx),
        "key": "k",
        "id": "a",
        "value": "same",
      },
      { "kind": "commit_request", "tx": Json(first_tx) },
      { "kind": "commit_ok", "tx": Json(first_tx) },
      { "kind": "begin", "tx": "t", "connection": "c2" },
      {
        "kind": "append",
        "tx": "t",
        "key": Json(second_key),
        "id": "b",
        "value": "same",
      },
      { "kind": "commit_request", "tx": "t" },
      { "kind": "commit_ok", "tx": "t" },
    ])
    let initial : Map[String, Json] = Map([])
    initial["k"] = Json(([] : Array[Json]))
    initial[second_key] = Json(([] : Array[Json]))
    object_fields_unchecked_v3(
      anomaly_v4_array(capture_field(source, "events"))[0],
    )["initial"] = Json::object(initial)
    let report = anomaly_test_report(source)
    assert_eq(v4_test_at(report, ["execution", "orderConstraints"]), Json(0))
    assert_false(anomaly_test_has(report, "version-order-conflict"))
  }
}

///|
test "anomalies v4 35 list key-item identities cannot collide through separators" {
  for separator in ["|", ":", "/", "::", "->", "[]", "\\", "\""] {
    let first_key = "a" + separator + "b"
    let second_id = "b" + separator + "c"
    let source = v4_test_model_complete(AppendListV4, [
      {
        "kind": "list_read",
        "tx": "A",
        "key": Json(first_key),
        "items": [{ "id": "c", "value": "left" }],
      },
      {
        "kind": "list_read",
        "tx": "A",
        "key": "a",
        "items": [{ "id": Json(second_id), "value": "right" }],
      },
    ])
    let initial : Map[String, Json] = Map([])
    initial[first_key] = Json(([{ "id": "c", "value": "left" }] : Array[Json]))
    initial["a"] = Json(
      ([{ "id": Json(second_id), "value": "right" }] : Array[Json]),
    )
    object_fields_unchecked_v3(
      anomaly_v4_array(capture_field(source, "events"))[0],
    )["initial"] = Json::object(initial)
    let report = anomaly_test_report(source)
    assert_false(anomaly_test_has(report, "identity-conflict"))
    assert_false(anomaly_test_has(report, "missing-source"))
    assert_eq(capture_field(report, "status"), Json("checked"))
  }
}

///|
test "anomalies v4 36 reliable finding coexists with unrelated unknown writer" {
  let history = hist([
    tx("A", [read_op("x", "x1"), write_op("x", "x1"), read_op("y", "y1")]),
    tx("W", [write_op("y", "y1")], status=Unknown),
  ])
  let report = inspect_anomalies_v4(register_history_v4(history).unwrap())
  assert_true(anomaly_test_has(report, "future-read"))
  assert_true(anomaly_test_has(report, "unknown-writer"))
  assert_eq(capture_field(report, "status"), Json("findings"))
  assert_eq(v4_test_at(report, ["coverage", "complete"]), Json(false))
  assert_eq(
    v4_test_at(report, ["scope", "acceptsIsolationModels"]),
    Json(false),
  )
}

///|
test "anomalies v4 37 later exhausted work cannot erase an earlier proved finding" {
  let ops = [read_op("x", "x1"), write_op("x", "x1")]
  for index in 0..<100 {
    ops.push(read_op("y", "absent-" + index.to_string()))
  }
  let h = register_history_v4(hist([tx("A", ops)])).unwrap()
  let full = inspect_anomalies_v4(h)
  let count = match v4_test_at(full, ["execution", "checks"]) {
    Number(n, ..) => n.to_int()
    _ => 0
  }
  let limited = inspect_anomalies_v4(h, max_checks=count - 1)
  assert_eq(capture_field(limited, "status"), Json("findings"))
  assert_true(anomaly_test_has(limited, "future-read"))
  assert_eq(v4_test_at(limited, ["coverage", "budgetExhausted"]), Json(true))
  assert_eq(v4_test_at(limited, ["coverage", "complete"]), Json(false))
}

///|
test "anomalies v4 38 unknown-gap output saturation cannot suppress a proved finding" {
  let ops : Array[Operation] = []
  for index in 0..<256 {
    ops.push(read_op("y", "absent-" + index.to_string()))
  }
  ops.push(read_op("x", "x1"))
  ops.push(write_op("x", "x1"))
  let report = inspect_anomalies_v4(
    register_history_v4(hist([tx("A", ops)])).unwrap(),
  )
  assert_true(anomaly_test_has(report, "future-read"))
  assert_eq(capture_field(report, "status"), Json("findings"))
  assert_eq(v4_test_at(report, ["coverage", "findingsTruncated"]), Json(true))
  assert_eq(
    anomaly_v4_array(v4_test_at(report, ["coverage", "diagnosticGaps"])).length() +
    anomaly_test_entries(report, "findings").length(),
    256,
  )
}

///|
test "anomalies v4 39 unsupported model stays unsupported under zero work" {
  let h = parse_history_v4(
    v4_test_model_complete(RelationSetV4, []).stringify(),
  ).unwrap()
  let report = inspect_anomalies_v4(h, max_checks=0)
  assert_eq(capture_field(report, "status"), Json("unsupported"))
  assert_eq(v4_test_at(report, ["coverage", "complete"]), Json(false))
  assert_eq(
    v4_test_at(report, ["scope", "acceptsIsolationModels"]),
    Json(false),
  )
}

///|
test "anomalies v4 40 completed diagnostics with a finding do not accept any model" {
  let h = register_history_v4(
    hist([tx("A", [read_op("x", "x1"), write_op("x", "x1")])]),
  ).unwrap()
  let full = inspect_anomalies_v4(h)
  let count = match v4_test_at(full, ["execution", "checks"]) {
    Number(n, ..) => n.to_int()
    _ => 0
  }
  let exact = inspect_anomalies_v4(h, max_checks=count)
  assert_eq(capture_field(exact, "status"), Json("findings"))
  assert_eq(v4_test_at(exact, ["coverage", "complete"]), Json(true))
  assert_eq(v4_test_at(exact, ["scope", "acceptsIsolationModels"]), Json(false))
  assert_true(verify_anomalies_v4(h, exact, max_checks=count))
  v4_test_replace(exact, ["scope", "acceptsIsolationModels"], Json(true))
  assert_false(verify_anomalies_v4(h, exact, max_checks=count))
}
