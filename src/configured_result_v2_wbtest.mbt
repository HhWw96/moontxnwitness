///|
fn result52_b64(text : String) -> Json {
  Json(@base64.encode(@utf8.encode(text[:])[:]))
}

///|
fn result52_fixture(
  layout : Int32,
  operation~ : String = "select",
  returning~ : Bool = true,
  empty~ : Bool = false,
) -> Json raise {
  let config_text = sql52_config_text(layout)
  let config = parse_sql_config_v2(config_text).unwrap()
  let table = config.parser_config.tables[0]
  let target = [
      "ledger.accounts", "\"App-X\".\"Customer.Space\"", "identity.members",
    ][layout]
  let key = if layout == 1 { "\"User ID\"" } else { table.key }
  let slot = if layout == 2 { "%s::UUID" } else { "%s" }
  let native_values : Array[Json] = []
  let original_values : Array[Json] = []
  for index, column in table.columns {
    let value : Json = match column.kind {
      "uuid" => Json("a8098c1a-f86e-11da-bd1a-00112444be1e")
      "text" => Json(if index == 0 { "Key" } else { "值🙂-" + column.name })
      "int64" => Json(if index == 0 { 7 } else { 17 })
      _ => Json(true)
    }
    native_values.push(value)
    original_values.push(
      if column.kind == "uuid" {
        Json("A8098C1AF86E11DABD1A00112444BE1E")
      } else {
        value
      },
    )
  }
  let (source, parameters) : (String, Json) = if operation == "select" {
    (
      "SELECT * FROM " + target + " WHERE " + key + "=" + slot,
      Json([original_values[0]]),
    )
  } else if operation == "insert" {
    let names = table.columns.map(c => {
      if c.name == "User ID" {
        "\"User ID\""
      } else {
        c.name
      }
    })
    let slots = table.columns.map(c => {
      if c.kind == "uuid" {
        "%s::UUID"
      } else {
        "%s"
      }
    })
    (
      "INSERT INTO " +
      target +
      "(" +
      names.join(",") +
      ") VALUES(" +
      slots.join(",") +
      ")" +
      (if returning { " RETURNING *" } else { "" }),
      Json(original_values),
    )
  } else if operation == "update" {
    (
      "UPDATE " +
      target +
      " SET " +
      table.columns[1].name +
      "=%s WHERE " +
      key +
      "=" +
      slot +
      (if returning { " RETURNING *" } else { "" }),
      Json([original_values[1], original_values[0]]),
    )
  } else {
    (
      "DELETE FROM " +
      target +
      " WHERE " +
      key +
      "=" +
      slot +
      (if returning { " RETURNING *" } else { "" }),
      Json([original_values[0]]),
    )
  }
  let grammar = sql_candidate_check_v2_json(
    normalize_sql_candidate_v2(config, source, parameters),
  )
  let descriptor = v4_test_at(grammar, ["descriptor"])
  let tuple_result = operation == "select" || returning
  let fields : Array[Json] = []
  let native_row : Array[Json] = []
  let delivered_cells : Array[Json] = []
  if tuple_result {
    for index, column in table.columns {
      let kind = column.kind
      let oid = match kind {
        "uuid" => 2950
        "text" => 25
        "bool" => 16
        _ => 20
      }
      fields.push({
        "nameBase64": result52_b64(column.name),
        "oid": Json(oid),
        "format": 0,
        "typmod": -1,
        "tableOid": 17000,
        "tableColumn": Json(index + 1),
      })
      let value = native_values[index]
      let raw = match kind {
        "int64" => sql_number_text_v1(value)
        "bool" => "t"
        _ => sql_string_v1(value)
      }
      native_row.push(result52_b64(raw))
      delivered_cells.push({
        "pythonType": Json(
          match kind {
            "uuid" => "uuid.UUID"
            "text" => "builtins.str"
            "bool" => "builtins.bool"
            _ => "builtins.int"
          },
        ),
        "value": if kind == "int64" {
          Json(raw)
        } else {
          value
        },
      })
    }
  }
  let count = if empty { "0" } else { "1" }
  let command_tag = if operation == "insert" {
    "INSERT 0 " + count
  } else {
    operation.to_upper() + " " + count
  }
  let native_rows : Array[Json] = if tuple_result && !empty {
    [Json(native_row)]
  } else {
    []
  }
  let delivered_rows : Array[Json] = if tuple_result && !empty {
    [{ "pythonType": "builtins.tuple", "cells": Json(delivered_cells) }]
  } else {
    []
  }
  let execution : Json = {
    "format": "moontxnwitness-configured-execution/v2",
    "connection": "c1",
    "cursor": "q1",
    "tx": "t1",
    "statementSeq": 1,
    "executionNoteSeq": 2,
    "sql": Json(source),
    "parameters": parameters,
    "candidate": descriptor,
    "sqlRewritten": false,
    "success": true,
    "decoderContract": "psycopg-default-text-scalars/v2",
  }
  let native : Json = {
    "format": "moontxnwitness-native-result/v2",
    "resultId": "r1",
    "connection": "c1",
    "cursor": "q1",
    "tx": "t1",
    "statementSeq": 1,
    "executionNoteSeq": 2,
    "nativeNoteSeq": 3,
    "sqlSha256": v4_test_at(grammar, ["sqlSha256"]),
    "originalParametersSha256": v4_test_at(grammar, ["originalParametersSha256"]),
    "status": Json(if tuple_result { 2 } else { 1 }),
    "clientEncodingBase64": result52_b64("UTF8"),
    "commandStatusBase64": result52_b64(command_tag),
    "commandTuples": { "pythonType": "builtins.int", "value": Json(count) },
    "fields": Json(fields),
    "rows": Json(native_rows),
  }
  let deliveries : Array[Json] = if tuple_result {
    [
      {
        "format": "moontxnwitness-actual-delivery/v2",
        "resultId": "r1",
        "connection": "c1",
        "cursor": "q1",
        "tx": "t1",
        "statementSeq": 1,
        "nativeNoteSeq": 3,
        "deliveryNoteSeq": 4,
        "method": "fetchall",
        "resultPythonType": "builtins.list",
        "requestedSize": Json::null(),
        "effectiveSize": Json::null(),
        "start": 0,
        "rows": Json(delivered_rows),
        "exhaustedObserved": false,
      },
    ]
  } else {
    []
  }
  {
    "config": Json(config_text),
    "execution": execution,
    "native": native,
    "deliveries": Json(deliveries),
  }
}

