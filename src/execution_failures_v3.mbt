///|
fn v3_failure_kind(state : Json) -> String {
  match state {
    String("40P01") => "deadlock"
    String("40001") => "serialization_abort"
    String("55P03") => "lock_not_available"
    String("57014") => "query_canceled"
    _ => "statement_error"
  }
}

///|
/// Describe recorded driver failures independently of the isolation judgment.
/// A SQLSTATE is an observation supplied by the caller, not database attestation.
pub fn inspect_execution_failures_v3_json(text : String) -> String {
  try {
    let normalized = object_fields(
      guarded_json(normalize_capture_v3_json(text), limit=33554432),
      "normalized",
    )
    if normalized.at("status") == Json("invalid") {
      return (
        {
          "schemaVersion": 3,
          "algorithm": "v3-observed-failures-1",
          "valid": false,
          "status": "invalid",
          "reason": "The capture failed v3 structural or lifecycle validation",
          "faults": [],
        } : Json).stringify()
    }
    let faults : Array[Json] = []
    let events = presence_capture_array(
      normalized.at("observations"),
      "observations",
    )
    for raw in events {
      let event = object_fields(raw, "event")
      let kind = event.at("kind")
      if kind == Json("rows") {
        match event.get("error") {
          Some(value) => {
            let error = object_fields(value, "rows.error")
            let state = error.get_or_default("sqlstate", Json::null())
            faults.push({
              "seq": event.at("seq"),
              "tx": event.at("tx"),
              "statement": event.at("statement"),
              "kind": Json(v3_failure_kind(state)),
              "sqlstate": state,
              "driverClass": error.get_or_default("class", Json::null()),
              "origin": "rows.error",
            })
          }
          None => ()
        }
      } else if kind == Json("rollback_ok") {
        match event.get("commitResponse") {
          Some(value) => {
            let response = object_fields(value, "commitResponse")
            let state = response.get_or_default("sqlstate", Json::null())
            faults.push({
              "seq": event.at("seq"),
              "tx": event.at("tx"),
              "statement": Json::null(),
              "request": response.at("request"),
              "kind": Json(
                if response.contains("commandTag") {
                  "commit_rolled_back"
                } else {
                  v3_failure_kind(state)
                },
              ),
              "sqlstate": state,
              "driverClass": Json::null(),
              "origin": "rollback_ok.commitResponse",
            })
          }
          None => ()
        }
      }
    }
    (
      {
        "schemaVersion": 3,
        "algorithm": "v3-observed-failures-1",
        "valid": true,
        "status": "observations",
        "scope": "Recorded execution failures; not an isolation-level conclusion",
        "modelViolationClaim": false,
        "databaseAuthenticityVerified": false,
        "certifiesFailureAbsence": false,
        "captureStatus": normalized.at("status"),
        "captureCoverage": normalized.at("coverage"),
        "transactionOutcomes": normalized.at("transactions"),
        "observedFaultCount": Json(faults.length()),
        "faults": Json(faults),
      } : Json).stringify()
  } catch {
    error =>
      (
        {
          "schemaVersion": 3,
          "algorithm": "v3-observed-failures-1",
          "valid": false,
          "status": "invalid",
          "reason": Json(error.to_string()),
          "faults": [],
        } : Json).stringify()
  }
}
