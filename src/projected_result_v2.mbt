///|
pub struct ProjectedResultOptionsV2 {
  priv result_options : ConfiguredResultOptionsV2
  priv projection_budget : PointProjectionVerificationOptionsV2
}

///|
pub fn projected_result_options_v2(
  max_checks~ : Int32 = 1000000,
  max_cell_bytes~ : Int32 = 65536,
  max_total_bytes~ : Int32 = 262144,
  max_delivery_records~ : Int32 = 1024,
  projection_budget~ : PointProjectionVerificationOptionsV2 = point_projection_verification_options_v2(),
) -> ProjectedResultOptionsV2 {
  {
    result_options: configured_result_options_v2(
      max_checks~,
      max_cell_bytes~,
      max_total_bytes~,
      max_delivery_records~,
    ),
    projection_budget,
  }
}

///|
pub struct ProjectedResultCheckV2 {
  priv record : Json
}

///|
pub fn projected_result_check_v2_json(check : ProjectedResultCheckV2) -> Json {
  v4_json_copy(check.record)
}

///|
fn projected_column_kind_v2(
  config : SQLConfigV2,
  name : String,
) -> String raise {
  match
    config.parser_config.tables[0].columns
    .iter()
    .find_first(c => c.name == name) {
    Some(column) => column.kind
    None => fail("mismatch:projected-column-outside-config")
  }
}

///|
fn projected_identity_v2(raw : Json) -> Unit raise {
  let value = sql_string_v1(raw)
  if value.is_empty() ||
    orm_utf8_size(value) > 256 ||
    !sql_well_formed_utf16_v1(value) ||
    value.contains("\u0000") {
    fail("mismatch:projected-observer-identity")
  }
}

///|
fn projected_reference_value_v2(
  config : SQLConfigV2,
  descriptor : Map[String, Json],
  reference : Json,
) -> Json raise {
  let fields = object_fields(reference, "independent scalar reference")
  let kind = sql_string_v1(fields.at("type"))
  if fields.at("kind") == Json("literal") {
    return { "type": Json(kind), "value": fields.at("value") }
  }
  for raw in orm_array(descriptor.at("typedInputBindings")) {
    let binding = object_fields(raw, "independent typed binding")
    if sql_canonical_v1(binding.at("reference")) == sql_canonical_v1(reference) {
      let (_, semantic) = point_atom_v2(binding.at("value"))
      return sql_typed_value_v2(
        semantic,
        kind,
        config.parser_config.limits.at("max_text_bytes"),
      )
    }
  }
  fail("mismatch:projected-reference-not-bound")
}

///|
fn projected_expected_fields_v2(
  work : ResultWorkV2,
  config : SQLConfigV2,
  descriptor : Map[String, Json],
) -> (Array[String], Array[String], Array[Bool]) raise {
  let count = fetch_number_v1(descriptor.at("nativeColumnCount"), 53)
  if count == 0 {
    fail("mismatch:projected-no-native-fields")
  }
  let names = Array::make(count, "")
  let kinds = Array::make(count, "")
  let versions = Array::make(count, false)
  let business = object_fields(
    descriptor.at("businessResult"),
    "business shape",
  )
  for raw in orm_array(business.at("columns")) {
    work.charge()
    let field = object_fields(raw, "business field")
    let index = fetch_number_v1(field.at("nativeIndex"), count - 1)
    names[index] = sql_string_v1(field.at("outputName"))
    kinds[index] = projected_column_kind_v2(
      config,
      sql_string_v1(field.at("column")),
    )
  }
  for raw in orm_array(descriptor.at("hiddenResults")) {
    let image = object_fields(raw, "hidden image")
    if image.at("image") != Json("read") {
      for raw in orm_array(image.at("columns")) {
        work.charge()
        let field = object_fields(raw, "hidden field")
        let index = fetch_number_v1(field.at("nativeIndex"), count - 1)
        names[index] = sql_string_v1(field.at("outputName"))
        kinds[index] = projected_column_kind_v2(
          config,
          sql_string_v1(field.at("column")),
        )
      }
    }
    work.charge()
    let field = object_fields(image.at("version"), "version field")
    let index = fetch_number_v1(field.at("nativeIndex"), count - 1)
    names[index] = sql_string_v1(field.at("outputName"))
    kinds[index] = "int64"
    versions[index] = true
  }
  if kinds.any(k => k.is_empty()) || names.any(n => n.is_empty()) {
    fail("mismatch:projected-native-slots-incomplete")
  }
  (names, kinds, versions)
}

