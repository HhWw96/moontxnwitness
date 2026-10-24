///|
priv struct ModelProfileFactV3 {
  statement : Int64
  rows : Array[Int64]
  event : Json
  effect : Json
}

///|
fn model_row_v3(cells : Array[Json]) -> Json {
  {
    "key": cells[0],
    "version": cells[4],
    "values": { "balance": cells[1], "active": cells[2], "region": cells[3] },
  }
}

///|
fn model_business_v3(cells : Array[Json], is_list : Bool) -> Json raise {
  if is_list {
    return [cells[0]].to_json()
  }
  [
    model_encoded_integer_v3(orm_text(cells[0])),
    model_encoded_integer_v3(orm_text(cells[1])),
    cells[2],
    cells[3],
  ].to_json()
}

///|
fn model_predicate_match_v3(
  cells : Array[Json],
  plan : ModelProfilePlanV3,
  params : Array[Json],
) -> Unit raise {
  for i, term in plan.predicate {
    let position = if term.0 == "id" {
      0
    } else if term.0 == "balance" {
      1
    } else if term.0 == "active" {
      2
    } else {
      3
    }
    let kind = if position < 2 {
      "int64"
    } else if position == 2 {
      "bool"
    } else {
      "text"
    }
    let comparison = relation_v3_compare(
      relation_v3_cell(cells[position], kind),
      relation_v3_cell(params[i], kind),
    )
    let matches = match term.1 {
      "eq" => comparison == 0
      "lt" => comparison < 0
      "le" => comparison <= 0
      "gt" => comparison > 0
      _ => comparison >= 0
    }
    orm_assert(
      matches, "Actual returned row satisfies its original SQL predicate",
    )
  }
}