///|
fn result52_section(fixture : Json, name : String) -> Map[String, Json] raise {
  object_fields(orm_get(fixture, name), name)
}

///|
fn result52_field(fixture : Json, index : Int32) -> Map[String, Json] raise {
  object_fields(
    orm_array(result52_section(fixture, "native").at("fields"))[index],
    "field",
  )
}

///|
fn result52_batch(fixture : Json) -> Map[String, Json] raise {
  object_fields(orm_array(orm_get(fixture, "deliveries"))[0], "batch")
}

///|
fn result52_cell(fixture : Json, index : Int32) -> Map[String, Json] raise {
  let row = object_fields(
    orm_array(result52_batch(fixture).at("rows"))[0],
    "row",
  )
  object_fields(orm_array(row.at("cells"))[index], "cell")
}

///|
fn result52_run(
  fixture : Json,
  options~ : ConfiguredResultOptionsV2 = configured_result_options_v2(),
) -> Json raise {
  let root = object_fields(fixture, "fixture")
  configured_result_check_v2_json(
    verify_configured_result_v2(
      parse_sql_config_v2(sql_string_v1(root.at("config"))).unwrap(),
      root.at("execution"),
      root.at("native"),
      root.at("deliveries"),
      options~,
    ),
  )
}

///|
fn result52_no_facts(report : Json) -> Unit raise {
  for
    flag in [
      "captureFactsProduced", "sourceFactsProduced", "sourceAuthenticated", "sourceColumnMappingVerified",
      "catalogVerified", "sourceWindowVerified", "modelCoverageAccepted", "commitVerified",
      "committedWriteEffectVerified", "moonbitProjectionVerified",
    ] {
    assert_eq(v4_test_at(report, [flag]), Json(false))
  }
}

