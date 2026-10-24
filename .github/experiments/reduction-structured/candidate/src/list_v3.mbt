///|
priv struct ListV3Item {
  id : String
  value : String
  key : String
  tx : String?
  seq : Int64
}

///|
priv enum ListV3Action {
  Append(String, Int)
  ReadList(String, Array[Int], Int64)
  Mark(String)
  Undo(String)
  Release(String)
}

///|
priv struct ListV3Program {
  id : String
  status : TxStatus
  actions : Array[ListV3Action]
}

///|
priv struct ListV3Parsed {
  normalized : Json
  initial : Map[String, Array[Int]]
  items : Array[ListV3Item]
  programs : Array[ListV3Program]
  findings : Array[Json]
  source_evidence : Array[Json]
  operations : Int
}

///|
priv struct ListV3Options {
  max_states : Int
  max_operations : Int
}

///|
priv struct ListV3Search {
  programs : Array[ListV3Program]
  items : Array[ListV3Item]
  state : Map[String, Array[Int]]
  trail : Array[String]
  prefix : Array[String]
  blockers : Array[Json]
  options : ListV3Options
  mut states : Int
  mut operations : Int
  mut limited : Bool
  mut reason : String
}

///|
fn list_v3_value(value : Json) -> String raise {
  match value {
    String(value) => value
    _ => fail("append-list-v1 business values must be JSON strings")
  }
}

///|
fn list_v3_item(
  value : Json,
  key : String,
  tx : String?,
  seq : Int64,
) -> ListV3Item raise {
  let fields = object_fields(value, "list item")
  known_fields(fields, ["id", "value"], "list item")
  {
    id: identifier(required(fields, "id", "list item"), "item.id"),
    value: list_v3_value(required(fields, "value", "list item")),
    key,
    tx,
    seq,
  }
}

///|
fn list_v3_copy(event : Map[String, Json]) -> Map[String, Json] {
  let result : Map[String, Json] = Map([])
  for key, value in event {
    result[key] = value
  }
  result
}

///|
fn list_v3_finding(
  code : String,
  tx : String,
  seq : Int64,
  key : String,
  id : String,
) -> Json {
  {
    "code": code.to_json(),
    "tx": tx.to_json(),
    "readSeq": seq.to_double().to_json(),
    "key": key.to_json(),
    "itemId": id.to_json(),
  }
}

///|
fn list_v3_invalid(text : String, message : String) -> Json {
  let observations = try {
    let root = object_fields(guarded_json(text, limit=8388608), "trace")
    root.get_or_default("events", Json::null())
  } catch {
    _ => Json::null()
  }
  {
    "schema": 3,
    "dataModel": "append-list-v1",
    "algorithm": "v3-list-lifecycle-1",
    "status": "invalid",
    "coverage": {
      "complete": false,
      "gaps": [capture_gap("invalid_list_capture_v3", message)],
    },
    "observations": observations,
    "effects": [],
    "transactions": [],
    "history": Json::null(),
    "error": message.to_json(),
  }
}

