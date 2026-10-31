///|
fn ror_certificate(order : Array[String], prefixes : Array[Int32]) -> Json {
  let rows : Array[Json] = []
  for i, tx in order {
    let visible : Array[String] = []
    for j in 0..<prefixes[i] {
      visible.push(order[j])
    }
    rows.push({
      "transaction": Json(tx),
      "visiblePrefixLength": Json(prefixes[i]),
      "visibleTransactions": Json(visible),
    })
  }
  { "commitOrder": Json(order), "visibilityPrefixes": Json(rows) }
}

///|
fn ror_run(
  history : HistoryV4,
  certificate : Json,
  mode~ : RelationProgramReplayModeV4 = RelationSnapshotPrefixes,
  maximum~ : Int32 = 1000000,
) -> RelationProgramReplayV4 {
  replay_relation_program_v4(history, certificate, mode~, max_checks=maximum).unwrap()
}

///|
test "original rows 01 original point reads writes and values independently replay" {
  let h = rcl_history(rmp_one())
  let before = history_v4_json(h)
  let cert = ror_certificate(["A"], [0])
  let replay = ror_run(h, cert)
  assert_eq(replay.status(), "checked-compatible")
  assert_true(
    verify_relation_program_replay_v4(
      h,
      replay.record,
      cert,
      mode=RelationSnapshotPrefixes,
    ),
  )
  assert_eq(history_v4_json(h), before)
}

///|
test "original rows 02 snapshot and serial modes are independent caller choices" {
  let h = rcl_history(rmp_one())
  let cert = ror_certificate(["A"], [0])
  let snapshot = ror_run(h, cert)
  let serial = ror_run(h, cert, mode=RelationSerialOrder)
  assert_eq(snapshot.status(), "checked-compatible")
  assert_eq(serial.status(), "checked-compatible")
  assert_false(
    verify_relation_program_replay_v4(
      h,
      snapshot.record,
      cert,
      mode=RelationSerialOrder,
    ),
  )
}

///|
test "original rows 03 known actual row write skew has a valid SI certificate despite serial failures" {
  let h = rcl_history(rmp_skew())
  let snapshot = ror_run(h, ror_certificate(["A", "B"], [0, 0]))
  assert_eq(snapshot.status(), "checked-compatible")
  assert_eq(
    ror_run(h, ror_certificate(["A", "B"], [0, 1]), mode=RelationSerialOrder).status(),
    "unknown",
  )
  assert_eq(
    ror_run(h, ror_certificate(["B", "A"], [0, 1]), mode=RelationSerialOrder).status(),
    "unknown",
  )
  assert_eq(
    v4_test_at(snapshot.record, ["scope", "serialFailureIsRCOrSIRefutation"]),
    Json(false),
  )
}

///|
test "original rows 04 temporary hidden preconditions do not justify a serial certificate" {
  let h = rcl_history(rmp_unobserved_temporary_preconditions())
  assert_eq(
    ror_run(h, ror_certificate(["A", "B"], [0, 0])).status(),
    "checked-compatible",
  )
  assert_eq(
    ror_run(h, ror_certificate(["A", "B"], [0, 1]), mode=RelationSerialOrder).status(),
    "unknown",
  )
  assert_eq(
    ror_run(h, ror_certificate(["B", "A"], [0, 1]), mode=RelationSerialOrder).status(),
    "unknown",
  )
  assert_eq(
    mct_status(
      rmp_report(h, models=[ElleSerializable], clients=[]),
      ElleSerializable,
    ),
    "unknown",
  )
}

///|
test "original rows 05 source event gaps cannot be repaired by using normalized programs" {
  let raw = rpg_trace(rmp_one())
  let fields = object_fields_unchecked_v3(raw)
  let events = capture_source_array_v4(fields.at("events"))
  fields["events"] = Json(events.filter(e => v4_test_at(e, ["seq"]) != Json(3)))
  let h = parse_history_v4(raw.stringify()).unwrap()
  assert_eq(ror_run(h, ror_certificate(["A"], [0])).status(), "unknown")
}

///|
test "original rows 06 an actual empty query cannot be explained by inventing initial absence" {
  let body = [rpg_begin("A"), rpg_read("A", "1", None)]
  rpg_commit(body, "A")
  let h = rcl_history(body)
  assert_eq(ror_run(h, ror_certificate(["A"], [0])).status(), "unknown")
}

///|
test "original rows 07 literal initial absence and an actual insert replay without a ghost writer" {
  let body = [
    rpg_begin("A"),
    rpg_read("A", "1", None),
    rpg_write("A", "1", "v1", None, action="insert"),
    rpg_read("A", "1", Some("v1")),
  ]
  rpg_commit(body, "A")
  let h = rcl_history(body, empty=true)
  assert_eq(
    ror_run(h, ror_certificate(["A"], [0])).status(),
    "checked-compatible",
  )
}