///|
fn model_fact_v3(
  config : ModelProfileConfigV3,
  raw : Json,
  events : Array[Json],
) -> ModelProfileFactV3 raise {
  let batch = orm_exact(raw, [
    "sourceSeq", "kind", "statement", "tx", "operation", "originalSql", "executedSql",
    "parameters", "actualPGresult", "businessColumns", "commandTag", "rowcount",
    "businessRowsEvents", "deliveredRows", "resultComplete",
  ])
  let statement = v3_capture_seq(
    required(batch, "statement", "batch"),
    "original statement",
  )
  orm_assert(statement.to_int() <= events.length(), "Original statement exists")
  let original = object_fields(events[statement.to_int() - 1], "statement")
  orm_equal(
    required(original, "kind", "statement"),
    "statement".to_json(),
    "Actual raw statement",
  )
  orm_equal(
    required(original, "tx", "statement"),
    required(batch, "tx", "batch"),
    "Original statement transaction",
  )
  let sql = orm_text(required(batch, "originalSql", "batch"))
  let mut selected : ModelProfilePlanV3? = None
  for plan in model_plans_v3(config) {
    if plan.sql == sql {
      orm_assert(selected is None, "Unambiguous independently registered SQL")
      selected = Some(plan)
    }
  }
  let plan = match selected {
    Some(plan) => plan
    None => fail("Original SQL is outside independently configured plans")
  }
  orm_equal(
    required(batch, "operation", "batch"),
    plan.operation.to_json(),
    "Operation derived from actual SQL",
  )
  orm_equal(
    required(original, "sql", "statement"),
    plan.sql.to_json(),
    "Original SQL bytes",
  )
  orm_equal(
    required(original, "executedSql", "statement"),
    plan.executed.to_json(),
    "Same-statement executed SQL",
  )
  orm_equal(
    required(batch, "executedSql", "batch"),
    plan.executed.to_json(),
    "Independent executed SQL derivation",
  )
  orm_equal(
    required(original, "mappingId", "statement"),
    ("configured-model/" + plan.operation).to_json(),
    "Typed source mapping identity",
  )
  orm_equal(
    required(original, "parameters", "statement"),
    required(batch, "parameters", "batch"),
    "Original driver parameters",
  )
  let params = model_parameters_v3(
    config,
    plan,
    required(batch, "parameters", "batch"),
  )
  let native = model_native_rows_v3(batch, config, plan)
  let expected_columns : Json = if config.is_list {
    [{ "name": "items", "typeCode": 3802 }]
  } else {
    [
      { "name": "id", "typeCode": 20 },
      { "name": "balance", "typeCode": 20 },
      { "name": "active", "typeCode": 16 },
      { "name": "region", "typeCode": 25 },
    ]
  }
  orm_equal(
    required(batch, "businessColumns", "batch"),
    expected_columns,
    "Original business column layout",
  )
  orm_equal(
    required(batch, "resultComplete", "batch"),
    true.to_json(),
    "Actual source result completed",
  )
  orm_equal(
    required(batch, "deliveredRows", "batch"),
    native.length().to_json(),
    "All native rows actually delivered",
  )
  let raw_refs = orm_array(required(batch, "businessRowsEvents", "batch"))
  orm_assert(
    !raw_refs.is_empty() && raw_refs.length() <= 128,
    "Bounded actual delivery references",
  )
  let rows : Array[Int64] = []
  let delivered : Array[Json] = []
  let mut previous = statement
  for i, reference in raw_refs {
    let seq = v3_capture_seq(reference, "actual rows event")
    orm_assert(
      seq > previous && seq.to_int() <= events.length(),
      "Actual delivery references are unique, ordered and after execute",
    )
    previous = seq
    let event = object_fields(events[seq.to_int() - 1], "actual rows")
    orm_equal(
      required(event, "kind", "rows"),
      "rows".to_json(),
      "Actual business rows event",
    )
    orm_equal(
      required(event, "tx", "rows"),
      required(batch, "tx", "batch"),
      "Delivered original transaction",
    )
    orm_equal(
      required(event, "statement", "rows"),
      statement.to_double().to_json(),
      "Delivered original statement",
    )
    orm_equal(
      required(event, "columns", "rows"),
      expected_columns,
      "Unchanged delivered business columns",
    )
    orm_equal(
      required(event, "complete", "rows"),
      (i == raw_refs.length() - 1).to_json(),
      "Exactly one final actual delivery boundary",
    )
    orm_assert(
      !event.contains("error") && !event.contains("serverRows"),
      "No fabricated delivery, raw error or unverified extra projection",
    )
    for row in orm_array(required(event, "rows", "rows")) {
      delivered.push(row)
    }
    rows.push(seq)
  }
  orm_equal(
    delivered.to_json(),
    native.map(cells => model_business_v3(cells, config.is_list)).to_json(),
    "Native/business delivery equality without early consumption",
  )
  let tx = required(batch, "tx", "batch")
  let mut result : Json = Json::null()
  let mut effect : Json = Json::null()
  if config.is_list {
    let key = params[params.length() - 1]
    let items = orm_array(native[0][0])
    for item in items {
      ignore(model_list_item_v3(item))
    }
    if plan.operation == "list-read" {
      result = {
        "kind": "list_read",
        "tx": tx,
        "key": key,
        "items": items.to_json(),
      }
    } else {
      orm_assert(
        !items.is_empty() && items[items.length() - 1] == params[0],
        "Actual append tail equals its original unique item",
      )
      result = {
        "kind": "append",
        "tx": tx,
        "key": key,
        "id": orm_get(params[0], "id"),
        "value": orm_get(params[0], "value"),
      }
      effect = { "key": key, "item": params[0], "items": items.to_json() }
    }
  } else if plan.operation == "row-read" {
    let returned : Array[Json] = []
    let keys : Map[String, Bool] = Map([])
    for cells in native {
      let key = orm_text(cells[0])
      orm_assert(
        config.keys.contains(key) && !keys.contains(key),
        "Returned unique row lies in installed source domain",
      )
      keys[key] = true
      model_predicate_match_v3(cells, plan, params)
      returned.push(model_row_v3(cells))
    }
    let predicate : Array[Json] = []
    for i, term in plan.predicate {
      predicate.push({
        "column": term.0.to_json(),
        "op": term.1.to_json(),
        "value": params[i],
      })
    }
    result = {
      "kind": "row_read",
      "tx": tx,
      "relation": "business",
      "predicate": predicate.to_json(),
      "rows": returned.to_json(),
      "complete": true,
    }
  } else {
    let cells = native[0]
    let key = params[params.length() - 1]
    orm_equal(cells[0], key, "Actual point write affects original key")
    let deleted = plan.operation == "row-delete"
    let action = if deleted {
      "delete"
    } else if plan.operation == "row-insert" {
      "insert"
    } else {
      "update"
    }
    let image : Json = if deleted {
      Json::null()
    } else {
      { "balance": cells[1], "active": cells[2], "region": cells[3] }
    }
    if !deleted {
      orm_equal(
        image,
        { "balance": params[0], "active": params[1], "region": params[2] },
        "Actual row effect equals original write parameters",
      )
    }
    result = {
      "kind": "row_write",
      "tx": tx,
      "relation": "business",
      "key": key,
      "action": action.to_json(),
      "version": cells[4],
      "predecessor": cells[5],
      "values": image,
    }
    effect = {
      "key": key,
      "version": cells[4],
      "predecessor": cells[5],
      "action": action.to_upper().to_json(),
      "oldPresent": (action != "insert").to_json(),
      "newPresent": (!deleted).to_json(),
      "values": image,
    }
  }
  { statement, rows, event: result, effect, }
}

