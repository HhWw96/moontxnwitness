///|
fn mraw_history(body : Array[Json], missing~ : Array[Int32] = []) -> HistoryV4 {
  let events : Array[Json] = [
    {
      "kind": "snapshot",
      "initial": { "x": "x0", "y": "y0" },
      "consistent": true,
    },
  ]
  events.append(body)
  let stamped = events.mapi((i, e) => {
    let fields = object_fields_unchecked_v3(e)
    fields["seq"] = Json(i + 1)
    fields["time"] = Json(i)
    Json(fields)
  })
  parse_history_v4(
    (
      {
        "traceSchema": 3,
        "dataModel": "point-register-v1",
        "clockDomain": "raw-model-map-test",
        "scope": { "exclusiveWriters": true },
        "events": Json(
          stamped.filter(e => {
            !missing.contains(rcl_number(v4_test_at(e, ["seq"])))
          }),
        ),
        "gaps": [],
      } : Json).stringify(),
  ).unwrap()
}

///|
fn mraw_facts(h : HistoryV4) -> ModelFactsV4 {
  let root = object_fields_unchecked_v3(h.source_document)
  let ids : Array[String] = []
  for event in capture_source_array_v4(root.at("events")) {
    let e = object_fields_unchecked_v3(event)
    if e.at("kind") == Json("begin") {
      ids.push(capture_source_string_v4(e.at("tx")))
    }
  }
  model_facts_v4(
    h,
    clients=ids.map(id => {
      ({ id: "logical-" + id, transactions: [id], } : ModelClientV4)
    }),
    clients_complete=true,
  ).unwrap()
}

///|
fn mraw_simple() -> Array[Json] {
  let body = [
    raw5_begin("A"),
    raw5_read("A", "x0"),
    raw5_write("A", "x1", "x0"),
    raw5_read("A", "x1"),
  ]
  raw5_commit(body, "A")
  body.push(raw5_begin("B"))
  body.push(raw5_read("B", "x1"))
  body.push(raw5_write("B", "x2", "x1"))
  raw5_commit(body, "B")
  body
}

///|
fn mraw_report(
  h : HistoryV4,
  models~ : Array[ElleModelV4] = elle_core_models_v4(),
  source~ : Int32 = 1000000,
) -> Json {
  mct_report(mraw_facts(h), models~, source~)
}

///|
test "raw model mapping 01 all fourteen definitions consume complete original point programs" {
  let h = mraw_history(mraw_simple())
  let report = mraw_report(h)
  for model in elle_core_models_v4() {
    assert_eq(mct_status(report, model), "checked-compatible")
  }
  assert_eq(
    v4_test_at(report, ["sourceProfile"]),
    Json("captured-register-full-program/v2"),
  )
  let completion = mct_rule(
    report,
    ElleSnapshotIsolation,
    "completion/Ext/data-only",
  )
  assert_eq(
    v4_test_at(completion, ["evidence", "sourceProjection", "definition"]),
    Json("captured-register-program-projection/v1"),
  )
  assert_true(
    verify_models_v4(
      mraw_facts(h),
      report,
      model_options_v4(models=elle_core_models_v4()).unwrap(),
    ),
  )
}

///|
test "raw model mapping 02 savepoint revoked own observations remain valid with full completion" {
  let body = [
    raw5_begin("A"),
    raw5_read("A", "x0"),
    raw5_mark("A"),
    raw5_write("A", "a", "x0"),
    raw5_read("A", "a"),
    raw5_undo("A"),
    raw5_read("A", "x0"),
    raw5_write("A", "a2", "x0"),
  ]
  raw5_commit(body, "A")
  let report = mraw_report(mraw_history(body))
  for model in elle_core_models_v4() {
    assert_eq(mct_status(report, model), "checked-compatible")
  }
  let mapped = v4_test_at(
    mct_rule(report, ElleSnapshotIsolation, "completion/Ext/data-only"),
    ["evidence", "sourceProjection", "transactions"],
  )
  assert_eq(
    capture_source_array_v4(
      v4_test_at(capture_source_array_v4(mapped)[0], ["operations"]),
    ).length(),
    5,
  )
  assert_eq(
    capture_source_array_v4(
      v4_test_at(
        mct_rule(report, ElleSnapshotIsolation, "completion/Ext/data-only"),
        ["evidence", "sourceProjection", "programEvents"],
      ),
    ).length(),
    11,
  )
}

///|
test "raw model mapping 03 sequence hole cannot close final-source completion" {
  let h = mraw_history(mraw_simple(), missing=[4])
  let report = mraw_report(h)
  assert_eq(mct_status(report, ElleSnapshotIsolation), "unknown")
  assert_true(v4_test_at(report, ["sourceCoverage", "ww"]) != Json(true))
}