///|
test "result52 three layouts full row and original RETURNING match without source facts" {
  for layout in [0, 1, 2] {
    for operation in ["select", "insert", "update", "delete"] {
      let fixture = result52_fixture(layout, operation~)
      let report = result52_run(fixture)
      assert_eq(v4_test_at(report, ["status"]), Json("matched"))
      assert_eq(v4_test_at(report, ["completeFetchVerified"]), Json(true))
      assert_eq(
        v4_test_at(report, ["nativeObservation"]),
        orm_get(fixture, "native"),
      )
      assert_eq(
        v4_test_at(report, ["deliveryObservations"]),
        orm_get(fixture, "deliveries"),
      )
      result52_no_facts(report)
    }
  }
}

///|
test "result52 COMMAND OK DML zero and one are original observations not committed effects" {
  for operation in ["insert", "update", "delete"] {
    for empty in [false, true] {
      let report = result52_run(
        result52_fixture(2, operation~, returning=false, empty~),
      )
      assert_eq(v4_test_at(report, ["status"]), Json("matched"))
      assert_eq(v4_test_at(report, ["commandObservationVerified"]), Json(true))
      assert_eq(v4_test_at(report, ["completeFetchVerified"]), Json(false))
      assert_eq(
        v4_test_at(report, ["affectedRowsObservation"]),
        Json(if empty { "0" } else { "1" }),
      )
      assert_eq(v4_test_at(report, ["returnedKeyObserved"]), Json(false))
      assert_eq(
        v4_test_at(report, ["returnedKeyConsistencyVerified"]),
        Json(false),
      )
      result52_no_facts(report)
    }
  }
}

///|
test "result52 single fetchone row completes by native count with no fetchNone" {
  let fixture = result52_fixture(2)
  result52_batch(fixture)["method"] = Json("fetchone")
  result52_batch(fixture)["resultPythonType"] = Json("builtins.tuple")
  let report = result52_run(fixture)
  assert_eq(v4_test_at(report, ["status"]), Json("matched"))
  assert_eq(v4_test_at(report, ["completeFetchVerified"]), Json(true))
  assert_eq(v4_test_at(report, ["exhaustedObserved"]), Json(false))
  let observed = result52_cell(fixture, 0)
  assert_eq(observed.at("pythonType"), Json("uuid.UUID"))
  assert_eq(observed.at("value"), Json("a8098c1a-f86e-11da-bd1a-00112444be1e"))
  assert_eq(v4_test_at(report, ["returnedKeyConsistencyVerified"]), Json(true))
  assert_eq(
    v4_test_at(report, ["pointKeyIdentity", "value"]),
    Json("a8098c1a-f86e-11da-bd1a-00112444be1e"),
  )
  result52_no_facts(report)
}

///|
test "result52 empty native requires meaningful fetch not none or fetchmany zero" {
  for delivery_method in ["fetchone", "fetchall", "fetchmany"] {
    let fixture = result52_fixture(2, empty=true)
    let batch = result52_batch(fixture)
    batch["method"] = Json(delivery_method)
    if delivery_method == "fetchone" {
      batch["resultPythonType"] = Json("builtins.NoneType")
    }
    if delivery_method == "fetchmany" {
      batch["requestedSize"] = Json(1)
      batch["effectiveSize"] = Json(1)
    }
    assert_eq(
      v4_test_at(result52_run(fixture), ["completeFetchVerified"]),
      Json(true),
    )
  }
  let fixture = result52_fixture(2, empty=true)
  let batch = result52_batch(fixture)
  batch["method"] = Json("fetchmany")
  batch["requestedSize"] = Json(0)
  batch["effectiveSize"] = Json(0)
  batch["exhaustedObserved"] = Json(true)
  let zero = result52_run(fixture)
  assert_eq(v4_test_at(zero, ["status"]), Json("partial"))
  assert_eq(v4_test_at(zero, ["completeFetchVerified"]), Json(false))
  object_fields(fixture, "fixture")["deliveries"] = Json(([] : Array[Json]))
  assert_eq(
    v4_test_at(result52_run(fixture), ["completeFetchVerified"]),
    Json(false),
  )
  result52_no_facts(zero)
}

