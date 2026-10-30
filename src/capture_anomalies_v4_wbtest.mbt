///|
fn cap034_report(text : String, max_checks~ : Int32 = 1000000) -> Json {
  capture_anomalies_v4_json(
    inspect_capture_anomalies_v4(parse_history_v4(text).unwrap(), max_checks~),
  )
}

///|
fn cap034_find(report : Json, category : String) -> Array[Json] {
  match object_fields_unchecked_v3(report).at("findings") {
    Array(items) =>
      items.filter(item => {
        object_fields_unchecked_v3(item).at("category") == Json(category)
      })
    _ => []
  }
}

///|
fn cap034_gap(report : Json, code : String) -> Bool {
  let coverage = object_fields_unchecked_v3(
    object_fields_unchecked_v3(report).at("coverage"),
  )
  match coverage.at("gaps") {
    Array(items) =>
      items.any(item => {
        object_fields_unchecked_v3(item).at("code") == Json(code)
      })
    _ => false
  }
}

///|
test "capture034 01 confirmed aborted register source proves G1a" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"rollback_ok\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(!cap034_find(report, "G1a").is_empty())
  assert_true(cap034_find(report, "G1b").is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
  assert_eq(
    v4_test_at(cap034_find(report, "G1a")[0], [
      "evidence", "sourceEffect", "transaction",
    ]),
    Json("W"),
  )
}

///|
test "capture034 02 later whole rollback preserves earlier delivered external read" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":5,\"time\":4,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_ok\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"rollback_ok\",\"tx\":\"W\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(!cap034_find(report, "G1a").is_empty())
}

///|
test "capture034 03 committed reader observes savepoint-revoked external effect" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"savepoint\",\"tx\":\"W\",\"name\":\"s\",\"instance\":\"s1\"},{\"seq\":4,\"time\":3,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":5,\"time\":4,\"kind\":\"rollback_to\",\"tx\":\"W\",\"instance\":\"s1\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":8,\"time\":7,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":9,\"time\":8,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":11,\"time\":10,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(!cap034_find(report, "G1a").is_empty())
  assert_true(cap034_find(report, "G1b").is_empty())
}

///|
test "capture034 04 future savepoint rollback does not erase external observation" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"savepoint\",\"tx\":\"W\",\"name\":\"s\",\"instance\":\"s1\"},{\"seq\":4,\"time\":3,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"},{\"seq\":9,\"time\":8,\"kind\":\"rollback_to\",\"tx\":\"W\",\"instance\":\"s1\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":11,\"time\":10,\"kind\":\"commit_ok\",\"tx\":\"W\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(!cap034_find(report, "G1a").is_empty())
}

///|
test "capture034 05 aborted reader does not assert committed G1a" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"rollback_ok\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":7,\"time\":6,\"kind\":\"rollback_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "G1a").is_empty())
}

///|
test "capture034 06 own read before own later rollback is not external G1a" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"savepoint\",\"tx\":\"W\",\"name\":\"s\",\"instance\":\"s1\"},{\"seq\":4,\"time\":3,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":5,\"time\":4,\"kind\":\"read\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":6,\"time\":5,\"kind\":\"rollback_to\",\"tx\":\"W\",\"instance\":\"s1\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"W\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "G1a").is_empty())
  assert_true(cap034_find(report, "G1b").is_empty())
  assert_true(cap034_find(report, "dirty-update").is_empty())
}

///|
test "capture034 07 committed nonfinal register write proves G1b" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w2\",\"predecessor\":\"w1\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":7,\"time\":6,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(!cap034_find(report, "G1b").is_empty())
  assert_true(cap034_find(report, "G1a").is_empty())
}

///|
test "capture034 08 final register source is not G1b" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w2\",\"predecessor\":\"w1\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":7,\"time\":6,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w2\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "G1b").is_empty())
}

