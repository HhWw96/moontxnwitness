///|
priv struct EffectiveListReadV4 {
  tx : String
  key : String
  seq : Int64
  observed : Array[Int32]
  own_at_read : Array[Int32]
  mut usable : Bool
  mut reason : String
}

///|
priv struct EffectiveListIndexV4 {
  parsed : ListV3Parsed
  outcomes : Map[String, TxStatus]
  reads : Array[EffectiveListReadV4]
  groups : Map[String, Map[String, Array[Int32]]]
  active : Array[Int32]
  active_set : FixedArray[Bool]
  intrinsic : Array[Json]
  gaps : Array[Json]
  mut journal_complete : Bool
  mut reads_complete : Bool
}

///|
priv struct EffectiveListBudgetV4 {
  maximum : Int32
  mut checks : Int32
  mut limited : Bool
  mut reason : String
}

///|
pub struct EffectiveListGraphV4 {
  priv base : ClassificationModelV3Graph
  priv index : EffectiveListIndexV4
  priv orders : Array[Json]
  priv quarantined : Array[Json]
  priv item_order_validated : Bool
  priv checks : Int32
  priv maximum : Int32
  priv limited : Bool
}

///|
fn list_effective_slice_matches_v4(
  expected : Array[Int32],
  actual : Array[Int32],
  offset : Int32,
) -> Bool {
  if offset < 0 || offset + expected.length() > actual.length() {
    return false
  }
  for position, item in expected {
    if actual[offset + position] != item {
      return false
    }
  }
  true
}

///|
fn list_effective_charge_v4(budget : EffectiveListBudgetV4) -> Bool {
  if budget.checks >= budget.maximum {
    budget.limited = true
    budget.reason = "list-effective-construction-budget"
    false
  } else {
    budget.checks += 1
    true
  }
}

///|
fn list_effective_empty_index_v4(parsed : ListV3Parsed) -> EffectiveListIndexV4 {
  {
    parsed,
    outcomes: Map([]),
    reads: [],
    groups: Map([]),
    active: [],
    active_set: FixedArray::make(parsed.items.length(), false),
    intrinsic: [],
    gaps: match object_fields_unchecked_v3(parsed.normalized).get("coverage") {
      Some(Object(coverage)) =>
        match coverage.get("gaps") {
          Some(Array(gaps)) => gaps.copy()
          _ => []
        }
      _ => []
    },
    journal_complete: false,
    reads_complete: false,
  }
}

///|
fn list_effective_item_ids_v4(
  parsed : ListV3Parsed,
  items : Array[Int32],
) -> Array[String] {
  items.map(index => {
    if index < 0 {
      "<missing-source>"
    } else {
      parsed.items[index].id
    }
  })
}

///|
fn list_effective_gap_v4(
  index : EffectiveListIndexV4,
  read : EffectiveListReadV4,
  reason : String,
) -> Unit {
  read.usable = false
  read.reason = reason
  index.gaps.push({
    "code": Json(reason),
    "transaction": Json(read.tx),
    "key": Json(read.key),
    "readSeq": Json(read.seq.to_double()),
  })
}

