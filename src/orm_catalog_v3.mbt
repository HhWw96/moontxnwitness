///|
fn orm_constraint(kind : String, column : Int32) -> Json {
  [
    Json(kind),
    Json([Json(column)]),
    true,
    true,
    false,
    false,
    Json(kind != "n"),
  ]
}

///|
fn orm_index(primary : Bool, field : String) -> Json {
  [
    Json(primary),
    true,
    true,
    true,
    true,
    1,
    1,
    true,
    true,
    "btree",
    Json([Json(field)]),
    ["pg_catalog"],
    [true],
  ]
}

///|
fn orm_set_equal(
  actual : Json,
  expected : Array[Json],
  label : String,
) -> Unit raise {
  let actual = orm_array(actual)
  orm_assert(
    actual.length() == expected.length(),
    label + " cardinality mismatch",
  )
  let seen : Map[Int32, Bool] = Map([])
  for row in actual {
    let mut matched = -1
    for i, target in expected {
      if row == target {
        matched = i
      }
    }
    orm_assert(
      matched >= 0 && !seen.contains(matched),
      label + " unexpected/duplicate entry",
    )
    seen[matched] = true
  }
}

///|
fn orm_catalog_relation(
  value : Json,
  names : Array[String],
  types : Array[String],
  null_count : Int32,
  unique_constraint : Bool,
  extra_index : String?,
  oid : Json?,
  used_oids : Map[Int64, Bool],
) -> Unit raise {
  let obj = object_fields(value, "catalog relation")
  let relation = orm_array(required(obj, "relation", "catalog"))
  orm_assert(relation.length() == 5, "Invalid catalog relation shape")
  let relation_oid = v3_capture_seq(relation[0], "relation OID")
  orm_assert(
    relation_oid <= 4294967295L && !used_oids.contains(relation_oid),
    "Duplicate/invalid relation OID",
  )
  used_oids[relation_oid] = true
  if oid is Some(expected) {
    orm_equal(relation[0], expected, "business table OID")
  }
  orm_equal(
    Json(relation),
    [relation[0], "r", false, false, "p"],
    "ordinary non-RLS permanent relation",
  )
  let columns : Array[Json] = []
  let constraints = [orm_constraint("p", 1)]
  for i, name in names {
    columns.push([
      Json(name),
      Json(types[i]),
      Json(i < null_count),
      "",
      "",
      false,
    ])
    if i < null_count {
      constraints.push(orm_constraint("n", i + 1))
    }
  }
  if unique_constraint {
    constraints.push(orm_constraint("u", 2))
  }
  orm_equal(
    required(obj, "columns", "catalog"),
    Json(columns),
    "native exact columns/defaults",
  )
  orm_set_equal(
    required(obj, "constraints", "catalog"),
    constraints,
    "PG18 NOT NULL/PK/UNIQUE constraints",
  )
  let indexes = [orm_index(true, names[0])]
  if extra_index is Some(field) {
    indexes.push(orm_index(false, field))
  }
  orm_set_equal(
    required(obj, "indexes", "catalog"),
    indexes,
    "native deterministic unique B-tree indexes",
  )
}

