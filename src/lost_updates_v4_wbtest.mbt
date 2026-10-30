///|
fn lost_update_test_report(history : History) -> Json {
  inspect_lost_updates_v4(register_history_v4(history).unwrap())
}

///|
fn lost_update_test_pattern() -> History {
  hist([
    tx("A", [read_op("x", "x0"), write_op("x", "a1")]),
    tx("B", [read_op("x", "x0"), write_op("x", "b1")]),
  ])
}

///|
fn lost_update_test_capture(
  a : Array[Json],
  final_a~ : String = "a1",
  branch~ : Bool = false,
) -> Json {
  let body : Array[Json] = [
    { "kind": "begin", "tx": "A", "connection": "a" },
    { "kind": "begin", "tx": "B", "connection": "b" },
    { "kind": "read", "tx": "B", "key": "x", "version": "x0" },
  ]
  for event in a {
    body.push(event)
  }
  body.push({ "kind": "commit_request", "tx": "A" })
  body.push({ "kind": "commit_ok", "tx": "A" })
  body.push({
    "kind": "write",
    "tx": "B",
    "key": "x",
    "version": "b1",
    "predecessor": Json(if branch { "x0" } else { final_a }),
  })
  body.push({ "kind": "commit_request", "tx": "B" })
  body.push({ "kind": "commit_ok", "tx": "B" })
  v3_test_trace(body)
}

///|
fn lost_update_test_capture_report(source : Json) -> Json raise {
  match parse_history_v4(source.stringify()) {
    Ok(history) => inspect_lost_updates_v4(history)
    Err(reason) => fail(reason)
  }
}

///|
test "lost updates v4 01 actual same-version reads and distinct final writes prove a pair" {
  let h = register_history_v4(lost_update_test_pattern()).unwrap()
  let report = inspect_lost_updates_v4(h)
  assert_true(anomaly_test_has(report, "lost-update"))
  let proof = capture_field(
    anomaly_test_finding(report, "lost-update"),
    "evidence",
  )
  assert_eq(capture_field(proof, "readVersionIdentity"), Json("x0"))
  assert_eq(capture_field(proof, "versionOrderRequired"), Json(false))
  assert_eq(anomaly_v4_array(capture_field(proof, "transactions")).length(), 2)
  assert_eq(
    capture_field(
      anomaly_test_finding(report, "lost-update"),
      "impliedAnomalies",
    ),
    Json(["lost-update", "write-skew", "G2-item", "G2"]),
  )
  assert_true(verify_lost_updates_v4(h, report))
}

///|
test "lost updates v4 02 source-only default and its counters remain unchanged" {
  let h = register_history_v4(lost_update_test_pattern()).unwrap()
  let ordinary = inspect_anomalies_v4(h)
  assert_false(anomaly_test_has(ordinary, "lost-update"))
  assert_eq(
    capture_field(ordinary, "algorithm"),
    Json("v4-source-index-and-order-witness-1"),
  )
  let extended = inspect_lost_updates_v4(h)
  assert_eq(
    capture_field(extended, "algorithm"),
    Json("v4-register-source-lost-update-1"),
  )
  assert_eq(
    v4_test_at(extended, ["execution", "counterContract"]),
    Json("v4-register-source-lost-update-checks-1"),
  )
  assert_false(verify_anomalies_v4(h, extended))
}

///|
test "lost updates v4 03 a noninitial confirmed final writer provides source evidence" {
  let h = hist([
    tx("P", [write_op("x", "p1")]),
    tx("A", [read_op("x", "p1"), write_op("x", "a1")]),
    tx("B", [read_op("x", "p1"), write_op("x", "b1")]),
  ])
  let proof = capture_field(
    anomaly_test_finding(lost_update_test_report(h), "lost-update"),
    "evidence",
  )
  assert_eq(v4_test_at(proof, ["readSource", "transaction"]), Json("P"))
  assert_eq(v4_test_at(proof, ["readSource", "identity"]), Json("p1"))
}

///|
test "lost updates v4 04 equal displayed value labels with different identities are not grouped" {
  let h : History = {
    model: Serializable,
    initial: { "x": "amount-7#v0" },
    version_orders: Map([]),
    transactions: [
      tx("P", [write_op("x", "amount-7#v1")]),
      tx("A", [read_op("x", "amount-7#v0"), write_op("x", "a1")]),
      tx("B", [read_op("x", "amount-7#v1"), write_op("x", "b1")]),
    ],
  }
  assert_false(anomaly_test_has(lost_update_test_report(h), "lost-update"))
}