///|
pub fn verify_projected_result_v2(
  config : SQLConfigV2,
  source : String,
  original_typed_parameters : Json,
  independent_projection_options : PointProjectionOptionsV2,
  supplied_descriptor : Json,
  native_frame : Json,
  deliveries : Json,
  options~ : ProjectedResultOptionsV2 = projected_result_options_v2(),
) -> ProjectedResultCheckV2 {
  let limits = options.result_options
  let work : ResultWorkV2 = { options: limits, checks: 0, bytes: 0, }
  let mut projection : Json = Json::null()
  let mut native_observation : Json = Json::null()
  let mut delivery_observations : Json = Json::null()
  let mut reason = ""
  let mut operation = ""
  let mut native_verified = false
  let mut images_verified = false
  let mut complete = false
  let mut rows_mode = false
  let mut meaningful = false
  let mut exhausted = false
  let mut delivered = 0
  let mut total = 0
  let mut point_key : Json = Json::null()
  let decoded : Array[Json] = []
  let delivered_rows : Array[Json] = []
  let images : Map[String, Json] = Map([])
  let status = try {
    if limits.max_checks < 0 ||
      limits.max_checks > 1000000 ||
      limits.max_cell_bytes < 0 ||
      limits.max_cell_bytes > 65536 ||
      limits.max_total_bytes < 0 ||
      limits.max_total_bytes > 1048576 ||
      limits.max_delivery_records < 0 ||
      limits.max_delivery_records > 1024 {
      fail("invalid:projected-result-options")
    }
    work.charge()
    projection = point_projection_check_v2_json(
      verify_point_projection_v2(
        config,
        source,
        original_typed_parameters,
        independent_projection_options,
        supplied_descriptor,
        budget=options.projection_budget,
      ),
    )
    let checked = object_fields(projection, "projection check")
    if checked.at("status") != Json("matched") {
      if checked.at("status") == Json("unknown") {
        fail("unsupported:projected-descriptor-incomplete")
      }
      if checked.at("status") == Json("invalid") {
        fail("invalid:projected-independent-inputs")
      }
      fail("mismatch:projected-independent-descriptor")
    }
    let descriptor = object_fields(
      checked.at("expectedDescriptor"),
      "independently rebuilt projection",
    )
    let candidate = object_fields(
      descriptor.at("candidate"),
      "independent SQL candidate",
    )
    operation = sql_string_v1(candidate.at("operation"))
    point_key = projected_reference_value_v2(
      config,
      descriptor,
      candidate.at("keyReference"),
    )
    let business = object_fields(
      descriptor.at("businessResult"),
      "business result",
    )
    rows_mode = business.at("mode") == Json("rows")
    let business_fields = orm_array(business.at("columns"))
    if native_frame == Json::null() {
      fail("unsupported:projected-native-observation-missing")
    }
    if deliveries == Json::null() {
      fail("unsupported:projected-delivery-observations-missing")
    }
    if orm_utf8_size(sql_canonical_v1(native_frame)) > 2097152 ||
      orm_utf8_size(sql_canonical_v1(deliveries)) > 4194304 {
      fail("budget:projected-observation-wire-bytes")
    }
    native_observation = v4_json_copy(native_frame)
    delivery_observations = v4_json_copy(deliveries)
    let frame = orm_exact(native_frame, [
      "resultId", "projectionNoteSeq", "connection", "cursor", "tx", "statementSeq",
      "native", "sourceFactsProduced",
    ])
    for name in ["resultId", "connection", "cursor", "tx"] {
      projected_identity_v2(frame.at(name))
    }
    if frame.at("projectionNoteSeq") == Json::null() {
      fail("unsupported:projected-construction-record-missing")
    }
    let _ = result_note_v2(frame.at("projectionNoteSeq"))
    let _ = result_note_v2(frame.at("statementSeq"))
    result_equal_v2(
      frame.at("sourceFactsProduced"),
      Json(false),
      "producer-does-not-grant-source-facts",
    )
    let native = orm_exact(frame.at("native"), [
      "format", "status", "clientEncodingBase64", "commandStatusBase64", "commandTuples",
      "fields", "rows", "backendPid", "transactionStatus",
    ])
    if native.at("clientEncodingBase64") == Json::null() ||
      native.at("commandStatusBase64") == Json::null() ||
      native.at("commandTuples") == Json::null() {
      fail("unsupported:projected-native-metadata-missing")
    }
    result_equal_v2(
      native.at("format"),
      Json("moontxnwitness-projected-native-result/v2"),
      "projected-native-format",
    )
    result_equal_v2(native.at("status"), Json(2), "projected-TUPLES-OK")
    result_equal_v2(
      native.at("transactionStatus"),
      Json(2),
      "projected-active-transaction",
    )
    let pid = result_uint_v2(native.at("backendPid"), "2147483647")
    if pid == "0" {
      fail("mismatch:projected-backend-pid")
    }
    result_equal_v2(
      Json(result_bytes_v2(work, native.at("clientEncodingBase64"))),
      Json("UTF8"),
      "projected-native-encoding",
    )
    let raw_rows = orm_array(native.at("rows"))
    total = raw_rows.length()
    if total > 1 {
      fail("unsupported:projected-point-row-count")
    }
    let command = result_bytes_v2(work, native.at("commandStatusBase64"))
    let prefix = if operation == "insert" {
      "INSERT 0 "
    } else {
      operation.to_upper() + " "
    }
    result_equal_v2(
      Json(command),
      Json(prefix + total.to_string()),
      "projected-command-count",
    )
    let getter = orm_exact(native.at("commandTuples"), ["pythonType", "value"])
    if getter.at("pythonType") != Json("builtins.int") {
      fail("unsupported:projected-command-getter-type")
    }
    let getter_value = sql_string_v1(getter.at("value"))
    work.payload(orm_utf8_size(getter_value))
    result_equal_v2(
      Json(getter_value),
      Json(total.to_string()),
      "projected-command-getter-value",
    )
    let (names, kinds, versions) = projected_expected_fields_v2(
      work, config, descriptor,
    )
    let fields = orm_array(native.at("fields"))
    if fields.length() != names.length() {
      fail("mismatch:projected-field-count")
    }
    let oids : Array[Int32] = []
    for index, raw in fields {
      work.charge()
      let field = orm_exact(raw, [
        "nameBase64", "oid", "format", "typmod", "tableOid", "tableColumn",
      ])
      result_equal_v2(
        Json(result_bytes_v2(work, field.at("nameBase64"))),
        Json(names[index]),
        "projected-output-name-position",
      )
      if field.at("format") != Json(0) {
        fail("unsupported:projected-binary-format")
      }
      let oid = result_oid_v2(kinds[index], field.at("oid"))
      if versions[index] && oid != 20 {
        fail("mismatch:projected-version-must-be-bigint")
      }
      oids.push(oid)
      let _ = result_uint_v2(field.at("tableOid"), "4294967295")
      let _ = result_uint_v2(field.at("tableColumn"), "32767")
      if field.at("typmod") != Json(-1) {
        let _ = result_uint_v2(field.at("typmod"), "2147483647")
      }
    }
    for raw in raw_rows {
      let cells = orm_array(raw)
      if cells.length() != fields.length() {
        fail("mismatch:projected-native-row-arity")
      }
      let values : Array[Json] = []
      for index, cell in cells {
        work.charge()
        let value = result_native_cell_v2(
          work,
          cell,
          kinds[index],
          oids[index],
          config.parser_config.limits.at("max_text_bytes"),
        )
        if versions[index] {
          let decimal = sql_string_v1(
            object_fields(value, "version value").at("value"),
          )
          if decimal == "0" || decimal.has_prefix("-") {
            fail("mismatch:projected-version-positive")
          }
        }
        values.push(value)
      }
      decoded.push(Json(values))
    }
    native_verified = true
    if total == 1 {
      let values = orm_array(decoded[0])
      for raw in orm_array(descriptor.at("hiddenResults")) {
        work.charge()
        let image = object_fields(raw, "hidden row image")
        let name = sql_string_v1(image.at("image"))
        let columns : Map[String, Json] = Map([])
        for raw in orm_array(image.at("columns")) {
          work.charge()
          let column = object_fields(raw, "hidden row column")
          columns[sql_string_v1(column.at("column"))] = values[fetch_number_v1(
              column.at("nativeIndex"),
              fields.length() - 1,
            )]
        }
        result_equal_v2(
          columns.at(config.parser_config.tables[0].key),
          point_key,
          "projected-image-original-key",
        )
        let version = object_fields(image.at("version"), "hidden version")
        images[name] = {
          "values": Json(columns),
          "version": values[fetch_number_v1(
            version.at("nativeIndex"),
            fields.length() - 1,
          )],
        }
      }
      if operation == "update" {
        let old = object_fields(images.at("old"), "old image")
        let new = object_fields(images.at("new"), "new image")
        if old.at("version") == new.at("version") {
          fail("mismatch:projected-update-version-reused")
        }
        let assignments : Map[String, Json] = Map([])
        for raw in orm_array(candidate.at("assignments")) {
          work.charge()
          let assignment = object_fields(raw, "assignment")
          assignments[sql_string_v1(assignment.at("column"))] = projected_reference_value_v2(
            config,
            descriptor,
            assignment.at("value"),
          )
        }
        let before = object_fields(old.at("values"), "old values")
        let after = object_fields(new.at("values"), "new values")
        for column in config.parser_config.tables[0].columns {
          work.charge()
          result_equal_v2(
            after.at(column.name),
            assignments.get_or_default(column.name, before.at(column.name)),
            "projected-update-assigned-or-unchanged",
          )
        }
      } else if operation == "insert" {
        let row = object_fields(
          object_fields(images.at("new"), "new image").at("values"),
          "inserted values",
        )
        let columns = orm_array(candidate.at("insertColumns"))
        let references = orm_array(orm_array(candidate.at("insertRows"))[0])
        for index, column in columns {
          work.charge()
          result_equal_v2(
            row.at(sql_string_v1(column)),
            projected_reference_value_v2(config, descriptor, references[index]),
            "projected-insert-original-value",
          )
        }
      }
      let image = object_fields(
        images.at(sql_string_v1(business.at("rowImage"))),
        "business image",
      )
      let image_values = object_fields(
        image.at("values"),
        "business image values",
      )
      for raw in business_fields {
        work.charge()
        let field = object_fields(raw, "business native slot")
        result_equal_v2(
          values[fetch_number_v1(field.at("nativeIndex"), fields.length() - 1)],
          image_values.at(sql_string_v1(field.at("column"))),
          "projected-business-hidden-image",
        )
      }
    }
    images_verified = true
    let batches = orm_array(deliveries)
    if batches.length() > limits.max_delivery_records {
      fail("budget:projected-delivery-records")
    }
    if !rows_mode {
      if !batches.is_empty() {
        fail("mismatch:projected-hidden-results-not-business-delivery")
      }
      complete = true
      "matched"
    } else {
      for raw in batches {
        work.charge()
        let batch = orm_exact(raw, [
          "format", "resultId", "connection", "cursor", "tx", "statementSeq", "method",
          "resultPythonType", "requestedSize", "effectiveSize", "start", "rows",
          "exhaustedObserved", "sourceFactsProduced",
        ])
        result_equal_v2(
          batch.at("format"),
          Json("moontxnwitness-projected-delivery/v2"),
          "projected-delivery-format",
        )
        result_equal_v2(
          batch.at("sourceFactsProduced"),
          Json(false),
          "projected-delivery-not-source",
        )
        for name in ["resultId", "connection", "cursor", "tx", "statementSeq"] {
          result_equal_v2(
            batch.at(name),
            frame.at(name),
            "projected-delivery-native-identity",
          )
        }
        if fetch_number_v1(batch.at("start"), 1) != delivered {
          fail("mismatch:projected-delivery-position")
        }
        let delivery_method = sql_string_v1(batch.at("method"))
        if !["fetchone", "fetchmany", "fetchall"].contains(delivery_method) {
          fail("unsupported:projected-delivery-method")
        }
        let rows = orm_array(batch.at("rows"))
        let expected_type = if delivery_method == "fetchone" {
          if rows.is_empty() {
            "builtins.NoneType"
          } else {
            "builtins.tuple"
          }
        } else {
          "builtins.list"
        }
        if batch.at("resultPythonType") != Json(expected_type) {
          fail("unsupported:projected-business-collection-type")
        }
        let current_meaningful = if delivery_method == "fetchmany" {
          let size = fetch_number_v1(batch.at("effectiveSize"), 256)
          if batch.at("requestedSize") != Json::null() &&
            batch.at("requestedSize") != Json(0) {
            result_equal_v2(
              batch.at("requestedSize"),
              Json(size),
              "projected-fetchmany-request-size",
            )
          }
          if rows.length() > size {
            fail("mismatch:projected-fetchmany-length")
          }
          size > 0
        } else {
          result_equal_v2(
            batch.at("requestedSize"),
            Json::null(),
            "projected-fetch-size-not-applicable",
          )
          result_equal_v2(
            batch.at("effectiveSize"),
            Json::null(),
            "projected-fetch-size-not-applicable",
          )
          if delivery_method == "fetchone" && rows.length() > 1 {
            fail("mismatch:projected-fetchone-length")
          }
          true
        }
        if delivered + rows.length() > total || (exhausted && !rows.is_empty()) {
          fail("mismatch:projected-delivery-after-native-end")
        }
        for raw in rows {
          work.charge()
          let row = orm_exact(raw, ["pythonType", "cells"])
          if row.at("pythonType") != Json("builtins.tuple") {
            fail("unsupported:projected-custom-row-factory")
          }
          let cells = orm_array(row.at("cells"))
          if cells.length() != business_fields.length() {
            fail("mismatch:projected-delivery-hidden-or-missing-columns")
          }
          let values = orm_array(decoded[delivered])
          let verified : Array[Json] = []
          for index, cell in cells {
            work.charge()
            let field = object_fields(
              business_fields[index],
              "business ordinal",
            )
            let native_index = fetch_number_v1(
              field.at("nativeIndex"),
              fields.length() - 1,
            )
            let actual = result_delivered_cell_v2(
              work,
              cell,
              kinds[native_index],
              config.parser_config.limits.at("max_text_bytes"),
            )
            result_equal_v2(
              actual,
              values[native_index],
              "projected-delivery-native-cell",
            )
            verified.push(actual)
          }
          delivered_rows.push(Json(verified))
          delivered += 1
        }
        let observed = match batch.at("exhaustedObserved") {
          True => true
          False => false
          _ => fail("mismatch:projected-exhaustion-boolean")
        }
        if ((observed && current_meaningful) || delivery_method == "fetchall") &&
          delivered != total {
          fail("mismatch:projected-premature-exhaustion")
        }
        meaningful = meaningful || current_meaningful
        exhausted = exhausted || (observed && current_meaningful)
      }
      complete = meaningful && delivered == total
      if complete {
        "matched"
      } else {
        "partial"
      }
    }
  } catch {
    error => {
      reason = error.to_string()
      if reason.contains("budget:") || reason.contains("unsupported:") {
        "unknown"
      } else if reason.contains("mismatch:") {
        "mismatch"
      } else {
        "invalid"
      }
    }
  }
  {
    record: {
      "format": "moontxnwitness-projected-result-verification/v2",
      "semanticContract": "postgres18-projected-point-native-business-delivery-consistency/v2",
      "algorithm": "moonbit-projected-point-result-images-delivery-2",
      "status": Json(status),
      "valid": Json(status == "matched"),
      "completeObservationVerified": Json(status == "matched" && complete),
      "nativeResultVerified": Json(native_verified),
      "rowImageConsistencyVerified": Json(images_verified),
      "completeFetchVerified": Json(
        status == "matched" && rows_mode && complete,
      ),
      "nativeRows": Json(total),
      "deliveredRows": Json(delivered),
      "operation": Json(operation),
      "pointKeyIdentity": point_key,
      "projection": projection,
      "decodedNativeRows": Json(decoded),
      "rowImageObservations": Json(images),
      "verifiedBusinessDeliveries": Json(delivered_rows),
      "nativeFrameObservation": native_observation,
      "deliveryObservations": delivery_observations,
      "databaseExecuted": false,
      "databaseSyntaxValidated": false,
      "sourceFactsProduced": false,
      "captureFactsProduced": false,
      "sourceAuthenticated": false,
      "catalogVerified": false,
      "sourceColumnMappingVerified": false,
      "completeWindow": false,
      "sourceWindowVerified": false,
      "modelCoverageAccepted": false,
      "commitVerified": false,
      "committedWriteEffectVerified": false,
      "moonbitProjectionVerified": false,
      "absenceSourceVerified": false,
      "execution": {
        "counterContract": "projected-field-image-business-delivery-checks-2",
        "checks": Json(work.checks),
        "payloadBytes": Json(work.bytes),
        "limits": {
          "maxChecks": Json(limits.max_checks),
          "maxCellBytes": Json(limits.max_cell_bytes),
          "maxTotalBytes": Json(limits.max_total_bytes),
          "maxDeliveryRecords": Json(limits.max_delivery_records),
          "maxNativeRows": 1,
          "maxNativeColumns": 53,
        },
      },
      "gaps": [
        Json(
          if reason.is_empty() {
            "projection-result-consistency-only-source-window-lifecycle-and-model-unproven"
          } else {
            reason
          },
        ),
      ],
      "scope": "independently reconstructed projection and consistency of supplied native/write-image/business-delivery observations; no source, lifecycle, absence, commit or model admission",
    },
  }
}
