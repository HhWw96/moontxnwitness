///|
fn int034_report(source : String, max_checks~ : Int32 = 1000000) -> Json {
  internal_consistency_v4_json(
    inspect_internal_consistency_v4(
      parse_history_v4(source).unwrap(),
      max_checks~,
    ),
  )
}

///|
fn int034_findings(report : Json) -> Array[Json] {
  match object_fields_unchecked_v3(report).at("findings") {
    Array(items) => items
    _ => []
  }
}

///|
fn int034_gap(report : Json, code : String) -> Bool {
  let fields = object_fields_unchecked_v3(
    object_fields_unchecked_v3(report).at("coverage"),
  )
  match fields.at("gaps") {
    Array(items) =>
      items.any(item => {
        object_fields_unchecked_v3(item).at("code") == Json(code)
      })
    _ => false
  }
}

///|
test "internal034 01 external read own write own read rollback restores external base" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"savepoint\",\"tx\":\"R\",\"name\":\"s\",\"instance\":\"one\"},{\"seq\":5,\"time\":4,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\",\"predecessor\":\"x0\"},{\"seq\":6,\"time\":5,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\"},{\"seq\":7,\"time\":6,\"kind\":\"rollback_to\",\"tx\":\"R\",\"instance\":\"one\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("checked"))
}

///|
test "internal034 02 own at delivery before rollback does not invent external base" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"savepoint\",\"tx\":\"R\",\"name\":\"s\",\"instance\":\"one\"},{\"seq\":4,\"time\":3,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\",\"predecessor\":\"x0\"},{\"seq\":5,\"time\":4,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\"},{\"seq\":6,\"time\":5,\"kind\":\"rollback_to\",\"tx\":\"R\",\"instance\":\"one\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
}

///|
test "internal034 03 no prior base write rollback first external read is legal" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"savepoint\",\"tx\":\"R\",\"name\":\"s\",\"instance\":\"one\"},{\"seq\":4,\"time\":3,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\",\"predecessor\":\"x0\"},{\"seq\":5,\"time\":4,\"kind\":\"rollback_to\",\"tx\":\"R\",\"instance\":\"one\"},{\"seq\":6,\"time\":5,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
}

///|
test "internal034 04 external read in rolled back scope persists for later INT" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"savepoint\",\"tx\":\"R\",\"name\":\"s\",\"instance\":\"one\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":9,\"time\":8,\"kind\":\"rollback_to\",\"tx\":\"R\",\"instance\":\"one\"},{\"seq\":10,\"time\":9,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":11,\"time\":10,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":12,\"time\":11,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(!int034_findings(report).is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
}

///|
test "internal034 05 own later revoked write was effective when read delivered" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"savepoint\",\"tx\":\"R\",\"name\":\"s\",\"instance\":\"one\"},{\"seq\":4,\"time\":3,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\",\"predecessor\":\"x0\"},{\"seq\":5,\"time\":4,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":6,\"time\":5,\"kind\":\"rollback_to\",\"tx\":\"R\",\"instance\":\"one\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(!int034_findings(report).is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
}

///|
test "internal034 06 nearest own write must match read" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(!int034_findings(report).is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
}

///|
test "internal034 07 matching own intermediate reads before later writes are legal" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\"},{\"seq\":5,\"time\":4,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r2\",\"predecessor\":\"r1\"},{\"seq\":6,\"time\":5,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r2\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
}

///|
test "internal034 08 overwritten own identity is INT not external intermediate rule" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r2\",\"predecessor\":\"r1\"},{\"seq\":5,\"time\":4,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(!int034_findings(report).is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
}

///|
test "internal034 09 external repeated same identity remains compatible" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
}

///|
test "internal034 10 changed external reads are formal INT without PG assertion" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(!int034_findings(report).is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
  assert_eq(
    v4_test_at(report, ["scope", "databaseProductIsolationLevelAsserted"]),
    Json(false),
  )
  assert_eq(
    v4_test_at(report, ["scope", "acceptsIsolationModels"]),
    Json(false),
  )
}

///|
test "internal034 11 first witness endpoints survive later base updates" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":9,\"time\":8,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":11,\"time\":10,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(!int034_findings(report).is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
  assert_eq(int034_findings(report).length(), 1)
  let proof = int034_findings(report)[0]
  assert_eq(v4_test_at(proof, ["evidence", "expected", "identity"]), Json("x0"))
  assert_eq(
    v4_test_at(proof, ["evidence", "expected", "actualIdentity"]),
    Json("w1"),
  )
  assert_eq(
    v4_test_at(proof, ["evidence", "expected", "observation", "eventSeq"]),
    Json(7),
  )
  assert_eq(
    v4_test_at(proof, ["evidence", "actualObservation", "eventSeq"]),
    Json(8),
  )
}

///|
test "internal034 12 nested repeated names restore correct overlay instances" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"savepoint\",\"tx\":\"R\",\"name\":\"same\",\"instance\":\"outer\"},{\"seq\":5,\"time\":4,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\",\"predecessor\":\"x0\"},{\"seq\":6,\"time\":5,\"kind\":\"savepoint\",\"tx\":\"R\",\"name\":\"same\",\"instance\":\"inner\"},{\"seq\":7,\"time\":6,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r2\",\"predecessor\":\"r1\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r2\"},{\"seq\":9,\"time\":8,\"kind\":\"rollback_to\",\"tx\":\"R\",\"instance\":\"inner\"},{\"seq\":10,\"time\":9,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\"},{\"seq\":11,\"time\":10,\"kind\":\"release\",\"tx\":\"R\",\"instance\":\"inner\"},{\"seq\":12,\"time\":11,\"kind\":\"rollback_to\",\"tx\":\"R\",\"instance\":\"outer\"},{\"seq\":13,\"time\":12,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":14,\"time\":13,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":15,\"time\":14,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
}

