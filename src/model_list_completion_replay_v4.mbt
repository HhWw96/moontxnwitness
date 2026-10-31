///|
fn model_list_replay_context_v4(
  parsed : ListV3Parsed,
  state : Map[String, Array[Int32]],
  remaining : Int32,
) -> ListV3Search {
  let detached : Map[String, Array[Int32]] = Map([])
  for key, items in state {
    detached[key] = items.copy()
  }
  {
    programs: parsed.programs,
    items: parsed.items,
    state: detached,
    trail: [],
    prefix: [],
    blockers: [],
    options: { max_states: 0, max_operations: remaining, },
    states: 0,
    operations: 0,
    limited: false,
    reason: "complete",
  }
}

///|
/// Linear validation of one supplied CO/VIS, not the six-transaction enumerator.
/// The unchanged typed list interpreter executes all actual original reads.
fn model_list_certificate_replay_v4(
  parsed : ListV3Parsed,
  commit_order : Array[String],
  visibility : Array[Json],
  maximum : Int32,
) -> ModelRuleV4 {
  let id = "original-list-program-prefix-replay"
  let budget : ModelSourceBudgetV4 = { maximum, checks: 0, limited: false, }
  let programs : Map[String, ListV3Program] = Map([])
  let deltas : Map[String, Map[String, Array[Int32]]] = Map([])
  let empty : Map[String, Array[Int32]] = Map([])
  let blockers : Array[Json] = []
  let mut valid = maximum >= 0 && maximum <= 1000000
  for key, _ in parsed.initial {
    empty[key] = []
  }
  for program in parsed.programs {
    if !model_source_charge_v4(budget) {
      valid = false
      break
    }
    if program.status != Committed {
      continue
    }
    programs[program.id] = program
    // This effect-only pass computes surviving appended IDs. Every delivered
    // read is checked separately below against the selected original snapshot.
    let effect : ListV3Program = {
      ..program,
      actions: program.actions.filter(a => {
        match a {
          ReadList(_, _, _) => false
          _ => true
        }
      }),
    }
    let ctx = model_list_replay_context_v4(
      parsed,
      empty,
      maximum - budget.checks,
    )
    let ok = list_v3_execute(ctx, effect)
    budget.checks += ctx.operations
    if !ok || ctx.limited {
      valid = false
      budget.limited = ctx.limited
      break
    }
    deltas[program.id] = ctx.state
  }
  let ranks : Map[String, Int32] = Map([])
  if commit_order.length() != programs.length() {
    valid = false
  }
  for i, tx in commit_order {
    if !model_source_charge_v4(budget) {
      valid = false
      break
    }
    if !programs.contains(tx) || ranks.contains(tx) {
      valid = false
      break
    }
    ranks[tx] = i
  }
  let prefixes : Map[String, Int32] = Map([])
  for raw in visibility {
    if !model_source_charge_v4(budget) {
      valid = false
      break
    }
    let r = object_fields_unchecked_v3(raw)
    let tx = capture_source_string_v4(r.at("transaction"))
    let count = capture_source_seq_v4(r.at("visiblePrefixLength")).to_int()
    let seen = capture_source_array_v4(r.at("visibleTransactions"))
    if !ranks.contains(tx) ||
      prefixes.contains(tx) ||
      count < 0 ||
      count > ranks.get_or_default(tx, -1) ||
      seen.length() != count {
      valid = false
      break
    }
    for i in 0..<count {
      if !model_source_charge_v4(budget) {
        valid = false
        break
      }
      if seen[i] != Json(commit_order[i]) {
        valid = false
      }
    }
    prefixes[tx] = count
  }
  if prefixes.length() != programs.length() {
    valid = false
  }
  let completed : Array[String] = []
  let last_writer : Map[String, String] = Map([])
  if valid && !budget.limited {
    for tx in commit_order {
      if !model_source_charge_v4(budget) {
        valid = false
        break
      }
      let snapshot : Map[String, Array[Int32]] = Map([])
      for key, items in parsed.initial {
        snapshot[key] = items.copy()
      }
      for i in 0..<prefixes.at(tx) {
        if !model_source_charge_v4(budget) {
          valid = false
          break
        }
        for key, items in deltas.at(commit_order[i]) {
          let list = snapshot.at(key)
          for item in items {
            if !model_source_charge_v4(budget) {
              valid = false
              break
            }
            list.push(item)
          }
        }
      }
      if !valid {
        break
      }
      for key, items in deltas.at(tx) {
        if !model_source_charge_v4(budget) {
          valid = false
          break
        }
        if items.is_empty() {
          continue
        }
        match last_writer.get(key) {
          Some(previous) if ranks.at(previous) >= prefixes.at(tx) => {
            valid = false
            blockers.push({
              "code": "snapshot-write-conflict",
              "transaction": Json(tx),
              "key": Json(key),
              "previousWriter": Json(previous),
            })
          }
          _ => ()
        }
        last_writer[key] = tx
      }
      if !valid {
        break
      }
      let ctx = model_list_replay_context_v4(
        parsed,
        snapshot,
        maximum - budget.checks,
      )
      let ok = list_v3_execute(ctx, programs.at(tx))
      budget.checks += ctx.operations
      if !ok || ctx.limited {
        valid = false
        budget.limited = ctx.limited
        blockers.append(ctx.blockers)
        break
      }
      completed.push(tx)
    }
  }
  model_rule_v4(
    id,
    if valid && !budget.limited {
      "checked-compatible"
    } else {
      "unknown"
    },
    "the original append/read/savepoint programs execute against the emitted visible prefixes; this is linear certificate replay and grants no extra enumeration capacity",
    evidence={
      "definition": "original-list-program-CO-VIS-replay/v1",
      "committedProgramsReplayed": Json(completed),
      "retainsEveryDeliveredRead": true,
      "enumeratedTransactionOrders": false,
      "blockers": Json(blockers),
      "execution": model_mapping_counter_v4(
        budget, "list-original-program-prefix-replay-checks-1",
      ),
    },
  )
}
