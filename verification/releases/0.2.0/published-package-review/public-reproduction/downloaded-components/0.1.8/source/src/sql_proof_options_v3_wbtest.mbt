///|
fn v3_test_sql_options() -> String {
  "{\"sqlProof\":\"dislock-f9946f0-sql-proof-1\"}"
}

///|
test "v3 SQL proof is explicit and leaves the original conservative default intact" {
  let trace = d3_test_fixture()
  let text = trace.stringify()
  let legacy = @json.parse(normalize_capture_v3_json(text))
  let explicit = @json.parse(
    normalize_capture_v3_options_json(text, v3_test_sql_options()),
  )
  assert_eq(capture_field(legacy, "status"), "inconclusive".to_json())
  assert_eq(capture_field(legacy, "algorithm"), "v3-lifecycle-1".to_json())
  assert_true(!object_fields_unchecked_v3(legacy).contains("sqlProof"))
  assert_eq(capture_field(explicit, "status"), "ready".to_json())
  assert_eq(
    capture_field(explicit, "algorithm"),
    "v3-lifecycle-sql-1".to_json(),
  )
  assert_eq(
    capture_field(explicit, "observations"),
    capture_field(trace, "events"),
  )
  assert_eq(
    capture_field(capture_field(explicit, "sqlProof"), "profileEvidence"),
    capture_field(trace, "sqlProfiles"),
  )
  assert_eq(trace.stringify(), text)
}

///|
test "v3 analysis records the chosen SQL policy and verifies the whole report" {
  let text = d3_test_fixture().stringify()
  let report = v3_analysis(text, v3_test_sql_options())
  assert_eq(capture_field(report, "status"), "consistent".to_json())
  assert_eq(capture_field(report, "algorithm"), "v3-register-sql-1".to_json())
  assert_eq(
    capture_field(report, "normalized"),
    @json.parse(normalize_capture_v3_options_json(text, v3_test_sql_options())),
  )
  assert_eq(
    capture_field(
      capture_field(capture_field(report, "execution"), "analysisOptions"),
      "sqlProof",
    ),
    "dislock-f9946f0-sql-proof-1".to_json(),
  )
  assert_eq(
    capture_field(
      @json.parse(verify_v3_json(text, report.stringify())),
      "valid",
    ),
    true.to_json(),
  )
}

///|
test "v3 deleting the SQL policy cannot retain its stronger report" {
  let text = d3_test_fixture().stringify()
  let report = v3_analysis(text, v3_test_sql_options())
  object_fields_unchecked_v3(
    capture_field(capture_field(report, "execution"), "analysisOptions"),
  ).remove("sqlProof")
  assert_eq(
    capture_field(
      @json.parse(verify_v3_json(text, report.stringify())),
      "valid",
    ),
    false.to_json(),
  )
}

///|
test "v3 a forged SQL policy is rejected instead of silently falling back" {
  for
    options in [
      "{\"sqlProof\":null}", "{\"sqlProof\":false}", "{\"sqlProof\":1}", "{\"sqlProof\":{}}",
      "{\"sqlProof\":[]}", "{\"sqlProof\":\"unknown\"}",
    ] {
    let text = d3_test_fixture().stringify()
    let normalized = @json.parse(
      normalize_capture_v3_options_json(text, options),
    )
    assert_eq(capture_field(normalized, "status"), "invalid".to_json())
    assert_eq(
      capture_field(@json.parse(analyze_v3_json(text, options)), "status"),
      "invalid".to_json(),
    )
  }
}

///|
test "v3 normalization rejects unrelated or duplicate option keys" {
  let text = d3_test_fixture().stringify()
  for
    options in [
      "{\"maxAttempts\":1}", "{\"sqlProof\":\"dislock-f9946f0-sql-proof-1\",\"unknown\":true}",
      "{\"sqlProof\":\"dislock-f9946f0-sql-proof-1\",\"sqlProof\":\"dislock-f9946f0-sql-proof-1\"}",
    ] {
    assert_eq(
      capture_field(
        @json.parse(normalize_capture_v3_options_json(text, options)),
        "status",
      ),
      "invalid".to_json(),
    )
  }
}

