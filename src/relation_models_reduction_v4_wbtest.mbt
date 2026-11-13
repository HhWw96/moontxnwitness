///|
fn rmrt_report(
  facts : ModelFactsV4,
  target~ : ElleModelV4 = ElleSerializable,
  max_checks~ : Int32 = 256,
  options~ : ModelOptionsV4 = model_options_v4().unwrap(),
) -> Json {
  relation_model_reduction_v4_json(
    reduce_relation_models_v4(facts, target, options, max_checks~),
  )
}

///|
test "relation model reduction 01 source-closed G2 noise reduces to two and revalidates model" {
  let facts = rmt_facts(rrt_g2_body(noise=2))
  let result = reduce_relation_models_v4(
    facts,
    ElleSerializable,
    model_options_v4().unwrap(),
  )
  let report = relation_model_reduction_v4_json(result)
  assert_eq(v4_capture_transaction_ids(result.facts().history), ["A", "B"])
  assert_eq(capture_field(report, "status"), Json("reduced"))
  assert_eq(capture_field(report, "oneMinimal"), Json(true))
  assert_eq(capture_field(report, "preserveModel"), Json("serializable"))
  assert_eq(
    capture_field(capture_field(report, "classification"), "status"),
    Json("refuted"),
  )
  assert_eq(
    capture_field(capture_field(report, "execution"), "candidateChecks"),
    Json(4),
  )
}

///|
test "relation model reduction 02 zero candidate budget retains and fully rechecks original" {
  let facts = rmt_facts(rrt_g2_body(noise=1))
  let report = rmrt_report(facts, max_checks=0)
  assert_eq(capture_field(report, "status"), Json("budget"))
  assert_eq(capture_field(report, "oneMinimal"), Json(false))
  assert_eq(capture_field(report, "originalFacts"), facts.source_record)
  assert_eq(capture_field(report, "analysisView"), facts.source_record)
  assert_eq(
    capture_field(capture_field(report, "execution"), "candidateChecks"),
    Json(0),
  )
  assert_eq(
    capture_field(capture_field(report, "execution"), "finalRevalidation"),
    Json(true),
  )
  assert_eq(
    capture_field(capture_field(report, "classification"), "status"),
    Json("refuted"),
  )
}

///|
test "relation model reduction 03 exact final single-delete pass may finish at the limit" {
  let report = rmrt_report(rmt_facts(rrt_g2_body(noise=2)), max_checks=4)
  assert_eq(capture_field(report, "oneMinimal"), Json(true))
  assert_eq(
    capture_field(capture_field(report, "execution"), "candidateLimitReached"),
    Json(true),
  )
  assert_eq(
    capture_field(
      capture_field(report, "execution"),
      "candidateBudgetExhausted",
    ),
    Json(false),
  )
}

///|
test "relation model reduction 04 incomplete remaining single-delete pass cannot claim minimality" {
  let report = rmrt_report(rmt_facts(rrt_g2_body(noise=2)), max_checks=3)
  assert_eq(capture_field(report, "status"), Json("budget"))
  assert_eq(capture_field(report, "oneMinimal"), Json(false))
  assert_eq(
    capture_field(capture_field(report, "classification"), "status"),
    Json("refuted"),
  )
}

///|
test "relation model reduction 05 deleting an aborted source is source-open and blocks minimality" {
  let facts = rmt_facts(rcl_direct_body("G1a"))
  let report = rmrt_report(facts, target=ElleReadCommitted)
  assert_eq(capture_field(report, "oneMinimal"), Json(false))
  assert_eq(capture_field(report, "status"), Json("undetermined"))
  assert_eq(
    capture_field(capture_field(report, "classification"), "status"),
    Json("refuted"),
  )
  assert_true(!v3_test_items(report, "unresolvedCandidates").is_empty())
}

///|
test "relation model reduction 06 target RU cannot be replaced with a serializability anomaly" {
  let report = rmrt_report(
    rmt_facts(rrt_g2_body(noise=1)),
    target=ElleReadUncommitted,
  )
  assert_eq(capture_field(report, "status"), Json("not-refuted"))
  assert_eq(
    capture_field(capture_field(report, "execution"), "candidateChecks"),
    Json(0),
  )
  assert_eq(
    capture_field(capture_field(report, "classification"), "status"),
    Json("checked-compatible"),
  )
}

