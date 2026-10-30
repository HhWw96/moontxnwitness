///|
priv struct InternalEffectV4 {
  seq : Int64
  tx : String
  key : String
  identity : String
  value : Json
  revoked : Int64?
}

///|
priv struct InternalBaseV4 {
  identities : Array[String]
  observation : Json
  observed_at : Int64
}

///|
priv struct InternalTransactionV4 {
  base : Map[String, InternalBaseV4]
  own : Map[String, Array[InternalEffectV4]]
  failed : Map[String, Bool]
}

///|
priv struct InternalWorkV4 {
  maximum : Int32
  mut checks : Int32
  mut limited : Bool
  mut truncated : Bool
  findings : Array[Json]
  gaps : Array[Json]
  outcomes : Map[String, String]
  events : Map[Int64, Json]
  sources : Map[String, Map[String, InternalEffectV4]]
  revocations : Map[Int64, Array[InternalEffectV4]]
  initial : Map[String, Array[String]]
  states : Map[String, InternalTransactionV4]
  blocked : Map[String, Bool]
  uncertain_after : Map[String, Int64]
}

///|
/// A formal INT check over supplied capture facts; no database product label.
pub struct InternalConsistencyV4 {
  priv record : Json
}

///|
fn internal_charge_v4(work : InternalWorkV4) -> Bool {
  if work.checks >= work.maximum {
    work.limited = true
    false
  } else {
    work.checks += 1
    true
  }
}

///|
fn internal_seq_v4(value : Json) -> Int64 {
  match value {
    Number(n, ..) => n.to_int64()
    _ => abort("Validated internal-consistency capture sequence")
  }
}

///|
fn internal_string_v4(value : Json) -> String {
  match value {
    String(text) => text
    _ => abort("Validated internal-consistency identity")
  }
}

///|
fn internal_array_v4(value : Json) -> Array[Json] {
  match value {
    Array(items) => items
    _ => []
  }
}

///|
fn internal_emit_v4(
  work : InternalWorkV4,
  proved : Bool,
  record : Json,
) -> Unit {
  if work.findings.length() + work.gaps.length() >= 256 {
    work.truncated = true
    if proved && !work.gaps.is_empty() {
      ignore(work.gaps.pop())
      work.findings.push(record)
    }
  } else if proved {
    work.findings.push(record)
  } else {
    work.gaps.push(record)
  }
}

///|
fn internal_gap_v4(
  work : InternalWorkV4,
  code : String,
  evidence : Json,
) -> Unit {
  internal_emit_v4(work, false, { "code": Json(code), "evidence": evidence })
}

///|
fn internal_ref_v4(event : Json) -> Json {
  let e = object_fields_unchecked_v3(event)
  {
    "eventSeq": e.at("seq"),
    "transaction": e.get_or_default("tx", Json::null()),
    "kind": e.at("kind"),
    "key": e.get_or_default("key", Json::null()),
  }
}

///|
fn internal_state_v4(
  work : InternalWorkV4,
  tx : String,
) -> InternalTransactionV4 {
  match work.states.get(tx) {
    Some(state) => state
    None => {
      let state : InternalTransactionV4 = {
        base: Map([]),
        own: Map([]),
        failed: Map([]),
      }
      work.states[tx] = state
      state
    }
  }
}

///|
fn internal_effect_ref_v4(
  work : InternalWorkV4,
  effect : InternalEffectV4,
) -> Json {
  {
    "eventSeq": Json(effect.seq.to_double()),
    "transaction": Json(effect.tx),
    "key": Json(effect.key),
    "identity": Json(effect.identity),
    "observation": internal_ref_v4(work.events.at(effect.seq)),
    "revertedBy": match effect.revoked {
      Some(seq) => Json(seq.to_double())
      None => Json::null()
    },
  }
}

///|
fn internal_proof_v4(
  work : InternalWorkV4,
  state : InternalTransactionV4,
  key : String,
  actual : Json,
  expected : Json,
) -> Unit {
  if state.failed.contains(key) {
    return
  }
  state.failed[key] = true
  internal_emit_v4(work, true, {
    "category": "INT",
    "definition": "elle-int-effective-overlay-v1",
    "evidence": {
      "expected": expected,
      "actualObservation": internal_ref_v4(actual),
      "observationPointer": "observations.document.events[eventSeq-1]",
      "rule": "nearest-delivered-read-or-current-effective-own-write; rollback-revokes-writes-only",
      "databaseProductIsolationLevelAsserted": false,
    },
  })
}