///|
test "capture034 09 own intermediate read is not external G1b" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"read\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":5,\"time\":4,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w2\",\"predecessor\":\"w1\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_ok\",\"tx\":\"W\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "G1b").is_empty())
}

///|
test "capture034 10 missing source is gap not aborted read" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"absent\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "G1a").is_empty())
  assert_true(cap034_find(report, "G1b").is_empty())
  assert_true(cap034_gap(report, "missing-source"))
}

///|
test "capture034 11 source unknown outcome is gap" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"disconnect\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "G1a").is_empty())
  assert_true(cap034_find(report, "G1b").is_empty())
  assert_true(cap034_gap(report, "unknown-source-outcome"))
}

///|
test "capture034 12 unknown reader cannot assert committed phenomena" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"rollback_ok\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":7,\"time\":6,\"kind\":\"disconnect\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "G1a").is_empty())
  assert_true(cap034_gap(report, "unknown-observer-outcome"))
}

///|
test "capture034 13 later client source observation is no future proof" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":4,\"time\":3,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":5,\"time\":4,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":6,\"time\":5,\"kind\":\"rollback_ok\",\"tx\":\"W\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "G1a").is_empty())
  assert_true(cap034_gap(report, "source-not-observed-before-use"))
}

///|
test "capture034 14 unknown unrelated transaction does not mask proof" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"rollback_ok\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"U\",\"connection\":\"c-U\"},{\"seq\":6,\"time\":5,\"kind\":\"disconnect\",\"tx\":\"U\"},{\"seq\":7,\"time\":6,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(!cap034_find(report, "G1a").is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
  assert_eq(v4_test_at(report, ["coverage", "complete"]), Json(false))
}

///|
test "capture034 15 actual predecessor proves dirty update without SELECT" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"rollback_ok\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\",\"predecessor\":\"w1\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(!cap034_find(report, "dirty-update").is_empty())
  assert_true(cap034_find(report, "G1a").is_empty())
  assert_true(cap034_find(report, "G1b").is_empty())
}

///|
test "capture034 16 revoked actual predecessor proves dirty update" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"savepoint\",\"tx\":\"W\",\"name\":\"s\",\"instance\":\"s1\"},{\"seq\":4,\"time\":3,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":5,\"time\":4,\"kind\":\"rollback_to\",\"tx\":\"W\",\"instance\":\"s1\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":8,\"time\":7,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":9,\"time\":8,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\",\"predecessor\":\"w1\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":11,\"time\":10,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(!cap034_find(report, "dirty-update").is_empty())
}

///|
test "capture034 17 own valid write base is not dirty update" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w2\",\"predecessor\":\"w1\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_ok\",\"tx\":\"W\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "dirty-update").is_empty())
}

///|
test "capture034 18 aborted successor does not prove dirty update" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"rollback_ok\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\",\"predecessor\":\"w1\"},{\"seq\":7,\"time\":6,\"kind\":\"rollback_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "dirty-update").is_empty())
}

///|
test "capture034 19 revoked successor does not prove dirty update" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"rollback_ok\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"savepoint\",\"tx\":\"R\",\"name\":\"s\",\"instance\":\"s1\"},{\"seq\":7,\"time\":6,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\",\"predecessor\":\"w1\"},{\"seq\":8,\"time\":7,\"kind\":\"rollback_to\",\"tx\":\"R\",\"instance\":\"s1\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "dirty-update").is_empty())
}

///|
test "capture034 20 unknown actual predecessor stays unknown" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"disconnect\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\",\"predecessor\":\"w1\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "dirty-update").is_empty())
  assert_true(cap034_gap(report, "unknown-source-outcome"))
}

///|
test "capture034 21 committed intermediate predecessor alone is not dirty or read" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w2\",\"predecessor\":\"w1\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":7,\"time\":6,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":8,\"time\":7,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\",\"predecessor\":\"w1\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "dirty-update").is_empty())
  assert_true(cap034_find(report, "G1b").is_empty())
  assert_true(cap034_find(report, "G1a").is_empty())
}

