///|
/// Native scoped-factory ownership. This protocol does not reuse the configured
/// ORM engine attachment claim or silently turn local factories into engines.
fn model_lifecycle_v3(
  text : String,
  installation : Map[String, Json],
  final_record : Map[String, Json],
) -> OrmProfileWindowV3 raise {
  orm_assert(
    orm_utf8_size(text) <= 8388608 && text.has_suffix("\n"),
    "Bounded original model lifecycle JSONL",
  )
  let lines = text.split("\n").to_array()
  orm_assert(
    lines.length() >= 10 &&
    lines.length() <= 65537 &&
    lines[lines.length() - 1].is_empty(),
    "Complete model lifecycle envelope",
  )
  let records : Array[Json] = []
  let prefix = StringBuilder()
  let connected : Map[String, Bool] = Map([])
  let closed_connections : Map[String, Bool] = Map([])
  let calls : Map[String, Map[String, Json]] = Map([])
  let finished : Map[String, Bool] = Map([])
  let active : Map[String, String] = Map([])
  let active_txs : Map[String, String] = Map([])
  let mut domain = ""
  let mut opened = -1
  let mut quiesced = -1
  let mut closed = -1
  let mut attached = false
  let mut detached = false
  for i in 0..<(lines.length() - 1) {
    let line = lines[i].to_owned()
    orm_assert(
      !line.is_empty() && orm_utf8_size(line) <= 524288,
      "Bounded actual model lifecycle record",
    )
    let raw = guarded_json(line, limit=524288)
    let record = object_fields(raw, "model lifecycle")
    orm_equal(
      required(record, "seq", "lifecycle"),
      Json(i + 1),
      "Contiguous original lifecycle sequence",
    )
    let kind = orm_text(required(record, "kind", "lifecycle"))
    if i == 0 {
      orm_exact(raw, [
        "seq", "kind", "format", "diagnosticOnly", "processMonotonicDomain",
      ])
      |> ignore
      orm_equal(
        required(record, "format", "header"),
        Json("moontxnwitness-instrumentation/v1"),
        "Original diagnostic instrumentation format",
      )
      orm_equal(
        required(record, "diagnosticOnly", "header"),
        Json(true),
        "Raw diagnostic flag retained",
      )
      orm_assert(kind == "header", "One initial lifecycle header")
      domain = identifier(
        required(record, "processMonotonicDomain", "header"),
        "process domain",
      )
    } else if i == lines.length() - 2 {
      orm_exact(raw, ["seq", "kind", "prefixSha256", "records"]) |> ignore
      orm_assert(
        kind == "seal" && detached,
        "One terminal closed lifecycle seal",
      )
      orm_equal(
        required(record, "records", "seal"),
        Json(i),
        "Lifecycle record count",
      )
      orm_equal(
        required(record, "prefixSha256", "seal"),
        Json(v3_dislock_sha256(prefix.to_string())),
        "Original lifecycle prefix bytes",
      )
    } else {
      orm_equal(
        required(record, "processMonotonicDomain", "record"),
        Json(domain),
        "One original client clock domain",
      )
      let ns = orm_profile_ns_v3(record)
      if kind == "model-window-open" ||
        kind == "model-window-quiesced" ||
        kind == "model-window-close" {
        orm_equal(
          required(record, "profile", "window"),
          Json("pg18-configured-models/1"),
          "Pinned model profile",
        )
        orm_equal(
          required(record, "installationNonce", "window"),
          required(installation, "nonce", "installation"),
          "One original installation identity",
        )
        if kind == "model-window-open" {
          orm_assert(
            i == 1 && opened < 0 && !attached && !detached,
            "Initialized source opens before factory creation",
          )
          orm_equal(
            required(record, "initialSourceSeq", "window"),
            required(installation, "sourceSeq", "installation"),
            "Original initialized source record",
          )
          opened = i
        } else if kind == "model-window-quiesced" {
          orm_assert(
            attached &&
            !detached &&
            quiesced < 0 &&
            closed < 0 &&
            active.is_empty() &&
            active_txs.is_empty() &&
            connected.length() == closed_connections.length(),
            "All actual connections, transactions and calls finish before quiescence",
          )
          quiesced = i
        } else {
          orm_assert(
            quiesced > opened && closed < 0 && !detached,
            "Final source window closes after actual workers stop",
          )
          orm_equal(
            required(record, "finalSourceSeq", "window"),
            required(final_record, "sourceSeq", "finalization"),
            "Original final locked source record",
          )
          closed = i
        }
      } else if kind == "model-factory-attached" {
        orm_assert(
          opened >= 0 &&
          !attached &&
          !detached &&
          connected.is_empty() &&
          quiesced < 0,
          "One startup local factory before every business connection",
        )
        orm_equal(
          required(record, "asynchronous", "factory"),
          Json(false),
          "First profile supports native synchronous factory only",
        )
        attached = true
      } else if kind == "instrumentation-detached" {
        orm_assert(
          attached &&
          !detached &&
          closed > quiesced &&
          quiesced > opened &&
          active.is_empty() &&
          active_txs.is_empty() &&
          connected.length() == closed_connections.length(),
          "No live work survives finalized model observation",
        )
        orm_equal(
          required(record, "borrowedConnections", "detach"),
          Json(0),
          "No borrowed connection on detach",
        )
        detached = true
      } else {
        orm_assert(
          attached && !detached && opened >= 0 && quiesced < 0 && closed < 0,
          "All driver work stays inside initialized attached window",
        )
        let connection = identifier(
          required(record, "connection", "lifecycle"),
          "actual connection",
        )
        if kind == "connect" {
          orm_assert(
            !connected.contains(connection),
            "Each actual connection is observed once from creation",
          )
          orm_equal(
            required(record, "asynchronous", "connect"),
            Json(false),
            "Synchronous native connection",
          )
          connected[connection] = true
        } else {
          orm_assert(
            connected.contains(connection) &&
            !closed_connections.contains(connection),
            "Actual work uses a live observed connection",
          )
          if kind == "connection-close" {
            orm_assert(
              !active.contains(connection) && !active_txs.contains(connection),
              "Connection closes after its actual calls and transactions complete",
            )
            closed_connections[connection] = true
          } else if kind == "call-start" {
            let id = identifier(
              required(record, "callId", "call"),
              "actual call",
            )
            orm_assert(
              !calls.contains(id) && !active.contains(connection),
              "Each original call has one nonoverlapping start",
            )
            orm_assert(
              ["execute", "commit", "rollback"].contains(
                orm_text(required(record, "method", "call")),
              ),
              "Supported fixed driver method",
            )
            let call_method = orm_text(required(record, "method", "call"))
            match required(record, "tx", "call") {
              Null =>
                orm_assert(
                  call_method != "execute" && !active_txs.contains(connection),
                  "Administrative completion cannot hide an active transaction",
                )
              String(tx) =>
                match active_txs.get(connection) {
                  Some(current) =>
                    orm_assert(
                      current == tx,
                      "Actual transaction identity remains active until confirmed completion",
                    )
                  None => {
                    orm_assert(
                      call_method == "execute",
                      "Terminal call requires an actual active transaction",
                    )
                    active_txs[connection] = tx
                  }
                }
              _ => fail("Actual transaction identity is string or null")
            }
            calls[id] = record
            active[connection] = id
          } else if kind == "call-end" {
            let id = identifier(
              required(record, "callId", "call"),
              "actual call",
            )
            orm_assert(
              calls.contains(id) &&
              !finished.contains(id) &&
              active.get(connection) == Some(id),
              "Exact original call completion",
            )
            orm_assert(
              orm_profile_ns_le_v3(orm_profile_ns_v3(calls[id]), ns),
              "Actual call start precedes response",
            )
            for field in ["connection", "tx", "method"] {
              orm_equal(
                required(record, field, "call"),
                required(calls[id], field, "start"),
                "Paired original call identity",
              )
            }
            finished[id] = true
            active.remove(connection) |> ignore
            if required(record, "method", "call") != Json("execute") {
              active_txs.remove(connection) |> ignore
            }
          } else if kind == "commit-response" {
            let id = match active.get(connection) {
              Some(id) => id
              None => fail("Native COMMIT response outside original call")
            }
            orm_equal(
              required(calls[id], "method", "call"),
              Json("commit"),
              "Original native COMMIT call",
            )
            orm_assert(
              orm_profile_ns_le_v3(orm_profile_ns_v3(calls[id]), ns),
              "Native response follows actual call start",
            )
          } else {
            fail(
              "Unknown or unsupported lifecycle work prevents model promotion",
            )
          }
        }
      }
    }
    records.push(raw)
    prefix.write_string(line)
    prefix.write_string("\n")
  }
  orm_assert(
    opened == 1 &&
    quiesced > opened &&
    closed > quiesced &&
    attached &&
    detached &&
    calls.length() == finished.length() &&
    active.is_empty() &&
    active_txs.is_empty() &&
    connected.length() == closed_connections.length(),
    "Complete scoped factory lifecycle",
  )
  for (a, b) in [(opened, quiesced), (quiesced, closed)] {
    orm_assert(
      orm_profile_ns_le_v3(
        orm_profile_ns_v3(object_fields(records[a], "boundary")),
        orm_profile_ns_v3(object_fields(records[b], "boundary")),
      ),
      "Source boundary clocks preserve order",
    )
  }
  { records, opened, quiesced, closed, }
}
