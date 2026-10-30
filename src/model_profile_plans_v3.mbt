///|
priv struct ModelProfileConfigV3 {
  schema : String
  is_list : Bool
  keys : Array[String]
  raw_keys : Array[Json]
  predicates : Array[Array[(String, String)]]
}

///|
priv struct ModelProfilePlanV3 {
  operation : String
  sql : String
  executed : String
  predicate : Array[(String, String)]
}

///|
fn model_identifier_v3(value : Json) -> String raise {
  let text = orm_text(value)
  orm_assert(
    text.length() > 0 && text.length() <= 40,
    "Bounded configured identifier",
  )
  for i, c in text.iter().to_array() {
    orm_assert(
      (c >= 'a' && c <= 'z') || (i > 0 && ((c >= '0' && c <= '9') || c == '_')),
      "Safe lowercase configured identifier",
    )
  }
  text
}

///|
fn model_integer_v3(value : Json) -> String raise {
  match value {
    Number(n, ..) => {
      orm_assert(
        n >= -9007199254740991.0 &&
        n <= 9007199254740991.0 &&
        n.to_int64().to_double() == n,
        "Exact original DBAPI integer",
      )
      n.to_int64().to_string()
    }
    _ => {
      let object = orm_exact(value, ["captureType", "value"])
      orm_equal(
        required(object, "captureType", "integer"),
        Json("int"),
        "Original large integer encoding",
      )
      let text = orm_text(required(object, "value", "integer"))
      ignore(relation_v3_int64(text))
      text
    }
  }
}

///|
fn model_encoded_integer_v3(text : String) -> Json raise {
  let n = relation_v3_int64(text)
  if n >= -9007199254740991L && n <= 9007199254740991L {
    Json(n.to_double())
  } else {
    { "captureType": "int", "value": Json(text) }
  }
}

///|
fn model_config_v3(raw : Json) -> ModelProfileConfigV3 raise {
  let object = orm_exact(raw, ["schema", "model", "keys", "predicates"])
  let schema = model_identifier_v3(required(object, "schema", "configuration"))
  let model = orm_text(required(object, "model", "configuration"))
  orm_assert(
    model == "append-list-v1" || model == "relation-set-v1",
    "One configured model",
  )
  let is_list = model == "append-list-v1"
  let raw_keys = orm_array(required(object, "keys", "configuration"))
  orm_assert(
    raw_keys.length() >= 1 && raw_keys.length() <= 8,
    "One to eight installed keys",
  )
  let keys : Array[String] = []
  for value in raw_keys {
    let key = if is_list {
      model_identifier_v3(value)
    } else {
      model_integer_v3(value)
    }
    orm_assert(!keys.contains(key), "Unique installed domain keys")
    keys.push(key)
  }
  let predicates : Array[Array[(String, String)]] = []
  let configured = orm_array(required(object, "predicates", "configuration"))
  orm_assert(
    configured.length() <= 8 && (!is_list || configured.is_empty()),
    "Bounded relation-only AND plans",
  )
  for raw in configured {
    let parts = orm_array(raw)
    orm_assert(
      parts.length() > 0 && parts.length() <= 8,
      "Bounded nonempty AND plan",
    )
    let terms : Array[(String, String)] = []
    for raw in parts {
      let pair = orm_array(raw)
      orm_assert(pair.length() == 2, "Column/operator pair")
      let column = orm_text(pair[0])
      let op = orm_text(pair[1])
      orm_assert(
        ["id", "balance", "active", "region"].contains(column),
        "Known configured column",
      )
      orm_assert(
        ["eq", "lt", "le", "gt", "ge"].contains(op) &&
        (column != "active" || op == "eq"),
        "Supported configured operator",
      )
      terms.push((column, op))
    }
    orm_assert(!predicates.contains(terms), "Distinct configured plans")
    predicates.push(terms)
  }
  { schema, is_list, keys, raw_keys, predicates, }
}