///|
test "internal034 13 inner rollback cannot erase outer surviving own write" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"savepoint\",\"tx\":\"R\",\"name\":\"same\",\"instance\":\"outer\"},{\"seq\":5,\"time\":4,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\",\"predecessor\":\"x0\"},{\"seq\":6,\"time\":5,\"kind\":\"savepoint\",\"tx\":\"R\",\"name\":\"same\",\"instance\":\"inner\"},{\"seq\":7,\"time\":6,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r2\",\"predecessor\":\"r1\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r2\"},{\"seq\":9,\"time\":8,\"kind\":\"rollback_to\",\"tx\":\"R\",\"instance\":\"inner\"},{\"seq\":10,\"time\":9,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":11,\"time\":10,\"kind\":\"release\",\"tx\":\"R\",\"instance\":\"inner\"},{\"seq\":12,\"time\":11,\"kind\":\"rollback_to\",\"tx\":\"R\",\"instance\":\"outer\"},{\"seq\":13,\"time\":12,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":14,\"time\":13,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":15,\"time\":14,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(!int034_findings(report).is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
}

///|
test "internal034 14 release retains own effect until real commit" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"savepoint\",\"tx\":\"R\",\"name\":\"s\",\"instance\":\"one\"},{\"seq\":4,\"time\":3,\"kind\":\"write\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\",\"predecessor\":\"x0\"},{\"seq\":5,\"time\":4,\"kind\":\"release\",\"tx\":\"R\",\"instance\":\"one\"},{\"seq\":6,\"time\":5,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"r1\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
}

///|
test "internal034 15 new transaction retry identity has a fresh base" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R1\",\"connection\":\"c-R1\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"R1\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_request\",\"tx\":\"R1\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_ok\",\"tx\":\"R1\"},{\"seq\":10,\"time\":9,\"kind\":\"begin\",\"tx\":\"R2\",\"connection\":\"c-R2\"},{\"seq\":11,\"time\":10,\"kind\":\"read\",\"tx\":\"R2\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":12,\"time\":11,\"kind\":\"commit_request\",\"tx\":\"R2\"},{\"seq\":13,\"time\":12,\"kind\":\"commit_ok\",\"tx\":\"R2\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
}

///|
test "internal034 16 aborted observer is outside committed INT rule" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":9,\"time\":8,\"kind\":\"rollback_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
}

///|
test "internal034 17 unknown observer remains gap not committed INT" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":9,\"time\":8,\"kind\":\"disconnect\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
  assert_true(int034_gap(report, "unknown-observer-outcome"))
}

///|
test "internal034 18 missing identity cannot create a false witness" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"missing\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
  assert_true(int034_gap(report, "missing-source"))
}

///|
test "internal034 19 later client source observation is not future-read evidence" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":4,\"time\":3,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":5,\"time\":4,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":6,\"time\":5,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
  assert_true(int034_gap(report, "source-not-observed-before-read"))
}

///|
test "internal034 20 other key source gap does not mask reliable INT" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\",\"y\":\"y0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"y\",\"version\":\"missing\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":9,\"time\":8,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":11,\"time\":10,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(!int034_findings(report).is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
  assert_true(int034_gap(report, "missing-source"))
  assert_eq(v4_test_at(report, ["coverage", "complete"]), Json(false))
}

///|
test "internal034 21 unknown unrelated transaction does not mask reliable INT" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"U\",\"connection\":\"c-U\"},{\"seq\":7,\"time\":6,\"kind\":\"disconnect\",\"tx\":\"U\"},{\"seq\":8,\"time\":7,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":9,\"time\":8,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":10,\"time\":9,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":11,\"time\":10,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":12,\"time\":11,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(!int034_findings(report).is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
  assert_eq(v4_test_at(report, ["coverage", "complete"]), Json(false))
}

///|
test "internal034 22 generic missing program segment cannot invent proof across omitted writes" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[{\"code\":\"missing_segment\",\"message\":\"Transaction steps may be missing\"}]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
  assert_true(int034_gap(report, "transaction-program-coverage-unproven"))
}

///|
test "internal034 23 unproved SQL may hide own writes and must remain gap" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":8,\"time\":7,\"kind\":\"statement\",\"tx\":\"R\",\"sql\":\"UPDATE arbitrary SET data=1\"},{\"seq\":9,\"time\":8,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":11,\"time\":10,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
  assert_true(int034_gap(report, "transaction-program-coverage-unproven"))
}

///|
test "internal034 24 first list read validates unknown prefix own suffix" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"p\",\"value\":\"same\"}]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"R\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"},{\"id\":\"a\",\"value\":\"same\"}]},{\"seq\":5,\"time\":4,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
}

///|
test "internal034 25 own at delivery full value strips suffix before rollback" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"p\",\"value\":\"same\"}]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"savepoint\",\"tx\":\"R\",\"name\":\"s\",\"instance\":\"one\"},{\"seq\":4,\"time\":3,\"kind\":\"append\",\"tx\":\"R\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":5,\"time\":4,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"},{\"id\":\"a\",\"value\":\"same\"}]},{\"seq\":6,\"time\":5,\"kind\":\"rollback_to\",\"tx\":\"R\",\"instance\":\"one\"},{\"seq\":7,\"time\":6,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"}]},{\"seq\":8,\"time\":7,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("checked"))
}

