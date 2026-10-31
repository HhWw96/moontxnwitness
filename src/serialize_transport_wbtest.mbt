///|
// Exactly the original transport construction, used only as a reference oracle.
fn transport_reference038(
  report : Report,
  format : String,
  extras~ : Map[String, Json] = Map([]),
) -> String {
  let structured = report_json(report)
  let fields = object_fields_unchecked_v3(structured)
  for name, value in extras {
    fields[name] = value
  }
  let output = if format == "json" {
    report_string(report, extras~) + "\n"
  } else {
    render_report(report, format)
  }
  (
    {
      "report": structured,
      "output": Json(output),
      "exitCode": Json(exit_code(report.outcome)),
    } : Json).stringify()
}

///|
fn transport_check038(
  report : Report,
  extras~ : Map[String, Json] = Map([]),
) -> Unit raise {
  for
    format in ["json", "text", "markdown", "dot", "unknown-falls-back-to-text"] {
    let actual = report_transport_string(report, format, extras~)
    assert_eq(actual, transport_reference038(report, format, extras~))
    let parsed = @json.parse(actual)
    let structured = report_json(report)
    let fields = object_fields_unchecked_v3(structured)
    for name, value in extras {
      fields[name] = value
    }
    assert_eq(v4_test_at(parsed, ["report"]), structured)
  }
}

///|
test "transport038 01 analyzed positive negative unknown and invalid reports preserve every byte" {
  for
    history in [
      hist([]),
      skew(),
      hist([tx("A", [read_op("x", "missing")])]),
      hist([tx("A", [read_op("x", "x0")], status=Unknown)]),
      hist([tx("A", [write_op("x", "x0")])]),
    ] {
    transport_check038(analyze(history))
  }
}

///|
test "transport038 02 balanced extras keep their position budgets counters and blockers" {
  for history in [skew(), completion_noise(6), hist([])] {
    for attempts in [0, 1, 100000] {
      let result = analyze_with_options(
        history,
        options=analysis_options(max_attempts=attempts, max_cached_states=0),
      )
      transport_check038(result.report, extras=analysis_extras(result))
      let output = @json.parse(
        report_transport_string(
          result.report,
          "json",
          extras=analysis_extras(result),
        ),
      )
      assert_eq(v4_test_at(output, ["report"]), analysis_result_json(result))
    }
  }
}

///|
test "transport038 03 all edge option fields and nonstandard realtime reasons survive" {
  let edges : Array[Edge] = []
  for kind in [WW, WR, RW, RT] {
    edges.push({
      from: "a\"\\🙂",
      to: "b\n\t中",
      kind,
      key: None,
      from_op: None,
      to_op: None,
      from_version: None,
      to_version: None,
      reason: "reason \u0000 \u001f /    ",
    })
    edges.push({
      from: "b\n\t中",
      to: "a\"\\🙂",
      kind,
      key: Some("key/\"\\🙂"),
      from_op: Some(-2147483648),
      to_op: Some(2147483647),
      from_version: Some(""),
      to_version: Some("版本\r\n"),
      reason: "nonstandard RT carries every optional field",
    })
  }
  transport_check038({ ..analyze(hist([])), edges, witness: edges, })
}

///|
test "transport038 04 standard realtime shell keeps full edge evidence" {
  let history = hist(
    [
      tx("A", [], start=Some(0L), end=Some(1L)),
      tx("B", [], start=Some(2L), end=Some(3L)),
    ],
    model=StrictSerializable,
  )
  let report = analyze(history)
  assert_eq(report.edges.length(), 1)
  assert_true(report.edges[0].kind == RT)
  transport_check038(report)
}

///|
test "transport038 05 arbitrary Unicode findings coverage serial order and orders retain official escaping" {
  let key = "键\"\\\t🙂"
  let finding : Finding = {
    code: "custom\u0000",
    severity: "uncertainty",
    message: "正文\n\r\t\"\\ / 🙂 é  ",
    transactions: ["a\"\\中"],
    key: Some(key),
    ops: [0, 2147483647],
  }
  let report : Report = {
    ..analyze(hist([])),
    findings: [finding],
    serial_order: ["a\"\\中", ""],
    transaction_count: 2147483647,
    committed_count: 2,
    operation_count: 3,
    inferred_orders: Map([(key, ["初始", "v\"\\🙂"])]),
    order_sources: Map([(key, "supplied")]),
    coverage: [
      {
        key,
        committed_reads: 7,
        committed_final_writes: 1,
        unresolved_reads: 2,
      },
    ],
    search: {
      status: "custom\"",
      attempts: 19,
      operation_checks: 31,
      reason: "reason\n🙂",
      blockers: [finding],
    },
    graph: {
      analyzed: true,
      components: 5,
      cyclic_components: 2,
      cyclic_transactions: 4,
      bfs_roots: 3,
      edge_budget_exceeded: true,
    },
  }
  transport_check038(report)
}

///|
test "transport038 06 current JSON APIs preserve exact result envelope and presentation newline" {
  for
    source in [
      history_json(skew()).stringify(),
      "{",
      "[]",
      "{\"transactions\":[]}",
    ] {
    let r = match parse_history(source) {
      Ok(h) => analyze(h)
      Err(message) => input_error_report(message)
    }
    for format in ["json", "dot", "markdown", "text"] {
      assert_eq(run_json(source, format), transport_reference038(r, format))
    }
    let balanced = options_input(source, "{}")
    for format in ["json", "dot", "markdown", "text"] {
      assert_eq(
        run_options_json(source, format),
        transport_reference038(
          balanced.report,
          format,
          extras=analysis_extras(balanced),
        ),
      )
    }
  }
}

///|
test "transport038 07 certificate remains independently replayable after transport decoding" {
  let h = skew()
  let text = history_json(h).stringify()
  let transported = @json.parse(run_json(text, "json"))
  let encoded = v4_test_at(transported, ["report"]).stringify()
  assert_true(result_valid(verify_certificate_json(text, encoded)))
  assert_true(result_valid(replay_report_json(text, encoded)))
}

///|
test "transport038 08 quote cache saturation does not change escaped report output" {
  let findings : Array[Finding] = []
  for index in 0..<2200 {
    findings.push({
      code: "code-" + index.to_string(),
      severity: "info",
      message: "消息\"\\🙂-" + index.to_string(),
      transactions: [],
      key: None,
      ops: [],
    })
  }
  let report = { ..analyze(hist([])), findings, }
  transport_check038(report)
}
