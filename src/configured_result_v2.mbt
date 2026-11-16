///|
pub struct ConfiguredResultOptionsV2 {
  priv max_checks : Int32
  priv max_cell_bytes : Int32
  priv max_total_bytes : Int32
  priv max_delivery_records : Int32
  priv grammar_options : SQLVerificationOptionsV2
}

///|
pub fn configured_result_options_v2(
  max_checks~ : Int32 = 1000000,
  max_cell_bytes~ : Int32 = 65536,
  max_total_bytes~ : Int32 = 262144,
  max_delivery_records~ : Int32 = 1024,
  grammar_options~ : SQLVerificationOptionsV2 = sql_verification_options_v2(),
) -> ConfiguredResultOptionsV2 {
  {
    max_checks,
    max_cell_bytes,
    max_total_bytes,
    max_delivery_records,
    grammar_options,
  }
}

///|
pub struct ConfiguredResultCheckV2 {
  priv record : Json
}

///|
pub fn configured_result_check_v2_json(
  result : ConfiguredResultCheckV2,
) -> Json {
  v4_json_copy(result.record)
}

///|
priv struct ResultWorkV2 {
  options : ConfiguredResultOptionsV2
  mut checks : Int32
  mut bytes : Int32
}

///|
fn ResultWorkV2::charge(self : ResultWorkV2) -> Unit raise {
  if self.checks >= self.options.max_checks {
    fail("budget:V2-result-checks")
  }
  self.checks += 1
}

///|
fn ResultWorkV2::payload(self : ResultWorkV2, size : Int32) -> Unit raise {
  if size > self.options.max_cell_bytes ||
    size > self.options.max_total_bytes - self.bytes {
    fail("budget:V2-result-bytes")
  }
  self.bytes += size
}

///|
fn result_equal_v2(
  actual : Json,
  expected : Json,
  label : String,
) -> Unit raise {
  if sql_canonical_v1(actual) != sql_canonical_v1(expected) {
    fail("mismatch:V2-" + label)
  }
}

///|
fn result_bytes_v2(work : ResultWorkV2, value : Json) -> String raise {
  let encoded = sql_string_v1(value)
  if encoded.length() > (work.options.max_cell_bytes + 2) / 3 * 4 {
    fail("budget:V2-base64-cell")
  }
  let bytes = @base64.decode(encoded[:], ignore_whitespace=false)
  if @base64.encode(bytes[:]) != encoded {
    fail("mismatch:V2-base64-canonical")
  }
  work.payload(bytes.length())
  @utf8.decode(bytes[:], ignore_bom=false)
}

///|
fn result_uint_v2(value : Json, ceiling : String) -> String raise {
  let text = sql_number_text_v1(value)
  if !sql_digits_v1(text) ||
    text.length() > ceiling.length() ||
    (text.length() == ceiling.length() && text > ceiling) {
    fail("mismatch:V2-unsigned-integer")
  }
  text
}

///|
fn result_note_v2(value : Json) -> Int32 raise {
  let number = fetch_number_v1(value, 100000000)
  if number == 0 {
    fail("mismatch:V2-positive-note")
  }
  number
}

///|
fn result_oid_v2(kind : String, value : Json) -> Int32 raise {
  let oid = fetch_number_v1(value, 100000000)
  if !((kind == "int64" && [20, 21, 23].contains(oid)) ||
    (kind == "bool" && oid == 16) ||
    (kind == "text" && [25, 1043].contains(oid)) ||
    (kind == "uuid" && oid == 2950)) {
    fail("unsupported:V2-native-OID")
  }
  oid
}