///|
test "internal034 26 no observed base append rollback permits first full read" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"p\",\"value\":\"same\"}]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"savepoint\",\"tx\":\"R\",\"name\":\"s\",\"instance\":\"one\"},{\"seq\":4,\"time\":3,\"kind\":\"append\",\"tx\":\"R\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":5,\"time\":4,\"kind\":\"rollback_to\",\"tx\":\"R\",\"instance\":\"one\"},{\"seq\":6,\"time\":5,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"}]},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
}

///|
test "internal034 27 external full base plus own append survives matching reads and undo" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"p\",\"value\":\"same\"}]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"}]},{\"seq\":4,\"time\":3,\"kind\":\"savepoint\",\"tx\":\"R\",\"name\":\"s\",\"instance\":\"one\"},{\"seq\":5,\"time\":4,\"kind\":\"append\",\"tx\":\"R\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":6,\"time\":5,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"},{\"id\":\"a\",\"value\":\"same\"}]},{\"seq\":7,\"time\":6,\"kind\":\"rollback_to\",\"tx\":\"R\",\"instance\":\"one\"},{\"seq\":8,\"time\":7,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"}]},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
}

///|
test "internal034 28 own append later revoked still constrains earlier read" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"p\",\"value\":\"same\"}]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"savepoint\",\"tx\":\"R\",\"name\":\"s\",\"instance\":\"one\"},{\"seq\":4,\"time\":3,\"kind\":\"append\",\"tx\":\"R\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":5,\"time\":4,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"}]},{\"seq\":6,\"time\":5,\"kind\":\"rollback_to\",\"tx\":\"R\",\"instance\":\"one\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(!int034_findings(report).is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
}

///|
test "internal034 29 list read before next own append is not internal anomaly" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"p\",\"value\":\"same\"}]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"R\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"},{\"id\":\"a\",\"value\":\"same\"}]},{\"seq\":5,\"time\":4,\"kind\":\"append\",\"tx\":\"R\",\"key\":\"x\",\"id\":\"b\",\"value\":\"same\"},{\"seq\":6,\"time\":5,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"},{\"id\":\"a\",\"value\":\"same\"},{\"id\":\"b\",\"value\":\"same\"}]},{\"seq\":7,\"time\":6,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
}

///|
test "internal034 30 list nested undo uses actual instance not repeated name" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"p\",\"value\":\"same\"}]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"}]},{\"seq\":4,\"time\":3,\"kind\":\"savepoint\",\"tx\":\"R\",\"name\":\"same\",\"instance\":\"outer\"},{\"seq\":5,\"time\":4,\"kind\":\"append\",\"tx\":\"R\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":6,\"time\":5,\"kind\":\"savepoint\",\"tx\":\"R\",\"name\":\"same\",\"instance\":\"inner\"},{\"seq\":7,\"time\":6,\"kind\":\"append\",\"tx\":\"R\",\"key\":\"x\",\"id\":\"b\",\"value\":\"same\"},{\"seq\":8,\"time\":7,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"},{\"id\":\"a\",\"value\":\"same\"},{\"id\":\"b\",\"value\":\"same\"}]},{\"seq\":9,\"time\":8,\"kind\":\"rollback_to\",\"tx\":\"R\",\"instance\":\"inner\"},{\"seq\":10,\"time\":9,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"},{\"id\":\"a\",\"value\":\"same\"}]},{\"seq\":11,\"time\":10,\"kind\":\"release\",\"tx\":\"R\",\"instance\":\"inner\"},{\"seq\":12,\"time\":11,\"kind\":\"rollback_to\",\"tx\":\"R\",\"instance\":\"outer\"},{\"seq\":13,\"time\":12,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"}]},{\"seq\":14,\"time\":13,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":15,\"time\":14,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
}

///|
test "internal034 31 same displayed values do not substitute different identities" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"p\",\"value\":\"same\"}]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"b\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"append\",\"tx\":\"R\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":8,\"time\":7,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"},{\"id\":\"b\",\"value\":\"same\"}]},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(!int034_findings(report).is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
}

///|
test "internal034 32 unknown prefix means suffix rather than whole first value" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"p\",\"value\":\"same\"}]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"q\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"append\",\"tx\":\"R\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":8,\"time\":7,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"},{\"id\":\"q\",\"value\":\"same\"},{\"id\":\"a\",\"value\":\"same\"}]},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
}

///|
test "internal034 33 mismatching own suffix proves INT with unknown prefix" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"p\",\"value\":\"same\"}]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"b\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"append\",\"tx\":\"R\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":8,\"time\":7,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"},{\"id\":\"b\",\"value\":\"same\"}]},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(!int034_findings(report).is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
}

///|
test "internal034 34 full list base forbids subsequent changed external value" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"p\",\"value\":\"same\"}]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"b\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"}]},{\"seq\":8,\"time\":7,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"},{\"id\":\"b\",\"value\":\"same\"}]},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(!int034_findings(report).is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
}

///|
test "internal034 35 missing list identity remains source gap" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"p\",\"value\":\"same\"}]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"R\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"},{\"id\":\"missing\",\"value\":\"same\"}]},{\"seq\":5,\"time\":4,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
  assert_true(int034_gap(report, "missing-source"))
}

///|
test "internal034 36 known identity with conflicting value remains gap" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"p\",\"value\":\"same\"}]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"R\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"},{\"id\":\"a\",\"value\":\"different\"}]},{\"seq\":5,\"time\":4,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
  assert_true(int034_gap(report, "identity-value-conflict"))
}

