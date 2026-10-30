///|
fn large_noise(n : Int32) -> History {
  let initial : Map[String, String] = Map([("x", "x0"), ("y", "y0")])
  let txs : Array[Transaction] = []
  for i in 0..<(n - 2) {
    let key = "noise" + i.to_string()
    initial[key] = "v0"
    txs.push(tx(key, [read_op(key, "v0")]))
  }
  { ..skew(), initial, transactions: txs + skew().transactions, }
}

///|
test "balanced reduces 512 transactions to two and proves singleton minimality" {
  let h = large_noise(512)
  assert_eq(reduce_history(h).status, "skipped")
  let result = reduce_with_options(h)
  assert_eq(result.reduction.history.transactions.length(), 2)
  assert_true(result.reduction.one_minimal)
  assert_true(result.analysis.report.outcome == Violation)
  assert_eq(
    analysis_result_json(result.analysis),
    analysis_result_json(analyze_with_options(result.reduction.history)),
  )
  assert_true(result.reduction.history.initial == h.initial)
  assert_true(result.reduction.checks <= 4)
  for i in 0..<2 {
    assert_true(
      analyze_with_options(without_chunk(result.reduction.history, i, 1)).report.outcome !=
      Violation,
    )
  }
}

///|
test "zero and interrupted reduction budgets retain an honest verified counterexample" {
  let h = large_noise(32)
  for max_checks in [0, 1, 2] {
    let result = reduce_with_options(h, options=reduction_options(max_checks~))
    assert_eq(result.reduction.status, "budget")
    assert_true(!result.reduction.one_minimal)
    assert_true(result.analysis.report.outcome == Violation)
    assert_true(result.reduction.checks <= max_checks)
  }
}

///|
test "candidate writer remapping matches fresh collection including aborts and intermediate writes" {
  let h = hist([
    tx("noise", [write_op("y", "y1")], status=Aborted),
    tx("A", [write_op("x", "x1"), write_op("x", "x2")]),
    tx("B", [read_op("x", "x2")]),
  ])
  let ctx : ReductionContext = {
    original: h,
    writes: collect_writes(h),
    options: reduction_options(),
    original_indices: Map([]),
    negative_candidates: Map([]),
    checks: 0,
    hits: 0,
  }
  for
    txs in [
      h.transactions,
      [h.transactions[1], h.transactions[2]],
      [h.transactions[0]],
    ] {
    let (candidate, writes) = indexed_candidate(ctx, txs)
    let expected = collect_writes(candidate)
    assert_eq(writes.length(), expected.length())
    for key, versions in writes {
      assert_eq(versions.length(), expected.at(key).length())
      for version, w in versions {
        let e = expected.at(key).at(version)
        assert_eq(w.tx, e.tx)
        assert_eq(w.op, e.op)
        assert_eq(w.is_final, e.is_final)
      }
    }
  }
}

///|
test "balanced reduction never promotes a searched order into input facts" {
  let h = completion_noise(6)
  let r = reduce_with_options(h)
  assert_true(r.reduction.one_minimal)
  assert_true(r.reduction.history.version_orders.is_empty())
  assert_true(r.analysis.report.outcome == Violation)
}

///|
test "cached candidate misses do not spend another analysis budget" {
  let h = skew()
  let ctx : ReductionContext = {
    original: h,
    writes: collect_writes(h),
    options: reduction_options(),
    original_indices: Map([]),
    negative_candidates: Map([]),
    checks: 0,
    hits: 0,
  }
  assert_true(reduction_trial(ctx, [h.transactions[0]]) is None)
  assert_true(reduction_trial(ctx, [h.transactions[0]]) is None)
  assert_eq(ctx.checks, 1)
  assert_eq(ctx.hits, 1)
}

///|
test "streamed reduced history and full result preserve structured values" {
  for
    h in [
      large_noise(7),
      hist([
        tx(
          "quoted\"\\☃",
          [write_op("x", "x1")],
          start=Some(9007199254740990L),
          end=Some(9007199254740991L),
        ),
      ]),
    ] {
    assert_eq(@json.parse(history_string(h)), history_json(h))
    let r = reduce_with_options(h)
    assert_eq(@json.parse(reduction_result_string(r)), reduction_result_json(r))
  }
}