///|
/// Replay only the transaction-local append journal. Delivered read observations
/// are immutable, including own reads of effects revoked by a later rollback.
fn list_effective_index_v4(
  parsed : ListV3Parsed,
  budget : EffectiveListBudgetV4,
) -> EffectiveListIndexV4 {
  let index = list_effective_empty_index_v4(parsed)
  let final_own : Map[String, Map[String, Array[Int32]]] = Map([])
  for program in parsed.programs {
    index.outcomes[program.id] = program.status
    let own : Map[String, Array[Int32]] = Map([])
    let trail : Array[(String, Int32)] = []
    let scopes : Array[(String, Int32)] = []
    for action in program.actions {
      if !list_effective_charge_v4(budget) {
        return index
      }
      match action {
        Append(key, item) => {
          let values = own.get_or_default(key, [])
          values.push(item)
          own[key] = values
          trail.push((key, item))
        }
        ReadList(key, observed, seq) => {
          let values = own.get_or_default(key, [])
          for _ in values {
            if !list_effective_charge_v4(budget) {
              return index
            }
          }
          index.reads.push({
            tx: program.id,
            key,
            seq,
            observed,
            own_at_read: values.copy(),
            usable: false,
            reason: "not-validated",
          })
        }
        Mark(instance) => scopes.push((instance, trail.length()))
        Undo(instance) | Release(instance) => {
          let mut found = -1
          for position, scope in scopes {
            if scope.0 == instance {
              found = position
            }
          }
          if found < 0 {
            index.gaps.push({
              "code": "invalid-effective-savepoint-journal",
              "transaction": Json(program.id),
            })
            return index
          }
          if action is Undo(_) {
            while trail.length() > scopes[found].1 {
              if !list_effective_charge_v4(budget) {
                return index
              }
              let removed = trail.pop().unwrap()
              let _ = own.at(removed.0).pop()
            }
          }
          let retained = if action is Undo(_) { found + 1 } else { found }
          while scopes.length() > retained {
            let _ = scopes.pop()
          }
        }
      }
    }
    if program.status == Committed {
      final_own[program.id] = own
      for _, values in own {
        for item in values {
          index.active_set[item] = true
        }
      }
    }
  }
  // Check the independently replayed final effects against the lifecycle ledger.
  for item_index, item in parsed.items {
    if !list_effective_charge_v4(budget) {
      return index
    }
    match item.tx {
      Some(writer) if index.outcomes.get(writer) == Some(Committed) => {
        let source = object_fields_unchecked_v3(
          parsed.source_evidence[item_index],
        )
        let expected = source.get("revertedBy") == Some(Json::null())
        if index.active_set[item_index] != expected {
          index.gaps.push({
            "code": "effective-append-ledger-mismatch",
            "itemId": Json(item.id),
            "appendSeq": Json(item.seq.to_double()),
          })
          return index
        }
        if expected {
          index.active.push(item_index)
        }
      }
      _ => ()
    }
  }
  for writer, keys in final_own {
    for key, values in keys {
      if values.is_empty() {
        continue
      }
      let groups = index.groups.get_or_default(key, Map([]))
      groups[writer] = values
      index.groups[key] = groups
      for position in 1..<values.length() {
        let first = parsed.items[values[position - 1]]
        let last = parsed.items[values[position]]
        index.intrinsic.push({
          "basis": "same-transaction-final-effective-append-order",
          "transaction": Json(writer),
          "key": Json(key),
          "fromItem": Json(first.id),
          "toItem": Json(last.id),
          "fromAppendSeq": Json(first.seq.to_double()),
          "toAppendSeq": Json(last.seq.to_double()),
        })
      }
    }
  }
  index.journal_complete = true
  let invalid : Map[Int64, String] = Map([])
  for finding in parsed.findings {
    let fields = object_fields_unchecked_v3(finding)
    match fields.get("readSeq") {
      Some(Number(n, ..)) =>
        invalid[n.to_int64()] = match fields.get("code") {
          Some(String(code)) => code
          _ => "invalid-list-source"
        }
      _ => ()
    }
  }
  for read in index.reads {
    if index.outcomes.get(read.tx) != Some(Committed) {
      read.usable = false
      read.reason = "reader-not-committed"
      continue
    }
    if invalid.contains(read.seq) {
      list_effective_gap_v4(index, read, invalid.at(read.seq))
      continue
    }
    if !parsed.initial.contains(read.key) {
      list_effective_gap_v4(index, read, "missing-initial-list")
      continue
    }
    let initial = parsed.initial.at(read.key)
    if !list_effective_slice_matches_v4(initial, read.observed, 0) {
      list_effective_gap_v4(index, read, "missing-or-reordered-initial-prefix")
      continue
    }
    let present : Map[Int32, Bool] = Map([])
    let projections : Map[String, Array[Int32]] = Map([])
    let mut reason = ""
    for item_index in read.observed {
      if !list_effective_charge_v4(budget) {
        return index
      }
      if item_index < 0 {
        reason = "missing-item-source"
        break
      }
      let item = parsed.items[item_index]
      if present.contains(item_index) {
        reason = "duplicate-list-identity"
        break
      }
      present[item_index] = true
      if item.key != read.key || item.seq >= read.seq {
        reason = "missing-or-wrong-item-source"
        break
      }
      match item.tx {
        Some(writer) if writer == read.tx =>
          if !read.own_at_read.contains(item_index) {
            reason = "own-item-not-active-at-read"
            break
          }
        Some(writer) => {
          if index.outcomes.get(writer) != Some(Committed) {
            reason = "external-writer-not-committed"
            break
          }
          if !index.active_set[item_index] {
            reason = "external-revoked-append-source"
            break
          }
          let projection = projections.get_or_default(writer, [])
          projection.push(item_index)
          projections[writer] = projection
        }
        None => ()
      }
    }
    if reason == "" {
      let start = read.observed.length() - read.own_at_read.length()
      if !list_effective_slice_matches_v4(
          read.own_at_read,
          read.observed,
          start,
        ) {
        reason = "own-effective-append-suffix-mismatch"
      }
    }
    if reason == "" {
      let groups = index.groups.get_or_default(read.key, Map([]))
      for writer, observed in projections {
        let final_items = groups.get_or_default(writer, [])
        if !list_effective_slice_matches_v4(observed, final_items, 0) {
          reason = "missing-or-reordered-writer-prefix"
          break
        }
        if observed.length() < final_items.length() {
          reason = "external-intermediate-list-prefix"
          break
        }
      }
    }
    if reason != "" {
      list_effective_gap_v4(index, read, reason)
    } else {
      read.usable = true
      read.reason = "complete"
    }
  }
  index.reads_complete = true
  index
}