///|
test "result52 partial delivery cannot complete even with native buffer present" {
  let fixture = result52_fixture(2)
  let batch = result52_batch(fixture)
  batch["method"] = Json("fetchmany")
  batch["requestedSize"] = Json(0)
  batch["effectiveSize"] = Json(0)
  batch["rows"] = Json(([] : Array[Json]))
  let report = result52_run(fixture)
  assert_eq(v4_test_at(report, ["status"]), Json("partial"))
  assert_eq(v4_test_at(report, ["valid"]), Json(false))
  assert_eq(v4_test_at(report, ["completeObservationVerified"]), Json(false))
  result52_no_facts(report)
}

///|
test "result52 default fetchmany size is recorded independently of omitted argument" {
  let fixture = result52_fixture(2)
  let batch = result52_batch(fixture)
  batch["method"] = Json("fetchmany")
  batch["requestedSize"] = Json::null()
  batch["effectiveSize"] = Json(1)
  assert_eq(v4_test_at(result52_run(fixture), ["status"]), Json("matched"))
  // Pinned psycopg treats an explicit zero as its observed arraysize default.
  batch["requestedSize"] = Json(0)
  assert_eq(v4_test_at(result52_run(fixture), ["status"]), Json("matched"))
  batch["requestedSize"] = Json(2)
  assert_eq(v4_test_at(result52_run(fixture), ["status"]), Json("mismatch"))
}

///|
test "result52 explicit zero request with positive resolved size can observe absence" {
  let fixture = result52_fixture(2, empty=true)
  let batch = result52_batch(fixture)
  batch["method"] = Json("fetchmany")
  batch["requestedSize"] = Json(0)
  batch["effectiveSize"] = Json(1)
  assert_eq(v4_test_at(result52_run(fixture), ["status"]), Json("matched"))
  batch["effectiveSize"] = Json(0)
  assert_eq(v4_test_at(result52_run(fixture), ["status"]), Json("partial"))
}

///|
test "result52 UUID OID and actual UUID object type are required even on empty result" {
  for empty in [false, true] {
    let fixture = result52_fixture(2, empty~)
    result52_field(fixture, 0)["oid"] = Json(25)
    let report = result52_run(fixture)
    assert_eq(v4_test_at(report, ["completeObservationVerified"]), Json(false))
    assert_eq(v4_test_at(report, ["status"]), Json("unknown"))
    result52_no_facts(report)
  }
  let fixture = result52_fixture(2)
  result52_cell(fixture, 0)["pythonType"] = Json("builtins.str")
  let report = result52_run(fixture)
  assert_eq(v4_test_at(report, ["status"]), Json("unknown"))
  result52_no_facts(report)
}

///|
test "result52 native field names formats and positions cannot be candidate authorized" {
  for field_name in ["nameBase64", "format"] {
    let fixture = result52_fixture(2, empty=true)
    result52_field(fixture, 0)[field_name] = if field_name == "format" {
      Json(1)
    } else {
      result52_b64("wrong")
    }
    let report = result52_run(fixture)
    assert_eq(v4_test_at(report, ["completeObservationVerified"]), Json(false))
    result52_no_facts(report)
  }
}

///|
test "result52 delivered rows types values and positions are checked" {
  for field_name in ["start", "nativeNoteSeq", "deliveryNoteSeq"] {
    let fixture = result52_fixture(2)
    result52_batch(fixture)[field_name] = Json(1)
    assert_eq(v4_test_at(result52_run(fixture), ["status"]), Json("mismatch"))
  }
  let fixture = result52_fixture(2)
  result52_cell(fixture, 1)["value"] = Json("different")
  assert_eq(v4_test_at(result52_run(fixture), ["status"]), Json("mismatch"))
  let fixture2 = result52_fixture(0)
  result52_cell(fixture2, 0)["pythonType"] = Json("builtins.bool")
  assert_eq(
    v4_test_at(result52_run(fixture2), ["completeObservationVerified"]),
    Json(false),
  )
}

