///|
fn session47_fixture() -> Json raise {
  let f = fetch37_fixture()
  let n = fetch37_field(f, "native")
  let rows = orm_array(n.at("rows"))
  n["rows"] = Json([rows[0]])
  let batch = v4_json_copy(orm_array(source_object_v4(f).at("deliveries"))[0])
  let d = source_object_v4(batch)
  d["method"] = Json("fetchall")
  d["complete"] = Json(true)
  source_object_v4(f)["deliveries"] = Json([batch])
  f
}

///|
fn session47_lifecycle(fixtures : Array[Json]) -> String raise {
  let records : Array[Json] = [
    {
      "kind": "header",
      "format": "moontxnwitness-instrumentation/v1",
      "diagnosticOnly": true,
      "processMonotonicDomain": "session-test",
    },
  ]
  for f in fixtures {
    let fields = source_object_v4(f)
    let execution = fields.at("execution")
    let execution_note = records.length() + 1
    records.push({
      "kind": "configured-execution",
      "processMonotonicDomain": "session-test",
      "monotonicNs": "1",
      "frameText": Json(execution.stringify()),
    })
    let native = v4_json_copy(fields.at("native"))
    source_object_v4(native)["executionNoteSeq"] = Json(execution_note)
    let native_note = records.length() + 1
    records.push({
      "kind": "configured-native-result",
      "processMonotonicDomain": "session-test",
      "monotonicNs": "2",
      "frameText": Json(native.stringify()),
    })
    for batch in orm_array(fields.at("deliveries")) {
      let delivered = v4_json_copy(batch)
      source_object_v4(delivered)["nativeNoteSeq"] = Json(native_note)
      records.push({
        "kind": "configured-delivery",
        "processMonotonicDomain": "session-test",
        "monotonicNs": "3",
        "frameText": Json(delivered.stringify()),
      })
    }
  }
  session47_seal(records)
}

///|
fn session47_seal(records : Array[Json]) -> String raise {
  let prefix = StringBuilder()
  for index, record in records {
    source_object_v4(record)["seq"] = Json(index + 1)
    prefix.write_string(record.stringify())
    prefix.write_string("\n")
  }
  let seal : Json = {
    "seq": Json(records.length() + 1),
    "kind": "seal",
    "records": Json(records.length()),
    "prefixSha256": Json(v3_dislock_sha256(prefix.to_string())),
  }
  prefix.write_string(seal.stringify())
  prefix.write_string("\n")
  prefix.to_string()
}

///|
fn session47_records(log : String) -> Array[Json] raise {
  let all : Array[Json] = []
  for line in log.split("\n") {
    if !line.is_empty() {
      all.push(sql_json_v1(line.to_owned(), 524288))
    }
  }
  ignore(all.pop())
  all
}

///|
fn session47_run(
  f : Json,
  log : String,
  options~ : ConfiguredSessionOptionsV4 = configured_session_options_v4().unwrap(),
) -> Json raise {
  let config = parse_sql_config_v1(source_object_v4(f).at("config").stringify()).unwrap()
  configured_session_diagnostic_v4_json(
    diagnose_configured_session_v4(config, log, "null", Json::null(), options~),
  )
}

///|
test "session47 01 native WHERE and PK components use one configured entry" {
  let f = session47_fixture()
  let r = session47_run(f, session47_lifecycle([f]))
  assert_eq(
    v4_test_at(r, ["resultConsistency"]),
    Json("consistent-observed-results"),
  )
  assert_eq(v4_test_at(r, ["sourceFactsProduced"]), Json(false))
  assert_eq(v4_test_at(r, ["isolationAnalysisReady"]), Json(false))
}

