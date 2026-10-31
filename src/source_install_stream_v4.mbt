///|
priv struct SourceWorkV4 {
  limit : Int32
  mut checks : Int32
}

///|
fn SourceWorkV4::charge(self : SourceWorkV4) -> Unit raise {
  if self.checks >= self.limit {
    fail("budget:source-component-checks")
  }
  self.checks += 1
}

///|
priv struct SourceCommandV4 {
  query_id : String
  sql : String
  parameters : Json
  native : Json
  decoded : Array[Json]
  before : Int32
  after : Int32
  request_seq : Int32
  result_seq : Int32
}

///|
priv struct SourceStreamV4 {
  commands : Array[SourceCommandV4]
  mut next_index : Int32
  work : SourceWorkV4
  commit_request_seq : Int32
}

///|
fn source_equal_v4(a : Json, b : Json, label : String) -> Unit raise {
  if sql_canonical_v1(a) != sql_canonical_v1(b) {
    fail("mismatch:source-" + label)
  }
}

///|
fn source_object_v4(value : Json) -> Map[String, Json] raise {
  object_fields(value, "source-component")
}

///|
fn source_positive_v4(value : Json) -> String raise {
  let text = sql_number_text_v1(value)
  if !sql_digits_v1(text) || text == "0" {
    fail("mismatch:source-positive-integer")
  }
  text
}

///|
fn source_parse_stream_v4(
  text : String,
  receipt : Json,
  policy : SourcePolicyV4,
  work : SourceWorkV4,
) -> SourceStreamV4 raise {
  if orm_utf8_size(text) > 8388608 ||
    orm_utf8_size(text) > policy.max_log_bytes ||
    !text.has_suffix("\n") {
    fail("unsupported:source-log-size-or-tail")
  }
  let lines = text.split("\n").to_array()
  if lines.length() < 5 || lines.length() > 65537 {
    fail("unsupported:source-log-record-count")
  }
  let prefix = StringBuilder()
  let commands : Array[SourceCommandV4] = []
  let mut pending : Map[String, Json]? = None
  let mut commit_request_seq = 0
  for index in 0..<(lines.length() - 1) {
    work.charge()
    let line = lines[index].to_owned()
    if line.is_empty() {
      fail("mismatch:source-empty-record")
    }
    let raw = sql_json_v1(line, 1048576)
    let record = source_object_v4(raw)
    if record.get("seq") != Some(Json(index + 1)) {
      fail("mismatch:source-record-sequence")
    }
    let kind = sql_string_v1(required(record, "kind", "source-record"))
    if index == 0 {
      let _ = orm_exact(raw, [
        "seq", "kind", "format", "diagnosticOnly", "processMonotonicDomain",
      ])
      if kind != "header" ||
        record.at("format") != Json("moontxnwitness-instrumentation/v1") ||
        record.at("diagnosticOnly") != Json(true) ||
        sql_string_v1(record.at("processMonotonicDomain")).is_empty() {
        fail("mismatch:source-header")
      }
    } else if index == lines.length() - 2 {
      let _ = orm_exact(raw, ["seq", "kind", "prefixSha256", "records"])
      if kind != "seal" ||
        pending is Some(_) ||
        record.at("records") != Json(index) ||
        record.at("prefixSha256") != Json(v3_dislock_sha256(prefix.to_string())) {
        fail("mismatch:source-seal")
      }
    } else if kind == "source-control-request" {
      let _ = orm_exact(raw, [
        "seq", "kind", "queryId", "sql", "parameters", "transactionStatusBefore",
      ])
      if pending is Some(_) {
        fail("mismatch:source-overlapping-control")
      }
      pending = Some(record)
    } else if kind == "source-control" {
      let _ = orm_exact(raw, [
        "seq", "kind", "requestSeq", "transactionStatusAfter", "queryId", "sql",
        "parameters", "native", "decodedRows",
      ])
      let request = match pending {
        Some(value) => value
        None => fail("mismatch:source-result-without-request")
      }
      source_equal_v4(
        record.at("requestSeq"),
        request.at("seq"),
        "request-reference",
      )
      for name in ["queryId", "sql", "parameters"] {
        source_equal_v4(
          record.at(name),
          request.at(name),
          "request-result-binding",
        )
      }
      let n = orm_exact(record.at("native"), [
        "status", "tag", "fields", "columns", "rows",
      ])
      let field_count = fetch_number_v1(n.at("fields"), 1)
      let native_rows = orm_array(n.at("rows"))
      let delivered = orm_array(record.at("decodedRows"))
      if native_rows.length() != delivered.length() ||
        native_rows.length() > 256 {
        fail("mismatch:source-control-row-count")
      }
      let decoded : Array[Json] = []
      if field_count == 0 {
        if n.at("status") != Json(1) ||
          !native_rows.is_empty() ||
          !orm_array(n.at("columns")).is_empty() {
          fail("mismatch:source-command-status")
        }
      } else {
        source_equal_v4(
          n.at("columns"),
          [{ "oid": 25, "format": 0 }],
          "native-text-column",
        )
        if n.at("status") != Json(2) ||
          n.at("tag") != Json("SELECT " + native_rows.length().to_string()) {
          fail("mismatch:source-select-status")
        }
        for row_index, raw_row in native_rows {
          work.charge()
          let raw_cells = orm_array(raw_row)
          let delivery_cells = orm_array(delivered[row_index])
          if raw_cells.length() != 1 || delivery_cells.length() != 1 {
            fail("mismatch:source-control-cell-count")
          }
          let encoded = sql_string_v1(raw_cells[0])
          if encoded.length() > 180000 {
            fail("budget:source-native-cell")
          }
          let bytes = @base64.decode(encoded[:], ignore_whitespace=false)
          if @base64.encode(bytes[:]) != encoded || bytes.length() > 131072 {
            fail("mismatch:source-native-base64")
          }
          let cell = @utf8.decode(bytes[:], ignore_bom=false)
          if delivery_cells[0] != Json(cell) {
            fail("mismatch:source-native-delivery")
          }
          decoded.push(sql_json_v1(cell, 131072))
        }
      }
      commands.push({
        query_id: sql_string_v1(record.at("queryId")),
        sql: sql_string_v1(record.at("sql")),
        parameters: record.at("parameters"),
        native: record.at("native"),
        decoded,
        before: fetch_number_v1(request.at("transactionStatusBefore"), 4),
        after: fetch_number_v1(record.at("transactionStatusAfter"), 4),
        request_seq: fetch_number_v1(request.at("seq"), 65536),
        result_seq: index + 1,
      })
      pending = None
    } else if kind == "source-install-commit-request" {
      let _ = orm_exact(raw, ["seq", "kind", "statusBefore"])
      if pending is Some(_) ||
        commit_request_seq != 0 ||
        record.at("statusBefore") != Json(2) {
        fail("mismatch:source-commit-request")
      }
      commit_request_seq = index + 1
    } else {
      fail("unsupported:source-log-kind")
    }
    if index != lines.length() - 2 {
      prefix.write_string(line)
      prefix.write_string("\n")
    }
  }
  let log = orm_exact(source_object_v4(receipt).at("log"), [
    "sealed", "records", "bytes", "sha256",
  ])
  source_equal_v4(log.at("sealed"), Json(true), "receipt-log-sealed")
  source_equal_v4(
    log.at("records"),
    Json(lines.length() - 1),
    "receipt-log-count",
  )
  source_equal_v4(
    log.at("bytes"),
    Json(orm_utf8_size(text)),
    "receipt-log-bytes",
  )
  source_equal_v4(
    log.at("sha256"),
    Json(v3_dislock_sha256(text)),
    "receipt-log-digest",
  )
  { commands, next_index: 0, work, commit_request_seq, }
}

