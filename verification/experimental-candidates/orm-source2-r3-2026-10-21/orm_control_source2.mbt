///|
priv struct OrmControl2 {
  seq : Int64
  connection : String
  backend : Int64
  transaction : String
  sql : String
  parameters : Json
  rows : Array[Json]
  result : Map[String, Json]
  before : String
  after : String
}

///|
priv struct OrmControlCursor2 {
  controls : Array[OrmControl2]
  mut at : Int
  verified : Array[Json]
}

///|
fn orm2_integer(value : Json) -> Int64 raise {
  match value {
    Number(n, ..) => {
      orm_assert(n >= -9007199254740991.0 && n <= 9007199254740991.0, "Exact bounded JSON integer range")
      let integer = n.to_int64()
      orm_assert(
        integer.to_double() == n && integer >= -9007199254740991L &&
        integer <= 9007199254740991L,
        "Exact bounded JSON integer required",
      )
      integer
    }
    _ => fail("JSON integer required")
  }
}

///|
fn orm2_text_integer(text : String) -> Json raise {
  let value = orm2_integer(guarded_json(text, limit=64))
  orm_assert(value.to_string() == text, "Canonical PostgreSQL integer text required")
  orm_assert(
    value >= -9007199254740991L && value <= 9007199254740991L,
    "Native integer exceeds exact JSON range",
  )
  value.to_double().to_json()
}

///|
fn orm2_array_cell(text : String, element : Int) -> Json raise {
  let chars = text.iter().to_array()
  orm_assert(
    chars.length() >= 2 && chars[0] == '{' && chars[chars.length() - 1] == '}',
    "Only flat default-bound PostgreSQL arrays are supported",
  )
  let out : Array[Json] = []
  let end = chars.length() - 1
  let mut i = 1
  while i < end {
    let builder = StringBuilder()
    let quoted = chars[i] == '"'
    let mut escaped = false
    let mut closed = !quoted
    if quoted {
      i += 1
      while i < end {
        let ch = chars[i]
        i += 1
        if ch == '\\' {
          orm_assert(i < end, "Truncated quoted PostgreSQL array escape")
          builder.write_char(chars[i])
          i += 1
          escaped = true
        } else if ch == '"' {
          closed = true
          break
        } else {
          builder.write_char(ch)
        }
      }
      orm_assert(closed, "Unclosed PostgreSQL array item")
    } else {
      while i < end && chars[i] != ',' {
        let ch = chars[i]
        i += 1
        if ch == '\\' {
          orm_assert(i < end, "Truncated PostgreSQL array escape")
          builder.write_char(chars[i])
          i += 1
          escaped = true
        } else {
          orm_assert(
            ch != '"' && ch != '{' && ch != '}' && ch != ' ' &&
            ch != '\t' && ch != '\r' && ch != '\n',
            "Unsupported nested or whitespace PostgreSQL array form",
          )
          builder.write_char(ch)
        }
      }
    }
    let token = builder.to_string()
    orm_assert(quoted || !token.is_empty(), "Empty unquoted PostgreSQL array item")
    let cell = if !quoted && !escaped && token == "NULL" {
      Json::null()
    } else if element == 16 {
      match token {
        "t" => true.to_json()
        "f" => false.to_json()
        _ => fail("Invalid PostgreSQL boolean array item")
      }
    } else if element == 21 {
      let number = orm2_text_integer(token)
      let value = orm2_integer(number)
      orm_assert(value >= -32768L && value <= 32767L, "smallint array overflow")
      number
    } else {
      token.to_json()
    }
    out.push(cell)
    orm_assert(out.length() <= 512, "PostgreSQL array item budget")
    if i < end {
      orm_assert(chars[i] == ',', "PostgreSQL array delimiter required")
      i += 1
      orm_assert(i < end, "Trailing PostgreSQL array delimiter")
    }
  }
  out.to_json()
}

