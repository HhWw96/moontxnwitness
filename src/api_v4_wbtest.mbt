///|
fn wire_test_json(text : String) -> Json {
  @json.parse(text) catch {
    _ => abort("Invalid wire test JSON")
  }
}

///|
test "v4 wire register typed result matches direct analysis" {
  let source = history_json(skew()).stringify()
  let history = parse_history_v4(source).unwrap()
  assert_eq(
    wire_test_json(analyze_v4_json(source, "{}")),
    analysis_v4_json(analyze_v4(history)),
  )
  assert_eq(
    wire_test_json(verify_v4_json(source, analyze_v4_json(source, "{}"), "{}")),
    wire_test_json(wire_v4_verified(true)),
  )
}

///|
test "v4 wire three models roundtrip without text normalization" {
  for
    source in [
      history_json(skew()).stringify(),
      v4_test_model_complete(AppendListV4, [
        { "kind": "append", "tx": "A", "key": "x", "id": "i", "value": "same" },
      ]).stringify(),
      v4_test_model_complete(RelationSetV4, [
        {
          "kind": "row_read",
          "tx": "A",
          "relation": "r",
          "predicate": [],
          "rows": [],
          "complete": true,
        },
      ]).stringify(),
    ] {
    let report = analyze_v4_json(source, "{}")
    assert_eq(
      v4_test_at(wire_test_json(verify_v4_json(source, report, "{}")), ["valid"]),
      Json(true),
    )
    assert_eq(
      v4_test_at(wire_test_json(report), ["observations", "document"]),
      wire_test_json(source),
    )
  }
}

///|
test "v4 wire rejects unknown and overflowing analysis options" {
  let source = history_json(skew()).stringify()
  for
    options in [
      "{\"maxAttempt\":1}", "{\"maxAttempts\":100001}", "{\"maxStates\":-1}", "{\"maxOperationChecks\":1.5}",
      "{\"maxCachedStates\":50001}", "{\"model\":\"serializable\"}", "[]", "null",
      "{\"maxStates\":0,\"maxStates\":1}",
    ] {
    assert_eq(
      v4_test_at(wire_test_json(analyze_v4_json(source, options)), ["status"]),
      Json("invalid"),
    )
  }
}

///|
test "v4 wire verifier uses independent expected budget" {
  let source = history_json(completion_noise(3)).stringify()
  let report = analyze_v4_json(source, "{\"maxAttempts\":0}")
  assert_eq(
    v4_test_at(wire_test_json(report), ["judgment", "status"]),
    Json("inconclusive"),
  )
  assert_eq(
    v4_test_at(wire_test_json(verify_v4_json(source, report, "{}")), ["valid"]),
    Json(false),
  )
  assert_eq(
    v4_test_at(
      wire_test_json(verify_v4_json(source, report, "{\"maxAttempts\":0}")),
      ["valid"],
    ),
    Json(true),
  )
}

///|
test "v4 wire report identity and source tampering rejected" {
  let source = history_json(skew()).stringify()
  for
    path in [
      ["algorithm"],
      ["semanticContract"],
      ["execution", "counterContract"],
      ["observations", "document", "model"],
      ["judgment", "status"],
    ] {
    let report = wire_test_json(analyze_v4_json(source, "{}"))
    v4_test_replace(report, path, Json("tampered"))
    assert_eq(
      v4_test_at(
        wire_test_json(verify_v4_json(source, report.stringify(), "{}")),
        ["valid"],
      ),
      Json(false),
    )
  }
}

///|
test "v4 wire classification rejects unsupported categories and explicit null" {
  let source = history_json(skew()).stringify()
  for
    options in [
      "{\"categories\":[]}", "{\"categories\":[\"G0\",\"G0\"]}", "{\"categories\":[\"G2\"]}",
      "{\"categories\":null}", "{\"maxEdgeChecks\":1000001}", "{\"models\":[\"serializable\"]}",
    ] {
    assert_eq(
      v4_test_at(wire_test_json(classify_v4_json(source, options)), ["status"]),
      Json("invalid"),
    )
  }
}

///|
test "v4 wire classification uses its own caller options" {
  let source = history_json(skew()).stringify()
  let options = "{\"categories\":[\"G2-item\"],\"maxStates\":0}"
  let report = classify_v4_json(source, options)
  assert_eq(
    v4_test_at(
      wire_test_json(verify_classification_v4_json(source, report, options)),
      ["valid"],
    ),
    Json(true),
  )
  assert_eq(
    v4_test_at(
      wire_test_json(verify_classification_v4_json(source, report, "{}")),
      ["valid"],
    ),
    Json(false),
  )
}

///|
test "v4 wire relation classification explicitly unsupported" {
  let source = v4_test_model_complete(RelationSetV4, [
    {
      "kind": "row_read",
      "tx": "A",
      "relation": "r",
      "predicate": [],
      "rows": [],
      "complete": true,
    },
  ]).stringify()
  assert_eq(
    v4_test_at(wire_test_json(classify_v4_json(source, "{}")), [
      "judgment", "status",
    ]),
    Json("unsupported"),
  )
}

///|
test "v4 wire reduction requires an explicit known preservation model" {
  let source = history_json(skew()).stringify()
  for
    options in [
      "{}", "{\"preserve\":\"snapshot-isolation\"}", "{\"preserve\":\"serializable\",\"maxChecks\":257}",
      "{\"preserve\":\"serializable\",\"analysisOptions\":{\"bogus\":0}}",
    ] {
    assert_eq(
      v4_test_at(wire_test_json(reduce_v4_json(source, options)), ["status"]),
      Json("invalid"),
    )
  }
  let options = "{\"preserve\":\"serializable\",\"maxChecks\":0}"
  let report = reduce_v4_json(source, options)
  assert_eq(
    v4_test_at(
      wire_test_json(verify_reduction_v4_json(source, report, options)),
      ["valid"],
    ),
    Json(true),
  )
  assert_eq(
    v4_test_at(
      wire_test_json(
        verify_reduction_v4_json(
          source, report, "{\"preserve\":\"strict-serializable\",\"maxChecks\":0}",
        ),
      ),
      ["valid"],
    ),
    Json(false),
  )
  assert_eq(v4_test_at(wire_test_json(report), ["oneMinimal"]), Json(false))
}

///|
test "v4 wire malformed report and unsupported source remain invalid" {
  let source = history_json(skew()).stringify()
  assert_eq(
    v4_test_at(
      wire_test_json(
        verify_v4_json(
          source, "{\"algorithm\":\"a\",\"algorithm\":\"b\"}", "{}",
        ),
      ),
      ["valid"],
    ),
    Json(false),
  )
  assert_eq(
    v4_test_at(wire_test_json(analyze_v4_json("{\"traceSchema\":4}", "{}")), [
      "status",
    ]),
    Json("invalid"),
  )
}

///|
test "v4 wire capsule duplicate keys rejected before host inspection" {
  assert_eq(
    v4_test_at(
      wire_test_json(
        capsule_v4_content_json(
          "{\"format\":\"moontxnwitness-replay/v4\",\"format\":\"moontxnwitness-replay/v4\"}",
        ),
      ),
      ["status"],
    ),
    Json("invalid"),
  )
}
