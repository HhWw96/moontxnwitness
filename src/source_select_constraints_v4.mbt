///|
fn source_select_integer_compare_v4(
  left : String,
  right : String,
) -> Int32 raise {
  if sql_decimal_v1(left) != left || sql_decimal_v1(right) != right {
    fail("mismatch:noncanonical-select-int64")
  }
  let negative_left = left.has_prefix("-")
  let negative_right = right.has_prefix("-")
  if negative_left != negative_right {
    return if negative_left { -1 } else { 1 }
  }
  let l = if negative_left { left[1:].to_owned() } else { left }
  let r = if negative_right { right[1:].to_owned() } else { right }
  let order = if l.length() < r.length() {
    -1
  } else if l.length() > r.length() {
    1
  } else if l < r {
    -1
  } else if l > r {
    1
  } else {
    0
  }
  if negative_left {
    0 - order
  } else {
    order
  }
}

///|
fn source_select_compare_v4(left : Json, right : Json) -> Int32 raise {
  let l = orm_exact(left, ["type", "value"])
  let r = orm_exact(right, ["type", "value"])
  source_equal_v4(l.at("type"), r.at("type"), "SELECT-scalar-kind")
  match sql_string_v1(l.at("type")) {
    "int64" =>
      source_select_integer_compare_v4(
        sql_string_v1(l.at("value")),
        sql_string_v1(r.at("value")),
      )
    "text" =>
      relation_v3_text_compare(
        sql_string_v1(l.at("value")),
        sql_string_v1(r.at("value")),
      )
    "bool" => {
      match l.at("value") {
        True | False => ()
        _ => fail("mismatch:SELECT-boolean")
      }
      match r.at("value") {
        True | False => ()
        _ => fail("mismatch:SELECT-boolean")
      }
      if l.at("value") == r.at("value") {
        0
      } else if l.at("value") == Json(false) {
        -1
      } else {
        1
      }
    }
    _ => fail("unsupported:SELECT-scalar-kind")
  }
}

///|
fn source_select_expected_v4(
  reference : Json,
  bindings : Array[Json],
  work : SourceWorkV4,
) -> Json raise {
  let r = orm_exact(reference, ["kind", "type", "value"])
  if r.at("kind") == Json("literal") {
    return { "type": r.at("type"), "value": r.at("value") }
  }
  if r.at("kind") != Json("named") && r.at("kind") != Json("positional") {
    fail("unsupported:SELECT-binding-reference")
  }
  let mut found : Json? = None
  for raw in bindings {
    work.charge()
    let binding = orm_exact(raw, ["reference", "value"])
    if sql_canonical_v1(binding.at("reference")) == sql_canonical_v1(reference) {
      match found {
        None => found = Some(binding.at("value"))
        Some(previous) =>
          source_equal_v4(
            previous,
            binding.at("value"),
            "SELECT-binding-identity",
          )
      }
    }
  }
  match found {
    Some(value) => value
    None => fail("mismatch:SELECT-binding-unresolved")
  }
}

