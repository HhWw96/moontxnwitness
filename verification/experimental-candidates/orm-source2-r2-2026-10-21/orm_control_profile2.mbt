///|
fn orm2_control_seqs(cursor : OrmControlCursor2, begin : Int, end : Int) -> Json {
  let out : Array[Json] = []
  for i in begin..<end { out.push(cursor.controls[i].seq.to_double().to_json()) }
  out.to_json()
}

///|
fn orm2_marker(cursor : OrmControlCursor2, schema : String, nonce : Json, oid : Json, record : Map[String, Json], prefix : String) -> Unit raise {
  let query = orm2_select(cursor, "SELECT nonce::text,table_oid FROM " + orm2_qualified(schema, "_mtw_orm_installation"), Json::null(), ["nonce", "table_oid"], [25, 26])
  let expected : Json = [[nonce, oid].to_json()].to_json()
  orm_equal(query.rows.to_json(), expected, "Actual installation marker rows")
  orm_equal(required(record, prefix + "MarkerRows", "marker"), expected, "Marker metadata/native binding")
  orm_equal(required(record, prefix + "MarkerQuerySeq", "marker"), query.seq.to_double().to_json(), "Marker source query reference")
}

///|
fn orm2_init_profile(installation : Map[String, Json], controls : Array[OrmControl2], known : Map[String, Bool]) -> (Json, Array[Json]) raise {
  let metadata = object_fields(required(installation, "metadata", "installation"), "metadata")
  let schema = orm_text(required(installation, "schema", "installation"))
  let table = orm_text(required(installation, "table", "installation"))
  let target = orm2_qualified(schema, table)
  let oid = required(metadata, "tableOid", "metadata")
  let server = required(metadata, "serverVersion", "metadata")
  let version = v3_capture_seq(server, "server version")
  orm_assert(version >= 180000L && version < 190000L, "PostgreSQL18 source contract")
  orm_equal(required(metadata, "versionColumn", "metadata"), "_mtw_orm_version".to_json(), "Private version column")
  orm_equal(required(metadata, "coreProofAccepted", "metadata"), false.to_json(), "Unpromoted producer declaration")
  let nonce = orm_uuid(required(metadata, "nonce", "metadata")).to_json()
  let state = object_fields(required(metadata, "initialState", "metadata"), "initial state")
  let functions = object_fields(required(metadata, "functions", "metadata"), "functions")
  let cursor = { controls, at: 0, verified: [] }
  let begin = orm2_command(cursor, "BEGIN", Json::null(), "BEGIN", None)
  let first_lock = orm2_command(cursor, "LOCK TABLE " + target + " IN ACCESS EXCLUSIVE MODE", Json::null(), "LOCK TABLE", None)
  let (prior_catalog, _) = orm2_collect_catalog(cursor, schema, table, server, true)
  orm2_business_catalog(prior_catalog, oid, false, [])
  let existing = orm2_select(cursor, "SELECT id::text FROM " + target + " LIMIT 129", Json::null(), ["id"], [25])
  let live_keys : Map[String, Bool] = Map([])
  for row in existing.rows {
    let row = orm_array(row)
    orm_assert(row.length() == 1, "Original live-key row width")
    let key = orm_uuid(row[0])
    orm_assert(known.contains(key) && !live_keys.contains(key), "Pre-migration key outside fixed domain")
    live_keys[key] = true
  }
  ignore(orm2_command(cursor, "ALTER TABLE " + target + " ADD COLUMN \"_mtw_orm_version\" uuid NOT NULL DEFAULT gen_random_uuid()", Json::null(), "ALTER TABLE", None))
  ignore(orm2_command(cursor, "ALTER TABLE " + target + " ALTER COLUMN \"_mtw_orm_version\" DROP DEFAULT", Json::null(), "ALTER TABLE", None))
  ignore(orm2_command(cursor, "CREATE TABLE " + orm2_qualified(schema, "_mtw_orm_installation") + "(nonce uuid PRIMARY KEY,table_oid oid NOT NULL)", Json::null(), "CREATE TABLE", None))
  ignore(orm2_command(cursor, "INSERT INTO " + orm2_qualified(schema, "_mtw_orm_installation") + " VALUES(%s,%s)", [nonce, oid], "INSERT 0 1", Some(1)))
  ignore(orm2_command(cursor, "CREATE TABLE " + orm2_qualified(schema, "_mtw_orm_state") + "(key text PRIMARY KEY,token uuid NOT NULL UNIQUE,present boolean NOT NULL,image jsonb)", Json::null(), "CREATE TABLE", None))
  for name in ["candidates", "effects"] {
    ignore(orm2_command(cursor, "CREATE TABLE " + orm2_qualified(schema, "_mtw_orm_" + name) + "(token uuid PRIMARY KEY,key text NOT NULL,predecessor uuid NOT NULL,action text NOT NULL,old_present boolean NOT NULL,new_present boolean NOT NULL,old_image jsonb,new_image jsonb)", Json::null(), "CREATE TABLE", None))
  }
  ignore(orm2_command(cursor, "CREATE UNIQUE INDEX _mtw_orm_effect_predecessor ON " + orm2_qualified(schema, "_mtw_orm_effects") + "(predecessor)", Json::null(), "CREATE INDEX", None))
  let observed = orm2_select(cursor, "SELECT id::text,\"_mtw_orm_version\"::text," + orm_payload(target) + " FROM " + target, Json::null(), ["id", "_mtw_orm_version", "jsonb_build_object"], [25, 25, 3802])
  let images : Map[String, Json] = Map([])
  orm_assert(observed.rows.length() == live_keys.length(), "ALTER migration changed original key domain")
  for row in observed.rows {
    let row = orm_array(row)
    orm_assert(row.length() == 3, "Observed migrated business image width")
    let key = orm_uuid(row[0])
    orm_assert(live_keys.contains(key) && !images.contains(key), "Migrated image key/source domain")
    ignore(orm_uuid(row[1]))
    orm_image(row[2], key, true)
    orm_equal(required(state, key, "initial state"), { "version": row[1], "present": true, "image": row[2] }, "Actual initial live state/source")
    images[key] = row.to_json()
  }
  let parameter_groups : Array[Json] = []
  let mut jsonb_parameters = 0
  for key in orm_array(required(installation, "knownIds", "installation")) {
    let key_text = orm_uuid(key)
    let entry = orm_exact(required(state, key_text, "initial state"), ["version", "present", "image"])
    let token = orm_uuid(required(entry, "version", "state")).to_json()
    let present = live_keys.contains(key_text)
    orm_equal(required(entry, "present", "state"), present.to_json(), "Initial presence from original live rows")
    let image = required(entry, "image", "state")
    orm_image(image, key_text, present)
    let parameter_image : Json = if present {
      jsonb_parameters += 1
      { "captureType": "psycopg-jsonb", "objectDumps": "stdlib-json-dumps", "value": image }
    } else {
      Json::null()
    }
    let query = orm2_command(cursor, "INSERT INTO " + orm2_qualified(schema, "_mtw_orm_state") + " VALUES(%s,%s,%s,%s)", [key, token, present.to_json(), parameter_image], "INSERT 0 1", Some(1))
    parameter_groups.push({ "sourceSeq": query.seq.to_double().to_json(), "key": key, "present": present.to_json(), "explicitJsonb": present.to_json() })
  }
  for name in ["predecessor", "deleted_version", "before", "after"] {
    ignore(orm2_command(cursor, orm2_create_function(schema, name), Json::null(), "CREATE FUNCTION", None))
    let lookup = orm2_query(cursor, "function_oid", [schema.to_json(), orm2_function_name(name).to_json()])
    let meta = object_fields(required(functions, name, "functions"), "function")
    orm_equal(orm2_one(lookup), [required(meta, "functionOid", "function")].to_json(), "Created actual function OID")
    if name == "before" || name == "after" {
      ignore(orm2_command(cursor, orm2_create_trigger(schema, table, name), Json::null(), "CREATE TRIGGER", None))
      let lookup = orm2_query(cursor, "trigger_oid", [oid, ("_mtw_orm_" + name).to_json()])
      orm_equal(orm2_one(lookup), [required(meta, "triggerOid", "function")].to_json(), "Created actual trigger OID")
    }
  }
  let all_lock = orm2_command(cursor, orm2_lock_all(schema, table), Json::null(), "LOCK TABLE", None)
  let catalog_begin = cursor.at
  let (catalog, catalog_refs) = orm2_collect_catalog(cursor, schema, table, server, true)
  orm_equal(required(metadata, "catalog", "metadata"), catalog, "Initial raw catalog leaves")
  orm_equal(required(metadata, "catalogQueryRefs", "metadata"), catalog_refs, "Initial catalog source query references")
  let trigger_oids = orm2_functions(cursor, schema, oid, functions)
  orm2_business_catalog(catalog, oid, true, trigger_oids)
  orm2_marker(cursor, schema, nonce, oid, metadata, "initial")
  let (owned, owned_refs) = orm2_collect_owned(cursor, schema, server)
  orm_equal(required(metadata, "ownedCatalog", "metadata"), owned, "Initial raw owned catalog leaves")
  orm_equal(required(metadata, "ownedCatalogQueryRefs", "metadata"), owned_refs, "Initial owned catalog query references")
  orm2_owned_catalog(object_fields(owned, "owned catalog"), oid)
  let catalog_end = cursor.at
  let snapshot = orm2_snapshot_query(cursor, schema, table)
  orm2_snapshot_rows(snapshot.rows, state, known)
  orm_equal(required(metadata, "initialSnapshotRows", "metadata"), snapshot.rows.to_json(), "Initial raw seven-cell snapshot")
  orm_equal(required(metadata, "initialSnapshotQuerySeq", "metadata"), snapshot.seq.to_double().to_json(), "Initial snapshot source reference")
  let commit = orm2_command(cursor, "COMMIT", Json::null(), "COMMIT", None)
  orm_assert(cursor.at == controls.length(), "Unexpected extra initialization control SQL")
  let window : Json = [
    { "kind": "begin", "commandTag": "BEGIN", "querySeq": begin.seq.to_double().to_json() },
    { "kind": "lock", "commandTag": "LOCK TABLE", "mode": "ACCESS EXCLUSIVE", "tableOid": oid,
      "querySeqs": [first_lock.seq.to_double().to_json(), all_lock.seq.to_double().to_json()], "relations": orm2_relations(schema, table, oid, owned) },
    { "kind": "catalog", "tableOid": oid, "querySeqs": orm2_control_seqs(cursor, catalog_begin, catalog_end) },
    { "kind": "snapshot", "rows": snapshot.rows.to_json(), "querySeq": snapshot.seq.to_double().to_json() },
    { "kind": "commit", "commandTag": "COMMIT", "querySeq": commit.seq.to_double().to_json() },
  ]
  orm_equal(required(metadata, "initializationWindow", "metadata"), window, "Actual initialization lock/catalog/snapshot/ACK window")
  ({ "window": window, "parameterGroups": parameter_groups.to_json(), "explicitJsonbParameters": jsonb_parameters.to_json(), "migrationDdlStatements": 13, "preMigrationCatalog": prior_catalog }, cursor.verified)
}

