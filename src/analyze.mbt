///|
fn collect_writes(h : History) -> Map[String, Map[String, WriteRef]] {
  let writes : Map[String, Map[String, WriteRef]] = Map([])
  for ti, tx in h.transactions {
    let mut single_key = ""
    let mut single_last = -1
    let mut multiple_keys = false
    for oi, op in tx.ops {
      if op.kind == Write {
        if single_last < 0 {
          single_key = op.key
        } else if single_key != op.key {
          multiple_keys = true
        }
        single_last = oi
      }
    }
    if single_last < 0 {
      continue
    }
    let last : Map[String, Int]? = if multiple_keys {
      Some(Map([]))
    } else {
      None
    }
    if multiple_keys {
      for oi, op in tx.ops {
        if op.kind == Write {
          last.unwrap()[op.key] = oi
        }
      }
    }
    for oi, op in tx.ops {
      if op.kind == Write {
        let versions = match writes.get(op.key) {
          Some(versions) => versions
          None => Map([])
        }
        versions[op.version] = {
          tx: ti,
          op: oi,
          is_final: if multiple_keys {
            last.unwrap().get(op.key) == Some(oi)
          } else {
            oi == single_last
          },
        }
        writes[op.key] = versions
      }
    }
  }
  writes
}

///|
fn resolve_orders(
  h : History,
  writes : Map[String, Map[String, WriteRef]],
  findings : Array[Finding],
) -> Map[String, Array[String]] {
  let result : Map[String, Array[String]] = Map([])
  for key, _ in h.version_orders {
    if !h.initial.contains(key) {
      findings.push(
        issue(
          "invalid_version_order",
          "error",
          "Version order key has no initial version",
          key=Some(key),
        ),
      )
    }
  }
  let keys = h.initial.keys().collect()
  keys.sort()
  for key in keys {
    let init = h.initial.at(key)
    if !writes.contains(key) && !h.version_orders.contains(key) {
      result[key] = [init]
      continue
    }
    let committed : Array[String] = []
    for
      v, w in (match writes.get(key) {
        Some(versions) => versions
        None => Map([])
      }) {
      if w.is_final && h.transactions[w.tx].status == Committed {
        committed.push(v)
      }
    }
    committed.sort()
    match h.version_orders.get(key) {
      Some(order) => {
        let seen : Map[String, Bool] = Map([])
        let mut valid = order.length() == committed.length() + 1
        if order.length() == 0 || order[0] != init {
          valid = false
        }
        for i, v in order {
          if seen.contains(v) || (i > 0 && !committed.contains(v)) {
            valid = false
          }
          seen[v] = true
        }
        for v in committed {
          if !seen.contains(v) {
            valid = false
          }
        }
        if valid {
          result[key] = order.copy()
        } else {
          findings.push(
            issue(
              "invalid_version_order",
              "error",
              "Order must start with the initial version and contain each committed final write exactly once",
              key=Some(key),
            ),
          )
        }
      }
      None =>
        if committed.length() <= 1 {
          let order = [init]
          for v in committed {
            order.push(v)
          }
          result[key] = order
        } else {
          findings.push(
            issue(
              "missing_version_order",
              "uncertainty",
              "Multiple committed writers: their version order is not observable from scalar reads alone",
              key=Some(key),
            ),
          )
        }
    }
  }
  result
}

///|
fn add_edge(
  edges : Array[Edge],
  seen : Map[Edge, Bool],
  overflow : Array[Bool],
  edge : Edge,
) -> Unit {
  if edge.from == edge.to {
    return
  }
  if seen.contains(edge) {
    return
  }
  if edges.length() >= 50000 {
    overflow[0] = true
    return
  }
  seen[edge] = true
  edges.push(edge)
}

///|
fn count_ops(h : History) -> Int {
  let mut n = 0
  for tx in h.transactions {
    n += tx.ops.length()
  }
  n
}

