///|
fn snapshot52_install(fixture : Json) -> SourceAdmissionV2 raise {
  let f = source_object_v4(fixture)
  let config = match parse_sql_config_v2(f.at("config").stringify()) {
    Ok(value) => value
    Err(reason) => fail(reason)
  }
  verify_source_admission_v2(
    config,
    f.at("policy"),
    sql_string_v1(f.at("installLog")),
    f.at("installed"),
  )
}

///|
fn snapshot52_run(
  fixture : Json,
  max_checks~ : Int32 = 1000000,
  max_rows~ : Int32 = 4096,
  max_effects~ : Int32 = 4096,
) -> Json raise {
  let f = source_object_v4(fixture)
  snapshot_admission_v2_json(
    verify_snapshot_admission_v2(
      snapshot52_install(fixture),
      sql_string_v1(f.at("endLog")),
      f.at("endReceipt"),
      max_checks~,
      max_rows~,
      max_effects~,
    ),
  )
}

///|
fn snapshot52_no_authority(report : Json) -> Unit raise {
  for
    name in [
      "sourceFactsProduced", "sourceAuthenticated", "completeWindow", "writerWindowVerified",
      "modelCoverageAccepted", "commitVerified",
    ] {
    assert_eq(v4_test_at(report, [name]), Json(false))
  }
}

///|
fn snapshot52_records(fixture : Json) -> Array[Json] raise {
  let records : Array[Json] = []
  for line in sql_string_v1(source_object_v4(fixture).at("endLog")).split("\n") {
    if !line.is_empty() {
      records.push(sql_json_v1(line.to_owned(), 524288))
    }
  }
  records
}

///|
fn snapshot52_reseal(fixture : Json, records : Array[Json]) -> Unit raise {
  let prefix = records[0:records.length() - 1]
    .to_owned()
    .map(sql_canonical_v1)
    .join("\n") +
    "\n"
  let seal = source_object_v4(records[records.length() - 1])
  seal["prefixSha256"] = Json(v3_dislock_sha256(prefix))
  let log = prefix + sql_canonical_v1(Json(seal)) + "\n"
  let f = source_object_v4(fixture)
  f["endLog"] = Json(log)
  let receipt = source_object_v4(f.at("endReceipt"))
  let summary = source_object_v4(receipt.at("log"))
  summary["bytes"] = Json(orm_utf8_size(log))
  summary["sha256"] = Json(v3_dislock_sha256(log))
}

///|
fn snapshot52_mutate_payload(
  fixture : Json,
  query : String,
  occurrence : Int32,
  change : (Json) -> Unit raise,
) -> Unit raise {
  let records = snapshot52_records(fixture)
  let mut count = 0
  let mut target = -1
  let mut request_seq : Json = Json::null()
  let mut changed = ""
  for index, raw in records {
    let event = source_object_v4(raw)
    if event.get("kind") == Some(Json("control-native")) &&
      event.get("queryId") == Some(Json(query)) {
      if count == occurrence {
        target = index
        request_seq = event.at("requestSeq")
        let rows = orm_array(source_object_v4(event.at("native")).at("rows"))
        let cells = orm_array(rows[0])
        let encoded = sql_string_v1(cells[0])
        let bytes = @base64.decode(encoded[:], ignore_whitespace=false)
        let payload = sql_json_v1(
          @utf8.decode(bytes[:], ignore_bom=false),
          131072,
        )
        change(payload)
        changed = sql_canonical_v1(payload)
        cells[0] = Json(@base64.encode(@utf8.encode(changed)[:]))
        break
      }
      count += 1
    }
  }
  if target < 0 {
    fail("fixture:query-occurrence")
  }
  for raw in records {
    let event = source_object_v4(raw)
    if event.get("kind") == Some(Json("control-delivery")) &&
      event.get("requestSeq") == Some(request_seq) {
      let rows = orm_array(source_object_v4(event.at("observation")).at("rows"))
      let cells = orm_array(source_object_v4(rows[0]).at("cells"))
      source_object_v4(cells[0])["value"] = Json(changed)
    }
  }
  snapshot52_reseal(fixture, records)
}

///|
test "snapshot52 real installation and complete snapshots support all three primary key kinds" {
  for index in 0..<3 {
    let report = snapshot52_run(snapshot52_fixture(index))
    assert_eq(
      v4_test_at(report, ["status"]),
      Json("matched"),
      msg=report.stringify(),
    )
    assert_eq(v4_test_at(report, ["snapshotVerified"]), Json(true))
    assert_eq(v4_test_at(report, ["rowsObserved"]), Json(3))
    assert_eq(v4_test_at(report, ["effectsObserved"]), Json(6))
    snapshot52_no_authority(report)
  }
}