///|
test "session47 02 original full result violating WHERE is a capture contradiction" {
  let f = fetch37_fixture()
  let r = session47_run(f, session47_lifecycle([f]))
  assert_eq(v4_test_at(r, ["resultConsistency"]), Json("mismatch"))
  let first = orm_array(source_object_v4(r).at("results"))[0]
  assert_eq(
    v4_test_at(first, ["returnedRowConstraints", "witness", "rule"]),
    Json("returned-row-WHERE-AND"),
  )
  assert_eq(v4_test_at(r, ["isolationModelChecked"]), Json(false))
}

///|
test "session47 03 different connections with the same statement number stay distinct" {
  let a = session47_fixture()
  let b = session47_fixture()
  for name in ["execution", "native"] {
    fetch37_field(b, name)["connection"] = Json("other-connection")
    fetch37_field(b, name)["cursor"] = Json("other-cursor")
    fetch37_field(b, name)["tx"] = Json("other-tx")
  }
  fetch37_field(b, "native")["resultId"] = Json("other-result")
  let d = fetch37_batch(b, 0)
  d["connection"] = Json("other-connection")
  d["cursor"] = Json("other-cursor")
  d["tx"] = Json("other-tx")
  d["resultId"] = Json("other-result")
  let r = session47_run(a, session47_lifecycle([a, b]))
  assert_eq(orm_array(source_object_v4(r).at("results")).length(), 2)
  assert_eq(
    v4_test_at(r, ["resultConsistency"]),
    Json("consistent-observed-results"),
  )
}

///|
test "session47 04 replayed execution identity is rejected" {
  let f = session47_fixture()
  let r = session47_run(f, session47_lifecycle([f, f]))
  assert_eq(v4_test_at(r, ["status"]), Json("input-unverified"))
  assert_eq(v4_test_at(r, ["lifecycleIntegrityChecked"]), Json(false))
}

///|
test "session47 05 torn lifecycle seal is never complete" {
  let f = session47_fixture()
  let raw = session47_lifecycle([f])
  let r = session47_run(f, raw + " ")
  assert_eq(v4_test_at(r, ["status"]), Json("input-unverified"))
}

///|
test "session47 06 sequence holes are not renumbered" {
  let f = session47_fixture()
  let raw = session47_lifecycle([f]).replace_all(
    old="\"seq\":2",
    new="\"seq\":9",
  )
  assert_eq(
    v4_test_at(session47_run(f, raw), ["status"]),
    Json("input-unverified"),
  )
}

///|
test "session47 07 caller zero result budget is not adopted from reports" {
  let f = session47_fixture()
  let raw = session47_lifecycle([f])
  let options = configured_session_options_v4(max_results=0).unwrap()
  let config = parse_sql_config_v1(source_object_v4(f).at("config").stringify()).unwrap()
  let report = session47_run(f, raw, options~)
  assert_eq(v4_test_at(report, ["status"]), Json("input-unverified"))
  assert_true(
    verify_configured_session_diagnostic_v4(
      config,
      raw,
      "null",
      Json::null(),
      report,
      expected_options=options,
    ),
  )
  assert_false(
    verify_configured_session_diagnostic_v4(
      config,
      raw,
      "null",
      Json::null(),
      report,
    ),
  )
}

///|
test "session47 08 zero journal budget records zero checks" {
  let f = session47_fixture()
  let r = session47_run(
    f,
    session47_lifecycle([f]),
    options=configured_session_options_v4(max_journal_checks=0).unwrap(),
  )
  assert_eq(v4_test_at(r, ["execution", "journalChecks"]), Json(0))
  assert_eq(v4_test_at(r, ["resultConsistency"]), Json("unknown"))
}

///|
test "session47 09 an unsupported native OID remains a concrete gap" {
  let f = session47_fixture()
  fetch37_native_field(f, 0)["oid"] = Json(2950)
  let r = session47_run(f, session47_lifecycle([f]))
  assert_true(
    v4_test_at(r, ["resultConsistency"]) != Json("consistent-observed-results"),
  )
}

