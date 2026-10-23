///|
/// Exact lifecycle ownership is separate from SQL/source semantics. Missing or
/// unknown observations cannot be promoted by an otherwise valid source proof.
fn orm_profile_ns_le_v3(a : String, b : String) -> Bool {
  if a.length() != b.length() {
    return a.length() < b.length()
  }
  for i in 0..<a.length() {
    let x = a.unsafe_get(i).to_int()
    let y = b.unsafe_get(i).to_int()
    if x != y {
      return x < y
    }
  }
  true
}

///|
fn orm_profile_ns_v3(record : Map[String, Json]) -> String raise {
  let ns = orm_text(required(record, "monotonicNs", "lifecycle"))
  orm_assert(ns.length() > 0 && ns.length() <= 20, "Bounded lifecycle clock")
  orm_assert(
    ns.length() == 1 || !ns.has_prefix("0"),
    "Canonical decimal lifecycle clock",
  )
  for c in ns.iter() {
    orm_assert(c >= '0' && c <= '9', "Decimal lifecycle clock")
  }
  ns
}

///|
fn orm_profile_ownership_v3(window : OrmProfileWindowV3) -> Unit raise {
  let open_ns = orm_profile_ns_v3(
    object_fields(window.records[window.opened], "open"),
  )
  let quiet_ns = orm_profile_ns_v3(
    object_fields(window.records[window.quiesced], "quiesced"),
  )
  let close_ns = orm_profile_ns_v3(
    object_fields(window.records[window.closed], "close"),
  )
  orm_assert(
    orm_profile_ns_le_v3(open_ns, quiet_ns) &&
    orm_profile_ns_le_v3(quiet_ns, close_ns),
    "Profile boundary clock order",
  )
  let connected : Map[String, Bool] = Map([])
  let pooled : Map[String, Bool] = Map([])
  let borrowed : Map[String, Bool] = Map([])
  let pool_closed : Map[String, Bool] = Map([])
  let connection_closed : Map[String, Bool] = Map([])
  let active_calls : Map[String, Map[String, Json]] = Map([])
  let active_txs : Map[String, String] = Map([])
  let seen_calls : Map[String, Bool] = Map([])
  let mut attached = false
  let mut detached = false
  for i, raw in window.records {
    let record = object_fields(raw, "lifecycle")
    let kind = orm_text(required(record, "kind", "lifecycle"))
    if kind == "header" || kind == "seal" {
      continue
    }
    let ns = orm_profile_ns_v3(record)
    if kind == "profile-window-open" {
      continue
    }
    if kind == "profile-window-quiesced" || kind == "profile-window-close" {
      orm_assert(
        attached &&
        !detached &&
        borrowed.is_empty() &&
        active_calls.is_empty() &&
        active_txs.is_empty(),
        "Profile boundary requires all actual leases, calls and transactions to finish",
      )
      continue
    }
    if kind == "engine-attached" {
      orm_assert(
        !attached && !detached && i > window.opened && i < window.quiesced,
        "One engine must attach before observed work",
      )
      match required(record, "asynchronous", "attachment") {
        True | False => ()
        _ => fail("Typed engine attachment required")
      }
      attached = true
    } else if kind == "instrumentation-detached" {
      orm_assert(
        attached &&
        !detached &&
        i > window.closed &&
        i < window.records.length() - 1,
        "Detach only after the finalized worker window",
      )
      orm_equal(
        required(record, "borrowedConnections", "detach"),
        (0).to_json(),
        "No connection may remain borrowed on detach",
      )
      orm_assert(
        borrowed.is_empty() && active_calls.is_empty() && active_txs.is_empty(),
        "No unobserved work may survive detach",
      )
      orm_assert(
        orm_profile_ns_le_v3(close_ns, ns),
        "Detach follows the final boundary clock",
      )
      detached = true
      continue
    } else {
      orm_assert(
        attached && !detached && i > window.opened && i < window.quiesced,
        "All actual driver and pool work must be inside the attached worker window",
      )
      let connection = identifier(
        required(record, "connection", "lifecycle"),
        "actual connection",
      )
      if kind == "connect" {
        orm_assert(
          !connected.contains(connection),
          "One observed physical connection identity",
        )
        connected[connection] = true
      } else if kind == "pool-connect" {
        orm_assert(
          connected.contains(connection) &&
          !pooled.contains(connection) &&
          !connection_closed.contains(connection),
          "Pool connection requires its original wrapped connection",
        )
        pooled[connection] = true
      } else if kind == "pool-checkout" {
        orm_assert(
          pooled.contains(connection) &&
          !borrowed.contains(connection) &&
          !pool_closed.contains(connection) &&
          !connection_closed.contains(connection),
          "Pool checkout requires a live returned connection",
        )
        borrowed[connection] = true
      } else if kind == "pool-checkin" {
        orm_assert(
          borrowed.contains(connection) &&
          !active_calls.contains(connection) &&
          !active_txs.contains(connection),
          "Pool checkin requires confirmed transaction completion",
        )
        borrowed.remove(connection) |> ignore
      } else if kind == "pool-reset" {
        orm_assert(
          borrowed.contains(connection) && !active_calls.contains(connection),
          "Pool reset requires a known idle driver lease",
        )
        orm_equal(
          required(record, "terminateOnly", "reset"),
          false.to_json(),
          "Terminating reset is outside the verified profile",
        )
        orm_equal(
          required(record, "transactionWasReset", "reset"),
          false.to_json(),
          "Implicit reset outcome is outside the verified profile",
        )
        match required(record, "asyncioSafe", "reset") {
          True | False => ()
          _ => fail("Typed reset safety observation required")
        }
      } else if kind == "pool-close" || kind == "connection-close" {
        orm_assert(
          pooled.contains(connection) &&
          !borrowed.contains(connection) &&
          !active_calls.contains(connection) &&
          !active_txs.contains(connection),
          "Physical close cannot hide active or borrowed work",
        )
        if kind == "pool-close" {
          orm_assert(
            !pool_closed.contains(connection),
            "One pool close observation",
          )
          pool_closed[connection] = true
        } else {
          orm_assert(
            !connection_closed.contains(connection),
            "One physical connection close observation",
          )
          connection_closed[connection] = true
        }
      } else if kind == "call-start" {
        orm_assert(
          borrowed.contains(connection) &&
          !pool_closed.contains(connection) &&
          !connection_closed.contains(connection) &&
          !active_calls.contains(connection),
          "Actual calls require a live exclusive observed lease",
        )
        let id = identifier(required(record, "callId", "call"), "call identity")
        orm_assert(!seen_calls.contains(id), "One atomic driver call identity")
        seen_calls[id] = true
        let call_method = orm_text(required(record, "method", "call"))
        orm_assert(
          ["execute", "commit", "rollback"].contains(call_method),
          "Only configured fixed-profile calls are covered",
        )
        match required(record, "tx", "call") {
          Null => {
            orm_assert(
              call_method != "execute" && !active_txs.contains(connection),
              "Only transaction-free administrative completion may have a null transaction",
            )
            orm_equal(
              required(record, "statementSeq", "call"),
              Json::null(),
              "Administrative call cannot contain a SQL statement",
            )
            orm_assert(
              object_fields(
                required(record, "journalEventSeqs", "call"),
                "refs",
              ).is_empty(),
              "Administrative call cannot assert transaction facts",
            )
          }
          String(tx) =>
            match active_txs.get(connection) {
              Some(current) =>
                orm_assert(
                  current == tx,
                  "Observed transaction identity remains active until confirmed completion",
                )
              None => {
                orm_assert(
                  call_method == "execute",
                  "Terminal driver call requires an observed active transaction",
                )
                active_txs[connection] = tx
              }
            }
          _ => fail("Actual transaction identity must be a string or null")
        }
        active_calls[connection] = record
      } else if kind == "call-end" {
        let start = match active_calls.get(connection) {
          Some(start) => start
          None => fail("Actual call end requires an active call on this lease")
        }
        for field in ["callId", "method", "tx"] {
          orm_equal(
            required(record, field, "end"),
            required(start, field, "start"),
            "Atomic call identity and transaction binding",
          )
        }
        orm_assert(
          orm_profile_ns_le_v3(orm_profile_ns_v3(start), ns),
          "Actual driver call clock order",
        )
        orm_equal(
          required(record, "succeeded", "call"),
          true.to_json(),
          "Unconfirmed or failed calls remain uncovered",
        )
        let call_method = orm_text(required(record, "method", "call"))
        if required(record, "tx", "call") == Json::null() {
          orm_equal(
            required(record, "statementSeq", "call"),
            Json::null(),
            "Administrative completion has no SQL statement",
          )
          orm_assert(
            object_fields(required(record, "journalEventSeqs", "call"), "refs").is_empty(),
            "Administrative completion has no transaction facts",
          )
        }
        if call_method != "execute" {
          active_txs.remove(connection) |> ignore
        }
        active_calls.remove(connection) |> ignore
      } else if kind == "commit-response" {
        let start = match active_calls.get(connection) {
          Some(start) => start
          None => fail("Native response requires an actual active COMMIT call")
        }
        orm_equal(
          required(start, "method", "call"),
          "commit".to_json(),
          "Native response belongs to COMMIT",
        )
        orm_assert(
          required(start, "tx", "call") != Json::null(),
          "Native response requires a known transaction",
        )
        orm_assert(
          orm_profile_ns_le_v3(orm_profile_ns_v3(start), ns),
          "Native response follows its request call",
        )
      } else {
        // Includes invalidation, soft-invalidation, driver errors and future SQL
        // sidecar records. They require an explicit semantic contract first.
        fail(
          "Unsupported lifecycle observation prevents full profile coverage: " +
          kind,
        )
      }
    }
    orm_assert(
      orm_profile_ns_le_v3(open_ns, ns) && orm_profile_ns_le_v3(ns, quiet_ns),
      "Worker observations remain inside the actual boundary clock interval",
    )
  }
  orm_assert(
    attached && detached,
    "Complete engine attachment and detach evidence required; local factories remain diagnostic",
  )
}