///|
test "original rows 08 nested repeated savepoint names retain actual delivered reads" {
  let body = [
    rpg_begin("A"),
    rpg_read("A", "1", Some("v0")),
    ({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "outer" } : Json),
    rpg_write("A", "1", "v1", Some("v0")),
    ({ "kind": "savepoint", "tx": "A", "name": "s", "instance": "inner" } : Json),
    rpg_write("A", "1", "v2", Some("v1")),
    rpg_read("A", "1", Some("v2")),
    ({ "kind": "rollback_to", "tx": "A", "instance": "inner" } : Json),
    rpg_read("A", "1", Some("v1")),
    ({ "kind": "release", "tx": "A", "instance": "inner" } : Json),
    ({ "kind": "rollback_to", "tx": "A", "instance": "outer" } : Json),
    rpg_read("A", "1", Some("v0")),
  ]
  rpg_commit(body, "A")
  let h = rcl_history(body)
  assert_eq(
    ror_run(h, ror_certificate(["A"], [0])).status(),
    "checked-compatible",
  )
  assert_true(project_relation_rows_v4(h).unwrap().is_projected())
}

///|
test "original rows 09 changed row business value is checked independently of version identity" {
  let body = [rpg_begin("A"), rpg_read("A", "1", Some("v0"), value="different")]
  rpg_commit(body, "A")
  let h = rcl_history(body)
  assert_eq(ror_run(h, ror_certificate(["A"], [0])).status(), "unknown")
}

///|
test "original rows 10 model status and arbitrary graph proof JSON cannot authorize replay" {
  let h = rcl_history(rmp_one())
  let fake : Json = {
    "status": "checked-compatible",
    "models": [{ "model": "serializable", "status": "checked-compatible" }],
    "sourceComplete": true,
  }
  assert_eq(ror_run(h, fake).status(), "unknown")
}

///|
test "original rows 11 unknown and duplicate certificate transaction identities are refused" {
  let h = rcl_history(rmp_one())
  assert_eq(ror_run(h, ror_certificate(["missing"], [0])).status(), "unknown")
  assert_eq(ror_run(h, ror_certificate(["A", "A"], [0, 1])).status(), "unknown")
}

///|
test "original rows 12 complete transaction set and actual visible prefix are required" {
  let h = rcl_history(rmp_skew())
  let cert = ror_certificate(["A", "B"], [0, 0])
  let rows = capture_source_array_v4(v4_test_at(cert, ["visibilityPrefixes"]))
  object_fields_unchecked_v3(rows[1])["visibleTransactions"] = Json(["A"])
  assert_eq(ror_run(h, cert).status(), "unknown")
  assert_eq(ror_run(h, ror_certificate(["A"], [0])).status(), "unknown")
}

///|
test "original rows 13 source zero budget and exact budget are separately reproducible" {
  let h = rcl_history(rmp_one())
  let cert = ror_certificate(["A"], [0])
  let full = ror_run(h, cert)
  let count = capture_source_seq_v4(
    v4_test_at(full.record, ["execution", "checks"]),
  ).to_int()
  assert_true(count > 0)
  assert_eq(ror_run(h, cert, maximum=count).status(), "checked-compatible")
  let short = ror_run(h, cert, maximum=count - 1)
  assert_eq(short.status(), "unknown")
  assert_true(
    capture_source_seq_v4(v4_test_at(short.record, ["execution", "checks"])) <=
    (count - 1).to_int64(),
  )
  let zero = ror_run(h, cert, maximum=0)
  assert_eq(zero.status(), "unknown")
  assert_eq(v4_test_at(zero.record, ["execution", "checks"]), Json(0))
  assert_true(
    verify_relation_program_replay_v4(
      h,
      zero.record,
      cert,
      mode=RelationSnapshotPrefixes,
      max_checks=0,
    ),
  )
  assert_false(
    verify_relation_program_replay_v4(
      h,
      zero.record,
      cert,
      mode=RelationSnapshotPrefixes,
    ),
  )
}

///|
test "original rows 14 detached evidence does not retain a caller certificate alias" {
  let h = rcl_history(rmp_one())
  let cert = ror_certificate(["A"], [0])
  let replay = ror_run(h, cert)
  object_fields_unchecked_v3(cert)["commitOrder"] = Json(["changed"])
  assert_eq(
    v4_test_at(relation_program_replay_v4_json(replay), [
      "certificate", "commitOrder",
    ]),
    Json(["A"]),
  )
}

