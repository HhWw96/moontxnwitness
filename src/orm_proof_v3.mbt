///|
fn orm_journal(text : String) -> Array[Json] raise {
  orm_assert(
    orm_utf8_size(text) <= 16777216 && text.has_suffix("\n"),
    "Bounded, newline-terminated source journal required",
  )
  let lines = text.split("\n").to_array()
  orm_assert(
    lines.length() >= 5 &&
    lines.length() <= 16385 &&
    lines[lines.length() - 1].is_empty(),
    "Incomplete/oversized source journal",
  )
  let records : Array[Json] = []
  let prefix = StringBuilder()
  for i in 0..<(lines.length() - 1) {
    let line = lines[i].to_owned()
    orm_assert(
      !line.is_empty() && orm_utf8_size(line) <= 131072,
      "Source record byte limit exceeded",
    )
    let value = guarded_json(line, limit=131072)
    ignore(orm_nodes(value, 0))
    let record = object_fields(value, "source record")
    orm_equal(
      required(record, "sourceSeq", "record"),
      Json(i + 1),
      "source sequence",
    )
    let kind = orm_text(required(record, "kind", "record"))
    if i == 0 {
      orm_equal(
        value,
        {
          "sourceSeq": 1,
          "kind": "header",
          "sourceSchema": "orm-source-draft/1",
          "coreProofAccepted": false,
        },
        "source header",
      )
    } else if i == 1 {
      orm_assert(
        kind == "installation",
        "Installation must immediately follow header",
      )
    } else if i == lines.length() - 2 {
      orm_exact(value, ["sourceSeq", "kind", "prefixSha256", "sourceRecords"])
      |> ignore
      orm_assert(kind == "seal", "Terminal source seal required")
      orm_equal(
        required(record, "sourceRecords", "seal"),
        Json(i),
        "sealed record count",
      )
      orm_equal(
        required(record, "prefixSha256", "seal"),
        Json(v3_dislock_sha256(prefix.to_string())),
        "original-byte journal seal",
      )
    } else if i == lines.length() - 3 {
      orm_assert(
        kind == "final-effect-ledger",
        "Final ledger must precede terminal seal",
      )
    } else {
      orm_assert(
        kind == "source-batch" || kind == "source-gap",
        "Unexpected source record kind/order",
      )
    }
    records.push(value)
    prefix.write_string(line)
    prefix.write_string("\n")
  }
  records
}