///|
test "raw model mapping 04 unmapped statement cannot supply a completion premise" {
  let body = mraw_simple()
  body.insert(
    3,
    ({ "kind": "statement", "tx": "A", "sql": "ROLLBACK TO SAVEPOINT s" } : Json),
  )
  assert_eq(
    mct_status(mraw_report(mraw_history(body)), ElleSnapshotIsolation),
    "unknown",
  )
}

///|
test "raw model mapping 05 missing source cannot be completed into a false observed source" {
  let body = mraw_simple()
  body[1] = raw5_read("A", "missing")
  assert_eq(
    mct_status(mraw_report(mraw_history(body)), ElleReadCommitted),
    "unknown",
  )
}

///|
test "raw model mapping 06 initial read with own immediate successor never gets later RW" {
  let body = [
    raw5_begin("A"),
    raw5_read("A", "x0"),
    raw5_write("A", "x1", "x0"),
    ({ "kind": "read", "tx": "A", "key": "y", "version": "y1" } : Json),
  ]
  raw5_commit(body, "A")
  body.push(raw5_begin("B"))
  body.push(raw5_write("B", "x2", "x1"))
  body.push({
    "kind": "write",
    "tx": "B",
    "key": "y",
    "version": "y1",
    "predecessor": "y0",
  })
  raw5_commit(body, "B")
  let source = model_register_source_v4(mraw_history(body), 1000000)
  assert_true(
    !source.edges.any(e => {
      e.from == "A" && e.to == "B" && e.kind == ScopedRWItem
    }),
  )
  assert_eq(
    mct_status(mraw_report(mraw_history(body)), ElleReadCommitted),
    "refuted",
  )
}

///|
test "raw model mapping 07 all delivered external reads retain hidden WR cycles under RC" {
  let body = [
    raw5_begin("A"),
    raw5_begin("B"),
    raw5_read("A", "x0"),
    ({ "kind": "read", "tx": "B", "key": "y", "version": "y0" } : Json),
    (
      {
        "kind": "write",
        "tx": "A",
        "key": "y",
        "version": "y1",
        "predecessor": "y0",
      } : Json),
    raw5_write("B", "x1", "x0"),
    raw5_read("A", "x1"),
    ({ "kind": "read", "tx": "B", "key": "y", "version": "y1" } : Json),
  ]
  raw5_commit(body, "A")
  raw5_commit(body, "B")
  assert_eq(
    mct_status(mraw_report(mraw_history(body)), ElleReadCommitted),
    "refuted",
  )
}

///|
test "raw model mapping 08 given logical snapshot assertions remain unsupported" {
  let facts = mraw_facts(mraw_history(mraw_simple()))
  let options = model_options_v4(
    models=[ElleSnapshotIsolation],
    completion_policy=ModelGivenSnapshotsUnsupported,
  ).unwrap()
  let report = model_classification_v4_json(classify_models_v4(facts, options))
  assert_eq(mct_status(report, ElleSnapshotIsolation), "unknown")
}

///|
test "raw model mapping 09 caller budgets and original program evidence cannot be self authorized" {
  let facts = mraw_facts(mraw_history(mraw_simple()))
  let options = model_options_v4(models=[ElleSnapshotIsolation]).unwrap()
  let report = model_classification_v4_json(classify_models_v4(facts, options))
  assert_true(
    !verify_models_v4(
      facts,
      report,
      model_options_v4(models=[ElleSnapshotIsolation], max_source_checks=0).unwrap(),
    ),
  )
  let completion = mct_rule(
    report,
    ElleSnapshotIsolation,
    "completion/Ext/data-only",
  )
  v4_test_replace(
    completion,
    ["evidence", "sourceProjection", "initialVersions", "x"],
    Json("false"),
  )
  assert_true(!verify_models_v4(facts, report, options))
}

///|
test "raw model mapping 10 source zero budget cannot complete any model" {
  let report = mraw_report(mraw_history(mraw_simple()), source=0)
  for model in elle_core_models_v4() {
    assert_eq(mct_status(report, model), "unknown")
  }
}

///|
test "raw model mapping 11 missing rollback cannot leak a stale source helper G1b proof" {
  let body = raw5_producer()
  let history = mraw_history(body, missing=[6])
  let source = model_register_source_v4(history, 1000000)
  assert_eq(source.rules.at("G1b").status, "unknown")
  assert_eq(mct_status(mraw_report(history), ElleReadCommitted), "unknown")
}

///|
test "raw model mapping 12 confirmed whole abort proof survives a producer hole without finality" {
  let body = [
    raw5_begin("P"),
    raw5_read("P", "x0"),
    raw5_write("P", "p1", "x0"),
    ({ "kind": "rollback_ok", "tx": "P" } : Json),
    raw5_begin("R"),
    raw5_read("R", "p1"),
  ]
  raw5_commit(body, "R")
  let report = mraw_report(mraw_history(body, missing=[3]))
  assert_eq(mct_status(report, ElleReadCommitted), "refuted")
  assert_eq(mct_status(report, ElleSnapshotIsolation), "refuted")
  assert_eq(v4_test_at(report, ["sourceCoverage", "ww"]), Json(false))
}