///|
fn result_native_cell_v2(
  work : ResultWorkV2,
  raw : Json,
  kind : String,
  oid : Int32,
  text_limit : Int32,
) -> Json raise {
  if raw == Json::null() {
    fail("unsupported:V2-NULL-cell")
  }
  let text = result_bytes_v2(work, raw)
  if text.contains("\u0000") {
    fail("mismatch:V2-native-NUL")
  }
  if kind == "uuid" {
    let identity = sql_uuid_identity_v2(Json(text))
    if text != identity {
      fail("mismatch:V2-native-UUID-canonical")
    }
    { "type": "uuid", "value": Json(identity) }
  } else if kind == "int64" {
    let decimal = sql_decimal_v1(text)
    if decimal != text {
      fail("mismatch:V2-native-integer-canonical")
    }
    if oid == 21 || oid == 23 {
      let negative = text.has_prefix("-")
      let magnitude = if negative { text[1:].to_owned() } else { text }
      let bound = if oid == 21 {
        if negative {
          "32768"
        } else {
          "32767"
        }
      } else if negative {
        "2147483648"
      } else {
        "2147483647"
      }
      if magnitude.length() > bound.length() ||
        (magnitude.length() == bound.length() && magnitude > bound) {
        fail("mismatch:V2-native-integer-OID-width")
      }
    }
    { "type": "int64", "value": Json(decimal) }
  } else if kind == "bool" {
    if text != "t" && text != "f" {
      fail("mismatch:V2-native-boolean")
    }
    { "type": "bool", "value": Json(text == "t") }
  } else {
    if orm_utf8_size(text) > text_limit {
      fail("budget:V2-configured-text")
    }
    { "type": "text", "value": Json(text) }
  }
}

///|
fn result_delivered_cell_v2(
  work : ResultWorkV2,
  raw : Json,
  kind : String,
  text_limit : Int32,
) -> Json raise {
  let cell = orm_exact(raw, ["pythonType", "value"])
  let expected = match kind {
    "int64" => "builtins.int"
    "bool" => "builtins.bool"
    "text" => "builtins.str"
    "uuid" => "uuid.UUID"
    _ => fail("unsupported:V2-configured-type")
  }
  if cell.at("pythonType") != Json(expected) {
    fail("unsupported:V2-custom-scalar-decoder")
  }
  let raw_value = cell.at("value")
  if kind == "bool" {
    return sql_typed_value_v2(raw_value, kind, text_limit)
  }
  let text = sql_string_v1(raw_value)
  if !sql_well_formed_utf16_v1(text) || text.contains("\u0000") {
    fail("mismatch:V2-delivery-Unicode")
  }
  work.payload(orm_utf8_size(text))
  if kind == "int64" {
    let decimal = sql_decimal_v1(text)
    if decimal != text {
      fail("mismatch:V2-delivered-integer-canonical")
    }
    { "type": "int64", "value": Json(decimal) }
  } else if kind == "uuid" {
    let identity = sql_uuid_identity_v2(raw_value)
    if identity != text {
      fail("mismatch:V2-UUID-object-observation")
    }
    { "type": "uuid", "value": Json(identity) }
  } else {
    sql_typed_value_v2(raw_value, kind, text_limit)
  }
}

///|
// Only the independently rebuilt descriptor and typed original bindings enter here.
fn result_point_key_v2(
  grammar : Map[String, Json],
  descriptor : Map[String, Json],
) -> Json raise {
  let reference = descriptor.at("keyReference")
  let fields = object_fields(reference, "V2 independent key reference")
  if fields.at("kind") == Json("literal") {
    return { "type": fields.at("type"), "value": fields.at("value") }
  }
  for binding in orm_array(grammar.at("bindings")) {
    let fields = object_fields(binding, "V2 independent binding")
    if sql_canonical_v1(fields.at("reference")) == sql_canonical_v1(reference) {
      return fields.at("value")
    }
  }
  fail("mismatch:V2-independent-point-key-binding")
}

