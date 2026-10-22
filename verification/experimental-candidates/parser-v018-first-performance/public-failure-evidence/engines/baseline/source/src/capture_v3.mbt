///|
priv struct V3CaptureEffect {
  seq : Int64
  tx : String
  key : String
  version : String
  predecessor : String
  reverted_by : Int64?
}

///|
priv struct V3CaptureStep {
  op : Operation
  own : Bool
  effect : Int?
}

///|
priv struct V3CaptureScope {
  name : String
  instance : String
  mark : Int
}

///|
priv struct V3CaptureTx {
  id : String
  connection : String
  begin_seq : Int64
  mut end_seq : Int64?
  mut status : TxStatus
  mut active : Bool
  mut commit_requested : Bool
  mut commit_request_seq : Int64?
  mut confirmed_rollback_response : Bool
  events : Array[Int64]
  steps : Array[V3CaptureStep]
  effects : Array[Int]
  own : Map[String, String?]
  trail : Array[(Int, String?)]
  scopes : Array[V3CaptureScope]
}

///|
priv struct V3CaptureSource {
  key : String
  effect : Int?
}

///|
fn v3_capture_seq(value : Json, path : String) -> Int64 raise {
  match value {
    Number(n, ..) if n >= 1.0 &&
      n <= 9007199254740991.0 &&
      n.to_int64().to_double() == n => n.to_int64()
    _ => fail(path + " must be a positive safe integer")
  }
}

///|
fn v3_capture_own(tx : V3CaptureTx, key : String) -> String? {
  match tx.own.get(key) {
    Some(value) => value
    None => None
  }
}

///|
fn v3_capture_rollback(
  tx : V3CaptureTx,
  effects : Array[V3CaptureEffect],
  mark : Int,
  seq : Int64,
) -> Unit {
  // A write enters and leaves this trail at most once. Savepoint creation and
  // release never copy the complete own-write map or scan earlier observations.
  while tx.trail.length() > mark {
    let (index, previous) = tx.trail.pop().unwrap()
    let effect = effects[index]
    tx.own[effect.key] = previous
    effects[index] = { ..effect, reverted_by: Some(seq), }
  }
}

///|
fn v3_capture_active(
  event : Map[String, Json],
  ids : Map[String, Int],
  transactions : Array[V3CaptureTx],
  path : String,
) -> V3CaptureTx raise {
  let id = identifier(required(event, "tx", path), path + ".tx")
  let index = match ids.get(id) {
    Some(index) => index
    None => fail(path + ": unknown transaction")
  }
  let tx = transactions[index]
  if !tx.active {
    fail(path + ": transaction is already terminal")
  }
  tx
}

///|
fn v3_capture_scope(tx : V3CaptureTx, instance : String) -> Int raise {
  let mut found = -1
  for index, scope in tx.scopes {
    if scope.instance == instance {
      found = index
    }
  }
  if found < 0 {
    fail("Savepoint instance is not active in this transaction")
  }
  // PostgreSQL resolves names to the newest identically named active mark.
  // Instance IDs disambiguate evidence but must not permit impossible SQL.
  for index in (found + 1)..<tx.scopes.length() {
    if tx.scopes[index].name == tx.scopes[found].name {
      fail("An older identically named savepoint is hidden")
    }
  }
  found
}

///|
fn v3_capture_final_writes(
  tx : V3CaptureTx,
  effects : Array[V3CaptureEffect],
) -> Array[Int64] {
  let result : Array[Int64] = []
  for index in tx.effects {
    let effect = effects[index]
    if effect.reverted_by is None &&
      v3_capture_own(tx, effect.key) == Some(effect.version) {
      result.push(effect.seq)
    }
  }
  result
}