///|
test "capture034 22 confirmed revoke retained with unknown enclosing outcome" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"savepoint\",\"tx\":\"W\",\"name\":\"s\",\"instance\":\"s1\"},{\"seq\":4,\"time\":3,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":5,\"time\":4,\"kind\":\"rollback_to\",\"tx\":\"W\",\"instance\":\"s1\"},{\"seq\":6,\"time\":5,\"kind\":\"disconnect\",\"tx\":\"W\"},{\"seq\":7,\"time\":6,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(!cap034_find(report, "G1a").is_empty())
  assert_eq(v4_test_at(report, ["coverage", "complete"]), Json(false))
}

///|
test "capture034 23 observer savepoint rollback retains already delivered read" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"rollback_ok\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"savepoint\",\"tx\":\"R\",\"name\":\"s\",\"instance\":\"s1\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":8,\"time\":7,\"kind\":\"rollback_to\",\"tx\":\"R\",\"instance\":\"s1\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(!cap034_find(report, "G1a").is_empty())
}

///|
test "capture034 24 aborted append item proves G1a" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"rollback_ok\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"same\"}]},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(!cap034_find(report, "G1a").is_empty())
  assert_true(cap034_find(report, "G1b").is_empty())
}

///|
test "capture034 25 committed nonfinal last append proves G1b" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"b\",\"value\":\"same\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":7,\"time\":6,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":8,\"time\":7,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"same\"}]},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(!cap034_find(report, "G1b").is_empty())
}

///|
test "capture034 26 earlier append contained in full final read is not G1b" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"b\",\"value\":\"same\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":7,\"time\":6,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":8,\"time\":7,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"same\"},{\"id\":\"b\",\"value\":\"same\"}]},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "G1b").is_empty())
}

///|
test "capture034 27 last item belongs to other final writer not early intermediate" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"begin\",\"tx\":\"C\",\"connection\":\"c-C\"},{\"seq\":5,\"time\":4,\"kind\":\"append\",\"tx\":\"C\",\"key\":\"x\",\"id\":\"c\",\"value\":\"same\"},{\"seq\":6,\"time\":5,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"b\",\"value\":\"same\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"C\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"C\"},{\"seq\":11,\"time\":10,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":12,\"time\":11,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"same\"},{\"id\":\"c\",\"value\":\"same\"}]},{\"seq\":13,\"time\":12,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":14,\"time\":13,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "G1b").is_empty())
}

///|
test "capture034 28 own intermediate append read is not external G1b" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"list_read\",\"tx\":\"W\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"same\"}]},{\"seq\":5,\"time\":4,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"b\",\"value\":\"same\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_ok\",\"tx\":\"W\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "G1b").is_empty())
}

///|
test "capture034 29 missing writer prefix cannot prove full version G1b" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"b\",\"value\":\"same\"},{\"seq\":5,\"time\":4,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"c\",\"value\":\"same\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":8,\"time\":7,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":9,\"time\":8,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"b\",\"value\":\"same\"}]},{\"seq\":10,\"time\":9,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":11,\"time\":10,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "G1b").is_empty())
  assert_true(cap034_gap(report, "list-complete-version-unproven"))
}

///|
test "capture034 30 matching aborted item survives malformed list shape" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"b\",\"value\":\"same\"},{\"seq\":5,\"time\":4,\"kind\":\"rollback_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"b\",\"value\":\"same\"},{\"id\":\"a\",\"value\":\"same\"}]},{\"seq\":8,\"time\":7,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(!cap034_find(report, "G1a").is_empty())
  assert_true(cap034_find(report, "G1b").is_empty())
}

///|
test "capture034 31 equal identity conflicting business value does not prove G1a" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"rollback_ok\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"different\"}]},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "G1a").is_empty())
  assert_true(cap034_gap(report, "item-identity-value-conflict"))
}

