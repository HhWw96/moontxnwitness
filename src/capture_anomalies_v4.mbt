///|
priv struct CaptureSourceAnomalyEffectV4 {
  seq : Int64
  tx : String
  key : String
  identity : String
  value : Json
  revoked : Int64?
}

///|
priv struct CaptureSourceAnomalyWorkV4 {
  maximum : Int32
  mut checks : Int32
  mut limited : Bool
  mut truncated : Bool
  findings : Array[Json]
  gaps : Array[Json]
  outcomes : Map[String, String]
  transactions : Map[String, Json]
  sources : Map[String, Map[String, CaptureSourceAnomalyEffectV4]]
  finals : Map[String, Map[String, CaptureSourceAnomalyEffectV4]]
  positions : Map[String, Map[String, Int32]]
  append_counts : Map[String, Map[String, Int32]]
  initial : Map[String, Array[String]]
  mut window : CaptureWindowV5?
}

///|
/// Source-only capture diagnostics. The private record is detached by its getter.
pub struct CaptureAnomaliesV4 {
  priv record : Json
}

///|
fn capture_source_charge_v4(work : CaptureSourceAnomalyWorkV4) -> Bool {
  if work.checks >= work.maximum {
    work.limited = true
    false
  } else {
    work.checks += 1
    true
  }
}

///|
fn capture_source_seq_v4(value : Json) -> Int64 {
  match value {
    Number(n, ..) => n.to_int64()
    _ => abort("Validated capture sequence")
  }
}

///|
fn capture_source_string_v4(value : Json) -> String {
  match value {
    String(text) => text
    _ => abort("Validated capture identity")
  }
}

///|
fn capture_source_array_v4(value : Json) -> Array[Json] {
  match value {
    Array(values) => values
    _ => []
  }
}

///|
fn capture_source_emit_v4(
  work : CaptureSourceAnomalyWorkV4,
  finding : Bool,
  item : Json,
) -> Unit {
  if work.findings.length() + work.gaps.length() >= 256 {
    work.truncated = true
    if finding && !work.gaps.is_empty() {
      ignore(work.gaps.pop())
      work.findings.push(item)
    }
  } else if finding {
    work.findings.push(item)
  } else {
    work.gaps.push(item)
  }
}

///|
fn capture_source_gap_v4(
  work : CaptureSourceAnomalyWorkV4,
  code : String,
  evidence : Json,
) -> Unit {
  capture_source_emit_v4(work, false, {
    "code": Json(code),
    "evidence": evidence,
  })
}

///|
fn capture_source_event_ref_v4(event : Json) -> Json {
  let e = object_fields_unchecked_v3(event)
  {
    "eventSeq": e.at("seq"),
    "transaction": e.get_or_default("tx", Json::null()),
    "kind": e.at("kind"),
    "key": e.get_or_default("key", Json::null()),
  }
}

///|
fn capture_source_effect_ref_v4(
  work : CaptureSourceAnomalyWorkV4,
  effect : CaptureSourceAnomalyEffectV4,
) -> Json {
  let complete = match work.window {
    Some(w) => w.closed.get_or_default(effect.tx, false)
    _ => false
  }
  let aborted = work.outcomes.get(effect.tx) == Some("aborted")
  let prefix = effect.revoked is Some(at) &&
    capture_prefix_known_v5(work.window, effect.tx, at)
  let known = complete || aborted || prefix
  let trusted = if aborted && !prefix {
    object_fields_unchecked_v3(
      work.transactions.get_or_default(effect.tx, Json::null()),
    ).get_or_default("endSeq", Json::null())
  } else if known {
    match effect.revoked {
      Some(seq) => Json(seq.to_double())
      None => Json::null()
    }
  } else {
    Json::null()
  }
  {
    "eventSeq": Json(effect.seq.to_double()),
    "transaction": if effect.tx == "" {
      Json::null()
    } else {
      Json(effect.tx)
    },
    "key": Json(effect.key),
    "identity": Json(effect.identity),
    "outcome": if effect.tx == "" {
      Json("initial")
    } else {
      Json(work.outcomes.get_or_default(effect.tx, "unknown"))
    },
    "writeJournalComplete": Json(complete),
    "revocationKnown": Json(known),
    "revertedBy": trusted,
    "observedLedgerRevertedBy": match effect.revoked {
      Some(seq) => Json(seq.to_double())
      None => Json::null()
    },
    "transactionOutcome": work.transactions.get_or_default(
      effect.tx,
      Json::null(),
    ),
  }
}