///|
fn list_v3_parse(text : String, v? : Json) -> ListV3Parsed raise {
  let root = object_fields(v3_guarded_candidate(text, v), "list trace")
  known_fields(
    root,
    ["traceSchema", "dataModel", "clockDomain", "scope", "events", "gaps"],
    "list trace",
  )
  if required(root, "traceSchema", "list trace") != (3).to_json() ||
    required(root, "dataModel", "list trace") != "append-list-v1".to_json() {
    fail("Expected traceSchema 3 and dataModel append-list-v1")
  }
  let observations = required(root, "events", "list trace")
  let events = presence_capture_array(observations, "events")
  if events.length() > 65536 {
    fail("At most 65,536 list events are supported")
  }
  let initial : Map[String, Array[Int]] = Map([])
  let items : Array[ListV3Item] = []
  let ids : Map[String, Int] = Map([])
  let append_indices : Map[Int64, Int] = Map([])
  let lifecycle_initial : Map[String, String] = Map([])
  let metadata : Array[Json] = []
  let mut operations = 0
  let mut append_count = 0
  let mut needs_sentinel = false
  let mut snapshot_seen = false
  for raw in events {
    let e = object_fields(raw, "event")
    let kind = identifier(required(e, "kind", "event"), "event.kind")
    let seq = v3_capture_seq(required(e, "seq", "event"), "event.seq")
    if kind == "snapshot" {
      known_fields(
        e,
        ["seq", "time", "kind", "initial", "consistent"],
        "snapshot",
      )
      if snapshot_seen {
        fail("Exactly one list snapshot is required")
      }
      snapshot_seen = true
      let raw_initial = object_fields(
        required(e, "initial", "snapshot"),
        "initial",
      )
      if raw_initial.length() > 10000 {
        fail("At most 10,000 initialized list keys are supported")
      }
      for key, raw_list in raw_initial {
        let _ = identifier(key.to_json(), "initial key")
        let list : Array[Int] = []
        for value in presence_capture_array(raw_list, "initial list") {
          let item = list_v3_item(value, key, None, seq)
          if ids.contains(item.id) {
            fail("Initial and append identities must be globally unique")
          }
          ids[item.id] = items.length()
          list.push(items.length())
          items.push(item)
          if items.length() > 10000 {
            fail("At most 10,000 list identities are supported")
          }
        }
        initial[key] = list
      }
    } else if kind == "append" {
      known_fields(
        e,
        ["seq", "time", "kind", "tx", "key", "id", "value"],
        "append",
      )
      let key = identifier(required(e, "key", "append"), "append.key")
      let id = identifier(required(e, "id", "append"), "append.id")
      let tx = identifier(required(e, "tx", "append"), "append.tx")
      let value = list_v3_value(required(e, "value", "append"))
      if ids.contains(id) {
        fail("Initial and append identities must be globally unique")
      }
      append_indices[seq] = items.length()
      ids[id] = items.length()
      items.push({ id, value, key, tx: Some(tx), seq, })
      append_count += 1
      operations += 1
      if items.length() > 10000 {
        fail("At most 10,000 list identities are supported")
      }
    } else if kind == "list_read" {
      known_fields(
        e,
        ["seq", "time", "kind", "tx", "key", "items"],
        "list_read",
      )
      let _ = identifier(required(e, "tx", "list_read"), "list_read.tx")
      let key = identifier(required(e, "key", "list_read"), "list_read.key")
      for
        value in presence_capture_array(
          required(e, "items", "list_read"),
          "list_read.items",
        ) {
        let _ = list_v3_item(value, key, None, seq)
      }
      needs_sentinel = true
      operations += 1
    } else if kind == "read" || kind == "write" {
      fail("Register and append-list operations cannot be mixed")
    }
  }
  if operations > 10000 {
    fail("At most 10,000 list appends and reads are supported")
  }
  // The adapter checks only lifecycle/scopes. Its bookkeeping registers are
  // never model data, never analyzed, and never exported as observations/facts.
  for index in 0..<append_count {
    lifecycle_initial["list-life-key-" + index.to_string()] = "list-life-initial-" +
      index.to_string()
  }
  if needs_sentinel {
    lifecycle_initial["list-life-read-key"] = "list-life-read-initial"
  }
  let mut append_number = 0
  for raw in events {
    let e = object_fields(raw, "event")
    let kind = identifier(required(e, "kind", "event"), "event.kind")
    let copy = list_v3_copy(e)
    if kind == "snapshot" {
      copy["initial"] = lifecycle_initial.to_json()
      metadata.push(Json::object(copy))
    } else if kind == "append" {
      metadata.push({
        "seq": required(e, "seq", "append"),
        "time": required(e, "time", "append"),
        "kind": "write",
        "tx": required(e, "tx", "append"),
        "key": ("list-life-key-" + append_number.to_string()).to_json(),
        "version": ("list-life-write-" + append_number.to_string()).to_json(),
        "predecessor": ("list-life-initial-" + append_number.to_string()).to_json(),
      })
      append_number += 1
    } else if kind == "list_read" {
      metadata.push({
        "seq": required(e, "seq", "list_read"),
        "time": required(e, "time", "list_read"),
        "kind": "read",
        "tx": required(e, "tx", "list_read"),
        "key": "list-life-read-key",
        "version": "list-life-read-initial",
      })
    } else if kind == "condition" {
      known_fields(
        e,
        ["seq", "time", "kind", "tx", "predicate", "matched", "sourceVersion"],
        "condition",
      )
      // Unsupported condition semantics remain a gap, without treating a list
      // element identity as a synthetic register version.
      let condition : Map[String, Json] = Map([])
      for key, value in copy {
        if key != "sourceVersion" {
          condition[key] = value
        }
      }
      match e.get("sourceVersion") {
        Some(value) => {
          let _ = identifier(value, "condition.sourceVersion")
        }
        None => ()
      }
      metadata.push(Json::object(condition))
    } else {
      metadata.push(Json::object(copy))
    }
  }
  let life_trace : Json = {
    "traceSchema": 3,
    "clockDomain": required(root, "clockDomain", "list trace"),
    "scope": required(root, "scope", "list trace"),
    "events": metadata.to_json(),
    "gaps": required(root, "gaps", "list trace"),
  }
  let life = object_fields(
    guarded_json(
      normalize_register_capture_v3_json(life_trace.stringify()),
      limit=33554432,
    ),
    "lifecycle",
  )
  let status = required(life, "status", "lifecycle")
  let coverage = object_fields(
    required(life, "coverage", "lifecycle"),
    "coverage",
  )
  let gaps = presence_capture_array(
    required(coverage, "gaps", "coverage"),
    "gaps",
  ).copy()
  let transactions = presence_capture_array(
    required(life, "transactions", "lifecycle"),
    "transactions",
  )
  let outcomes : Map[String, TxStatus] = Map([])
  let programs : Array[ListV3Program] = []
  let program_ids : Map[String, Int] = Map([])
  for raw_tx in transactions {
    let tx = object_fields(raw_tx, "transaction")
    let id = identifier(required(tx, "id", "transaction"), "transaction.id")
    let outcome = match required(tx, "status", "transaction") {
      String("committed") => Committed
      String("aborted") => Aborted
      _ => Unknown
    }
    outcomes[id] = outcome
    program_ids[id] = programs.length()
    programs.push({ id, status: outcome, actions: [], })
  }
  let effects : Array[Json] = []
  let revoked : Map[Int64, Int64?] = Map([])
  for
    raw_effect in presence_capture_array(
      required(life, "effects", "lifecycle"),
      "effects",
    ) {
    let effect = object_fields(raw_effect, "effect")
    let seq = v3_capture_seq(required(effect, "seq", "effect"), "effect.seq")
    let index = append_indices.get(seq).unwrap()
    let item = items[index]
    let reverted = required(effect, "revertedBy", "effect")
    revoked[seq] = match reverted {
      Null => None
      value => Some(v3_capture_seq(value, "revertedBy"))
    }
    effects.push({
      "seq": seq.to_double().to_json(),
      "tx": item.tx.unwrap().to_json(),
      "key": item.key.to_json(),
      "id": item.id.to_json(),
      "value": item.value.to_json(),
      "revertedBy": reverted,
    })
  }
  let findings : Array[Json] = []
  let mut read_items = 0
  for raw in events {
    let e = object_fields(raw, "event")
    let kind = identifier(required(e, "kind", "event"), "event.kind")
    if !["append", "list_read", "savepoint", "rollback_to", "release"].contains(
        kind,
      ) {
      continue
    }
    let tx = identifier(required(e, "tx", "event"), "event.tx")
    let seq = v3_capture_seq(required(e, "seq", "event"), "event.seq")
    let program = match program_ids.get(tx) {
      Some(index) => programs[index]
      None => continue
    }
    match kind {
      "append" => {
        let index = append_indices.get(seq).unwrap()
        let item = items[index]
        if !initial.contains(item.key) {
          gaps.push(
            capture_gap(
              "missing_initial", "An appended list has no captured initial state",
            ),
          )
        }
        program.actions.push(Append(item.key, index))
      }
      "list_read" => {
        let key = identifier(required(e, "key", "list_read"), "list_read.key")
        if !initial.contains(key) {
          gaps.push(
            capture_gap(
              "missing_initial", "A read list has no captured initial state",
            ),
          )
        }
        let expected : Array[Int] = []
        let seen : Map[String, Bool] = Map([])
        for
          raw_item in presence_capture_array(
            required(e, "items", "list_read"),
            "items",
          ) {
          read_items += 1
          if read_items > 100000 {
            fail("At most 100,000 returned list item references are supported")
          }
          let observed = list_v3_item(raw_item, key, None, seq)
          if seen.contains(observed.id) && program.status == Committed {
            findings.push(
              list_v3_finding("duplicate_list_item", tx, seq, key, observed.id),
            )
          }
          seen[observed.id] = true
          match ids.get(observed.id) {
            None => {
              gaps.push(
                capture_gap(
                  "missing_item_source", "A returned item has no captured source",
                ),
              )
              expected.push(-1)
            }
            Some(index) => {
              let source = items[index]
              expected.push(index)
              if source.seq >= seq {
                gaps.push(
                  capture_gap(
                    "missing_item_source", "An item producer was not observed before the read",
                  ),
                )
              }
              if program.status == Committed {
                if source.key != key {
                  findings.push(
                    list_v3_finding(
                      "item_key_mismatch",
                      tx,
                      seq,
                      key,
                      source.id,
                    ),
                  )
                }
                if source.value != observed.value {
                  findings.push(
                    list_v3_finding(
                      "item_value_mismatch",
                      tx,
                      seq,
                      key,
                      source.id,
                    ),
                  )
                }
                match source.tx {
                  None => ()
                  Some(writer) => {
                    if writer != tx && outcomes.get(writer) == Some(Aborted) {
                      findings.push(
                        list_v3_finding(
                          "read_from_aborted_append",
                          tx,
                          seq,
                          key,
                          source.id,
                        ),
                      )
                    }
                    match revoked.get(source.seq) {
                      Some(Some(at)) if writer != tx || at < seq =>
                        findings.push(
                          list_v3_finding(
                            "read_from_reverted_append",
                            tx,
                            seq,
                            key,
                            source.id,
                          ),
                        )
                      _ => ()
                    }
                  }
                }
              }
            }
          }
        }
        program.actions.push(ReadList(key, expected, seq))
      }
      "savepoint" =>
        program.actions.push(
          Mark(identifier(required(e, "instance", kind), "instance")),
        )
      "rollback_to" =>
        program.actions.push(
          Undo(identifier(required(e, "instance", kind), "instance")),
        )
      "release" =>
        program.actions.push(
          Release(identifier(required(e, "instance", kind), "instance")),
        )
      _ => ()
    }
  }
  let source_evidence = items.map(item => {
    (
      {
        "id": item.id.to_json(),
        "value": item.value.to_json(),
        "key": item.key.to_json(),
        "sourceSeq": item.seq.to_double().to_json(),
        "writer": match item.tx {
          None => Json::null()
          Some(id) => id.to_json()
        },
        "revertedBy": match revoked.get(item.seq) {
          Some(Some(seq)) => seq.to_double().to_json()
          _ => Json::null()
        },
      } : Json)
  })
  let final_status = if status == "invalid".to_json() {
    "invalid"
  } else if gaps.length() > 0 {
    "inconclusive"
  } else {
    "ready"
  }
  let normalized : Json = {
    "schema": 3,
    "dataModel": "append-list-v1",
    "algorithm": "v3-list-lifecycle-1",
    "status": final_status.to_json(),
    "coverage": {
      "complete": (final_status == "ready").to_json(),
      "gaps": gaps.to_json(),
    },
    "observations": observations,
    "effects": effects.to_json(),
    "transactions": transactions.to_json(),
    "history": Json::null(),
  }
  {
    normalized,
    initial,
    items,
    programs,
    findings,
    source_evidence,
    operations,
  }
}

