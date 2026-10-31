///|
fn mwire_report(source : String, options : Json) -> Json raise {
  @json.parse(classify_models_v4_json(source, options.stringify()))
}

///|
test "models wire 01 all fourteen canonical obligations and caller facts cross the independent namespace" {
  let h = mraw_history(mraw_simple())
  let options : Json = {
    "models": "elle-core",
    "clients": [
      { "id": "client-A", "transactions": ["A"] },
      { "id": "client-B", "transactions": ["B"] },
    ],
    "clientsComplete": true,
  }
  let report = mwire_report(h.source_text, options)
  assert_eq(
    capture_source_array_v4(v4_test_at(report, ["models"])).length(),
    14,
  )
  assert_eq(v4_test_at(report, ["status"]), Json("checked-compatible"))
  assert_eq(
    wire034_at(
      verify_model_classification_v4_json(
        h.source_text,
        report.stringify(),
        options.stringify(),
      ),
      ["valid"],
    ),
    Json(true),
  )
  assert_eq(
    wire034_at(
      verify_model_classification_v4_json(
        h.source_text,
        report.stringify(),
        "{}",
      ),
      ["valid"],
    ),
    Json(false),
  )
}

///|
test "models wire 02 default is six and list mapping remains caller opt in" {
  let h = mlp_history(mlp_multi())
  let native = mwire_report(h.source_text, {})
  assert_eq(capture_source_array_v4(v4_test_at(native, ["models"])).length(), 6)
  assert_eq(mct_status(native, ElleSnapshotIsolation), "unknown")
  let options : Json = {
    "models": ["snapshot-isolation"],
    "listProfile": "captured-list-prefix-state/v2",
  }
  let report = mwire_report(h.source_text, options)
  assert_eq(mct_status(report, ElleSnapshotIsolation), "checked-compatible")
  assert_eq(
    wire034_at(
      verify_model_classification_v4_json(
        h.source_text,
        report.stringify(),
        options.stringify(),
      ),
      ["valid"],
    ),
    Json(true),
  )
  assert_eq(
    wire034_at(
      verify_model_classification_v4_json(
        h.source_text,
        report.stringify(),
        "{}",
      ),
      ["valid"],
    ),
    Json(false),
  )
}

///|
test "models wire 03 strict canonical names duplicate decoded keys and bounds are enforced" {
  let h = mraw_history(mraw_simple())
  for
    options in [
      "{\"models\":[\"PL-1\"]}", "{\"models\":[\"serializable\",\"serializable\"]}",
      "{\"models\":[],\"maxStates\":0}", "{\"maxStates\":100001}", "{\"maxSourceChecks\":-1}",
      "{\"clientsComplete\":1}", "{\"listProfile\":\"legacy\"}", "{\"models\":\"elle-core\",\"mo\u0064els\":[\"serializable\"]}",
      "{\"maxAttempts\":1}", "{\"models\":14}",
    ] {
    assert_eq(
      wire034_at(classify_models_v4_json(h.source_text, options), ["status"]),
      Json("invalid"),
      msg=options,
    )
  }
}

///|
test "models wire 04 missing source or independent zero budget cannot acquire completion" {
  let h = mraw_history(mraw_simple(), missing=[3])
  assert_eq(
    mct_status(
      mwire_report(h.source_text, { "models": ["snapshot-isolation"] }),
      ElleSnapshotIsolation,
    ),
    "unknown",
  )
  let full = mraw_history(mraw_simple())
  let options : Json = {
    "models": ["snapshot-isolation"],
    "maxSourceChecks": 0,
  }
  let report = mwire_report(full.source_text, options)
  assert_eq(v4_test_at(report, ["status"]), Json("unknown"))
  assert_eq(
    wire034_at(
      verify_model_classification_v4_json(
        full.source_text,
        report.stringify(),
        options.stringify(),
      ),
      ["valid"],
    ),
    Json(true),
  )
  assert_eq(
    wire034_at(
      verify_model_classification_v4_json(
        full.source_text,
        report.stringify(),
        "{}",
      ),
      ["valid"],
    ),
    Json(false),
  )
}

///|
test "models wire 05 entire report headers proofs budgets and source profiles are verified" {
  let h = mlp_history(mlp_multi())
  let options : Json = {
    "models": ["snapshot-isolation"],
    "listProfile": "captured-list-prefix-state/v2",
  }
  for
    field in [
      "semanticContract", "algorithm", "sourceProfile", "status", "sourceSha256",
    ] {
    let report = mwire_report(h.source_text, options)
    object_fields_unchecked_v3(report)[field] = Json("tampered")
    assert_eq(
      wire034_at(
        verify_model_classification_v4_json(
          h.source_text,
          report.stringify(),
          options.stringify(),
        ),
        ["valid"],
      ),
      Json(false),
    )
  }
  let report = mwire_report(h.source_text, options)
  object_fields_unchecked_v3(v4_test_at(report, ["options"]))["maxSourceChecksPerModule"] = Json(
    999999,
  )
  assert_eq(
    wire034_at(
      verify_model_classification_v4_json(
        h.source_text,
        report.stringify(),
        options.stringify(),
      ),
      ["valid"],
    ),
    Json(false),
  )
}

///|
test "models wire 06 logical clients bind original transaction identity and cannot be pool labels" {
  let h = mraw_history(mraw_simple())
  let choices : Array[Json] = [
    { "clients": [{ "id": "one", "transactions": ["missing"] }] },
    {
      "clients": [
        { "id": "one", "transactions": ["A"] },
        { "id": "two", "transactions": ["A"] },
      ],
    },
    {
      "clients": [{ "id": "one", "transactions": ["A"], "connection": "pool" }],
    },
  ]
  for options in choices {
    assert_eq(
      v4_test_at(mwire_report(h.source_text, options), ["status"]),
      Json("invalid"),
    )
  }
}

///|
test "models wire 07 same external reread remains RC compatible without a snapshot oracle veto" {
  let body = [
    leg_test_begin("R"),
    leg_test_read("R", []),
    leg_test_begin("W"),
    leg_test_append("W", "a"),
  ]
  leg_test_commit(body, "W")
  body.push(leg_test_read("R", ["a"]))
  leg_test_commit(body, "R")
  let h = mlp_history(body)
  let report = mwire_report(h.source_text, {
    "models": ["read-committed", "snapshot-isolation"],
    "listProfile": "captured-list-prefix-state/v2",
  })
  assert_eq(mct_status(report, ElleReadCommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleSnapshotIsolation), "refuted")
}

///|
test "models wire 08 given logical snapshot assertions never become observation completion" {
  let h = mraw_history(mraw_simple())
  let report = mwire_report(h.source_text, {
    "models": ["snapshot-isolation"],
    "completionPolicy": "given-logical-snapshot-assertions/unsupported",
  })
  assert_eq(v4_test_at(report, ["status"]), Json("unknown"))
}