///|
test "capture034 32 revoked final append restores earlier surviving final identity" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"savepoint\",\"tx\":\"W\",\"name\":\"s\",\"instance\":\"s1\"},{\"seq\":5,\"time\":4,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"b\",\"value\":\"same\"},{\"seq\":6,\"time\":5,\"kind\":\"rollback_to\",\"tx\":\"W\",\"instance\":\"s1\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":9,\"time\":8,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":10,\"time\":9,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"same\"}]},{\"seq\":11,\"time\":10,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":12,\"time\":11,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "G1b").is_empty())
  assert_true(cap034_find(report, "G1a").is_empty())
}

///|
test "capture034 33 read revoked append gets G1a not G1b" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"savepoint\",\"tx\":\"W\",\"name\":\"s\",\"instance\":\"s1\"},{\"seq\":5,\"time\":4,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"b\",\"value\":\"same\"},{\"seq\":6,\"time\":5,\"kind\":\"rollback_to\",\"tx\":\"W\",\"instance\":\"s1\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":9,\"time\":8,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":10,\"time\":9,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"same\"},{\"id\":\"b\",\"value\":\"same\"}]},{\"seq\":11,\"time\":10,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":12,\"time\":11,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(!cap034_find(report, "G1a").is_empty())
  assert_true(cap034_find(report, "G1b").is_empty())
}

///|
test "capture034 34 rollback after external list read preserves G1a observation" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"savepoint\",\"tx\":\"W\",\"name\":\"s\",\"instance\":\"s1\"},{\"seq\":4,\"time\":3,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"same\"}]},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"},{\"seq\":9,\"time\":8,\"kind\":\"rollback_to\",\"tx\":\"W\",\"instance\":\"s1\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":11,\"time\":10,\"kind\":\"commit_ok\",\"tx\":\"W\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(!cap034_find(report, "G1a").is_empty())
}

///|
test "capture034 35 legal key transaction and item names cannot collide in indices" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"x\",\"connection\":\"c-x\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"x\",\"key\":\"x\",\"id\":\"x\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"append\",\"tx\":\"x\",\"key\":\"x\",\"id\":\"x|tail\",\"value\":\"same\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_request\",\"tx\":\"x\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_ok\",\"tx\":\"x\"},{\"seq\":7,\"time\":6,\"kind\":\"begin\",\"tx\":\"R|x\",\"connection\":\"c-R|x\"},{\"seq\":8,\"time\":7,\"kind\":\"list_read\",\"tx\":\"R|x\",\"key\":\"x\",\"items\":[{\"id\":\"x\",\"value\":\"same\"}]},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R|x\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R|x\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(!cap034_find(report, "G1b").is_empty())
}

///|
test "capture034 36 list missing item retains gap not G1a" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"missing\",\"value\":\"same\"}]},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "G1a").is_empty())
  assert_true(cap034_gap(report, "missing-source"))
}

///|
test "capture034 37 list append adjacency does not invent dirty update" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"rollback_ok\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"append\",\"tx\":\"R\",\"key\":\"x\",\"id\":\"b\",\"value\":\"same\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_true(cap034_find(report, "dirty-update").is_empty())
  assert_eq(
    v4_test_at(report, ["scope", "listDirtyUpdate"]),
    Json("unsupported"),
  )
}

///|
test "capture034 38 capture gap does not become completed diagnosis" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true}],\"gaps\":[{\"code\":\"missing_segment\",\"message\":\"A segment is missing\"}]}"
  let report = cap034_report(source)
  assert_eq(v4_test_at(report, ["status"]), Json("unknown"))
  assert_true(cap034_gap(report, "normalization-coverage-gap"))
}

///|
test "capture034 39 writer scope missing stays explicit unknown" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":false},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_eq(v4_test_at(report, ["coverage", "complete"]), Json(false))
}