///|
fn model_plans_v3(
  config : ModelProfileConfigV3,
) -> Array[ModelProfilePlanV3] raise {
  let q = v3_dislock_quote(config.schema)
  let table = q + ".\"business\""
  if config.is_list {
    let read = "SELECT items FROM " + table + " WHERE key=%s"
    let append = "UPDATE " +
      table +
      " SET items=items || %s::jsonb WHERE key=%s RETURNING items"
    return [
      { operation: "list-read", sql: read, executed: read, predicate: [], },
      {
        operation: "list-append",
        sql: append,
        executed: append,
        predicate: [],
      },
    ]
  }
  let fields = "id,balance,active,region"
  let read = "SELECT " + fields + " FROM " + table + " WHERE id=%s"
  let insert = "INSERT INTO " +
    table +
    "(id,balance,active,region) VALUES(%s,%s,%s,%s) RETURNING " +
    fields
  let update = "UPDATE " +
    table +
    " SET balance=%s,active=%s,region=%s WHERE id=%s"
  let delete = "DELETE FROM " + table + " WHERE id=%s"
  let result : Array[ModelProfilePlanV3] = [
    {
      operation: "row-read",
      sql: read,
      executed: "SELECT " + fields + ",version FROM " + table + " WHERE id=%s",
      predicate: [("id", "eq")],
    },
    {
      operation: "row-insert",
      sql: insert,
      executed: insert + ",version," + q + ".\"predecessor\"(version)",
      predicate: [],
    },
    {
      operation: "row-update",
      sql: update + " RETURNING " + fields,
      executed: update +
      " RETURNING WITH (OLD AS o,NEW AS n) n.id,n.balance,n.active,n.region,n.version,o.version",
      predicate: [],
    },
    {
      operation: "row-delete",
      sql: delete + " RETURNING " + fields,
      executed: delete +
      " RETURNING WITH (OLD AS o,NEW AS n) o.id,o.balance,o.active,o.region," +
      q +
      ".\"delete_token\"(o.id,o.version),o.version",
      predicate: [],
    },
  ]
  for predicate in config.predicates {
    let clauses : Array[String] = []
    for term in predicate {
      let op = match term.1 {
        "eq" => "="
        "lt" => "<"
        "le" => "<="
        "gt" => ">"
        _ => ">="
      }
      clauses.push(
        v3_dislock_quote(term.0) +
        (if term.0 == "region" { " COLLATE \"C\"" } else { "" }) +
        op +
        "%s",
      )
    }
    let suffix = " FROM " +
      table +
      " WHERE " +
      clauses.join(" AND ") +
      " ORDER BY id"
    result.push({
      operation: "row-read",
      sql: "SELECT " + fields + suffix,
      executed: "SELECT " + fields + ",version" + suffix,
      predicate,
    })
  }
  result
}

///|
fn model_string_v3(raw : Json, maximum : Int32) -> String raise {
  orm_native_text(raw, maximum)
}

///|
fn model_list_item_v3(raw : Json) -> Json raise {
  let item = orm_exact(raw, ["id", "value"])
  orm_assert(
    !model_string_v3(required(item, "id", "item"), 128).is_empty(),
    "Nonempty append identity",
  )
  ignore(model_string_v3(required(item, "value", "item"), 1024))
  raw
}

///|
fn model_parameters_v3(
  config : ModelProfileConfigV3,
  plan : ModelProfilePlanV3,
  raw : Json,
) -> Array[Json] raise {
  let params = orm_array(raw)
  let values : Array[Json] = []
  if config.is_list {
    orm_assert(
      params.length() == (if plan.operation == "list-read" { 1 } else { 2 }),
      "Exact list parameter arity",
    )
    let key = orm_text(params[params.length() - 1])
    orm_assert(config.keys.contains(key), "Known installed list key")
    if plan.operation == "list-append" {
      let items = orm_array(guarded_json(orm_text(params[0]), limit=8192))
      orm_assert(items.length() == 1, "One actual append item")
      values.push(model_list_item_v3(items[0]))
    }
    values.push(Json(key))
  } else if plan.operation == "row-read" {
    orm_assert(
      params.length() == plan.predicate.length(),
      "Exact predicate parameter arity",
    )
    for i, term in plan.predicate {
      let value = params[i]
      if term.0 == "id" || term.0 == "balance" {
        values.push(Json(model_integer_v3(value)))
      } else if term.0 == "active" {
        match value {
          True | False => values.push(value)
          _ => fail("Original bool predicate required")
        }
      } else {
        values.push(Json(model_string_v3(value, 1024)))
      }
    }
  } else {
    orm_assert(
      params.length() == (if plan.operation == "row-delete" { 1 } else { 4 }),
      "Exact point write parameter arity",
    )
    let key_index = if plan.operation == "row-insert" {
      0
    } else {
      params.length() - 1
    }
    let key = model_integer_v3(params[key_index])
    orm_assert(config.keys.contains(key), "Write key in installed domain")
    if plan.operation != "row-delete" {
      let offset = if plan.operation == "row-insert" { 1 } else { 0 }
      values.push(Json(model_integer_v3(params[offset])))
      match params[offset + 1] {
        True | False => ()
        _ => fail("Original row boolean required")
      }
      values.push(params[offset + 1])
      values.push(Json(model_string_v3(params[offset + 2], 1024)))
    }
    values.push(Json(key))
  }
  values
}