///|
test "raw model mapping 13 write lineage mismatch is not a fabricated formal read" {
  let body = [
    raw5_begin("A"),
    raw5_write("A", "a1", "x0"),
    raw5_write("A", "a2", "x0"),
  ]
  raw5_commit(body, "A")
  let source = model_register_source_v4(mraw_history(body), 1000000)
  assert_eq(source.rules.at("write-input-applicability").status, "unknown")
  assert_true(source.rules.at("internal").status != "refuted")
  assert_eq(
    mct_status(mraw_report(mraw_history(body)), ElleSnapshotIsolation),
    "unknown",
  )
}

///|
test "raw model mapping 14 missing installed predecessor branch cannot produce a writer total order" {
  let body = [raw5_begin("A"), raw5_write("A", "a", "x0")]
  raw5_commit(body, "A")
  body.push(raw5_begin("B"))
  body.push(raw5_write("B", "b", "x0"))
  raw5_commit(body, "B")
  let report = mraw_report(mraw_history(body))
  assert_eq(v4_test_at(report, ["sourceCoverage", "ww"]), Json(false))
  assert_eq(mct_status(report, ElleReadUncommitted), "unknown")
}

///|
test "raw model mapping 15 source budget exact boundary includes window and lineage references" {
  let h = mraw_history(mraw_simple())
  let full = model_register_source_v4(h, 1000000)
  let count = rcl_number(v4_test_at(full.execution, ["checks"]))
  let exact = model_register_source_v4(h, count)
  let short = model_register_source_v4(h, count - 1)
  assert_eq(
    exact.rules.at("write-input-applicability").status,
    "checked-compatible",
  )
  assert_eq(v4_test_at(exact.execution, ["limited"]), Json(false))
  assert_eq(short.rules.at("write-input-applicability").status, "unknown")
  assert_eq(v4_test_at(short.execution, ["checks"]), Json(count - 1))
  assert_eq(
    v4_test_at(full.execution, ["counterContract"]),
    Json("model-captured-register-window-and-source-checks-2"),
  )
}

///|
test "raw model mapping 16 mutable certificate getters cannot mutate retained original facts" {
  let h = mraw_history(mraw_simple())
  let facts = mraw_facts(h)
  let original = history_v4_json(h)
  let r = classify_models_v4(
    facts,
    model_options_v4(models=[ElleSnapshotIsolation]).unwrap(),
  )
  let exposed = model_classification_v4_json(r)
  let cert = mct_rule(
    exposed,
    ElleSnapshotIsolation,
    "completion/Ext/data-only",
  )
  let events = capture_source_array_v4(
    v4_test_at(cert, ["evidence", "sourceProjection", "programEvents"]),
  )
  object_fields_unchecked_v3(events[0])["kind"] = Json("tampered")
  assert_eq(history_v4_json(h), original)
  assert_true(
    v4_test_at(model_classification_v4_json(r), ["models"]) !=
    v4_test_at(exposed, ["models"]),
  )
}

///|
test "raw model mapping 17 actual dirty write retains its specific label and established G1a implication" {
  let body = [
    raw5_begin("P"),
    raw5_write("P", "p1", "x0"),
    ({ "kind": "rollback_ok", "tx": "P" } : Json),
    raw5_begin("R"),
    raw5_write("R", "r1", "p1"),
  ]
  raw5_commit(body, "R")
  let source = model_register_source_v4(mraw_history(body), 1000000)
  assert_eq(source.rules.at("G1a").status, "refuted")
  assert_true(
    capture_source_array_v4(
      v4_test_at(source.rules.at("G1a").evidence, ["findings"]),
    ).any(f => v4_test_at(f, ["category"]) == Json("dirty-update")),
  )
  assert_eq(
    mct_status(mraw_report(mraw_history(body)), ElleReadCommitted),
    "refuted",
  )
}

///|
test "raw model mapping 18 RC may complete while an external repeatable read is refuted" {
  let body = [
    raw5_begin("R"),
    raw5_read("R", "x0"),
    raw5_begin("W"),
    raw5_write("W", "x1", "x0"),
  ]
  raw5_commit(body, "W")
  body.push(raw5_read("R", "x1"))
  raw5_commit(body, "R")
  let report = mraw_report(mraw_history(body))
  assert_eq(mct_status(report, ElleReadCommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleRepeatableRead), "refuted")
  assert_eq(mct_status(report, ElleSnapshotIsolation), "refuted")
}