///|
fn capture_source_proof_v4(
  work : CaptureSourceAnomalyWorkV4,
  category : String,
  basis : String,
  event : Json,
  source : CaptureSourceAnomalyEffectV4,
  final_effect : CaptureSourceAnomalyEffectV4?,
) -> Unit {
  let evidence : Json = {
    "basis": Json(basis),
    "observation": capture_source_event_ref_v4(event),
    "sourceEffect": capture_source_effect_ref_v4(work, source),
    "originalObservationPointer": "observations.document.events where seq equals observation.eventSeq",
    "sourceIdentityComparedBy": "key-and-unique-version-or-item-identity",
    "clientSequenceIsCommitOrder": false,
  }
  match final_effect {
    Some(effect) =>
      object_fields_unchecked_v3(evidence)["laterEffectiveWrite"] = capture_source_effect_ref_v4(
        work, effect,
      )
    None => ()
  }
  capture_source_emit_v4(work, true, {
    "category": Json(category),
    "specificCategory": Json(category),
    "impliedAnomalies": if category == "dirty-update" {
      Json((["dirty-update", "G1a", "G1"] : Array[String]))
    } else {
      Json([category, "G1"])
    },
    "evidence": evidence,
  })
}

///|
fn capture_source_lookup_v4(
  work : CaptureSourceAnomalyWorkV4,
  key : String,
  identity : String,
  event : Json,
) -> CaptureSourceAnomalyEffectV4? {
  match work.sources.get_or_default(key, Map([])).get(identity) {
    None => {
      capture_source_gap_v4(work, "missing-source", {
        "observation": capture_source_event_ref_v4(event),
        "identity": Json(identity),
      })
      None
    }
    Some(source) => {
      let seq = capture_source_seq_v4(
        object_fields_unchecked_v3(event).at("seq"),
      )
      if source.seq >= seq {
        capture_source_gap_v4(work, "source-not-observed-before-use", {
          "observation": capture_source_event_ref_v4(event),
          "sourceEffect": capture_source_effect_ref_v4(work, source),
          "reason": "A later client observation does not prove database visibility or a future read",
        })
        None
      } else {
        Some(source)
      }
    }
  }
}

///|
fn capture_source_classify_ref_v4(
  work : CaptureSourceAnomalyWorkV4,
  event : Json,
  source : CaptureSourceAnomalyEffectV4,
  writing : Bool,
  intermediate : Bool,
) -> Unit {
  let e = object_fields_unchecked_v3(event)
  let reader = capture_source_string_v4(e.at("tx"))
  if source.tx == "" {
    return
  }
  if source.tx == reader {
    let seq = capture_source_seq_v4(e.at("seq"))
    match source.revoked {
      Some(at) if at < seq =>
        capture_source_gap_v4(work, "own-revoked-source", {
          "observation": capture_source_event_ref_v4(event),
          "sourceEffect": capture_source_effect_ref_v4(work, source),
          "scope": "Own-source consistency requires a separate INT check; it is not external G1a/G1b/dirty-update",
        })
      _ => ()
    }
    return
  }
  let outcome = work.outcomes.get_or_default(source.tx, "unknown")
  // Confirmed revocation is useful even when the enclosing outcome is unknown.
  let known_revocation = match source.revoked {
    Some(at) => capture_prefix_known_v5(work.window, source.tx, at)
    None => false
  }
  if outcome == "aborted" || known_revocation {
    capture_source_proof_v4(
      work,
      if writing {
        "dirty-update"
      } else {
        "G1a"
      },
      if outcome == "aborted" {
        "external-confirmed-aborted-source"
      } else {
        "external-confirmed-revoked-source"
      },
      event,
      source,
      None,
    )
  } else if source.revoked is Some(_) {
    capture_source_gap_v4(work, "revocation-window-unproven", {
      "observation": capture_source_event_ref_v4(event),
      "sourceEffect": capture_source_effect_ref_v4(work, source),
    })
  } else if outcome != "committed" {
    capture_source_gap_v4(work, "unknown-source-outcome", {
      "observation": capture_source_event_ref_v4(event),
      "sourceEffect": capture_source_effect_ref_v4(work, source),
    })
  } else if intermediate && !writing {
    let source_closed = match work.window {
      Some(w) => w.closed.get_or_default(source.tx, false)
      _ => false
    }
    if !source_closed {
      capture_source_gap_v4(work, "final-effect-window-unproven", {
        "observation": capture_source_event_ref_v4(event),
        "sourceEffect": capture_source_effect_ref_v4(work, source),
      })
      return
    }
    match work.finals.get_or_default(source.tx, Map([])).get(source.key) {
      Some(final_effect) if final_effect.seq != source.seq =>
        capture_source_proof_v4(
          work,
          "G1b",
          "external-committed-nonfinal-effective-write",
          event,
          source,
          Some(final_effect),
        )
      None =>
        capture_source_gap_v4(work, "unconfirmed-final-source", {
          "sourceEffect": capture_source_effect_ref_v4(work, source),
        })
      _ => ()
    }
  }
}

