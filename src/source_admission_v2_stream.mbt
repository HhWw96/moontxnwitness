///|
priv struct SourceControlStreamV2 {
  commands : Array[SourceCommandV4]
  mut next_index : Int32
  work : SourceWorkV4
  commit_request_seq : Int32
}

///|
fn admission_bytes_v2(value : Json, maximum : Int32) -> String raise {
  let text = sql_string_v1(value)
  if text.length() > (maximum + 2) / 3 * 4 {
    fail("budget:admission-native-cell")
  }
  let bytes = @base64.decode(text[:], ignore_whitespace=false)
  if @base64.encode(bytes[:]) != text || bytes.length() > maximum {
    fail("mismatch:admission-native-base64")
  }
  @utf8.decode(bytes[:], ignore_bom=false)
}

///|
fn source_control_tag_v2(command : SourceCommandV4) -> String raise {
  admission_bytes_v2(
    source_object_v4(command.native).at("commandStatusBase64"),
    128,
  )
}

///|
fn source_control_count_v2(command : SourceCommandV4) -> String? raise {
  let n = source_object_v4(command.native)
  let count = orm_exact(n.at("commandTuples"), ["pythonType", "value"])
  if count.at("pythonType") == Json("builtins.NoneType") &&
    count.at("value") == Json::null() {
    return None
  }
  if count.at("pythonType") != Json("builtins.int") {
    fail("mismatch:admission-command-count-type")
  }
  let text = sql_string_v1(count.at("value"))
  if !sql_digits_v1(text) ||
    (text != "0" && text.has_prefix("0")) ||
    text.length() > 19 ||
    (text.length() == 19 && text > "9223372036854775807") {
    fail("mismatch:admission-command-count")
  }
  Some(text)
}

///|
fn source_control_ack_v2(command : SourceCommandV4, tag : String) -> Unit raise {
  let native = source_object_v4(command.native)
  if native.at("status") != Json(1) ||
    native.at("fieldCount") != Json(0) ||
    source_control_tag_v2(command) != tag {
    fail("mismatch:admission-command-ack")
  }
  let count = source_control_count_v2(command)
  let expected = if tag.has_prefix("INSERT 0 ") {
    Some(tag[9:].to_owned())
  } else if tag.has_prefix("UPDATE ") {
    Some(tag[7:].to_owned())
  } else if tag.has_prefix("DELETE ") {
    Some(tag[7:].to_owned())
  } else {
    None
  }
  if count != expected {
    fail("mismatch:admission-command-getter-ack")
  }
}