///|
fn v3_capture_result(
  status : String,
  gaps : Array[Json],
  observations : Json,
  effects : Array[V3CaptureEffect],
  transactions : Array[V3CaptureTx],
  history : Json,
  error : String?,
  sql_proof : Json,
) -> String {
  let raw_effects = effects.map(effect => {
    let reverted = match effect.reverted_by {
      Some(seq) => seq.to_double().to_json()
      None => Json::null()
    }
    (
      {
        "seq": effect.seq.to_double().to_json(),
        "tx": effect.tx.to_json(),
        "key": effect.key.to_json(),
        "version": effect.version.to_json(),
        "predecessor": effect.predecessor.to_json(),
        "revertedBy": reverted,
      } : Json)
  })
  let raw_transactions = transactions.map(tx => {
    let end_seq = match tx.end_seq {
      Some(seq) => seq.to_double().to_json()
      None => Json::null()
    }
    (
      {
        "id": tx.id.to_json(),
        "connection": tx.connection.to_json(),
        "status": status_label(tx.status).to_json(),
        "beginSeq": tx.begin_seq.to_double().to_json(),
        "endSeq": end_seq,
        "events": tx.events.map(seq => seq.to_double().to_json()).to_json(),
        "finalWrites": v3_capture_final_writes(tx, effects)
        .map(seq => seq.to_double().to_json())
        .to_json(),
      } : Json)
  })
  let result : Json = {
    "schema": 3,
    "algorithm": (if sql_proof != Json::null() {
      "v3-lifecycle-sql-1"
    } else if transactions.any(tx => tx.confirmed_rollback_response) {
      "v3-lifecycle-2"
    } else {
      "v3-lifecycle-1"
    }).to_json(),
    "status": status.to_json(),
    "coverage": {
      "complete": (status == "ready").to_json(),
      "gaps": gaps.to_json(),
    },
    "observations": observations,
    "effects": raw_effects.to_json(),
    "transactions": raw_transactions.to_json(),
    "history": history,
  }
  if sql_proof != Json::null() {
    object_fields_unchecked_v3(result)["sqlProof"] = sql_proof
  }
  match error {
    Some(message) =>
      object_fields_unchecked_v3(result)["error"] = message.to_json()
    None => ()
  }
  result.stringify(indent=2)
}

///|
fn object_fields_unchecked_v3(value : Json) -> Map[String, Json] {
  match value {
    Object(fields) => fields
    _ => Map([])
  }
}

///|
fn v3_capture_external_final(
  source : V3CaptureSource,
  effects : Array[V3CaptureEffect],
  ids : Map[String, Int],
  transactions : Array[V3CaptureTx],
) -> Bool {
  match source.effect {
    None => true
    Some(index) => {
      let effect = effects[index]
      let tx = transactions[ids.get(effect.tx).unwrap()]
      effect.reverted_by is None &&
      tx.status == Committed &&
      v3_capture_own(tx, effect.key) == Some(effect.version)
    }
  }
}

