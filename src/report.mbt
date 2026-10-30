///|
fn string_option(s : String?) -> Json {
  match s {
    Some(v) => Json(v)
    None => Json::null()
  }
}

///|
fn int_option(s : Int32?) -> Json {
  match s {
    Some(v) => Json(v)
    None => Json::null()
  }
}

///|
fn edge_json(e : Edge) -> Json {
  {
    "from": Json(e.from),
    "to": Json(e.to),
    "kind": Json(dependency_label(e.kind)),
    "key": string_option(e.key),
    "fromOp": int_option(e.from_op),
    "toOp": int_option(e.to_op),
    "fromVersion": string_option(e.from_version),
    "toVersion": string_option(e.to_version),
    "reason": Json(e.reason),
  }
}

///|
fn finding_json(f : Finding) -> Json {
  {
    "code": Json(f.code),
    "severity": Json(f.severity),
    "message": Json(f.message),
    "transactions": Json(f.transactions),
    "key": string_option(f.key),
    "ops": Json(f.ops),
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
      "transactions": Json(ids),
      "edges": Json(r.witness.map(edge_json)),
      "minimality": "shortest directed cycle in the constructed graph",
    }
  }
  {
    "schemaVersion": 1,
    "tool": "MoonTxnWitness",
    "version": Json(version()),
    "status": Json(outcome_label(r.outcome)),
    "model": Json(model_label(r.model)),
    "scope": "versioned point-read/write registers; supplied history and asserted version orders",
    "complete": Json(
      !r.findings.any(f => f.severity == "uncertainty" || f.severity == "error"),
    ),
    "stats": {
      "transactions": Json(r.transaction_count),
      "committed": Json(r.committed_count),
      "operations": Json(r.operation_count),
      "dependencies": Json(r.edges.length()),
    },
    "findings": Json(r.findings.map(finding_json)),
    "edges": Json(r.edges.map(edge_json)),
    "witness": witness,
    "serialOrder": Json(r.serial_order),
    "versionOrders": Json(r.inferred_orders),
    "versionOrderSources": Json(r.order_sources),
    "graph": {
      "analyzed": Json(r.graph.analyzed),
      "components": Json(r.graph.components),
      "cyclicComponents": Json(r.graph.cyclic_components),
      "cyclicTransactions": Json(r.graph.cyclic_transactions),
      "bfsRoots": Json(r.graph.bfs_roots),
      "edgeBudgetExceeded": Json(r.graph.edge_budget_exceeded),
    },
    "coverage": Json(
      r.coverage.map(k => {
        (
          {
            "key": Json(k.key),
            "committedReads": Json(k.committed_reads),
            "committedFinalWrites": Json(k.committed_final_writes),
            "unresolvedReads": Json(k.unresolved_reads),
            "versionOrderSource": Json(r.order_sources.at(k.key)),
            "sourceLabel": Json(
              order_source_cn(
                r.order_sources.at(k.key),
                k.committed_final_writes,
              ),
            ),
          } : Json)
      }),
    ),
    "nextSteps": Json(next_steps(r)),
    "search": {
      "status": Json(r.search.status),
      "attempts": Json(r.search.attempts),
      "operationChecks": Json(r.search.operation_checks),
      "reason": Json(r.search.reason),
      "limits": {
        "transactions": 8,
        "operations": 512,
        "keys": 128,
        "attempts": 100000,
        "operationChecks": 1000000,
      },
      "blockers": Json(r.search.blockers.map(finding_json)),
    },
  }
}

///|
/// Main portable host entry. Syntax/schema errors have the same report envelope.
pub fn analyze_json(text : String) -> String {
  match parse_history(text) {
    Ok(h) => report_string(analyze(h))
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
      "reason": Json(message),
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
  if root.get("tool") != Some(Json("MoonTxnWitness")) ||
    root.get("schemaVersion") != Some(Json(1)) ||
    !compatible_evidence_version(root.get("version")) ||
    root.get("model") != Some(Json(model_label(h.model))) ||
    root.get("status") != Some(Json("violation")) {
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
  if w.get("kind") != Some(Json("dependency_cycle")) ||
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
    if ids[i] != Json(from) || em.get("to") != Some(ids[i + 1]) {
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
    "verifiedEdges": Json(cert_edges.length()),
    "checks": [
      "input constraints", "edge provenance", "transaction path", "cycle closure",
    ],
  }
  verified.stringify(indent=2)
}
