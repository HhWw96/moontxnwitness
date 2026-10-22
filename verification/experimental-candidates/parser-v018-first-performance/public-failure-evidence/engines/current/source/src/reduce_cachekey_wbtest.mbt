///|
test "reduction cache does not confuse similar-ID candidates with opposite anomaly results" {
  let s = skew()
  let h = hist([
    tx("a", []),
    tx("bc", []),
    { ..s.transactions[0], id: "ab", },
    { ..s.transactions[1], id: "c", },
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
  let consistent = [h.transactions[0], h.transactions[1]]
  let violating = [h.transactions[2], h.transactions[3]]
  assert_true(reduction_trial(ctx, consistent) is None)
  assert_true(reduction_trial(ctx, consistent) is None)
  assert_eq(ctx.checks, 1)
  assert_eq(ctx.hits, 1)
  let (_, result) = reduction_trial(ctx, violating).unwrap()
  assert_true(result.report.outcome == Violation)
  assert_eq(ctx.checks, 2)
  assert_eq(ctx.hits, 1)
}

///|
test "reduction cache bounds long Unicode IDs and distinguishes indices zero and 511" {
  let original = large_noise(512)
  let txs = original.transactions.copy()
  let name = StringBuilder(size_hint=256)
  for _ in 0..<240 {
    name.write_char('长')
  }
  let prefix = name.to_string()
  txs[0] = { ..txs[0], id: prefix + "🙂\"\\", }
  txs[511] = { ..txs[511], id: prefix + "🙂\"\\末尾", }
  let h = { ..original, transactions: txs, }
  let ctx : ReductionContext = {
    original: h,
    writes: collect_writes(h),
    options: reduction_options(),
    original_indices: Map([]),
    negative_candidates: Map([]),
    checks: 0,
    hits: 0,
  }
  let first = [h.transactions[0]]
  let last = [h.transactions[511]]
  assert_true(reduction_trial(ctx, []) is None)
  assert_true(reduction_trial(ctx, first) is None)
  assert_true(reduction_trial(ctx, last) is None)
  assert_true(reduction_trial(ctx, first) is None)
  assert_true(reduction_trial(ctx, last) is None)
  assert_eq(ctx.checks, 3)
  assert_eq(ctx.hits, 2)
  assert_eq(reduction_candidate_key(ctx, first).length(), 1)
  assert_eq(reduction_candidate_key(ctx, last).length(), 1)
  assert_eq(reduction_candidate_key(ctx, h.transactions).length(), 512)
  assert_true(
    reduction_candidate_key(ctx, first) != reduction_candidate_key(ctx, last),
  )
  assert_true(reduction_candidate_key(ctx, []).is_empty())
}

///|
test "exhausted reduction budget still recognizes a cached failure without spending a check" {
  let h = large_noise(7)
  let ctx : ReductionContext = {
    original: h,
    writes: collect_writes(h),
    options: reduction_options(max_checks=1),
    original_indices: Map([]),
    negative_candidates: Map([]),
    checks: 0,
    hits: 0,
  }
  let candidate = [h.transactions[0]]
  assert_true(reduction_trial(ctx, candidate) is None)
  assert_eq(ctx.checks, 1)
  assert_true(reduction_trial(ctx, candidate) is None)
  assert_eq(ctx.checks, 1)
  assert_eq(ctx.hits, 1)
  assert_true(
    reduction_trial(ctx, [h.transactions[5], h.transactions[6]]) is None,
  )
  assert_eq(ctx.checks, 1)
  assert_eq(ctx.hits, 1)
  assert_eq(ctx.negative_candidates.length(), 1)
}

///|
test "typed control-character transaction IDs fail validation before reduction cache use" {
  for code in [0, 31, 127] {
    let id = "a" + code.unsafe_to_char().to_string() + "b"
    let s = skew()
    let h = {
      ..s,
      transactions: [{ ..s.transactions[0], id, }, s.transactions[1]],
    }
    let result = reduce_with_options(h)
    assert_true(result.analysis.report.outcome == Invalid)
    assert_eq(result.reduction.checks, 0)
    assert_eq(result.cached_checks, 0)
    assert_true(!result.reduction.one_minimal)
  }
}