///|
test "capture034 40 RC repeated external reads do not guess INT" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = cap034_report(source)
  assert_eq(v4_test_at(report, ["scope", "INT"]), Json("unsupported"))
  assert_eq(
    v4_test_at(report, ["scope", "acceptsIsolationModels"]),
    Json(false),
  )
}

///|
test "capture034 41 proved source replaces gap when output is saturated" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"rollback_ok\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[{\"code\":\"frozen_gap_0\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_1\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_2\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_3\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_4\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_5\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_6\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_7\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_8\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_9\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_10\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_11\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_12\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_13\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_14\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_15\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_16\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_17\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_18\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_19\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_20\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_21\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_22\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_23\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_24\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_25\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_26\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_27\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_28\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_29\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_30\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_31\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_32\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_33\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_34\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_35\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_36\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_37\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_38\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_39\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_40\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_41\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_42\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_43\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_44\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_45\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_46\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_47\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_48\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_49\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_50\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_51\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_52\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_53\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_54\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_55\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_56\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_57\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_58\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_59\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_60\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_61\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_62\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_63\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_64\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_65\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_66\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_67\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_68\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_69\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_70\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_71\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_72\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_73\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_74\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_75\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_76\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_77\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_78\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_79\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_80\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_81\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_82\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_83\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_84\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_85\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_86\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_87\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_88\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_89\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_90\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_91\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_92\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_93\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_94\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_95\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_96\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_97\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_98\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_99\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_100\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_101\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_102\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_103\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_104\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_105\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_106\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_107\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_108\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_109\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_110\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_111\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_112\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_113\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_114\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_115\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_116\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_117\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_118\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_119\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_120\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_121\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_122\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_123\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_124\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_125\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_126\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_127\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_128\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_129\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_130\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_131\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_132\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_133\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_134\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_135\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_136\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_137\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_138\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_139\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_140\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_141\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_142\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_143\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_144\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_145\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_146\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_147\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_148\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_149\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_150\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_151\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_152\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_153\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_154\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_155\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_156\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_157\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_158\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_159\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_160\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_161\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_162\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_163\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_164\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_165\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_166\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_167\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_168\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_169\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_170\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_171\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_172\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_173\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_174\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_175\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_176\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_177\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_178\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_179\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_180\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_181\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_182\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_183\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_184\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_185\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_186\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_187\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_188\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_189\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_190\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_191\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_192\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_193\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_194\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_195\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_196\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_197\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_198\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_199\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_200\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_201\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_202\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_203\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_204\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_205\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_206\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_207\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_208\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_209\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_210\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_211\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_212\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_213\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_214\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_215\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_216\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_217\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_218\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_219\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_220\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_221\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_222\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_223\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_224\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_225\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_226\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_227\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_228\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_229\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_230\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_231\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_232\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_233\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_234\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_235\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_236\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_237\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_238\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_239\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_240\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_241\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_242\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_243\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_244\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_245\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_246\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_247\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_248\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_249\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_250\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_251\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_252\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_253\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_254\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_255\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_256\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_257\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_258\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_259\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_260\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_261\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_262\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_263\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_264\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_265\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_266\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_267\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_268\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_269\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_270\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_271\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_272\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_273\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_274\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_275\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_276\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_277\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_278\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_279\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_280\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_281\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_282\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_283\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_284\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_285\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_286\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_287\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_288\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_289\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_290\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_291\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_292\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_293\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_294\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_295\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_296\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_297\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_298\",\"message\":\"Retained missing observation\"},{\"code\":\"frozen_gap_299\",\"message\":\"Retained missing observation\"}]}"
  let report = cap034_report(source)
  assert_true(!cap034_find(report, "G1a").is_empty())
  assert_eq(v4_test_at(report, ["coverage", "findingsTruncated"]), Json(true))
  assert_eq(v4_test_at(report, ["coverage", "complete"]), Json(false))
}