///|
fn orm_verify_catalog(
  installation : Map[String, Json],
  gaps : Array[Json],
) -> Json raise {
  let metadata = object_fields(
    required(installation, "metadata", "installation"),
    "metadata",
  )
  let schema = orm_text(required(installation, "schema", "installation"))
  let server = v3_capture_seq(
    required(metadata, "serverVersion", "metadata"),
    "server version",
  )
  orm_assert(
    server >= 180000L && server < 190000L,
    "Exact PostgreSQL18 catalog semantics required",
  )
  orm_equal(
    required(metadata, "versionColumn", "metadata"),
    Json("_mtw_orm_version"),
    "private version column",
  )
  ignore(orm_uuid(required(metadata, "nonce", "metadata")))
  orm_equal(
    required(metadata, "coreProofAccepted", "metadata"),
    Json(false),
    "unpromoted producer metadata",
  )
  let functions = object_fields(
    required(metadata, "functions", "metadata"),
    "functions",
  )
  known_fields(
    functions,
    ["before", "after", "predecessor", "deleted_version"],
    "owned functions",
  )
  orm_assert(functions.length() == 4, "Missing owned source helper")
  let used_function_oids : Map[Int64, Bool] = Map([])
  let trigger_oids : Array[Json] = []
  let used_trigger_oids : Map[Int64, Bool] = Map([])
  for name in ["before", "after", "predecessor", "deleted_version"] {
    let function = object_fields(
      required(functions, name, "functions"),
      "function",
    )
    let oid = v3_capture_seq(
      required(function, "functionOid", "function"),
      "function OID",
    )
    orm_assert(
      oid <= 4294967295L && !used_function_oids.contains(oid),
      "Invalid/duplicate source function OID",
    )
    used_function_oids[oid] = true
    let source = orm_expected_function(schema, name)
    orm_equal(
      required(function, "source", "function"),
      Json(source),
      "fixed raw pg_proc.prosrc template",
    )
    orm_equal(
      required(function, "sourceSha256", "function"),
      Json(v3_dislock_sha256(source)),
      "owned source SHA",
    )
    let args = if name == "before" || name == "after" {
      0
    } else if name == "predecessor" {
      1
    } else {
      2
    }
    let function_name = "_mtw_orm_" +
      name +
      (if args == 0 { "_fn" } else { "" })
    let expected : Json = [
      Json(schema),
      Json(function_name),
      Json(source),
      false,
      "v",
      ["search_path=pg_catalog"],
      Json(args),
      if args == 0 {
        Json("trigger")
      } else {
        Json("uuid")
      },
      "plpgsql",
    ]
    orm_equal(
      required(function, "functionCatalog", "function"),
      expected,
      "actual function catalog identity/config",
    )
    if args == 0 {
      let trigger_oid = v3_capture_seq(
        required(function, "triggerOid", "function"),
        "trigger OID",
      )
      orm_assert(
        trigger_oid <= 4294967295L && !used_trigger_oids.contains(trigger_oid),
        "Invalid/duplicate trigger OID",
      )
      used_trigger_oids[trigger_oid] = true
      trigger_oids.push(Json([Json(trigger_oid.to_double())]))
      orm_equal(
        required(function, "triggerCatalog", "function"),
        [
          Json(oid.to_double()),
          if name == "before" {
            Json(31)
          } else {
            Json(29)
          },
          "O",
          0,
          "",
          false,
          true,
        ],
        "owned row trigger type/function/qualifier/enablement",
      )
    }
  }
  let used_oids : Map[Int64, Bool] = Map([])
  let catalog = object_fields(
    required(metadata, "catalog", "metadata"),
    "catalog",
  )
  orm_equal(
    required(catalog, "serverVersion", "catalog"),
    required(metadata, "serverVersion", "metadata"),
    "catalog server version",
  )
  orm_catalog_relation(
    Json(catalog),
    [
      "id", "email", "hashed_password", "is_active", "is_superuser", "is_verified",
      "_mtw_orm_version",
    ],
    [
      "uuid", "character varying(320)", "character varying(1024)", "boolean", "boolean",
      "boolean", "uuid",
    ],
    7,
    false,
    Some("email"),
    Some(required(metadata, "tableOid", "metadata")),
    used_oids,
  )
  orm_equal(
    required(catalog, "locks", "catalog"),
    [["AccessExclusiveLock", true]],
    "actual granted initialization lock",
  )
  orm_equal(
    required(catalog, "databaseLocale", "catalog"),
    ["C", "C"],
    "fixed database locale",
  )
  orm_equal(
    required(catalog, "unsafeEffects", "catalog"),
    [0, 0, 0, 0],
    "business unsupported side effects",
  )
  orm_set_equal(
    required(catalog, "userTriggers", "catalog"),
    trigger_oids,
    "owned business triggers only",
  )
  let owned = object_fields(
    required(metadata, "ownedCatalog", "metadata"),
    "owned catalog",
  )
  known_fields(
    owned,
    ["installation", "state", "candidates", "effects"],
    "owned catalog",
  )
  orm_assert(owned.length() == 4, "Missing owned catalog")
  for name in ["installation", "state", "candidates", "effects"] {
    let names = if name == "installation" {
      ["nonce", "table_oid"]
    } else if name == "state" {
      ["key", "token", "present", "image"]
    } else {
      [
        "token", "key", "predecessor", "action", "old_present", "new_present", "old_image",
        "new_image",
      ]
    }
    let types = if name == "installation" {
      ["uuid", "oid"]
    } else if name == "state" {
      ["text", "uuid", "boolean", "jsonb"]
    } else {
      ["uuid", "text", "uuid", "text", "boolean", "boolean", "jsonb", "jsonb"]
    }
    let entry = required(owned, name, "owned")
    orm_catalog_relation(
      entry,
      names,
      types,
      if name == "installation" {
        2
      } else if name == "state" {
        3
      } else {
        6
      },
      name == "state",
      if name == "state" {
        Some("token")
      } else if name == "effects" {
        Some("predecessor")
      } else {
        None
      },
      None,
      used_oids,
    )
    let entry = object_fields(entry, "owned entry")
    for missing in ["userTriggers", "unsafeEffects"] {
      if !entry.contains(missing) {
        gaps.push(
          capture_gap(
            "orm_profile_missing_raw_field",
            "ownedCatalog." + name + "." + missing,
          ),
        )
      }
    }
    if entry.contains("userTriggers") {
      orm_equal(
        required(entry, "userTriggers", "owned"),
        orm_empty(),
        "owned metadata must have no user triggers",
      )
    }
    if entry.contains("unsafeEffects") {
      orm_equal(
        required(entry, "unsafeEffects", "owned"),
        [0, 0, 0, 0],
        "owned unsafe effects",
      )
    }
  }
  let expected_window : Json = [
    { "kind": "begin", "commandTag": "BEGIN" },
    {
      "kind": "lock",
      "commandTag": "LOCK TABLE",
      "tableOid": required(metadata, "tableOid", "metadata"),
      "mode": "ACCESS EXCLUSIVE",
    },
    { "kind": "catalog" },
    {
      "kind": "snapshot",
      "rows": required(metadata, "initialState", "metadata"),
    },
    { "kind": "commit", "commandTag": "COMMIT" },
  ]
  orm_equal(
    required(metadata, "initializationWindow", "metadata"),
    expected_window,
    "controlled initialization acknowledgements",
  )
  for
    missing in [
      "initialMarkerRows", "initialSnapshotRows", "finalCatalog", "finalOwnedCatalog",
      "finalFunctions", "finalMarkerRows", "finalSnapshotRows", "finalizationWindow",
    ] {
    // This contract does not interpret future, unreviewed field shapes. Merely
    // adding a self-reported field must never complete an old capture.
    gaps.push(
      capture_gap(
        "orm_profile_missing_raw_field",
        "No supported raw proof contract for metadata." + missing,
      ),
    )
  }
  {
    "functions": 4,
    "businessRelation": 1,
    "ownedRelations": 4,
    "initializationAcknowledgements": 5,
    "fullSafetyProfileVerified": false,
  }
}
