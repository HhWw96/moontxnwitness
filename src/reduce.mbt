///|
pub(all) struct Reduction {
  history : History
  report : Report
  status : String
  removed : Array[String]
  checks : Int32
  one_minimal : Bool
  reason : String
} derive(Eq)

///|
pub extend Reduction with Eq::{equal, not_equal}

///|
// Removing transactions must prune only asserted orders, never assert searched ones.
fn without_chunk(h : History, start : Int32, size : Int32) -> History {
  let transactions : Array[Transaction] = []
  for i, tx in h.transactions {
    if i < start || i >= start + size {
      transactions.push(tx)
    }
  }
  let candidate : History = { ..h, transactions, version_orders: Map([]), }
  let writes = collect_writes(candidate)
  let orders : Map[String, Array[String]] = Map([])
  for key, order in h.version_orders {
    let kept : Array[String] = []
    for version in order {
      if h.initial.get(key) == Some(version) {
        kept.push(version)
      } else {
        match writes.get_or_default(key, Map([])).get(version) {
          Some(w) if w.is_final && transactions[w.tx].status == Committed =>
            kept.push(version)
          _ => ()
        }
      }
    }
    orders[key] = kept
  }
  { ..candidate, version_orders: orders, }
}

///|
/// Delta debugging followed by a complete singleton pass proves one-minimality.
/// The predicate is a definite Violation from this analyzer, not absence of a serial replay with unknown sources.
pub fn reduce_history(h : History, max_checks~ : Int32 = 128) -> Reduction {
  let original = analyze(h)
  if original.outcome != Violation {
    return {
      history: h,
      report: original,
      status: "not-violation",
      removed: [],
      checks: 0,
      one_minimal: false,
      reason: "Reduction requires a definite violation.",
    }
  }
  if h.transactions.length() > 64 || count_ops(h) > 2048 {
    return {
      history: h,
      report: original,
      status: "skipped",
      removed: [],
      checks: 0,
      one_minimal: false,
      reason: "Reduction supports at most 64 transactions and 2,048 operations.",
    }
  }
  let mut current = h
  let mut report = original
  let mut checks = 0
  let mut parts = 2
  let mut minimal = false
  while !current.transactions.is_empty() && checks < max_checks {
    let n = current.transactions.length()
    parts = if parts > n { n } else { parts }
    let size = (n + parts - 1) / parts
    let mut start = 0
    let mut accepted = false
    while start < n && checks < max_checks {
      let candidate = without_chunk(current, start, size)
      let result = analyze(candidate)
      checks += 1
      if result.outcome == Violation {
        current = candidate
        report = result
        parts = if parts > 2 { parts - 1 } else { 2 }
        accepted = true
        break
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
    if checks >= max_checks {
      break
    }
    parts = if parts * 2 > n { n } else { parts * 2 }
  }
  let ids = current.transactions.map(t => t.id)
  let removed = h.transactions.filter(t => !ids.contains(t.id)).map(t => t.id)
  {
    history: current,
    report,
    removed,
    checks,
    one_minimal: minimal,
    status: if !minimal {
      "budget"
    } else if removed.is_empty() {
      "unchanged"
    } else {
      "reduced"
    },
    reason: if minimal {
      "No single remaining transaction can be deleted while retaining a definite violation, with asserted orders pruned and initial state fixed. This is not a global minimum."
    } else {
      "Reduction budget ended; a definite violation is retained but one-minimality was not established."
    },
  }
}

///|
pub fn reduction_json(r : Reduction) -> Json {
  {
    "tool": "MoonTxnWitness",
    "version": Json(version()),
    "status": Json(r.status),
    "oneMinimal": Json(r.one_minimal),
    "removedTransactions": Json(r.removed),
    "checks": Json(r.checks),
    "reason": Json(r.reason),
    "reducedHistory": history_json(r.history),
    "report": report_json(r.report),
    "limits": { "transactions": 64, "operations": 2048, "checks": 128 },
    "scope": "transaction deletion; fixed initial state; asserted orders pruned; analyzer-specific definite-violation predicate",
  }
}

///|
pub fn shrink_json(text : String) -> String {
  match parse_history(text) {
    Ok(h) => reduction_json(reduce_history(h)).stringify(indent=2)
    Err(e) => {
      let result : Json = {
        "status": "invalid",
        "reason": Json(e),
        "oneMinimal": false,
        "reducedHistory": Json::null(),
        "report": Json::null(),
      }
      result.stringify(indent=2)
    }
  }
}