///|
fn orm2_decode_cell(raw : Json, oid : Int) -> Json raise {
  let value = orm_raw_text(raw)
  if value == Json::null() {
    return value
  }
  let text = orm_text(value)
  match oid {
    16 => match text {
      "t" => true.to_json()
      "f" => false.to_json()
      _ => fail("Invalid PostgreSQL boolean cell")
    }
    18 | 19 | 25 => value
    20 | 21 | 26 => {
      let number = orm2_text_integer(text)
      let integer = orm2_integer(number)
      if oid == 21 {
        orm_assert(integer >= -32768L && integer <= 32767L, "smallint overflow")
      } else if oid == 26 {
        orm_assert(integer >= 0L && integer <= 4294967295L, "OID overflow")
      }
      number
    }
    1000 => orm2_array_cell(text, 16)
    1003 | 1009 => orm2_array_cell(text, 25)
    1005 => orm2_array_cell(text, 21)
    3802 => {
      let parsed = guarded_json(text, limit=32768)
      ignore(orm_nodes(parsed, 0))
      parsed
    }
    _ => fail("Unsupported PostgreSQL control-result OID")
  }
}

///|
fn orm2_control(value : Json) -> OrmControl2 raise {
  let record = orm_exact(value, [
    "sourceSeq", "kind", "connection", "backendPid", "transaction", "sql", "parameters",
    "transactionStatusBefore", "transactionStatusAfter", "result",
  ])
  orm_equal(required(record, "kind", "control"), "control-query".to_json(), "control kind")
  let result = orm_exact(required(record, "result", "control"), [
    "status", "commandTag", "rowcount", "columns", "rows", "complete", "actualPGresult",
  ])
  orm_equal(required(result, "complete", "result"), true.to_json(), "complete control result")
  let actual = orm_exact(required(result, "actualPGresult", "result"), [
    "status", "commandTag", "commandTuples", "ntuples", "nfields", "fields", "rawRows",
  ])
  let rows = orm_array(required(result, "rows", "result"))
  let raw_rows = orm_array(required(actual, "rawRows", "PGresult"))
  let fields = orm_array(required(actual, "fields", "PGresult"))
  orm_assert(rows.length() <= 512 && fields.length() <= 32 && rows.length() * fields.length() <= 512, "Control row/column/cell limit")
  orm_equal(required(actual, "ntuples", "PGresult"), rows.length().to_json(), "raw/native tuple count")
  orm_equal(required(actual, "nfields", "PGresult"), fields.length().to_json(), "raw/native field count")
  orm_assert(raw_rows.length() == rows.length(), "raw/native row count")
  orm_equal(required(actual, "status", "PGresult"), required(result, "status", "result"), "control native/raw result status")
  orm_equal(orm_raw_text(required(actual, "commandTag", "PGresult")), required(result, "commandTag", "result"), "control actual command tag")
  let columns = required(result, "columns", "result")
  let mut raw_size = 0
  if fields.length() == 0 {
    orm_equal(columns, Json::null(), "command columns")
    orm_equal(required(actual, "status", "PGresult"), (1).to_json(), "COMMAND_OK")
    orm_assert(rows.is_empty(), "Command must not fabricate native rows")
  } else {
    orm_equal(required(actual, "status", "PGresult"), (2).to_json(), "TUPLES_OK")
    let descriptions = orm_array(columns)
    orm_assert(descriptions.length() == fields.length(), "Control columns/PG fields differ")
    for i, field in fields {
      let field = orm_exact(field, ["oid", "format", "typmod"])
      let description = orm_exact(descriptions[i], ["name", "typeCode"])
      ignore(orm_native_text(required(description, "name", "column"), 128))
      orm_equal(required(field, "format", "field"), (0).to_json(), "Control text field format")
      orm_equal(required(field, "typmod", "field"), (-1).to_json(), "Control catalog typmod")
      orm_equal(required(field, "oid", "field"), required(description, "typeCode", "column"), "Control raw/native OID")
      let oid = orm2_integer(required(field, "oid", "field"))
      orm_assert(oid == 16L || oid == 18L || oid == 19L || oid == 20L || oid == 21L || oid == 25L || oid == 26L || oid == 1000L || oid == 1003L || oid == 1005L || oid == 1009L || oid == 3802L, "Supported control field OID required even for empty results")
    }
    for i, row in rows {
      let row = orm_array(row)
      let wire = orm_array(raw_rows[i])
      orm_assert(row.length() == fields.length() && wire.length() == fields.length(), "Control row width")
      for j, cell in wire {
        let decoded_text = orm_raw_text(cell)
        if decoded_text != Json::null() {
          raw_size += orm_utf8_size(orm_text(decoded_text))
          orm_assert(raw_size <= 32768, "Aggregate control raw-cell byte limit")
        }
        let oid = orm2_integer(orm_get(fields[j], "oid"))
        orm_assert(oid <= 100000L && oid >= 0L, "Control OID range")
        orm_equal(orm2_decode_cell(cell, oid.to_int()), row[j], "Control native/raw cell disagreement")
      }
    }
  }
  let transaction = orm_native_text(required(record, "transaction", "control"), 256)
  let connection = orm_native_text(required(record, "connection", "control"), 256)
  orm_assert(!transaction.is_empty() && !connection.is_empty(), "Explicit setup transaction identity required")
  {
    seq: v3_capture_seq(required(record, "sourceSeq", "control"), "control sequence"),
    connection,
    backend: v3_capture_seq(required(record, "backendPid", "control"), "backend PID"),
    transaction,
    sql: orm_native_text(required(record, "sql", "control"), 65536),
    parameters: required(record, "parameters", "control"),
    rows,
    result,
    before: orm_text(required(record, "transactionStatusBefore", "control")),
    after: orm_text(required(record, "transactionStatusAfter", "control")),
  }
}