///|
/// Validate lifecycle facts without flattening revoked writes into committed
/// state. Only a complete, independently source-checked register projection is
/// exported. Conditions and raw SQL remain observations with explicit gaps.
fn normalize_register_capture_v3_json(
  text : String,
  use_sql_proof? : Bool = false,
) -> String {
  let mut observations : Json = Json::null()
  let mut proof_evidence : Json = Json::null()
  let effects : Array[V3CaptureEffect] = []
  let transactions : Array[V3CaptureTx] = []
  let gaps : Array[Json] = []
  try {
    let root = object_fields(guarded_json(text, limit=8388608), "capture v3")
    known_fields(
      root,
      [
        "traceSchema", "clockDomain", "scope", "events", "gaps", "dataModel", "sqlProfiles",
      ],
      "capture v3",
    )
    match root.get("dataModel") {
      None | Some(String("point-register-v1")) => ()
      _ => fail("Unsupported register dataModel")
    }
    if required(root, "traceSchema", "capture v3") != (3).to_json() {
      fail("traceSchema must be 3")
    }
    let _ = identifier(
      required(root, "clockDomain", "capture v3"),
      "clockDomain",
    )
    let scope = object_fields(required(root, "scope", "capture v3"), "scope")
    known_fields(scope, ["exclusiveWriters"], "scope")
    match required(scope, "exclusiveWriters", "scope") {
      True => ()
      False =>
        gaps.push(
          capture_gap(
            "writer_scope_unproven", "Other writers have not been excluded",
          ),
        )
      _ => fail("scope.exclusiveWriters must be a boolean")
    }
    let raw_gaps = presence_capture_array(
      required(root, "gaps", "capture v3"),
      "gaps",
    )
    for raw_gap in raw_gaps {
      let gap = object_fields(raw_gap, "gap")
      known_fields(gap, ["code", "message"], "gap")
      let code = identifier(required(gap, "code", "gap"), "gap.code")
      let message = match required(gap, "message", "gap") {
        String(message) if message.length() > 0 && message.length() <= 4096 =>
          message
        _ => fail("gap.message must contain 1..4096 code units")
      }
      gaps.push(capture_gap(code, message))
    }
    observations = required(root, "events", "capture v3")
    let events = presence_capture_array(observations, "events")
    if events.length() > 65536 {
      fail("At most 65,536 v3 events are supported")
    }
    let sql_proof : V3DislockSQLProof = if use_sql_proof {
      v3_dislock_sql_proof(root)
    } else {
      {
        verified_statements: Map([]),
        verified_facts: Map([]),
        verified_profiles: Map([]),
        gaps: [],
      }
    }
    if use_sql_proof {
      proof_evidence = v3_sql_proof_evidence(sql_proof, root)
      for gap in sql_proof.gaps {
        gaps.push(gap)
      }
    }
    v3_sql_profiles(root, gaps, sql_proof.verified_profiles)
    let initial : Map[String, String] = Map([])
    let sources : Map[String, V3CaptureSource] = Map([])
    let ids : Map[String, Int] = Map([])
    let connections : Map[String, Int?] = Map([])
    let instances : Map[String, Bool] = Map([])
    let statements : Map[Int64, String] = Map([])
    let row_complete : Map[Int64, Bool] = Map([])
    let mut snapshot_seen = false
    let mut next_seq = 1L
    let mut last_time = 0L
    let mut op_count = 0
    let mut row_count = 0
    for raw_event in events {
      let event = object_fields(raw_event, "event")
      let seq = v3_capture_seq(required(event, "seq", "event"), "event.seq")
      if seq < next_seq {
        fail("Event sequence numbers must be unique and increasing")
      }
      if seq != next_seq {
        gaps.push(
          capture_gap("sequence_gap", "One or more v3 events are missing"),
        )
      }
      next_seq = seq + 1L
      let time = capture_time(event, "event")
      if time < last_time {
        fail("Event time goes backwards in clockDomain")
      }
      last_time = time
      let kind = identifier(required(event, "kind", "event"), "event.kind")
      if kind == "snapshot" {
        known_fields(
          event,
          ["seq", "time", "kind", "initial", "consistent"],
          "snapshot",
        )
        if snapshot_seen || transactions.length() > 0 {
          fail("Exactly one snapshot must precede transactions")
        }
        snapshot_seen = true
        match required(event, "consistent", "snapshot") {
          True => ()
          False =>
            gaps.push(
              capture_gap(
                "inconsistent_snapshot", "Initial state is not a consistent captured snapshot",
              ),
            )
          _ => fail("snapshot.consistent must be a boolean")
        }
        let raw_initial = object_fields(
          required(event, "initial", "snapshot"),
          "snapshot.initial",
        )
        if raw_initial.length() > 10000 {
          fail("At most 10,000 initialized keys are supported")
        }
        for key, value in raw_initial {
          let _ = identifier(key.to_json(), "initial key")
          let version = identifier(value, "initial version")
          if sources.contains(version) {
            fail("Version identities must be globally unique")
          }
          initial[key] = version
          sources[version] = { key, effect: None, }
        }
        continue
      }
      if kind == "begin" {
        known_fields(
          event,
          ["seq", "time", "kind", "tx", "connection"],
          "begin",
        )
        if !snapshot_seen {
          fail("A snapshot must precede transaction begin")
        }
        let id = identifier(required(event, "tx", "begin"), "begin.tx")
        let connection = identifier(
          required(event, "connection", "begin"),
          "begin.connection",
        )
        if ids.contains(id) {
          fail("Transaction identities cannot be reused")
        }
        match connections.get(connection) {
          Some(Some(_)) =>
            fail("A connection cannot own two active transactions")
          _ => ()
        }
        if transactions.length() >= 512 {
          fail("At most 512 v3 transactions are supported")
        }
        ids[id] = transactions.length()
        connections[connection] = Some(transactions.length())
        transactions.push({
          id,
          connection,
          begin_seq: seq,
          end_seq: None,
          status: Unknown,
          active: true,
          commit_requested: false,
          commit_request_seq: None,
          confirmed_rollback_response: false,
          events: [seq],
          steps: [],
          effects: [],
          own: Map([]),
          trail: [],
          scopes: [],
        })
        continue
      }
      let tx = v3_capture_active(event, ids, transactions, "event")
      tx.events.push(seq)
      if tx.commit_requested &&
        !["commit_ok", "rollback_ok", "disconnect"].contains(kind) {
        fail("Only an outcome or disconnect may follow commit_request")
      }
      match kind {
        "read" | "write" => {
          if kind == "read" {
            known_fields(
              event,
              [
                "seq", "time", "kind", "tx", "key", "version", "statement", "mappingId",
                "evidence",
              ],
              "read",
            )
          } else {
            known_fields(
              event,
              [
                "seq", "time", "kind", "tx", "key", "version", "predecessor", "statement",
                "mappingId", "evidence",
              ],
              "write",
            )
          }
          v3_sql_fact_metadata(
            event,
            seq,
            tx.id,
            statements,
            gaps,
            sql_proof.verified_facts.contains(seq),
          )
          let key = identifier(required(event, "key", "event"), "event.key")
          let version = identifier(
            required(event, "version", "event"),
            "event.version",
          )
          if !initial.contains(key) {
            gaps.push(
              capture_gap(
                "missing_initial", "An operated key has no initial version",
              ),
            )
          }
          op_count += 1
          if op_count > 10000 {
            fail("At most 10,000 v3 reads and writes are supported")
          }
          let own = v3_capture_own(tx, key)
          if kind == "read" {
            match sources.get(version) {
              None =>
                gaps.push(
                  capture_gap(
                    "missing_version_source", "A read version was not observed before this read",
                  ),
                )
              Some(source) if source.key != key =>
                fail("Read source belongs to another key")
              _ => ()
            }
            let own_read = own == Some(version)
            if own is Some(_) && !own_read {
              gaps.push(
                capture_gap(
                  "own_read_mismatch", "A read does not observe the current own-write overlay",
                ),
              )
            }
            tx.steps.push({
              op: { kind: Read, key, version, },
              own: own_read,
              effect: None,
            })
          } else {
            let predecessor = identifier(
              required(event, "predecessor", "write"),
              "write.predecessor",
            )
            if sources.contains(version) || predecessor == version {
              fail("Each write needs a new globally unique version identity")
            }
            match sources.get(predecessor) {
              None =>
                gaps.push(
                  capture_gap(
                    "missing_version_source", "A write predecessor was not observed before this write",
                  ),
                )
              Some(source) if source.key != key =>
                fail("Write predecessor belongs to another key")
              Some(source) =>
                match (own, source.effect) {
                  (Some(previous), _) if previous != predecessor =>
                    gaps.push(
                      capture_gap(
                        "own_write_predecessor_mismatch", "A write does not follow the current own-write overlay",
                      ),
                    )
                  (None, Some(index)) if effects[index].tx == tx.id =>
                    gaps.push(
                      capture_gap(
                        "own_write_predecessor_mismatch", "A write follows its own revoked effect",
                      ),
                    )
                  _ => ()
                }
            }
            let index = effects.length()
            effects.push({
              seq,
              tx: tx.id,
              key,
              version,
              predecessor,
              reverted_by: None,
            })
            sources[version] = { key, effect: Some(index), }
            tx.effects.push(index)
            tx.trail.push((index, own))
            tx.own[key] = Some(version)
            tx.steps.push({
              op: { kind: Write, key, version, },
              own: false,
              effect: Some(index),
            })
          }
        }
        "condition" => {
          known_fields(
            event,
            [
              "seq", "time", "kind", "tx", "predicate", "matched", "sourceVersion",
              "statement", "mappingId", "evidence",
            ],
            "condition",
          )
          v3_sql_fact_metadata(
            event,
            seq,
            tx.id,
            statements,
            gaps,
            sql_proof.verified_facts.contains(seq),
          )
          let _ = required(event, "predicate", "condition")
          let _ = presence_capture_bool(
            required(event, "matched", "condition"),
            "condition.matched",
          )
          match event.get("sourceVersion") {
            None => ()
            Some(value) => {
              let source = identifier(value, "condition.sourceVersion")
              if !sources.contains(source) {
                gaps.push(
                  capture_gap(
                    "missing_version_source", "A condition source was not observed before the condition",
                  ),
                )
              }
            }
          }
          if !sql_proof.verified_facts.contains(seq) {
            gaps.push(
              capture_gap(
                "unsupported_condition", "Condition semantics are retained but not proved by the lifecycle projection",
              ),
            )
          }
        }
        "statement" => {
          known_fields(
            event,
            [
              "seq", "time", "kind", "tx", "sql", "parameters", "mappingId", "executedSql",
            ],
            "statement",
          )
          match required(event, "sql", "statement") {
            String(_) => ()
            _ => fail("statement.sql must be a string")
          }
          v3_sql_statement_metadata(event)
          statements[seq] = tx.id
          if !sql_proof.verified_statements.contains(seq) {
            gaps.push(
              capture_gap(
                "unmapped_statement", "Raw SQL has no verified versioned statement mapping",
              ),
            )
          }
        }
        "rows" => {
          known_fields(
            event,
            [
              "seq", "time", "kind", "tx", "statement", "rows", "complete", "serverRows",
              "columns", "error",
            ],
            "rows",
          )
          let statement = v3_capture_seq(
            required(event, "statement", "rows"),
            "rows.statement",
          )
          if statement >= seq || statements.get(statement) != Some(tx.id) {
            fail(
              "rows must reference a preceding statement in the same transaction",
            )
          }
          if row_complete.get(statement) == Some(true) {
            fail("Rows cannot follow the statement's complete result")
          }
          let rows = presence_capture_array(
            required(event, "rows", "rows"),
            "rows.rows",
          )
          row_count += rows.length()
          if row_count > 10000 {
            fail("At most 10,000 raw result rows are supported")
          }
          v3_sql_rows_metadata(event, rows)
          row_complete[statement] = presence_capture_bool(
            required(event, "complete", "rows"),
            "rows.complete",
          )
        }
        "savepoint" => {
          known_fields(
            event,
            ["seq", "time", "kind", "tx", "name", "instance"],
            "savepoint",
          )
          let name = identifier(
            required(event, "name", "savepoint"),
            "savepoint.name",
          )
          let instance = identifier(
            required(event, "instance", "savepoint"),
            "savepoint.instance",
          )
          if instances.contains(instance) {
            fail("Savepoint instance identities cannot be reused")
          }
          if tx.scopes.length() >= 64 {
            fail("At most 64 nested savepoints are supported")
          }
          instances[instance] = true
          tx.scopes.push({ name, instance, mark: tx.trail.length(), })
        }
        "rollback_to" | "release" => {
          known_fields(event, ["seq", "time", "kind", "tx", "instance"], kind)
          let instance = identifier(
            required(event, "instance", kind),
            kind + ".instance",
          )
          let index = v3_capture_scope(tx, instance)
          if kind == "rollback_to" {
            v3_capture_rollback(tx, effects, tx.scopes[index].mark, seq)
          }
          let retained = if kind == "rollback_to" { index + 1 } else { index }
          while tx.scopes.length() > retained {
            let _ = tx.scopes.pop()
          }
        }
        "commit_request" => {
          known_fields(event, ["seq", "time", "kind", "tx"], kind)
          tx.commit_requested = true
          tx.commit_request_seq = Some(seq)
        }
        "commit_ok" | "rollback_ok" | "disconnect" => {
          if kind == "rollback_ok" {
            known_fields(
              event,
              ["seq", "time", "kind", "tx", "commitResponse"],
              kind,
            )
          } else {
            known_fields(event, ["seq", "time", "kind", "tx"], kind)
          }
          let confirmed_abort = if kind == "rollback_ok" {
            v3_confirmed_commit_rollback(event, tx)
          } else {
            false
          }
          if kind == "commit_ok" {
            if !tx.commit_requested {
              fail("commit_ok requires a preceding commit_request")
            }
            tx.status = Committed
          } else if kind == "rollback_ok" &&
            (!tx.commit_requested || confirmed_abort) {
            v3_capture_rollback(tx, effects, 0, seq)
            tx.status = Aborted
            tx.confirmed_rollback_response = confirmed_abort
          } else {
            tx.status = Unknown
            gaps.push(
              capture_gap(
                "unknown_commit", "The original transaction outcome has not been confirmed",
              ),
            )
          }
          tx.end_seq = Some(seq)
          tx.active = false
          connections[tx.connection] = None
        }
        _ => fail("Unsupported v3 event kind: " + kind)
      }
    }
    if !snapshot_seen {
      gaps.push(
        capture_gap("missing_snapshot", "No initial snapshot was observed"),
      )
    }
    for tx in transactions {
      if tx.active {
        gaps.push(
          capture_gap(
            "outstanding_transaction", "A transaction has no confirmed terminal event",
          ),
        )
      }
    }
    for _, complete in row_complete {
      if !complete {
        gaps.push(
          capture_gap("incomplete_rows", "A statement result was not exhausted"),
        )
      }
    }
    // Source outcomes are checked only after all events: a delayed client ACK
    // is not a database commit-order fact.
    for tx in transactions {
      for step in tx.steps {
        if step.op.kind == Read && !step.own {
          match sources.get(step.op.version) {
            None => () // The earlier missing-source gap is permanent.
            Some(source) if source.key != step.op.key =>
              fail("Read source belongs to another key")
            Some(source) =>
              match source.effect {
                Some(index) if effects[index].tx == tx.id =>
                  gaps.push(
                    capture_gap(
                      "own_read_mismatch", "A read refers to its own revoked or noncurrent effect",
                    ),
                  )
                _ =>
                  if !v3_capture_external_final(
                      source, effects, ids, transactions,
                    ) {
                    gaps.push(
                      capture_gap(
                        "unsafe_read_source", "An external read depends on an unknown, revoked, aborted or intermediate effect",
                      ),
                    )
                  }
              }
          }
        }
      }
    }
    for effect in effects {
      match sources.get(effect.predecessor) {
        None => ()
        Some(source) => {
          if source.key != effect.key {
            fail("Write predecessor belongs to another key")
          }
          match source.effect {
            Some(index) if effects[index].seq >= effect.seq =>
              fail("Write predecessor must precede its successor effect")
            Some(index) if effects[index].tx != effect.tx =>
              if !v3_capture_external_final(source, effects, ids, transactions) {
                gaps.push(
                  capture_gap(
                    "unsafe_write_source", "An external predecessor is not a committed final source",
                  ),
                )
              }
            _ => ()
          }
        }
      }
    }
    let successors : Map[String, String] = Map([])
    let final_counts : Map[String, Int] = Map([])
    // An incomplete source chain cannot safely be followed or exported.
    if gaps.length() == 0 {
      for tx in transactions {
        if tx.status == Committed {
          for index in tx.effects {
            let effect = effects[index]
            if effect.reverted_by is None &&
              v3_capture_own(tx, effect.key) == Some(effect.version) {
              let mut cursor = effect.predecessor
              let mut steps = 0
              while true {
                match sources.get(cursor).unwrap().effect {
                  Some(previous) if effects[previous].tx == tx.id => {
                    cursor = effects[previous].predecessor
                    steps += 1
                    if steps > effects.length() {
                      fail("Version predecessor cycle")
                    }
                  }
                  _ => break
                }
              }
              if successors.contains(cursor) {
                gaps.push(
                  capture_gap(
                    "version_order_gap", "Committed predecessor facts branch rather than form one chain",
                  ),
                )
              } else {
                successors[cursor] = effect.version
              }
              final_counts[effect.key] = final_counts.get_or_default(
                  effect.key,
                  0,
                ) +
                1
            }
          }
        }
      }
    }
    let orders : Map[String, Array[String]] = Map([])
    if gaps.length() == 0 {
      for key, first in initial {
        let order = [first]
        let mut cursor = first
        let mut count = 0
        while successors.contains(cursor) {
          cursor = successors.get(cursor).unwrap()
          order.push(cursor)
          count += 1
          if count > effects.length() {
            fail("Committed version chain contains a cycle")
          }
        }
        if count != final_counts.get_or_default(key, 0) {
          gaps.push(
            capture_gap(
              "version_order_gap", "Version chain does not cover every committed final effect",
            ),
          )
        }
        orders[key] = order
      }
    }
    if gaps.length() > 0 {
      return v3_capture_result(
        "inconclusive",
        gaps,
        observations,
        effects,
        transactions,
        Json::null(),
        None,
        proof_evidence,
      )
    }
    let projected_txs : Array[Transaction] = []
    for tx in transactions {
      let ops : Array[Operation] = []
      for step in tx.steps {
        match step.effect {
          Some(index) =>
            if effects[index].reverted_by is None {
              ops.push(step.op)
            }
          None => if !step.own { ops.push(step.op) }
        }
      }
      projected_txs.push({
        id: tx.id,
        status: tx.status,
        ops,
        start: None,
        end: None,
      })
    }
    let history = history_json({
      model: Serializable,
      initial,
      version_orders: orders,
      transactions: projected_txs,
    })
    match parse_history(history.stringify()) {
      Err(reason) => fail("Safe legacy projection rejected: " + reason)
      Ok(projected) => {
        let issues = validate_history(projected)
        if issues.length() > 0 {
          fail("Safe legacy projection rejected: " + issues[0].message)
        }
      }
    }
    v3_capture_result(
      "ready",
      [],
      observations,
      effects,
      transactions,
      history,
      None,
      proof_evidence,
    )
  } catch {
    error =>
      v3_capture_result(
        "invalid",
        [capture_gap("invalid_capture_v3", error.to_string())],
        observations,
        effects,
        transactions,
        Json::null(),
        Some(error.to_string()),
        proof_evidence,
      )
  }
}
