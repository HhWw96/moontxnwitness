///|
// Independent six-transaction source counterexample: A-rw-B-ww-C-ww-F-ww-A.
// The source is copied verbatim from the frozen audit input, not a model verdict.
fn classification_implication_trace() -> Json raise {
  @json.parse(
    "{\n  \"traceSchema\": 3,\n  \"clockDomain\": \"independent-implication-boundary-20261024\",\n  \"scope\": {\n    \"exclusiveWriters\": true\n  },\n  \"events\": [\n    {\n      \"seq\": 1,\n      \"time\": 0,\n      \"kind\": \"snapshot\",\n      \"initial\": {\n        \"a-bc\": \"a-bc-initial\",\n        \"b-bd\": \"b-bd-initial\",\n        \"c-be\": \"c-be-initial\",\n        \"d-cf\": \"d-cf-initial\",\n        \"e-fa\": \"e-fa-initial\",\n        \"x\": \"0.2.0\"\n      },\n      \"consistent\": true\n    },\n    {\n      \"seq\": 2,\n      \"time\": 1,\n      \"kind\": \"begin\",\n      \"tx\": \"A\",\n      \"connection\": \"connection-A\"\n    },\n    {\n      \"seq\": 3,\n      \"time\": 2,\n      \"kind\": \"begin\",\n      \"tx\": \"B\",\n      \"connection\": \"connection-B\"\n    },\n    {\n      \"seq\": 4,\n      \"time\": 3,\n      \"kind\": \"begin\",\n      \"tx\": \"C\",\n      \"connection\": \"connection-C\"\n    },\n    {\n      \"seq\": 5,\n      \"time\": 4,\n      \"kind\": \"begin\",\n      \"tx\": \"D\",\n      \"connection\": \"connection-D\"\n    },\n    {\n      \"seq\": 6,\n      \"time\": 5,\n      \"kind\": \"begin\",\n      \"tx\": \"E\",\n      \"connection\": \"connection-E\"\n    },\n    {\n      \"seq\": 7,\n      \"time\": 6,\n      \"kind\": \"begin\",\n      \"tx\": \"F\",\n      \"connection\": \"connection-F\"\n    },\n    {\n      \"seq\": 8,\n      \"time\": 7,\n      \"kind\": \"write\",\n      \"tx\": \"B\",\n      \"key\": \"a-bc\",\n      \"version\": \"B-bc\",\n      \"predecessor\": \"a-bc-initial\"\n    },\n    {\n      \"seq\": 9,\n      \"time\": 8,\n      \"kind\": \"write\",\n      \"tx\": \"B\",\n      \"key\": \"b-bd\",\n      \"version\": \"B-bd\",\n      \"predecessor\": \"b-bd-initial\"\n    },\n    {\n      \"seq\": 10,\n      \"time\": 9,\n      \"kind\": \"write\",\n      \"tx\": \"B\",\n      \"key\": \"c-be\",\n      \"version\": \"B-be\",\n      \"predecessor\": \"c-be-initial\"\n    },\n    {\n      \"seq\": 11,\n      \"time\": 10,\n      \"kind\": \"write\",\n      \"tx\": \"B\",\n      \"key\": \"x\",\n      \"version\": \"B-x\",\n      \"predecessor\": \"0.2.0\"\n    },\n    {\n      \"seq\": 12,\n      \"time\": 11,\n      \"kind\": \"write\",\n      \"tx\": \"C\",\n      \"key\": \"a-bc\",\n      \"version\": \"C-bc\",\n      \"predecessor\": \"B-bc\"\n    },\n    {\n      \"seq\": 13,\n      \"time\": 12,\n      \"kind\": \"write\",\n      \"tx\": \"C\",\n      \"key\": \"d-cf\",\n      \"version\": \"C-cf\",\n      \"predecessor\": \"d-cf-initial\"\n    },\n    {\n      \"seq\": 14,\n      \"time\": 13,\n      \"kind\": \"write\",\n      \"tx\": \"D\",\n      \"key\": \"b-bd\",\n      \"version\": \"D-bd\",\n      \"predecessor\": \"B-bd\"\n    },\n    {\n      \"seq\": 15,\n      \"time\": 14,\n      \"kind\": \"write\",\n      \"tx\": \"E\",\n      \"key\": \"c-be\",\n      \"version\": \"E-be\",\n      \"predecessor\": \"B-be\"\n    },\n    {\n      \"seq\": 16,\n      \"time\": 15,\n      \"kind\": \"write\",\n      \"tx\": \"F\",\n      \"key\": \"d-cf\",\n      \"version\": \"F-cf\",\n      \"predecessor\": \"C-cf\"\n    },\n    {\n      \"seq\": 17,\n      \"time\": 16,\n      \"kind\": \"write\",\n      \"tx\": \"F\",\n      \"key\": \"e-fa\",\n      \"version\": \"F-fa\",\n      \"predecessor\": \"e-fa-initial\"\n    },\n    {\n      \"seq\": 18,\n      \"time\": 17,\n      \"kind\": \"write\",\n      \"tx\": \"A\",\n      \"key\": \"e-fa\",\n      \"version\": \"A-fa\",\n      \"predecessor\": \"F-fa\"\n    },\n    {\n      \"seq\": 19,\n      \"time\": 18,\n      \"kind\": \"read\",\n      \"tx\": \"A\",\n      \"key\": \"x\",\n      \"version\": \"0.2.0\"\n    },\n    {\n      \"seq\": 20,\n      \"time\": 19,\n      \"kind\": \"commit_request\",\n      \"tx\": \"A\"\n    },\n    {\n      \"seq\": 21,\n      \"time\": 20,\n      \"kind\": \"commit_ok\",\n      \"tx\": \"A\"\n    },\n    {\n      \"seq\": 22,\n      \"time\": 21,\n      \"kind\": \"commit_request\",\n      \"tx\": \"B\"\n    },\n    {\n      \"seq\": 23,\n      \"time\": 22,\n      \"kind\": \"commit_ok\",\n      \"tx\": \"B\"\n    },\n    {\n      \"seq\": 24,\n      \"time\": 23,\n      \"kind\": \"commit_request\",\n      \"tx\": \"C\"\n    },\n    {\n      \"seq\": 25,\n      \"time\": 24,\n      \"kind\": \"commit_ok\",\n      \"tx\": \"C\"\n    },\n    {\n      \"seq\": 26,\n      \"time\": 25,\n      \"kind\": \"commit_request\",\n      \"tx\": \"D\"\n    },\n    {\n      \"seq\": 27,\n      \"time\": 26,\n      \"kind\": \"commit_ok\",\n      \"tx\": \"D\"\n    },\n    {\n      \"seq\": 28,\n      \"time\": 27,\n      \"kind\": \"commit_request\",\n      \"tx\": \"E\"\n    },\n    {\n      \"seq\": 29,\n      \"time\": 28,\n      \"kind\": \"commit_ok\",\n      \"tx\": \"E\"\n    },\n    {\n      \"seq\": 30,\n      \"time\": 29,\n      \"kind\": \"commit_request\",\n      \"tx\": \"F\"\n    },\n    {\n      \"seq\": 31,\n      \"time\": 30,\n      \"kind\": \"commit_ok\",\n      \"tx\": \"F\"\n    }\n  ],\n  \"gaps\": []\n}\n",
  )
}