///|
test "capture034 42 zero exact and exhausted work budgets" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true}],\"gaps\":[]}"
  let zero = cap034_report(source, max_checks=0)
  assert_eq(v4_test_at(zero, ["execution", "checks"]), Json(0))
  assert_eq(v4_test_at(zero, ["execution", "limited"]), Json(true))
  let exact = cap034_report(source, max_checks=3)
  assert_eq(v4_test_at(exact, ["status"]), Json("checked"))
  assert_eq(v4_test_at(exact, ["execution", "limited"]), Json(false))
  assert_eq(
    v4_test_at(cap034_report(source, max_checks=2), ["status"]),
    Json("unknown"),
  )
}

///|
test "capture034 43 invalid budgets grant no work" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true}],\"gaps\":[]}"
  for budget in [-1, 1000001] {
    let report = cap034_report(source, max_checks=budget)
    assert_eq(v4_test_at(report, ["status"]), Json("invalid-budget"))
    assert_eq(v4_test_at(report, ["execution", "checks"]), Json(0))
  }
}

///|
test "capture034 44 declared order chain is outside raw source helper" {
  let source = "{\"schemaVersion\":1,\"model\":\"serializable\",\"initial\":{\"x\":\"x0\"},\"versionOrders\":{\"x\":[\"x0\",\"a\",\"b\"]},\"transactions\":[{\"id\":\"A\",\"status\":\"committed\",\"ops\":[{\"type\":\"write\",\"key\":\"x\",\"version\":\"a\"}]},{\"id\":\"B\",\"status\":\"committed\",\"ops\":[{\"type\":\"write\",\"key\":\"x\",\"version\":\"b\"}]}]}"
  let report = cap034_report(source)
  assert_eq(v4_test_at(report, ["status"]), Json("unsupported"))
  assert_true(cap034_find(report, "dirty-update").is_empty())
  assert_eq(
    v4_test_at(report, ["scope", "declaredVersionOrdersAcceptedAsWriteBase"]),
    Json(false),
  )
}

///|
test "capture034 45 getter returns detached evidence and original document" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"rollback_ok\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let history = parse_history_v4(source).unwrap()
  let inspected = inspect_capture_anomalies_v4(history)
  let first = capture_anomalies_v4_json(inspected)
  object_fields_unchecked_v3(first)["findings"] = Json::null()
  object_fields_unchecked_v3(
    object_fields_unchecked_v3(first).at("observations"),
  )["document"] = Json::null()
  let second = capture_anomalies_v4_json(inspected)
  assert_true(!cap034_find(second, "G1a").is_empty())
  assert_eq(
    v4_test_at(second, ["observations", "document"]),
    history_v4_json(history),
  )
}

///|
test "capture034 46 finding survives remaining work budget exhaustion" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"capture-source-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"rollback_ok\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let full = cap034_report(source)
  let max = capture_source_seq_v4(v4_test_at(full, ["execution", "checks"])).to_int()
  let mut observed = false
  for budget in 0..<max {
    let report = cap034_report(source, max_checks=budget)
    if !cap034_find(report, "G1a").is_empty() {
      assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
      assert_eq(v4_test_at(report, ["execution", "limited"]), Json(true))
      observed = true
    }
  }
  assert_true(observed)
}

///|
test "capture034 47 own revoked write base remains gap not dirty update" {
  let report = cap034_report(
    "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"source-edge-hardening\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"savepoint\",\"tx\":\"W\",\"name\":\"repeat\",\"instance\":\"one\"},{\"seq\":4,\"time\":3,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"a\",\"predecessor\":\"x0\"},{\"seq\":5,\"time\":4,\"kind\":\"rollback_to\",\"tx\":\"W\",\"instance\":\"one\"},{\"seq\":6,\"time\":5,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"b\",\"predecessor\":\"a\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"W\"}],\"gaps\":[]}",
  )
  assert_true(cap034_find(report, "dirty-update").is_empty())
  assert_true(cap034_gap(report, "own-revoked-source"))
}

