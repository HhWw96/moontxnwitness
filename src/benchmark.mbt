///|
/// Development-only phase hooks. Timers live in the host, not the analyzer.
pub fn benchmark_infer(h : History) -> Report {
  analyze_internal(h, false)
}

///|
pub fn benchmark_cycle(h : History, r : Report) -> Int {
  let (cycle, _) = shortest_cycle(h.transactions, r.edges)
  cycle.length()
}

///|
pub fn benchmark_search(h : History, r : Report) -> Int {
  let (info, _) = search_serial(h, r.inferred_orders, r.edges)
  info.attempts
}

///|
pub fn benchmark_render(r : Report) -> String {
  report_string(r)
}
