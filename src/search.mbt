///|
priv struct SearchContext {
  mut attempts : Int32
  mut operations : Int32
  mut limited : Bool
  max_attempts : Int32
  max_operations : Int32
  blockers : Array[Finding]
}

///|
fn clone_state(state : Map[String, String]) -> Map[String, String] {
  let result : Map[String, String] = Map([])
  for k, v in state {
    result[k] = v
  }
  result
}

///|
fn search_step(
  h : History,
  orders : Map[String, Array[String]],
  edges : Array[Edge],
  selected : Array[Bool],
  prefix : Array[Int32],
  state : Map[String, String],
  positions : Map[String, Int32],
  ctx : SearchContext,
  count : Int32,
) -> Array[Int32]? {
  if prefix.length() == count {
    return Some(prefix)
  }
  for ti, tx in h.transactions {
    if tx.status != Committed || selected[ti] {
      continue
    }
    let mut ready = true
    for e in edges {
      if e.to == tx.id {
        for pi, prior in h.transactions {
          if prior.id == e.from && !selected[pi] {
            ready = false
          }
        }
      }
    }
    if !ready {
      continue
    }
    if ctx.attempts >= ctx.max_attempts {
      ctx.limited = true
      return None
    }
    ctx.attempts += 1
    let next_state = clone_state(state)
    let final_writes : Map[String, String] = Map([])
    let mut valid = true
    for oi, op in tx.ops {
      if ctx.operations >= ctx.max_operations {
        ctx.limited = true
        return None
      }
      ctx.operations += 1
      if op.kind == Read {
        if next_state.get(op.key) != Some(op.version) {
          valid = false
          if ctx.blockers.length() < 32 {
            ctx.blockers.push(
              issue(
                "candidate_read_mismatch",
                "diagnostic",
                "Candidate prefix cannot reproduce read " +
                op.version +
                "; current version is " +
                next_state.get_or_default(op.key, "<missing>"),
                txs=prefix.map(i => h.transactions[i].id) + [tx.id],
                key=Some(op.key),
                ops=[oi],
              ),
            )
          }
          break
        }
      } else {
        next_state[op.key] = op.version
        final_writes[op.key] = op.version
      }
    }
    if !valid {
      continue
    }
    let next_positions : Map[String, Int32] = Map([])
    for k, v in positions {
      next_positions[k] = v
    }
    for key, v in final_writes {
      let position = positions.get_or_default(key, 0) + 1
      match orders.get(key) {
        Some(order) =>
          if position >= order.length() || order[position] != v {
            valid = false
          }
        None => ()
      }
      next_positions[key] = position
    }
    if !valid {
      continue
    }
    selected[ti] = true
    let next_prefix = prefix.copy()
    next_prefix.push(ti)
    let result = search_step(
      h, orders, edges, selected, next_prefix, next_state, next_positions, ctx, count,
    )
    selected[ti] = false
    if result is Some(_) || ctx.limited {
      return result
    }
  }
  None
}

///|
fn search_serial(
  h : History,
  orders : Map[String, Array[String]],
  edges : Array[Edge],
  max_attempts~ : Int32 = 100000,
  max_operations~ : Int32 = 1000000,
) -> (SearchInfo, Array[String]?) {
  let count = h.transactions.filter(t => t.status == Committed).length()
  if count > 8 || count_ops(h) > 512 || h.initial.length() > 128 {
    return (
      {
        status: "skipped",
        attempts: 0,
        operation_checks: 0,
        reason: "Completion search supports at most 8 committed transactions, 512 operations and 128 keys.",
        blockers: [],
      },
      None,
    )
  }
  let ctx : SearchContext = {
    attempts: 0,
    operations: 0,
    limited: false,
    max_attempts,
    max_operations,
    blockers: [],
  }
  let path = search_step(
    h,
    orders,
    edges,
    Array::make(h.transactions.length(), false),
    [],
    h.initial,
    Map([]),
    ctx,
    count,
  )
  let status = if ctx.limited {
    "budget"
  } else if path is Some(_) {
    "found"
  } else {
    "exhausted"
  }
  (
    {
      status,
      attempts: ctx.attempts,
      operation_checks: ctx.operations,
      reason: if ctx.limited {
        "Completion search reached its attempt or operation budget; no negative verdict is justified."
      } else if path is Some(_) {
        "One valid serial execution exists; searched version orders are possible completions, not observed facts."
      } else {
        "All admissible serial prefixes were exhausted without a valid execution."
      },
      blockers: ctx.blockers,
    },
    path.map(p => p.map(i => h.transactions[i].id)),
  )
}

///|
fn orders_for_serial(
  h : History,
  ids : Array[String],
) -> Map[String, Array[String]] {
  let result : Map[String, Array[String]] = Map([])
  for key, v in h.initial {
    result[key] = [v]
  }
  for id in ids {
    for tx in h.transactions {
      if tx.id != id {
        continue
      }
      let final_writes : Map[String, String] = Map([])
      for op in tx.ops {
        if op.kind == Write {
          final_writes[op.key] = op.version
        }
      }
      for key, v in final_writes {
        result.at(key).push(v)
      }
    }
  }
  result
}
