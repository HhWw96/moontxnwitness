///|
priv struct PresenceCaptureOp {
  seq : Int
  tx : String
  key : String
  version : String
  kind : OpKind
}

///|
priv struct PresenceCaptureSource {
  key : String
  present : Bool
  tx : String?
  seq : Int
  predecessor : String?
  old_present : Bool
}

///|
fn presence_capture_result(
  status : String,
  gaps : Array[Json],
  history : Json,
  source_facts : Json,
) -> String {
  let result : Json = {
    "schema": 1,
    "status": status.to_json(),
    "coverage": {
      "complete": (status == "ready").to_json(),
      "gaps": gaps.to_json(),
    },
    "history": history,
    "projection": {
      "version": "column-presence-register-v0.1.2-experimental",
      "scope": "unique-version point-register projection",
    },
    "sourceFacts": source_facts,
  }
  result.stringify(indent=2)
}

///|
fn presence_capture_uuid(value : Json, path : String) -> String raise {
  let token = identifier(value, path)
  if token.length() != 36 {
    fail(path + " must be a canonical lowercase UUID")
  }
  for index in 0..<36 {
    let unit = token[index]
    if index == 8 || index == 13 || index == 18 || index == 23 {
      if unit != 45 {
        fail(path + " must be a canonical lowercase UUID")
      }
    } else if !((unit >= 48 && unit <= 57) || (unit >= 97 && unit <= 102)) {
      fail(path + " must be a canonical lowercase UUID")
    }
  }
  token
}

///|
fn presence_capture_bool(value : Json, path : String) -> Bool raise {
  match value {
    True => true
    False => false
    _ => fail(path + " must be a boolean")
  }
}

///|
fn presence_capture_array(value : Json, path : String) -> Array[Json] raise {
  match value {
    Array(items) => items
    _ => fail(path + " must be an array")
  }
}

///|
fn presence_capture_seq(value : Json, path : String) -> Int raise {
  match value {
    Number(n, ..) if n >= 1.0 && n <= 65536.0 && n.to_int().to_double() == n =>
      n.to_int()
    _ => fail(path + " must be a capture sequence in 1..65536")
  }
}

///|
fn presence_capture_fact_op(
  fact : Map[String, Json],
  kind : OpKind,
  operations : Map[Int, PresenceCaptureOp],
  seen : Map[Int, Bool],
  path : String,
) -> PresenceCaptureOp raise {
  let seq = presence_capture_seq(required(fact, "seq", path), path + ".seq")
  let tx = identifier(required(fact, "tx", path), path + ".tx")
  let key = identifier(required(fact, "key", path), path + ".key")
  let version = presence_capture_uuid(
    required(fact, "version", path),
    path + ".version",
  )
  if seen.contains(seq) {
    fail(path + ": duplicate operation fact")
  }
  let op = match operations.get(seq) {
    Some(op) => op
    None => fail(path + ": fact does not identify an original operation event")
  }
  if op.tx != tx || op.key != key || op.version != version || op.kind != kind {
    fail(path + ": fact does not match the original operation event")
  }
  seen[seq] = true
  op
}