///|
fn orm2_journal(text : String) -> (Array[Json], Int, Array[OrmControl2], Array[OrmControl2]) raise {
  orm_assert(orm_utf8_size(text) <= 16777216 && text.has_suffix("\n"), "Complete bounded sourceSchema2 JSONL required")
  let lines = text.split("\n").to_array()
  orm_assert(lines.length() >= 6 && lines.length() <= 16385 && lines[lines.length() - 1].is_empty(), "SourceSchema2 record count")
  let records : Array[Json] = []
  let initial : Array[OrmControl2] = []
  let terminal : Array[OrmControl2] = []
  let prefix = StringBuilder()
  let mut installation = -1
  let mut finalizing = false
  for i in 0..<(lines.length() - 1) {
    let line = lines[i].to_owned()
    orm_assert(!line.is_empty() && orm_utf8_size(line) <= 131072, "SourceSchema2 record byte limit")
    let value = guarded_json(line, limit=131072)
    ignore(orm_nodes(value, 0))
    let obj = object_fields(value, "sourceSchema2 record")
    orm_equal(required(obj, "sourceSeq", "record"), (i + 1).to_json(), "SourceSchema2 sequence")
    let kind = orm_text(required(obj, "kind", "record"))
    if i == 0 {
      orm_equal(value, {
        "sourceSeq": 1, "kind": "header", "sourceSchema": "orm-source-draft/2",
        "controlSchema": "orm-control-query/1", "coreProofAccepted": false,
      }, "SourceSchema2 header")
    } else if i == lines.length() - 2 {
      orm_exact(value, ["sourceSeq", "kind", "prefixSha256", "sourceRecords"]) |> ignore
      orm_assert(kind == "seal", "Terminal sourceSchema2 seal required")
      orm_equal(required(obj, "sourceRecords", "seal"), i.to_json(), "SourceSchema2 seal count")
      orm_equal(required(obj, "prefixSha256", "seal"), v3_dislock_sha256(prefix.to_string()).to_json(), "Original sourceSchema2 prefix bytes")
    } else if i == lines.length() - 3 {
      orm_assert(installation >= 0 && kind == "final-effect-ledger", "Terminal sourceSchema2 final ledger required")
    } else if kind == "installation" {
      orm_assert(installation < 0 && !finalizing, "Duplicate/misplaced initialization")
      installation = i
    } else if kind == "control-query" {
      let control = orm2_control(value)
      if installation < 0 {
        initial.push(control)
      } else {
        finalizing = true
        terminal.push(control)
      }
    } else {
      orm_assert(installation >= 0 && !finalizing && (kind == "source-batch" || kind == "source-gap"), "Unknown or misplaced sourceSchema2 record")
    }
    records.push(value)
    prefix.write_string(line)
    prefix.write_string("\n")
  }
  orm_assert(installation > 1 && !initial.is_empty() && !terminal.is_empty(), "Both controlled provenance windows required")
  (records, installation, initial, terminal)
}

