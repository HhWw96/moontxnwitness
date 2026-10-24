///|
fn model_expect_reject_v3(action : () -> Unit raise) -> Unit raise {
  let rejected = try {
    action()
    false
  } catch {
    _ => true
  }
  assert_true(rejected)
}

///|
fn model_test_config_v3(is_list? : Bool = false) -> ModelProfileConfigV3 raise {
  model_config_v3(
    if is_list {
      {
        "schema": "model_test",
        "model": "append-list-v1",
        "keys": ["x", "y"],
        "predicates": [],
      }
    } else {
      {
        "schema": "model_test",
        "model": "relation-set-v1",
        "keys": [1, 2],
        "predicates": [[["active", "eq"], ["balance", "ge"]]],
      }
    },
  )
}

///|
test "configured model raw unknown envelope remains inconclusive" {
  let report = guarded_json(
    model_profile_source_v3_json("{}", "{}"),
    limit=1048576,
  )
  assert_eq(orm_get(report, "status"), "inconclusive".to_json())
  assert_eq(orm_get(report, "analysisCoverageAccepted"), false.to_json())
  assert_eq(orm_get(report, "derivedTrace"), Json::null())
}

///|
test "configured model unsafe schema rejected" {
  for name in ["UPPER", "bad;sql", "_hidden", "bad\"quoted"] {
    model_expect_reject_v3(fn() raise {
      ignore(model_identifier_v3(name.to_json()))
    })
  }
}

///|
test "configured model canonical int64 boundaries retain exact source encoding" {
  for text in ["-9223372036854775808", "9223372036854775807", "0", "-1"] {
    assert_eq(model_integer_v3(model_encoded_integer_v3(text)), text)
  }
  model_expect_reject_v3(fn() raise { ignore(model_integer_v3(true.to_json())) })
  model_expect_reject_v3(fn() raise { ignore(model_integer_v3(1.5.to_json())) })
}

///|
test "configured model integer overflow rejected" {
  model_expect_reject_v3(fn() raise {
    ignore(
      model_integer_v3({ "captureType": "int", "value": "9223372036854775808" }),
    )
  })
}

///|
test "configured model list identity differs from repeated business value" {
  let a = model_list_item_v3({ "id": "a", "value": "same" })
  let b = model_list_item_v3({ "id": "b", "value": "same" })
  assert_true(a != b)
  assert_eq(orm_get(a, "value"), orm_get(b, "value"))
}

///|
test "configured model nonstring list value rejected" {
  model_expect_reject_v3(fn() raise {
    ignore(model_list_item_v3({ "id": "a", "value": 7 }))
  })
  model_expect_reject_v3(fn() raise {
    ignore(model_list_item_v3({ "id": "", "value": "v" }))
  })
}

///|
test "configured model literal exact AND plans retain same-statement versions" {
  let config = model_test_config_v3()
  let plans = model_plans_v3(config)
  assert_eq(plans.length(), 5)
  assert_true(
    plans[4].sql.has_suffix(
      "WHERE \"active\"=%s AND \"balance\">=%s ORDER BY id",
    ),
  )
  assert_true(
    plans[4].executed.has_prefix("SELECT id,balance,active,region,version"),
  )
  assert_true(plans[1].predicate.is_empty())
  assert_true(plans[2].predicate.is_empty())
}

///|
test "configured model point write outside domain rejected" {
  let config = model_test_config_v3()
  model_expect_reject_v3(fn() raise {
    ignore(
      model_parameters_v3(config, model_plans_v3(config)[2], [
        1, true, "east", 3,
      ]),
    )
  })
}

///|
test "configured model predicate type coercion rejected" {
  let config = model_test_config_v3()
  model_expect_reject_v3(fn() raise {
    ignore(model_parameters_v3(config, model_plans_v3(config)[4], ["true", 1]))
  })
}

///|
test "configured model multiple append request rejected" {
  let config = model_test_config_v3(is_list=true)
  model_expect_reject_v3(fn() raise {
    ignore(
      model_parameters_v3(config, model_plans_v3(config)[1], [
        "[{\"id\":\"a\",\"value\":\"v\"},{\"id\":\"b\",\"value\":\"v\"}]", "x",
      ]),
    )
  })
}

///|
test "configured model returned row must satisfy original AND predicate" {
  let config = model_test_config_v3()
  let plan = model_plans_v3(config)[4]
  model_predicate_match_v3(
    ["1", "5", true, "east", "00000000-0000-4000-8000-000000000001"],
    plan,
    [true, "0"],
  )
  model_expect_reject_v3(fn() raise {
    model_predicate_match_v3(
      ["1", "-5", true, "east", "00000000-0000-4000-8000-000000000001"],
      plan,
      [true, "0"],
    )
  })
}

///|
test "configured model empty complete relation source closes without invented versions" {
  let config = model_test_config_v3()
  let state : Array[Json] = [
    { "key": "1", "version": Json::null(), "present": false },
    { "key": "2", "version": Json::null(), "present": false },
  ]
  let source : ModelProfileWindowV3 = {
    initial: [],
    final_rows: [],
    final_state: state,
    ledger: [],
  }
  model_closure_v3(config, source, [])
}

///|
test "configured model orphan committed source cannot become an initial fact" {
  let config = model_test_config_v3()
  let effect : Json = {
    "key": "1",
    "version": "00000000-0000-4000-8000-000000000002",
    "predecessor": "00000000-0000-4000-8000-000000000001",
    "action": "UPDATE",
    "oldPresent": true,
    "newPresent": true,
    "values": { "balance": "9", "active": true, "region": "east" },
  }
  let source : ModelProfileWindowV3 = {
    initial: [],
    final_rows: [],
    final_state: [],
    ledger: [effect],
  }
  model_expect_reject_v3(fn() raise {
    model_closure_v3(config, source, [effect])
  })
}

///|
test "configured model missing committed effect ledger rejected" {
  let config = model_test_config_v3(is_list=true)
  let effect : Json = {
    "key": "x",
    "item": { "id": "a", "value": "same" },
    "items": [{ "id": "a", "value": "same" }],
  }
  let source : ModelProfileWindowV3 = {
    initial: [],
    final_rows: [],
    final_state: [],
    ledger: [],
  }
  model_expect_reject_v3(fn() raise {
    model_closure_v3(config, source, [effect])
  })
}

///|
test "configured model final database content cannot fabricate missing list append" {
  let config = model_test_config_v3(is_list=true)
  let source : ModelProfileWindowV3 = {
    initial: [],
    final_rows: [
      { "key": "x", "items": [{ "id": "unobserved", "value": "v" }] },
      { "key": "y", "items": [] },
    ],
    final_state: [],
    ledger: [],
  }
  model_expect_reject_v3(fn() raise { model_closure_v3(config, source, []) })
}

///|
test "configured model list exact chain closes with duplicate values" {
  let config = model_test_config_v3(is_list=true)
  let a : Json = { "id": "a", "value": "same" }
  let b : Json = { "id": "b", "value": "same" }
  let effects : Array[Json] = [
    { "key": "x", "item": a, "items": [a] },
    { "key": "x", "item": b, "items": [a, b] },
  ]
  let source : ModelProfileWindowV3 = {
    initial: [],
    final_rows: [{ "key": "x", "items": [a, b] }, { "key": "y", "items": [] }],
    final_state: [
      { "id": "a", "key": "x", "value": "same" },
      { "id": "b", "key": "x", "value": "same" },
    ],
    ledger: effects,
  }
  model_closure_v3(config, source, effects)
}
