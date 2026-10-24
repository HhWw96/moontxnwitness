///|
priv struct ModelProfileWindowV3 {
  initial : Array[Json]
  final_rows : Array[Json]
  final_state : Array[Json]
  ledger : Array[Json]
}

///|
fn model_control_rows_v3(control : OrmControl2) -> Array[Json] raise {
  control.rows.map(row => {
    let row = orm_array(row)
    orm_assert(row.length() == 1, "One native JSONB control column")
    row[0]
  })
}

///|
fn model_catalog_v3(
  config : ModelProfileConfigV3,
  functions : Array[Json],
  triggers : Array[Json],
) -> Unit raise {
  let statements = model_ddl_v3(config.schema, config.is_list)
  let offset = if config.is_list { 4 } else { 6 }
  let names = if config.is_list {
    ["before", "after"]
  } else {
    ["before", "after", "predecessor", "delete_token"]
  }
  let expected : Array[Json] = []
  for i, name in names {
    let parts = statements[offset + i].split(" AS $model$").to_array()
    orm_assert(parts.length() == 2, "Reviewed fixed function delimiter")
    let body = parts[1].to_owned().replace_all(old="$model$", new="")
    let args = if name == "predecessor" {
      "v uuid"
    } else if name == "delete_token" {
      "k bigint, p uuid"
    } else {
      ""
    }
    expected.push({
      "name": name.to_json(),
      "body": body.to_json(),
      "securityDefiner": false,
      "volatility": "v",
      "config": ["search_path=pg_catalog"],
      "arguments": args.to_json(),
      "return": (if i < 2 { "trigger" } else { "uuid" }).to_json(),
      "language": "plpgsql",
    })
  }
  orm_set_equal(functions.to_json(), expected, "Owned source function identity")
  let expected_triggers : Array[Json] = [
    {
      "name": "model_before",
      "function": "before",
      "type": 31,
      "enabled": "O",
      "args": "",
      "internal": false,
      "noPredicate": true,
    },
    {
      "name": "model_after",
      "function": "after",
      "type": (if config.is_list { 17 } else { 29 }).to_json(),
      "enabled": "O",
      "args": "",
      "internal": false,
      "noPredicate": true,
    },
  ]
  if config.is_list {
    // The reviewed identities -> business FK creates exactly two internal
    // no-action triggers on the referenced business table. Their suffix is a
    // database-assigned OID, not a semantic identity or write-order source.
    let seen : Map[String, Bool] = Map([])
    for raw in triggers {
      if orm_get(raw, "internal") != true.to_json() {
        continue
      }
      let trigger = orm_exact(raw, [
        "name", "function", "type", "enabled", "args", "internal", "noPredicate",
      ])
      let name = orm_text(required(trigger, "name", "trigger"))
      let prefix = "RI_ConstraintTrigger_a_"
      orm_assert(name.has_prefix(prefix), "Owned internal FK trigger name")
      let suffix = name.replace_all(old=prefix, new="")
      let oid = v3_capture_seq(
        guarded_json(suffix, limit=16),
        "internal FK OID",
      )
      orm_assert(
        oid <= 4294967295L,
        "Bounded database-assigned internal trigger OID",
      )
      let function = orm_text(required(trigger, "function", "trigger"))
      orm_assert(
        !seen.contains(function) &&
        ["RI_FKey_noaction_del", "RI_FKey_noaction_upd"].contains(function),
        "Exactly the two reviewed internal no-action FK hooks",
      )
      seen[function] = true
      orm_equal(
        raw,
        {
          "name": name.to_json(),
          "function": function.to_json(),
          "type": (if function == "RI_FKey_noaction_del" { 9 } else { 17 }).to_json(),
          "enabled": "O",
          "args": "",
          "internal": true,
          "noPredicate": true,
        },
        "Actual internal FK hook definition",
      )
      expected_triggers.push(raw)
    }
    orm_assert(
      seen.length() == 2,
      "Both actual FK enforcement hooks are present",
    )
  }
  orm_set_equal(
    triggers.to_json(),
    expected_triggers,
    "Owned source trigger identity",
  )
}