///|
fn orm2_final_profile(installation : Map[String, Json], final_record : Map[String, Json], controls : Array[OrmControl2], known : Map[String, Bool]) -> (Json, Array[Json]) raise {
  let metadata = object_fields(required(installation, "metadata", "installation"), "metadata")
  let schema = orm_text(required(installation, "schema", "installation"))
  let table = orm_text(required(installation, "table", "installation"))
  let oid = required(metadata, "tableOid", "metadata")
  let server = required(metadata, "serverVersion", "metadata")
  let functions = object_fields(required(final_record, "finalFunctions", "final"), "final functions")
  let original_functions = object_fields(required(metadata, "functions", "metadata"), "original functions")
  for name in ["predecessor", "deleted_version", "before", "after"] {
    let first = object_fields(required(original_functions, name, "original functions"), "function")
    let final_meta = object_fields(required(functions, name, "final functions"), "function")
    for field in ["functionOid", "sourceSha256", "source", "functionCatalog"] {
      orm_equal(required(final_meta, field, "final function"), required(first, field, "original function"), "Stable function identity/body/config")
    }
    if name == "before" || name == "after" {
      for field in ["triggerOid", "triggerCatalog"] { orm_equal(required(final_meta, field, "final trigger"), required(first, field, "original trigger"), "Stable trigger identity/config") }
    }
  }
  let cursor = { controls, at: 0, verified: [] }
  let begin = orm2_command(cursor, "BEGIN", Json::null(), "BEGIN", None)
  let lock = orm2_command(cursor, orm2_lock_all(schema, table), Json::null(), "LOCK TABLE", None)
  let catalog_begin = cursor.at
  let (catalog, refs) = orm2_collect_catalog(cursor, schema, table, server, true)
  orm_equal(required(final_record, "finalCatalog", "final"), catalog, "Final raw business catalog leaves")
  orm_equal(required(final_record, "finalCatalogQueryRefs", "final"), refs, "Final catalog raw references")
  orm_equal(catalog, required(metadata, "catalog", "metadata"), "Stable supported business catalog")
  let trigger_oids = orm2_functions(cursor, schema, oid, functions)
  orm2_business_catalog(catalog, oid, true, trigger_oids)
  orm2_marker(cursor, schema, required(metadata, "nonce", "metadata"), oid, final_record, "final")
  let (owned, refs) = orm2_collect_owned(cursor, schema, server)
  orm_equal(required(final_record, "finalOwnedCatalog", "final"), owned, "Final raw owned catalog leaves")
  orm_equal(required(final_record, "finalOwnedCatalogQueryRefs", "final"), refs, "Final owned raw references")
  orm_equal(owned, required(metadata, "ownedCatalog", "metadata"), "Stable supported owned catalogs")
  orm2_owned_catalog(object_fields(owned, "owned catalog"), oid)
  let catalog_end = cursor.at
  let ledger = orm2_select(cursor, "SELECT token::text,key,predecessor::text,action,old_present,new_present,old_image,new_image FROM " + orm2_qualified(schema, "_mtw_orm_effects") + " ORDER BY token LIMIT 513", Json::null(), ["token", "key", "predecessor", "action", "old_present", "new_present", "old_image", "new_image"], [25, 25, 25, 25, 16, 16, 3802, 3802])
  orm_assert(ledger.rows.length() <= 512, "Actual final effect ledger capacity")
  let effects : Array[Json] = []
  for row in ledger.rows {
    let row = orm_array(row)
    orm_assert(row.length() == 8, "Final ledger raw row width")
    effects.push({ "version": row[0], "key": row[1], "predecessor": row[2], "action": row[3], "oldPresent": row[4], "newPresent": row[5], "oldImage": row[6], "newImage": row[7] })
  }
  orm_equal(required(final_record, "ledger", "final"), effects.to_json(), "Actual raw final ledger binding")
  orm_equal(required(final_record, "ledgerQuerySeq", "final"), ledger.seq.to_double().to_json(), "Final ledger raw source reference")
  let snapshot = orm2_snapshot_query(cursor, schema, table)
  orm2_snapshot_rows(snapshot.rows, object_fields(required(final_record, "state", "final"), "final state"), known)
  orm_equal(required(final_record, "finalSnapshotRows", "final"), snapshot.rows.to_json(), "Final raw seven-cell snapshot")
  orm_equal(required(final_record, "finalSnapshotQuerySeq", "final"), snapshot.seq.to_double().to_json(), "Final snapshot raw source reference")
  let commit = orm2_command(cursor, "COMMIT", Json::null(), "COMMIT", None)
  orm_assert(cursor.at == controls.length(), "Unexpected extra finalization control SQL")
  let window : Json = [
    { "kind": "begin", "commandTag": "BEGIN", "querySeq": begin.seq.to_double().to_json() },
    { "kind": "lock", "commandTag": "LOCK TABLE", "mode": "ACCESS EXCLUSIVE", "tableOid": oid, "querySeq": lock.seq.to_double().to_json(), "relations": orm2_relations(schema, table, oid, owned) },
    { "kind": "catalog", "tableOid": oid, "querySeqs": orm2_control_seqs(cursor, catalog_begin, catalog_end) },
    { "kind": "snapshot_and_ledger", "rows": snapshot.rows.to_json(), "effectLedger": effects.to_json(), "snapshotQuerySeq": snapshot.seq.to_double().to_json(), "ledgerQuerySeq": ledger.seq.to_double().to_json() },
    { "kind": "commit", "commandTag": "COMMIT", "querySeq": commit.seq.to_double().to_json() },
  ]
  orm_equal(required(final_record, "finalizationWindow", "final"), window, "Actual final lock/catalog/snapshot/ledger/ACK window")
  ({ "window": window, "ledgerEntries": effects.length().to_json() }, cursor.verified)
}