///|
test "capture034 48 separate direct categories never mask each other" {
  let report = cap034_report(
    "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"source-edge-hardening\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"c-A\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"A\",\"key\":\"x\",\"version\":\"a\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"rollback_ok\",\"tx\":\"A\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"a\"},{\"seq\":7,\"time\":6,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\",\"predecessor\":\"a\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}",
  )
  assert_true(!cap034_find(report, "G1a").is_empty())
  assert_true(!cap034_find(report, "dirty-update").is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
}

///|
test "capture034 49 G1b and raw dirty update preserve independent evidence" {
  let report = cap034_report(
    "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"source-edge-hardening\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"a\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"b\",\"predecessor\":\"a\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":7,\"time\":6,\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"c-A\"},{\"seq\":8,\"time\":7,\"kind\":\"write\",\"tx\":\"A\",\"key\":\"x\",\"version\":\"c\",\"predecessor\":\"b\"},{\"seq\":9,\"time\":8,\"kind\":\"rollback_ok\",\"tx\":\"A\"},{\"seq\":10,\"time\":9,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":11,\"time\":10,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"a\"},{\"seq\":12,\"time\":11,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\",\"predecessor\":\"c\"},{\"seq\":13,\"time\":12,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":14,\"time\":13,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}",
  )
  assert_true(!cap034_find(report, "G1b").is_empty())
  assert_true(!cap034_find(report, "dirty-update").is_empty())
}

///|
test "capture034 50 revoked base with unknown enclosing result retains dirty proof and gaps" {
  let report = cap034_report(
    "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"source-edge-hardening\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"c-A\"},{\"seq\":3,\"time\":2,\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"repeat\",\"instance\":\"one\"},{\"seq\":4,\"time\":3,\"kind\":\"write\",\"tx\":\"A\",\"key\":\"x\",\"version\":\"a\",\"predecessor\":\"x0\"},{\"seq\":5,\"time\":4,\"kind\":\"rollback_to\",\"tx\":\"A\",\"instance\":\"one\"},{\"seq\":6,\"time\":5,\"kind\":\"disconnect\",\"tx\":\"A\"},{\"seq\":7,\"time\":6,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":8,\"time\":7,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\",\"predecessor\":\"a\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}",
  )
  assert_true(!cap034_find(report, "dirty-update").is_empty())
  assert_eq(v4_test_at(report, ["coverage", "complete"]), Json(false))
}

///|
test "capture034 51 malformed initial list prefix cannot erase matching aborted element" {
  let report = cap034_report(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"source-edge-hardening\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"initial\",\"value\":\"same\"}]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"c-A\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"rollback_ok\",\"tx\":\"A\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"same\"}]},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}",
  )
  assert_true(!cap034_find(report, "G1a").is_empty())
  assert_true(cap034_find(report, "G1b").is_empty())
  assert_true(cap034_gap(report, "list-complete-version-unproven"))
}

///|
test "capture034 52 rule completion cannot imply INT or isolation acceptance" {
  let report = cap034_report(
    "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"source-edge-hardening\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true}],\"gaps\":[]}",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("checked"))
  assert_eq(
    v4_test_at(report, ["scope", "acceptsIsolationModels"]),
    Json(false),
  )
  let checks = capture_source_array_v4(v4_test_at(report, ["checks"]))
  assert_eq(v4_test_at(checks[3], ["category"]), Json("INT"))
  assert_eq(v4_test_at(checks[3], ["status"]), Json("unsupported"))
}

///|
test "capture034 53 relation observations remain explicitly unsupported" {
  let history = parse_history_v4(
    v4_test_model_complete(RelationSetV4, []).stringify(),
  ).unwrap()
  let report = capture_anomalies_v4_json(inspect_capture_anomalies_v4(history))
  assert_eq(v4_test_at(report, ["status"]), Json("unsupported"))
  assert_eq(v4_test_at(report, ["execution", "checks"]), Json(0))
}