///|
test "relation model reduction 07 selected original events retain exact source seq and fields" {
  let facts = rmt_facts(rrt_g2_body(noise=2))
  let report = rmrt_report(facts)
  assert_eq(capture_field(report, "originalFacts"), facts.source_record)
  let source_events = v3_test_items(facts.history.source_document, "events")
  let selected = v3_test_items(report, "selectedOriginalEvents")
  let origins = v3_test_items(report, "originalEventSequence")
  assert_eq(selected.length(), origins.length())
  for i, event in selected {
    assert_eq(capture_field(event, "seq"), origins[i])
    assert_true(source_events.contains(event))
  }
  let view = model_facts_v4(
    parse_history_v4(
      capture_field(capture_field(report, "analysisView"), "history").stringify(),
    ).unwrap(),
  ).unwrap()
  assert_true(rmr_original_selection_v4(facts.history, view.history, origins))
  let changed = v4_json_copy(view.history.source_document)
  let changed_event = object_fields_unchecked_v3(
    v3_test_items(changed, "events")[1],
  )
  changed_event["time"] = Json(rcl_number(changed_event.at("time")) - 1)
  assert_false(
    rmr_original_selection_v4(
      facts.history,
      parse_history_v4(changed.stringify()).unwrap(),
      origins,
    ),
  )
}

///|
test "relation model reduction 08 original sequence loss is never healed by derived indices" {
  let trace = rpg_trace(rrt_g2_body(noise=1))
  for event in v3_test_items(trace, "events") {
    let fields = object_fields_unchecked_v3(event)
    fields["seq"] = Json(rcl_number(fields.at("seq")) + 1)
  }
  let facts = model_facts_v4(parse_history_v4(trace.stringify()).unwrap()).unwrap()
  let report = rmrt_report(facts)
  assert_eq(
    capture_field(
      capture_field(report, "sourceCoverage"),
      "originalSequenceWindowClosed",
    ),
    Json(false),
  )
  assert_eq(
    capture_field(capture_field(report, "execution"), "candidateChecks"),
    Json(0),
  )
  assert_eq(capture_field(report, "oneMinimal"), Json(false))
}

///|
test "relation model reduction 09 independent target budget source and outcome reject tampering" {
  let facts = rmt_facts(rrt_g2_body(noise=1))
  let options = model_options_v4().unwrap()
  let report = rmrt_report(facts)
  assert_true(
    verify_relation_model_reduction_v4(facts, report, ElleSerializable, options),
  )
  assert_false(
    verify_relation_model_reduction_v4(
      facts,
      report,
      ElleReadCommitted,
      options,
    ),
  )
  assert_false(
    verify_relation_model_reduction_v4(
      facts,
      report,
      ElleSerializable,
      options,
      max_checks=0,
    ),
  )
  assert_false(
    verify_relation_model_reduction_v4(
      rmt_facts(rrt_g2_body(noise=2)),
      report,
      ElleSerializable,
      options,
    ),
  )
  let altered = v4_json_copy(report)
  object_fields_unchecked_v3(altered)["oneMinimal"] = Json(false)
  assert_false(
    verify_relation_model_reduction_v4(
      facts,
      altered,
      ElleSerializable,
      options,
    ),
  )
}

///|
test "relation model reduction 10 client membership projection preserves declared IDs and order" {
  let body = rrt_g2_body(noise=1)
  let facts = rmt_facts(
    body,
    clients=[
      { id: "logical-one", transactions: ["noise-0", "A"], },
      { id: "logical-two", transactions: ["B"], },
    ],
    clients_complete=true,
  )
  let result = reduce_relation_models_v4(
    facts,
    ElleSessionSerializable,
    model_options_v4().unwrap(),
  )
  let report = relation_model_reduction_v4_json(result)
  assert_eq(capture_field(report, "status"), Json("reduced"))
  assert_eq(
    capture_field(result.facts().source_record, "clients"),
    Json([
      ({ "id": "logical-one", "transactions": ["A"] } : Json),
      ({ "id": "logical-two", "transactions": ["B"] } : Json),
    ]),
  )
  assert_eq(
    capture_field(capture_field(report, "originalFacts"), "clients"),
    capture_field(facts.source_record, "clients"),
  )
}

///|
test "relation model reduction 11 invalid candidate budgets and non-relation inputs stay visible" {
  let facts = rmt_facts(rrt_g2_body())
  for maximum in [-1, 257] {
    let report = rmrt_report(facts, max_checks=maximum)
    assert_eq(capture_field(report, "status"), Json("invalid"))
    assert_eq(
      capture_field(capture_field(report, "execution"), "candidateChecks"),
      Json(0),
    )
    assert_eq(capture_field(report, "oneMinimal"), Json(false))
  }
  assert_eq(
    capture_field(rmrt_report(mct_facts(mct_single())), "status"),
    Json("unsupported"),
  )
}

