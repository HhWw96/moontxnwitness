///|
pub(all) struct ReductionOptions {
  max_checks : Int
  analysis : AnalysisOptions
} derive(Eq)

///|
pub extend ReductionOptions with Eq::{equal, not_equal}

///|
pub fn reduction_options(
  max_checks? : Int = 256,
  analysis? : AnalysisOptions = analysis_options(),
) -> ReductionOptions {
  { max_checks, analysis, }
}

///|
pub(all) struct ReductionResult {
  reduction : Reduction
  analysis : AnalysisResult
  cached_checks : Int
  max_checks : Int
} derive(Eq)

///|
pub extend ReductionResult with Eq::{equal, not_equal}

///|
priv struct ReductionContext {
  original : History
  writes : Map[String, Map[String, WriteRef]]
  options : ReductionOptions
  original_indices : Map[String, Int]
  negative_candidates : Map[String, Bool]
  mut checks : Int
  mut hits : Int
}

///|
fn reduction_candidate_key(
  ctx : ReductionContext,
  txs : Array[Transaction],
) -> String {
  // Candidate histories are subsequences of one validated original history.
  // Its at most 512 unique transaction IDs have indices 0..511, each encoded
  // losslessly as one character below the surrogate range. The cache is private
  // to this original, so neither separators nor a full original-length bitmap
  // are needed. Long/Unicode IDs never enlarge a key beyond 512 characters.
  if ctx.original_indices.is_empty() {
    for i, tx in ctx.original.transactions {
      ctx.original_indices[tx.id] = i
    }
  }
  let key = StringBuilder(size_hint=txs.length())
  for tx in txs {
    key.write_char(ctx.original_indices.at(tx.id).unsafe_to_char())
  }
  key.to_string()
}

///|
fn indexed_candidate(
  ctx : ReductionContext,
  txs : Array[Transaction],
) -> (History, Map[String, Map[String, WriteRef]]) {
  let local_ids : Map[String, Int] = Map([])
  for i, tx in txs {
    local_ids[tx.id] = i
  }
  let writes : Map[String, Map[String, WriteRef]] = Map([])
  for key, versions in ctx.writes {
    let kept : Map[String, WriteRef] = Map([])
    for version, w in versions {
      match local_ids.get(ctx.original.transactions[w.tx].id) {
        Some(ti) => kept[version] = { ..w, tx: ti, }
        None => ()
      }
    }
    if !kept.is_empty() {
      writes[key] = kept
    }
  }
  let orders : Map[String, Array[String]] = Map([])
  for key, chain in ctx.original.version_orders {
    orders[key] = chain.filter(v => {
      if ctx.original.initial.get(key) == Some(v) {
        true
      } else {
        match writes.get_or_default(key, Map([])).get(v) {
          Some(w) => w.is_final && txs[w.tx].status == Committed
          None => false
        }
      }
    })
  }
  ({ ..ctx.original, transactions: txs, version_orders: orders, }, writes)
}

///|
fn reduction_trial(
  ctx : ReductionContext,
  txs : Array[Transaction],
) -> (History, AnalysisResult)? {
  // With no recorded failures an exhausted budget cannot yield a cached hit.
  if ctx.checks >= ctx.options.max_checks && ctx.negative_candidates.is_empty() {
    return None
  }
  let key = reduction_candidate_key(ctx, txs)
  if ctx.negative_candidates.contains(key) {
    ctx.hits += 1
    return None
  }
  if ctx.checks >= ctx.options.max_checks {
    return None
  }
  let (h, writes) = indexed_candidate(ctx, txs)
  ctx.checks += 1
  // Deleting transactions from the already-validated original and pruning its
  // asserted orders preserves input invariants. Intermediate diagnostics are
  // deferred; every candidate still rebuilds dependency and execution semantics.
  let mut committed = 0
  for tx in txs {
    if tx.status == Committed {
      committed += 1
    }
  }
  // With at most one committed transaction neither a dependency cycle nor
  // missing multi-writer completion is possible. Unused initial-only keys
  // cannot affect direct read/source checks. The retained history still has
  // every original initial fact; accepted singleton results get a full final
  // analysis because graph.analyzed is false on this internal path.
  let tested = if committed <= 1 { singleton_projection(h) } else { h }
  let result = analyze_balanced_indexed(
    tested,
    ctx.options.analysis,
    writes,
    with_coverage=false,
    validated=true,
    search_cycles=committed > 1,
  )
  if result.report.outcome == Violation {
    Some((h, result))
  } else {
    ctx.negative_candidates[key] = true
    None
  }
}

///|
fn singleton_projection(h : History) -> History {
  let initial : Map[String, String] = Map([])
  let orders : Map[String, Array[String]] = Map([])
  for tx in h.transactions {
    for op in tx.ops {
      initial[op.key] = h.initial.at(op.key)
      match h.version_orders.get(op.key) {
        Some(order) => orders[op.key] = order
        None => ()
      }
    }
  }
  { ..h, initial, version_orders: orders, }
}

///|
fn witness_seed(
  h : History,
  r : Report,
  writes : Map[String, Map[String, WriteRef]],
) -> Array[Transaction] {
  let ids : Map[String, Bool] = Map([])
  for e in r.witness {
    ids[e.from] = true
  }
  if ids.is_empty() {
    for finding in r.findings {
      if finding.severity == "violation" && !finding.transactions.is_empty() {
        for id in finding.transactions {
          ids[id] = true
        }
        break
      }
    }
  }
  if ids.is_empty() {
    return h.transactions
  }
  let mut changed = true
  while changed {
    changed = false
    for tx in h.transactions {
      if !ids.contains(tx.id) {
        continue
      }
      for op in tx.ops {
        if op.kind != Read || h.initial.get(op.key) == Some(op.version) {
          continue
        }
        match writes.get_or_default(op.key, Map([])).get(op.version) {
          Some(w) => {
            let id = h.transactions[w.tx].id
            if !ids.contains(id) {
              ids[id] = true
              changed = true
            }
          }
          None => ()
        }
      }
    }
  }
  h.transactions.filter(t => ids.contains(t.id))
}