///|
test "internal034 37 duplicate list identity does not create alleged INT proof" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"p\",\"value\":\"same\"}]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"R\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"},{\"id\":\"a\",\"value\":\"same\"},{\"id\":\"a\",\"value\":\"same\"}]},{\"seq\":5,\"time\":4,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":6,\"time\":5,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
  assert_true(int034_gap(report, "duplicate-observed-identity"))
}

///|
test "internal034 38 empty initial list establishes complete empty external base" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":3,\"time\":2,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[]},{\"seq\":4,\"time\":3,\"kind\":\"append\",\"tx\":\"R\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":5,\"time\":4,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"a\",\"value\":\"same\"}]},{\"seq\":6,\"time\":5,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":7,\"time\":6,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
}

///|
test "internal034 39 legal delimiter keys and transaction names stay independent" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x|y\":\"x|0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"x|y\",\"connection\":\"c-x|y\"},{\"seq\":3,\"time\":2,\"kind\":\"read\",\"tx\":\"x|y\",\"key\":\"x|y\",\"version\":\"x|0\"},{\"seq\":4,\"time\":3,\"kind\":\"savepoint\",\"tx\":\"x|y\",\"name\":\"s\",\"instance\":\"one\"},{\"seq\":5,\"time\":4,\"kind\":\"write\",\"tx\":\"x|y\",\"key\":\"x|y\",\"version\":\"x|1\",\"predecessor\":\"x|0\"},{\"seq\":6,\"time\":5,\"kind\":\"read\",\"tx\":\"x|y\",\"key\":\"x|y\",\"version\":\"x|1\"},{\"seq\":7,\"time\":6,\"kind\":\"rollback_to\",\"tx\":\"x|y\",\"instance\":\"one\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"x|y\",\"key\":\"x|y\",\"version\":\"x|0\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_request\",\"tx\":\"x|y\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_ok\",\"tx\":\"x|y\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(int034_findings(report).is_empty())
}