///|
test "snapshot52 full rescans include low version committed after a higher version" {
  let fixture = snapshot52_fixture(0)
  let f = source_object_v4(fixture)
  let installation = snapshot52_install(fixture)
  let middle = verify_snapshot_admission_v2(
    installation,
    sql_string_v1(f.at("middleLog")),
    f.at("middleReceipt"),
  )
  assert_eq(
    v4_test_at(snapshot_admission_v2_json(middle), ["snapshotVerified"]),
    Json(true),
  )
  assert_eq(middle.effects.contains("6"), true)
  assert_eq(middle.effects.contains("5"), false)
  let ending = verify_snapshot_admission_v2(
    installation,
    sql_string_v1(f.at("endLog")),
    f.at("endReceipt"),
  )
  assert_eq(ending.effects.contains("5"), true)
  assert_eq(ending.effects.contains("6"), true)
  assert_eq(
    v4_test_at(snapshot_admission_v2_json(ending), ["snapshotVerified"]),
    Json(true),
  )
}

///|
test "snapshot52 independent check row and effect budgets cannot be expanded by receipts" {
  for kind in ["checks", "rows", "effects"] {
    let fixture = snapshot52_fixture(0)
    let report = match kind {
      "checks" => snapshot52_run(fixture, max_checks=0)
      "rows" => snapshot52_run(fixture, max_rows=2)
      _ => snapshot52_run(fixture, max_effects=5)
    }
    assert_eq(v4_test_at(report, ["status"]), Json("unknown"))
    assert_eq(v4_test_at(report, ["snapshotVerified"]), Json(false))
    snapshot52_no_authority(report)
  }
}

///|
test "snapshot52 receipt counts mode config and authorization tampering are rejected" {
  for
    field in [
      "configSha256", "installationLogSha256", "rowsObserved", "effectsObserved",
      "completeWindow", "moonbitSourceVerified", "effectVersions",
    ] {
    let fixture = snapshot52_fixture(0)
    let r = source_object_v4(source_object_v4(fixture).at("endReceipt"))
    r[field] = match field {
      "rowsObserved" | "effectsObserved" => Json(0)
      "completeWindow" | "moonbitSourceVerified" => Json(true)
      "effectVersions" => Json::array([])
      _ => Json("altered")
    }
    let report = snapshot52_run(fixture)
    assert_eq(v4_test_at(report, ["snapshotVerified"]), Json(false))
    snapshot52_no_authority(report)
  }
}

///|
test "snapshot52 rehashed row values and source identities still fail semantic replay" {
  for query in ["visible-row", "retained-effect"] {
    let fixture = snapshot52_fixture(0)
    snapshot52_mutate_payload(fixture, query, 0, payload => {
      let p = source_object_v4(payload)
      let values = source_object_v4(
        p.at(if query == "visible-row" { "row" } else { "rowValues" }),
      )
      values["balance"] = Json(99)
    })
    let report = snapshot52_run(fixture)
    assert_eq(v4_test_at(report, ["status"]), Json("mismatch"))
    assert_eq(v4_test_at(report, ["snapshotVerified"]), Json(false))
  }
}

///|
test "snapshot52 initial ledger writer identity is bound to independently checked installation" {
  let fixture = snapshot52_fixture(0)
  snapshot52_mutate_payload(fixture, "retained-effect", 0, raw => {
    source_object_v4(raw)["writerPid"] = Json(9999)
  })
  assert_eq(v4_test_at(snapshot52_run(fixture), ["status"]), Json("mismatch"))
}

///|
test "snapshot52 rehashed missing predecessor writer and live deletion are rejected" {
  for change in ["baseVersion", "writerLogin", "operation"] {
    let fixture = snapshot52_fixture(0)
    snapshot52_mutate_payload(fixture, "retained-effect", 2, raw => {
      source_object_v4(raw)[change] = Json(
        match change {
          "baseVersion" => "999"
          "writerLogin" => "outside_writer"
          _ => "DELETE"
        },
      )
    })
    let report = snapshot52_run(fixture)
    assert_eq(v4_test_at(report, ["snapshotVerified"]), Json(false))
    snapshot52_no_authority(report)
  }
}

///|
test "snapshot52 readonly snapshot and peer are compared to original control cells" {
  for field in ["readOnly", "isolation", "snapshot"] {
    let fixture = snapshot52_fixture(0)
    snapshot52_mutate_payload(fixture, "snapshot-mode", 0, raw => {
      source_object_v4(raw)[field] = Json(
        if field == "readOnly" {
          "off"
        } else {
          "bad"
        },
      )
    })
    assert_eq(
      v4_test_at(snapshot52_run(fixture), ["snapshotVerified"]),
      Json(false),
    )
  }
  let fixture = snapshot52_fixture(0)
  snapshot52_mutate_payload(fixture, "snapshot-peer", 0, raw => {
    source_object_v4(raw)["databaseOid"] = Json(999)
  })
  assert_eq(
    v4_test_at(snapshot52_run(fixture), ["snapshotVerified"]),
    Json(false),
  )
}