///|
fn model_window_controls_v3(
  config : ModelProfileConfigV3,
  controls : Array[OrmControl2],
  raw : Json,
  phase : String,
) -> (Array[Json], Array[Json], Array[Json]) raise {
  orm_assert(
    controls.length() == 9,
    "Exactly nine original locked-window control observations",
  )
  let window = orm_exact(raw, [
    "phase", "queries", "snapshot", "ledger", "state", "catalog", "triggers", "locale",
    "snapshotRows", "ledgerRows", "stateRows", "catalogRows", "triggerRows", "localeRows",
  ])
  orm_equal(
    required(window, "phase", "window"),
    phase.to_json(),
    "Window phase",
  )
  orm_equal(
    required(window, "queries", "window"),
    controls.map(c => c.seq.to_double().to_json()).to_json(),
    "All original window query references",
  )
  let cursor : OrmControlCursor2 = { controls, at: 0, verified: [], }
  ignore(orm2_command(cursor, "BEGIN", Json::null(), "BEGIN", None))
  ignore(
    orm2_command(
      cursor,
      model_control_sql_v3("lock", config.schema, config.is_list),
      Json::null(),
      "LOCK TABLE",
      None,
    ),
  )
  let observed : Map[String, Array[Json]] = Map([])
  for name in ["snapshot", "ledger", "state", "catalog", "triggers", "locale"] {
    let params = if name == "catalog" {
      [config.schema.to_json()].to_json()
    } else if name == "triggers" {
      [(v3_dislock_quote(config.schema) + ".\"business\"").to_json()].to_json()
    } else {
      Json::null()
    }
    let query = orm2_select(
      cursor,
      model_control_sql_v3(name, config.schema, config.is_list),
      params,
      ["jsonb_build_object"],
      [3802],
    )
    orm_equal(
      required(window, name, "window"),
      query.seq.to_double().to_json(),
      "Exact original window source sequence",
    )
    let row_field = if name == "triggers" {
      "triggerRows"
    } else {
      name + "Rows"
    }
    orm_equal(
      required(window, row_field, "window"),
      query.rows.to_json(),
      "Redundant declared rows equal independently decoded native control",
    )
    observed[name] = model_control_rows_v3(query)
  }
  ignore(orm2_command(cursor, "COMMIT", Json::null(), "COMMIT", None))
  model_catalog_v3(config, observed["catalog"], observed["triggers"])
  orm_equal(
    observed["locale"].to_json(),
    [{ "collate": "C", "ctype": "C" }].to_json(),
    "Supported C database comparison rules",
  )
  (observed["snapshot"], observed["state"], observed["ledger"])
}

///|
fn model_initial_row_v3(
  raw : Json,
  config : ModelProfileConfigV3,
) -> Json raise {
  let row = orm_exact(raw, ["key", "version", "values"])
  let key = orm_text(required(row, "key", "row"))
  ignore(relation_v3_int64(key))
  orm_assert(
    config.keys.contains(key),
    "Initial row lies in installed key domain",
  )
  ignore(orm_uuid(required(row, "version", "row")))
  let values = orm_exact(required(row, "values", "row"), [
    "balance", "active", "region",
  ])
  ignore(relation_v3_int64(orm_text(required(values, "balance", "values"))))
  match required(values, "active", "values") {
    True | False => ()
    _ => fail("Native initial boolean")
  }
  ignore(model_string_v3(required(values, "region", "values"), 1024))
  raw
}

