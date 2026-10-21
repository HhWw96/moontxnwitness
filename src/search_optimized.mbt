///|
priv struct CompiledOperation {
  key : Int
  version : Int
  read : Bool
  original : Int
}

///|
priv struct CompiledTransaction {
  id : String
  ops : Array[CompiledOperation]
  final_writes : Array[(Int, Int)]
  predecessors : Int
}

///|
priv struct OptimizedSearch {
  txs : Array[CompiledTransaction]
  keys : Array[String]
  versions : Array[Array[String]]
  orders : Array[Array[Int]]
  state : Array[Int]
  positions : Array[Int]
  trail_keys : FixedArray[Int]
  trail_values : FixedArray[Int]
  position_keys : FixedArray[Int]
  position_values : FixedArray[Int]
  mut trail_size : Int
  mut position_size : Int
  failures : Map[String, Bool]
  prefix : Array[Int]
  blockers : Array[Finding]
  options : AnalysisOptions
  mut attempts : Int
  mut operations : Int
  mut hits : Int
  mut limited : Bool
}

///|
fn encode_search_state_key(
  selected : Int,
  state : Array[Int],
  positions : Array[Int],
) -> String {
  // The compiled search admits at most 12 transactions and 512 operations:
  // selected <= 4095, each version ID <= 512, and each position <= 12.
  // These nonnegative values are all below the Unicode surrogate range.
  // Both vectors have the same fixed key count K throughout this search, so
  // one character per component gives a lossless key of exactly 1 + 2*K
  // characters. It retains selected, every current version and every position;
  // no delimiters, decimal strings, truncation or probabilistic digest is used.
  let b = StringBuilder(size_hint=1 + state.length() + positions.length())
  b.write_char(selected.unsafe_to_char())
  for value in state {
    b.write_char(value.unsafe_to_char())
  }
  for value in positions {
    b.write_char(value.unsafe_to_char())
  }
  b.to_string()
}

///|
fn optimized_state_key(ctx : OptimizedSearch, selected : Int) -> String {
  encode_search_state_key(selected, ctx.state, ctx.positions)
}

///|
fn undo_search(ctx : OptimizedSearch, mark : Int, position_mark : Int) -> Unit {
  while ctx.trail_size > mark {
    ctx.trail_size -= 1
    ctx.state[ctx.trail_keys[ctx.trail_size]] = ctx.trail_values[ctx.trail_size]
  }
  while ctx.position_size > position_mark {
    ctx.position_size -= 1
    ctx.positions[ctx.position_keys[ctx.position_size]] = ctx.position_values[ctx.position_size]
  }
}

///|
fn optimized_step(ctx : OptimizedSearch, selected : Int) -> Array[Int]? {
  if ctx.prefix.length() == ctx.txs.length() {
    return Some(ctx.prefix.copy())
  }
  let key = if ctx.options.max_cached_states > 0 {
    optimized_state_key(ctx, selected)
  } else {
    ""
  }
  if ctx.options.max_cached_states > 0 && ctx.failures.contains(key) {
    ctx.hits += 1
    return None
  }
  for ti, tx in ctx.txs {
    let bit = 1 << ti
    if (selected & bit) != 0 || (selected & tx.predecessors) != tx.predecessors {
      continue
    }
    if ctx.attempts >= ctx.options.max_attempts {
      ctx.limited = true
      return None
    }
    ctx.attempts += 1
    let mark = ctx.trail_size
    let position_mark = ctx.position_size
    let mut valid = true
    for op in tx.ops {
      if ctx.operations >= ctx.options.max_operation_checks {
        ctx.limited = true
        undo_search(ctx, mark, position_mark)
        return None
      }
      ctx.operations += 1
      if op.read {
        if ctx.state[op.key] != op.version {
          valid = false
          if ctx.blockers.length() < 32 {
            ctx.blockers.push(
              issue(
                "candidate_read_mismatch",
                "diagnostic",
                "Candidate prefix cannot reproduce read " +
                ctx.versions[op.key][op.version] +
                "; current version is " +
                ctx.versions[op.key][ctx.state[op.key]],
                txs=ctx.prefix.map(i => ctx.txs[i].id) + [tx.id],
                key=Some(ctx.keys[op.key]),
                ops=[op.original],
              ),
            )
          }
          break
        }
      } else {
        // A selected prefix plus its next distinct transaction contains at most
        // the admitted 512 operations; therefore the live write trail fits.
        ctx.trail_keys[ctx.trail_size] = op.key
        ctx.trail_values[ctx.trail_size] = ctx.state[op.key]
        ctx.trail_size += 1
        ctx.state[op.key] = op.version
      }
    }
    if valid {
      for pair in tx.final_writes {
        let (k, v) = pair
        let position = ctx.positions[k] + 1
        if !ctx.orders[k].is_empty() &&
          (position >= ctx.orders[k].length() || ctx.orders[k][position] != v) {
          valid = false
          break
        }
        // Final writes are a subset of those same admitted write operations.
        ctx.position_keys[ctx.position_size] = k
        ctx.position_values[ctx.position_size] = ctx.positions[k]
        ctx.position_size += 1
        ctx.positions[k] = position
      }
    }
    if valid {
      ctx.prefix.push(ti)
      let result = optimized_step(ctx, selected | bit)
      let _ = ctx.prefix.pop()
      undo_search(ctx, mark, position_mark)
      if result is Some(_) || ctx.limited {
        return result
      }
    } else {
      undo_search(ctx, mark, position_mark)
    }
  }
  // Only fully explored states are negative lemmas. Never cache interrupted work.
  if ctx.failures.length() < ctx.options.max_cached_states {
    ctx.failures[key] = true
  }
  None
}

