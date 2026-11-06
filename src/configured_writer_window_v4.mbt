///|
priv struct ConfiguredPointSourceV4 {
  commits : Map[String, Json]
  mut installation : SourceInstallationCheckV4?
  mut effects : Map[String, Json]?
}

///|
fn configured_writer_window_v4(
  before_input : String,
  after_input : String,
  session_input : String,
  options : String,
  point_source? : ConfiguredPointSourceV4,
) -> Json raise {
  let limits = source_object_v4(sql_json_v1(options, 8192))
  known_fields(
    limits,
    ["maxRows", "maxChecks", "maxInstallationChecks", "maxBindingChecks"],
    "writer-window-options",
  )
  let work : SourceWorkV4 = {
    limit: source_wire_limit_v4(limits, "maxBindingChecks", 1000000),
    checks: 0,
  }
  limits.remove("maxBindingChecks")
  let before = configured_effects_envelope_v4(
    sql_json_v1(before_input, 25165824),
  )
  let after = configured_effects_envelope_v4(sql_json_v1(after_input, 25165824))
  for
    key in [
      "configText", "policyText", "installationLogText", "installationReceiptText",
    ] {
    if before.at(key) != after.at(key) {
      fail("mismatch:writer-window-installation")
    }
  }
  let context = configured_effects_context_v4(before, Json(limits))
  let before_rows : Map[String, Json] = Map([])
  let after_rows : Map[String, Json] = Map([])
  let (before_raw, before_digest) = configured_effects_observation_v4(
    before,
    context,
    retained_rows=before_rows,
  )
  let (after_raw, after_digest) = configured_effects_observation_v4(
    after,
    context,
    retained_rows=after_rows,
  )
  let before_observation = source_object_v4(before_raw)
  let after_observation = source_object_v4(after_raw)
  let peer = match before_observation.get("peer") {
    Some(value) if after_observation.get("peer") == Some(value) => value
    _ => fail("mismatch:writer-window-peer")
  }
  let start_snapshot = sql_string_v1(before_observation.at("snapshot"))
  let end_snapshot = sql_string_v1(after_observation.at("snapshot"))
  let (start_lower, start_upper, start_active) = effects_snapshot_bounds_v4(
    start_snapshot, work,
  )
  let (end_lower, end_upper, end_active) = effects_snapshot_bounds_v4(
    end_snapshot, work,
  )
  if source_version_after_v4(start_lower, end_lower) ||
    source_version_after_v4(start_upper, end_upper) {
    fail("mismatch:writer-window-snapshot-regression")
  }
  for xid, _ in end_active {
    work.charge()
    if effects_xid_completed_v4(xid, start_upper, start_active) {
      fail("mismatch:writer-window-completed-XID-active-again")
    }
  }
  for version, row in before_rows {
    work.charge()
    match after_rows.get(version) {
      None => fail("mismatch:writer-window-missing-prior-effect")
      Some(end_row) if end_row != row =>
        fail("mismatch:writer-window-changed-prior-effect")
      _ => ()
    }
  }
  let commits = match point_source {
    Some(source) => {
      source.installation = Some(context.installation)
      source.effects = Some(after_rows)
      configured_writer_session_commits_v4(
        after,
        session_input,
        peer,
        work,
        by_tx=source.commits,
      )
    }
    None =>
      configured_writer_session_commits_v4(after, session_input, peer, work)
  }
  let matched : Array[Json] = []
  let unmatched : Array[Json] = []
  for raw in orm_array(after_observation.at("observations")) {
    work.charge()
    let effect = source_object_v4(raw)
    let version = sql_string_v1(effect.at("version"))
    if before_rows.contains(version) {
      continue
    }
    let xid = sql_string_v1(effect.at("writerXid"))
    if effects_xid_completed_v4(xid, start_upper, start_active) {
      fail("mismatch:writer-window-prior-XID-with-new-effect")
    }
    match configured_writer_binding_v4(effect, commits) {
      Some(binding) => matched.push({ "effect": raw, "clientCommit": binding })
      None => unmatched.push(raw)
    }
  }
  {
    "format": "moontxnwitness-configured-writer-window/v4",
    "valid": true,
    "status": if unmatched.is_empty() {
      Json("complete-ledger-delta")
    } else {
      Json("incomplete-ledger-delta")
    },
    "ledgerDeltaCovered": Json(unmatched.is_empty()),
    "scope": "committed row effects present in the configured sidecar between the two observed snapshots",
    "startSnapshot": Json(start_snapshot),
    "endSnapshot": Json(end_snapshot),
    "startEffectsLogSha256": Json(before_digest),
    "endEffectsLogSha256": Json(after_digest),
    "installationLogSha256": Json(context.installation.log_digest),
    "sessionInputSha256": Json(v3_dislock_sha256(session_input)),
    "retainedEffects": Json(before_rows.length()),
    "deltaEffects": Json(matched.length() + unmatched.length()),
    "matchedEffects": Json(matched),
    "unmatchedEffects": Json(unmatched),
    "snapshotChecks": Json(context.work.checks),
    "maxSnapshotChecks": Json(context.work.limit),
    "bindingChecks": Json(work.checks),
    "maxBindingChecks": Json(work.limit),
    "sourceFactsProduced": false,
    "sourceAuthenticated": false,
    "writerWindowVerified": false,
    "isolationAnalysisReady": false,
  }
}

///|
/// Recheck two snapshots and report client coverage of the newly visible ledger effects.
pub fn verify_configured_writer_window_v4_json(
  before : String,
  after : String,
  session : String,
  options : String,
) -> String {
  configured_writer_window_v4(before, after, session, options).stringify() catch {
    error =>
      (
        {
          "format": "moontxnwitness-configured-writer-window/v4",
          "status": if error.to_string().contains("budget:") {
            Json("unknown")
          } else {
            Json("invalid")
          },
          "valid": false,
          "ledgerDeltaCovered": false,
          "sourceFactsProduced": false,
          "sourceAuthenticated": false,
          "writerWindowVerified": false,
          "isolationAnalysisReady": false,
          "reason": Json(error.to_string()),
        } : Json).stringify()
  }
}
