///|
pub struct ConfiguredFetchCheckV1 {
  priv record : Json
}

///|
pub fn configured_fetch_check_v1_json(result : ConfiguredFetchCheckV1) -> Json {
  v4_json_copy(result.record)
}

///|
priv struct FetchWorkV1 {
  limit : Int32
  mut checks : Int32
}

///|
fn FetchWorkV1::charge(self : FetchWorkV1) -> Unit raise {
  if self.checks >= self.limit {
    fail("budget:fetch-checks")
  }
  self.checks += 1
}

///|
fn fetch_number_v1(value : Json, maximum : Int32) -> Int32 raise {
  let digits = sql_number_text_v1(value)
  if !sql_digits_v1(digits) || digits.length() > 9 {
    fail("mismatch:unsigned-integer")
  }
  let mut number = 0
  for c in digits.to_array() {
    number = number * 10 + c.to_int() - 48
  }
  if number > maximum {
    fail("mismatch:integer-limit")
  }
  number
}

///|
fn fetch_equal_v1(a : Json, b : Json, label : String) -> Unit raise {
  if sql_canonical_v1(a) != sql_canonical_v1(b) {
    fail("mismatch:" + label)
  }
}

///|
fn fetch_cell_v1(
  raw : Json,
  kind : String,
  oid : Int32,
  format : Int32,
) -> Json raise {
  if raw == Json::null() {
    fail("unsupported:NULL-cell")
  }
  if format != 0 {
    fail("unsupported:binary-cell-format")
  }
  let encoded = sql_string_v1(raw)
  if encoded.length() > 65536 {
    fail("budget:cell-bytes")
  }
  let bytes = @base64.decode(encoded[:], ignore_whitespace=false)
  if @base64.encode(bytes[:]) != encoded {
    fail("mismatch:noncanonical-base64")
  }
  let value = @utf8.decode(bytes[:], ignore_bom=false)
  if kind == "int64" && (oid == 20 || oid == 21 || oid == 23) {
    let decimal = sql_decimal_v1(value)
    if decimal != value {
      fail("mismatch:noncanonical-native-integer")
    }
    { "type": "int64", "value": Json(decimal) }
  } else if kind == "bool" && oid == 16 {
    if value != "t" && value != "f" {
      fail("mismatch:native-boolean")
    }
    { "type": "bool", "value": Json(value == "t") }
  } else if kind == "text" && (oid == 25 || oid == 1043) {
    { "type": "text", "value": Json(value) }
  } else {
    fail("unsupported:native-OID-configuration")
  }
}

