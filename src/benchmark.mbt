///|
/// Development-only phase hooks. Timers live in the host, not the analyzer.
pub fn benchmark_infer(h : History) -> Report {
  analyze_internal(h, false)
}

///|
pub fn benchmark_cycle(h : History, r : Report) -> Int32 {
  let (cycle, _) = shortest_cycle(h.transactions, r.edges)
  cycle.length()
}

///|
pub fn benchmark_search(h : History, r : Report) -> Int32 {
  let (info, _) = search_serial(h, r.inferred_orders, r.edges)
  info.attempts
}

///|
pub fn benchmark_render(r : Report) -> String {
  report_string(r)
}

///|
pub fn benchmark_search_balanced(h : History, r : Report) -> Int32 {
  let (info, _, _, _) = search_optimized(
    h,
    r.inferred_orders,
    r.edges,
    analysis_options(),
  )
  info.attempts
}

///|
pub fn benchmark_reduce_balanced(h : History) -> ReductionResult {
  reduce_with_options(h)
}