///|
fn base_report(
  h : History,
  outcome : Outcome,
  findings : Array[Finding],
  orders : Map[String, Array[String]],
  writes? : Map[String, Map[String, WriteRef]] = collect_writes(h),
  with_coverage? : Bool = true,
) -> Report {
  let mut committed = 0
  for tx in h.transactions {
    if tx.status == Committed {
      committed += 1
    }
  }
  let sources : Map[String, String] = Map([])
  for key, _ in h.initial {
    sources[key] = if h.version_orders.contains(key) {
      "asserted"
    } else if orders.contains(key) {
      "single-writer"
    } else {
      "missing"
    }
  }
  {
    outcome,
    model: h.model,
    findings,
    edges: [],
    witness: [],
    serial_order: [],
    transaction_count: h.transactions.length(),
    committed_count: committed,
    operation_count: count_ops(h),
    inferred_orders: orders,
    order_sources: sources,
    graph: empty_graph(),
    coverage: if with_coverage {
      coverage_indexed(h, writes)
    } else {
      []
    },
    search: {
      status: "not-needed",
      attempts: 0,
      operation_checks: 0,
      reason: "No bounded completion search was required.",
      blockers: [],
    },
  }
}

///|
/// Analyze point reads and unique versioned writes. No arrival/commit order is invented.
pub fn analyze(h : History) -> Report {
  analyze_internal(h, true)
}

