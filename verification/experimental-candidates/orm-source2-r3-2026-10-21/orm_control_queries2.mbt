///|
fn orm2_qualified(schema : String, name : String) -> String {
  "\"" + schema + "\".\"" + name + "\""
}

///|
fn orm2_query(cursor : OrmControlCursor2, name : String, parameters : Json) -> OrmControl2 raise {
  let (names, oids) = match name {
    "relation" => (["oid", "relkind", "relrowsecurity", "relforcerowsecurity", "relpersistence"], [26, 18, 16, 16, 18])
    "locks" => (["mode", "granted"], [25, 16])
    "columns" => (["attname", "format_type", "attnotnull", "attgenerated", "attidentity", "?column?"], [19, 25, 16, 18, 18, 16])
    "constraints" => (["contype", "conkey", "convalidated", "conenforced", "condeferrable", "condeferred", "connoinherit"], [18, 1005, 16, 16, 16, 16, 16])
    "triggers" | "function_oid" | "trigger_oid" => (["oid"], [26])
    "indexes" => (["indisprimary", "indisunique", "indisvalid", "indisready", "indimmediate", "indnkeyatts", "indnatts", "?column?", "?column?", "amname", "array", "array", "array"], [16, 16, 16, 16, 16, 21, 21, 16, 16, 19, 1003, 1003, 1000])
    "unsafe" => (["count", "count", "count", "count"], [20, 20, 20, 20])
    "locale" => (["datcollate", "datctype"], [25, 25])
    "function_catalog" => (["nspname", "proname", "prosrc", "prosecdef", "provolatile", "proconfig", "pronargs", "prorettype", "lanname"], [19, 19, 25, 16, 18, 1009, 21, 25, 19])
    "trigger_catalog" => (["tgfoid", "tgtype", "tgenabled", "tgnargs", "encode", "tgisinternal", "?column?"], [26, 21, 18, 21, 25, 16, 16])
    _ => fail("Unknown fixed catalog descriptor")
  }
  orm2_select(cursor, orm2_sql(name), parameters, names, oids)
}

///|
fn orm2_one(value : OrmControl2) -> Json raise {
  orm_assert(value.rows.length() == 1, "Exactly one actual metadata row required")
  value.rows[0]
}

///|
fn orm2_function_name(name : String) -> String {
  "_mtw_orm_" + name + (if name == "before" || name == "after" { "_fn" } else { "" })
}

///|
fn orm2_create_function(schema : String, name : String) -> String raise {
  let args = if name == "before" || name == "after" {
    ""
  } else if name == "predecessor" {
    "token_text text"
  } else if name == "deleted_version" {
    "key_text text,predecessor_text text"
  } else {
    fail("Unknown owned function")
  }
  "CREATE FUNCTION " + orm2_qualified(schema, orm2_function_name(name)) + "(" + args +
  ") RETURNS " + (if args.is_empty() { "trigger" } else { "uuid" }) +
  " LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS $$" +
  orm_expected_function(schema, name) + "$$"
}

///|
fn orm2_create_trigger(schema : String, table : String, name : String) -> String raise {
  let phase = match name { "before" => "BEFORE"; "after" => "AFTER"; _ => fail("Unknown trigger phase") }
  "CREATE TRIGGER \"_mtw_orm_" + name + "\" " + phase + " INSERT OR UPDATE OR DELETE ON " +
  orm2_qualified(schema, table) + " FOR EACH ROW EXECUTE FUNCTION " +
  orm2_qualified(schema, orm2_function_name(name)) + "()"
}

///|
fn orm2_lock_all(schema : String, table : String) -> String {
  let names = [orm2_qualified(schema, table)]
  for name in ["installation", "state", "candidates", "effects"] {
    names.push(orm2_qualified(schema, "_mtw_orm_" + name))
  }
  let builder = StringBuilder()
  for i, name in names {
    if i > 0 { builder.write_string(",") }
    builder.write_string(name)
  }
  "LOCK TABLE " + builder.to_string() + " IN ACCESS EXCLUSIVE MODE"
}

///|
/// The setup/catalog query returns native JSONB. The business transport helper
/// deliberately casts a different expression to bounded text and is not valid
/// for this independent control SQL contract.
fn orm2_control_payload(prefix_name : String) -> String {
  "jsonb_build_object('id'," + prefix_name + ".\"id\"::text,'email'," +
  prefix_name + ".\"email\",'hashed_password'," + prefix_name +
  ".\"hashed_password\",'is_active'," + prefix_name + ".\"is_active\",'is_superuser'," +
  prefix_name + ".\"is_superuser\",'is_verified'," + prefix_name + ".\"is_verified\")"
}

///|
fn orm2_snapshot_sql(schema : String, table : String) -> String {
  "SELECT s.key,s.token::text,s.present,s.image,t.id::text,t.\"_mtw_orm_version\"::text," + orm2_control_payload("t") +
  " FROM " + orm2_qualified(schema, "_mtw_orm_state") + " s LEFT JOIN " + orm2_qualified(schema, table) +
  " t ON t.id=s.key::uuid ORDER BY s.key LIMIT 129"
}

///|
fn orm2_snapshot_query(cursor : OrmControlCursor2, schema : String, table : String) -> OrmControl2 raise {
  orm2_select(cursor, orm2_snapshot_sql(schema, table), Json::null(),
    ["key", "token", "present", "image", "id", "_mtw_orm_version", "jsonb_build_object"],
    [25, 25, 16, 3802, 25, 25, 3802])
}