///|
test "session47 10 mismatched outer native reference cannot borrow another execution" {
  let f = session47_fixture()
  let records = session47_records(session47_lifecycle([f]))
  let native = sql_json_v1(
    sql_string_v1(source_object_v4(records[2]).at("frameText")),
    61440,
  )
  source_object_v4(native)["executionNoteSeq"] = Json(1)
  source_object_v4(records[2])["frameText"] = Json(native.stringify())
  assert_eq(
    v4_test_at(session47_run(f, session47_seal(records)), ["status"]),
    Json("input-unverified"),
  )
}

///|
test "session47 11 report authority claims are rejected by independent replay" {
  let f = session47_fixture()
  let raw = session47_lifecycle([f])
  let config = parse_sql_config_v1(source_object_v4(f).at("config").stringify()).unwrap()
  let r = session47_run(f, raw)
  source_object_v4(r)["sourceFactsProduced"] = Json(true)
  assert_false(
    verify_configured_session_diagnostic_v4(
      config,
      raw,
      "null",
      Json::null(),
      r,
    ),
  )
}

///|
test "session47 12 public caller options reject duplicate decoded keys" {
  let r = sql_json_v1(
    configured_session_options_v4_json(
      "{\"maxResults\":1,\"max\\u0052esults\":2}",
    ),
    8192,
  )
  assert_eq(v4_test_at(r, ["valid"]), Json(false))
}

///|
test "session47 13 unknown installation metadata cannot invent a window" {
  let f = session47_fixture()
  let config = parse_sql_config_v1(source_object_v4(f).at("config").stringify()).unwrap()
  let source : Json = {
    "format": "pretend-window",
    "writerWindowVerified": true,
  }
  let r = configured_session_diagnostic_v4_json(
    diagnose_configured_session_v4(
      config,
      session47_lifecycle([f]),
      "null",
      source,
    ),
  )
  assert_eq(v4_test_at(r, ["writerWindowVerified"]), Json(false))
  assert_eq(v4_test_at(r, ["status"]), Json("input-unverified"))
}

///|
test "session47 14 opaque result getters do not alias the next observation" {
  let f = session47_fixture()
  let config = parse_sql_config_v1(source_object_v4(f).at("config").stringify()).unwrap()
  let result = diagnose_configured_session_v4(
    config,
    session47_lifecycle([f]),
    "null",
    Json::null(),
  )
  let detached = configured_session_diagnostic_v4_json(result)
  source_object_v4(detached)["results"] = Json([])
  assert_eq(
    orm_array(
      source_object_v4(configured_session_diagnostic_v4_json(result)).at(
        "results",
      ),
    ).length(),
    1,
  )
}

///|
test "session47 15 exact journal budget completes while one fewer stays unknown" {
  let f = session47_fixture()
  let raw = session47_lifecycle([f])
  let report = session47_run(f, raw)
  let checks = fetch_number_v1(
    v4_test_at(report, ["execution", "journalChecks"]),
    1000000,
  )
  assert_eq(
    v4_test_at(
      session47_run(
        f,
        raw,
        options=configured_session_options_v4(max_journal_checks=checks).unwrap(),
      ),
      ["resultConsistency"],
    ),
    Json("consistent-observed-results"),
  )
  assert_eq(
    v4_test_at(
      session47_run(
        f,
        raw,
        options=configured_session_options_v4(max_journal_checks=checks - 1).unwrap(),
      ),
      ["status"],
    ),
    Json("input-unverified"),
  )
}

///|
test "session47 16 actual native note reference cannot be substituted" {
  let f = session47_fixture()
  let records = session47_records(session47_lifecycle([f]))
  let d = sql_json_v1(
    sql_string_v1(source_object_v4(records[3]).at("frameText")),
    61440,
  )
  source_object_v4(d)["nativeNoteSeq"] = Json(2)
  source_object_v4(records[3])["frameText"] = Json(d.stringify())
  assert_eq(
    v4_test_at(session47_run(f, session47_seal(records)), ["status"]),
    Json("input-unverified"),
  )
}

