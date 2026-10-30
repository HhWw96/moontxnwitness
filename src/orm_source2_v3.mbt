///|
pub fn orm_sql_source2_v3_proof_json(text : String) -> String {
  try {
    orm_assert(
      text.length() <= 67108864 && orm_utf8_size(text) <= 67108864,
      "SourceSchema2 diagnostic envelope limit",
    )
    let input = orm_exact(guarded_json(text, limit=67108864), [
      "schema", "profile", "traceText", "sourceJournalText",
    ])
    orm_equal(
      required(input, "schema", "input"),
      Json(2),
      "Separate sourceSchema2 diagnostic input",
    )
    orm_equal(
      required(input, "profile", "input"),
      Json("fastapi-users-sqlalchemy-7.0.0-pg18/1"),
      "Pinned ORM profile",
    )
    let trace_text = orm_text(required(input, "traceText", "input"))
    orm_assert(orm_utf8_size(trace_text) <= 8388608, "Raw trace byte budget")
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
      "Invalid lifecycle cannot receive sourceSchema2 proof",
    )
    let events = orm_array(required(root, "events", "trace"))
    orm_assert(
      !events.is_empty() && events.length() <= 65536,
      "Bounded original events required",
    )
    let snapshot = object_fields(events[0], "snapshot")
    orm_equal(
      required(snapshot, "kind", "snapshot"),
      Json("snapshot"),
      "First actual initialized snapshot",
    )
    orm_equal(
      required(snapshot, "seq", "snapshot"),
      Json(1),
      "Actual snapshot sequence",
    )
    orm_equal(
      required(snapshot, "consistent", "snapshot"),
      Json(true),
      "Consistent actual initial snapshot",
    )
    orm_equal(
      orm_get(required(root, "scope", "trace"), "exclusiveWriters"),
      Json(true),
      "Declared controlled writer scope",
    )
    let (records, installation_index, initial_controls, final_controls) = orm2_journal(
      orm_text(required(input, "sourceJournalText", "input")),
    )
    let installation = object_fields(
      records[installation_index],
      "installation",
    )
    let final_record = object_fields(
      records[records.length() - 2],
      "final ledger",
    )
    let known = orm_known_domain(installation)
    let metadata = object_fields(
      required(installation, "metadata", "installation"),
      "metadata",
    )
    let sources = orm_initial_sources(metadata, known, snapshot)
    let (initialization, initial_queries) = orm2_init_profile(
      installation, initial_controls, known,
    )
    let (finalization, final_queries) = orm2_final_profile(
      installation, final_record, final_controls, known,
    )
    let schema = orm_text(required(installation, "schema", "installation"))
    let table = orm_text(required(installation, "table", "installation"))
    let gaps = orm_array(
      orm_get(required(lifecycle, "coverage", "lifecycle"), "gaps"),
    )
    let event_map : Map[Int64, Map[String, Json]] = Map([])
    for i, event in events {
      let obj = object_fields(event, "event")
      orm_equal(
        required(obj, "seq", "event"),
        Json(i + 1),
        "Original event sequence",
      )
      event_map[(i + 1).to_int64()] = obj
    }
    let statements : Array[Json] = []
    let batches : Array[Json] = []
    let facts : Array[Json] = []
    let seen_statement : Map[Int64, Bool] = Map([])
    let seen_rows : Map[Int64, Bool] = Map([])
    for i in (installation_index + 1)..<(records.length() - 2) {
      let batch = object_fields(records[i], "sourceSchema2 batch")
      let kind = required(batch, "kind", "batch")
      if kind == Json("control-query") {
        continue
      }
      if kind == Json("source-gap") {
        gaps.push(
          capture_gap(
            "orm_source_gap", "Original zero/error source result has no invented read or write",
          ),
        )
        continue
      }
      orm_equal(kind, Json("source-batch"), "Original source batch kind")
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
        "Duplicate/reversed business source binding",
      )
      let statement = match event_map.get(statement_seq) {
        Some(value) => value
        None => fail("Missing original business statement")
      }
      let row = match event_map.get(rows_seq) {
        Some(value) => value
        None => fail("Missing actual delivered business rows")
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
            "orm_unproven_statement", "Original statement lacks complete same-statement source evidence",
          ),
        )
      }
    }
    let (effects, ledger) = orm_effect_ledger(
      facts,
      events,
      orm_array(required(lifecycle, "transactions", "lifecycle")),
      sources,
      final_record,
      known,
    )
    let controls : Array[Json] = []
    for query in initial_queries {
      controls.push(query)
    }
    for query in final_queries {
      controls.push(query)
    }
    gaps.push(
      capture_gap(
        "orm_diagnostic_transport_only", "Local sourceSchema2 proofs grant no capture coverage exemptions or accepted history",
      ),
    )
    let result : Json = {
      "schema": 2,
      "algorithm": "v3-orm-source-proof-2",
      "analysisCoverageAccepted": false,
      "history": Json::null(),
      "controlProfileComplete": true,
      "matchedStatements": Json(statements),
      "verifiedSourceBatches": Json(batches),
      "candidateFacts": Json(facts),
      "provenStatements": Json(statements),
      "provenFacts": Json(facts),
      "verifiedStatements": [],
      "verifiedFacts": [],
      "verifiedProfiles": [],
      "verifiedControlQueries": Json(controls),
      "initializationEvidence": initialization,
      "finalizationEvidence": finalization,
      "observedEffects": Json(effects),
      "ledger": ledger,
      "gaps": Json(gaps),
      "traceSha256": Json(v3_dislock_sha256(trace_text)),
      "sourceJournalSha256": Json(
        v3_dislock_sha256(
          orm_text(required(input, "sourceJournalText", "input")),
        ),
      ),
      "scope": "Individual original source proofs under controlled writers, standard adapters and no unobserved DDL/metadata assumptions; no database authentication or complete-trace acceptance.",
    }
    result.stringify(indent=2)
  } catch {
    error => {
      let result : Json = {
        "schema": 2,
        "algorithm": "v3-orm-source-proof-2",
        "analysisCoverageAccepted": false,
        "history": Json::null(),
        "controlProfileComplete": false,
        "matchedStatements": [],
        "verifiedSourceBatches": [],
        "candidateFacts": [],
        "provenStatements": [],
        "provenFacts": [],
        "verifiedStatements": [],
        "verifiedFacts": [],
        "verifiedProfiles": [],
        "verifiedControlQueries": [],
        "gaps": [capture_gap("invalid_orm_source2_proof", error.to_string())],
      }
      result.stringify(indent=2)
    }
  }
}