///|
test "internal034 40 proved INT survives unknown gap saturation" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\",\"y\":\"y0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"U\",\"connection\":\"c-U\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-0\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-1\"},{\"seq\":9,\"time\":8,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-2\"},{\"seq\":10,\"time\":9,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-3\"},{\"seq\":11,\"time\":10,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-4\"},{\"seq\":12,\"time\":11,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-5\"},{\"seq\":13,\"time\":12,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-6\"},{\"seq\":14,\"time\":13,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-7\"},{\"seq\":15,\"time\":14,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-8\"},{\"seq\":16,\"time\":15,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-9\"},{\"seq\":17,\"time\":16,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-10\"},{\"seq\":18,\"time\":17,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-11\"},{\"seq\":19,\"time\":18,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-12\"},{\"seq\":20,\"time\":19,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-13\"},{\"seq\":21,\"time\":20,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-14\"},{\"seq\":22,\"time\":21,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-15\"},{\"seq\":23,\"time\":22,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-16\"},{\"seq\":24,\"time\":23,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-17\"},{\"seq\":25,\"time\":24,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-18\"},{\"seq\":26,\"time\":25,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-19\"},{\"seq\":27,\"time\":26,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-20\"},{\"seq\":28,\"time\":27,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-21\"},{\"seq\":29,\"time\":28,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-22\"},{\"seq\":30,\"time\":29,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-23\"},{\"seq\":31,\"time\":30,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-24\"},{\"seq\":32,\"time\":31,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-25\"},{\"seq\":33,\"time\":32,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-26\"},{\"seq\":34,\"time\":33,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-27\"},{\"seq\":35,\"time\":34,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-28\"},{\"seq\":36,\"time\":35,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-29\"},{\"seq\":37,\"time\":36,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-30\"},{\"seq\":38,\"time\":37,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-31\"},{\"seq\":39,\"time\":38,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-32\"},{\"seq\":40,\"time\":39,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-33\"},{\"seq\":41,\"time\":40,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-34\"},{\"seq\":42,\"time\":41,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-35\"},{\"seq\":43,\"time\":42,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-36\"},{\"seq\":44,\"time\":43,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-37\"},{\"seq\":45,\"time\":44,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-38\"},{\"seq\":46,\"time\":45,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-39\"},{\"seq\":47,\"time\":46,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-40\"},{\"seq\":48,\"time\":47,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-41\"},{\"seq\":49,\"time\":48,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-42\"},{\"seq\":50,\"time\":49,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-43\"},{\"seq\":51,\"time\":50,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-44\"},{\"seq\":52,\"time\":51,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-45\"},{\"seq\":53,\"time\":52,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-46\"},{\"seq\":54,\"time\":53,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-47\"},{\"seq\":55,\"time\":54,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-48\"},{\"seq\":56,\"time\":55,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-49\"},{\"seq\":57,\"time\":56,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-50\"},{\"seq\":58,\"time\":57,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-51\"},{\"seq\":59,\"time\":58,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-52\"},{\"seq\":60,\"time\":59,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-53\"},{\"seq\":61,\"time\":60,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-54\"},{\"seq\":62,\"time\":61,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-55\"},{\"seq\":63,\"time\":62,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-56\"},{\"seq\":64,\"time\":63,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-57\"},{\"seq\":65,\"time\":64,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-58\"},{\"seq\":66,\"time\":65,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-59\"},{\"seq\":67,\"time\":66,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-60\"},{\"seq\":68,\"time\":67,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-61\"},{\"seq\":69,\"time\":68,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-62\"},{\"seq\":70,\"time\":69,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-63\"},{\"seq\":71,\"time\":70,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-64\"},{\"seq\":72,\"time\":71,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-65\"},{\"seq\":73,\"time\":72,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-66\"},{\"seq\":74,\"time\":73,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-67\"},{\"seq\":75,\"time\":74,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-68\"},{\"seq\":76,\"time\":75,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-69\"},{\"seq\":77,\"time\":76,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-70\"},{\"seq\":78,\"time\":77,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-71\"},{\"seq\":79,\"time\":78,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-72\"},{\"seq\":80,\"time\":79,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-73\"},{\"seq\":81,\"time\":80,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-74\"},{\"seq\":82,\"time\":81,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-75\"},{\"seq\":83,\"time\":82,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-76\"},{\"seq\":84,\"time\":83,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-77\"},{\"seq\":85,\"time\":84,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-78\"},{\"seq\":86,\"time\":85,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-79\"},{\"seq\":87,\"time\":86,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-80\"},{\"seq\":88,\"time\":87,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-81\"},{\"seq\":89,\"time\":88,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-82\"},{\"seq\":90,\"time\":89,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-83\"},{\"seq\":91,\"time\":90,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-84\"},{\"seq\":92,\"time\":91,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-85\"},{\"seq\":93,\"time\":92,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-86\"},{\"seq\":94,\"time\":93,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-87\"},{\"seq\":95,\"time\":94,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-88\"},{\"seq\":96,\"time\":95,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-89\"},{\"seq\":97,\"time\":96,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-90\"},{\"seq\":98,\"time\":97,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-91\"},{\"seq\":99,\"time\":98,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-92\"},{\"seq\":100,\"time\":99,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-93\"},{\"seq\":101,\"time\":100,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-94\"},{\"seq\":102,\"time\":101,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-95\"},{\"seq\":103,\"time\":102,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-96\"},{\"seq\":104,\"time\":103,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-97\"},{\"seq\":105,\"time\":104,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-98\"},{\"seq\":106,\"time\":105,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-99\"},{\"seq\":107,\"time\":106,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-100\"},{\"seq\":108,\"time\":107,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-101\"},{\"seq\":109,\"time\":108,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-102\"},{\"seq\":110,\"time\":109,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-103\"},{\"seq\":111,\"time\":110,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-104\"},{\"seq\":112,\"time\":111,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-105\"},{\"seq\":113,\"time\":112,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-106\"},{\"seq\":114,\"time\":113,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-107\"},{\"seq\":115,\"time\":114,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-108\"},{\"seq\":116,\"time\":115,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-109\"},{\"seq\":117,\"time\":116,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-110\"},{\"seq\":118,\"time\":117,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-111\"},{\"seq\":119,\"time\":118,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-112\"},{\"seq\":120,\"time\":119,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-113\"},{\"seq\":121,\"time\":120,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-114\"},{\"seq\":122,\"time\":121,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-115\"},{\"seq\":123,\"time\":122,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-116\"},{\"seq\":124,\"time\":123,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-117\"},{\"seq\":125,\"time\":124,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-118\"},{\"seq\":126,\"time\":125,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-119\"},{\"seq\":127,\"time\":126,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-120\"},{\"seq\":128,\"time\":127,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-121\"},{\"seq\":129,\"time\":128,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-122\"},{\"seq\":130,\"time\":129,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-123\"},{\"seq\":131,\"time\":130,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-124\"},{\"seq\":132,\"time\":131,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-125\"},{\"seq\":133,\"time\":132,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-126\"},{\"seq\":134,\"time\":133,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-127\"},{\"seq\":135,\"time\":134,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-128\"},{\"seq\":136,\"time\":135,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-129\"},{\"seq\":137,\"time\":136,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-130\"},{\"seq\":138,\"time\":137,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-131\"},{\"seq\":139,\"time\":138,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-132\"},{\"seq\":140,\"time\":139,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-133\"},{\"seq\":141,\"time\":140,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-134\"},{\"seq\":142,\"time\":141,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-135\"},{\"seq\":143,\"time\":142,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-136\"},{\"seq\":144,\"time\":143,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-137\"},{\"seq\":145,\"time\":144,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-138\"},{\"seq\":146,\"time\":145,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-139\"},{\"seq\":147,\"time\":146,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-140\"},{\"seq\":148,\"time\":147,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-141\"},{\"seq\":149,\"time\":148,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-142\"},{\"seq\":150,\"time\":149,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-143\"},{\"seq\":151,\"time\":150,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-144\"},{\"seq\":152,\"time\":151,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-145\"},{\"seq\":153,\"time\":152,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-146\"},{\"seq\":154,\"time\":153,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-147\"},{\"seq\":155,\"time\":154,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-148\"},{\"seq\":156,\"time\":155,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-149\"},{\"seq\":157,\"time\":156,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-150\"},{\"seq\":158,\"time\":157,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-151\"},{\"seq\":159,\"time\":158,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-152\"},{\"seq\":160,\"time\":159,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-153\"},{\"seq\":161,\"time\":160,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-154\"},{\"seq\":162,\"time\":161,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-155\"},{\"seq\":163,\"time\":162,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-156\"},{\"seq\":164,\"time\":163,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-157\"},{\"seq\":165,\"time\":164,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-158\"},{\"seq\":166,\"time\":165,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-159\"},{\"seq\":167,\"time\":166,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-160\"},{\"seq\":168,\"time\":167,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-161\"},{\"seq\":169,\"time\":168,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-162\"},{\"seq\":170,\"time\":169,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-163\"},{\"seq\":171,\"time\":170,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-164\"},{\"seq\":172,\"time\":171,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-165\"},{\"seq\":173,\"time\":172,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-166\"},{\"seq\":174,\"time\":173,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-167\"},{\"seq\":175,\"time\":174,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-168\"},{\"seq\":176,\"time\":175,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-169\"},{\"seq\":177,\"time\":176,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-170\"},{\"seq\":178,\"time\":177,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-171\"},{\"seq\":179,\"time\":178,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-172\"},{\"seq\":180,\"time\":179,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-173\"},{\"seq\":181,\"time\":180,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-174\"},{\"seq\":182,\"time\":181,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-175\"},{\"seq\":183,\"time\":182,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-176\"},{\"seq\":184,\"time\":183,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-177\"},{\"seq\":185,\"time\":184,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-178\"},{\"seq\":186,\"time\":185,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-179\"},{\"seq\":187,\"time\":186,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-180\"},{\"seq\":188,\"time\":187,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-181\"},{\"seq\":189,\"time\":188,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-182\"},{\"seq\":190,\"time\":189,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-183\"},{\"seq\":191,\"time\":190,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-184\"},{\"seq\":192,\"time\":191,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-185\"},{\"seq\":193,\"time\":192,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-186\"},{\"seq\":194,\"time\":193,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-187\"},{\"seq\":195,\"time\":194,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-188\"},{\"seq\":196,\"time\":195,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-189\"},{\"seq\":197,\"time\":196,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-190\"},{\"seq\":198,\"time\":197,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-191\"},{\"seq\":199,\"time\":198,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-192\"},{\"seq\":200,\"time\":199,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-193\"},{\"seq\":201,\"time\":200,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-194\"},{\"seq\":202,\"time\":201,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-195\"},{\"seq\":203,\"time\":202,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-196\"},{\"seq\":204,\"time\":203,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-197\"},{\"seq\":205,\"time\":204,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-198\"},{\"seq\":206,\"time\":205,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-199\"},{\"seq\":207,\"time\":206,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-200\"},{\"seq\":208,\"time\":207,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-201\"},{\"seq\":209,\"time\":208,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-202\"},{\"seq\":210,\"time\":209,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-203\"},{\"seq\":211,\"time\":210,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-204\"},{\"seq\":212,\"time\":211,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-205\"},{\"seq\":213,\"time\":212,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-206\"},{\"seq\":214,\"time\":213,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-207\"},{\"seq\":215,\"time\":214,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-208\"},{\"seq\":216,\"time\":215,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-209\"},{\"seq\":217,\"time\":216,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-210\"},{\"seq\":218,\"time\":217,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-211\"},{\"seq\":219,\"time\":218,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-212\"},{\"seq\":220,\"time\":219,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-213\"},{\"seq\":221,\"time\":220,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-214\"},{\"seq\":222,\"time\":221,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-215\"},{\"seq\":223,\"time\":222,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-216\"},{\"seq\":224,\"time\":223,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-217\"},{\"seq\":225,\"time\":224,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-218\"},{\"seq\":226,\"time\":225,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-219\"},{\"seq\":227,\"time\":226,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-220\"},{\"seq\":228,\"time\":227,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-221\"},{\"seq\":229,\"time\":228,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-222\"},{\"seq\":230,\"time\":229,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-223\"},{\"seq\":231,\"time\":230,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-224\"},{\"seq\":232,\"time\":231,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-225\"},{\"seq\":233,\"time\":232,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-226\"},{\"seq\":234,\"time\":233,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-227\"},{\"seq\":235,\"time\":234,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-228\"},{\"seq\":236,\"time\":235,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-229\"},{\"seq\":237,\"time\":236,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-230\"},{\"seq\":238,\"time\":237,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-231\"},{\"seq\":239,\"time\":238,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-232\"},{\"seq\":240,\"time\":239,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-233\"},{\"seq\":241,\"time\":240,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-234\"},{\"seq\":242,\"time\":241,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-235\"},{\"seq\":243,\"time\":242,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-236\"},{\"seq\":244,\"time\":243,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-237\"},{\"seq\":245,\"time\":244,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-238\"},{\"seq\":246,\"time\":245,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-239\"},{\"seq\":247,\"time\":246,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-240\"},{\"seq\":248,\"time\":247,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-241\"},{\"seq\":249,\"time\":248,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-242\"},{\"seq\":250,\"time\":249,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-243\"},{\"seq\":251,\"time\":250,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-244\"},{\"seq\":252,\"time\":251,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-245\"},{\"seq\":253,\"time\":252,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-246\"},{\"seq\":254,\"time\":253,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-247\"},{\"seq\":255,\"time\":254,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-248\"},{\"seq\":256,\"time\":255,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-249\"},{\"seq\":257,\"time\":256,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-250\"},{\"seq\":258,\"time\":257,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-251\"},{\"seq\":259,\"time\":258,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-252\"},{\"seq\":260,\"time\":259,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-253\"},{\"seq\":261,\"time\":260,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-254\"},{\"seq\":262,\"time\":261,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-255\"},{\"seq\":263,\"time\":262,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-256\"},{\"seq\":264,\"time\":263,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-257\"},{\"seq\":265,\"time\":264,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-258\"},{\"seq\":266,\"time\":265,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-259\"},{\"seq\":267,\"time\":266,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-260\"},{\"seq\":268,\"time\":267,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-261\"},{\"seq\":269,\"time\":268,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-262\"},{\"seq\":270,\"time\":269,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-263\"},{\"seq\":271,\"time\":270,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-264\"},{\"seq\":272,\"time\":271,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-265\"},{\"seq\":273,\"time\":272,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-266\"},{\"seq\":274,\"time\":273,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-267\"},{\"seq\":275,\"time\":274,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-268\"},{\"seq\":276,\"time\":275,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-269\"},{\"seq\":277,\"time\":276,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-270\"},{\"seq\":278,\"time\":277,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-271\"},{\"seq\":279,\"time\":278,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-272\"},{\"seq\":280,\"time\":279,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-273\"},{\"seq\":281,\"time\":280,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-274\"},{\"seq\":282,\"time\":281,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-275\"},{\"seq\":283,\"time\":282,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-276\"},{\"seq\":284,\"time\":283,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-277\"},{\"seq\":285,\"time\":284,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-278\"},{\"seq\":286,\"time\":285,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-279\"},{\"seq\":287,\"time\":286,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-280\"},{\"seq\":288,\"time\":287,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-281\"},{\"seq\":289,\"time\":288,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-282\"},{\"seq\":290,\"time\":289,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-283\"},{\"seq\":291,\"time\":290,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-284\"},{\"seq\":292,\"time\":291,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-285\"},{\"seq\":293,\"time\":292,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-286\"},{\"seq\":294,\"time\":293,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-287\"},{\"seq\":295,\"time\":294,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-288\"},{\"seq\":296,\"time\":295,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-289\"},{\"seq\":297,\"time\":296,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-290\"},{\"seq\":298,\"time\":297,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-291\"},{\"seq\":299,\"time\":298,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-292\"},{\"seq\":300,\"time\":299,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-293\"},{\"seq\":301,\"time\":300,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-294\"},{\"seq\":302,\"time\":301,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-295\"},{\"seq\":303,\"time\":302,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-296\"},{\"seq\":304,\"time\":303,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-297\"},{\"seq\":305,\"time\":304,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-298\"},{\"seq\":306,\"time\":305,\"kind\":\"read\",\"tx\":\"U\",\"key\":\"y\",\"version\":\"missing-299\"},{\"seq\":307,\"time\":306,\"kind\":\"commit_request\",\"tx\":\"U\"},{\"seq\":308,\"time\":307,\"kind\":\"commit_ok\",\"tx\":\"U\"},{\"seq\":309,\"time\":308,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":310,\"time\":309,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":311,\"time\":310,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":312,\"time\":311,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":313,\"time\":312,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let report = int034_report(source)
  assert_true(!int034_findings(report).is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
  assert_eq(v4_test_at(report, ["coverage", "findingsTruncated"]), Json(true))
  assert_eq(v4_test_at(report, ["coverage", "complete"]), Json(false))
}