///|
fn orm2_take(cursor : OrmControlCursor2, sql : String, parameters : Json) -> OrmControl2 raise {
  orm_assert(cursor.at < cursor.controls.length(), "Missing actual control query")
  let value = cursor.controls[cursor.at]
  cursor.at += 1
  if value.sql != sql {
    fail("Exact fixed control SQL at sourceSeq=" + value.seq.to_string() +
      "; expectedSha256=" + v3_dislock_sha256(sql) +
      "; actualSha256=" + v3_dislock_sha256(value.sql))
  }
  orm_equal(value.parameters, parameters, "Exact control parameters")
  let first = cursor.controls[0]
  orm_assert(value.connection == first.connection && value.backend == first.backend && value.transaction == first.transaction, "Control window connection/backend/transaction mismatch")
  cursor.verified.push({ "sourceSeq": value.seq.to_double().to_json(), "sqlSha256": v3_dislock_sha256(sql).to_json() })
  value
}

///|
fn orm2_command(cursor : OrmControlCursor2, sql : String, parameters : Json, tag : String, count : Int?) -> OrmControl2 raise {
  let value = orm2_take(cursor, sql, parameters)
  orm_equal(required(value.result, "status", "result"), (1).to_json(), "Actual control COMMAND_OK")
  orm_equal(required(value.result, "commandTag", "result"), tag.to_json(), "Expected control ACK")
  let actual = object_fields(required(value.result, "actualPGresult", "result"), "PGresult")
  let expected_count = match count { Some(n) => n.to_json(); None => Json::null() }
  orm_equal(required(actual, "commandTuples", "PGresult"), expected_count, "Control command tuple count")
  orm_equal(required(value.result, "rowcount", "result"), match count { Some(n) => n.to_json(); None => (-1).to_json() }, "Control command rowcount")
  if sql == "BEGIN" {
    orm_assert(value.before == "IDLE" && value.after == "INTRANS", "Actual BEGIN transaction status")
  } else if sql == "COMMIT" {
    orm_assert(value.before == "INTRANS" && value.after == "IDLE", "Actual COMMIT transaction status")
  } else {
    orm_assert(value.before == "INTRANS" && value.after == "INTRANS", "Actual control in-transaction ACK")
  }
  value
}

///|
fn orm2_select(cursor : OrmControlCursor2, sql : String, parameters : Json, names : Array[String], oids : Array[Int]) -> OrmControl2 raise {
  let value = orm2_take(cursor, sql, parameters)
  orm_assert(value.before == "INTRANS" && value.after == "INTRANS", "Actual metadata query transaction status")
  orm_equal(required(value.result, "status", "result"), (2).to_json(), "Actual metadata TUPLES_OK")
  orm_equal(required(value.result, "commandTag", "result"), ("SELECT " + value.rows.length().to_string()).to_json(), "Actual metadata SELECT tag")
  orm_equal(required(value.result, "rowcount", "result"), value.rows.length().to_json(), "Actual metadata rowcount")
  let actual = object_fields(required(value.result, "actualPGresult", "result"), "PGresult")
  orm_equal(required(actual, "commandTuples", "PGresult"), value.rows.length().to_json(), "Actual metadata command tuples")
  let columns = orm_array(required(value.result, "columns", "result"))
  orm_assert(columns.length() == names.length() && names.length() == oids.length(), "Fixed control descriptor width")
  for i, name in names {
    orm_equal(columns[i], { "name": name.to_json(), "typeCode": oids[i].to_json() }, "Fixed control descriptor")
  }
  value
}
