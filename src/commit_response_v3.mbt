///|
/// A response to the original COMMIT is different from a later idle ROLLBACK.
fn v3_confirmed_commit_rollback(
  event : Map[String, Json],
  tx : V3CaptureTx,
) -> Bool raise {
  let proof = match event.get("commitResponse") {
    None => return false
    Some(value) => object_fields(value, "rollback_ok.commitResponse")
  }
  let request = v3_capture_seq(
    required(proof, "request", "commitResponse"),
    "commitResponse.request",
  )
  if !tx.commit_requested || tx.commit_request_seq != Some(request) {
    fail(
      "A COMMIT response must reference this transaction's pending COMMIT request",
    )
  }
  if proof.contains("commandTag") {
    known_fields(proof, ["request", "commandTag"], "commitResponse")
    if required(proof, "commandTag", "commitResponse") != Json("ROLLBACK") {
      fail("The acknowledged COMMIT must have returned commandTag ROLLBACK")
    }
  } else {
    known_fields(
      proof,
      ["request", "sqlstate", "diagnosticSqlstate", "transactionStatus"],
      "commitResponse",
    )
    let state = identifier(
      required(proof, "sqlstate", "commitResponse"),
      "commitResponse.sqlstate",
    )
    if !["40001", "40P01"].contains(state) ||
      required(proof, "diagnosticSqlstate", "commitResponse") != Json(state) ||
      required(proof, "transactionStatus", "commitResponse") != Json("IDLE") {
      fail(
        "COMMIT error proof requires matching server diagnostics and confirmed IDLE state",
      )
    }
  }
  true
}
