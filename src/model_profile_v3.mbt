///|
fn model_diagnostic_gaps_v3(raw : Json, index~ : Bool = false) -> Unit raise {
  let seen : Map[String, Bool] = Map([])
  for raw in orm_array(raw) {
    let gap = orm_exact(raw, ["code", "message"])
    let code = orm_text(required(gap, "code", "gap"))
    let message = orm_text(required(gap, "message", "gap"))
    let expected = match code {
      "initialization_unproven" =>
        "The initial database snapshot has not been established as consistent."
      "diagnostic_instrumentation_only" =>
        "No verified initial/version/predicate mapping; raw observations never grant complete analysis coverage."
      "source_unsealed" if !index =>
        "Journal and explicit source window have not both been sealed."
      "diagnostic_only" if !index =>
        "This export is incomplete diagnostic evidence, not a complete analysis input."
      _ => fail("Unresolved original diagnostic gap prevents model projection")
    }
    orm_assert(
      !seen.contains(code) && message == expected,
      "Exact retained raw diagnostic gap",
    )
    seen[code] = true
  }
  orm_assert(
    seen.length() == (if index { 2 } else { 4 }),
    "All original diagnostic boundaries remain present",
  )
}

///|
fn model_index_v3(text : String, events : Array[Json]) -> Unit raise {
  orm_assert(orm_utf8_size(text) <= 2097152, "Original index byte bound")
  let index = object_fields(
    guarded_json(text, limit=2097152),
    "model source index",
  )
  orm_profile_index_digest_v3(text, index)
  for
    (name, value) in [
      ("indexSchema", Json(1)),
      ("traceSchema", Json(3)),
      ("closed", Json(true)),
      ("sourceClosed", Json(false)),
      ("eventCount", Json(events.length())),
      ("durableSeq", Json(events.length())),
    ] {
    orm_equal(required(index, name, "index"), value, "Original index " + name)
  }
  orm_assert(!events.is_empty(), "Original journal has a diagnostic snapshot")
  orm_equal(
    required(index, "lastTime", "index"),
    orm_get(events[events.length() - 1], "time"),
    "Original index/export tail",
  )
  for name in ["activeTransactions", "commitRequests"] {
    orm_assert(
      orm_array(required(index, name, "index")).is_empty(),
      "No active transaction or outstanding commit request",
    )
  }
  let refs = orm_exact(required(index, "references", "index"), [
    "activeTransactions", "unreadResults", "versionSources",
  ])
  for name in ["activeTransactions", "unreadResults"] {
    orm_assert(
      orm_array(required(refs, name, "references")).is_empty(),
      "No active source/result reference",
    )
  }
  model_diagnostic_gaps_v3(required(index, "gaps", "index"), index=true)
  let segments = orm_array(required(index, "segments", "index"))
  orm_assert(
    !segments.is_empty() && segments.length() <= 4096,
    "Bounded original segment descriptors",
  )
  let mut next = 1L
  for raw in segments {
    let segment = object_fields(raw, "segment")
    let count = v3_capture_seq(
      required(segment, "eventCount", "segment"),
      "count",
    )
    let first = v3_capture_seq(
      required(segment, "firstSeq", "segment"),
      "first",
    )
    let last = v3_capture_seq(required(segment, "lastSeq", "segment"), "last")
    orm_assert(
      count <= 65536L && first == next && last == first + count - 1L,
      "Contiguous original segment sequence descriptors",
    )
    next = last + 1L
  }
  orm_assert(
    next == (events.length() + 1).to_int64(),
    "Original descriptors exactly cover exported observations",
  )
}