///|
fn source_parse_control_v2(
  text : String,
  log_receipt : Json,
  expected_log_format : String,
  expected_contract : String,
  work : SourceWorkV4,
  allow_commit_request~ : Bool = false,
  allow_snapshot_pages~ : Bool = false,
  allow_predicate_rows~ : Bool = false,
) -> SourceControlStreamV2 raise {
  if orm_utf8_size(text) > 67108864 || !text.has_suffix("\n") {
    fail("unsupported:admission-log-size-or-tail")
  }
  let lines = text.split("\n").to_array()
  if lines.length() < 3 || lines.length() > 65537 {
    fail("unsupported:admission-record-count")
  }
  let prefix = StringBuilder()
  let commands : Array[SourceCommandV4] = []
  let mut pending : Map[String, Json]? = None
  let mut result : Map[String, Json]? = None
  let mut commit_request_seq = 0
  for index in 0..<(lines.length() - 1) {
    work.charge()
    let line = lines[index].to_owned()
    if line.is_empty() {
      fail("mismatch:admission-empty-log-record")
    }
    let raw = sql_json_v1(line, 524288)
    let record = source_object_v4(raw)
    if record.get("seq") != Some(Json(index + 1)) {
      fail("mismatch:admission-record-sequence")
    }
    let kind = sql_string_v1(required(record, "kind", "admission-record"))
    if index == 0 {
      let _ = orm_exact(raw, [
        "seq", "kind", "format", "contract", "sourceFactsProduced",
      ])
      if kind != "header" ||
        record.at("format") != Json(expected_log_format) ||
        record.at("contract") != Json(expected_contract) ||
        record.at("sourceFactsProduced") != Json(false) {
        fail("mismatch:admission-header")
      }
    } else if index == lines.length() - 2 {
      let _ = orm_exact(raw, ["seq", "kind", "prefixSha256", "records"])
      if kind != "seal" ||
        pending is Some(_) ||
        result is Some(_) ||
        record.at("records") != Json(index) ||
        record.at("prefixSha256") != Json(v3_dislock_sha256(prefix.to_string())) {
        fail("mismatch:admission-seal")
      }
    } else if kind == "control-request" {
      let _ = orm_exact(raw, [
        "seq", "kind", "format", "queryId", "sql", "parameters", "transactionStatusBefore",
      ])
      if record.at("format") != Json("moontxnwitness-source-control-request/v2") ||
        pending is Some(_) ||
        result is Some(_) {
        fail("mismatch:admission-overlapping-request")
      }
      pending = Some(record)
    } else if kind == "control-native" {
      let _ = orm_exact(raw, [
        "seq", "kind", "format", "requestSeq", "queryId", "native", "transactionStatusAfter",
      ])
      let request = match pending {
        Some(value) => value
        None => fail("mismatch:admission-native-without-request")
      }
      if result is Some(_) ||
        record.at("format") != Json("moontxnwitness-source-control-native/v2") ||
        record.at("requestSeq") != request.at("seq") ||
        record.at("queryId") != request.at("queryId") {
        fail("mismatch:admission-native-reference")
      }
      result = Some(record)
    } else if kind == "control-delivery" {
      let _ = orm_exact(raw, [
        "seq", "kind", "format", "requestSeq", "queryId", "observation",
      ])
      let request = match pending {
        Some(value) => value
        None => fail("mismatch:admission-delivery-without-request")
      }
      let observed = match result {
        Some(value) => value
        None => fail("mismatch:admission-delivery-without-native")
      }
      if record.at("format") !=
        Json("moontxnwitness-source-control-delivery/v2") ||
        record.at("requestSeq") != request.at("seq") ||
        record.at("queryId") != request.at("queryId") {
        fail("mismatch:admission-delivery-reference")
      }
      let native = orm_exact(observed.at("native"), [
        "rawComplete", "status", "fieldCount", "rowCount", "commandStatusBase64",
        "commandTuples", "fields", "rows",
      ])
      if native.at("rawComplete") != Json(true) {
        fail("unsupported:admission-incomplete-native-buffer")
      }
      let fields = fetch_number_v1(native.at("fieldCount"), 1)
      let rows = orm_array(native.at("rows"))
      let paged = allow_snapshot_pages &&
        [Json("visible-row-page"), Json("retained-effect-page")].contains(
          request.at("queryId"),
        )
      let predicate = allow_predicate_rows &&
        request.at("queryId") == Json("range")
      let max_rows = if paged || predicate { 128 } else { 1 }
      if rows.length() > max_rows ||
        native.at("rowCount") != Json(rows.length()) {
        fail("mismatch:admission-native-row-count")
      }
      let delivery = orm_exact(record.at("observation"), [
        "method", "fetchExecuted", "pythonType", "rows",
      ])
      let delivered = orm_array(delivery.at("rows"))
      let decoded : Array[Json] = []
      if fields == 0 {
        if native.at("status") != Json(1) ||
          !rows.is_empty() ||
          native.at("fields") != Json::array([]) ||
          delivery.at("method") != Json::null() ||
          delivery.at("fetchExecuted") != Json(false) ||
          delivery.at("pythonType") != Json("builtins.NoneType") ||
          !delivered.is_empty() {
          fail("mismatch:admission-command-observation")
        }
      } else {
        if native.at("status") != Json(2) ||
          native.at("fields") != Json([{ "oid": 25, "format": 0 }]) ||
          delivery.at("method") != Json("fetchall") ||
          delivery.at("fetchExecuted") != Json(true) ||
          delivery.at("pythonType") != Json("builtins.list") ||
          delivered.length() != rows.length() {
          fail("mismatch:admission-text-result-observation")
        }
        let mut page_bytes = 0
        for row_index, value in rows {
          work.charge()
          let cells = orm_array(value)
          let delivered_row = orm_exact(delivered[row_index], [
            "pythonType", "cells",
          ])
          let delivered_cells = orm_array(delivered_row.at("cells"))
          if cells.length() != 1 ||
            delivered_cells.length() != 1 ||
            delivered_row.at("pythonType") != Json("builtins.tuple") {
            fail("mismatch:admission-control-row-type")
          }
          let actual = orm_exact(delivered_cells[0], ["pythonType", "value"])
          let cell = admission_bytes_v2(cells[0], 131072)
          if paged {
            page_bytes += orm_utf8_size(cell)
            if page_bytes > 131072 {
              fail("budget:snapshot-native-page-bytes")
            }
          }
          if actual.at("pythonType") != Json("builtins.str") ||
            actual.at("value") != Json(cell) {
            fail("mismatch:admission-control-native-delivery")
          }
          decoded.push(sql_json_v1(cell, 131072))
        }
      }
      let command : SourceCommandV4 = {
        query_id: sql_string_v1(request.at("queryId")),
        sql: sql_string_v1(request.at("sql")),
        parameters: request.at("parameters"),
        native: observed.at("native"),
        decoded,
        before: fetch_number_v1(request.at("transactionStatusBefore"), 4),
        after: fetch_number_v1(observed.at("transactionStatusAfter"), 4),
        request_seq: fetch_number_v1(request.at("seq"), 65536),
        result_seq: fetch_number_v1(observed.at("seq"), 65536),
      }
      let count = source_control_count_v2(command)
      let tag = source_control_tag_v2(command)
      if fields == 1 &&
        (
          tag != "SELECT " + rows.length().to_string() ||
          count != Some(rows.length().to_string())
        ) {
        fail("mismatch:admission-select-command-count")
      }
      commands.push(command)
      pending = None
      result = None
    } else if kind == "installation-commit-request" {
      let _ = orm_exact(raw, [
        "seq", "kind", "format", "transactionStatusBefore",
      ])
      if !allow_commit_request ||
        pending is Some(_) ||
        result is Some(_) ||
        commit_request_seq != 0 ||
        record.at("format") != Json("moontxnwitness-source-commit-request/v2") ||
        record.at("transactionStatusBefore") != Json(2) {
        fail("mismatch:admission-installation-commit-request")
      }
      commit_request_seq = index + 1
    } else {
      fail("unsupported:admission-log-kind")
    }
    if index != lines.length() - 2 {
      prefix.write_string(line)
      prefix.write_string("\n")
    }
  }
  let r = orm_exact(log_receipt, [
    "format", "sealed", "records", "bytes", "sha256",
  ])
  if r.at("format") != Json(expected_log_format) ||
    r.at("sealed") != Json(true) ||
    r.at("records") != Json(lines.length() - 1) ||
    r.at("bytes") != Json(orm_utf8_size(text)) ||
    r.at("sha256") != Json(v3_dislock_sha256(text)) {
    fail("mismatch:admission-log-receipt")
  }
  { commands, next_index: 0, work, commit_request_seq, }
}

///|
fn SourceControlStreamV2::next(
  self : SourceControlStreamV2,
  id : String,
  sql : String,
  params : Json,
  before~ : Int32 = 2,
  after~ : Int32 = 2,
) -> SourceCommandV4 raise {
  self.work.charge()
  if self.next_index >= self.commands.length() {
    fail("mismatch:admission-missing-command-" + id)
  }
  let command = self.commands[self.next_index]
  self.next_index += 1
  if command.query_id != id ||
    command.sql != sql ||
    command.before != before ||
    command.after != after {
    fail("mismatch:admission-command-SQL-state-" + id)
  }
  source_equal_v4(command.parameters, params, "V2-command-parameters-" + id)
  command
}

///|
fn SourceControlStreamV2::one(
  self : SourceControlStreamV2,
  id : String,
  sql : String,
  params : Json,
  before~ : Int32 = 2,
  after~ : Int32 = 2,
) -> Json raise {
  let command = self.next(id, sql, params, before~, after~)
  if command.decoded.length() != 1 {
    fail("mismatch:admission-one-control-row-" + id)
  }
  command.decoded[0]
}