///|
test "original rows 15 distinct typed relation keys and equal business values remain distinct" {
  let raw = rpg_trace([])
  let fields = object_fields_unchecked_v3(raw)
  let schema = object_fields_unchecked_v3(fields.at("relationSchema"))
  schema["labels"] = {
    "primaryKey": "id",
    "columns": { "id": "text", "value": "text" },
  }
  let scope = object_fields_unchecked_v3(fields.at("scope"))
  scope["completeSnapshotTables"] = Json(["items", "labels"])
  let events = capture_source_array_v4(fields.at("events"))
  let initial = object_fields_unchecked_v3(v4_test_at(events[0], ["initial"]))
  initial["labels"] = Json([rpg_row("1", "text-initial")])
  let a = rpg_read("A", "1", Some("text-initial"))
  object_fields_unchecked_v3(a)["relation"] = Json("labels")
  let body = [rpg_begin("A"), rpg_read("A", "1", Some("v0")), a]
  rpg_commit(body, "A")
  for e in body {
    events.push(e)
  }
  for i, e in events {
    object_fields_unchecked_v3(e)["seq"] = Json(i + 1)
    object_fields_unchecked_v3(e)["time"] = Json(i)
  }
  let h = parse_history_v4(raw.stringify()).unwrap()
  let projected = project_relation_rows_v4(h).unwrap()
  assert_true(projected.is_projected())
  assert_eq(projected.program.unwrap().initial.length(), 4)
  assert_eq(
    ror_run(h, ror_certificate(["A"], [0])).status(),
    "checked-compatible",
  )
}

///|
test "original rows 16 invalid limits or a different source model cannot enter the row interpreter" {
  let h = rcl_history(rmp_one())
  assert_true(
    replay_relation_program_v4(
      h,
      ror_certificate(["A"], [0]),
      mode=RelationSnapshotPrefixes,
      max_checks=-1,
    )
    is Err(_),
  )
  assert_true(
    replay_relation_program_v4(
      mlp_history(mlp_multi()),
      ror_certificate(["A"], [0]),
      mode=RelationSnapshotPrefixes,
    )
    is Err(_),
  )
}

///|
fn ror_corpus(seed : Int32) -> (HistoryV4, Array[String]) {
  let versions : Map[String, String] = { "1": "v0", "2": "u0" }
  let body : Array[Json] = []
  let order : Array[String] = []
  for step in 0..<3 {
    let tx = "row-" + seed.to_string() + "-" + step.to_string()
    order.push(tx)
    let key = if (seed + step) % 2 == 0 { "1" } else { "2" }
    let previous = versions.at(key)
    body.append([
      rpg_begin(tx),
      rpg_read(tx, "1", Some(versions.at("1"))),
      rpg_read(tx, "2", Some(versions.at("2"))),
    ])
    if seed % 3 == 0 {
      let instance = tx + "-scope"
      let temp = tx + "-temp"
      body.append([
        (
          {
            "kind": "savepoint",
            "tx": Json(tx),
            "name": "same",
            "instance": Json(instance),
          } : Json),
        rpg_write(tx, key, temp, Some(previous)),
        rpg_read(tx, key, Some(temp)),
        (
          { "kind": "rollback_to", "tx": Json(tx), "instance": Json(instance) } :
          Json),
      ])
    }
    let terminal_version = tx + "-final"
    body.push(rpg_write(tx, key, terminal_version, Some(previous)))
    body.push(
      rpg_read(
        tx,
        key,
        Some(
          if seed % 4 == 0 && step == 0 {
            previous
          } else {
            terminal_version
          },
        ),
      ),
    )
    rpg_commit(body, tx)
    versions[key] = terminal_version
  }
  (rcl_history(body), order)
}

///|
test "original rows 17 one thousand distinct original programs have independent replay contrasts" {
  let seen : Map[String, Bool] = Map([])
  let mut accepted = 0
  let mut rejected = 0
  for seed in 0..<1000 {
    let (h, order) = ror_corpus(seed)
    assert_false(seen.contains(h.source_text))
    seen[h.source_text] = true
    let cert = ror_certificate(order, [0, 1, 2])
    let replay = ror_run(h, cert, mode=RelationSerialOrder)
    let clients = [
      (
        { id: "logical-original-program", transactions: order.copy(), } :
        ModelClientV4),
    ]
    let report = rmp_report(
      h,
      models=[ElleSerializable, ElleSnapshotIsolation],
      clients~,
    )
    if seed % 4 == 0 {
      rejected += 1
      assert_eq(replay.status(), "unknown", msg=seed.to_string())
      assert_eq(mct_status(report, ElleSerializable), "refuted")
      assert_eq(mct_status(report, ElleSnapshotIsolation), "refuted")
    } else {
      accepted += 1
      assert_eq(replay.status(), "checked-compatible", msg=seed.to_string())
      assert_eq(
        mct_status(report, ElleSerializable),
        "checked-compatible",
        msg=seed.to_string() + report.stringify(),
      )
      assert_eq(mct_status(report, ElleSnapshotIsolation), "checked-compatible")
      assert_eq(
        v4_test_at(
          mct_rule(report, ElleSnapshotIsolation, "completion/Ext/data-only"),
          ["evidence", "originalProgramReplay", "status"],
        ),
        Json("checked-compatible"),
      )
      assert_eq(
        v4_test_at(
          mct_rule(
            report,
            ElleSerializable,
            "completion/original-row-serial/data-only",
          ),
          ["evidence", "originalProgramReplay", "status"],
        ),
        Json("checked-compatible"),
      )
    }
  }
  assert_eq(accepted, 750)
  assert_eq(rejected, 250)
}
