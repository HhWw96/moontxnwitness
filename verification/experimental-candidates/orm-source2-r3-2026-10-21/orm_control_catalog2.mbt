///|
fn orm2_collect_catalog(cursor : OrmControlCursor2, schema : String, table : String, server : Json, business : Bool) -> (Json, Json) raise {
  let relation = orm2_query(cursor, "relation", [schema.to_json(), table.to_json()])
  let row = orm_array(orm2_one(relation))
  orm_assert(row.length() == 5, "Actual relation tuple width")
  let oid = row[0]
  ignore(v3_capture_seq(oid, "actual relation OID"))
  let facts : Map[String, Json] = Map([("relation", row.to_json())])
  let refs : Map[String, Json] = Map([("relation", relation.seq.to_double().to_json())])
  if business {
    facts["serverVersion"] = server
    let locks = orm2_query(cursor, "locks", [oid])
    facts["locks"] = locks.rows.to_json()
    refs["locks"] = locks.seq.to_double().to_json()
  }
  let requests = if business { ["columns", "constraints", "triggers", "indexes", "unsafe", "locale"] } else { ["columns", "constraints", "triggers", "unsafe", "indexes"] }
  for name in requests {
    let params = if name == "locale" { Json::null() } else if name == "unsafe" { [oid, oid, oid, oid, oid, oid].to_json() } else { [oid].to_json() }
    let query = orm2_query(cursor, name, params)
    let key = match name { "triggers" => "userTriggers"; "unsafe" => "unsafeEffects"; "locale" => "databaseLocale"; _ => name }
    facts[key] = if name == "unsafe" || name == "locale" { orm2_one(query) } else { query.rows.to_json() }
    refs[key] = query.seq.to_double().to_json()
  }
  (facts.to_json(), refs.to_json())
}

///|
fn orm2_business_catalog(facts : Json, oid : Json, versioned : Bool, triggers : Array[Json]) -> Unit raise {
  let names = ["id", "email", "hashed_password", "is_active", "is_superuser", "is_verified"]
  let types = ["uuid", "character varying(320)", "character varying(1024)", "boolean", "boolean", "boolean"]
  if versioned { names.push("_mtw_orm_version"); types.push("uuid") }
  orm_catalog_relation(facts, names, types, names.length(), false, Some("email"), Some(oid), Map([]))
  let object = object_fields(facts, "business catalog")
  orm_equal(required(object, "locks", "catalog"), [["AccessExclusiveLock", true]], "Actual business lock")
  orm_equal(required(object, "databaseLocale", "catalog"), ["C", "C"], "Supported database locale")
  orm_equal(required(object, "unsafeEffects", "catalog"), [0, 0, 0, 0], "Business unsupported side effects")
  orm_set_equal(required(object, "userTriggers", "catalog"), triggers, "Exact business trigger set")
}

///|
fn orm2_owned_catalog(owned : Map[String, Json], business_oid : Json) -> Unit raise {
  orm_assert(owned.length() == 4, "All four owned catalogs required")
  let used : Map[Int64, Bool] = Map([(v3_capture_seq(business_oid, "business OID"), true)])
  for name in ["installation", "state", "candidates", "effects"] {
    let names = if name == "installation" { ["nonce", "table_oid"] } else if name == "state" { ["key", "token", "present", "image"] } else { ["token", "key", "predecessor", "action", "old_present", "new_present", "old_image", "new_image"] }
    let types = if name == "installation" { ["uuid", "oid"] } else if name == "state" { ["text", "uuid", "boolean", "jsonb"] } else { ["uuid", "text", "uuid", "text", "boolean", "boolean", "jsonb", "jsonb"] }
    let fact = required(owned, name, "owned")
    orm_catalog_relation(fact, names, types, if name == "installation" { 2 } else if name == "state" { 3 } else { 6 }, name == "state", if name == "state" { Some("token") } else if name == "effects" { Some("predecessor") } else { None }, None, used)
    orm_equal(orm_get(fact, "userTriggers"), orm_empty(), "Owned tables have no user triggers")
    orm_equal(orm_get(fact, "unsafeEffects"), [0, 0, 0, 0], "Owned table unsafe effects")
  }
}