///|
test "snapshot52 active or future writer transaction cannot be visible" {
  let fixture = snapshot52_fixture(0)
  snapshot52_mutate_payload(fixture, "retained-effect", 1, raw => {
    source_object_v4(raw)["writerXid"] = Json("18446744073709551615")
  })
  assert_eq(v4_test_at(snapshot52_run(fixture), ["status"]), Json("mismatch"))
}

///|
test "snapshot52 rehashed changed control SQL is rejected" {
  let fixture = snapshot52_fixture(0)
  let records = snapshot52_records(fixture)
  for raw in records {
    let e = source_object_v4(raw)
    if e.get("queryId") == Some(Json("snapshot-finish")) &&
      e.get("kind") == Some(Json("control-request")) {
      e["sql"] = Json("COMMIT")
    }
  }
  snapshot52_reseal(fixture, records)
  assert_eq(
    v4_test_at(snapshot52_run(fixture), ["snapshotVerified"]),
    Json(false),
  )
}

///|
test "snapshot52 preserved observations expose original row and control references" {
  let fixture = snapshot52_fixture(0)
  let f = source_object_v4(fixture)
  let check = verify_snapshot_admission_v2(
    snapshot52_install(fixture),
    sql_string_v1(f.at("endLog")),
    f.at("endReceipt"),
  )
  assert_eq(source_object_v4(check.rows.at("1")).contains("row"), true)
  assert_eq(source_object_v4(check.rows.at("1")).contains("requestSeq"), true)
  assert_eq(
    source_object_v4(check.effects.at("4")).at("operation"),
    Json("DELETE"),
  )
  assert_eq(
    source_object_v4(check.effects.at("4")).at("rowValues"),
    Json::null(),
  )
  assert_eq(source_object_v4(check.effects.at("4")).contains("resultSeq"), true)
}

///|
test "snapshot52 rehashed complete row set cannot replace a current version with a consumed one" {
  let fixture = snapshot52_fixture(0)
  snapshot52_mutate_payload(fixture, "visible-row", 1, raw => {
    source_object_v4(raw)["row"] = {
      "identity": 9,
      "balance": 10,
      "enabled": true,
      "__mtw_source_version": 2,
    }
  })
  let records = snapshot52_records(fixture)
  for raw in records {
    let event = source_object_v4(raw)
    if event.get("kind") == Some(Json("control-request")) &&
      event.get("queryId") == Some(Json("visible-row")) &&
      event.get("parameters") == Some(Json([5])) {
      event["parameters"] = Json([2])
    }
  }
  snapshot52_reseal(fixture, records)
  source_object_v4(source_object_v4(fixture).at("endReceipt"))["visibleRowVersions"] = [
    "1", "2", "6",
  ]
  let report = snapshot52_run(fixture)
  assert_eq(v4_test_at(report, ["status"]), Json("mismatch"))
  assert_eq(v4_test_at(report, ["snapshotVerified"]), Json(false))
}

///|
test "snapshot52 JSON options are independent and malformed ranges stay invalid" {
  let fixture = source_object_v4(snapshot52_fixture(0))
  fn run(options : String) -> Json raise {
    sql_json_v1(
      verify_snapshot_admission_v2_json(
        fixture.at("config").stringify(),
        fixture.at("policy").stringify(),
        sql_string_v1(fixture.at("installLog")),
        fixture.at("installed").stringify(),
        sql_string_v1(fixture.at("endLog")),
        fixture.at("endReceipt").stringify(),
        options,
      ),
      8388608,
    )
  }
  assert_eq(v4_test_at(run("{}"), ["snapshotVerified"]), Json(true))
  for
    options in [
      "{\"maxChecks\":0}", "{\"maxInstallationChecks\":0}", "{\"maxRows\":0}", "{\"maxEffects\":0}",
    ] {
    let report = run(options)
    assert_eq(v4_test_at(report, ["status"]), Json("unknown"))
    snapshot52_no_authority(report)
  }
  for
    options in [
      "{\"maxRows\":16385}", "{\"maxChecks\":true}", "{\"maxEffects\":-1}", "{\"budget:\":1}",
    ] {
    let report = run(options)
    assert_eq(v4_test_at(report, ["status"]), Json("invalid"))
    assert_eq(v4_test_at(report, ["snapshotVerified"]), Json(false))
  }
}