///|
pub fn normalize_list_capture_v3_json(text : String) -> String {
  list_v3_parse(text).normalized.stringify(indent=2) catch {
    error => list_v3_invalid(text, error.to_string()).stringify(indent=2)
  }
}

///|
fn list_v3_options(text : String) -> ListV3Options raise {
  let options = object_fields(guarded_json(text, limit=4096), "list options")
  known_fields(options, ["maxStates", "maxOperationChecks"], "list options")
  fn number(
    options : Map[String, Json],
    name : String,
    maximum : Int,
  ) -> Int raise {
    match options.get(name) {
      None => maximum
      Some(Number(n, ..)) if n >= 0.0 &&
        n <= maximum.to_double() &&
        n.to_int().to_double() == n => n.to_int()
      _ => fail("Invalid append-list search budget: " + name)
    }
  }
  {
    max_states: number(options, "maxStates", 100000),
    max_operations: number(options, "maxOperationChecks", 1000000),
  }
}

///|
fn list_v3_undo(ctx : ListV3Search, mark : Int) -> Unit {
  while ctx.trail.length() > mark {
    let key = ctx.trail.pop().unwrap()
    let _ = ctx.state.get(key).unwrap().pop()
  }
}

///|
fn list_v3_check_budget(ctx : ListV3Search) -> Bool {
  if ctx.operations >= ctx.options.max_operations {
    ctx.limited = true
    ctx.reason = "operation_budget"
    false
  } else {
    ctx.operations += 1
    true
  }
}