///|
/// Verify the index's own checksum from the original text, eliding only its
/// top-level digest member. No other number, Unicode string or whitespace is
/// decoded/re-encoded; segment payload verification is a separate boundary.
fn orm_profile_index_digest_v3(
  text : String,
  index : Map[String, Json],
) -> Unit raise {
  let expected = orm_text(required(index, "indexSha256", "index"))
  orm_assert(expected.length() == 64, "Index digest is a SHA256 value")
  for c in expected.iter() {
    orm_assert(
      (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'),
      "Canonical lower-case SHA256 required",
    )
  }
  let scan : JsonScan = {
    chars: text.iter().collect(),
    decoded_keys: Map([]),
    pos: 0,
    depth: 0,
  }
  scan.white()
  orm_assert(
    scan.pos < scan.chars.length() && scan.chars[scan.pos] == '{',
    "Original index object required",
  )
  scan.pos += 1
  let mut previous_comma = -1
  let mut remove_start = -1
  let mut remove_end = -1
  while scan.pos < scan.chars.length() {
    scan.white()
    orm_assert(scan.pos < scan.chars.length(), "Complete original index object")
    if scan.chars[scan.pos] == '}' {
      break
    }
    let key_start = scan.pos
    let key = orm_text(guarded_json(scan.string_token(), limit=2097152))
    scan.white()
    orm_assert(
      scan.pos < scan.chars.length() && scan.chars[scan.pos] == ':',
      "Original index member colon",
    )
    scan.pos += 1
    scan.value()
    scan.white()
    let value_end = scan.pos
    orm_assert(scan.pos < scan.chars.length(), "Original index member boundary")
    let comma = scan.chars[scan.pos] == ','
    orm_assert(comma || scan.chars[scan.pos] == '}', "Original index separator")
    if key == "indexSha256" {
      orm_assert(remove_start < 0, "One top-level index digest")
      remove_start = if previous_comma >= 0 {
        previous_comma
      } else {
        key_start
      }
      remove_end = if previous_comma < 0 && comma {
        value_end + 1
      } else {
        value_end
      }
    }
    if !comma {
      break
    }
    previous_comma = scan.pos
    scan.pos += 1
  }
  orm_assert(
    remove_start >= 0 && remove_end > remove_start,
    "Top-level index checksum member required",
  )
  let body_end = if scan.chars.length() > 0 &&
    scan.chars[scan.chars.length() - 1] == '\n' {
    scan.chars.length() - 1
  } else {
    scan.chars.length()
  }
  let payload = StringBuilder()
  for i in 0..<body_end {
    if i < remove_start || i >= remove_end {
      payload.write_char(scan.chars[i])
    }
  }
  orm_equal(
    v3_dislock_sha256(payload.to_string()).to_json(),
    expected.to_json(),
    "Original journal index checksum",
  )
}
