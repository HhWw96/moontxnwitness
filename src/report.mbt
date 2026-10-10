///|
fn string_option(s : String?) -> Json {
  match s {
    Some(v) => v.to_json()
    None => Json::null()
  }
}

///|
fn int_option(s : Int?) -> Json {
  match s {
    Some(v) => v.to_json()
    None => Json::null()
  }
}

///|
fn edge_json(e : Edge) -> Json {
  {
    "from": e.from.to_json(),
    "to": e.to.to_json(),
    "kind": dependency_label(e.kind).to_json(),
    "key": string_option(e.key),
    "fromOp": int_option(e.from_op),
    "toOp": int_option(e.to_op),
    "fromVersion": string_option(e.from_version),
    "toVersion": string_option(e.to_version),
    "reason": e.reason.to_json(),
  }
}

///|
fn finding_json(f : Finding) -> Json {
  {
    "code": f.code.to_json(),
    "severity": f.severity.to_json(),
    "message": f.message.to_json(),
    "transactions": f.transactions.to_json(),
    "key": string_option(f.key),
    "ops": f.ops.to_json(),
  }
}

///|
pub fn report_json(r : Report) -> Json {
  let witness : Json = if r.witness.is_empty() {
    Json::null()
  } else {
    let ids = r.witness.map(e => e.from)
    ids.push(r.witness[0].from)
    {
      "kind": "dependency_cycle",
      "transactions": ids.to_json(),
      "edges": r.witness.map(edge_json).to_json(),
      "minimality": "shortest directed cycle in the constructed graph",
    }
  }
  {
    "schemaVersion": 1,
    "tool": "MoonTxnWitness",
    "version": version().to_json(),
    "status": outcome_label(r.outcome).to_json(),
    "model": model_label(r.model).to_json(),
    "scope": "versioned point-read/write registers; supplied history and asserted version orders",
    "complete": (!r.findings.any(f => {
      f.severity == "uncertainty" || f.severity == "error"
    })).to_json(),
    "stats": {
      "transactions": r.transaction_count.to_json(),
      "committed": r.committed_count.to_json(),
      "operations": r.operation_count.to_json(),
      "dependencies": r.edges.length().to_json(),
    },
    "findings": r.findings.map(finding_json).to_json(),
    "edges": r.edges.map(edge_json).to_json(),
    "witness": witness,
    "serialOrder": r.serial_order.to_json(),
    "versionOrders": r.inferred_orders.to_json(),
    "versionOrderSources": r.order_sources.to_json(),
    "search": {
      "status": r.search.status.to_json(),
      "attempts": r.search.attempts.to_json(),
      "operationChecks": r.search.operation_checks.to_json(),
      "reason": r.search.reason.to_json(),
      "limits": {
        "transactions": 8,
        "operations": 512,
        "keys": 128,
        "attempts": 100000,
        "operationChecks": 1000000,
      },
      "blockers": r.search.blockers.map(finding_json).to_json(),
    },
  }
}

///|
/// Main portable host entry. Syntax/schema errors have the same report envelope.
pub fn analyze_json(text : String) -> String {
  match parse_history(text) {
    Ok(h) => report_json(analyze(h)).stringify(indent=2)
    Err(message) => {
      let empty : History = {
        model: Serializable,
        initial: Map([]),
        version_orders: Map([]),
        transactions: [],
      }
      report_json(
        base_report(
          empty,
          Invalid,
          [issue("invalid_input", "error", message)],
          Map([]),
        ),
      ).stringify(indent=2)
    }
  }
}

///|
/// Verify edge provenance and cycle closure without running cycle search again.
pub fn verify_cycle(h : History, witness : Array[Edge]) -> Bool {
  if witness.length() < 2 {
    return false
  }
  let analysis = analyze_internal(h, false)
  if analysis.outcome == Invalid {
    return false
  }
  let seen : Map[String, Bool] = Map([])
  for i, edge in witness {
    if !analysis.edges.contains(edge) ||
      edge.to != witness[(i + 1) % witness.length()].from ||
      seen.contains(edge.from) {
      return false
    }
    seen[edge.from] = true
  }
  true
}

///|
pub fn verify_certificate_json(
  history_text : String,
  certificate_text : String,
) -> String {
  let invalid = fn(message : String) -> String {
    let j : Json = {
      "valid": false,
      "reason": message.to_json(),
      "scope": "dependency-cycle certificate",
    }
    j.stringify(indent=2)
  }
  let h = match parse_history(history_text) {
    Ok(h) => h
    Err(e) => return invalid("Invalid history: " + e)
  }
  let r = analyze_internal(h, false)
  if r.outcome == Invalid {
    return invalid("History violates input constraints")
  }
  let c = guarded_json(certificate_text, limit=33554432) catch {
    _ => return invalid("Invalid certificate JSON")
  }
  let root = match c {
    Object(m) => m
    _ => return invalid("Certificate must be a report object")
  }
  if root.get("tool") != Some("MoonTxnWitness".to_json()) ||
    root.get("schemaVersion") != Some((1).to_json()) ||
    !compatible_evidence_version(root.get("version")) ||
    root.get("model") != Some(model_label(h.model).to_json()) ||
    root.get("status") != Some("violation".to_json()) {
    return invalid(
      "Certificate header does not match this tool, version, model and status",
    )
  }
  let w = match root.get("witness") {
    Some(Object(m)) => m
    _ => return invalid("Certificate has no dependency-cycle witness")
  }
  let cert_edges = match w.get("edges") {
    Some(Array(a)) => a
    _ => return invalid("Witness edges must be an array")
  }
  if w.get("kind") != Some("dependency_cycle".to_json()) ||
    cert_edges.length() < 2 ||
    cert_edges.length() > 512 {
    return invalid("Invalid witness kind or size")
  }
  let ids = match w.get("transactions") {
    Some(Array(a)) => a
    _ => return invalid("Witness transactions must be an array")
  }
  if ids.length() != cert_edges.length() + 1 {
    return invalid("Witness transaction path length does not match its edges")
  }
  let available = r.edges.map(edge_json)
  let seen : Map[String, Bool] = Map([])
  for i, e in cert_edges {
    if !available.contains(e) {
      return invalid("An edge is not justified by the supplied history")
    }
    let em = match e {
      Object(m) => m
      _ => return invalid("Edge must be an object")
    }
    let from = match em.get("from") {
      Some(String(s)) => s
      _ => return invalid("Invalid source identifier")
    }
    if seen.contains(from) {
      return invalid("Witness repeats a transaction before closure")
    }
    seen[from] = true
    if ids[i] != from.to_json() || em.get("to") != Some(ids[i + 1]) {
      return invalid("Witness edges do not follow the stated transaction path")
    }
  }
  if ids[0] != ids[ids.length() - 1] {
    return invalid("Witness is not a closed cycle")
  }
  let verified : Json = {
    "valid": true,
    "reason": "Every edge is justified and the simple transaction path closes into a cycle.",
    "scope": "dependency-cycle certificate",
    "verifiedEdges": cert_edges.length().to_json(),
    "checks": [
      "input constraints", "edge provenance", "transaction path", "cycle closure",
    ],
  }
  verified.stringify(indent=2)
}
