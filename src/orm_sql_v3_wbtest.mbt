///|
/// Fabricated unit inputs test transport semantics, not database execution.
fn orm_test_reject(action : () -> Unit raise) -> Unit raise {
  let rejected = try {
    action()
    false
  } catch {
    _ => true
  }
  assert_true(rejected)
}

///|
fn orm_test_image(email : String) -> Json {
  {
    "id": "00000000-0000-0000-0000-000000000001",
    "email": Json(email),
    "hashed_password": "hash",
    "is_active": true,
    "is_superuser": false,
    "is_verified": false,
  }
}

///|
test "ORM varchar counts Unicode scalars rather than UTF16 code units" {
  let value = "😀".repeat(320)
  orm_image(orm_test_image(value), "00000000-0000-0000-0000-000000000001", true)
  orm_test_reject(() => {
    orm_image(
      orm_test_image(value + "x"),
      "00000000-0000-0000-0000-000000000001",
      true,
    )
  })
}

///|
test "ORM varchar counts combining scalars without normalization" {
  let value = "é".repeat(160)
  assert_eq(orm_native_text(Json(value), 320), value)
  orm_test_reject(() => ignore(orm_native_text(Json(value + "́"), 320)))
}

///|
test "ORM native PostgreSQL text rejects NUL" {
  orm_test_reject(() => ignore(orm_native_text(Json("a\u0000b"), 320)))
}

///|
test "ORM image flags cannot be numeric booleans" {
  let image = orm_test_image("a")
  object_fields(image, "image")["is_active"] = Json(1)
  orm_test_reject(() => {
    orm_image(image, "00000000-0000-0000-0000-000000000001", true)
  })
}

///|
test "ORM image id must equal bound UUID" {
  orm_test_reject(() => {
    orm_image(orm_test_image("a"), "00000000-0000-0000-0000-000000000002", true)
  })
}

///|
test "ORM absent image cannot retain business columns" {
  orm_test_reject(() => {
    orm_image(
      orm_test_image("a"),
      "00000000-0000-0000-0000-000000000001",
      false,
    )
  })
  orm_image(Json::null(), "00000000-0000-0000-0000-000000000001", false)
}

///|
test "ORM six native columns reject extras" {
  let image = orm_test_image("a")
  object_fields(image, "image")["role"] = Json("admin")
  orm_test_reject(() => {
    orm_image(image, "00000000-0000-0000-0000-000000000001", true)
  })
}

///|
test "ORM password length is independent of email length" {
  let image = orm_test_image("a")
  object_fields(image, "image")["hashed_password"] = Json("密".repeat(1024))
  orm_image(image, "00000000-0000-0000-0000-000000000001", true)
  object_fields(image, "image")["hashed_password"] = Json("密".repeat(1025))
  orm_test_reject(() => {
    orm_image(image, "00000000-0000-0000-0000-000000000001", true)
  })
}

///|
test "ORM typed UUID uses exact capture type and canonical case" {
  assert_eq(
    orm_bound_uuid({
      "captureType": "UUID",
      "value": "00000000-0000-0000-0000-000000000001",
    }),
    "00000000-0000-0000-0000-000000000001",
  )
  orm_test_reject(() => {
    ignore(
      orm_bound_uuid({
        "captureType": "uuid",
        "value": "00000000-0000-0000-0000-000000000001",
      }),
    )
  })
  orm_test_reject(() => {
    ignore(orm_bound_uuid(Json("ABCDEF00-0000-0000-0000-000000000001")))
  })
}

///|
test "ORM byte decoding rejects noncanonical padding" {
  assert_eq(
    orm_raw_text({ "captureType": "bytes", "base64": "YQ==" }),
    Json("a"),
  )
  orm_test_reject(() => {
    ignore(orm_raw_text({ "captureType": "bytes", "base64": "YQ" }))
  })
}

///|
test "ORM byte decoding rejects whitespace and invalid UTF8" {
  orm_test_reject(() => {
    ignore(orm_raw_text({ "captureType": "bytes", "base64": "Y Q==" }))
  })
  orm_test_reject(() => {
    ignore(orm_raw_text({ "captureType": "bytes", "base64": "/w==" }))
  })
}

///|
test "ORM byte decoding preserves initial BOM as an actual scalar" {
  assert_eq(
    orm_raw_text({ "captureType": "bytes", "base64": "77u/YQ==" }),
    Json("﻿a"),
  )
}

///|
test "ORM raw NULL is distinct from JSON text null" {
  assert_eq(orm_raw_text(Json::null()), Json::null())
  assert_eq(
    orm_raw_text({ "captureType": "bytes", "base64": "bnVsbA==" }),
    Json("null"),
  )
}

///|
test "ORM raw cells cannot exceed predecode or decoded limit" {
  orm_test_reject(() => {
    ignore(
      orm_raw_text({ "captureType": "bytes", "base64": Json("A".repeat(70001)) }),
    )
  })
  let text = "a".repeat(51201)
  let encoded = @base64.encode(@utf8.encode(text[:])[:])
  orm_test_reject(() => {
    ignore(orm_raw_text({ "captureType": "bytes", "base64": Json(encoded) }))
  })
}