///|
test "result52 native tag raw count status and success must align" {
  for field_name in ["commandStatusBase64", "commandTuples", "status"] {
    let fixture = result52_fixture(2, operation="update", returning=false)
    result52_section(fixture, "native")[field_name] = match field_name {
      "status" => Json(2)
      "commandTuples" => { "pythonType": "builtins.int", "value": "0" }
      _ => result52_b64("DELETE 1")
    }
    let report = result52_run(fixture)
    assert_eq(v4_test_at(report, ["status"]), Json("mismatch"))
    result52_no_facts(report)
  }
  let fixture = result52_fixture(2)
  result52_section(fixture, "execution")["success"] = Json(false)
  assert_eq(v4_test_at(result52_run(fixture), ["status"]), Json("mismatch"))
}

///|
test "result52 more than one native row or affected count cannot complete point contract" {
  let fixture = result52_fixture(2)
  let native = result52_section(fixture, "native")
  let rows = orm_array(native.at("rows"))
  rows.push(rows[0])
  let report = result52_run(fixture)
  assert_eq(v4_test_at(report, ["completeObservationVerified"]), Json(false))
  let command_fixture = result52_fixture(2, operation="delete", returning=false)
  let command = result52_section(command_fixture, "native")
  command["commandStatusBase64"] = result52_b64("DELETE 2")
  command["commandTuples"] = { "pythonType": "builtins.int", "value": "2" }
  assert_eq(
    v4_test_at(result52_run(command_fixture), ["completeObservationVerified"]),
    Json(false),
  )
}

///|
test "result52 missing native and unrewritten SQL mismatch remain incomplete" {
  let fixture = result52_fixture(2)
  object_fields(fixture, "fixture")["native"] = Json::null()
  assert_eq(
    v4_test_at(result52_run(fixture), ["completeObservationVerified"]),
    Json(false),
  )
  let fixture2 = result52_fixture(2)
  result52_section(fixture2, "execution")["sqlRewritten"] = Json(true)
  assert_eq(v4_test_at(result52_run(fixture2), ["status"]), Json("mismatch"))
}

///|
test "result52 result and grammar caller budgets stay independent unknown" {
  for
    options in [
      configured_result_options_v2(max_checks=0),
      configured_result_options_v2(max_cell_bytes=0),
      configured_result_options_v2(max_total_bytes=0),
      configured_result_options_v2(max_delivery_records=0),
      configured_result_options_v2(
        grammar_options=sql_verification_options_v2(max_checks=0),
      ),
    ] {
    let report = result52_run(result52_fixture(2), options~)
    assert_eq(v4_test_at(report, ["status"]), Json("unknown"))
    assert_eq(v4_test_at(report, ["completeObservationVerified"]), Json(false))
    result52_no_facts(report)
  }
}

///|
test "result52 raw bytes and integer OID width are checked independently of equal delivered claims" {
  let fixture = result52_fixture(0)
  result52_field(fixture, 1)["oid"] = Json(21)
  let row = orm_array(
    orm_array(result52_section(fixture, "native").at("rows"))[0],
  )
  row[1] = result52_b64("65536")
  result52_cell(fixture, 1)["value"] = Json("65536")
  assert_eq(v4_test_at(result52_run(fixture), ["status"]), Json("mismatch"))
  let fixture2 = result52_fixture(2)
  let row2 = orm_array(
    orm_array(result52_section(fixture2, "native").at("rows"))[0],
  )
  row2[0] = result52_b64("A8098C1A-F86E-11DA-BD1A-00112444BE1E")
  assert_eq(v4_test_at(result52_run(fixture2), ["status"]), Json("mismatch"))
  let fixture3 = result52_fixture(2)
  result52_field(fixture3, 0)["nameBase64"] = Json("/w==")
  assert_eq(
    v4_test_at(result52_run(fixture3), ["completeObservationVerified"]),
    Json(false),
  )
}