///|
fn classification_implication_report(
  models : Array[String],
  states : Int32,
  edges : Int32,
) -> Json raise {
  classification26_test_report(
    classification_implication_trace(),
    options=(
      {
        "models": Json(models),
        "maxStates": Json(states),
        "maxEdgeChecks": Json(edges),
      } : Json).stringify(),
  )
}

///|
fn classification_implication_assert(
  report : Json,
  model_name : String,
) -> Unit raise {
  let own = classification_test_rule(report, "G2-item")
  assert_eq(capture_field(own, "status"), Json("unknown"))
  assert_eq(capture_field(own, "states"), Json(3))
  assert_eq(capture_field(own, "edgeChecks"), Json(10))
  assert_eq(capture_field(own, "evidence"), Json::null())
  let source = classification_test_rule(report, "G-nonadjacent")
  assert_eq(capture_field(source, "status"), Json("refuted"))
  assert_true(capture_field(source, "evidence") != Json::null())
  let model = classification26_test_model(report, model_name)
  assert_eq(capture_field(model, "status"), Json("refuted"))
  assert_eq(capture_field(model, "refutedBy"), Json(["G-nonadjacent"]))
  assert_true(v3_test_items(model, "incompleteRules").contains(Json("G2-item")))
  let proof = v3_test_items(model, "refutationWitnesses").filter(p => {
      capture_field(p, "requiredRule") == Json("G2-item")
    })[0]
  assert_eq(capture_field(proof, "provedBy"), Json("G-nonadjacent"))
  assert_eq(capture_field(proof, "specificAnomaly"), Json("G-nonadjacent-item"))
  assert_eq(
    capture_field(proof, "sourceEvidencePath"),
    Json(["rules", "G-nonadjacent", "evidence"]),
  )
  assert_eq(capture_field(proof, "requiredRuleStatus"), Json("unknown"))
}