///|
fn internal_index_v4(
  work : InternalWorkV4,
  history : HistoryV4,
  normalized : Json,
) -> Unit {
  let n = object_fields_unchecked_v3(normalized)
  let original = object_fields_unchecked_v3(history.source_document)
  let window_missing = !internal_array_v4(
    original.get_or_default("gaps", Json(([] : Array[Json]))),
  ).is_empty()
  let gaps = internal_array_v4(
    object_fields_unchecked_v3(n.at("coverage")).at("gaps"),
  )
  for gap in gaps {
    if !internal_charge_v4(work) {
      return
    }
    internal_gap_v4(work, "normalization-coverage-gap", gap)
  }
  let proof = object_fields_unchecked_v3(
    n.get_or_default("sqlProof", Json::null()),
  )
  let verified_statements : Map[Int64, Bool] = Map([])
  let verified_facts : Map[Int64, Bool] = Map([])
  for
    seq in internal_array_v4(
      proof.get_or_default("verifiedStatements", Json::null()),
    ) {
    if !internal_charge_v4(work) {
      return
    }
    verified_statements[internal_seq_v4(seq)] = true
  }
  for
    seq in internal_array_v4(
      proof.get_or_default("verifiedFacts", Json::null()),
    ) {
    if !internal_charge_v4(work) {
      return
    }
    verified_facts[internal_seq_v4(seq)] = true
  }
  for raw_tx in internal_array_v4(n.at("transactions")) {
    if !internal_charge_v4(work) {
      return
    }
    let tx = object_fields_unchecked_v3(raw_tx)
    let id = internal_string_v4(tx.at("id"))
    work.outcomes[id] = internal_string_v4(tx.at("status"))
    if window_missing {
      work.blocked[id] = true
    }
  }
  for event in internal_array_v4(n.at("observations")) {
    if !internal_charge_v4(work) {
      return
    }
    let e = object_fields_unchecked_v3(event)
    let seq = internal_seq_v4(e.at("seq"))
    work.events[seq] = event
    let kind = internal_string_v4(e.at("kind"))
    let unknown_program = (
        kind == "statement" && !verified_statements.contains(seq)
      ) ||
      (kind == "condition" && !verified_facts.contains(seq)) ||
      (kind == "rows" && e.get("complete") == Some(Json(false)))
    if unknown_program {
      let tx = internal_string_v4(e.at("tx"))
      match work.uncertain_after.get(tx) {
        Some(previous) if previous <= seq => ()
        _ => work.uncertain_after[tx] = seq
      }
    }
    if kind != "snapshot" {
      continue
    }
    for key, value in object_fields_unchecked_v3(e.at("initial")) {
      let ids : Array[String] = []
      let sources = work.sources.get_or_default(key, Map([]))
      if history.data_model == RegisterV4 {
        if !internal_charge_v4(work) {
          return
        }
        let identity = internal_string_v4(value)
        ids.push(identity)
        sources[identity] = {
          seq,
          tx: "",
          key,
          identity,
          value: Json::null(),
          revoked: None,
        }
      } else {
        for item in internal_array_v4(value) {
          if !internal_charge_v4(work) {
            return
          }
          let i = object_fields_unchecked_v3(item)
          let identity = internal_string_v4(i.at("id"))
          ids.push(identity)
          sources[identity] = {
            seq,
            tx: "",
            key,
            identity,
            value: i.at("value"),
            revoked: None,
          }
        }
      }
      work.sources[key] = sources
      work.initial[key] = ids
    }
  }
  for effect in internal_array_v4(n.at("effects")) {
    if !internal_charge_v4(work) {
      return
    }
    let e = object_fields_unchecked_v3(effect)
    let source : InternalEffectV4 = {
      seq: internal_seq_v4(e.at("seq")),
      tx: internal_string_v4(e.at("tx")),
      key: internal_string_v4(e.at("key")),
      identity: internal_string_v4(
        e.at(if history.data_model == RegisterV4 { "version" } else { "id" }),
      ),
      value: e.get_or_default("value", Json::null()),
      revoked: match e.at("revertedBy") {
        Null => None
        seq => Some(internal_seq_v4(seq))
      },
    }
    let sources = work.sources.get_or_default(source.key, Map([]))
    sources[source.identity] = source
    work.sources[source.key] = sources
    match source.revoked {
      None => ()
      Some(at) => {
        let undone = work.revocations.get_or_default(at, [])
        undone.push(source)
        work.revocations[at] = undone
      }
    }
  }
}