///|
fn capture_source_index_v4(
  work : CaptureSourceAnomalyWorkV4,
  normalized : Json,
  model : DataModelV4,
) -> Unit {
  let n = object_fields_unchecked_v3(normalized)
  for raw_tx in capture_source_array_v4(n.at("transactions")) {
    if !capture_source_charge_v4(work) {
      return
    }
    let tx = object_fields_unchecked_v3(raw_tx)
    let id = capture_source_string_v4(tx.at("id"))
    work.outcomes[id] = capture_source_string_v4(tx.at("status"))
    work.transactions[id] = {
      "id": Json(id),
      "status": tx.at("status"),
      "beginSeq": tx.at("beginSeq"),
      "endSeq": tx.at("endSeq"),
    }
  }
  for event in capture_source_array_v4(n.at("observations")) {
    if !capture_source_charge_v4(work) {
      return
    }
    let e = object_fields_unchecked_v3(event)
    let seq = capture_source_seq_v4(e.at("seq"))
    if e.at("kind") != Json("snapshot") {
      continue
    }
    let initial = object_fields_unchecked_v3(e.at("initial"))
    for key, value in initial {
      let identities : Array[String] = []
      let sources = work.sources.get_or_default(key, Map([]))
      if model == RegisterV4 {
        if !capture_source_charge_v4(work) {
          return
        }
        let identity = capture_source_string_v4(value)
        identities.push(identity)
        sources[identity] = {
          seq,
          tx: "",
          key,
          identity,
          value: Json::null(),
          revoked: None,
        }
      } else {
        for raw in capture_source_array_v4(value) {
          if !capture_source_charge_v4(work) {
            return
          }
          let item = object_fields_unchecked_v3(raw)
          let identity = capture_source_string_v4(item.at("id"))
          identities.push(identity)
          sources[identity] = {
            seq,
            tx: "",
            key,
            identity,
            value: item.at("value"),
            revoked: None,
          }
        }
      }
      work.initial[key] = identities
      work.sources[key] = sources
    }
  }
  for raw_effect in capture_source_array_v4(n.at("effects")) {
    if !capture_source_charge_v4(work) {
      return
    }
    let e = object_fields_unchecked_v3(raw_effect)
    let seq = capture_source_seq_v4(e.at("seq"))
    let key = capture_source_string_v4(e.at("key"))
    let tx = capture_source_string_v4(e.at("tx"))
    let effect : CaptureSourceAnomalyEffectV4 = {
      seq,
      tx,
      key,
      identity: capture_source_string_v4(
        e.at(if model == RegisterV4 { "version" } else { "id" }),
      ),
      value: e.get_or_default("value", Json::null()),
      revoked: match e.at("revertedBy") {
        Null => None
        value => Some(capture_source_seq_v4(value))
      },
    }
    let sources = work.sources.get_or_default(key, Map([]))
    sources[effect.identity] = effect
    work.sources[key] = sources
    if effect.revoked is None &&
      (match work.window {
        Some(w) => w.closed.get_or_default(tx, false)
        _ => false
      }) {
      let finals = work.finals.get_or_default(tx, Map([]))
      finals[key] = effect
      work.finals[tx] = finals
      if model == AppendListV4 {
        let positions = work.positions.get_or_default(key, Map([]))
        // Nested tx->key counts avoid joining legal identities with delimiters.
        let count = work.append_counts.get_or_default(tx, Map([]))
        let rank = count.get_or_default(key, 0)
        count[key] = rank + 1
        work.append_counts[tx] = count
        positions[effect.identity] = rank
        work.positions[key] = positions
      }
    }
  }
}