///|
test "lost updates v4 05 final effective write is chosen from a multi-operation transaction" {
  let h = hist([
    tx("A", [
      read_op("x", "x0"),
      write_op("x", "intermediate"),
      read_op("x", "intermediate"),
      write_op("y", "y1"),
      write_op("x", "final"),
    ]),
    tx("B", [read_op("x", "x0"), write_op("x", "b1")]),
  ])
  let proof = capture_field(
    anomaly_test_finding(lost_update_test_report(h), "lost-update"),
    "evidence",
  )
  let participants = anomaly_v4_array(capture_field(proof, "transactions"))
  assert_eq(
    v4_test_at(participants[0], ["finalEffectiveWrite", "identity"]),
    Json("final"),
  )
  assert_eq(
    v4_test_at(participants[0], ["finalEffectiveWrite", "operationIndex"]),
    Json(4),
  )
}

///|
test "lost updates v4 06 reading after a current own write is not an external-read candidate" {
  let h = hist([
    tx("A", [write_op("x", "a1"), read_op("x", "x0")]),
    tx("B", [read_op("x", "x0"), write_op("x", "b1")]),
  ])
  assert_false(anomaly_test_has(lost_update_test_report(h), "lost-update"))
}

///|
test "lost updates v4 07 the first external read is not replaced by a later matching read" {
  let h = hist([
    tx("P", [write_op("x", "p1")]),
    tx("A", [read_op("x", "x0"), read_op("x", "p1"), write_op("x", "a1")]),
    tx("B", [read_op("x", "p1"), write_op("x", "b1")]),
  ])
  assert_false(anomaly_test_has(lost_update_test_report(h), "lost-update"))
}

///|
test "lost updates v4 08 version adjacency and blind writes cannot synthesize reads" {
  let h = hist(
    [tx("A", [write_op("x", "a1")]), tx("B", [write_op("x", "b1")])],
    orders={ "x": ["x0", "a1", "b1"] },
  )
  let report = lost_update_test_report(h)
  assert_false(anomaly_test_has(report, "lost-update"))
  assert_false(anomaly_test_has(report, "dirty-update"))
  assert_eq(v4_test_at(report, ["scope", "dirtyUpdateSupported"]), Json(false))
}

///|
test "lost updates v4 09 unknown source writer yields a gap rather than a pair" {
  let h = hist([
    tx("P", [write_op("x", "p1")], status=Unknown),
    tx("A", [read_op("x", "p1"), write_op("x", "a1")]),
    tx("B", [read_op("x", "p1"), write_op("x", "b1")]),
  ])
  let report = lost_update_test_report(h)
  assert_false(anomaly_test_has(report, "lost-update"))
  assert_true(anomaly_test_has(report, "lost-update-read-source-unconfirmed"))
  assert_true(anomaly_test_has(report, "unknown-writer"))
  assert_eq(v4_test_at(report, ["coverage", "complete"]), Json(false))
}

///|
test "lost updates v4 10 missing source version is retained as a gap" {
  let h = hist([
    tx("A", [read_op("x", "unobserved"), write_op("x", "a1")]),
    tx("B", [read_op("x", "unobserved"), write_op("x", "b1")]),
  ])
  let report = lost_update_test_report(h)
  assert_false(anomaly_test_has(report, "lost-update"))
  assert_true(anomaly_test_has(report, "missing-source"))
  assert_true(anomaly_test_has(report, "lost-update-read-source-unconfirmed"))
}

///|
test "lost updates v4 11 an intermediate external version is not a final source proof" {
  let h = hist([
    tx("P", [write_op("x", "p1"), write_op("x", "p2")]),
    tx("A", [read_op("x", "p1"), write_op("x", "a1")]),
    tx("B", [read_op("x", "p1"), write_op("x", "b1")]),
  ])
  let report = lost_update_test_report(h)
  assert_false(anomaly_test_has(report, "lost-update"))
  assert_true(anomaly_test_has(report, "lost-update-read-source-unconfirmed"))
}

///|
test "lost updates v4 12 aborted or unknown candidate outcome cannot establish lost update" {
  for status in [Aborted, Unknown] {
    let h = hist([
      tx("A", [read_op("x", "x0"), write_op("x", "a1")], status~),
      tx("B", [read_op("x", "x0"), write_op("x", "b1")]),
    ])
    assert_false(anomaly_test_has(lost_update_test_report(h), "lost-update"))
  }
}