///|
fn internal_revoke_v4(work : InternalWorkV4, seq : Int64) -> Unit {
  let undone = work.revocations.get_or_default(seq, [])
  for index = undone.length() - 1; index >= 0; index = index - 1 {
    if !internal_charge_v4(work) {
      return
    }
    let effect = undone[index]
    let state = internal_state_v4(work, effect.tx)
    let own = state.own.get_or_default(effect.key, [])
    if !own.is_empty() && own[own.length() - 1].seq == effect.seq {
      ignore(own.pop())
      state.own[effect.key] = own
    } else {
      work.blocked[effect.tx] = true
      internal_gap_v4(work, "overlay-revocation-unproven", {
        "sourceEffect": internal_effect_ref_v4(work, effect),
        "revertedBy": Json(seq.to_double()),
      })
    }
  }
}

///|
fn internal_observed_source_v4(
  work : InternalWorkV4,
  key : String,
  identity : String,
  event : Json,
  value : Json?,
) -> InternalEffectV4? {
  match work.sources.get_or_default(key, Map([])).get(identity) {
    None => {
      internal_gap_v4(work, "missing-source", {
        "observation": internal_ref_v4(event),
        "identity": Json(identity),
      })
      None
    }
    Some(source) => {
      let seq = internal_seq_v4(object_fields_unchecked_v3(event).at("seq"))
      if source.seq >= seq {
        internal_gap_v4(work, "source-not-observed-before-read", {
          "observation": internal_ref_v4(event),
          "sourceSeq": Json(source.seq.to_double()),
          "identity": Json(identity),
        })
        return None
      }
      match value {
        Some(actual) if actual != source.value => {
          internal_gap_v4(work, "identity-value-conflict", {
            "observation": internal_ref_v4(event),
            "identity": Json(identity),
          })
          return None
        }
        _ => ()
      }
      if source.tx != "" &&
        work.outcomes.get_or_default(source.tx, "unknown") == "unknown" {
        internal_gap_v4(work, "unknown-source-outcome", {
          "observation": internal_ref_v4(event),
          "sourceTransaction": Json(source.tx),
          "identity": Json(identity),
        })
      }
      Some(source)
    }
  }
}

///|
fn internal_register_read_v4(work : InternalWorkV4, event : Json) -> Unit {
  let e = object_fields_unchecked_v3(event)
  let tx = internal_string_v4(e.at("tx"))
  let key = internal_string_v4(e.at("key"))
  let id = internal_string_v4(e.at("version"))
  let source = match internal_observed_source_v4(work, key, id, event, None) {
    None => return
    Some(source) => source
  }
  let state = internal_state_v4(work, tx)
  let own = state.own.get_or_default(key, [])
  let latest = if own.is_empty() { None } else { Some(own[own.length() - 1]) }
  let base = state.base.get(key)
  let expected = match (latest, base) {
    (Some(effect), Some(previous)) if previous.observed_at > effect.seq =>
      Some((previous.identities[0], previous.observation, "external-read"))
    (Some(effect), _) =>
      Some(
        (
          effect.identity,
          internal_ref_v4(work.events.at(effect.seq)),
          "effective-own-write",
        ),
      )
    (None, Some(previous)) =>
      Some((previous.identities[0], previous.observation, "external-read"))
    _ => None
  }
  match expected {
    Some((identity, observation, basis)) if identity != id =>
      internal_proof_v4(work, state, key, event, {
        "kind": "register-version",
        "basis": Json(basis),
        "identity": Json(identity),
        "actualIdentity": Json(id),
        "observation": observation,
      })
    _ => ()
  }
  if source.tx != tx {
    state.base[key] = {
      identities: [id],
      observation: internal_ref_v4(event),
      observed_at: internal_seq_v4(e.at("seq")),
    }
  } else if !own.any(effect => effect.identity == id) {
    internal_gap_v4(work, "noncurrent-own-source", {
      "observation": internal_ref_v4(event),
      "identity": Json(id),
    })
  }
}