///|
/// Evidence verification shares inference rules but does not run graph search.
fn analyze_internal(
  h : History,
  search_cycles : Bool,
  writes? : Map[String, Map[String, WriteRef]] = collect_writes(h),
  complete_search? : Bool = true,
  with_coverage? : Bool = true,
  validated? : Bool = false,
) -> Report {
  let findings = if validated { [] } else { validate_history(h) }
  if !findings.is_empty() {
    return base_report(h, Invalid, findings, Map([]), writes~, with_coverage~)
  }
  let orders = resolve_orders(h, writes, findings)
  if findings.any(f => f.severity == "error") {
    return base_report(h, Invalid, findings, orders, writes~, with_coverage~)
  }
  let edges : Array[Edge] = []
  let edge_seen : Map[Edge, Bool] = Map([])
  let overflow = [false]
  let keys = orders.keys().collect()
  keys.sort()
  let ranks : Map[String, Map[String, Int]] = Map([])
  for key in keys {
    if orders.at(key).length() < 3 {
      continue
    }
    let by_rank : Map[String, Int] = Map([])
    for i, v in orders.at(key) {
      by_rank[v] = i
    }
    ranks[key] = by_rank
  }
  // Consecutive version constraints suffice for write-write order.
  for key in keys {
    let order = orders.at(key)
    if order.length() < 3 {
      continue
    }
    let by_version = writes.get_or_default(key, Map([]))
    for i in 2..<order.length() {
      let a = by_version.at(order[i - 1])
      let b = by_version.at(order[i])
      let ta = h.transactions[a.tx]
      let tb = h.transactions[b.tx]
      add_edge(edges, edge_seen, overflow, {
        from: ta.id,
        to: tb.id,
        kind: WW,
        key: Some(key),
        from_op: Some(a.op),
        to_op: Some(b.op),
        from_version: Some(order[i - 1]),
        to_version: Some(order[i]),
        reason: "The asserted per-key version order puts this write before the next write.",
      })
    }
  }
  // Allocate scratch only for keys touched by a non-skipped committed
  // transaction. A reduced counterexample may retain many unused initial keys.
  let scratch_keys : Map[String, Int] = Map([])
  let own_epoch : Array[Int] = []
  let own_versions : Array[String] = []
  let own_ops : Array[Int] = []
  let read_epoch : Array[Int] = []
  let read_versions : Array[String] = []
  let read_ops : Array[Int] = []
  for ti, tx in h.transactions {
    if tx.status == Unknown {
      findings.push(
        issue(
          "unknown_commit",
          "uncertainty",
          "Transaction outcome is unknown; it is excluded from the committed graph",
          txs=[tx.id],
        ),
      )
    }
    if tx.status != Committed {
      continue
    }
    // Reads of unchanged initial-only keys cannot contribute a dependency or
    // a direct anomaly. Keep the transaction for RT and graph accounting.
    if tx.ops.all(op => {
        op.kind == Read &&
        h.initial.get(op.key) == Some(op.version) &&
        !writes.contains(op.key)
      }) {
      continue
    }
    let epoch = ti + 1
    for oi, op in tx.ops {
      let ki = match scratch_keys.get(op.key) {
        Some(index) => index
        None => {
          let index = scratch_keys.length()
          scratch_keys[op.key] = index
          own_epoch.push(0)
          own_versions.push("")
          own_ops.push(-1)
          read_epoch.push(0)
          read_versions.push("")
          read_ops.push(-1)
          index
        }
      }
      if op.kind == Write {
        own_epoch[ki] = epoch
        own_versions[ki] = op.version
        own_ops[ki] = oi
        continue
      }
      if own_epoch[ki] == epoch {
        if op.version != own_versions[ki] {
          findings.push(
            issue(
              "read_your_writes",
              "violation",
              "Read does not observe the most recent write in its own transaction",
              txs=[tx.id],
              key=Some(op.key),
              ops=[own_ops[ki], oi],
            ),
          )
        }
        continue
      }
      if read_epoch[ki] == epoch && read_versions[ki] != op.version {
        findings.push(
          issue(
            "non_repeatable_read",
            "violation",
            "The same transaction observes different versions without an intervening own write",
            txs=[tx.id],
            key=Some(op.key),
            ops=[read_ops[ki], oi],
          ),
        )
      }
      if read_epoch[ki] != epoch {
        read_epoch[ki] = epoch
        read_versions[ki] = op.version
        read_ops[ki] = oi
      }
      let is_initial = h.initial.get(op.key) == Some(op.version)
      if is_initial && !writes.contains(op.key) {
        continue
      }
      let by_version = writes.get_or_default(op.key, Map([]))
      let mut usable = is_initial
      if !is_initial {
        match by_version.get(op.version) {
          None =>
            findings.push(
              issue(
                "unobserved_version",
                "uncertainty",
                "Read version has no recorded writer; the supplied history may be incomplete",
                txs=[tx.id],
                key=Some(op.key),
                ops=[oi],
              ),
            )
          Some(w) => {
            let writer = h.transactions[w.tx]
            if w.tx == ti {
              findings.push(
                issue(
                  "future_read",
                  "violation",
                  "A transaction reads a version from its own future write",
                  txs=[tx.id],
                  key=Some(op.key),
                  ops=[oi, w.op],
                ),
              )
            } else if writer.status == Aborted {
              findings.push(
                issue(
                  "aborted_read",
                  "violation",
                  "A committed transaction reads a version written by an aborted transaction",
                  txs=[writer.id, tx.id],
                  key=Some(op.key),
                  ops=[w.op, oi],
                ),
              )
            } else if writer.status == Unknown {
              findings.push(
                issue(
                  "unknown_writer",
                  "uncertainty",
                  "The read's source transaction has an unknown outcome",
                  txs=[writer.id, tx.id],
                  key=Some(op.key),
                  ops=[w.op, oi],
                ),
              )
            } else if !w.is_final {
              findings.push(
                issue(
                  "intermediate_read",
                  "violation",
                  "A committed transaction observes another transaction's overwritten intermediate version",
                  txs=[writer.id, tx.id],
                  key=Some(op.key),
                  ops=[w.op, oi],
                ),
              )
            } else {
              usable = true
              add_edge(edges, edge_seen, overflow, {
                from: writer.id,
                to: tx.id,
                kind: WR,
                key: Some(op.key),
                from_op: Some(w.op),
                to_op: Some(oi),
                from_version: Some(op.version),
                to_version: Some(op.version),
                reason: "The reader observes the unique final version written by the source transaction.",
              })
            }
          }
        }
      }
      if !usable {
        continue
      }
      match orders.get(op.key) {
        Some(order) => {
          if order.length() < 2 {
            continue
          }
          let read_rank = if order.length() == 2 {
            if is_initial {
              0
            } else {
              1
            }
          } else {
            ranks.at(op.key).get_or_default(op.version, -1)
          }
          if read_rank >= 0 {
            for rank in (read_rank + 1)..<order.length() {
              let w = by_version.at(order[rank])
              let writer = h.transactions[w.tx]
              add_edge(edges, edge_seen, overflow, {
                from: tx.id,
                to: writer.id,
                kind: RW,
                key: Some(op.key),
                from_op: Some(oi),
                to_op: Some(w.op),
                from_version: Some(op.version),
                to_version: Some(order[rank]),
                reason: "The reader observes an earlier version and must precede this later committed write.",
              })
            }
          }
        }
        None =>
          // An initial read precedes every committed write even when their mutual order is unknown.
          if is_initial {
            let versions = by_version.keys().collect()
            versions.sort()
            for v in versions {
              let w = by_version.at(v)
              let writer = h.transactions[w.tx]
              if w.is_final && writer.status == Committed {
                add_edge(edges, edge_seen, overflow, {
                  from: tx.id,
                  to: writer.id,
                  kind: RW,
                  key: Some(op.key),
                  from_op: Some(oi),
                  to_op: Some(w.op),
                  from_version: Some(op.version),
                  to_version: Some(v),
                  reason: "An initial read must precede every committed write on this key.",
                })
              }
            }
          }
      }
    }
  }
  if h.model == StrictSerializable {
    for tx in h.transactions {
      if tx.status == Committed && (tx.start is None || tx.end is None) {
        findings.push(
          issue(
            "missing_interval",
            "uncertainty",
            "Strict serializability requires start and end from one monotonic observer clock",
            txs=[tx.id],
          ),
        )
      }
    }
    for a in h.transactions {
      if a.status != Committed {
        continue
      }
      for b in h.transactions {
        if b.status != Committed || a.id == b.id {
          continue
        }
        match (a.end, b.start) {
          (Some(e), Some(s)) if e < s => {
            // Unique validated transaction IDs make each ordered RT pair unique.
            // Other dependency kinds still use full structural deduplication.
            if edges.length() >= 50000 {
              overflow[0] = true
              continue
            }
            edges.push({
              from: a.id,
              to: b.id,
              kind: RT,
              key: None,
              from_op: None,
              to_op: None,
              from_version: None,
              to_version: None,
              reason: "The source completed before the target began on the asserted common observer clock.",
            })
          }
          _ => ()
        }
      }
    }
  }
  if overflow[0] {
    findings.push(
      issue(
        "edge_limit", "uncertainty", "More than 50,000 distinct dependencies; graph construction was truncated",
      ),
    )
  }
  let graph_index = if search_cycles {
    adjacency(h.transactions, edges)
  } else {
    { adj: [], sources: [], targets: [], }
  }
  let (witness, graph) = if search_cycles {
    shortest_cycle(h.transactions, edges, prepared=graph_index)
  } else {
    ([], empty_graph())
  }
  if !witness.is_empty() {
    let txs = witness.map(e => e.from)
    findings.push(
      issue(
        "dependency_cycle",
        "violation",
        "The dependency cycle prevents any serial order satisfying these observations and constraints",
        txs~,
      ),
    )
  }
  let mut outcome = if findings.any(f => f.severity == "violation") {
    Violation
  } else if findings.any(f => f.severity == "uncertainty") {
    Inconclusive
  } else {
    Consistent
  }
  let mut serial_order = if search_cycles && outcome == Consistent {
    topological_order(h.transactions, edges, prepared=graph_index)
  } else {
    []
  }
  let base = base_report(h, outcome, findings, orders, writes~, with_coverage~)
  let mut search = base.search
  let mut resolved_orders = orders
  if search_cycles &&
    complete_search &&
    outcome == Inconclusive &&
    findings.all(f => f.code == "missing_version_order") {
    let (info, solution) = search_serial(h, orders, edges)
    search = info
    if info.status == "found" || info.status == "exhausted" {
      findings.clear()
      match solution {
        Some(ids) => {
          serial_order = ids
          resolved_orders = orders_for_serial(h, ids)
          for key, source in base.order_sources {
            if source == "missing" {
              base.order_sources[key] = "searched"
            }
          }
          outcome = Consistent
        }
        None => {
          findings.push(
            issue(
              "no_serial_execution", "violation", "Bounded complete enumeration found no serial execution reproducing all recorded reads and asserted orders",
            ),
          )
          outcome = Violation
        }
      }
    } else {
      findings.push(issue("search_limit", "uncertainty", info.reason))
    }
  }
  {
    ..base,
    outcome,
    edges,
    witness,
    serial_order,
    inferred_orders: resolved_orders,
    search,
    graph: { ..graph, edge_budget_exceeded: overflow[0], },
  }
}
