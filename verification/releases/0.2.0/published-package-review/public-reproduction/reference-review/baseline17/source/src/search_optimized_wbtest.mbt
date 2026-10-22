///|
test "search cache key preserves zero and maximum numeric components" {
  let state = [0, 1, 255, 256, 511, 512]
  let positions = [0, 1, 2, 10, 11, 12]
  let key = encode_search_state_key(4095, state, positions)
  assert_eq(key.length(), 13)
  assert_eq(key.unsafe_get(0).to_int(), 4095)
  for i, value in state {
    assert_eq(key.unsafe_get(i + 1).to_int(), value)
  }
  for i, value in positions {
    assert_eq(key.unsafe_get(i + 1 + state.length()).to_int(), value)
  }
  // Embedded zero is a real component, not an end marker or empty string.
  let zero = encode_search_state_key(0, [0], [0])
  assert_eq(zero.length(), 3)
  assert_true(zero != "")
  assert_true(zero != encode_search_state_key(0, [], []))
}

///|
test "cache keys distinguish every mask and every component at the supported bounds" {
  let masks : Map[String, Bool] = Map([])
  for selected in 0..<4096 {
    let key = encode_search_state_key(selected, [512], [12])
    assert_true(!masks.contains(key))
    masks[key] = true
  }
  assert_eq(masks.length(), 4096)
  let versions : Map[String, Bool] = Map([])
  for version in 0..<513 {
    let key = encode_search_state_key(4095, [version], [12])
    assert_true(!versions.contains(key))
    versions[key] = true
  }
  assert_eq(versions.length(), 513)
  let state = Array::make(128, 0)
  let positions = Array::make(128, 0)
  let keys : Map[String, Bool] = Map([])
  keys[encode_search_state_key(4095, state, positions)] = true
  for i in 0..<128 {
    state[i] = 512
    let version_key = encode_search_state_key(4095, state, positions)
    assert_eq(version_key.length(), 257)
    assert_true(!keys.contains(version_key))
    keys[version_key] = true
    state[i] = 0
    positions[i] = 12
    let position_key = encode_search_state_key(4095, state, positions)
    assert_true(!keys.contains(position_key))
    keys[position_key] = true
    positions[i] = 0
  }
  assert_eq(keys.length(), 257)
}

///|
test "numeric cache keys retain exact search budgets counters and cache saturation" {
  let h = completion_noise(6)
  // These counts were frozen from the decimal-key implementation. They guard
  // the traversal, failure-cache membership and interrupted-state behavior,
  // including budgets exactly one short of and equal to exhaustive completion.
  for
    (options, outcome, attempts, operations, hits, cached, blockers) in [
      (analysis_options(), Violation, 108, 148, 53, 40, 16),
      (analysis_options(max_cached_states=0), Violation, 537, 773, 0, 0, 32),
      (analysis_options(max_cached_states=1), Violation, 478, 714, 59, 1, 32),
      (analysis_options(max_attempts=0), Inconclusive, 0, 0, 0, 0, 0),
      (analysis_options(max_attempts=1), Inconclusive, 1, 1, 0, 0, 0),
      (analysis_options(max_attempts=107), Inconclusive, 107, 146, 53, 37, 15),
      (analysis_options(max_attempts=108), Violation, 108, 148, 53, 40, 16),
      (analysis_options(max_operation_checks=0), Inconclusive, 1, 0, 0, 0, 0),
      (analysis_options(max_operation_checks=1), Inconclusive, 2, 1, 0, 0, 0),
      (
        analysis_options(max_operation_checks=147),
        Inconclusive,
        108,
        147,
        53,
        37,
        15,
      ),
      (
        analysis_options(max_operation_checks=148),
        Violation,
        108,
        148,
        53,
        40,
        16,
      ),
    ] {
    let result = analyze_with_options(h, options~)
    assert_true(result.report.outcome == outcome)
    assert_eq(result.report.search.attempts, attempts)
    assert_eq(result.report.search.operation_checks, operations)
    assert_eq(result.cache_hits, hits)
    assert_eq(result.cached_states, cached)
    assert_eq(result.report.search.blockers.length(), blockers)
    assert_eq(
      result.report.search.status,
      if outcome == Violation {
        "exhausted"
      } else {
        "budget"
      },
    )
    assert_true(
      has_code(
        result.report,
        if outcome == Violation {
          "no_serial_execution"
        } else {
          "search_limit"
        },
      ),
    )
  }
}