///|
test "lost updates v4 13 captured actual reads prove the pair without a total WW chain" {
  let source = lost_update_test_capture(
    [
      { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "a1",
        "predecessor": "x0",
      },
    ],
    branch=true,
  )
  let report = lost_update_test_capture_report(source)
  assert_true(anomaly_test_has(report, "lost-update"))
  assert_eq(
    v4_test_at(report, ["coverage", "inputCoverage", "complete"]),
    Json(false),
  )
  assert_eq(v4_test_at(report, ["observations", "document"]), source)
}

///|
test "lost updates v4 14 savepoint rollback chooses the surviving final write" {
  let source = lost_update_test_capture([
    { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
    { "kind": "savepoint", "tx": "A", "name": "s", "instance": "s" },
    {
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "temporary",
      "predecessor": "x0",
    },
    { "kind": "rollback_to", "tx": "A", "instance": "s" },
    {
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "a1",
      "predecessor": "x0",
    },
  ])
  let report = lost_update_test_capture_report(source)
  let participants = anomaly_v4_array(
    v4_test_at(anomaly_test_finding(report, "lost-update"), [
      "evidence", "transactions",
    ]),
  )
  assert_true(
    participants.any(candidate => {
      v4_test_at(candidate, ["finalEffectiveWrite", "identity"]) == Json("a1")
    }),
  )
  assert_false(
    participants.any(candidate => {
      v4_test_at(candidate, ["finalEffectiveWrite", "identity"]) ==
      Json("temporary")
    }),
  )
}

///|
test "lost updates v4 15 rollback before an external read restores its eligibility" {
  let source = lost_update_test_capture([
    { "kind": "savepoint", "tx": "A", "name": "s", "instance": "s" },
    {
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "temporary",
      "predecessor": "x0",
    },
    { "kind": "rollback_to", "tx": "A", "instance": "s" },
    { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
    {
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "a1",
      "predecessor": "x0",
    },
  ])
  assert_true(
    anomaly_test_has(lost_update_test_capture_report(source), "lost-update"),
  )
}

///|
test "lost updates v4 16 a read before rollback still has its active own overlay" {
  let source = lost_update_test_capture([
    { "kind": "savepoint", "tx": "A", "name": "s", "instance": "s" },
    {
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "temporary",
      "predecessor": "x0",
    },
    { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
    { "kind": "rollback_to", "tx": "A", "instance": "s" },
    {
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "a1",
      "predecessor": "x0",
    },
  ])
  assert_false(
    anomaly_test_has(lost_update_test_capture_report(source), "lost-update"),
  )
}

///|
test "lost updates v4 17 entirely reverted writes cannot make a candidate" {
  let source = lost_update_test_capture(
    [
      { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
      { "kind": "savepoint", "tx": "A", "name": "s", "instance": "s" },
      {
        "kind": "write",
        "tx": "A",
        "key": "x",
        "version": "temporary",
        "predecessor": "x0",
      },
      { "kind": "rollback_to", "tx": "A", "instance": "s" },
    ],
    final_a="x0",
  )
  assert_false(
    anomaly_test_has(lost_update_test_capture_report(source), "lost-update"),
  )
}

///|
test "lost updates v4 18 unproven capture window blocks provenance-dependent pairing" {
  let source = lost_update_test_capture([
    { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
    {
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "a1",
      "predecessor": "x0",
    },
  ])
  object_fields_unchecked_v3(source)["scope"] = { "exclusiveWriters": false }
  let report = lost_update_test_capture_report(source)
  assert_false(anomaly_test_has(report, "lost-update"))
  assert_true(anomaly_test_has(report, "lost-update-source-window-unproven"))
}

///|
test "lost updates v4 19 unrelated unknown outcomes cannot erase a reliable pair" {
  let h = lost_update_test_pattern()
  h.transactions.push(tx("unknown", [write_op("y", "y1")], status=Unknown))
  let report = lost_update_test_report(h)
  assert_true(anomaly_test_has(report, "lost-update"))
  assert_true(anomaly_test_has(report, "unknown-transaction-outcome"))
  assert_eq(capture_field(report, "status"), Json("findings"))
  assert_eq(v4_test_at(report, ["coverage", "complete"]), Json(false))
}

///|
test "lost updates v4 20 list shared prefixes are not register lost-update sources" {
  let source = v4_test_model_complete(AppendListV4, [
    { "kind": "list_read", "tx": "A", "key": "x", "items": [] },
    { "kind": "append", "tx": "A", "key": "x", "id": "a", "value": "same" },
  ])
  let report = inspect_lost_updates_v4(
    parse_history_v4(source.stringify()).unwrap(),
  )
  assert_eq(capture_field(report, "status"), Json("unsupported"))
  assert_false(anomaly_test_has(report, "lost-update"))
}

///|
test "lost updates v4 21 caller budget zero exact and exhausted results remain explicit" {
  let h = register_history_v4(lost_update_test_pattern()).unwrap()
  let zero = inspect_lost_updates_v4(h, max_checks=0)
  assert_eq(capture_field(zero, "status"), Json("inconclusive"))
  assert_eq(v4_test_at(zero, ["execution", "checks"]), Json(0))
  let full = inspect_lost_updates_v4(h)
  let count = match v4_test_at(full, ["execution", "checks"]) {
    Number(n, ..) => n.to_int()
    _ => 0
  }
  let exact = inspect_lost_updates_v4(h, max_checks=count)
  assert_true(anomaly_test_has(exact, "lost-update"))
  assert_eq(v4_test_at(exact, ["coverage", "budgetExhausted"]), Json(false))
  assert_eq(
    v4_test_at(inspect_lost_updates_v4(h, max_checks=count - 1), [
      "coverage", "complete",
    ]),
    Json(false),
  )
  assert_true(verify_lost_updates_v4(h, zero, max_checks=0))
  assert_false(verify_lost_updates_v4(h, zero))
}

///|
test "lost updates v4 22 source conclusion identity and contract tampering are refused" {
  let h = register_history_v4(lost_update_test_pattern()).unwrap()
  let report = inspect_lost_updates_v4(h)
  for
    path in [
      ["algorithm"],
      ["profile"],
      ["status"],
      ["execution", "counterContract"],
      ["scope", "dirtyUpdateSupported"],
      ["observations", "document", "model"],
    ] {
    let copy = v4_json_copy(report)
    v4_test_replace(copy, path, Json("forged"))
    assert_false(verify_lost_updates_v4(h, copy))
  }
  let proof = anomaly_test_finding(report, "lost-update")
  object_fields_unchecked_v3(capture_field(proof, "evidence"))["readVersionIdentity"] = Json(
    "forged",
  )
  assert_false(verify_lost_updates_v4(h, report))
}

///|
test "lost updates v4 23 per-key source groups cannot collide through separators" {
  let left = "a|b"
  let initial : Map[String, String] = { "a|b": "c", "a": "b|c" }
  let h : History = {
    model: Serializable,
    initial,
    version_orders: Map([]),
    transactions: [
      tx("A", [read_op(left, "c"), write_op(left, "left-new")]),
      tx("B", [read_op("a", "b|c"), write_op("a", "right-new")]),
    ],
  }
  assert_false(anomaly_test_has(lost_update_test_report(h), "lost-update"))
}

///|
test "lost updates v4 24 three transactions expose pair witnesses without comparing business values" {
  let h = lost_update_test_pattern()
  h.transactions.push(tx("C", [read_op("x", "x0"), write_op("x", "c1")]))
  let report = lost_update_test_report(h)
  let cases = anomaly_test_entries(report, "findings").filter(f => {
    object_fields_unchecked_v3(f).get("kind") == Some(Json("lost-update"))
  })
  assert_eq(cases.length(), 2)
  assert_eq(
    v4_test_at(report, ["scope", "acceptsIsolationModels"]),
    Json(false),
  )
}

///|
test "lost updates v4 25 a proved pair survives a later exhausted work check" {
  let h = register_history_v4(lost_update_test_pattern()).unwrap()
  let full = inspect_lost_updates_v4(h)
  let count = match v4_test_at(full, ["execution", "checks"]) {
    Number(n, ..) => n.to_int()
    _ => 0
  }
  let limited = inspect_lost_updates_v4(h, max_checks=count - 1)
  assert_true(anomaly_test_has(limited, "lost-update"))
  assert_eq(capture_field(limited, "status"), Json("findings"))
  assert_eq(v4_test_at(limited, ["coverage", "budgetExhausted"]), Json(true))
}

///|
test "lost updates v4 26 gap output saturation cannot erase the proved pair" {
  let h = lost_update_test_pattern()
  h.transactions.push(
    tx(
      "noise",
      Array::makei(256, index => read_op("y", "absent-" + index.to_string())),
    ),
  )
  let report = lost_update_test_report(h)
  assert_true(anomaly_test_has(report, "lost-update"))
  assert_eq(capture_field(report, "status"), Json("findings"))
  assert_eq(v4_test_at(report, ["coverage", "findingsTruncated"]), Json(true))
  assert_eq(v4_test_at(report, ["coverage", "complete"]), Json(false))
}

///|
test "lost updates v4 27 captured predecessor facts without actual reads are not candidates" {
  let source = v3_test_trace([
    { "kind": "begin", "tx": "A", "connection": "a" },
    {
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "a1",
      "predecessor": "x0",
    },
    { "kind": "commit_request", "tx": "A" },
    { "kind": "commit_ok", "tx": "A" },
    { "kind": "begin", "tx": "B", "connection": "b" },
    {
      "kind": "write",
      "tx": "B",
      "key": "x",
      "version": "b1",
      "predecessor": "a1",
    },
    { "kind": "commit_request", "tx": "B" },
    { "kind": "commit_ok", "tx": "B" },
  ])
  let report = lost_update_test_capture_report(source)
  assert_false(anomaly_test_has(report, "lost-update"))
  assert_false(anomaly_test_has(report, "dirty-update"))
}

///|
test "lost updates v4 28 an aborted source version cannot prove a pair" {
  let h = hist([
    tx("P", [write_op("x", "p1")], status=Aborted),
    tx("A", [read_op("x", "p1"), write_op("x", "a1")]),
    tx("B", [read_op("x", "p1"), write_op("x", "b1")]),
  ])
  let report = lost_update_test_report(h)
  assert_false(anomaly_test_has(report, "lost-update"))
  assert_true(anomaly_test_has(report, "lost-update-read-source-unconfirmed"))
}

///|
test "lost updates v4 29 unconfirmed actual write base remains a gap" {
  let source = v3_test_trace([
    { "kind": "begin", "tx": "W", "connection": "w" },
    {
      "kind": "write",
      "tx": "W",
      "key": "x",
      "version": "w1",
      "predecessor": "x0",
    },
    { "kind": "disconnect", "tx": "W" },
    { "kind": "begin", "tx": "A", "connection": "a" },
    { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
    {
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "a1",
      "predecessor": "w1",
    },
    { "kind": "commit_request", "tx": "A" },
    { "kind": "commit_ok", "tx": "A" },
    { "kind": "begin", "tx": "B", "connection": "b" },
    { "kind": "read", "tx": "B", "key": "x", "version": "x0" },
    {
      "kind": "write",
      "tx": "B",
      "key": "x",
      "version": "b1",
      "predecessor": "x0",
    },
    { "kind": "commit_request", "tx": "B" },
    { "kind": "commit_ok", "tx": "B" },
  ])
  let report = lost_update_test_capture_report(source)
  assert_false(anomaly_test_has(report, "lost-update"))
  assert_true(anomaly_test_has(report, "lost-update-write-source-unconfirmed"))
}

///|
test "lost updates v4 30 incomplete capture records cannot establish unique-writer provenance" {
  let source = lost_update_test_capture([
    { "kind": "read", "tx": "A", "key": "x", "version": "x0" },
    {
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "a1",
      "predecessor": "x0",
    },
  ])
  object_fields_unchecked_v3(source)["gaps"] = [
    { "code": "lost-record", "message": "collector event unavailable" },
  ]
  let report = lost_update_test_capture_report(source)
  assert_false(anomaly_test_has(report, "lost-update"))
  assert_true(anomaly_test_has(report, "lost-update-source-window-unproven"))
}

///|
test "lost updates v4 31 captured noninitial final source is referenced by identity" {
  let source = v3_test_trace([
    { "kind": "begin", "tx": "P", "connection": "p" },
    {
      "kind": "write",
      "tx": "P",
      "key": "x",
      "version": "p1",
      "predecessor": "x0",
    },
    { "kind": "commit_request", "tx": "P" },
    { "kind": "commit_ok", "tx": "P" },
    { "kind": "begin", "tx": "A", "connection": "a" },
    { "kind": "read", "tx": "A", "key": "x", "version": "p1" },
    { "kind": "begin", "tx": "B", "connection": "b" },
    { "kind": "read", "tx": "B", "key": "x", "version": "p1" },
    {
      "kind": "write",
      "tx": "A",
      "key": "x",
      "version": "a1",
      "predecessor": "p1",
    },
    { "kind": "commit_request", "tx": "A" },
    { "kind": "commit_ok", "tx": "A" },
    {
      "kind": "write",
      "tx": "B",
      "key": "x",
      "version": "b1",
      "predecessor": "a1",
    },
    { "kind": "commit_request", "tx": "B" },
    { "kind": "commit_ok", "tx": "B" },
  ])
  let report = lost_update_test_capture_report(source)
  let proof = capture_field(
    anomaly_test_finding(report, "lost-update"),
    "evidence",
  )
  assert_eq(v4_test_at(proof, ["readSource", "transaction"]), Json("P"))
  assert_eq(v4_test_at(proof, ["readSource", "identity"]), Json("p1"))
}