///|
fn model_controls_v3(
  config : ModelProfileConfigV3,
  installation : Map[String, Json],
  final_record : Map[String, Json],
  initial_controls : Array[OrmControl2],
  final_controls : Array[OrmControl2],
) -> ModelProfileWindowV3 raise {
  orm_assert(
    initial_controls.length() > 9 && final_controls.length() == 9,
    "Complete installation and both source windows",
  )
  let boundary = initial_controls.length() - 9
  for control in initial_controls {
    orm_assert(
      control.connection == initial_controls[0].connection &&
      control.backend == initial_controls[0].backend,
      "One original setup connection/backend from installation through initialization",
    )
  }
  let install_controls = initial_controls.filter(c => {
    c.seq < initial_controls[boundary].seq
  })
  let snapshot_controls = initial_controls.filter(c => {
    c.seq >= initial_controls[boundary].seq
  })
  orm_equal(
    required(installation, "installationQueries", "installation"),
    install_controls.map(c => c.seq.to_double().to_json()).to_json(),
    "Exact installation control references",
  )
  let cursor : OrmControlCursor2 = {
    controls: install_controls,
    at: 0,
    verified: [],
  }
  ignore(orm2_command(cursor, "BEGIN", Json::null(), "BEGIN", None))
  let statements = model_ddl_v3(config.schema, config.is_list)
  for i in 0..<(statements.length() - 2) {
    let sql = statements[i]
    let tag = if sql.has_prefix("CREATE SCHEMA ") {
      "CREATE SCHEMA"
    } else if sql.has_prefix("CREATE TABLE ") {
      "CREATE TABLE"
    } else if sql.has_prefix("CREATE UNIQUE INDEX ") {
      "CREATE INDEX"
    } else {
      "CREATE FUNCTION"
    }
    ignore(orm2_command(cursor, sql, Json::null(), tag, None))
  }
  let table = v3_dislock_quote(config.schema) + ".\"business\""
  let seeds : Map[String, Json] = Map([])
  if config.is_list {
    for raw_key in config.raw_keys {
      ignore(
        orm2_command(
          cursor,
          "INSERT INTO " + table + " VALUES(%s,%s::jsonb)",
          [raw_key, "[]".to_json()].to_json(),
          "INSERT 0 1",
          Some(1),
        ),
      )
    }
  } else {
    let sql = "INSERT INTO " + table + " VALUES(%s,%s,%s,%s,gen_random_uuid())"
    let insert = model_plans_v3(config)[1]
    while cursor.at < cursor.controls.length() &&
          cursor.controls[cursor.at].sql == sql {
      let params = cursor.controls[cursor.at].parameters
      let values = model_parameters_v3(config, insert, params)
      let key = orm_text(values[3])
      orm_assert(!seeds.contains(key), "Unique initial row insertion")
      seeds[key] = {
        "balance": values[0],
        "active": values[1],
        "region": values[2],
      }
      ignore(orm2_command(cursor, sql, params, "INSERT 0 1", Some(1)))
    }
    let state = v3_dislock_quote(config.schema) + ".\"state\""
    for i, key in config.keys {
      let present = seeds.contains(key)
      ignore(
        orm2_command(
          cursor,
          "INSERT INTO " +
          state +
          " SELECT %s,version,true FROM " +
          table +
          " WHERE id=%s",
          [config.raw_keys[i], config.raw_keys[i]].to_json(),
          if present {
            "INSERT 0 1"
          } else {
            "INSERT 0 0"
          },
          Some(if present { 1 } else { 0 }),
        ),
      )
      ignore(
        orm2_command(
          cursor,
          "INSERT INTO " +
          state +
          " VALUES(%s,NULL,false) ON CONFLICT DO NOTHING",
          [config.raw_keys[i]].to_json(),
          if present {
            "INSERT 0 0"
          } else {
            "INSERT 0 1"
          },
          Some(if present { 0 } else { 1 }),
        ),
      )
    }
  }
  for i in (statements.length() - 2)..<statements.length() {
    ignore(
      orm2_command(cursor, statements[i], Json::null(), "CREATE TRIGGER", None),
    )
  }
  ignore(orm2_command(cursor, "COMMIT", Json::null(), "COMMIT", None))
  orm_assert(
    cursor.at == cursor.controls.length(),
    "No unverified installation SQL",
  )
  let (initial, initial_state, initial_ledger) = model_window_controls_v3(
    config,
    snapshot_controls,
    required(installation, "window", "installation"),
    "initial",
  )
  let (final_rows, final_state, ledger) = model_window_controls_v3(
    config,
    final_controls,
    required(final_record, "window", "finalization"),
    "final",
  )
  orm_assert(initial_ledger.is_empty(), "Initial actual-effect ledger is empty")
  if config.is_list {
    orm_set_equal(
      initial.to_json(),
      config.keys.map(key => { "key": key.to_json(), "items": [] }),
      "Complete initially empty list domain",
    )
    orm_assert(
      initial_state.is_empty(),
      "No initial append identity is invented",
    )
  } else {
    orm_assert(
      initial.length() == seeds.length(),
      "Complete initial native relation snapshot",
    )
    let rows : Map[String, Json] = Map([])
    for raw in initial {
      let row = model_initial_row_v3(raw, config)
      let key = orm_text(orm_get(row, "key"))
      orm_assert(
        !rows.contains(key) && seeds.contains(key),
        "Unique independently seeded initial row",
      )
      orm_equal(
        orm_get(row, "values"),
        seeds[key],
        "Seed parameters/native initial image",
      )
      rows[key] = row
    }
    let expected : Array[Json] = []
    for key in config.keys {
      expected.push({
        "key": key.to_json(),
        "version": if rows.contains(key) {
          orm_get(rows[key], "version")
        } else {
          Json::null()
        },
        "present": rows.contains(key).to_json(),
      })
    }
    orm_set_equal(
      initial_state.to_json(),
      expected,
      "Complete initialized source state including absent keys",
    )
  }
  { initial, final_rows, final_state, ledger, }
}