///|
fn capture_source_register_v4(
  work : CaptureSourceAnomalyWorkV4,
  event : Json,
) -> Unit {
  let e = object_fields_unchecked_v3(event)
  let writing = e.at("kind") == Json("write")
  let key = capture_source_string_v4(e.at("key"))
  if writing {
    let observer = capture_source_string_v4(e.at("tx"))
    if !(match work.window {
        Some(w) => w.closed.get_or_default(observer, false)
        _ => false
      }) {
      capture_source_gap_v4(
        work,
        "write-effect-survival-window-unproven",
        capture_source_event_ref_v4(event),
      )
      return
    }
    let id = capture_source_string_v4(e.at("version"))
    let effect = work.sources.get_or_default(key, Map([])).at(id)
    if effect.revoked is Some(_) {
      return
    }
  }
  let identity = capture_source_string_v4(
    e.at(if writing { "predecessor" } else { "version" }),
  )
  match capture_source_lookup_v4(work, key, identity, event) {
    None => ()
    Some(source) =>
      capture_source_classify_ref_v4(work, event, source, writing, true)
  }
}

///|
fn capture_source_list_v4(
  work : CaptureSourceAnomalyWorkV4,
  event : Json,
) -> Unit {
  let e = object_fields_unchecked_v3(event)
  let key = capture_source_string_v4(e.at("key"))
  let reader = capture_source_string_v4(e.at("tx"))
  let items = capture_source_array_v4(e.at("items"))
  let initial = work.initial.get_or_default(key, [])
  let seen : Map[String, Bool] = Map([])
  let counts : Map[String, Int32] = Map([])
  let mut valid = work.initial.contains(key) &&
    items.length() >= initial.length()
  let mut last : CaptureSourceAnomalyEffectV4? = None
  for position, raw in items {
    if !capture_source_charge_v4(work) {
      return
    }
    let item = object_fields_unchecked_v3(raw)
    let identity = capture_source_string_v4(item.at("id"))
    if seen.contains(identity) {
      valid = false
    }
    seen[identity] = true
    if position < initial.length() && initial[position] != identity {
      valid = false
    }
    match capture_source_lookup_v4(work, key, identity, event) {
      None => {
        valid = false
        last = None
      }
      Some(source) => {
        if source.value != item.at("value") {
          capture_source_gap_v4(work, "item-identity-value-conflict", {
            "observation": capture_source_event_ref_v4(event),
            "itemPosition": Json(position),
            "sourceEffect": capture_source_effect_ref_v4(work, source),
          })
          valid = false
          last = None
          continue
        }
        // Each matching element can prove G1a independently of whole-list shape.
        capture_source_classify_ref_v4(work, event, source, false, false)
        if source.tx != "" {
          let expected = counts.get_or_default(source.tx, 0)
          if source.tx == reader ||
            source.revoked is Some(_) ||
            work.outcomes.get(source.tx) != Some("committed") ||
            work.positions.get_or_default(key, Map([])).get(identity) !=
            Some(expected) {
            valid = false
          }
          counts[source.tx] = expected + 1
        }
        last = Some(source)
      }
    }
  }
  if !valid {
    capture_source_gap_v4(work, "list-complete-version-unproven", {
      "observation": capture_source_event_ref_v4(event),
      "scope": "G1b needs an initial-prefix and complete producer-prefix valid list; matching aborted elements remain independent G1a evidence",
    })
  } else {
    match last {
      Some(source) =>
        capture_source_classify_ref_v4(work, event, source, false, true)
      None => ()
    }
  }
}