///|
fn orm_known_domain(
  installation : Map[String, Json],
) -> Map[String, Bool] raise {
  let known : Map[String, Bool] = Map([])
  let ids = orm_array(required(installation, "knownIds", "installation"))
  orm_assert(
    ids.length() > 0 && ids.length() <= 128,
    "Known UUID domain must have 1..128 entries",
  )
  for item in ids {
    let key = orm_uuid(item)
    orm_assert(!known.contains(key), "Duplicate known UUID")
    known[key] = true
  }
  let schema = orm_text(required(installation, "schema", "installation"))
  let table = orm_text(required(installation, "table", "installation"))
  orm_assert(
    schema.has_prefix("mtw_orm_v3_") &&
    schema.length() >= 12 &&
    schema.length() <= 51,
    "Explicit controlled ORM schema required",
  )
  for ch in schema.iter() {
    orm_assert(
      (ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9') || ch == '_',
      "Unsupported schema identifier",
    )
  }
  orm_assert(
    table.length() > 0 && table.length() <= 63,
    "Bounded table identifier required",
  )
  let mut i = 0
  for ch in table.iter() {
    orm_assert(
      (ch >= 'a' && ch <= 'z') || ch == '_' || (i > 0 && ch >= '0' && ch <= '9'),
      "Unsupported table identifier",
    )
    i += 1
  }
  known
}

///|
fn orm_initial_sources(
  metadata : Map[String, Json],
  known : Map[String, Bool],
  snapshot : Map[String, Json],
) -> Map[String, Json] raise {
  let initial = object_fields(
    required(metadata, "initialState", "metadata"),
    "initial state",
  )
  let tokens = object_fields(
    required(snapshot, "initial", "snapshot"),
    "snapshot tokens",
  )
  orm_assert(
    initial.length() == known.length() && tokens.length() == known.length(),
    "Initial state must exactly cover known UUIDs",
  )
  let sources : Map[String, Json] = Map([])
  for key, _ in known {
    let state = orm_exact(required(initial, key, "initial"), [
      "version", "present", "image",
    ])
    let version = orm_uuid(required(state, "version", "initial"))
    orm_equal(
      required(tokens, key, "snapshot"),
      Json(version),
      "initial snapshot token",
    )
    let present = required(state, "present", "state")
    orm_assert(
      present == Json(true) || present == Json(false),
      "Initial presence must be boolean",
    )
    let image = required(state, "image", "initial")
    orm_image(image, key, present == Json(true))
    orm_assert(!sources.contains(version), "Initial source UUID collision")
    sources[version] = {
      "key": Json(key),
      "version": Json(version),
      "present": present,
      "image": image,
      "seq": required(snapshot, "seq", "snapshot"),
      "writer": Json::null(),
      "effect": Json::null(),
    }
  }
  sources
}

///|
fn orm_effect_ledger(
  facts : Array[Json],
  events : Array[Json],
  transactions : Array[Json],
  sources : Map[String, Json],
  final_record : Map[String, Json],
  known : Map[String, Bool],
) -> (Array[Json], Json) raise {
  let effects : Array[OrmEffect] = []
  let by_row : Map[Int64, Json] = Map([])
  for fact in facts {
    let row = v3_capture_seq(orm_get(fact, "rows"), "fact rows")
    orm_assert(!by_row.contains(row), "Duplicate source row binding")
    by_row[row] = fact
  }
  let trails : Map[String, Array[Int32]] = Map([])
  let scopes : Map[String, Array[(String, Int32)]] = Map([])
  let outcomes : Map[String, String] = Map([])
  for tx in transactions {
    outcomes[orm_text(orm_get(tx, "id"))] = orm_text(orm_get(tx, "status"))
  }
  for event in events {
    let obj = object_fields(event, "event")
    let kind = orm_text(required(obj, "kind", "event"))
    let seq = v3_capture_seq(required(obj, "seq", "event"), "seq")
    if kind == "snapshot" {
      continue
    }
    let tx = orm_text(required(obj, "tx", "event"))
    if kind == "begin" {
      trails[tx] = []
      scopes[tx] = []
    }
    let trail = match trails.get(tx) {
      Some(value) => value
      None => fail("Source event lacks active transaction")
    }
    let stack = match scopes.get(tx) {
      Some(value) => value
      None => fail("Missing source scope stack")
    }
    if kind == "savepoint" {
      stack.push(
        (orm_text(required(obj, "instance", "savepoint")), trail.length()),
      )
    } else if kind == "rollback_to" || kind == "release" {
      let instance = orm_text(required(obj, "instance", "scope"))
      let mut target = -1
      for i, item in stack {
        if item.0 == instance {
          target = i
        }
      }
      orm_assert(target >= 0, "Unknown source savepoint instance")
      if kind == "rollback_to" {
        let mark = stack[target].1
        while trail.length() > mark {
          match trail.pop() {
            Some(index) => effects[index].reverted_by = Json(seq.to_double())
            None => ()
          }
        }
        while stack.length() > target + 1 {
          ignore(stack.pop())
        }
      } else {
        while stack.length() > target {
          ignore(stack.pop())
        }
      }
    }
    if kind == "rows" {
      match by_row.get(seq) {
        Some(fact) =>
          if orm_get(fact, "kind") == Json("write") {
            let data = object_fields(orm_get(fact, "data"), "write data")
            let version = orm_uuid(required(data, "version", "write"))
            orm_assert(
              !sources.contains(version),
              "Global source UUID collision",
            )
            sources[version] = {
              "key": required(data, "key", "write"),
              "version": Json(version),
              "present": required(data, "newPresent", "write"),
              "image": required(data, "newImage", "write"),
              "seq": Json(seq.to_double()),
              "writer": Json(tx),
              "effect": Json(effects.length()),
            }
            trail.push(effects.length())
            effects.push({
              tx,
              row_seq: seq,
              source_seq: v3_capture_seq(
                orm_get(fact, "sourceSeq"),
                "source seq",
              ),
              data,
              reverted_by: Json::null(),
            })
          }
        None => ()
      }
    }
    if kind == "rollback_ok" && outcomes.get(tx) == Some("aborted") {
      for index in trail {
        effects[index].reverted_by = Json(seq.to_double())
      }
      trail.clear()
    }
  }
  let last : Map[String, Map[String, Int32]] = Map([])
  for i, effect in effects {
    if effect.reverted_by == Json::null() {
      let table = match last.get(effect.tx) {
        Some(value) => value
        None => {
          let value = Map([])
          last[effect.tx] = value
          value
        }
      }
      table[orm_text(required(effect.data, "key", "effect"))] = i
    }
  }
  for fact in facts {
    let data = object_fields(orm_get(fact, "data"), "fact data")
    let write = orm_get(fact, "kind") == Json("write")
    let token = orm_uuid(
      required(data, if write { "predecessor" } else { "version" }, "fact"),
    )
    let source = object_fields(
      match sources.get(token) {
        Some(value) => value
        None => fail("Missing ORM source version")
      },
      "source",
    )
    let row_seq = v3_capture_seq(orm_get(fact, "rows"), "rows")
    orm_assert(
      v3_capture_seq(required(source, "seq", "source"), "producer seq") <
      row_seq,
      "Source appears after its observation",
    )
    orm_equal(
      required(source, "key", "source"),
      required(data, "key", "fact"),
      "source key",
    )
    orm_equal(
      required(source, "present", "source"),
      required(data, if write { "oldPresent" } else { "present" }, "fact"),
      "source presence",
    )
    orm_equal(
      required(source, "image", "source"),
      required(data, if write { "oldImage" } else { "image" }, "fact"),
      "source image",
    )
    let tx = orm_text(orm_get(fact, "tx"))
    let writer = required(source, "writer", "source")
    if writer != Json::null() {
      let writer = orm_text(writer)
      let index = match required(source, "effect", "source") {
        Number(n, ..) => n.to_int()
        _ => fail("Invalid effect reference")
      }
      let effect = effects[index]
      if writer == tx {
        orm_assert(
          effect.reverted_by == Json::null() ||
          v3_capture_seq(effect.reverted_by, "reverted seq") > row_seq,
          "Own source was already rolled back",
        )
      } else {
        orm_assert(
          outcomes.get(writer) == Some("committed") &&
          effect.reverted_by == Json::null(),
          "External source outcome/revocation not proven",
        )
        let finals = match last.get(writer) {
          Some(value) => value
          None => fail("External source has no surviving effect")
        }
        orm_assert(
          finals.get(orm_text(required(source, "key", "source"))) == Some(index),
          "External intermediate source is not transaction final",
        )
      }
    }
    // A present own overlay at observation time must be used, irrespective of
    // whether a later savepoint rollback revokes that version.
    let mut latest : Int64 = 0L
    let mut latest_token = ""
    for effect in effects {
      if effect.tx == tx &&
        effect.row_seq < row_seq &&
        required(effect.data, "key", "effect") == required(data, "key", "fact") &&
        (
          effect.reverted_by == Json::null() ||
          v3_capture_seq(effect.reverted_by, "revocation") > row_seq
        ) &&
        effect.row_seq > latest {
        latest = effect.row_seq
        latest_token = orm_text(required(effect.data, "version", "effect"))
      }
    }
    orm_assert(
      latest == 0L || latest_token == token,
      "Own overlay source mismatch",
    )
  }
  let ledger = orm_array(required(final_record, "ledger", "final ledger"))
  let actual : Map[String, Json] = Map([])
  for entry in ledger {
    let item = orm_exact(entry, [
      "key", "version", "predecessor", "action", "oldPresent", "newPresent", "oldImage",
      "newImage",
    ])
    let token = orm_uuid(required(item, "version", "ledger"))
    orm_assert(!actual.contains(token), "Duplicate final effect ledger token")
    actual[token] = entry
  }
  let surviving : Map[String, Json] = Map([])
  let output : Array[Json] = []
  for effect in effects {
    let token = orm_text(required(effect.data, "version", "effect"))
    let committed = outcomes.get(effect.tx) == Some("committed")
    let live = committed && effect.reverted_by == Json::null()
    if live {
      orm_equal(
        match actual.get(token) {
          Some(value) => value
          None => fail("Missing committed effect in server ledger")
        },
        Json(effect.data),
        "actual committed effect ledger",
      )
      surviving[token] = Json(effect.data)
    } else {
      orm_assert(
        !actual.contains(token),
        "Aborted/reverted/unknown effect present in final server ledger",
      )
    }
    output.push({
      "tx": Json(effect.tx),
      "rows": Json(effect.row_seq.to_double()),
      "sourceSeq": Json(effect.source_seq.to_double()),
      "data": Json(effect.data),
      "revertedBy": effect.reverted_by,
      "outcome": match outcomes.get(effect.tx) {
        Some(value) => Json(value)
        None => Json::null()
      },
    })
  }
  orm_assert(
    actual.length() == surviving.length(),
    "Final ledger contains unobserved effects",
  )
  let final_state = object_fields(
    required(final_record, "state", "final ledger"),
    "final state",
  )
  orm_assert(
    final_state.length() == known.length(),
    "Final state does not exactly cover declared keys",
  )
  let successors : Map[String, Json] = Map([])
  for _, effect in surviving {
    let pred = orm_text(orm_get(effect, "predecessor"))
    orm_assert(!successors.contains(pred), "Committed source chain branches")
    successors[pred] = effect
  }
  let visited : Map[String, Bool] = Map([])
  for key, _ in known {
    let mut token = ""
    let mut current : Json = Json::null()
    for id, source in sources {
      if orm_get(source, "writer") == Json::null() &&
        orm_get(source, "key") == Json(key) {
        token = id
        current = source
      }
    }
    orm_assert(!token.is_empty(), "Missing initial chain root")
    for _ in 0..<(surviving.length() + 1) {
      match successors.get(token) {
        Some(effect) => {
          let next = orm_text(orm_get(effect, "version"))
          orm_assert(!visited.contains(next), "Committed source cycle")
          orm_equal(orm_get(effect, "key"), Json(key), "committed chain key")
          orm_equal(
            orm_get(effect, "oldPresent"),
            orm_get(current, "present"),
            "committed chain OLD presence",
          )
          orm_equal(
            orm_get(effect, "oldImage"),
            orm_get(current, "image"),
            "committed chain OLD image",
          )
          visited[next] = true
          token = next
          current = {
            "version": Json(token),
            "present": orm_get(effect, "newPresent"),
            "image": orm_get(effect, "newImage"),
          }
        }
        None => break
      }
    }
    orm_equal(
      required(final_state, key, "final state"),
      {
        "version": Json(token),
        "present": orm_get(current, "present"),
        "image": orm_get(current, "image"),
      },
      "final same-key source state",
    )
  }
  orm_assert(
    visited.length() == surviving.length(),
    "Final ledger has disconnected source chains",
  )
  (
    output,
    {
      "observedEffects": Json(effects.length()),
      "committedUnrevertedEffects": Json(surviving.length()),
      "serverLedgerEffects": Json(actual.length()),
      "sourceChainsChecked": true,
    },
  )
}

///|
pub fn orm_sql_v3_proof_json(text : String) -> String {
  try {
    orm_assert(
      text.length() <= 67108864 && orm_utf8_size(text) <= 67108864,
      "ORM diagnostic envelope byte budget exceeded",
    )
    let input = orm_exact(guarded_json(text, limit=67108864), [
      "schema", "profile", "traceText", "sourceJournalText",
    ])
    orm_equal(required(input, "schema", "input"), Json(1), "diagnostic schema")
    orm_equal(
      required(input, "profile", "input"),
      Json("fastapi-users-sqlalchemy-7.0.0-pg18/1"),
      "diagnostic profile",
    )
    let trace_text = orm_text(required(input, "traceText", "input"))
    orm_assert(
      orm_utf8_size(trace_text) <= 8388608,
      "Raw trace byte limit exceeded",
    )
    let root = object_fields(guarded_json(trace_text, limit=8388608), "trace")
    let lifecycle = object_fields(
      guarded_json(
        normalize_register_capture_v3_json(trace_text),
        limit=33554432,
      ),
      "lifecycle",
    )
    orm_assert(
      required(lifecycle, "status", "lifecycle") != Json("invalid"),
      "Invalid v3 lifecycle cannot receive source diagnostics",
    )
    let events = orm_array(required(root, "events", "trace"))
    orm_assert(
      events.length() > 0 && events.length() <= 65536,
      "Trace event budget exceeded",
    )
    let snapshot = object_fields(events[0], "snapshot")
    orm_equal(
      required(snapshot, "kind", "snapshot"),
      Json("snapshot"),
      "initial event",
    )
    orm_equal(
      required(snapshot, "seq", "snapshot"),
      Json(1),
      "snapshot sequence",
    )
    orm_equal(
      required(snapshot, "consistent", "snapshot"),
      Json(true),
      "consistent initialized snapshot",
    )
    orm_equal(
      orm_get(required(root, "scope", "trace"), "exclusiveWriters"),
      Json(true),
      "controlled writers",
    )
    let records = orm_journal(
      orm_text(required(input, "sourceJournalText", "input")),
    )
    let installation = object_fields(records[1], "installation")
    let known = orm_known_domain(installation)
    let metadata = object_fields(
      required(installation, "metadata", "installation"),
      "metadata",
    )
    let sources = orm_initial_sources(metadata, known, snapshot)
    let schema = orm_text(required(installation, "schema", "installation"))
    let table = orm_text(required(installation, "table", "installation"))
    let gaps = orm_array(
      orm_get(required(lifecycle, "coverage", "lifecycle"), "gaps"),
    )
    let catalog = orm_verify_catalog(installation, gaps)
    let event_map : Map[Int64, Map[String, Json]] = Map([])
    for i, event in events {
      let obj = object_fields(event, "event")
      orm_equal(
        required(obj, "seq", "event"),
        Json(i + 1),
        "contiguous original event sequence",
      )
      event_map[(i + 1).to_int64()] = obj
    }
    let statements : Array[Json] = []
    let batches : Array[Json] = []
    let facts : Array[Json] = []
    let seen_statement : Map[Int64, Bool] = Map([])
    let seen_rows : Map[Int64, Bool] = Map([])
    for i in 2..<(records.length() - 2) {
      let batch = object_fields(records[i], "source batch")
      if required(batch, "kind", "batch") == Json("source-gap") {
        gaps.push(
          capture_gap(
            "orm_source_gap", "Observed zero/error source result grants no invented read/write fact",
          ),
        )
        continue
      }
      let statement_seq = v3_capture_seq(
        required(batch, "statement", "batch"),
        "statement",
      )
      let rows_seq = v3_capture_seq(
        required(batch, "businessRowsEvent", "batch"),
        "rows",
      )
      orm_assert(
        statement_seq < rows_seq &&
        !seen_statement.contains(statement_seq) &&
        !seen_rows.contains(rows_seq),
        "Duplicate/reversed source event binding",
      )
      let statement = match event_map.get(statement_seq) {
        Some(value) => value
        None => fail("Missing original source statement")
      }
      let row = match event_map.get(rows_seq) {
        Some(value) => value
        None => fail("Missing original delivered rows event")
      }
      let plan = orm_match_plan(batch, schema, table)
      let fact = orm_verify_batch(batch, plan, statement, row, known)
      seen_statement[statement_seq] = true
      seen_rows[rows_seq] = true
      statements.push({
        "statement": Json(statement_seq.to_double()),
        "mappingId": Json(plan.mapping),
      })
      batches.push({
        "sourceSeq": required(batch, "sourceSeq", "batch"),
        "statement": Json(statement_seq.to_double()),
        "rows": Json(rows_seq.to_double()),
        "kind": orm_get(fact, "kind"),
      })
      facts.push(fact)
    }
    for event in events {
      if orm_get(event, "kind") == Json("statement") &&
        !seen_statement.contains(
          v3_capture_seq(orm_get(event, "seq"), "statement"),
        ) {
        gaps.push(
          capture_gap(
            "orm_unproven_statement", "Original statement has no complete same-statement source batch",
          ),
        )
      }
    }
    let (effects, ledger) = orm_effect_ledger(
      facts,
      events,
      orm_array(required(lifecycle, "transactions", "lifecycle")),
      sources,
      object_fields(records[records.length() - 2], "final ledger"),
      known,
    )
    gaps.push(
      capture_gap(
        "orm_diagnostic_transport_only", "This isolated draft never grants capture coverage exemptions or produces accepted history",
      ),
    )
    let result : Json = {
      "schema": 1,
      "algorithm": "v3-orm-source-proof-1",
      "analysisCoverageAccepted": false,
      "history": Json::null(),
      "matchedStatements": Json(statements),
      "verifiedSourceBatches": Json(batches),
      "candidateFacts": Json(facts),
      "verifiedStatements": [],
      "verifiedFacts": [],
      "verifiedProfiles": [],
      "gaps": Json(gaps),
      "capturedCatalogChecked": catalog,
      "observedEffects": Json(effects),
      "ledger": ledger,
      "traceSha256": Json(v3_dislock_sha256(trace_text)),
      "sourceJournalSha256": Json(
        v3_dislock_sha256(
          orm_text(required(input, "sourceJournalText", "input")),
        ),
      ),
      "scope": "Semantic consistency under controlled writers/no unobserved DDL assumptions; captured metadata is not database authentication.",
    }
    result.stringify(indent=2)
  } catch {
    error => {
      let result : Json = {
        "schema": 1,
        "algorithm": "v3-orm-source-proof-1",
        "analysisCoverageAccepted": false,
        "history": Json::null(),
        "matchedStatements": [],
        "verifiedSourceBatches": [],
        "candidateFacts": [],
        "verifiedStatements": [],
        "verifiedFacts": [],
        "verifiedProfiles": [],
        "gaps": [capture_gap("invalid_orm_source_proof", error.to_string())],
      }
      result.stringify(indent=2)
    }
  }
}