///|
fn internal_list_read_v4(work : InternalWorkV4, event : Json) -> Unit {
  let e = object_fields_unchecked_v3(event)
  let tx = internal_string_v4(e.at("tx"))
  let key = internal_string_v4(e.at("key"))
  let state = internal_state_v4(work, tx)
  let own = state.own.get_or_default(key, [])
  let initial = work.initial.get_or_default(key, [])
  let actual : Array[String] = []
  let seen : Map[String, Bool] = Map([])
  let mut usable = true
  let mut prefix_valid = work.initial.contains(key)
  let mut has_own_prefix = false
  let items = internal_array_v4(e.at("items"))
  for position, item in items {
    if !internal_charge_v4(work) {
      return
    }
    let i = object_fields_unchecked_v3(item)
    let id = internal_string_v4(i.at("id"))
    actual.push(id)
    if seen.contains(id) {
      usable = false
      internal_gap_v4(work, "duplicate-observed-identity", {
        "observation": internal_ref_v4(event),
        "identity": Json(id),
      })
    }
    seen[id] = true
    if position < initial.length() && initial[position] != id {
      prefix_valid = false
    }
    match
      internal_observed_source_v4(work, key, id, event, Some(i.at("value"))) {
      None => usable = false
      Some(source) =>
        if source.tx == tx && position < items.length() - own.length() {
          has_own_prefix = true
        }
    }
  }
  if actual.length() < initial.length() {
    prefix_valid = false
  }
  if !prefix_valid {
    internal_gap_v4(work, "initial-list-prefix-unproven", {
      "observation": internal_ref_v4(event),
    })
  }
  if !usable {
    return
  }
  let base = state.base.get(key)
  let base_length = match base {
    Some(b) => b.identities.length()
    None => 0
  }
  let full = base is Some(_)
  let minimum = base_length + own.length()
  let start = if full { 0 } else { actual.length() - own.length() }
  let mut mismatch = -1
  let mut expected_id : String? = None
  let mut actual_id : String? = None
  if (full && actual.length() != minimum) || (!full && start < 0) {
    mismatch = if actual.length() < minimum { actual.length() } else { minimum }
    if mismatch < actual.length() {
      actual_id = Some(actual[mismatch])
    }
    if mismatch < minimum {
      expected_id = Some(
        if mismatch < base_length {
          base.unwrap().identities[mismatch]
        } else {
          own[mismatch - base_length].identity
        },
      )
    }
  } else {
    for position in 0..<minimum {
      if !internal_charge_v4(work) {
        return
      }
      let identity = if position < base_length {
        base.unwrap().identities[position]
      } else {
        own[position - base_length].identity
      }
      let observed = actual[start + position]
      if identity != observed {
        mismatch = start + position
        expected_id = Some(identity)
        actual_id = Some(observed)
        break
      }
    }
  }
  if mismatch >= 0 {
    internal_proof_v4(work, state, key, event, {
      "kind": "list-state",
      "mode": Json(
        if full {
          "complete-base-plus-effective-own"
        } else {
          "effective-own-suffix"
        },
      ),
      "baseObservation": match base {
        Some(b) => b.observation
        None => Json::null()
      },
      "basePrefixLength": Json(base_length),
      "ownAppendCount": Json(own.length()),
      "ownLastWrite": if own.is_empty() {
        Json::null()
      } else {
        internal_effect_ref_v4(work, own[own.length() - 1])
      },
      "expectedLength": if full {
        Json(minimum)
      } else {
        Json::null()
      },
      "minimumLength": Json(minimum),
      "actualLength": Json(actual.length()),
      "firstMismatchPosition": Json(mismatch),
      "expectedIdentity": match expected_id {
        Some(id) => Json(id)
        None => Json::null()
      },
      "actualIdentity": match actual_id {
        Some(id) => Json(id)
        None => Json::null()
      },
    })
  }
  // A whole own-at-delivery value is never retained as the external base.
  let prefix_length = actual.length() - own.length()
  let mut suffix_matches = prefix_length >= 0
  if suffix_matches {
    for position, effect in own {
      if !internal_charge_v4(work) {
        return
      }
      if actual[prefix_length + position] != effect.identity {
        suffix_matches = false
        break
      }
    }
  }
  if suffix_matches && prefix_valid && !has_own_prefix {
    let prefix : Array[String] = []
    for position in 0..<prefix_length {
      if !internal_charge_v4(work) {
        return
      }
      prefix.push(actual[position])
    }
    state.base[key] = {
      identities: prefix,
      observation: internal_ref_v4(event),
      observed_at: internal_seq_v4(e.at("seq")),
    }
  } else {
    internal_gap_v4(work, "external-list-base-unproven", {
      "observation": internal_ref_v4(event),
      "ownSuffixLength": Json(own.length()),
    })
  }
}