///|
fn list_effective_edge_v4(
  from : String,
  to : String,
  kind : Dependency,
  key : String,
  first : String,
  last : String,
) -> Edge {
  {
    from,
    to,
    kind,
    key: Some(key),
    from_op: None,
    to_op: None,
    from_version: Some(first),
    to_version: Some(last),
    reason: match kind {
      WW =>
        "A complete external read prefix proves this committed append identity order"
      WR =>
        "The complete read contains this committed effective append identity"
      _ =>
        "The complete read omits this other transaction's committed effective append identity"
    },
  }
}

///|
fn list_effective_emit_v4(
  edges : Array[Edge],
  sources : Map[Edge, Array[Json]],
  budget : EffectiveListBudgetV4,
  edge : Edge,
  proof : Json,
) -> Bool {
  if edge.from == edge.to {
    return true
  }
  if !list_effective_charge_v4(budget) {
    return false
  }
  if !classification_models_v3_add_list_edge(edges, sources, edge, proof) {
    budget.limited = true
    budget.reason = "list-effective-edge-budget-50000"
    false
  } else {
    true
  }
}

///|
fn list_effective_ww_v4(
  index : EffectiveListIndexV4,
  edges : Array[Edge],
  sources : Map[Edge, Array[Json]],
  budget : EffectiveListBudgetV4,
  read : EffectiveListReadV4,
  left : Int32,
  right : Int32,
  basis : String,
) -> Bool {
  let first = index.parsed.items[left]
  let last = index.parsed.items[right]
  list_effective_emit_v4(
    edges,
    sources,
    budget,
    list_effective_edge_v4(
      first.tx.unwrap(),
      last.tx.unwrap(),
      WW,
      read.key,
      first.id,
      last.id,
    ),
    {
      "basis": Json(basis),
      "readSeq": Json(read.seq.to_double()),
      "fromAppendSeq": Json(first.seq.to_double()),
      "toAppendSeq": Json(last.seq.to_double()),
      "fromItem": Json(first.id),
      "toItem": Json(last.id),
    },
  )
}

///|
fn list_effective_item_order_v4(
  index : EffectiveListIndexV4,
  edges : Array[Edge],
  budget : EffectiveListBudgetV4,
) -> Map[String, Bool]? {
  let count = index.active.length()
  let positions : Map[String, Int32] = Map([])
  for position, item in index.active {
    if !list_effective_charge_v4(budget) {
      return None
    }
    positions[index.parsed.items[item].id] = position
  }
  let adjacent : Array[Array[Int32]] = Array::makei(count, _ => [])
  let incoming = FixedArray::make(count, 0)
  for proof in index.intrinsic {
    if !list_effective_charge_v4(budget) {
      return None
    }
    let fields = object_fields_unchecked_v3(proof)
    let first = match fields.at("fromItem") {
      String(id) => positions.at(id)
      _ => -1
    }
    let last = match fields.at("toItem") {
      String(id) => positions.at(id)
      _ => -1
    }
    if first < 0 || last < 0 {
      budget.reason = "invalid-effective-item-order-proof"
      return None
    }
    adjacent[first].push(last)
    incoming[last] += 1
  }
  for edge in edges {
    if !list_effective_charge_v4(budget) {
      return None
    }
    if edge.kind != WW {
      continue
    }
    let first = positions.get_or_default(edge.from_version.unwrap(), -1)
    let last = positions.get_or_default(edge.to_version.unwrap(), -1)
    if first < 0 || last < 0 {
      budget.reason = "invalid-effective-item-order-proof"
      return None
    }
    adjacent[first].push(last)
    incoming[last] += 1
  }
  let queue = FixedArray::make(count, 0)
  let mut head = 0
  let mut tail = 0
  for position in 0..<count {
    if !list_effective_charge_v4(budget) {
      return None
    }
    if incoming[position] == 0 {
      queue[tail] = position
      tail += 1
    }
  }
  while head < tail {
    if !list_effective_charge_v4(budget) {
      return None
    }
    let position = queue[head]
    head += 1
    for target in adjacent[position] {
      if !list_effective_charge_v4(budget) {
        return None
      }
      incoming[target] -= 1
      if incoming[target] == 0 {
        queue[tail] = target
        tail += 1
      }
    }
  }
  let incompatible : Map[String, Bool] = Map([])
  for position, item in index.active {
    if !list_effective_charge_v4(budget) {
      return None
    }
    if incoming[position] > 0 {
      incompatible[index.parsed.items[item].key] = true
    }
  }
  Some(incompatible)
}