///|
fn list_v3_execute(ctx : ListV3Search, program : ListV3Program) -> Bool {
  let scopes : Array[(String, Int)] = []
  for action in program.actions {
    if !list_v3_check_budget(ctx) {
      return false
    }
    match action {
      Append(key, item) => {
        // Append-only state has a constant-size inverse: remove its last item.
        // No candidate prefix copies every list or every prior element.
        ctx.state.get(key).unwrap().push(item)
        ctx.trail.push(key)
      }
      ReadList(key, expected, seq) => {
        let current = ctx.state.get(key).unwrap()
        let mut same = current.length() == expected.length()
        if same {
          for index in 0..<expected.length() {
            if !list_v3_check_budget(ctx) {
              return false
            }
            if current[index] != expected[index] {
              same = false
              break
            }
          }
        }
        if !same {
          if ctx.blockers.length() < 16 {
            ctx.blockers.push({
              "tx": program.id.to_json(),
              "readSeq": seq.to_double().to_json(),
              "key": key.to_json(),
              "code": "list_state_mismatch",
              "actualIds": current.map(index => ctx.items[index].id).to_json(),
              "observedIds": expected
              .map(index => ctx.items[index].id)
              .to_json(),
            })
          }
          return false
        }
      }
      Mark(instance) => scopes.push((instance, ctx.trail.length()))
      Undo(instance) | Release(instance) => {
        let mut found = -1
        for index, scope in scopes {
          if scope.0 == instance {
            found = index
          }
        }
        // The independent lifecycle validator already checked these references.
        if found < 0 {
          ctx.limited = true
          ctx.reason = "invalid_scope_program"
          return false
        }
        match action {
          Undo(_) => list_v3_undo(ctx, scopes[found].1)
          _ => ()
        }
        let retained = match action {
          Undo(_) => found + 1
          _ => found
        }
        while scopes.length() > retained {
          let _ = scopes.pop()
        }
      }
    }
  }
  true
}