///|
test "internal034 41 zero exact and one-short budgets stay explicit" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true}],\"gaps\":[]}"
  let zero = int034_report(source, max_checks=0)
  assert_eq(v4_test_at(zero, ["execution", "checks"]), Json(0))
  assert_eq(v4_test_at(zero, ["execution", "limited"]), Json(true))
  let exact = int034_report(source, max_checks=4)
  assert_eq(v4_test_at(exact, ["status"]), Json("checked"))
  assert_eq(v4_test_at(exact, ["execution", "limited"]), Json(false))
  assert_eq(
    v4_test_at(int034_report(source, max_checks=3), ["status"]),
    Json("unknown"),
  )
}

///|
test "internal034 42 invalid budgets grant no work" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true}],\"gaps\":[]}"
  for maximum in [-1, 1000001] {
    let report = int034_report(source, max_checks=maximum)
    assert_eq(v4_test_at(report, ["status"]), Json("invalid-budget"))
    assert_eq(v4_test_at(report, ["execution", "checks"]), Json(0))
  }
}

///|
test "internal034 43 verifier uses independent caller budget" {
  let history = parse_history_v4(
    "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":9,\"time\":8,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":11,\"time\":10,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}",
  ).unwrap()
  let normal = internal_consistency_v4_json(
    inspect_internal_consistency_v4(history),
  )
  assert_true(verify_internal_consistency_v4(history, normal))
  let limited = internal_consistency_v4_json(
    inspect_internal_consistency_v4(history, max_checks=0),
  )
  assert_false(verify_internal_consistency_v4(history, limited))
  assert_true(verify_internal_consistency_v4(history, limited, max_checks=0))
}