///|
test "result52 original UUID parameter observations remain bound separately from canonical identity" {
  let fixture = result52_fixture(2)
  let execution = result52_section(fixture, "execution")
  execution["parameters"] = ["a8098c1a-f86e-11da-bd1a-00112444be1e"]
  let report = result52_run(fixture)
  assert_eq(v4_test_at(report, ["status"]), Json("mismatch"))
  result52_no_facts(report)
}

///|
test "result52 custom row factories and UUID decoder representations cannot complete" {
  let fixture = result52_fixture(2)
  object_fields(orm_array(result52_batch(fixture).at("rows"))[0], "row")["pythonType"] = Json(
    "builtins.list",
  )
  assert_eq(v4_test_at(result52_run(fixture), ["status"]), Json("unknown"))
  let fixture2 = result52_fixture(2)
  result52_cell(fixture2, 0)["pythonType"] = Json("custom.UUID")
  assert_eq(
    v4_test_at(result52_run(fixture2), ["completeObservationVerified"]),
    Json(false),
  )
}

///|
test "result52 original RETURNING subset keeps its own output shape" {
  let fixture = result52_fixture(2, operation="delete")
  let config = parse_sql_config_v2(sql_string_v1(orm_get(fixture, "config"))).unwrap()
  let execution = result52_section(fixture, "execution")
  let source = "DELETE FROM identity.members WHERE member_uuid=%s::UUID RETURNING member_uuid"
  let grammar = sql_candidate_check_v2_json(
    normalize_sql_candidate_v2(config, source, execution.at("parameters")),
  )
  execution["sql"] = Json(source)
  execution["candidate"] = v4_test_at(grammar, ["descriptor"])
  let native = result52_section(fixture, "native")
  native["sqlSha256"] = v4_test_at(grammar, ["sqlSha256"])
  let fields = orm_array(native.at("fields"))
  native["fields"] = Json([fields[0]])
  let cells = orm_array(orm_array(native.at("rows"))[0])
  native["rows"] = [Json([cells[0]])]
  let row = object_fields(
    orm_array(result52_batch(fixture).at("rows"))[0],
    "row",
  )
  let delivered = orm_array(row.at("cells"))
  row["cells"] = Json([delivered[0]])
  let report = result52_run(fixture)
  assert_eq(v4_test_at(report, ["status"]), Json("matched"))
  assert_eq(v4_test_at(report, ["completeFetchVerified"]), Json(true))
  result52_no_facts(report)
}

///|
test "result52 V2 JSON boundary rejects V1 formats invalid options and missing native" {
  let fixture = result52_fixture(2)
  let root = object_fields(fixture, "fixture")
  for
    options in [
      "{\"maxChecks\":-1}", "{\"trusted\":true}", "{\"maxTotalBytes\":true}",
    ] {
    let report = sql_json_v1(
      verify_configured_result_v2_json(
        sql_string_v1(root.at("config")),
        root.at("execution").stringify(),
        root.at("native").stringify(),
        root.at("deliveries").stringify(),
        options,
      ),
      8388608,
    )
    assert_eq(v4_test_at(report, ["status"]), Json("invalid"))
    result52_no_facts(report)
  }
  result52_section(fixture, "native")["format"] = Json(
    "moontxnwitness-native-result/v1",
  )
  assert_eq(v4_test_at(result52_run(fixture), ["status"]), Json("mismatch"))
}

///|
test "result52 three key types reject equal native delivery values for the wrong original key" {
  for layout in [0, 1, 2] {
    let fixture = result52_fixture(layout)
    let wrong = ["8", "key", "a8098c1a-f86e-11da-bd1a-00112444be1f"][layout]
    let row = orm_array(
      orm_array(result52_section(fixture, "native").at("rows"))[0],
    )
    row[0] = result52_b64(wrong)
    result52_cell(fixture, 0)["value"] = Json(wrong)
    let report = result52_run(fixture)
    assert_eq(v4_test_at(report, ["status"]), Json("mismatch"))
    assert_eq(v4_test_at(report, ["returnedKeyObserved"]), Json(true))
    assert_eq(
      v4_test_at(report, ["returnedKeyConsistencyVerified"]),
      Json(false),
    )
    result52_no_facts(report)
  }
}