///|
fn model_native_rows_v3(
  batch : Map[String, Json],
  config : ModelProfileConfigV3,
  plan : ModelProfilePlanV3,
) -> Array[Array[Json]] raise {
  let actual = orm_exact(required(batch, "actualPGresult", "batch"), [
    "status", "commandTag", "commandTuples", "nfields", "ntuples", "fields", "rawRows",
  ])
  let raw_rows = orm_array(required(actual, "rawRows", "result"))
  let fields = orm_array(required(actual, "fields", "result"))
  let width = if config.is_list {
    1
  } else if plan.operation == "row-read" {
    5
  } else {
    6
  }
  orm_assert(
    raw_rows.length() <= 128 && fields.length() == width,
    "Bounded native model result shape",
  )
  let oids = if config.is_list {
    [3802]
  } else if width == 5 {
    [20, 20, 16, 25, 2950]
  } else {
    [20, 20, 16, 25, 2950, 2950]
  }
  for i, raw in fields {
    let field = orm_exact(raw, ["oid", "format", "typmod"])
    orm_equal(
      required(field, "oid", "field"),
      Json(oids[i]),
      "Fixed native model OID",
    )
    orm_equal(
      required(field, "format", "field"),
      Json(0),
      "Native text result format",
    )
    orm_equal(
      required(field, "typmod", "field"),
      Json(-1),
      "Native unconstrained source typmod",
    )
  }
  orm_equal(required(actual, "status", "result"), Json(2), "Native TUPLES_OK")
  orm_equal(
    required(actual, "ntuples", "result"),
    Json(raw_rows.length()),
    "Native row count",
  )
  orm_equal(
    required(actual, "nfields", "result"),
    Json(width),
    "Native field count",
  )
  orm_equal(
    required(actual, "commandTuples", "result"),
    Json(raw_rows.length()),
    "Native command tuple count",
  )
  orm_equal(
    required(batch, "rowcount", "batch"),
    Json(raw_rows.length()),
    "Original affected/result count",
  )
  let tag = if plan.operation == "row-insert" {
    "INSERT 0 "
  } else if plan.operation == "row-update" || plan.operation == "list-append" {
    "UPDATE "
  } else if plan.operation == "row-delete" {
    "DELETE "
  } else {
    "SELECT "
  }
  orm_equal(
    required(batch, "commandTag", "batch"),
    Json(tag + raw_rows.length().to_string()),
    "Actual model command tag",
  )
  orm_equal(
    orm_raw_text(required(actual, "commandTag", "result")),
    required(batch, "commandTag", "batch"),
    "Native/original command tag",
  )
  if config.is_list || plan.operation != "row-read" {
    orm_assert(
      raw_rows.length() == 1,
      "Zero/multirow point effects are unproved conditions",
    )
  }
  let result : Array[Array[Json]] = []
  for raw in raw_rows {
    let wire = orm_array(raw)
    orm_assert(wire.length() == width, "Native source row width")
    let cells : Array[Json] = []
    for i, value in wire {
      let text = orm_raw_text(value)
      if text == Json::null() {
        orm_assert(
          !config.is_list && i == 5 && plan.operation == "row-insert",
          "Only absent predecessor may be SQL NULL",
        )
        cells.push(Json::null())
      } else if oids[i] == 20 {
        let integer = orm_text(text)
        ignore(relation_v3_int64(integer))
        cells.push(Json(integer))
      } else if oids[i] == 2950 {
        cells.push(Json(orm_uuid(text)))
      } else {
        cells.push(orm2_decode_cell(value, oids[i]))
      }
    }
    result.push(cells)
  }
  result
}