///|
fn search_optimized(
  h : History,
  orders : Map[String, Array[String]],
  edges : Array[Edge],
  options : AnalysisOptions,
) -> (SearchInfo, Array[String]?, Int, Int) {
  let transactions = h.transactions.filter(t => t.status == Committed)
  if transactions.length() > 12 ||
    count_ops(h) > 512 ||
    h.initial.length() > 128 {
    return (
      {
        status: "skipped",
        attempts: 0,
        operation_checks: 0,
        reason: "Balanced completion supports at most 12 committed transactions, 512 operations and 128 keys.",
        blockers: [],
      },
      None,
      0,
      0,
    )
  }
  let keys = h.initial.keys().collect()
  keys.sort()
  let key_ids : Map[String, Int] = Map([])
  let version_ids : Array[Map[String, Int]] = []
  let versions : Array[Array[String]] = []
  for i, key in keys {
    key_ids[key] = i
    version_ids.push(Map([(h.initial.at(key), 0)]))
    versions.push([h.initial.at(key)])
  }
  for tx in transactions {
    for op in tx.ops {
      let k = key_ids.at(op.key)
      if !version_ids[k].contains(op.version) {
        version_ids[k][op.version] = versions[k].length()
        versions[k].push(op.version)
      }
    }
  }
  let tx_ids : Map[String, Int] = Map([])
  for i, tx in transactions {
    tx_ids[tx.id] = i
  }
  let predecessors = Array::make(transactions.length(), 0)
  for e in edges {
    let target = tx_ids.at(e.to)
    predecessors[target] = predecessors[target] | (1 << tx_ids.at(e.from))
  }
  let compiled : Array[CompiledTransaction] = transactions.mapi((i, tx) => {
    let finals : Map[Int, Int] = Map([])
    let ops : Array[CompiledOperation] = tx.ops.mapi((oi, op) => {
      let key = key_ids.at(op.key)
      let version = version_ids[key].at(op.version)
      if op.kind == Write {
        finals[key] = version
      }
      { key, version, read: op.kind == Read, original: oi, }
    })
    {
      id: tx.id,
      ops,
      final_writes: finals.iter().collect(),
      predecessors: predecessors[i],
    }
  })
  let ctx : OptimizedSearch = {
    txs: compiled,
    keys,
    versions,
    orders: keys.mapi((i, key) => {
      orders.get_or_default(key, []).map(v => version_ids[i].at(v))
    }),
    state: Array::make(keys.length(), 0),
    positions: Array::make(keys.length(), 0),
    trail_keys: FixedArray::make(512, 0),
    trail_values: FixedArray::make(512, 0),
    position_keys: FixedArray::make(512, 0),
    position_values: FixedArray::make(512, 0),
    trail_size: 0,
    position_size: 0,
    failures: Map([]),
    prefix: [],
    blockers: [],
    options,
    attempts: 0,
    operations: 0,
    hits: 0,
    limited: false,
  }
  let path = optimized_step(ctx, 0)
  let status = if ctx.limited {
    "budget"
  } else if path is Some(_) {
    "found"
  } else {
    "exhausted"
  }
  let reason = if ctx.limited {
    "Completion search reached its attempt or operation budget; no negative verdict is justified."
  } else if path is Some(_) {
    "One valid serial execution exists; searched version orders are possible completions, not observed facts."
  } else {
    "All admissible serial prefixes were exhausted without a valid execution."
  }
  (
    {
      status,
      attempts: ctx.attempts,
      operation_checks: ctx.operations,
      reason,
      blockers: ctx.blockers,
    },
    path.map(p => p.map(i => compiled[i].id)),
    ctx.hits,
    ctx.failures.length(),
  )
}
