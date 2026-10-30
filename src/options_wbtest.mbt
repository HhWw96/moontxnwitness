///|
fn completion_noise(n : Int32) -> History {
  let txs : Array[Transaction] = []
  for i in 0..<(n - 3) {
    txs.push(tx("N" + i.to_string(), [read_op("z", "z0")]))
  }
  txs.push(tx("A", [write_op("x", "x1"), write_op("y", "y1")]))
  txs.push(tx("B", [write_op("x", "x2"), write_op("y", "y2")]))
  txs.push(tx("R", [read_op("x", "x1"), read_op("y", "y2")]))
  { ..hist(txs), initial: Map([("x", "x0"), ("y", "y0"), ("z", "z0")]), }
}

///|
test "balanced cache proves failure with fewer attempts and saturates safely" {
  let h = completion_noise(8)
  let cached = analyze_with_options(h)
  let uncached = analyze_with_options(
    h,
    options=analysis_options(max_cached_states=0),
  )
  let saturated = analyze_with_options(
    h,
    options=analysis_options(max_cached_states=1),
  )
  assert_true(cached.report.outcome == Violation)
  assert_true(uncached.report.outcome == Violation)
  assert_true(saturated.report.outcome == Violation)
  assert_true(cached.cache_hits > 0)
  assert_true(cached.report.search.attempts < uncached.report.search.attempts)
  assert_eq(saturated.cached_states, 1)
}

///|
test "cache distinguishes equal selected sets with different current versions" {
  let h = hist([
    tx("A", [write_op("x", "x1")]),
    tx("B", [write_op("x", "x2"), write_op("y", "y1")]),
    tx("R", [read_op("x", "x1"), read_op("y", "y1")]),
  ])
  let r = analyze_with_options(h).report
  assert_true(r.outcome == Consistent)
  assert_eq(r.serial_order, ["B", "A", "R"])
}

///|
test "balanced supports twelve writers while legacy keeps its size boundary" {
  let h = hist(
    Array::makei(12, i => {
      tx("T" + i.to_string(), [write_op("x", "v" + i.to_string())])
    }),
  )
  assert_true(analyze(h).outcome == Inconclusive)
  let r = analyze_with_options(h).report
  assert_true(r.outcome == Consistent)
  assert_eq(r.serial_order.length(), 12)
  assert_eq(r.order_sources.at("x"), "searched")
}

///|
test "balanced twelve transaction negative proof ignores only read-only noise" {
  let r = analyze_with_options(completion_noise(12))
  assert_true(r.report.outcome == Violation)
  assert_eq(r.report.search.status, "exhausted")
  assert_true(r.cache_hits > 0)
}

///|
test "interrupted search is never cached as exhausted" {
  let h = completion_noise(8)
  for
    options in [
      analysis_options(max_attempts=0),
      analysis_options(max_operation_checks=0),
      analysis_options(max_attempts=1),
    ] {
    let r = analyze_with_options(h, options~)
    assert_true(r.report.outcome == Inconclusive)
    assert_eq(r.report.search.status, "budget")
    assert_eq(r.cached_states, 0)
  }
}

///|
test "finishing exactly at the attempt budget remains an exhaustive result" {
  let h = completion_noise(3)
  let first = analyze_with_options(h)
  let exact = analyze_with_options(
    h,
    options=analysis_options(max_attempts=first.report.search.attempts),
  )
  assert_eq(exact.report.search.status, "exhausted")
  assert_true(exact.report.outcome == Violation)
}

///|
test "v2 serialization matches the structured result and replays" {
  let h = completion_noise(6)
  let r = analyze_with_options(h)
  assert_eq(@json.parse(analysis_result_string(r)), analysis_result_json(r))
  assert_true(
    result_valid(
      replay_report_json(history_json(h).stringify(), analysis_result_string(r)),
    ),
  )
}

///|
test "v2 rejects altered verdict, effective budget, algorithm and version provenance" {
  let h = completion_noise(3)
  let text = history_json(h).stringify()
  for
    (field, replacement) in [
      ("status", Json("consistent")),
      ("algorithm", Json("unknown")),
      ("effectiveLimits", Json::null()),
      ("versionOrderSources", Json::null()),
    ] {
    let j = analysis_result_json(analyze_with_options(h))
    match j {
      Object(m) => m[field] = replacement
      _ => abort("object")
    }
    assert_true(!result_valid(replay_report_json(text, j.stringify())))
  }
}

///|
test "v2 runtime counters are explicitly outside semantic claims" {
  let h = completion_noise(3)
  let j = analysis_result_json(analyze_with_options(h))
  match j {
    Object(m) => m["metrics"] = Json::null()
    _ => abort("object")
  }
  assert_true(
    result_valid(replay_report_json(history_json(h).stringify(), j.stringify())),
  )
}

///|
test "balanced option parsing rejects duplicate, fractional and excessive budgets" {
  let h = history_json(completion_noise(3)).stringify()
  for
    opts in [
      "{\"maxAttempts\":-1}", "{\"maxAttempts\":0.5}", "{\"maxCachedStates\":50001}",
      "{\"maxAttempts\":1,\"maxAttempts\":2}", "{\"unknown\":1}",
    ] {
    let j = @json.parse(analyze_options_json(h, opts))
    assert_true(j is Object(m) && m.get("status") == Some(Json("invalid")))
  }
}

///|
test "unknown outcomes and missing clocks remain unresolved in balanced mode" {
  let h = {
    ..completion_noise(6),
    transactions: completion_noise(6).transactions +
    [tx("U", [], status=Unknown)],
  }
  assert_true(analyze_with_options(h).report.outcome == Inconclusive)
  let strict = { ..completion_noise(3), model: StrictSerializable, }
  assert_true(analyze_with_options(strict).report.outcome == Inconclusive)
}
