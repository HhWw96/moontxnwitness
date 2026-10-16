///|
fn history_string(h : History) -> String {
  let strings : Map[String, String] = Map([])
  let b = json_text()
  b.write_string("{\"schemaVersion\":1,\"model\":")
  b.write_string(quoted_cached(strings, model_label(h.model)))
  b.write_string(",\"initial\":{")
  let mut first = true
  for key, value in h.initial {
    if !first {
      b.write_char(',')
    }
    first = false
    b.write_string(quoted_cached(strings, key))
    b.write_char(':')
    b.write_string(quoted_cached(strings, value))
  }
  b.write_string("},\"versionOrders\":{")
  first = true
  for key, versions in h.version_orders {
    if !first {
      b.write_char(',')
    }
    first = false
    b.write_string(quoted_cached(strings, key))
    b.write_string(":[")
    for i, v in versions {
      if i > 0 {
        b.write_char(',')
      }
      b.write_string(quoted_cached(strings, v))
    }
    b.write_char(']')
  }
  b.write_string("},\"transactions\":[")
  for i, tx in h.transactions {
    if i > 0 {
      b.write_char(',')
    }
    b.write_string("{\"id\":")
    b.write_string(quoted_cached(strings, tx.id))
    b.write_string(",\"status\":")
    b.write_string(quoted_cached(strings, status_label(tx.status)))
    b.write_string(",\"start\":")
    b.write_string(
      match tx.start {
        Some(t) => t.to_string()
        None => "null"
      },
    )
    b.write_string(",\"end\":")
    b.write_string(
      match tx.end {
        Some(t) => t.to_string()
        None => "null"
      },
    )
    b.write_string(",\"ops\":[")
    for oi, op in tx.ops {
      if oi > 0 {
        b.write_char(',')
      }
      b.write_string("{\"type\":")
      b.write_string(quoted_cached(strings, op_label(op.kind)))
      b.write_string(",\"key\":")
      b.write_string(quoted_cached(strings, op.key))
      b.write_string(",\"version\":")
      b.write_string(quoted_cached(strings, op.version))
      b.write_char('}')
    }
    b.write_string("]}")
  }
  b.write_string("]}")
  b.to_string()
}

///|
fn reduction_result_string(result : ReductionResult) -> String {
  let r = result.reduction
  let metadata : Json = {
    "schemaVersion": 2,
    "tool": "MoonTxnWitness",
    "version": version().to_json(),
    "status": r.status.to_json(),
    "oneMinimal": r.one_minimal.to_json(),
    "removedTransactions": r.removed.to_json(),
    "checks": r.checks.to_json(),
    "reason": r.reason.to_json(),
    "limits": {
      "transactions": 512,
      "operations": 10000,
      "checks": result.max_checks.to_json(),
    },
    "cachedCandidateChecks": result.cached_checks.to_json(),
    "scope": "transaction deletion; fixed initial state; asserted orders pruned; analyzer-specific definite-violation predicate",
  }
  let fields = match metadata {
    Object(m) => m
    _ => abort("object")
  }
  let b = json_text()
  let strings : Map[String, String] = Map([])
  b.write_char('{')
  for name, value in fields {
    b.write_string(quoted_cached(strings, name))
    b.write_char(':')
    b.write_string(scalar_string(value, strings))
    b.write_char(',')
  }
  b.write_string("\"reducedHistory\":")
  b.write_string(history_string(r.history))
  b.write_string(",\"report\":")
  b.write_string(analysis_result_string(result.analysis))
  b.write_char('}')
  b.to_string()
}