///|
fn list_effective_quarantine_v4(
  edges : Array[Edge],
  sources : Map[Edge, Array[Json]],
  keys : Map[String, Bool]?,
  quarantined : Array[Json],
  reason : String,
) -> Unit {
  let retained : Array[Edge] = []
  for edge in edges {
    let blocked = match keys {
      None => true
      Some(keys) =>
        match edge.key {
          Some(key) => keys.contains(key)
          None => true
        }
    }
    if blocked {
      quarantined.push({
        "reason": Json(reason),
        "edge": edge_json(edge),
        "sources": Json(sources.get_or_default(edge, [])),
      })
      let _ = sources.remove(edge)
    } else {
      retained.push(edge)
    }
  }
  while !edges.is_empty() {
    let _ = edges.pop()
  }
  for edge in retained {
    edges.push(edge)
  }
}

///|
fn list_effective_order_checks_v4(
  index : EffectiveListIndexV4,
  edges : Array[Edge],
  budget : EffectiveListBudgetV4,
  blocked_keys~ : Map[String, Bool] = Map([]),
) -> (Bool, Array[Json]) {
  let orders : Array[Json] = []
  let mut complete = true
  for key, groups in index.groups {
    let writers = groups.keys().collect()
    writers.sort()
    if blocked_keys.contains(key) {
      complete = false
      orders.push({
        "key": Json(key),
        "transactions": Json(writers),
        "complete": false,
        "cyclic": Json::null(),
        "sourceOrderQuarantined": true,
      })
      continue
    }
    let positions : Map[String, Int32] = Map([])
    for position, writer in writers {
      positions[writer] = position
    }
    let size = writers.length()
    let adjacent : Array[Array[Int32]] = Array::makei(size, _ => [])
    for edge in edges {
      if !list_effective_charge_v4(budget) {
        return (false, orders)
      }
      if edge.kind == WW && edge.key == Some(key) {
        let from = positions.at(edge.from)
        let to = positions.at(edge.to)
        if !adjacent[from].contains(to) {
          adjacent[from].push(to)
        }
      }
    }
    let reach = FixedArray::make(size * size, false)
    let queue = FixedArray::make(size, 0)
    let mut cyclic = false
    for root in 0..<size {
      let seen = FixedArray::make(size, false)
      seen[root] = true
      queue[0] = root
      let mut head = 0
      let mut tail = 1
      while head < tail {
        if !list_effective_charge_v4(budget) {
          return (false, orders)
        }
        let vertex = queue[head]
        head += 1
        for target in adjacent[vertex] {
          if !list_effective_charge_v4(budget) {
            return (false, orders)
          }
          reach[root * size + target] = true
          if target == root {
            cyclic = true
          }
          if !seen[target] {
            seen[target] = true
            queue[tail] = target
            tail += 1
          }
        }
      }
    }
    let mut missing = false
    for first in 0..<size {
      for last in (first + 1)..<size {
        if !reach[first * size + last] && !reach[last * size + first] {
          missing = true
        }
      }
    }
    if cyclic || missing {
      complete = false
      index.gaps.push({
        "code": Json(
          if cyclic {
            "incompatible-effective-transaction-order"
          } else {
            "missing-effective-transaction-order"
          },
        ),
        "key": Json(key),
      })
    }
    orders.push({
      "key": Json(key),
      "transactions": Json(writers),
      "complete": Json(!cyclic && !missing),
      "cyclic": Json(cyclic),
    })
  }
  (complete, orders)
}