///|
test "singleton internal projection preserves direct anomalies and uncertainty" {
  for
    ops in [
      [read_op("x", "x0")],
      [read_op("x", "x1")],
      [write_op("x", "x2"), read_op("x", "x0")],
      [read_op("x", "x0"), read_op("x", "x1")],
      [read_op("x", "unknown")],
    ] {
    for status in [Aborted, Unknown] {
      let initial = large_noise(64).initial
      let h = {
        ..hist([tx("A", ops), tx("source", [write_op("x", "x1")], status~)]),
        initial,
      }
      let projected = singleton_projection(h)
      assert_true(
        analyze_with_options(projected).report.outcome ==
        analyze_with_options(h).report.outcome,
      )
      let reduced = reduce_with_options(h)
      assert_eq(
        analysis_result_json(reduced.analysis),
        analysis_result_json(analyze_with_options(reduced.reduction.history)),
      )
      assert_true(reduced.reduction.history.initial == h.initial)
    }
  }
}

///|
test "encoding cache saturation changes neither escaping nor complete reports" {
  let result = reduce_with_options(large_noise(7))
  let before = reduction_result_string(result)
  for i in 0..<2100 {
    let value = "cache/" + i.to_string() + "中文\"\\\n"
    assert_eq(cached_quote(value), Json(value).stringify())
  }
  assert_true(quoted_strings.values.length() <= 2048)
  assert_true(quoted_strings.units <= 131072)
  assert_eq(reduction_result_string(result), before)
}

///|
test "shared reduction writer retains Unicode intermediate-read provenance" {
  let key = "键\"\\🙂"
  let middle = "中间\"\\版本"
  let final_version = "终版🙂"
  let h = {
    ..hist([
      tx("写者\"🙂", [
        write_op(key, middle),
        read_op(key, middle),
        write_op(key, final_version),
      ]),
      tx("读者\\", [read_op(key, middle)]),
    ]),
    initial: Map([(key, "初始\"\\版本"), ("未使用🙂", "初始")]),
  }
  let result = reduce_with_options(h)
  assert_true(result.reduction.one_minimal)
  assert_eq(result.reduction.history.transactions.length(), 2)
  assert_true(has_code(result.analysis.report, "intermediate_read"))
  let encoded = reduction_result_string(result)
  assert_eq(@json.parse(encoded), reduction_result_json(result))
  let output = object_fields(@json.parse(encoded), "output")
  let restored = parse_history(output.at("reducedHistory").stringify()).unwrap()
  assert_true(restored == result.reduction.history)
  assert_eq(restored.transactions[0].ops[0].version, middle)
  assert_eq(restored.transactions[0].ops[2].version, final_version)
  assert_true(
    result_valid(
      replay_report_json(
        history_string(restored),
        output.at("report").stringify(),
      ),
    ),
  )
}

///|
test "shared reduction writer retains all 512 initial facts and exact check accounting" {
  let h = large_noise(512)
  for max_checks in [0, 1, 256] {
    let result = reduce_with_options(h, options=reduction_options(max_checks~))
    let encoded = reduction_result_string(result)
    let output = object_fields(@json.parse(encoded), "output")
    let restored = parse_history(output.at("reducedHistory").stringify()).unwrap()
    assert_true(restored.initial == h.initial)
    assert_eq(restored.initial.length(), 512)
    assert_eq(result.analysis.report.coverage.length(), 512)
    assert_eq(result.analysis.report.inferred_orders.length(), 512)
    assert_eq(
      result.reduction.checks,
      if max_checks == 256 {
        3
      } else {
        max_checks
      },
    )
    assert_eq(result.cached_checks, 0)
    assert_eq(result.reduction.one_minimal, max_checks == 256)
    assert_eq(
      restored.transactions.length(),
      if max_checks == 0 {
        512
      } else {
        2
      },
    )
    assert_eq(@json.parse(encoded), reduction_result_json(result))
    assert_true(
      result_valid(
        replay_report_json(
          history_string(restored),
          output.at("report").stringify(),
        ),
      ),
    )
  }
}

///|
test "shared reduction writer distinguishes an empty history from a singleton violation" {
  let empty = hist([])
  let empty_result = reduce_with_options(empty)
  assert_eq(empty_result.reduction.status, "not-violation")
  assert_eq(empty_result.reduction.checks, 0)
  assert_true(!empty_result.reduction.one_minimal)
  assert_eq(
    @json.parse(reduction_result_string(empty_result)),
    reduction_result_json(empty_result),
  )
  let single = hist([
    tx("A", [read_op("x", "x0"), write_op("x", "x1"), read_op("x", "x0")]),
  ])
  let result = reduce_with_options(single)
  assert_eq(result.reduction.history.transactions.length(), 1)
  assert_eq(result.reduction.checks, 1)
  assert_true(result.reduction.one_minimal)
  assert_true(has_code(result.analysis.report, "read_your_writes"))
  let output = object_fields(
    @json.parse(reduction_result_string(result)),
    "output",
  )
  assert_eq(output.at("checks"), Json(1))
  assert_eq(
    @json.parse(reduction_result_string(result)),
    reduction_result_json(result),
  )
}