///|
fn model_projection_v3(
  config : ModelProfileConfigV3,
  records : Array[Json],
  original : Array[Json],
  source : ModelProfileWindowV3,
  transactions : Array[Json],
  clock : Json,
) -> (Json, Array[Json], Array[Json]) raise {
  let by_statement : Map[Int64, ModelProfileFactV3] = Map([])
  let by_rows : Map[Int64, ModelProfileFactV3] = Map([])
  let committed : Map[String, Bool] = Map([])
  for tx in transactions {
    let status = orm_text(orm_get(tx, "status"))
    orm_assert(
      status == "committed" || status == "aborted",
      "All model transactions have confirmed outcomes",
    )
    committed[orm_text(orm_get(tx, "id"))] = status == "committed"
  }
  let effects : Array[Json] = []
  let append_ids : Map[String, Bool] = Map([])
  for raw in records {
    if orm_get(raw, "kind") != "source-batch".to_json() {
      continue
    }
    let fact = model_fact_v3(config, raw, original)
    orm_assert(
      !by_statement.contains(fact.statement),
      "One original execute has exactly one source batch",
    )
    by_statement[fact.statement] = fact
    for seq in fact.rows {
      orm_assert(
        !by_rows.contains(seq),
        "Each original delivery belongs to exactly one source batch",
      )
      by_rows[seq] = fact
    }
    if config.is_list && orm_get(fact.event, "kind") == "append".to_json() {
      let id = orm_text(orm_get(fact.event, "id"))
      orm_assert(
        !append_ids.contains(id),
        "Append identities remain unique even across rolled-back attempts",
      )
      append_ids[id] = true
    }
    let tx = orm_text(orm_get(fact.event, "tx"))
    orm_assert(
      committed.contains(tx),
      "Source batch transaction exists in original lifecycle",
    )
    if committed[tx] && fact.effect != Json::null() {
      effects.push(fact.effect)
    }
  }
  orm_assert(
    !by_statement.is_empty(),
    "At least one original supported SQL operation",
  )
  let events : Array[Json] = []
  let origins : Array[Json] = []
  let initial : Json = if config.is_list {
    let values : Map[String, Json] = Map([])
    for key in config.keys {
      values[key] = Json::array([])
    }
    values.to_json()
  } else {
    { "business": source.initial.to_json() }
  }
  let mut used_statements = 0
  let mut used_rows = 0
  for i, raw in original {
    let event = object_fields(raw, "original event")
    let seq = v3_capture_seq(required(event, "seq", "event"), "original event")
    orm_assert(
      seq == (i + 1).to_int64(),
      "Original journal sequence remains contiguous",
    )
    let kind = orm_text(required(event, "kind", "event"))
    let mut derived : Json = Json::null()
    if kind == "statement" {
      orm_assert(
        by_statement.contains(seq),
        "Every original SQL statement has an independently proven mapping",
      )
      used_statements += 1
      continue
    } else if kind == "rows" {
      let fact = match by_rows.get(seq) {
        Some(fact) => fact
        None =>
          fail("Every actual delivered rows event has a unique original source")
      }
      used_rows += 1
      if seq != fact.rows[fact.rows.length() - 1] {
        continue
      }
      let copy = list_v3_copy(object_fields(fact.event, "proven model fact"))
      copy["time"] = required(event, "time", "actual delivery")
      derived = copy.to_json()
    } else if kind == "snapshot" {
      orm_assert(
        i == 0,
        "Only the original initial diagnostic snapshot is replaced in the separate derived trace",
      )
      derived = {
        "kind": "snapshot",
        "initial": initial,
        "consistent": true,
        "time": required(event, "time", "snapshot"),
      }
    } else {
      orm_assert(
        ["begin", "commit_request", "commit_ok", "rollback_ok"].contains(kind),
        "Unsupported controls, hand-authored model facts or unknown outcomes remain diagnostic",
      )
      orm_assert(
        !event.contains("commitResponse"),
        "Server-abort/unknown commit paths require a separately verified protocol",
      )
      derived = raw
    }
    let copy = list_v3_copy(object_fields(derived, "derived event"))
    copy["seq"] = (events.length() + 1).to_json()
    events.push(copy.to_json())
    origins.push(seq.to_double().to_json())
  }
  orm_assert(
    used_statements == by_statement.length() && used_rows == by_rows.length(),
    "Exact all-statements/all-deliveries source bijection",
  )
  let trace : Json = {
    "traceSchema": 3,
    "dataModel": (if config.is_list {
      "append-list-v1"
    } else {
      "relation-set-v1"
    }).to_json(),
    "clockDomain": clock,
    "scope": { "exclusiveWriters": true },
    "events": events.to_json(),
    "gaps": [],
  }
  if !config.is_list {
    let fields = object_fields_unchecked_v3(trace)
    fields["relationSchema"] = {
      "business": {
        "primaryKey": "id",
        "columns": {
          "id": "int64",
          "balance": "int64",
          "active": "bool",
          "region": "text",
        },
      },
    }
    object_fields_unchecked_v3(fields["scope"])["completeSnapshotTables"] = [
      "business",
    ].to_json()
  }
  (trace, origins, effects)
}