///|
pub fn verify_configured_fetch_v1(
  config : SQLConfigV1,
  execution : Json,
  native : Json,
  deliveries : Json,
  max_checks~ : Int32 = 1000000,
  grammar_options~ : SQLVerificationOptionsV1 = sql_verification_options_v1(),
) -> ConfiguredFetchCheckV1 {
  let work : FetchWorkV1 = { limit: max_checks, checks: 0, }
  let mut grammar : Json = Json::null()
  let mut reason = ""
  let mut delivered = 0
  let mut total = 0
  let mut complete = false
  let mut verified_prefix = false
  let mut stored_observations = 0
  let status = try {
    if max_checks < 0 || max_checks > 1000000 {
      fail("invalid:caller-fetch-budget")
    }
    work.charge()
    let e = orm_exact(execution, [
      "format", "connection", "cursor", "tx", "statementSeq", "sql", "parameters",
      "candidate", "sourceFactsProduced",
    ])
    fetch_equal_v1(
      e.at("format"),
      Json("moontxnwitness-configured-execution/v1"),
      "execution-format",
    )
    fetch_equal_v1(
      e.at("sourceFactsProduced"),
      Json(false),
      "unproved-source-facts",
    )
    for field in ["connection", "cursor", "tx"] {
      let text = sql_string_v1(e.at(field))
      if text.is_empty() || text.length() > 256 {
        fail("mismatch:execution-identity")
      }
    }
    let _ = fetch_number_v1(e.at("statementSeq"), 100000000)
    grammar = sql_candidate_check_v1_json(
      verify_sql_candidate_v1(
        config,
        sql_string_v1(e.at("sql")),
        e.at("parameters"),
        e.at("candidate"),
        options=grammar_options,
      ),
    )
    let g = object_fields(grammar, "grammar")
    if g.at("valid") != Json(true) {
      if g.at("status") == Json("unknown") {
        fail("unsupported:independent-SQL-grammar-incomplete")
      }
      fail("mismatch:independent-SQL-binding")
    }
    let descriptor = object_fields(g.at("descriptor"), "descriptor")
    if descriptor.at("operation") != Json("select") {
      fail("unsupported:only-original-SELECT-delivery")
    }
    let n = orm_exact(native, [
      "format", "resultId", "connection", "cursor", "tx", "statementSeq", "executionNoteSeq",
      "sqlSha256", "parametersSha256", "status", "fields", "rows", "storedColumnDeclarations",
      "sourceFactsProduced",
    ])
    fetch_equal_v1(
      n.at("format"),
      Json("moontxnwitness-native-result/v1"),
      "native-format",
    )
    fetch_equal_v1(
      n.at("sourceFactsProduced"),
      Json(false),
      "native-source-claim",
    )
    fetch_equal_v1(n.at("status"), Json(2), "native-status")
    for name in ["connection", "cursor", "tx", "statementSeq"] {
      fetch_equal_v1(n.at(name), e.at(name), "execution-native-identity")
    }
    let result_id = sql_string_v1(n.at("resultId"))
    if result_id.is_empty() || result_id.length() > 256 {
      fail("mismatch:result-identity")
    }
    let _ = fetch_number_v1(n.at("executionNoteSeq"), 100000000)
    let candidate = object_fields(g.at("expectedCandidate"), "candidate")
    for name in ["sqlSha256", "parametersSha256"] {
      fetch_equal_v1(n.at(name), candidate.at(name), "native-source-digest")
    }
    let projections = orm_array(descriptor.at("projections"))
    let fields = orm_array(n.at("fields"))
    let raw_rows = orm_array(n.at("rows"))
    total = raw_rows.length()
    if fields.is_empty() ||
      fields.length() > 128 ||
      fields.length() != projections.length() ||
      total > 256 ||
      total * fields.length() > 2048 {
      fail("unsupported:native-result-dimensions")
    }
    let table = object_fields(descriptor.at("table"), "table")
    let columns = orm_array(table.at("columns"))
    let kinds : Array[String] = []
    let oids : Array[Int32] = []
    let formats : Array[Int32] = []
    let physical : Array[Bool] = []
    for index, value in fields {
      work.charge()
      let field = orm_exact(value, [
        "name", "oid", "format", "typmod", "tableOid", "tableColumn",
      ])
      let projection = orm_exact(projections[index], ["column", "outputName"])
      fetch_equal_v1(
        field.at("name"),
        projection.at("outputName"),
        "native-output-name",
      )
      let column_name = sql_string_v1(projection.at("column"))
      let mut kind = ""
      for column in columns {
        let c = object_fields(column, "column")
        if c.at("name") == Json(column_name) {
          kind = sql_string_v1(c.at("type"))
        }
      }
      if kind.is_empty() {
        fail("mismatch:configured-projection")
      }
      kinds.push(kind)
      oids.push(fetch_number_v1(field.at("oid"), 100000000))
      formats.push(fetch_number_v1(field.at("format"), 1))
      let _ = sql_number_text_v1(field.at("typmod"))
      let table_oid = fetch_number_v1(field.at("tableOid"), 100000000)
      let column_number = fetch_number_v1(field.at("tableColumn"), 100000000)
      physical.push(table_oid > 0 && column_number > 0)
    }
    let decoded : Array[Json] = []
    for raw in raw_rows {
      let cells = orm_array(raw)
      if cells.length() != fields.length() {
        fail("mismatch:native-row-arity")
      }
      let values : Array[Json] = []
      for index, cell in cells {
        work.charge()
        values.push(
          fetch_cell_v1(cell, kinds[index], oids[index], formats[index]),
        )
      }
      decoded.push(Json(values))
    }
    let declared = orm_array(n.at("storedColumnDeclarations"))
    let names : Array[String] = []
    for value in declared {
      work.charge()
      let name = sql_string_v1(value)
      if names.contains(name) {
        fail("mismatch:duplicate-stored-column-declaration")
      }
      names.push(name)
      let mut configured = false
      for column in columns {
        if object_fields(column, "column").at("name") == value {
          configured = true
        }
      }
      if !configured {
        fail("mismatch:unconfigured-stored-column")
      }
      for index, projection in projections {
        if object_fields(projection, "projection").at("column") == value &&
          physical[index] {
          stored_observations += total
        }
      }
    }
    let batches = orm_array(deliveries)
    if batches.length() > 1024 {
      fail("budget:delivery-records")
    }
    let mut native_note : Json = Json::null()
    for batch in batches {
      work.charge()
      let d = orm_exact(batch, [
        "format", "resultId", "statementSeq", "connection", "cursor", "tx", "nativeNoteSeq",
        "method", "start", "rows", "complete", "sourceFactsProduced",
      ])
      fetch_equal_v1(
        d.at("format"),
        Json("moontxnwitness-actual-delivery/v1"),
        "delivery-format",
      )
      fetch_equal_v1(
        d.at("sourceFactsProduced"),
        Json(false),
        "delivery-source-claim",
      )
      for name in ["resultId", "statementSeq", "connection", "cursor", "tx"] {
        fetch_equal_v1(d.at(name), n.at(name), "delivery-native-identity")
      }
      let note = fetch_number_v1(d.at("nativeNoteSeq"), 100000000)
      if native_note == Json::null() {
        native_note = Json(note)
      } else {
        fetch_equal_v1(native_note, Json(note), "native-note-reference")
      }
      let delivery_method = sql_string_v1(d.at("method"))
      if !["fetchone", "fetchmany", "fetchall", "adapter-delivered"].contains(
          delivery_method,
        ) {
        fail("unsupported:delivery-method")
      }
      if fetch_number_v1(d.at("start"), 256) != delivered {
        fail("mismatch:delivery-position")
      }
      let rows = orm_array(d.at("rows"))
      if delivery_method == "fetchone" && rows.length() > 1 {
        fail("mismatch:fetchone-count")
      }
      if delivered + rows.length() > total || (complete && !rows.is_empty()) {
        fail("mismatch:rows-after-exhaustion")
      }
      for row in rows {
        work.charge()
        fetch_equal_v1(row, decoded[delivered], "native-delivered-value")
        delivered += 1
      }
      let exhausted = match d.at("complete") {
        True => true
        False => false
        _ => fail("mismatch:delivery-complete-boolean")
      }
      if exhausted && delivered != total {
        fail("mismatch:premature-result-exhaustion")
      }
      if delivery_method == "fetchall" && !exhausted {
        fail("mismatch:fetchall-incomplete")
      }
      complete = exhausted || complete
    }
    verified_prefix = !batches.is_empty()
    if complete {
      "matched"
    } else {
      "partial"
    }
  } catch {
    error => {
      reason = error.to_string()
      if reason.contains("mismatch:") {
        "mismatch"
      } else if reason.contains("invalid:") {
        "invalid"
      } else {
        "unknown"
      }
    }
  }
  {
    record: {
      "format": "moontxnwitness-configured-fetch-verification/v1",
      "semanticContract": "original-select-native-delivery/v1",
      "algorithm": "moonbit-native-delivery-consistency-1",
      "status": Json(status),
      "valid": Json(status == "matched" || status == "partial"),
      "deliveredPrefixVerified": Json(verified_prefix),
      "completeFetchVerified": Json(complete && status == "matched"),
      "sourceFactsProduced": false,
      "sourceAuthenticated": false,
      "catalogVerified": false,
      "sourceWindowVerified": false,
      "isolationModelChecked": false,
      "storedColumnObservations": Json(stored_observations),
      "nativeRows": Json(total),
      "deliveredRows": Json(delivered),
      "grammar": grammar,
      "gaps": if reason.is_empty() {
        [
          "read_version_unproven", "catalog_installation_and_writer_window_unproven",
        ]
      } else {
        [
          Json(reason),
          "read_version_unproven",
          "catalog_installation_and_writer_window_unproven",
        ]
      },
      "execution": {
        "counterContract": "native-field-cell-delivery-step-checks-1",
        "checks": Json(work.checks),
        "limits": {
          "maxChecks": Json(max_checks),
          "maxNativeRows": 256,
          "maxNativeColumns": 128,
          "maxNativeCells": 2048,
          "maxDeliveryRecords": 1024,
        },
      },
      "scope": "independent consistency of supplied original SELECT, configured bindings, native buffer and actual delivery claims; hashes do not authenticate observers or establish version provenance",
    },
  }
}