///|
fn orm2_functions(cursor : OrmControlCursor2, schema : String, oid : Json, functions : Map[String, Json]) -> Array[Json] raise {
  orm_assert(functions.length() == 4, "Exactly four owned functions required")
  let seen_functions : Map[Int64, Bool] = Map([])
  let seen_triggers : Map[Int64, Bool] = Map([])
  let triggers : Array[Json] = []
  for name in ["predecessor", "deleted_version", "before", "after"] {
    let meta = object_fields(required(functions, name, "functions"), "function")
    let function_oid = required(meta, "functionOid", "function")
    let number = v3_capture_seq(function_oid, "function OID")
    orm_assert(number <= 4294967295L && !seen_functions.contains(number), "Duplicate/invalid function OID")
    seen_functions[number] = true
    let source = orm_expected_function(schema, name)
    orm_equal(required(meta, "source", "function"), source.to_json(), "Fixed function body")
    orm_equal(required(meta, "sourceSha256", "function"), v3_dislock_sha256(source).to_json(), "Raw function source digest")
    let args = if name == "before" || name == "after" { 0 } else if name == "predecessor" { 1 } else { 2 }
    let expected : Json = [schema.to_json(), orm2_function_name(name).to_json(), source.to_json(), false, "v", ["search_path=pg_catalog"], args.to_json(), if args == 0 { "trigger".to_json() } else { "uuid".to_json() }, "plpgsql"]
    let query = orm2_query(cursor, "function_catalog", [function_oid])
    orm_equal(orm2_one(query), expected, "Actual pg_proc source/config")
    orm_equal(required(meta, "functionCatalog", "function"), expected, "Function metadata/raw query binding")
    orm_equal(required(meta, "functionQuerySeq", "function"), query.seq.to_double().to_json(), "Function query reference")
    if args == 0 {
      let trigger_oid = required(meta, "triggerOid", "function")
      let number = v3_capture_seq(trigger_oid, "trigger OID")
      orm_assert(number <= 4294967295L && !seen_triggers.contains(number), "Duplicate/invalid trigger OID")
      seen_triggers[number] = true
      let trigger = orm2_query(cursor, "trigger_catalog", [trigger_oid, oid])
      let expected : Json = [function_oid, if name == "before" { (31).to_json() } else { (29).to_json() }, "O", 0, "", false, true]
      orm_equal(orm2_one(trigger), expected, "Actual pg_trigger semantics")
      orm_equal(required(meta, "triggerCatalog", "function"), expected, "Trigger metadata/raw query binding")
      orm_equal(required(meta, "triggerQuerySeq", "function"), trigger.seq.to_double().to_json(), "Trigger query reference")
      triggers.push([trigger_oid].to_json())
    }
  }
  triggers
}

///|
fn orm2_collect_owned(cursor : OrmControlCursor2, schema : String, server : Json) -> (Json, Json) raise {
  let facts : Map[String, Json] = Map([])
  let refs : Map[String, Json] = Map([])
  for name in ["installation", "state", "candidates", "effects"] {
    let (fact, references) = orm2_collect_catalog(cursor, schema, "_mtw_orm_" + name, server, false)
    facts[name] = fact
    refs[name] = references
  }
  (facts.to_json(), refs.to_json())
}

///|
fn orm2_relations(schema : String, table : String, oid : Json, owned : Json) -> Json raise {
  let out : Array[Json] = [{ "schema": schema.to_json(), "table": table.to_json(), "oid": oid }]
  for name in ["installation", "state", "candidates", "effects"] {
    let row = orm_array(orm_get(orm_get(owned, name), "relation"))
    out.push({ "schema": schema.to_json(), "table": ("_mtw_orm_" + name).to_json(), "oid": row[0] })
  }
  out.to_json()
}

///|
fn orm2_snapshot_rows(rows : Array[Json], expected : Map[String, Json], known : Map[String, Bool]) -> Unit raise {
  orm_assert(rows.length() == known.length() && expected.length() == known.length(), "Exact joined snapshot domain")
  let seen : Map[String, Bool] = Map([])
  let versions : Map[String, Bool] = Map([])
  let mut previous = ""
  for row in rows {
    let row = orm_array(row)
    orm_assert(row.length() == 7, "Seven-cell source snapshot required")
    let key = orm_uuid(row[0])
    let token = orm_uuid(row[1])
    orm_assert(known.contains(key) && !seen.contains(key) && !versions.contains(token) && (previous.is_empty() || previous < key), "Joined snapshot key/token/order")
    seen[key] = true
    versions[token] = true
    previous = key
    let present = row[2]
    orm_assert(present == true.to_json() || present == false.to_json(), "Snapshot presence type")
    orm_image(row[3], key, present == true.to_json())
    orm_equal(required(expected, key, "state"), { "version": token.to_json(), "present": present, "image": row[3] }, "Actual joined state/image")
    if present == true.to_json() {
      orm_equal(row[4], key.to_json(), "Live business key")
      orm_equal(row[5], token.to_json(), "Live business token")
      orm_equal(row[6], row[3], "Live business/state same-statement image")
    } else {
      orm_equal(row[4], Json::null(), "Absent business ID")
      orm_equal(row[5], Json::null(), "Absent business token")
      orm_equal(row[6], { "id": Json::null(), "email": Json::null(), "hashed_password": Json::null(), "is_active": Json::null(), "is_superuser": Json::null(), "is_verified": Json::null() }, "Actual absent LEFT JOIN six-null payload")
    }
  }
}