///|
pub fn reduce_with_options(
  h : History,
  options? : ReductionOptions = reduction_options(),
) -> ReductionResult {
  let writes = collect_writes(h)
  let original = analyze_balanced_indexed(
    h,
    options.analysis,
    writes,
    with_coverage=false,
  )
  let mut current = h
  let mut analysis = original
  let ctx : ReductionContext = {
    original: h,
    writes,
    options,
    original_indices: Map([]),
    negative_candidates: Map([]),
    checks: 0,
    hits: 0,
  }
  let mut minimal = false
  let mut status = "budget"
  let mut reason = "Reduction ended at its candidate-check budget; a definite violation is retained."
  if options.max_checks < 0 ||
    options.max_checks > 256 ||
    !valid_analysis_options(options.analysis) {
    status = "invalid"
    reason = "Invalid reduction or analysis budget."
  } else if original.report.outcome != Violation {
    status = "not-violation"
    reason = "Reduction requires a definite violation."
  } else if h.transactions.length() > 512 || count_ops(h) > 10000 {
    status = "skipped"
    reason = "Balanced reduction supports at most 512 transactions and 10,000 operations."
  } else {
    let seed = witness_seed(h, original.report, writes)
    if seed.length() < h.transactions.length() {
      match reduction_trial(ctx, seed) {
        Some((candidate, result)) => {
          current = candidate
          analysis = result
        }
        None => ()
      }
    }
    let mut parts = 2
    while !current.transactions.is_empty() && ctx.checks < options.max_checks {
      let n = current.transactions.length()
      parts = if parts > n { n } else { parts }
      let size = (n + parts - 1) / parts
      let mut start = 0
      let mut accepted = false
      while start < n && ctx.checks < options.max_checks {
        let txs : Array[Transaction] = []
        for i, tx in current.transactions {
          if i < start || i >= start + size {
            txs.push(tx)
          }
        }
        match reduction_trial(ctx, txs) {
          Some((candidate, result)) => {
            current = candidate
            analysis = result
            parts = if parts > 2 { parts - 1 } else { 2 }
            accepted = true
            break
          }
          None => ()
        }
        start += size
      }
      if accepted {
        continue
      }
      if start >= n && parts == n {
        minimal = true
        break
      }
      if ctx.checks >= options.max_checks {
        break
      }
      parts = if parts * 2 > n { n } else { parts * 2 }
    }
    if minimal {
      status = if current.transactions.length() < h.transactions.length() {
        "reduced"
      } else {
        "unchanged"
      }
      reason = "Every remaining singleton deletion was checked under the fixed balanced analyzer predicate and options. Not a global or operation minimum."
    }
  }
  let kept : Map[String, Bool] = Map([])
  for tx in current.transactions {
    kept[tx.id] = true
  }
  let (_, final_writes) = indexed_candidate(ctx, current.transactions)
  analysis = if !analysis.report.graph.analyzed &&
    analysis.report.outcome != Invalid {
    analyze_balanced_indexed(current, options.analysis, final_writes)
  } else {
    {
      ..analysis,
      report: {
        ..analysis.report,
        coverage: coverage_indexed(current, final_writes),
      },
    }
  }
  let reduction : Reduction = {
    history: current,
    report: analysis.report,
    status,
    removed: h.transactions.filter(t => !kept.contains(t.id)).map(t => t.id),
    checks: ctx.checks,
    one_minimal: minimal,
    reason,
  }
  {
    reduction,
    analysis,
    cached_checks: ctx.hits,
    max_checks: options.max_checks,
  }
}

///|
pub fn reduction_result_json(result : ReductionResult) -> Json {
  let json = reduction_json(result.reduction)
  match json {
    Object(m) => {
      m["schemaVersion"] = (2).to_json()
      m["report"] = analysis_result_json(result.analysis)
      m["limits"] = {
        "transactions": 512,
        "operations": 10000,
        "checks": result.max_checks.to_json(),
      }
      m["cachedCandidateChecks"] = result.cached_checks.to_json()
    }
    _ => abort("Reduction object")
  }
  json
}

///|
pub fn shrink_options_json(text : String, options_text : String) -> String {
  try {
    if options_text == "{}" {
      let h = match parse_history_optimized(text) {
        Ok(h) => h
        Err(message) => fail(message)
      }
      return reduction_result_string(reduce_with_options(h))
    }
    let m = object_fields(guarded_json(options_text, limit=8192), "options")
    known_fields(m, ["maxChecks", "analysisOptions"], "options")
    let max_checks = match m.get("maxChecks") {
      None => 256
      Some(Number(n, ..)) if n >= 0.0 &&
        n <= 256.0 &&
        n.to_int().to_double() == n => n.to_int()
      _ => fail("maxChecks must be an integer in 0..256")
    }
    let analysis = match m.get("analysisOptions") {
      None => analysis_options()
      Some(value) => parse_analysis_options(value.stringify())
    }
    let h = match parse_history_optimized(text) {
      Ok(h) => h
      Err(message) => fail(message)
    }
    reduction_result_string(
      reduce_with_options(h, options=reduction_options(max_checks~, analysis~)),
    )
  } catch {
    e => {
      let result : Json = {
        "status": "invalid",
        "reason": e.to_string().to_json(),
        "oneMinimal": false,
        "reducedHistory": Json::null(),
        "report": Json::null(),
      }
      result.stringify()
    }
  }
}