///|
/// Fixed formal INT with an explicit effective-write extension for savepoints.
pub fn inspect_internal_consistency_v4(
  history : HistoryV4,
  max_checks~ : Int32 = 1000000,
) -> InternalConsistencyV4 {
  let work : InternalWorkV4 = {
    maximum: max_checks,
    checks: 0,
    limited: false,
    truncated: false,
    findings: [],
    gaps: [],
    outcomes: Map([]),
    events: Map([]),
    sources: Map([]),
    revocations: Map([]),
    initial: Map([]),
    states: Map([]),
    blocked: Map([]),
    uncertain_after: Map([]),
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
    input_complete = object_fields_unchecked_v3(
        object_fields_unchecked_v3(n).at("coverage"),
      ).get("complete") ==
      Some(Json(true))
    internal_index_v4(work, history, n)
    if !work.limited {
      for
        event in internal_array_v4(
          object_fields_unchecked_v3(n).at("observations"),
        ) {
        if !internal_charge_v4(work) {
          break
        }
        let e = object_fields_unchecked_v3(event)
        let seq = internal_seq_v4(e.at("seq"))
        internal_revoke_v4(work, seq)
        if work.limited {
          break
        }
        let kind = internal_string_v4(e.at("kind"))
        if kind == "write" || kind == "append" {
          let tx = internal_string_v4(e.at("tx"))
          let key = internal_string_v4(e.at("key"))
          let id = internal_string_v4(
            e.at(if kind == "write" { "version" } else { "id" }),
          )
          let effect = work.sources.get_or_default(key, Map([])).at(id)
          let state = internal_state_v4(work, tx)
          let own = state.own.get_or_default(key, [])
          own.push(effect)
          state.own[key] = own
        } else if kind == "read" || kind == "list_read" {
          let tx = internal_string_v4(e.at("tx"))
          let status = work.outcomes.get_or_default(tx, "unknown")
          if status == "aborted" {
            continue
          }
          if status != "committed" {
            internal_gap_v4(
              work,
              "unknown-observer-outcome",
              internal_ref_v4(event),
            )
            continue
          }
          let unknown_prefix = match work.uncertain_after.get(tx) {
            Some(at) => at <= seq
            None => false
          }
          if work.blocked.contains(tx) || unknown_prefix {
            internal_gap_v4(
              work,
              "transaction-program-coverage-unproven",
              internal_ref_v4(event),
            )
            continue
          }
          if kind == "read" {
            internal_register_read_v4(work, event)
          } else {
            internal_list_read_v4(work, event)
          }
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
  {
    record: {
      "format": "moontxnwitness-internal-consistency/v4",
      "schemaVersion": 4,
      "semanticContract": "moontxnwitness-internal-consistency-v4-1",
      "algorithm": "v4-effective-overlay-internal-consistency-1",
      "profile": "captured-formal-int/v1",
      "definition": {
        "id": "elle-int-effective-overlay-v1",
        "referenceCommit": "4e359e597c52938b0afebb8bc42273914d68a424",
        "register": "nearest actual external read or currently effective own write",
        "list": "effective own suffix before a full read; then observed external prefix plus active own appends",
        "savepoints": "undo writes only; delivered external base observations persist",
      },
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
        "databaseProductIsolationLevelAsserted": false,
        "authenticityVerified": false,
        "firstWitnessPerTransactionAndKey": true,
        "declaredHistorySupport": "unsupported",
        "programGapPolicy": "Unlocated journal loss blocks proof; unproved SQL blocks from its event onward and cannot erase earlier evidence",
      },
      "observations": { "document": history.source_document },
      "findings": Json(work.findings),
      "coverage": {
        "complete": Json(complete),
        "scope": "formal-INT-only",
        "gaps": Json(work.gaps),
        "findingsTruncated": Json(work.truncated),
      },
      "execution": {
        "counterContract": "v4-internal-overlay-reference-checks-1",
        "checks": Json(work.checks),
        "limited": Json(work.limited),
        "limits": { "maxChecks": Json(max_checks), "findingsAndGaps": 256 },
      },
    },
  }
}

///|
pub fn internal_consistency_v4_json(result : InternalConsistencyV4) -> Json {
  v4_json_copy(result.record)
}

///|
/// Verification uses the caller's independent budget, never a report's budget.
pub fn verify_internal_consistency_v4(
  history : HistoryV4,
  supplied : Json,
  max_checks~ : Int32 = 1000000,
) -> Bool {
  supplied == inspect_internal_consistency_v4(history, max_checks~).record
}