///|
/// Inspect raw register/list source effects; no schema1 version-order inference.
pub fn inspect_capture_anomalies_v4(
  history : HistoryV4,
  max_checks~ : Int32 = 1000000,
) -> CaptureAnomaliesV4 {
  let work : CaptureSourceAnomalyWorkV4 = {
    maximum: max_checks,
    checks: 0,
    limited: false,
    truncated: false,
    findings: [],
    gaps: [],
    outcomes: Map([]),
    transactions: Map([]),
    sources: Map([]),
    finals: Map([]),
    positions: Map([]),
    append_counts: Map([]),
    initial: Map([]),
    window: None,
  }
  let normalized = match history.payload {
    RegisterSnapshot(_, Some(n)) => Some(n)
    ListSnapshot(parsed) => Some(parsed.normalized)
    _ => None
  }
  let supported = history.source_format == "capture/v3" && normalized is Some(_)
  let valid_budget = max_checks >= 0 && max_checks <= 1000000
  let mut input_complete = false
  if supported && valid_budget {
    let n = normalized.unwrap()
    let coverage = object_fields_unchecked_v3(
      object_fields_unchecked_v3(n).at("coverage"),
    )
    input_complete = coverage.get("complete") == Some(Json(true))
    for gap in capture_source_array_v4(coverage.at("gaps")) {
      if !capture_source_charge_v4(work) {
        break
      }
      capture_source_gap_v4(work, "normalization-coverage-gap", gap)
    }
    if !work.limited {
      work.window = Some(
        capture_window_v5(history, n, fn() { capture_source_charge_v4(work) }),
      )
    }
    if !work.limited {
      capture_source_index_v4(work, n, history.data_model)
    }
    if !work.limited {
      for
        event in capture_source_array_v4(
          object_fields_unchecked_v3(n).at("observations"),
        ) {
        if !capture_source_charge_v4(work) {
          break
        }
        let e = object_fields_unchecked_v3(event)
        let kind = capture_source_string_v4(e.at("kind"))
        if !(kind == "read" || kind == "list_read" || kind == "write") {
          continue
        }
        let tx = capture_source_string_v4(e.at("tx"))
        let outcome = work.outcomes.get_or_default(tx, "unknown")
        if outcome == "aborted" {
          continue
        }
        if outcome != "committed" {
          capture_source_gap_v4(
            work,
            "unknown-observer-outcome",
            capture_source_event_ref_v4(event),
          )
          continue
        }
        if kind == "list_read" {
          capture_source_list_v4(work, event)
        } else {
          capture_source_register_v4(work, event)
        }
        if work.limited {
          break
        }
      }
    }
  }
  let complete = supported &&
    valid_budget &&
    input_complete &&
    !work.limited &&
    !work.truncated &&
    work.gaps.is_empty()
  let rules = ["G1a", "G1b", "dirty-update", "INT"].map(category => {
    let refuted = work.findings.any(finding => {
      object_fields_unchecked_v3(finding).at("category") == Json(category)
    })
    let applicable = category != "INT" &&
      (category != "dirty-update" || history.data_model == RegisterV4)
    (
      {
        "category": Json(category),
        "status": Json(
          if !supported || !applicable {
            "unsupported"
          } else if refuted {
            "refuted"
          } else if complete {
            "checked"
          } else {
            "unknown"
          },
        ),
      } : Json)
  })
  {
    record: {
      "format": "moontxnwitness-captured-source-anomalies/v4",
      "schemaVersion": 4,
      "semanticContract": "moontxnwitness-captured-source-anomalies-v4-2",
      "algorithm": "v4-capture-effective-source-anomalies-2",
      "profile": "raw-capture-source-anomalies/v2",
      "dataModel": Json(v4_model_name(history.data_model)),
      "status": Json(
        if !valid_budget {
          "invalid-budget"
        } else if !supported {
          "unsupported"
        } else if !work.findings.is_empty() {
          "refuted"
        } else if complete {
          "checked"
        } else {
          "unknown"
        },
      ),
      "scope": {
        "diagnosticOnly": true,
        "acceptsIsolationModels": false,
        "authenticityVerified": false,
        "sourceKind": "raw-normalized-observations-and-effects",
        "declaredVersionOrdersAcceptedAsWriteBase": false,
        "INT": "unsupported",
        "listDirtyUpdate": "unsupported",
        "listG1bOwnOverlay": "unsupported",
      },
      "observations": { "document": history.source_document },
      "findings": Json(work.findings),
      "coverage": {
        "complete": Json(complete),
        "scope": "supported-direct-source-rules-only; not isolation-model completeness",
        "gaps": Json(work.gaps),
        "findingsTruncated": Json(work.truncated),
      },
      "checks": Json(rules),
      "execution": {
        "counterContract": "v4-capture-source-reference-checks-2",
        "checks": Json(work.checks),
        "limited": Json(work.limited),
        "limits": { "maxChecks": Json(max_checks), "findingsAndGaps": 256 },
      },
    },
  }
}

///|
/// Return a detached record; a completed diagnostic never accepts a full model.
pub fn capture_anomalies_v4_json(result : CaptureAnomaliesV4) -> Json {
  v4_json_copy(result.record)
}