///|
test "classification implication PL3 uses a proved nonadjacent witness without completing G2 search" {
  classification_implication_assert(
    classification_implication_report(["adya-pl-3-v1"], 3, 100),
    "adya-pl-3-v1",
  )
}

///|
test "classification implication repeatable item model uses the same reliable source proof" {
  classification_implication_assert(
    classification_implication_report(["adya-pl-2.99-v1"], 3, 100),
    "adya-pl-2.99-v1",
  )
}

///|
test "classification implication strict model can refute on an ordinary proof without intervals" {
  classification_implication_assert(
    classification_implication_report(["strict-pl-ss-v1"], 3, 100),
    "strict-pl-ss-v1",
  )
}

///|
test "classification implication multiple models preserve independent statuses and direct SI proof" {
  let report = classification_implication_report(
    ["adya-pl-3-v1", "adya-pl-2.99-v1", "elle-generalized-si-v1"],
    3,
    100,
  )
  classification_implication_assert(report, "adya-pl-3-v1")
  classification_implication_assert(report, "adya-pl-2.99-v1")
  let si = classification26_test_model(report, "elle-generalized-si-v1")
  assert_eq(capture_field(si, "status"), Json("refuted"))
  assert_eq(capture_field(si, "refutedBy"), Json(["G-nonadjacent"]))
}

///|
test "classification implication no state budget cannot invent a refutation" {
  let report = classification_implication_report(["adya-pl-3-v1"], 0, 100)
  let model = classification26_test_model(report, "adya-pl-3-v1")
  assert_eq(capture_field(model, "status"), Json("inconclusive"))
  assert_true(v3_test_items(model, "refutationWitnesses").is_empty())
}

///|
test "classification implication no edge budget cannot invent a refutation" {
  let report = classification_implication_report(["adya-pl-3-v1"], 100, 0)
  let model = classification26_test_model(report, "adya-pl-3-v1")
  assert_eq(capture_field(model, "status"), Json("inconclusive"))
  assert_true(v3_test_items(model, "refutationWitnesses").is_empty())
}

///|
test "classification implication G0 keeps its specific label and original evidence path" {
  let report = classification26_test_report(
    classification_test_cycle_trace("G0"),
  )
  let model = classification26_test_model(report, "adya-pl-2-v1")
  assert_eq(capture_field(model, "refutedBy"), Json(["G0"]))
  for proof in v3_test_items(model, "refutationWitnesses") {
    assert_eq(capture_field(proof, "specificAnomaly"), Json("G0"))
    assert_eq(capture_field(proof, "provedBy"), Json("G0"))
    assert_eq(
      capture_field(proof, "sourceEvidencePath"),
      Json(["rules", "G0", "evidence"]),
    )
  }
}

///|
test "classification implication RT cycle is not an ordinary item cycle proof" {
  let rules : Map[String, Json] = Map([])
  rules["G2-item"] = classification_models_v3_rule(
    "unknown",
    "limited",
    Json::null(),
  )
  rules["SSG2-item"] = classification_models_v3_rule("refuted", "complete", {
    "specificCategory": "real-time-cycle",
    "edges": [1],
  })
  assert_eq(classification_models_v3_refutation_witness(rules, "G2-item"), None)
}

///|
test "classification implication refuted status without evidence is not proof" {
  let rules : Map[String, Json] = Map([])
  rules["G2-item"] = classification_models_v3_rule(
    "unknown",
    "limited",
    Json::null(),
  )
  rules["G-nonadjacent"] = classification_models_v3_rule(
    "refuted",
    "complete",
    Json::null(),
  )
  assert_eq(classification_models_v3_refutation_witness(rules, "G2-item"), None)
}
