///|
pub(all) struct AnalysisOptions {
  max_attempts : Int32
  max_operation_checks : Int32
  max_cached_states : Int32
} derive(Eq)

///|
pub extend AnalysisOptions with Eq::{equal, not_equal}

///|
pub fn analysis_options(
  max_attempts~ : Int32 = 100000,
  max_operation_checks~ : Int32 = 1000000,
  max_cached_states~ : Int32 = 50000,
) -> AnalysisOptions {
  { max_attempts, max_operation_checks, max_cached_states, }
}

///|
pub(all) struct AnalysisResult {
  report : Report
  options : AnalysisOptions
  cache_hits : Int32
  cached_states : Int32
} derive(Eq)

///|
pub extend AnalysisResult with Eq::{equal, not_equal}

///|
fn valid_analysis_options(o : AnalysisOptions) -> Bool {
  o.max_attempts >= 0 &&
  o.max_attempts <= 100000 &&
  o.max_operation_checks >= 0 &&
  o.max_operation_checks <= 1000000 &&
  o.max_cached_states >= 0 &&
  o.max_cached_states <= 50000
}

///|
pub fn analyze_with_options(
  h : History,
  options~ : AnalysisOptions = analysis_options(),
) -> AnalysisResult {
  analyze_balanced_indexed(h, options, collect_writes(h))
}

///|
fn analyze_balanced_indexed(
  h : History,
  options : AnalysisOptions,
  writes : Map[String, Map[String, WriteRef]],
  with_coverage~ : Bool = true,
  validated~ : Bool = false,
  search_cycles~ : Bool = true,
) -> AnalysisResult {
  if !valid_analysis_options(options) {
    return {
      report: base_report(
        h,
        Invalid,
        [
          issue(
            "invalid_options", "error", "Balanced budgets must be non-negative and within their documented maxima",
          ),
        ],
        Map([]),
      ),
      options: analysis_options(),
      cache_hits: 0,
      cached_states: 0,
    }
  }
  let base = analyze_internal(
    h,
    search_cycles,
    writes~,
    complete_search=false,
    with_coverage~,
    validated~,
  )
  if base.outcome != Inconclusive ||
    !base.findings.all(f => f.code == "missing_version_order") {
    return { report: base, options, cache_hits: 0, cached_states: 0, }
  }
  let (search, path, hits, cached) = search_optimized(
    h,
    base.inferred_orders,
    base.edges,
    options,
  )
  let mut report = { ..base, search, }
  if search.status == "found" {
    let ids = path.unwrap()
    let sources : Map[String, String] = Map([])
    for key, value in base.order_sources {
      sources[key] = if value == "missing" { "searched" } else { value }
    }
    report = {
      ..report,
      outcome: Consistent,
      findings: [],
      serial_order: ids,
      inferred_orders: orders_for_serial(h, ids),
      order_sources: sources,
    }
  } else if search.status == "exhausted" {
    report = {
      ..report,
      outcome: Violation,
      findings: [
        issue(
          "no_serial_execution", "violation", "Bounded complete enumeration found no serial execution reproducing all recorded reads and asserted orders",
        ),
      ],
    }
  } else {
    report = {
      ..report,
      findings: base.findings +
      [issue("search_limit", "uncertainty", search.reason)],
    }
  }
  { report, options, cache_hits: hits, cached_states: cached, }
}

///|
fn effective_limits(o : AnalysisOptions) -> Json {
  {
    "transactions": 12,
    "operations": 512,
    "keys": 128,
    "attempts": Json(o.max_attempts),
    "operationChecks": Json(o.max_operation_checks),
    "cachedStates": Json(o.max_cached_states),
  }
}

///|
fn analysis_extras(result : AnalysisResult) -> Map[String, Json] {
  Map([
    ("schemaVersion", Json(2)),
    ("algorithm", Json("bounded-register-v2.1")),
    ("effectiveLimits", effective_limits(result.options)),
    (
      "analysisOptions",
      {
        "maxAttempts": Json(result.options.max_attempts),
        "maxOperationChecks": Json(result.options.max_operation_checks),
        "maxCachedStates": Json(result.options.max_cached_states),
      },
    ),
    (
      "search",
      {
        "status": Json(result.report.search.status),
        "reason": Json(result.report.search.reason),
      },
    ),
    (
      "metrics",
      {
        "attempts": Json(result.report.search.attempts),
        "operationChecks": Json(result.report.search.operation_checks),
        "cacheHits": Json(result.cache_hits),
        "cachedStates": Json(result.cached_states),
        "blockers": Json(result.report.search.blockers.map(finding_json)),
      },
    ),
  ])
}

///|
pub fn analysis_result_json(result : AnalysisResult) -> Json {
  let j = report_json(result.report)
  match j {
    Object(m) =>
      for key, value in analysis_extras(result) {
        m[key] = value
      }
    _ => abort("Report object")
  }
  j
}

///|
fn analysis_result_string(result : AnalysisResult) -> String {
  report_string(result.report, extras=analysis_extras(result))
}

///|
fn parse_analysis_options(text : String) -> AnalysisOptions raise {
  if text == "{}" {
    return analysis_options()
  }
  let m = object_fields(guarded_json(text, limit=4096), "options")
  known_fields(
    m,
    ["maxAttempts", "maxOperationChecks", "maxCachedStates"],
    "options",
  )
  fn number(key : String, default : Int32, maximum : Int32) -> Int32 raise {
    match m.get(key) {
      None => default
      Some(Number(n, ..)) if n >= 0.0 &&
        n <= maximum.to_double() &&
        n.to_int().to_double() == n => n.to_int()
      _ => fail("Invalid budget: " + key)
    }
  }
  analysis_options(
    max_attempts=number("maxAttempts", 100000, 100000),
    max_operation_checks=number("maxOperationChecks", 1000000, 1000000),
    max_cached_states=number("maxCachedStates", 50000, 50000),
  )
}

///|
fn input_error_report(message : String) -> Report {
  base_report(
    {
      model: Serializable,
      initial: Map([]),
      version_orders: Map([]),
      transactions: [],
    },
    Invalid,
    [issue("invalid_input", "error", message)],
    Map([]),
  )
}

///|
fn options_input(text : String, options_text : String) -> AnalysisResult {
  try {
    let options = parse_analysis_options(options_text)
    match parse_history_optimized(text) {
      Ok(h) => analyze_with_options(h, options~)
      Err(message) =>
        {
          report: input_error_report(message),
          options,
          cache_hits: 0,
          cached_states: 0,
        }
    }
  } catch {
    e =>
      {
        report: input_error_report(e.to_string()),
        options: analysis_options(),
        cache_hits: 0,
        cached_states: 0,
      }
  }
}

///|
pub fn analyze_options_json(text : String, options_text : String) -> String {
  analysis_result_string(options_input(text, options_text))
}

///|
pub fn run_options_json(text : String, format : String) -> String {
  let result = options_input(text, "{}")
  report_transport_string(result.report, format, extras=analysis_extras(result))
}