///|
fn list_v3_search(ctx : ListV3Search, selected : Int) -> Array[String]? {
  if ctx.prefix.length() == ctx.programs.length() {
    return Some(ctx.prefix.copy())
  }
  for index, program in ctx.programs {
    let bit = 1 << index
    if (selected & bit) != 0 {
      continue
    }
    if ctx.states >= ctx.options.max_states {
      ctx.limited = true
      ctx.reason = "state_budget"
      return None
    }
    ctx.states += 1
    let mark = ctx.trail.length()
    if list_v3_execute(ctx, program) {
      ctx.prefix.push(program.id)
      let found = list_v3_search(ctx, selected | bit)
      let _ = ctx.prefix.pop()
      list_v3_undo(ctx, mark)
      if found is Some(_) {
        return found
      }
    } else {
      list_v3_undo(ctx, mark)
    }
    if ctx.limited {
      return None
    }
  }
  None
}

///|
fn list_v3_report(
  normalized : Json,
  status : String,
  evidence : Json,
  options : ListV3Options,
  states : Int,
  operations : Int,
  complete : Bool,
  reason : String,
) -> Json {
  {
    "schemaVersion": 3,
    "tool": "MoonTxnWitness",
    "version": version().to_json(),
    "algorithm": "v3-list-1",
    "status": status.to_json(),
    "modelDefinition": {
      "id": "append-list-serializable-v1",
      "scope": "committed transactions' full append/read/savepoint journals; aborted observations retained, no opacity or real-time claim",
    },
    "coverage": object_fields_unchecked_v3(normalized).get_or_default(
      "coverage",
      Json::null(),
    ),
    "normalized": normalized,
    "evidence": evidence,
    "execution": {
      "lifecycleAdapter": "register-v3-lifecycle-metadata-1",
      "analysisOptions": {
        "maxStates": options.max_states.to_json(),
        "maxOperationChecks": options.max_operations.to_json(),
      },
      "effectiveLimits": {
        "committedTransactions": 6,
        "operations": 128,
        "states": options.max_states.to_json(),
        "operationChecks": options.max_operations.to_json(),
        "inputUtf16Units": 8388608,
        "events": 65536,
        "identities": 10000,
        "returnedItemReferences": 100000,
      },
      "metrics": {
        "states": states.to_json(),
        "operationChecks": operations.to_json(),
        "complete": complete.to_json(),
        "reason": reason.to_json(),
      },
    },
  }
}