///|
test "ORM record node budget is shared across containers" {
  let first = Array::make(2050, Json::null())
  let second = Array::make(2050, Json::null())
  let record : Json = { "rows": Json(first), "effectRows": Json(second) }
  orm_test_reject(() => ignore(orm_nodes(record, 0)))
}

///|
test "ORM recursive node budget rejects excess depth" {
  let mut value : Json = Json::null()
  for _ in 0..<66 {
    value = Json([value])
  }
  orm_test_reject(() => ignore(orm_nodes(value, 0)))
}

///|
test "ORM SQL update masks keep pinned field order and casts" {
  let plan = orm_plan(
    "mtw_orm_v3_unit", "observed_user", "update", 17, "mtw_orm_v3_unit_observed_user_id",
  )
  assert_eq(plan.fields, ["email", "is_verified"])
  assert_true(
    plan.original.contains(
      "SET email=%(email)s::VARCHAR, is_verified=%(is_verified)s WHERE",
    ),
  )
  assert_true(plan.executed.has_suffix("'UPDATE'::text"))
}

///|
test "ORM SQL empty and out of range update masks are unsupported" {
  orm_test_reject(() => {
    ignore(
      orm_plan(
        "mtw_orm_v3_unit", "observed_user", "update", 0, "mtw_orm_v3_unit_observed_user_id",
      ),
    )
  })
  orm_test_reject(() => {
    ignore(
      orm_plan(
        "mtw_orm_v3_unit", "observed_user", "update", 32, "mtw_orm_v3_unit_observed_user_id",
      ),
    )
  })
}

///|
test "ORM SQL does not accept new operation families" {
  orm_test_reject(() => {
    ignore(orm_plan("mtw_orm_v3_unit", "observed_user", "upsert", 0, "id"))
  })
}

///|
test "ORM delete uses immutable tombstone helper not OLD token" {
  let plan = orm_plan("mtw_orm_v3_unit", "observed_user", "delete", 0, "id")
  assert_true(
    plan.executed.contains(
      "._mtw_orm_deleted_version(OLD.id::uuid::text,OLD._mtw_orm_version::uuid::text)::uuid::text,true,false",
    ),
  )
  assert_true(!plan.executed.contains("NEW."))
}

///|
test "ORM GET source LEFT JOIN is same-statement and domain-left" {
  let plan = orm_plan("mtw_orm_v3_unit", "observed_user", "get", 0, "pk_1")
  assert_true(
    plan.executed.contains(
      "FROM mtw_orm_v3_unit._mtw_orm_state AS _mtw_scope LEFT JOIN mtw_orm_v3_unit.observed_user",
    ),
  )
  assert_true(plan.executed.has_suffix("%(pk_1)s::UUID::text"))
}

///|
test "ORM pg18 constraints distinguish NOT NULL and PK inheritance flags" {
  assert_eq(
    orm_constraint("n", 1),
    @json.parse("[\"n\",[1],true,true,false,false,false]"),
  )
  assert_eq(
    orm_constraint("p", 1),
    @json.parse("[\"p\",[1],true,true,false,false,true]"),
  )
}

///|
test "ORM catalog sets reject duplicate entries even at same cardinality" {
  let a = orm_constraint("n", 1)
  let b = orm_constraint("p", 1)
  orm_test_reject(() => orm_set_equal(Json([a, a]), [a, b], "constraints"))
}

///|
test "ORM pg_proc templates require server-side DELETE candidate identity" {
  let text = orm_expected_function("mtw_orm_v3_unit", "deleted_version")
  assert_true(
    text.contains("predecessor=predecessor_text::uuid AND action='DELETE'"),
  )
  assert_true(text.contains("IF n<>1 THEN RAISE EXCEPTION"))
}

///|
test "ORM pg_proc templates retain row locking and actual effects separation" {
  let before = orm_expected_function("mtw_orm_v3_unit", "before")
  let after = orm_expected_function("mtw_orm_v3_unit", "after")
  assert_true(before.contains("FOR UPDATE"))
  assert_true(
    !before.contains("INSERT INTO \"mtw_orm_v3_unit\".\"_mtw_orm_effects\""),
  )
  assert_true(
    after.contains("INSERT INTO \"mtw_orm_v3_unit\".\"_mtw_orm_effects\""),
  )
}

///|
test "ORM unknown helper cannot use attacker supplied source hash" {
  orm_test_reject(() => {
    ignore(orm_expected_function("mtw_orm_v3_unit", "attacker"))
  })
}

///|
test "ORM partial source journal cannot be sealed implicitly" {
  orm_test_reject(() => ignore(orm_journal("{}")))
  orm_test_reject(() => ignore(orm_journal("{}\n")))
}

///|
test "ORM malformed envelope grants no partial source sets" {
  let result = @json.parse(orm_sql_v3_proof_json("{\"schema\":1,\"schema\":1}"))
  assert_eq(orm_get(result, "verifiedSourceBatches"), orm_empty())
  assert_eq(orm_get(result, "history"), Json::null())
  assert_eq(orm_get(result, "analysisCoverageAccepted"), Json(false))
}