///|
test "v3 the register SQL policy cannot be mixed into a list model" {
  let trace : Json = {
    "traceSchema": 3,
    "dataModel": "append-list-v1",
    "clockDomain": "list",
    "scope": { "exclusiveWriters": true },
    "gaps": [],
    "events": [
      {
        "seq": 1,
        "time": 0,
        "kind": "snapshot",
        "consistent": true,
        "initial": { "x": [] },
      },
    ],
  }
  assert_eq(
    capture_field(
      @json.parse(normalize_capture_v3_json(trace.stringify())),
      "status",
    ),
    "ready".to_json(),
  )
  assert_eq(
    capture_field(
      @json.parse(
        normalize_capture_v3_options_json(
          trace.stringify(),
          v3_test_sql_options(),
        ),
      ),
      "status",
    ),
    "invalid".to_json(),
  )
  assert_eq(
    capture_field(
      @json.parse(analyze_v3_json(trace.stringify(), v3_test_sql_options())),
      "status",
    ),
    "invalid".to_json(),
  )
}

///|
test "v3 verified SQL does not erase an explicitly incomplete snapshot" {
  let trace = d3_test_fixture()
  d3_test_set(trace, ["events", 0, "consistent"], false.to_json())
  let report = v3_analysis(trace.stringify(), v3_test_sql_options())
  assert_eq(capture_field(report, "status"), "inconclusive".to_json())
  assert_eq(capture_field(report, "evidence"), Json::null())
  assert_eq(
    capture_field(capture_field(report, "normalized"), "history"),
    Json::null(),
  )
}

///|
test "v3 explicit SQL never hides an unproven writer scope" {
  let trace = d3_test_fixture()
  d3_test_set(trace, ["scope", "exclusiveWriters"], false.to_json())
  let report = v3_analysis(trace.stringify(), v3_test_sql_options())
  assert_eq(capture_field(report, "status"), "inconclusive".to_json())
  assert_eq(
    capture_field(capture_field(report, "coverage"), "complete"),
    false.to_json(),
  )
}

///|
test "v3 analysis keeps the SQL policy separate from numeric budgets" {
  let options = "{\"sqlProof\":\"dislock-f9946f0-sql-proof-1\",\"maxAttempts\":0,\"maxOperationChecks\":0,\"maxCachedStates\":0}"
  let report = v3_analysis(d3_test_fixture().stringify(), options)
  let recorded = capture_field(
    capture_field(report, "execution"),
    "analysisOptions",
  )
  assert_eq(capture_field(recorded, "maxAttempts"), (0).to_json())
  assert_eq(capture_field(recorded, "maxOperationChecks"), (0).to_json())
  assert_eq(capture_field(recorded, "maxCachedStates"), (0).to_json())
  assert_eq(
    capture_field(recorded, "sqlProof"),
    "dislock-f9946f0-sql-proof-1".to_json(),
  )
  assert_eq(
    capture_field(
      @json.parse(
        verify_v3_json(d3_test_fixture().stringify(), report.stringify()),
      ),
      "valid",
    ),
    true.to_json(),
  )
}

///|
test "v3 SQL reduction prunes only deleted transaction effect ledger facts" {
  let trace = d3_test_fixture()
  let original = trace.stringify()
  let (reduced, _) = v3_without_transaction(trace, "A", prune_sql_ledger=true)
  let profiles = v3_test_items(reduced, "sqlProfiles")
  assert_eq(v3_test_items(profiles[0], "effectLedger").length(), 0)
  assert_eq(
    capture_field(profiles[0], "metadata"),
    capture_field(v3_test_items(trace, "sqlProfiles")[0], "metadata"),
  )
  assert_eq(
    capture_field(profiles[0], "initialState"),
    capture_field(v3_test_items(trace, "sqlProfiles")[0], "initialState"),
  )
  assert_eq(trace.stringify(), original)
  assert_eq(
    capture_field(
      v3_analysis(reduced.stringify(), v3_test_sql_options()),
      "status",
    ),
    "consistent".to_json(),
  )
}

///|
test "v3 legacy transaction deletion keeps its original ledger behavior" {
  let trace = d3_test_fixture()
  let (reduced, _) = v3_without_transaction(trace, "A")
  assert_eq(
    capture_field(reduced, "sqlProfiles"),
    capture_field(trace, "sqlProfiles"),
  )
}

///|
test "v3 reducing a consistent SQL capture is not a counterexample" {
  let result = @json.parse(
    reduce_v3_json(
      d3_test_fixture().stringify(),
      "{\"analysisOptions\":{\"sqlProof\":\"dislock-f9946f0-sql-proof-1\"}}",
    ),
  )
  assert_eq(capture_field(result, "status"), "not-violation".to_json())
  assert_eq(capture_field(result, "oneMinimal"), false.to_json())
  assert_eq(
    capture_field(capture_field(result, "report"), "status"),
    "consistent".to_json(),
  )
}