///|
/// Opt-in graph adapter. It never edits v3 observations, effects or programs.
fn list_graph_effective_v4(
  parsed : ListV3Parsed,
  max_checks~ : Int32 = 1000000,
) -> EffectiveListGraphV4 {
  let budget : EffectiveListBudgetV4 = {
    maximum: max_checks,
    checks: 0,
    limited: false,
    reason: "complete",
  }
  let valid = max_checks >= 0 && max_checks <= 1000000
  let capacity = parsed.programs.length() <= 128 && parsed.operations <= 4096
  let index = if valid && capacity {
    list_effective_index_v4(parsed, budget)
  } else {
    list_effective_empty_index_v4(parsed)
  }
  let transactions : Array[Transaction] = parsed.programs.map(program => {
    id: program.id,
    status: program.status,
    ops: [],
    start: None,
    end: None,
  })
  let edges : Array[Edge] = []
  let sources : Map[Edge, Array[Json]] = Map([])
  let ready = object_fields_unchecked_v3(parsed.normalized).get("status") ==
    Some(Json("ready"))
  let mut reason = if !valid {
    "invalid-list-effective-budget"
  } else if !capacity {
    "list-effective-capacity-128-4096"
  } else if budget.limited {
    budget.reason
  } else if !index.journal_complete {
    if budget.limited {
      budget.reason
    } else {
      "list-effective-journal-incomplete"
    }
  } else if !ready {
    "list-effective-source-coverage-incomplete"
  } else {
    "complete"
  }
  if reason == "complete" {
    let mut stopped = false
    for read in index.reads {
      if !read.usable {
        continue
      }
      let present : Map[Int32, Bool] = Map([])
      for item in read.observed {
        present[item] = true
      }
      let active = index.active.filter(item => {
        parsed.items[item].key == read.key
      })
      for item_index in active {
        let item = parsed.items[item_index]
        let writer = item.tx.unwrap()
        if writer == read.tx {
          continue
        }
        let contained = present.contains(item_index)
        let edge = if contained {
          list_effective_edge_v4(
            writer,
            read.tx,
            WR,
            read.key,
            item.id,
            item.id,
          )
        } else {
          list_effective_edge_v4(
            read.tx,
            writer,
            RW,
            read.key,
            "list-read-" + read.seq.to_string(),
            item.id,
          )
        }
        if !list_effective_emit_v4(edges, sources, budget, edge, {
            "basis": "complete-effective-list-read",
            "readProjection": "external-base-with-effective-own-suffix-removed",
            "ownAtRead": Json(
              list_effective_item_ids_v4(parsed, read.own_at_read),
            ),
            "readSeq": Json(read.seq.to_double()),
            "appendSeq": Json(item.seq.to_double()),
            "itemId": Json(item.id),
          }) {
          stopped = true
          break
        }
      }
      if stopped {
        break
      }
      // Own reads can expose a provisional local suffix. That suffix validates
      // the delivered read but is not a committed cross-transaction WW order.
      for position, left in read.observed {
        if left < 0 ||
          !index.active_set[left] ||
          parsed.items[left].tx == Some(read.tx) {
          continue
        }
        for right_position in (position + 1)..<read.observed.length() {
          let right = read.observed[right_position]
          if right < 0 ||
            !index.active_set[right] ||
            parsed.items[right].tx == Some(read.tx) {
            continue
          }
          if !list_effective_ww_v4(
              index, edges, sources, budget, read, left, right, "complete-observed-item-order",
            ) {
            stopped = true
            break
          }
        }
        if stopped {
          break
        }
        for right in active {
          if present.contains(right) || parsed.items[right].tx == Some(read.tx) {
            continue
          }
          if !list_effective_ww_v4(
              index, edges, sources, budget, read, left, right, "complete-read-prefix-before-omitted-append",
            ) {
            stopped = true
            break
          }
        }
        if stopped {
          break
        }
      }
      if stopped {
        break
      }
    }
    if budget.limited {
      reason = budget.reason
    }
  }
  let quarantined : Array[Json] = []
  let blocked_keys : Map[String, Bool] = Map([])
  let mut item_order_validated = false
  if reason == "complete" {
    match list_effective_item_order_v4(index, edges, budget) {
      Some(incompatible) => {
        item_order_validated = true
        for key, _ in incompatible {
          blocked_keys[key] = true
          index.gaps.push({
            "code": "incompatible-effective-item-order",
            "key": Json(key),
            "scope": "source item order, not a WW transaction-cycle certificate",
          })
        }
        if !incompatible.is_empty() {
          list_effective_quarantine_v4(
            edges,
            sources,
            Some(incompatible),
            quarantined,
            "incompatible-effective-item-order",
          )
          for read in index.reads {
            if incompatible.contains(read.key) && read.usable {
              read.usable = false
              read.reason = "incompatible-effective-item-order"
            }
          }
        }
      }
      None => {
        reason = budget.reason
        list_effective_quarantine_v4(
          edges,
          sources,
          None,
          quarantined,
          "effective-item-order-not-verified",
        )
      }
    }
  } else if budget.limited {
    list_effective_quarantine_v4(
      edges,
      sources,
      None,
      quarantined,
      "effective-item-order-not-verified",
    )
  }
  let (ordered, orders) = if reason == "complete" {
    list_effective_order_checks_v4(index, edges, budget, blocked_keys~)
  } else {
    (false, [])
  }
  if budget.limited {
    reason = budget.reason
  }
  let complete = reason == "complete" && ordered && index.gaps.is_empty()
  if reason == "complete" && !complete {
    reason = "list-effective-order-or-read-validity-incomplete"
  }
  {
    base: {
      normalized: parsed.normalized,
      transactions,
      edges,
      sources,
      validity_gaps: index.gaps,
      history: None,
      list_parsed: Some(parsed),
      complete,
      reason,
    },
    index,
    orders,
    quarantined,
    item_order_validated,
    checks: budget.checks,
    maximum: max_checks,
    limited: budget.limited,
  }
}