///|
test "internal034 44 report definition algorithm budget and evidence tampering rejected" {
  let history = parse_history_v4(
    "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":9,\"time\":8,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":11,\"time\":10,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}",
  ).unwrap()
  for
    field in [
      "semanticContract", "algorithm", "profile", "definition", "findings", "observations",
      "scope", "execution",
    ] {
    let report = internal_consistency_v4_json(
      inspect_internal_consistency_v4(history),
    )
    object_fields_unchecked_v3(report)[field] = Json("forged")
    assert_false(verify_internal_consistency_v4(history, report))
  }
}

///|
test "internal034 45 getter detaches original source and proof" {
  let history = parse_history_v4(
    "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":9,\"time\":8,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":11,\"time\":10,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}",
  ).unwrap()
  let checked = inspect_internal_consistency_v4(history)
  let exposed = internal_consistency_v4_json(checked)
  object_fields_unchecked_v3(exposed)["findings"] = Json::null()
  object_fields_unchecked_v3(
    object_fields_unchecked_v3(exposed).at("observations"),
  )["document"] = Json::null()
  let report = internal_consistency_v4_json(checked)
  assert_true(!int034_findings(report).is_empty())
  assert_eq(
    v4_test_at(report, ["observations", "document"]),
    history_v4_json(history),
  )
  assert_true(verify_internal_consistency_v4(history, report))
}

///|
test "internal034 46 proof is retained when later work exhausts budget" {
  let source = "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-state-tests\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":9,\"time\":8,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":11,\"time\":10,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}"
  let full = int034_report(source)
  let maximum = internal_seq_v4(v4_test_at(full, ["execution", "checks"])).to_int()
  let mut observed = false
  for budget in 0..<maximum {
    let report = int034_report(source, max_checks=budget)
    if !int034_findings(report).is_empty() {
      assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
      assert_eq(v4_test_at(report, ["execution", "limited"]), Json(true))
      observed = true
    }
  }
  assert_true(observed)
}