///|
test "session47 17 original statement SQL must bind the retained journal event" {
  let f = session47_fixture()
  let e = fetch37_field(f, "execution")
  let tx = e.at("tx")
  let trace : Json = {
    "events": [
      { "seq": 1, "kind": "begin", "tx": tx, "connection": e.at("connection") },
      {
        "seq": 3,
        "kind": "statement",
        "tx": tx,
        "sql": "DELETE FROM biz.orders",
      },
    ],
    "gaps": [],
  }
  let config = parse_sql_config_v1(source_object_v4(f).at("config").stringify()).unwrap()
  let report = configured_session_diagnostic_v4_json(
    diagnose_configured_session_v4(
      config,
      session47_lifecycle([f]),
      trace.stringify(),
      Json::null(),
    ),
  )
  assert_eq(v4_test_at(report, ["status"]), Json("input-unverified"))
}

///|
test "session47 18 component counters are not authorized by a supplied report" {
  let f = session47_fixture()
  let raw = session47_lifecycle([f])
  let report = session47_run(f, raw)
  source_object_v4(source_object_v4(report).at("execution"))["journalChecks"] = Json(
    0,
  )
  let config = parse_sql_config_v1(source_object_v4(f).at("config").stringify()).unwrap()
  assert_false(
    verify_configured_session_diagnostic_v4(
      config,
      raw,
      "null",
      Json::null(),
      report,
    ),
  )
}

///|
test "session47 19 a producer gap is retained without becoming a source fact" {
  let f = session47_fixture()
  let e = fetch37_field(f, "execution")
  let tx = e.at("tx")
  let trace : Json = {
    "events": [
      { "seq": 1, "kind": "begin", "tx": tx, "connection": e.at("connection") },
      { "seq": 3, "kind": "statement", "tx": tx, "sql": e.at("sql") },
    ],
    "gaps": [{ "code": "unknown_sql" }],
  }
  let config = parse_sql_config_v1(source_object_v4(f).at("config").stringify()).unwrap()
  let report = configured_session_diagnostic_v4_json(
    diagnose_configured_session_v4(
      config,
      session47_lifecycle([f]),
      trace.stringify(),
      Json::null(),
    ),
  )
  assert_eq(
    v4_test_at(report, ["diagnosticTrace", "producerGaps"]),
    Json([{ "code": "unknown_sql" }]),
  )
  assert_eq(
    v4_test_at(report, ["diagnosticTrace", "sourceJournalIndexVerified"]),
    Json(false),
  )
  assert_eq(v4_test_at(report, ["sourceFactsProduced"]), Json(false))
}

///|
test "session47 20 zero returned row budget does not imply a checked query" {
  let f = session47_fixture()
  let report = session47_run(
    f,
    session47_lifecycle([f]),
    options=configured_session_options_v4(max_result_checks=0).unwrap(),
  )
  assert_eq(
    v4_test_at(report, ["resultConsistency"]),
    Json("partial-or-unknown"),
  )
  assert_eq(v4_test_at(report, ["isolationAnalysisReady"]), Json(false))
}

///|
test "session47 21 malformed execution candidate returns a bounded diagnostic" {
  let f = session47_fixture()
  source_object_v4(f)["execution"] = {
    "connection": "c",
    "cursor": "u",
    "tx": "t",
    "statementSeq": 3,
  }
  let n = fetch37_field(f, "native")
  n["connection"] = Json("c")
  n["cursor"] = Json("u")
  n["tx"] = Json("t")
  let d = fetch37_batch(f, 0)
  d["connection"] = Json("c")
  d["cursor"] = Json("u")
  d["tx"] = Json("t")
  let r = session47_run(f, session47_lifecycle([f]))
  assert_eq(v4_test_at(r, ["status"]), Json("input-unverified"))
}