///|
fn list_graph_effective_v4_summary_json(result : EffectiveListGraphV4) -> Json {
  let index = result.index
  let groups : Array[Json] = []
  if index.journal_complete {
    for key, writers in index.groups {
      for writer, items in writers {
        groups.push({
          "key": Json(key),
          "transaction": Json(writer),
          "items": Json(list_effective_item_ids_v4(index.parsed, items)),
        })
      }
    }
  }
  let record : Json = {
    "algorithm": "list-effective-append-graph-1",
    "indexAlgorithm": "list-effective-append-journal-1",
    "complete": Json(result.base.complete),
    "reason": Json(result.base.reason),
    "journalComplete": Json(index.journal_complete),
    "readIndexComplete": Json(index.reads_complete),
    "effectiveGroups": Json(groups),
    "programOrders": Json(index.intrinsic),
    "readStates": Json(
      index.reads.map(read => {
        (
          {
            "transaction": Json(read.tx),
            "key": Json(read.key),
            "readSeq": Json(read.seq.to_double()),
            "observed": Json(
              read.observed.map(item => {
                if item < 0 {
                  Json::null()
                } else {
                  Json(index.parsed.items[item].id)
                }
              }),
            ),
            "ownAtRead": Json(
              list_effective_item_ids_v4(index.parsed, read.own_at_read),
            ),
            "usable": Json(read.usable),
            "reason": Json(read.reason),
          } : Json)
      }),
    ),
    "orders": Json(result.orders),
    "itemOrderValidated": Json(result.item_order_validated),
    "quarantinedDependencies": Json(result.quarantined),
    "gaps": Json(index.gaps),
    "execution": {
      "constructionChecks": Json(result.checks),
      "limited": Json(result.limited),
      "counterContract": "list-effective-construction-checks-1",
      "limits": {
        "transactions": 128,
        "operations": 4096,
        "edges": 50000,
        "constructionChecks": Json(result.maximum),
      },
    },
  }
  record
}

///|
pub fn list_graph_effective_v4_json(result : EffectiveListGraphV4) -> Json {
  let record = list_graph_effective_v4_summary_json(result)
  let fields = object_fields_unchecked_v3(record)
  fields["edges"] = Json(result.base.edges.map(edge_json))
  fields["edgeSources"] = Json(
    result.base.edges.map(edge => {
      (
        {
          "edge": edge_json(edge),
          "sources": Json(result.base.sources.get_or_default(edge, [])),
        } : Json)
    }),
  )
  v4_json_copy(record)
}

///|
/// Explicit low-level opt-in builder; classification defaults stay unchanged.
pub fn build_list_graph_effective_v4(
  history : HistoryV4,
  max_checks~ : Int32 = 1000000,
) -> Result[EffectiveListGraphV4, String] {
  if max_checks < 0 || max_checks > 1000000 {
    return Err("Effective list graph budget must be within 0..1000000")
  }
  match history.payload {
    ListSnapshot(parsed) => Ok(list_graph_effective_v4(parsed, max_checks~))
    _ => Err("Effective list graph requires an append-list-v1 capture")
  }
}
