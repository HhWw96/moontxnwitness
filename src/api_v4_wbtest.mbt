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

///|
test "v033 wire 01 explicit G-single and four categories preserve old default identities" {
  let source = history_json(
    hist(
      [
        tx("A", [read_op("x", "x0"), write_op("x", "x1")]),
        tx("B", [read_op("x", "x0"), write_op("x", "x2")]),
      ],
      orders={ "x": ["x0", "x1", "x2"] },
    ),
  ).stringify()
  let requested = "{\"categories\":[\"G0\",\"G1c\",\"G2-item\",\"G-single\"]}"
  let report = wire_test_json(classify_v4_json(source, requested))
  assert_eq(
    capture_field(report, "algorithm"),
    Json("v4-source-bound-category-g-single-1"),
  )
  assert_eq(
    v4_test_at(report, [
      "judgment", "rules", "G-single", "evidence", "rwEdgeCount",
    ]),
    Json(1),
  )
  assert_eq(
    v4_test_at(
      wire_test_json(
        verify_classification_v4_json(source, report.stringify(), requested),
      ),
      ["valid"],
    ),
    Json(true),
  )
  assert_eq(
    capture_field(wire_test_json(classify_v4_json(source, "{}")), "algorithm"),
    Json("v4-source-bound-category-bfs-1"),
  )
}

///|
test "v033 wire 02 inspection uses explicit independent budget" {
  let source = history_json(
    hist([tx("A", [read_op("x", "x1"), write_op("x", "x1")])]),
  ).stringify()
  let report = inspect_anomalies_v4_json(source, "{}")
  assert_eq(capture_field(wire_test_json(report), "status"), Json("findings"))
  assert_eq(
    v4_test_at(wire_test_json(verify_anomalies_v4_json(source, report, "{}")), [
      "valid",
    ]),
    Json(true),
  )
  assert_eq(
    v4_test_at(
      wire_test_json(
        verify_anomalies_v4_json(source, report, "{\"maxChecks\":0}"),
      ),
      ["valid"],
    ),
    Json(false),
  )
}

///|
test "v033 wire 03 inspection rejects duplicate unknown and over-budget options" {
  let source = history_json(skew()).stringify()
  for
    options in [
      "{\"maxChecks\":1000001}", "{\"maxChecks\":-1}", "{\"maxChecks\":1.5}", "{\"model\":\"serializable\"}",
      "{\"maxChecks\":0,\"maxChecks\":1000000}",
    ] {
    assert_eq(
      capture_field(
        wire_test_json(inspect_anomalies_v4_json(source, options)),
        "status",
      ),
      Json("invalid"),
    )
  }
}

///|
test "v033 wire 04 CLI option guard rejects Unicode-equivalent duplicate keys" {
  assert_eq(
    capture_field(
      wire_test_json(
        options_v4_content_json("{\"maxChecks\":1,\"max\\u0043hecks\":2}"),
      ),
      "status",
    ),
    Json("invalid"),
  )
  assert_eq(
    v4_test_at(wire_test_json(options_v4_content_json("{\"maxChecks\":0}")), [
      "options", "maxChecks",
    ]),
    Json(0),
  )
}

///|
test "v033 wire 05 constructor rejection remains visible instead of an empty diagnosis" {
  let source = v4_test_model_complete(AppendListV4, [
    { "kind": "append", "tx": "A", "key": "x", "id": "same", "value": "first" },
    { "kind": "append", "tx": "A", "key": "x", "id": "same", "value": "second" },
  ]).stringify()
  assert_eq(
    capture_field(
      wire_test_json(inspect_anomalies_v4_json(source, "{}")),
      "status",
    ),
    Json("invalid"),
  )
}