///|
fn SourceStreamV4::next(
  self : SourceStreamV4,
  id : String,
  sql : String,
  params : Json,
) -> SourceCommandV4 raise {
  self.work.charge()
  if self.next_index >= self.commands.length() {
    fail("mismatch:source-missing-command")
  }
  let command = self.commands[self.next_index]
  self.next_index += 1
  if command.query_id != id || command.sql != sql {
    fail("mismatch:source-command-SQL-" + id)
  }
  source_equal_v4(command.parameters, params, "command-parameters-" + id)
  if command.before != (if id == "begin" { 0 } else { 2 }) ||
    command.after != (if id == "installation-commit" { 0 } else { 2 }) {
    fail("mismatch:source-control-transaction-state")
  }
  command
}

///|
fn source_command_ack_v4(command : SourceCommandV4, tag : String) -> Unit raise {
  let n = source_object_v4(command.native)
  if n.at("status") != Json(1) ||
    n.at("tag") != Json(tag) ||
    n.at("fields") != Json(0) {
    fail("mismatch:source-command-acknowledgement")
  }
}

///|
fn SourceStreamV4::one(
  self : SourceStreamV4,
  id : String,
  sql : String,
  params : Json,
) -> Json raise {
  let command = self.next(id, sql, params)
  if command.decoded.length() != 1 {
    fail("mismatch:source-single-row-" + id)
  }
  command.decoded[0]
}