///|
test "internal034 47 declared register and relation inputs remain unsupported" {
  let declared = parse_history_v4(
    "{\"schemaVersion\":1,\"model\":\"serializable\",\"initial\":{\"x\":\"x0\"},\"transactions\":[]}",
  ).unwrap()
  assert_eq(
    v4_test_at(
      internal_consistency_v4_json(inspect_internal_consistency_v4(declared)),
      ["status"],
    ),
    Json("unsupported"),
  )
  let relation = parse_history_v4(
    v4_test_model_complete(RelationSetV4, []).stringify(),
  ).unwrap()
  assert_eq(
    v4_test_at(
      internal_consistency_v4_json(inspect_internal_consistency_v4(relation)),
      ["status"],
    ),
    Json("unsupported"),
  )
}

///|
test "internal034 48 later unproved SQL cannot erase an earlier proved INT" {
  let report = int034_report(
    "{\"traceSchema\":3,\"clockDomain\":\"before-unknown-sql\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"w\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"r\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":9,\"time\":8,\"kind\":\"statement\",\"tx\":\"R\",\"sql\":\"SELECT outside_declared_model()\"},{\"seq\":10,\"time\":9,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":11,\"time\":10,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}",
  )
  assert_true(!int034_findings(report).is_empty())
  assert_eq(v4_test_at(report, ["status"]), Json("refuted"))
  assert_eq(v4_test_at(report, ["coverage", "complete"]), Json(false))
}

///|
test "internal034 49 other transaction unproved SQL cannot mask known key INT" {
  let report = int034_report(
    "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-hardening\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"U\",\"connection\":\"c-U\"},{\"seq\":7,\"time\":6,\"kind\":\"statement\",\"tx\":\"U\",\"sql\":\"SELECT outside_model()\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_request\",\"tx\":\"U\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_ok\",\"tx\":\"U\"},{\"seq\":10,\"time\":9,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":11,\"time\":10,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":12,\"time\":11,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":13,\"time\":12,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":14,\"time\":13,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}",
  )
  assert_true(!int034_findings(report).is_empty())
  assert_eq(v4_test_at(report, ["coverage", "complete"]), Json(false))
}

///|
test "internal034 50 known delivered identity can prove INT despite unknown writer outcome" {
  let report = int034_report(
    "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-hardening\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"disconnect\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":8,\"time\":7,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}",
  )
  assert_true(!int034_findings(report).is_empty())
  assert_true(int034_gap(report, "unknown-source-outcome"))
  assert_eq(v4_test_at(report, ["coverage", "complete"]), Json(false))
}

///|
test "internal034 51 list known aborted item does not mask independent own suffix INT" {
  let report = int034_report(
    "{\"traceSchema\":3,\"dataModel\":\"append-list-v1\",\"clockDomain\":\"int-hardening\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":[{\"id\":\"p\",\"value\":\"same\"}]},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"b\",\"value\":\"same\"},{\"seq\":4,\"time\":3,\"kind\":\"rollback_ok\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":6,\"time\":5,\"kind\":\"append\",\"tx\":\"R\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\"},{\"seq\":7,\"time\":6,\"kind\":\"list_read\",\"tx\":\"R\",\"key\":\"x\",\"items\":[{\"id\":\"p\",\"value\":\"same\"},{\"id\":\"b\",\"value\":\"same\"}]},{\"seq\":8,\"time\":7,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":9,\"time\":8,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}",
  )
  assert_true(!int034_findings(report).is_empty())
  assert_eq(v4_test_at(report, ["coverage", "complete"]), Json(false))
}

///|
test "internal034 52 multiple mismatches retain the original first witness" {
  let report = int034_report(
    "{\"traceSchema\":3,\"dataModel\":\"point-register-v1\",\"clockDomain\":\"int-hardening\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"seq\":1,\"time\":0,\"kind\":\"snapshot\",\"initial\":{\"x\":\"x0\"},\"consistent\":true},{\"seq\":2,\"time\":1,\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"c-W\"},{\"seq\":3,\"time\":2,\"kind\":\"write\",\"tx\":\"W\",\"key\":\"x\",\"version\":\"w1\",\"predecessor\":\"x0\"},{\"seq\":4,\"time\":3,\"kind\":\"commit_request\",\"tx\":\"W\"},{\"seq\":5,\"time\":4,\"kind\":\"commit_ok\",\"tx\":\"W\"},{\"seq\":6,\"time\":5,\"kind\":\"begin\",\"tx\":\"R\",\"connection\":\"c-R\"},{\"seq\":7,\"time\":6,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":8,\"time\":7,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":9,\"time\":8,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"x0\"},{\"seq\":10,\"time\":9,\"kind\":\"read\",\"tx\":\"R\",\"key\":\"x\",\"version\":\"w1\"},{\"seq\":11,\"time\":10,\"kind\":\"commit_request\",\"tx\":\"R\"},{\"seq\":12,\"time\":11,\"kind\":\"commit_ok\",\"tx\":\"R\"}],\"gaps\":[]}",
  )
  assert_eq(int034_findings(report).length(), 1)
  assert_eq(
    v4_test_at(int034_findings(report)[0], ["evidence", "expected", "identity"]),
    Json("x0"),
  )
  assert_eq(
    v4_test_at(int034_findings(report)[0], [
      "evidence", "actualObservation", "eventSeq",
    ]),
    Json(8),
  )
}