///|
/// The model source package contains original observations, never an accepted
/// Python history. Projection is accepted only after independent SQL, source,
/// actual delivery, transaction, lifecycle and committed-effect checks.
pub fn model_profile_source_v3_json(
  text : String,
  options_text : String,
) -> String {
  let mut raw_coverage : Json = Json::null()
  try {
    orm_assert(
      orm_utf8_size(text) <= 67108864 && orm_utf8_size(options_text) <= 4096,
      "Bounded model profile input/options",
    )
    let input = orm_exact(guarded_json(text, limit=67108864), [
      "format", "profile", "traceText", "sourceJournalText", "lifecycleText", "journalIndexText",
    ])
    orm_equal(
      required(input, "format", "input"),
      Json("moontxnwitness-model-profile-source/v1"),
      "Separate configured model source format",
    )
    orm_equal(
      required(input, "profile", "input"),
      Json("pg18-configured-models/1"),
      "Pinned model source profile",
    )
    let trace_text = orm_text(required(input, "traceText", "input"))
    let source_text = orm_text(required(input, "sourceJournalText", "input"))
    let lifecycle_text = orm_text(required(input, "lifecycleText", "input"))
    let index_text = orm_text(required(input, "journalIndexText", "input"))
    let trace = object_fields(
      guarded_json(trace_text, limit=8388608),
      "original diagnostic",
    )
    model_diagnostic_gaps_v3(required(trace, "gaps", "trace"))
    let lifecycle = object_fields(
      guarded_json(
        normalize_register_capture_v3_json(trace_text),
        limit=33554432,
      ),
      "original normalized lifecycle",
    )
    raw_coverage = required(lifecycle, "coverage", "lifecycle")
    orm_assert(
      required(lifecycle, "status", "lifecycle") != Json("invalid"),
      "Original diagnostic lifecycle is valid",
    )
    let events = orm_array(required(trace, "events", "trace"))
    orm_assert(!events.is_empty(), "Original diagnostic snapshot exists")
    orm_equal(
      orm_get(events[0], "kind"),
      Json("snapshot"),
      "Original diagnostic begins with raw snapshot boundary",
    )
    orm_equal(
      orm_get(events[0], "initial"),
      Json::object(Map([])),
      "Original generic diagnostic contains no manufactured initial model versions",
    )
    orm_equal(
      orm_get(events[0], "consistent"),
      Json(false),
      "Original generic diagnostic keeps its unproved initial flag",
    )
    orm_equal(
      orm_get(required(trace, "scope", "trace"), "exclusiveWriters"),
      Json(false),
      "Original generic writer scope is not silently upgraded",
    )
    let (records, installation_index, initial_controls, final_controls) = orm2_journal(
      source_text,
    )
    let installation = orm_exact(records[installation_index], [
      "sourceSeq", "kind", "profile", "nonce", "config", "installationQueries", "window",
    ])
    let final_record = orm_exact(records[records.length() - 2], [
      "sourceSeq", "kind", "profile", "nonce", "window",
    ])
    for record in [installation, final_record] {
      orm_equal(
        required(record, "profile", "source"),
        Json("pg18-configured-models/1"),
        "One independently configured source profile",
      )
    }
    orm_equal(
      required(final_record, "nonce", "finalization"),
      required(installation, "nonce", "installation"),
      "Original installation/finalization nonce",
    )
    let config = model_config_v3(
      required(installation, "config", "installation"),
    )
    for record in records {
      orm_assert(
        orm_get(record, "kind") != Json("source-gap"),
        "No missing/unknown original source effect",
      )
    }
    for control in final_controls {
      orm_assert(
        control.connection == initial_controls[0].connection &&
        control.backend == initial_controls[0].backend,
        "Original setup connection/backend spans both source boundaries",
      )
    }
    let source = model_controls_v3(
      config, installation, final_record, initial_controls, final_controls,
    )
    let window = model_lifecycle_v3(lifecycle_text, installation, final_record)
    model_index_v3(index_text, events)
    let transactions = orm_array(
      required(lifecycle, "transactions", "lifecycle"),
    )
    let calls = orm_profile_calls_v3(window, events, transactions)
    let (derived, origins, effects) = model_projection_v3(
      config,
      records,
      events,
      source,
      transactions,
      required(trace, "clockDomain", "trace"),
    )
    model_closure_v3(config, source, effects)
    let analysis = if config.is_list {
      list_v3_analysis(derived.stringify(), options_text)
    } else {
      relation_v3_analysis(derived.stringify(), options_text)
    }
    orm_assert(
      orm_get(analysis, "status") != Json("invalid"),
      "Independently derived model history remains valid",
    )
    orm_equal(
      orm_get(orm_get(analysis, "coverage"), "complete"),
      Json(true),
      "No missing lifecycle or version source in derived model",
    )
    let report : Json = {
      "schemaVersion": 3,
      "tool": "MoonTxnWitness",
      "version": Json(version()),
      "algorithm": "v3-configured-model-source-projection-1",
      "profile": "pg18-configured-models/1",
      "status": orm_get(analysis, "status"),
      "analysisCoverageAccepted": true,
      "originalDiagnosticCoverage": raw_coverage,
      "derivedTrace": derived,
      "retainedOriginalSeq": Json(origins),
      "analysis": analysis,
      "mappingCoverage": {
        "complete": true,
        "gaps": [],
        "actualCalls": calls,
        "sourceWindowsChecked": true,
        "committedEffectsChecked": Json(effects.length()),
      },
      "sourceBindings": {
        "traceSha256": Json(v3_dislock_sha256(trace_text)),
        "sourceJournalSha256": Json(v3_dislock_sha256(source_text)),
        "lifecycleSha256": Json(v3_dislock_sha256(lifecycle_text)),
        "journalIndexSha256": Json(v3_dislock_sha256(index_text)),
      },
      "scope": "Explicit new controlled PostgreSQL18 schema and one startup synchronous psycopg factory; exact registered list append/point read or relation point CRUD/AND SELECT only. RETURNING is not a predicate read. Original raw gaps remain incomplete; source/driver observations are independently projected. Source checks bind the supplied index self-checksum/descriptors, not absent segment payloads. Hashes do not authenticate the server or exclusive writer declaration. No ORM, async, savepoint, arbitrary SQL/table, mixed model, isolation-level or real-time claim.",
    }
    report.stringify(indent=2)
  } catch {
    error => {
      let report : Json = {
        "schemaVersion": 3,
        "tool": "MoonTxnWitness",
        "version": Json(version()),
        "algorithm": "v3-configured-model-source-projection-1",
        "profile": "pg18-configured-models/1",
        "status": "inconclusive",
        "analysisCoverageAccepted": false,
        "originalDiagnosticCoverage": raw_coverage,
        "derivedTrace": Json::null(),
        "analysis": Json::null(),
        "mappingCoverage": {
          "complete": false,
          "gaps": [capture_gap("model_profile_not_proven", error.to_string())],
        },
      }
      report.stringify(indent=2)
    }
  }
}