///|
fn source_select_result_constraints_v4(
  native_check : Json,
  native : Json,
  work : SourceWorkV4,
) -> Json {
  let start = work.checks
  let mut reason = ""
  let gaps : Array[String] = []
  let mut witness : Json = Json::null()
  let mut delivered = 0
  let mut checked = 0
  let mut native_consistent = false
  let mut native_complete = false
  let mut result_reference : Json = Json::null()
  let status = try {
    work.charge()
    let f = source_object_v4(native_check)
    native_consistent = f.at("valid") == Json(true)
    native_complete = f.at("completeFetchVerified") == Json(true)
    if f.at("valid") != Json(true) {
      if f.at("status") == Json("mismatch") || f.at("status") == Json("invalid") {
        fail("mismatch:original-native-delivery-not-verified")
      }
      if sql_canonical_v1(native_check).contains("budget:") {
        fail("budget:original-native-delivery")
      }
      gaps.push("native-delivery-not-verified")
      fail("unsupported:original-native-delivery-not-verified")
    }
    let native_record = source_object_v4(native)
    result_reference = {
      "resultId": native_record.at("resultId"),
      "statementSeq": native_record.at("statementSeq"),
      "connection": native_record.at("connection"),
      "cursor": native_record.at("cursor"),
      "tx": native_record.at("tx"),
    }
    let grammar = source_object_v4(f.at("grammar"))
    let descriptor = source_object_v4(grammar.at("descriptor"))
    let table = source_object_v4(descriptor.at("table"))
    let key_name = sql_string_v1(table.at("primaryKey"))
    let projections = orm_array(descriptor.at("projections"))
    let terms = orm_array(descriptor.at("predicates"))
    let bindings = orm_array(grammar.at("bindings"))
    let fields = orm_array(source_object_v4(native).at("fields"))
    let raw_rows = orm_array(source_object_v4(native).at("rows"))
    delivered = fetch_number_v1(f.at("deliveredRows"), 256)
    let names : Array[String] = []
    let kinds : Array[String] = []
    let oids : Array[Int32] = []
    let formats : Array[Int32] = []
    for index, projection in projections {
      work.charge()
      let name = sql_string_v1(source_object_v4(projection).at("column"))
      names.push(name)
      let mut kind = ""
      for column in orm_array(table.at("columns")) {
        let c = source_object_v4(column)
        if c.at("name") == Json(name) {
          kind = sql_string_v1(c.at("type"))
        }
      }
      if kind.is_empty() {
        fail("mismatch:SELECT-configured-column")
      }
      kinds.push(kind)
      let field = source_object_v4(fields[index])
      oids.push(fetch_number_v1(field.at("oid"), 100000000))
      formats.push(fetch_number_v1(field.at("format"), 1))
    }
    if !names.contains(key_name) {
      gaps.push("primary-key-not-delivered")
    }
    for raw_term in terms {
      let term = source_object_v4(raw_term)
      let name = sql_string_v1(term.at("column"))
      if !names.contains(name) {
        gaps.push("predicate-column-not-delivered:" + name)
      }
    }
    if !orm_array(descriptor.at("ordering")).is_empty() {
      gaps.push("ORDER-BY-not-verified-by-this-profile")
    }
    let keys : Map[String, Int32] = Map([])
    for row_index in 0..<delivered {
      work.charge()
      let raw = orm_array(raw_rows[row_index])
      let values : Map[String, Json] = Map([])
      for index, cell in raw {
        work.charge()
        let value = fetch_cell_v1(
          cell,
          kinds[index],
          oids[index],
          formats[index],
        )
        match values.get(names[index]) {
          Some(previous) =>
            if sql_canonical_v1(previous) != sql_canonical_v1(value) {
              witness = {
                "rule": "same-projected-column-consistency",
                "rowIndex": Json(row_index),
                "column": Json(names[index]),
                "firstValue": previous,
                "otherValue": value,
              }
              fail("mismatch:SELECT-duplicate-column-values")
            }
          None => values[names[index]] = value
        }
      }
      match values.get(key_name) {
        None => ()
        Some(key) => {
          let identity = sql_canonical_v1(key)
          match keys.get(identity) {
            None => keys[identity] = row_index
            Some(first) => {
              witness = {
                "rule": "single-table-primary-key-result-uniqueness",
                "column": Json(key_name),
                "key": key,
                "firstRowIndex": Json(first),
                "secondRowIndex": Json(row_index),
              }
              fail("mismatch:SELECT-duplicate-primary-key")
            }
          }
        }
      }
      for raw_term in terms {
        work.charge()
        let term = source_object_v4(raw_term)
        let name = sql_string_v1(term.at("column"))
        match values.get(name) {
          None => ()
          Some(actual) => {
            let expected = source_select_expected_v4(
              term.at("value"),
              bindings,
              work,
            )
            let comparison = source_select_compare_v4(actual, expected)
            let comparison_op = sql_string_v1(term.at("operator"))
            let matched = match comparison_op {
              "eq" => comparison == 0
              "lt" => comparison < 0
              "le" => comparison <= 0
              "gt" => comparison > 0
              "ge" => comparison >= 0
              _ => fail("unsupported:SELECT-predicate-operator")
            }
            if !matched {
              witness = {
                "rule": "returned-row-WHERE-AND",
                "rowIndex": Json(row_index),
                "column": Json(name),
                "operator": Json(comparison_op),
                "observed": actual,
                "expected": expected,
              }
              fail("mismatch:SELECT-row-does-not-satisfy-WHERE")
            }
          }
        }
      }
      checked += 1
    }
    if f.at("completeFetchVerified") != Json(true) {
      gaps.push("fetch-not-exhausted")
    }
    if !gaps.is_empty() {
      fail("unsupported:" + gaps[0])
    }
    "matched-returned-row-constraints"
  } catch {
    error => {
      reason = error.to_string()
      if witness != Json::null() || reason.contains("mismatch:") {
        "mismatch"
      } else if reason.contains("invalid:") {
        "invalid"
      } else {
        "unknown"
      }
    }
  }
  {
    "format": "moontxnwitness-select-returned-row-constraints/v4",
    "semanticContract": "configured-WHERE-AND-and-primary-key-returned-rows/v4-2",
    "algorithm": "independent-returned-row-predicate-and-key-2",
    "counterContract": "select-returned-row-constraint-counters/v4-2",
    "status": Json(status),
    "valid": Json(status == "matched-returned-row-constraints"),
    "returnedRowConstraintsVerified": Json(
      status == "matched-returned-row-constraints",
    ),
    "nativeDeliveryConsistencyVerified": Json(native_consistent),
    "completeNativeResultDelivered": Json(native_complete),
    "resultReference": result_reference,
    "sourceFactsProduced": false,
    "resultSetCompletenessVerified": false,
    "negativeReadSourceVerified": false,
    "sourceAuthenticated": false,
    "isolationModelChecked": false,
    "deliveredRows": Json(delivered),
    "checkedRows": Json(checked),
    "witness": witness,
    "reason": Json(reason),
    "gaps": Json(gaps.map(gap => Json(gap))),
    "execution": {
      "checks": Json(work.checks - start),
      "maxChecks": Json(work.limit),
      "limited": Json(reason.contains("budget:")),
    },
    "scope": "Only delivered rows satisfying configured WHERE AND and single-table primary-key uniqueness; not an exhaustive query result set, database anomaly, authenticated source, or isolation conclusion",
  }
}