///|
test "result52 text key identity does not normalize Unicode or case" {
  let fixture = result52_fixture(1)
  let config = parse_sql_config_v2(sql_string_v1(orm_get(fixture, "config"))).unwrap()
  let execution = result52_section(fixture, "execution")
  execution["parameters"] = ["é"]
  let grammar = sql_candidate_check_v2_json(
    normalize_sql_candidate_v2(
      config,
      sql_string_v1(execution.at("sql")),
      execution.at("parameters"),
    ),
  )
  let native = result52_section(fixture, "native")
  native["originalParametersSha256"] = v4_test_at(grammar, [
    "originalParametersSha256",
  ])
  orm_array(orm_array(native.at("rows"))[0])[0] = result52_b64("é")
  result52_cell(fixture, 0)["value"] = Json("é")
  assert_eq(v4_test_at(result52_run(fixture), ["status"]), Json("mismatch"))
}

///|
test "result52 original RETURNING without key never fabricates key observations" {
  let fixture = result52_fixture(2, operation="update")
  let config = parse_sql_config_v2(sql_string_v1(orm_get(fixture, "config"))).unwrap()
  let execution = result52_section(fixture, "execution")
  let source = "UPDATE identity.members SET email=%s WHERE member_uuid=%s::UUID RETURNING email"
  let grammar = sql_candidate_check_v2_json(
    normalize_sql_candidate_v2(config, source, execution.at("parameters")),
  )
  execution["sql"] = Json(source)
  execution["candidate"] = v4_test_at(grammar, ["descriptor"])
  let native = result52_section(fixture, "native")
  native["sqlSha256"] = v4_test_at(grammar, ["sqlSha256"])
  native["fields"] = Json([orm_array(native.at("fields"))[1]])
  native["rows"] = [Json([orm_array(orm_array(native.at("rows"))[0])[1]])]
  let row = object_fields(
    orm_array(result52_batch(fixture).at("rows"))[0],
    "row",
  )
  row["cells"] = Json([orm_array(row.at("cells"))[1]])
  let report = result52_run(fixture)
  assert_eq(v4_test_at(report, ["status"]), Json("matched"))
  assert_eq(v4_test_at(report, ["returnedKeyObserved"]), Json(false))
  assert_eq(v4_test_at(report, ["returnedKeyConsistencyVerified"]), Json(false))
  result52_no_facts(report)
}

///|
test "result52 command tuple getter observation cannot impersonate native bytes or bool" {
  for
    observation in [
      ({ "pythonType": "builtins.NoneType", "value": Json::null() } : Json),
      { "pythonType": "builtins.bool", "value": true },
      { "pythonType": "builtins.bytes", "value": "MQ==" },
    ] {
    let fixture = result52_fixture(2, operation="delete", returning=false)
    result52_section(fixture, "native")["commandTuples"] = observation
    let report = result52_run(fixture)
    assert_eq(v4_test_at(report, ["completeObservationVerified"]), Json(false))
    result52_no_facts(report)
  }
}

///|
test "result52 missing encoding result type or row type observations cannot be assumed" {
  let fixture = result52_fixture(2)
  result52_section(fixture, "native").remove("clientEncodingBase64")
  assert_eq(
    v4_test_at(result52_run(fixture), ["completeObservationVerified"]),
    Json(false),
  )
  let fixture2 = result52_fixture(2)
  result52_batch(fixture2).remove("resultPythonType")
  assert_eq(
    v4_test_at(result52_run(fixture2), ["completeObservationVerified"]),
    Json(false),
  )
  let fixture3 = result52_fixture(2)
  object_fields(orm_array(result52_batch(fixture3).at("rows"))[0], "row").remove(
    "pythonType",
  )
  assert_eq(
    v4_test_at(result52_run(fixture3), ["completeObservationVerified"]),
    Json(false),
  )
}
