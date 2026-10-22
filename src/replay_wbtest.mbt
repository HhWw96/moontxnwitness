///|
fn result_valid(text : String) -> Bool {
  let j = @json.parse(text) catch { _ => return false }
  j is Object(m) && m.get("valid") == Some(true.to_json())
}

///|
test "stable v1 and v2 replay accepts released engines only in supported headers" {
  let h = skew()
  let history = history_json(h).stringify()
  for v2 in [false, true] {
    let report = if v2 {
      analysis_result_json(analyze_with_options(h))
    } else {
      report_json(analyze(h))
    }
    match report {
      Object(fields) => {
        for engine in ["0.1.1", "0.1.2", "0.1.3", "0.1.4", version()] {
          fields["version"] = engine.to_json()
          assert_true(
            result_valid(replay_report_json(history, report.stringify())),
          )
          let original_status = fields.at("status")
          fields["status"] = "consistent".to_json()
          assert_true(
            !result_valid(replay_report_json(history, report.stringify())),
          )
          fields["status"] = original_status
        }
        fields["version"] = "99.0.0".to_json()
        assert_true(
          !result_valid(replay_report_json(history, report.stringify())),
        )
      }
      _ => abort("report object")
    }
  }
}

///|
test "semantic report replay checks a genuine report" {
  let h = skew()
  assert_true(
    result_valid(
      replay_report_json(
        history_json(h).stringify(),
        report_json(analyze(h)).stringify(),
      ),
    ),
  )
}

///|
test "semantic replay rejects altered verdicts and counts" {
  let h = skew()
  let j = report_json(analyze(h))
  match j {
    Object(m) => m["status"] = "consistent".to_json()
    _ => abort("object")
  }
  assert_true(
    !result_valid(
      replay_report_json(history_json(h).stringify(), j.stringify()),
    ),
  )
  let j2 = report_json(analyze(h))
  match j2 {
    Object(m) => m["stats"] = Json::null()
    _ => abort("object")
  }
  assert_true(
    !result_valid(
      replay_report_json(history_json(h).stringify(), j2.stringify()),
    ),
  )
}

///|
test "semantic replay includes exact completion search data" {
  let h = hist([tx("A", [write_op("x", "x1")]), tx("B", [write_op("x", "x2")])])
  assert_true(
    result_valid(
      replay_report_json(
        history_json(h).stringify(),
        report_json(analyze(h)).stringify(),
      ),
    ),
  )
}

///|
test "old cycle evidence remains verifiable under schema v1" {
  let h = skew()
  let j = report_json(analyze(h))
  match j {
    Object(m) => m["version"] = "0.0.1".to_json()
    _ => abort("object")
  }
  assert_true(
    result_valid(
      verify_certificate_json(history_json(h).stringify(), j.stringify()),
    ),
  )
}

///|
test "model comparison isolates a realtime contradiction" {
  let h = hist([
    tx("W", [write_op("x", "x1")], start=Some(1L), end=Some(2L)),
    tx("R", [read_op("x", "x0")], start=Some(3L), end=Some(4L)),
  ])
  let j = compare_models(h)
  assert_true(
    j is Object(m) &&
    m.get("classification") == Some("realtime-only-violation".to_json()),
  )
  assert_true(h.model == Serializable)
}

///|
test "model comparison does not invent missing time intervals" {
  let j = compare_models(hist([tx("T", [])]))
  assert_true(
    j is Object(m) && m.get("classification") == Some("inconclusive".to_json()),
  )
}

///|
test "capsule structure validation does not claim cryptographic verification" {
  let h = skew()
  let j : Json = {
    "format": "moontxnwitness-replay/v1",
    "schemaVersion": 1,
    "tool": "MoonTxnWitness",
    "engineVersion": version().to_json(),
    "historyText": history_json(h).stringify().to_json(),
    "reportText": report_json(analyze(h)).stringify().to_json(),
    "historySha256": "0".repeat(64).to_json(),
    "reportSha256": "0".repeat(64).to_json(),
  }
  let inspected = capsule_content_json(j.stringify())
  assert_true(result_valid(inspected))
  assert_true(inspected.contains("caller must verify both hashes"))
}

///|
test "capsule parser rejects malformed hashes and text" {
  assert_true(!result_valid(capsule_content_json("{}")))
  assert_true(!result_valid(capsule_content_json("{")))
  assert_true(!result_valid(replay_report_json("{}", "{}")))
}