///|
/// Experimental presence facts are internally checked observations, not database
/// authentication. Predecessors constrain factual version order and never create
/// a read operation. The old trace-1 lifecycle validator remains the authority for
/// event sequence, transaction outcomes, clocks and coverage.
pub fn normalize_presence_capture_json(text : String) -> String {
  try {
    let root = object_fields(
      guarded_json(text, limit=8388608),
      "presence capture",
    )
    known_fields(
      root,
      ["traceSchema", "clockDomain", "scope", "events", "gaps", "presenceFacts"],
      "presence capture",
    )
    if required(root, "traceSchema", "presence capture") != (2).to_json() {
      fail("presence capture traceSchema must be 2")
    }
    let raw_facts = required(root, "presenceFacts", "presence capture")
    let facts = object_fields(raw_facts, "presenceFacts")
    known_fields(
      facts,
      ["schema", "projection", "initial", "reads", "writes"],
      "presenceFacts",
    )
    if required(facts, "schema", "presenceFacts") != (1).to_json() ||
      required(facts, "projection", "presenceFacts") !=
      "column-presence-register-v0.1.2-experimental".to_json() {
      fail("Unsupported presence fact schema or projection")
    }
    let raw_initial = presence_capture_array(
      required(facts, "initial", "presenceFacts"),
      "presenceFacts.initial",
    )
    let raw_reads = presence_capture_array(
      required(facts, "reads", "presenceFacts"),
      "presenceFacts.reads",
    )
    let raw_writes = presence_capture_array(
      required(facts, "writes", "presenceFacts"),
      "presenceFacts.writes",
    )
    if raw_initial.length() > 10000 ||
      raw_reads.length() + raw_writes.length() > 10000 {
      fail(
        "At most 10,000 initial facts and 10,000 operation facts are supported",
      )
    }
    let events = required(root, "events", "presence capture")
    let trace_one : Json = {
      "traceSchema": 1,
      "clockDomain": required(root, "clockDomain", "presence capture"),
      "scope": required(root, "scope", "presence capture"),
      "events": events,
      "gaps": required(root, "gaps", "presence capture"),
    }
    let base = object_fields(
      guarded_json(normalize_capture_json(trace_one.stringify()), limit=8388608),
      "normalized capture",
    )
    let base_status = identifier(
      required(base, "status", "normalized capture"),
      "normalized status",
    )
    let coverage = object_fields(
      required(base, "coverage", "normalized capture"),
      "coverage",
    )
    let base_gaps = presence_capture_array(
      required(coverage, "gaps", "coverage"),
      "coverage.gaps",
    )
    if base_status != "ready" {
      return presence_capture_result(
        base_status,
        base_gaps,
        Json::null(),
        raw_facts,
      )
    }
    let h = match
      parse_history(required(base, "history", "normalized capture").stringify()) {
      Ok(history) => history
      Err(message) => fail("Normalized presence history rejected: " + message)
    }
    let operations : Map[Int, PresenceCaptureOp] = Map([])
    let ordered_ops : Array[PresenceCaptureOp] = []
    for raw_event in presence_capture_array(events, "events") {
      let event = object_fields(raw_event, "event")
      if required(event, "kind", "event") == "op".to_json() {
        let raw_op = object_fields(required(event, "op", "event"), "op")
        let op : PresenceCaptureOp = {
          seq: presence_capture_seq(required(event, "seq", "event"), "op.seq"),
          tx: identifier(required(event, "tx", "event"), "op.tx"),
          key: identifier(required(raw_op, "key", "op"), "op.key"),
          version: presence_capture_uuid(
            required(raw_op, "version", "op"),
            "op.version",
          ),
          kind: if required(raw_op, "type", "op") == "read".to_json() {
            Read
          } else {
            Write
          },
        }
        operations[op.seq] = op
        ordered_ops.push(op)
      }
    }
    let sources : Map[String, PresenceCaptureSource] = Map([])
    let initial_keys : Map[String, Bool] = Map([])
    for raw_initial_fact in raw_initial {
      let fact = object_fields(raw_initial_fact, "initial fact")
      known_fields(fact, ["key", "version", "present"], "initial fact")
      let key = identifier(
        required(fact, "key", "initial fact"),
        "initial fact.key",
      )
      let version = presence_capture_uuid(
        required(fact, "version", "initial fact"),
        "initial fact.version",
      )
      let present = presence_capture_bool(
        required(fact, "present", "initial fact"),
        "initial fact.present",
      )
      if initial_keys.contains(key) ||
        sources.contains(version) ||
        h.initial.get(key) != Some(version) {
        fail(
          "Initial presence facts must uniquely match snapshot keys and globally unique tokens",
        )
      }
      initial_keys[key] = true
      sources[version] = {
        key,
        present,
        tx: None,
        seq: 0,
        predecessor: None,
        old_present: present,
      }
    }
    if initial_keys.length() != h.initial.length() {
      fail("Initial presence facts must cover every snapshot key exactly once")
    }
    let seen : Map[Int, Bool] = Map([])
    for raw_write in raw_writes {
      let fact = object_fields(raw_write, "write fact")
      known_fields(
        fact,
        [
          "seq", "tx", "key", "version", "predecessor", "oldPresent", "newPresent",
          "action",
        ],
        "write fact",
      )
      let op = presence_capture_fact_op(
        fact,
        Write,
        operations,
        seen,
        "write fact",
      )
      let predecessor = presence_capture_uuid(
        required(fact, "predecessor", "write fact"),
        "write fact.predecessor",
      )
      let old_present = presence_capture_bool(
        required(fact, "oldPresent", "write fact"),
        "write fact.oldPresent",
      )
      let present = presence_capture_bool(
        required(fact, "newPresent", "write fact"),
        "write fact.newPresent",
      )
      let action = identifier(
        required(fact, "action", "write fact"),
        "write fact.action",
      )
      let valid_action = match action {
        "insert" => !old_present && present
        "update" => old_present && present
        "delete" => old_present && !present
        _ => false
      }
      if !valid_action {
        fail("Write action does not match its old/new presence facts")
      }
      if sources.contains(op.version) {
        fail(
          "Presence version tokens must be globally unique across all keys and writes",
        )
      }
      sources[op.version] = {
        key: op.key,
        present,
        tx: Some(op.tx),
        seq: op.seq,
        predecessor: Some(predecessor),
        old_present,
      }
    }
    let gaps : Array[Json] = []
    for raw_read in raw_reads {
      let fact = object_fields(raw_read, "read fact")
      known_fields(
        fact,
        ["seq", "tx", "key", "version", "present"],
        "read fact",
      )
      let op = presence_capture_fact_op(
        fact,
        Read,
        operations,
        seen,
        "read fact",
      )
      let present = presence_capture_bool(
        required(fact, "present", "read fact"),
        "read fact.present",
      )
      match sources.get(op.version) {
        None =>
          gaps.push(
            capture_gap(
              "missing_presence_source", "Read source is not present in captured initial/write facts",
            ),
          )
        Some(source) =>
          if source.key != op.key || source.present != present {
            fail("Read presence does not match its version source")
          }
      }
    }
    if seen.length() != operations.length() {
      fail("Every operation requires exactly one matching presence fact")
    }
    let statuses : Map[String, TxStatus] = Map([])
    for tx in h.transactions {
      statuses[tx.id] = tx.status
    }
    // The final-write map is built in original event order; facts array order is
    // immaterial and cannot choose a version order.
    let final_by_tx : Map[String, Map[String, String]] = Map([])
    for op in ordered_ops {
      if op.kind == Write {
        let own = final_by_tx.get_or_default(op.tx, Map([]))
        let source = match sources.get(op.version) {
          Some(source) => source
          None => fail("Missing write source")
        }
        let predecessor = match source.predecessor {
          Some(version) => version
          None => fail("Missing predecessor")
        }
        match own.get(op.key) {
          Some(previous) if previous != predecessor =>
            fail(
              "A transaction's subsequent write must follow its own previous version",
            )
          _ => ()
        }
        own[op.key] = op.version
        final_by_tx[op.tx] = own
      }
    }
    for op in ordered_ops {
      if op.kind == Write {
        let source = sources.get(op.version).unwrap()
        let predecessor = source.predecessor.unwrap()
        match sources.get(predecessor) {
          None =>
            gaps.push(
              capture_gap(
                "missing_presence_source", "Write predecessor is absent from captured initial/write facts",
              ),
            )
          Some(previous) => {
            if previous.key != source.key ||
              previous.present != source.old_present ||
              previous.seq >= source.seq {
              fail(
                "Write predecessor key, presence or causal sequence is inconsistent",
              )
            }
            match previous.tx {
              Some(tx) if tx != op.tx =>
                if statuses.get(tx) != Some(Committed) ||
                  final_by_tx.get(tx).unwrap().get(op.key) != Some(predecessor) {
                  gaps.push(
                    capture_gap(
                      "unproven_committed_predecessor", "An external predecessor is not a captured committed final write",
                    ),
                  )
                }
              _ => ()
            }
          }
        }
      }
    }
    if gaps.length() > 0 {
      return presence_capture_result(
        "inconclusive",
        gaps,
        Json::null(),
        raw_facts,
      )
    }
    // Collapse only same-transaction intermediate writes, retaining all of them
    // in the exported operations and source facts. Aborted branches do not become
    // committed order facts. A linear successor relation must cover every final.
    let successors : Map[String, String] = Map([])
    let finals_per_key : Map[String, Int] = Map([])
    for tx in h.transactions {
      if tx.status == Committed {
        match final_by_tx.get(tx.id) {
          None => ()
          Some(finals) =>
            for key, final_version in finals {
              let mut cursor = sources.get(final_version).unwrap().predecessor.unwrap()
              let mut steps = 0
              while sources.get(cursor).unwrap().tx == Some(tx.id) {
                cursor = sources.get(cursor).unwrap().predecessor.unwrap()
                steps += 1
                if steps > raw_writes.length() {
                  fail("Presence predecessor chain contains a cycle")
                }
              }
              if successors.contains(cursor) {
                fail("Committed presence version chain branches")
              }
              successors[cursor] = final_version
              finals_per_key[key] = finals_per_key.get_or_default(key, 0) + 1
            }
        }
      }
    }
    let orders : Map[String, Array[String]] = Map([])
    for key, initial in h.initial {
      let order = [initial]
      let mut cursor = initial
      let mut visited = 0
      while successors.contains(cursor) {
        cursor = successors.get(cursor).unwrap()
        order.push(cursor)
        visited += 1
        if visited > raw_writes.length() {
          fail("Committed presence chain contains a cycle")
        }
      }
      if visited != finals_per_key.get_or_default(key, 0) {
        fail(
          "Committed presence chain does not cover every committed final write",
        )
      }
      orders[key] = order
    }
    let projected = { ..h, version_orders: orders, }
    let findings = validate_history(projected)
    if findings.length() > 0 {
      fail("Presence register projection rejected: " + findings[0].message)
    }
    presence_capture_result("ready", [], history_json(projected), raw_facts)
  } catch {
    error =>
      presence_capture_result(
        "invalid",
        [capture_gap("invalid_presence_capture", error.to_string())],
        Json::null(),
        Json::null(),
      )
  }
}