///|
pub fn verify_configured_result_v2(
  config : SQLConfigV2,
  execution : Json,
  native : Json,
  deliveries : Json,
  options~ : ConfiguredResultOptionsV2 = configured_result_options_v2(),
) -> ConfiguredResultCheckV2 {
  let work : ResultWorkV2 = { options, checks: 0, bytes: 0, }
  let mut grammar : Json = Json::null()
  let mut reason = ""
  let mut operation = ""
  let mut tuple_result = false
  let mut native_verified = false
  let mut command_verified = false
  let mut prefix_verified = false
  let mut complete = false
  let mut exhaustion_observed = false
  let mut meaningful_fetch = false
  let mut delivered = 0
  let mut total = 0
  let mut affected : Json = Json::null()
  let mut point_key : Json = Json::null()
  let mut returned_key_observed = false
  let mut returned_key_verified = false
  let decoded : Array[Json] = []
  let delivered_values : Array[Json] = []
  let status = try {
    if options.max_checks < 0 ||
      options.max_checks > 1000000 ||
      options.max_cell_bytes < 0 ||
      options.max_cell_bytes > 65536 ||
      options.max_total_bytes < 0 ||
      options.max_total_bytes > 1048576 ||
      options.max_delivery_records < 0 ||
      options.max_delivery_records > 1024 {
      fail("invalid:V2-result-options")
    }
    work.charge()
    let e = orm_exact(execution, [
      "format", "connection", "cursor", "tx", "statementSeq", "executionNoteSeq",
      "sql", "parameters", "candidate", "sqlRewritten", "success", "decoderContract",
    ])
    result_equal_v2(
      e.at("format"),
      Json("moontxnwitness-configured-execution/v2"),
      "execution-format",
    )
    result_equal_v2(e.at("sqlRewritten"), Json(false), "original-SQL-required")
    result_equal_v2(
      e.at("decoderContract"),
      Json("psycopg-default-text-scalars/v2"),
      "decoder-contract",
    )
    for name in ["connection", "cursor", "tx"] {
      let value = sql_string_v1(e.at(name))
      if value.is_empty() ||
        !sql_well_formed_utf16_v1(value) ||
        value.contains("\u0000") ||
        orm_utf8_size(value) > 256 {
        fail("mismatch:V2-execution-identity")
      }
    }
    let _ = result_note_v2(e.at("statementSeq"))
    let execution_note = result_note_v2(e.at("executionNoteSeq"))
    grammar = sql_candidate_check_v2_json(
      verify_sql_candidate_v2(
        config,
        sql_string_v1(e.at("sql")),
        e.at("parameters"),
        e.at("candidate"),
        options=options.grammar_options,
      ),
    )
    let g = object_fields(grammar, "V2 grammar")
    if g.at("status") != Json("matched") {
      if g.at("status") == Json("unknown") {
        fail("unsupported:V2-grammar-incomplete")
      }
      fail("mismatch:V2-independent-grammar")
    }
    let descriptor = object_fields(g.at("descriptor"), "V2 descriptor")
    point_key = result_point_key_v2(g, descriptor)
    operation = sql_string_v1(descriptor.at("operation"))
    let projections = orm_array(
      descriptor.at(
        if operation == "select" {
          "projections"
        } else {
          "returning"
        },
      ),
    )
    tuple_result = operation == "select" || !projections.is_empty()
    if native == Json::null() {
      fail("unsupported:V2-native-missing")
    }
    let n = orm_exact(native, [
      "format", "resultId", "connection", "cursor", "tx", "statementSeq", "executionNoteSeq",
      "nativeNoteSeq", "sqlSha256", "originalParametersSha256", "status", "clientEncodingBase64",
      "commandStatusBase64", "commandTuples", "fields", "rows",
    ])
    result_equal_v2(
      n.at("format"),
      Json("moontxnwitness-native-result/v2"),
      "native-format",
    )
    for
      name in ["connection", "cursor", "tx", "statementSeq", "executionNoteSeq"] {
      result_equal_v2(n.at(name), e.at(name), "native-execution-identity")
    }
    let native_note = result_note_v2(n.at("nativeNoteSeq"))
    if native_note <= execution_note {
      fail("mismatch:V2-native-note-order")
    }
    let result_id = sql_string_v1(n.at("resultId"))
    if result_id.is_empty() ||
      orm_utf8_size(result_id) > 256 ||
      !sql_well_formed_utf16_v1(result_id) ||
      result_id.contains("\u0000") {
      fail("mismatch:V2-result-id")
    }
    result_equal_v2(n.at("sqlSha256"), g.at("sqlSha256"), "native-original-SQL")
    result_equal_v2(
      n.at("originalParametersSha256"),
      g.at("originalParametersSha256"),
      "native-original-bindings",
    )
    result_equal_v2(
      Json(result_bytes_v2(work, n.at("clientEncodingBase64"))),
      Json("UTF8"),
      "native-encoding",
    )
    if n.at("status") != Json(1) && n.at("status") != Json(2) {
      fail("unsupported:V2-native-status")
    }
    result_equal_v2(
      n.at("status"),
      Json(if tuple_result { 2 } else { 1 }),
      "native-status-shape",
    )
    result_equal_v2(e.at("success"), Json(true), "execution-native-success")
    let fields = orm_array(n.at("fields"))
    let raw_rows = orm_array(n.at("rows"))
    total = raw_rows.length()
    if total > 1 {
      fail("unsupported:V2-point-native-row-count")
    }
    if fields.length() != projections.length() || fields.length() > 17 {
      fail("mismatch:V2-native-field-count")
    }
    let command_tag = result_bytes_v2(work, n.at("commandStatusBase64"))
    let prefix = if operation == "insert" {
      "INSERT 0 "
    } else {
      operation.to_upper() + " "
    }
    if !command_tag.has_prefix(prefix) {
      fail("mismatch:V2-command-tag-operation")
    }
    let command_count = command_tag[prefix.length():].to_owned()
    if !sql_digits_v1(command_count) ||
      sql_decimal_v1(command_count) != command_count {
      fail("mismatch:V2-command-tag-count")
    }
    if command_count != "0" && command_count != "1" {
      fail("unsupported:V2-command-point-count")
    }
    // psycopg 3.3.6 exposes command_tuples as an int/None getter, not raw bytes.
    let getter = orm_exact(n.at("commandTuples"), ["pythonType", "value"])
    if getter.at("pythonType") != Json("builtins.int") {
      fail("unsupported:V2-command-tuples-getter-type")
    }
    let getter_count = sql_string_v1(getter.at("value"))
    work.payload(orm_utf8_size(getter_count))
    result_equal_v2(
      Json(getter_count),
      Json(command_count),
      "command-tag-getter-count",
    )
    if tuple_result && command_count != total.to_string() {
      fail("mismatch:V2-command-native-row-count")
    }
    if operation != "select" {
      affected = Json(command_count)
    }
    command_verified = true
    let kinds : Array[String] = []
    let oids : Array[Int32] = []
    for index, raw_field in fields {
      work.charge()
      let field = orm_exact(raw_field, [
        "nameBase64", "oid", "format", "typmod", "tableOid", "tableColumn",
      ])
      let projection = object_fields(projections[index], "V2 projection")
      let name = result_bytes_v2(work, field.at("nameBase64"))
      result_equal_v2(
        Json(name),
        projection.at("outputName"),
        "native-output-name-position",
      )
      if field.at("format") != Json(0) {
        fail("unsupported:V2-native-binary-format")
      }
      let column_name = sql_string_v1(projection.at("column"))
      let column = config.parser_config.tables[0].columns
        .iter()
        .find_first(c => c.name == column_name)
        .unwrap()
      kinds.push(column.kind)
      oids.push(result_oid_v2(column.kind, field.at("oid")))
      let _ = result_uint_v2(field.at("tableOid"), "4294967295")
      let _ = result_uint_v2(field.at("tableColumn"), "32767")
      let typmod = sql_number_text_v1(field.at("typmod"))
      if typmod != "-1" {
        let _ = result_uint_v2(field.at("typmod"), "2147483647")
      }
    }
    for raw_row in raw_rows {
      let cells = orm_array(raw_row)
      if cells.length() != fields.length() {
        fail("mismatch:V2-native-row-arity")
      }
      let values : Array[Json] = []
      for index, cell in cells {
        work.charge()
        values.push(
          result_native_cell_v2(
            work,
            cell,
            kinds[index],
            oids[index],
            config.parser_config.limits.at("max_text_bytes"),
          ),
        )
      }
      decoded.push(Json(values))
    }
    for index, projection in projections {
      if object_fields(projection, "V2 projection").at("column") ==
        Json(config.parser_config.tables[0].key) {
        for row in decoded {
          work.charge()
          returned_key_observed = true
          result_equal_v2(
            orm_array(row)[index],
            point_key,
            "returned-original-point-key",
          )
          returned_key_verified = true
        }
      }
    }
    native_verified = true
    let batches = orm_array(deliveries)
    if batches.length() > options.max_delivery_records {
      fail("budget:V2-delivery-records")
    }
    if !tuple_result {
      if !fields.is_empty() || !raw_rows.is_empty() || !batches.is_empty() {
        fail("mismatch:V2-command-only-result")
      }
      complete = true
      "matched"
    } else {
      let mut previous_note = native_note
      for batch in batches {
        work.charge()
        let d = orm_exact(batch, [
          "format", "resultId", "connection", "cursor", "tx", "statementSeq", "nativeNoteSeq",
          "deliveryNoteSeq", "method", "resultPythonType", "requestedSize", "effectiveSize",
          "start", "rows", "exhaustedObserved",
        ])
        result_equal_v2(
          d.at("format"),
          Json("moontxnwitness-actual-delivery/v2"),
          "delivery-format",
        )
        for
          name in [
            "resultId", "connection", "cursor", "tx", "statementSeq", "nativeNoteSeq",
          ] {
          result_equal_v2(d.at(name), n.at(name), "delivery-native-identity")
        }
        let note = result_note_v2(d.at("deliveryNoteSeq"))
        if note <= previous_note {
          fail("mismatch:V2-delivery-note-order")
        }
        previous_note = note
        if fetch_number_v1(d.at("start"), 1) != delivered {
          fail("mismatch:V2-delivery-position")
        }
        let delivery_method = sql_string_v1(d.at("method"))
        if ![
            "fetchone", "fetchmany", "fetchall", "iterator-next", "iterator-stop",
          ].contains(delivery_method) {
          fail("unsupported:V2-delivery-method")
        }
        let rows = orm_array(d.at("rows"))
        let expected_result_type = if delivery_method == "fetchall" ||
          delivery_method == "fetchmany" {
          "builtins.list"
        } else if delivery_method == "iterator-stop" {
          "builtins.StopIteration"
        } else if rows.is_empty() {
          "builtins.NoneType"
        } else {
          "builtins.tuple"
        }
        if d.at("resultPythonType") != Json(expected_result_type) {
          fail("unsupported:V2-delivery-result-type")
        }
        let meaningful = if delivery_method == "fetchmany" {
          let size = fetch_number_v1(d.at("effectiveSize"), 256)
          if d.at("requestedSize") != Json::null() &&
            d.at("requestedSize") != Json(0) {
            result_equal_v2(
              d.at("requestedSize"),
              Json(size),
              "fetchmany-request-size",
            )
          }
          if rows.length() > size {
            fail("mismatch:V2-fetchmany-size")
          }
          size > 0
        } else {
          result_equal_v2(
            d.at("requestedSize"),
            Json::null(),
            "non-fetchmany-request",
          )
          result_equal_v2(
            d.at("effectiveSize"),
            Json::null(),
            "non-fetchmany-size",
          )
          if delivery_method == "fetchone" && rows.length() > 1 {
            fail("mismatch:V2-fetchone-size")
          }
          if delivery_method == "iterator-next" && rows.length() != 1 {
            fail("mismatch:V2-iterator-next")
          }
          if delivery_method == "iterator-stop" && !rows.is_empty() {
            fail("mismatch:V2-iterator-stop")
          }
          true
        }
        if delivered + rows.length() > total ||
          (exhaustion_observed && !rows.is_empty()) {
          fail("mismatch:V2-rows-after-native-end")
        }
        for raw_row in rows {
          work.charge()
          let row = orm_exact(raw_row, ["pythonType", "cells"])
          if row.at("pythonType") != Json("builtins.tuple") {
            fail("unsupported:V2-custom-row-factory")
          }
          let cells = orm_array(row.at("cells"))
          if cells.length() != fields.length() {
            fail("mismatch:V2-delivered-row-arity")
          }
          let values : Array[Json] = []
          for index, cell in cells {
            work.charge()
            values.push(
              result_delivered_cell_v2(
                work,
                cell,
                kinds[index],
                config.parser_config.limits.at("max_text_bytes"),
              ),
            )
          }
          result_equal_v2(
            Json(values),
            decoded[delivered],
            "native-delivered-type-value-position",
          )
          delivered_values.push(Json(values))
          delivered += 1
        }
        let observed = match d.at("exhaustedObserved") {
          True => true
          False => false
          _ => fail("mismatch:V2-exhaustion-boolean")
        }
        if observed && meaningful && delivered != total {
          fail("mismatch:V2-premature-exhaustion")
        }
        if delivery_method == "fetchall" && delivered != total {
          fail("mismatch:V2-fetchall-short")
        }
        if meaningful {
          meaningful_fetch = true
          exhaustion_observed = exhaustion_observed || observed
        }
      }
      prefix_verified = !batches.is_empty()
      complete = delivered == total && meaningful_fetch
      if complete {
        "matched"
      } else {
        "partial"
      }
    }
  } catch {
    error => {
      reason = error.to_string()
      if reason.contains("budget:") {
        "unknown"
      } else if reason.contains("mismatch:") {
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
      "format": "moontxnwitness-configured-result-verification/v2",
      "semanticContract": "original-point-CRUD-native-delivery-consistency/v2",
      "algorithm": "moonbit-native-point-result-delivery-2",
      "status": Json(status),
      "valid": Json(status == "matched"),
      "completeObservationVerified": Json(status == "matched" && complete),
      "nativeResultVerified": Json(native_verified),
      "commandObservationVerified": Json(
        status == "matched" && command_verified,
      ),
      "deliveredPrefixVerified": Json(prefix_verified),
      "completeFetchVerified": Json(
        status == "matched" && tuple_result && complete,
      ),
      "exhaustedObserved": Json(exhaustion_observed),
      "meaningfulFetchObserved": Json(meaningful_fetch),
      "operation": Json(operation),
      "nativeRows": Json(total),
      "deliveredRows": Json(delivered),
      "affectedRowsObservation": affected,
      "pointKeyIdentity": point_key,
      "returnedKeyObserved": Json(returned_key_observed),
      "returnedKeyConsistencyVerified": Json(returned_key_verified),
      "grammar": grammar,
      "decodedNativeRows": Json(decoded),
      "verifiedDeliveredRows": Json(delivered_values),
      "nativeObservation": v4_json_copy(native),
      "deliveryObservations": v4_json_copy(deliveries),
      "captureFactsProduced": false,
      "sourceFactsProduced": false,
      "sourceAuthenticated": false,
      "catalogVerified": false,
      "sourceWindowVerified": false,
      "sourceColumnMappingVerified": false,
      "modelCoverageAccepted": false,
      "commitVerified": false,
      "committedWriteEffectVerified": false,
      "moonbitProjectionVerified": false,
      "gaps": [
        Json(
          if reason.is_empty() {
            "observer_catalog_source_window_read_version_and_commit_unproven"
          } else {
            reason
          },
        ),
        "source_and_model_admission_not_performed",
      ],
      "execution": {
        "counterContract": "native-point-field-cell-delivery-checks-2",
        "checks": Json(work.checks),
        "payloadBytes": Json(work.bytes),
        "limits": {
          "maxChecks": Json(options.max_checks),
          "maxCellBytes": Json(options.max_cell_bytes),
          "maxTotalBytes": Json(options.max_total_bytes),
          "maxDeliveryRecords": Json(options.max_delivery_records),
          "maxNativeRows": 1,
          "maxNativeColumns": 17,
        },
      },
      "scope": "consistency of supplied original SQL, libpq text buffer and actual default-scalar delivery observations only; not observer authentication, source-column mapping, absence/version/conditional facts, commit effects or model analysis",
    },
  }
}