///|
fn list_v3_analysis(text : String, o : String, v? : Json) -> Json raise {
  let options = list_v3_options(o)
  let parsed = list_v3_parse(text, v?) catch {
    error =>
      return list_v3_report(
        list_v3_invalid(text, error.to_string()),
        "invalid",
        Json::null(),
        options,
        0,
        0,
        false,
        "invalid_capture",
      )
  }
  let status = object_fields_unchecked_v3(parsed.normalized).at("status")
  if status != "ready".to_json() {
    return list_v3_report(
      parsed.normalized,
      identifier(status, "status"),
      Json::null(),
      options,
      0,
      0,
      false,
      "coverage_gap",
    )
  }
  if !parsed.findings.is_empty() {
    return list_v3_report(
      parsed.normalized,
      "violation",
      {
        "kind": "source-proven-list-anomaly",
        "findings": parsed.findings.to_json(),
        "sourceEvidence": parsed.source_evidence.to_json(),
      },
      options,
      0,
      0,
      true,
      "source_proven_anomaly",
    )
  }
  let committed = parsed.programs.filter(program => program.status == Committed)
  if committed.length() > 6 || parsed.operations > 128 {
    return list_v3_report(
      parsed.normalized,
      "inconclusive",
      Json::null(),
      options,
      0,
      0,
      false,
      "exact_capacity",
    )
  }
  let state : Map[String, Array[Int]] = Map([])
  for key, list in parsed.initial {
    state[key] = list.copy()
  }
  let ctx : ListV3Search = {
    programs: committed,
    items: parsed.items,
    state,
    trail: [],
    prefix: [],
    blockers: [],
    options,
    states: 0,
    operations: 0,
    limited: false,
    reason: "exhausted",
  }
  let order = list_v3_search(ctx, 0)
  match order {
    Some(order) =>
      list_v3_report(
        parsed.normalized,
        "consistent",
        {
          "kind": "serial-list-replay",
          "serialOrder": order.to_json(),
          "sourceEvidence": parsed.source_evidence.to_json(),
        },
        options,
        ctx.states,
        ctx.operations,
        true,
        "found",
      )
    None if ctx.limited =>
      list_v3_report(
        parsed.normalized,
        "inconclusive",
        {
          "kind": "search-incomplete",
          "sampleBlockers": ctx.blockers.to_json(),
          "sourceEvidence": parsed.source_evidence.to_json(),
        },
        options,
        ctx.states,
        ctx.operations,
        false,
        ctx.reason,
      )
    None =>
      list_v3_report(
        parsed.normalized,
        "violation",
        {
          "kind": "bounded-serial-exhaustion",
          "code": "no_serial_list_execution",
          "sampleBlockers": ctx.blockers.to_json(),
          "sourceEvidence": parsed.source_evidence.to_json(),
        },
        options,
        ctx.states,
        ctx.operations,
        true,
        "exhausted",
      )
  }
}