///|
test "relation model reduction 12 graph budget exhaustion cannot count as a negative deletion check" {
  let report = rmrt_report(
    rmt_facts(rrt_g2_body()),
    options=model_options_v4(max_states=0).unwrap(),
  )
  assert_eq(capture_field(report, "status"), Json("unknown"))
  assert_eq(
    capture_field(capture_field(report, "execution"), "candidateChecks"),
    Json(0),
  )
  assert_eq(capture_field(report, "oneMinimal"), Json(false))
}

///|
test "relation model reduction 13 another surviving model witness cannot authorize a source-open deletion" {
  let body = [rpg_begin("P"), rpg_write("P", "3", "p1", Some("z0"))]
  rpg_commit(body, "P")
  body.push(rpg_begin("R"))
  body.push(rpg_read("R", "3", Some("p1")))
  rpg_commit(body, "R")
  for event in rrt_g2_body() {
    body.push(event)
  }
  let facts = rmt_facts(body)
  let report = rmrt_report(facts, max_checks=1)
  let first = v3_test_items(
      capture_field(report, "execution"),
      "candidateAudit",
    )[0]
  assert_eq(capture_field(first, "transaction"), Json("P"))
  assert_eq(capture_field(first, "classificationStatus"), Json("refuted"))
  assert_eq(capture_field(first, "sourceClosed"), Json(false))
  assert_eq(capture_field(first, "accepted"), Json(false))
  assert_true(v3_test_items(report, "removedTransactions").is_empty())
}

///|
test "relation model reduction 14 tampered origin and selected source cannot be repaired by report digests" {
  let facts = rmt_facts(rrt_g2_body(noise=1))
  let options = model_options_v4().unwrap()
  let report = rmrt_report(facts)
  let altered = v4_json_copy(report)
  let selected = v3_test_items(altered, "selectedOriginalEvents")
  object_fields_unchecked_v3(selected[1])["time"] = Json(10000)
  object_fields_unchecked_v3(altered)["sourceSha256"] = Json(
    model_digest_v4(capture_field(altered, "originalFacts")),
  )
  assert_false(
    verify_relation_model_reduction_v4(
      facts,
      altered,
      ElleSerializable,
      options,
    ),
  )
  let changed_mapping = v4_json_copy(report)
  let origins = v3_test_items(changed_mapping, "originalEventSequence")
  origins[1] = origins[0]
  assert_false(
    verify_relation_model_reduction_v4(
      facts,
      changed_mapping,
      ElleSerializable,
      options,
    ),
  )
}

///|
test "relation model reduction 15 unknown real time cannot create a strict refutation to shrink" {
  let facts = rmt_facts(rmt_stale_external())
  let options = model_options_v4().unwrap()
  let result = reduce_relation_models_v4(
    facts,
    ElleStrictSerializable,
    options,
    realtime_known=false,
  )
  let report = relation_model_reduction_v4_json(result)
  assert_eq(capture_field(report, "status"), Json("unknown"))
  assert_eq(
    capture_field(capture_field(report, "execution"), "candidateChecks"),
    Json(0),
  )
  assert_eq(
    capture_field(capture_field(report, "classification"), "status"),
    Json("unknown"),
  )
  assert_true(
    verify_relation_model_reduction_v4(
      facts,
      report,
      ElleStrictSerializable,
      options,
      realtime_known=false,
    ),
  )
  assert_false(
    verify_relation_model_reduction_v4(
      facts,
      report,
      ElleStrictSerializable,
      options,
    ),
  )
}

///|
test "relation model reduction 16 every candidate and final check retains unknown real-time policy" {
  let facts = rmt_facts(rrt_g2_body(noise=1))
  let options = model_options_v4().unwrap()
  let report = relation_model_reduction_v4_json(
    reduce_relation_models_v4(
      facts,
      ElleStrictSerializable,
      options,
      realtime_known=false,
    ),
  )
  assert_eq(capture_field(report, "selectedTransactions"), Json(["A", "B"]))
  assert_eq(capture_field(report, "oneMinimal"), Json(false))
  assert_eq(
    capture_field(report, "sourcePolicy"),
    ({ "realtimeKnown": false } : Json),
  )
  assert_eq(
    capture_field(
      capture_field(report, "initialClassification"),
      "sourcePolicy",
    ),
    ({ "realtimeKnown": false } : Json),
  )
  assert_eq(
    capture_field(capture_field(report, "classification"), "sourcePolicy"),
    ({ "realtimeKnown": false } : Json),
  )
  assert_eq(
    capture_field(capture_field(report, "classification"), "status"),
    Json("refuted"),
  )
  assert_true(
    v3_test_items(capture_field(report, "execution"), "candidateAudit").any(candidate => {
      capture_field(candidate, "classificationStatus") == Json("unknown")
    }),
  )
}
