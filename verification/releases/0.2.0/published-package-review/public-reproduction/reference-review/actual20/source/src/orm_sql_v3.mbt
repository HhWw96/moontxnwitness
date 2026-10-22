///|
/// Diagnostic transport only: no SQL-gap exemption or accepted history.
priv struct OrmPlan {
  operation : String
  mapping : String
  pk_bind : String
  fields : Array[String]
  original : String
  executed : String
}

///|
priv struct OrmEffect {
  tx : String
  row_seq : Int64
  source_seq : Int64
  data : Map[String, Json]
  mut reverted_by : Json
}

///|
fn orm_assert(ok : Bool, message : String) -> Unit raise {
  if !ok {
    fail(message)
  }
}

///|
fn orm_text(value : Json) -> String raise {
  v3_dislock_text(value, "ORM source text")
}

///|
fn orm_get(value : Json, key : String) -> Json raise {
  required(object_fields(value, "ORM object"), key, "ORM object")
}

///|
fn orm_array(value : Json) -> Array[Json] raise {
  presence_capture_array(value, "ORM array")
}

///|
fn orm_equal(actual : Json, expected : Json, label : String) -> Unit raise {
  orm_assert(actual == expected, "ORM source mismatch: " + label)
}

///|
fn orm_utf8_size(text : String) -> Int {
  @utf8.encode(text[:]).length()
}

///|
fn orm_nodes(value : Json, depth : Int) -> Int raise {
  orm_assert(depth <= 64, "ORM JSON nesting exceeds 64")
  let mut count = 1
  match value {
    Array(values) =>
      for item in values {
        count += orm_nodes(item, depth + 1)
      }
    Object(fields) =>
      for _, item in fields {
        count += 1 + orm_nodes(item, depth + 1)
      }
    _ => ()
  }
  orm_assert(count <= 4096, "Shared ORM source record node budget exceeded")
  count
}

///|
fn orm_exact(value : Json, fields : Array[String]) -> Map[String, Json] raise {
  let obj = object_fields(value, "ORM exact object")
  known_fields(obj, fields, "ORM exact object")
  orm_assert(obj.length() == fields.length(), "Missing ORM exact field")
  obj
}

///|
fn orm_native_text(value : Json, maximum : Int) -> String raise {
  let text = orm_text(value)
  let mut count = 0
  for ch in text.iter() {
    orm_assert(
      ch.to_int() != 0 && !(ch.to_int() >= 0xd800 && ch.to_int() <= 0xdfff),
      "Invalid PostgreSQL native text scalar",
    )
    count += 1
  }
  orm_assert(count <= maximum, "PostgreSQL varchar character limit exceeded")
  text
}

///|
fn orm_uuid(value : Json) -> String raise {
  presence_capture_uuid(value, "ORM canonical UUID")
}

///|
fn orm_bound_uuid(value : Json) -> String raise {
  match value {
    String(_) => orm_uuid(value)
    _ => {
      let obj = orm_exact(value, ["captureType", "value"])
      orm_equal(
        required(obj, "captureType", "UUID"),
        "UUID".to_json(),
        "UUID type",
      )
      orm_uuid(required(obj, "value", "UUID"))
    }
  }
}

///|
fn orm_image(value : Json, key : String, present : Bool) -> Unit raise {
  if !present {
    orm_equal(value, Json::null(), "absent image")
    return
  }
  let obj = orm_exact(value, [
    "id", "email", "hashed_password", "is_active", "is_superuser", "is_verified",
  ])
  orm_assert(
    orm_uuid(required(obj, "id", "image")) == key,
    "Image UUID differs from source key",
  )
  ignore(orm_native_text(required(obj, "email", "image"), 320))
  ignore(orm_native_text(required(obj, "hashed_password", "image"), 1024))
  for name in ["is_active", "is_superuser", "is_verified"] {
    match required(obj, name, "image") {
      True | False => ()
      _ => fail("Image flag must be boolean")
    }
  }
}

///|
fn orm_business_columns() -> Json {
  [
    { "name": "id", "typeCode": 2950 },
    { "name": "email", "typeCode": 1043 },
    { "name": "hashed_password", "typeCode": 1043 },
    { "name": "is_active", "typeCode": 16 },
    { "name": "is_superuser", "typeCode": 16 },
    { "name": "is_verified", "typeCode": 16 },
  ]
}

///|
fn orm_payload(prefix_name : String) -> String {
  "jsonb_build_object('id'," +
  prefix_name +
  ".id::uuid::text,'email'," +
  prefix_name +
  ".email,'hashed_password'," +
  prefix_name +
  ".hashed_password,'is_active'," +
  prefix_name +
  ".is_active,'is_superuser'," +
  prefix_name +
  ".is_superuser,'is_verified'," +
  prefix_name +
  ".is_verified)::text::varchar(12288)"
}

///|
fn orm_plan(
  schema : String,
  table : String,
  operation : String,
  mask : Int,
  pk : String,
) -> OrmPlan raise {
  let names = [
    "id", "email", "hashed_password", "is_active", "is_superuser", "is_verified",
  ]
  let fields : Array[String] = []
  if operation == "update" {
    orm_assert(mask > 0 && mask < 32, "Unknown ORM update mask")
    for i in 0..<5 {
      if (mask & (1 << i)) != 0 {
        fields.push(names[i + 1])
      }
    }
  } else {
    orm_assert(mask == 0, "Unexpected non-update mask")
  }
  let q = schema + "." + table
  let mut original = ""
  let mut executed = ""
  match operation {
    "get" => {
      orm_assert(pk == "id_1" || pk == "pk_1", "Unknown GET binding")
      let selected = names.map(name => q + "." + name).join(", ")
      original = "SELECT " +
        selected +
        " \nFROM " +
        q +
        " \nWHERE " +
        q +
        ".id = %(" +
        pk +
        ")s::UUID"
      executed = "SELECT " +
        selected +
        ", _mtw_scope.token::uuid::text, _mtw_scope.present\nFROM " +
        schema +
        "._mtw_orm_state AS _mtw_scope LEFT JOIN " +
        q +
        " ON " +
        q +
        ".id = _mtw_scope.key::uuid\nWHERE _mtw_scope.key = %(" +
        pk +
        ")s::UUID::text"
    }
    "create" => {
      orm_assert(pk == "id", "Unknown INSERT binding")
      original = "INSERT INTO " +
        q +
        " (id, email, hashed_password, is_active, is_superuser, is_verified) VALUES (%(id)s::UUID, %(email)s::VARCHAR, %(hashed_password)s::VARCHAR, %(is_active)s, %(is_superuser)s, %(is_verified)s)"
      executed = original +
        " RETURNING NEW.id::uuid::text," +
        schema +
        "._mtw_orm_predecessor(NEW._mtw_orm_version::uuid::text)::uuid::text,NEW._mtw_orm_version::uuid::text,false,true,NULL::varchar(12288)," +
        orm_payload("NEW") +
        ",'INSERT'::text"
    }
    "update" => {
      orm_assert(pk == schema + "_" + table + "_id", "Unknown UPDATE binding")
      let sets = fields.map(name => {
        name +
        "=%(" +
        name +
        ")s" +
        (if name == "email" || name == "hashed_password" {
          "::VARCHAR"
        } else {
          ""
        })
      })
      original = "UPDATE " +
        q +
        " SET " +
        sets.join(", ") +
        " WHERE " +
        q +
        ".id = %(" +
        pk +
        ")s::UUID"
      executed = original +
        " RETURNING OLD.id::uuid::text,OLD._mtw_orm_version::uuid::text,NEW._mtw_orm_version::uuid::text,true,true," +
        orm_payload("OLD") +
        "," +
        orm_payload("NEW") +
        ",'UPDATE'::text"
    }
    "delete" => {
      orm_assert(pk == "id", "Unknown DELETE binding")
      original = "DELETE FROM " + q + " WHERE " + q + ".id = %(id)s::UUID"
      executed = original +
        " RETURNING OLD.id::uuid::text,OLD._mtw_orm_version::uuid::text," +
        schema +
        "._mtw_orm_deleted_version(OLD.id::uuid::text,OLD._mtw_orm_version::uuid::text)::uuid::text,true,false," +
        orm_payload("OLD") +
        ",NULL::varchar(12288),'DELETE'::text"
    }
    _ => fail("Unsupported ORM SQL family")
  }
  {
    operation,
    mapping: "fastapi-users.base-user." +
    operation +
    "." +
    mask.to_string() +
    "/1",
    pk_bind: pk,
    fields,
    original,
    executed,
  }
}

///|
fn orm_match_plan(
  batch : Map[String, Json],
  schema : String,
  table : String,
) -> OrmPlan raise {
  let operation = orm_text(required(batch, "operation", "batch"))
  let mapping = orm_text(required(batch, "mappingId", "batch"))
  let params = object_fields(
    required(batch, "parameters", "batch"),
    "parameters",
  )
  let mut mask = 0
  if operation == "update" {
    for
      i, name in [
        "email", "hashed_password", "is_active", "is_superuser", "is_verified",
      ] {
      if params.contains(name) {
        mask += 1 << i
      }
    }
  }
  let pk = match operation {
    "get" => if params.contains("id_1") { "id_1" } else { "pk_1" }
    "update" => schema + "_" + table + "_id"
    _ => "id"
  }
  let plan = orm_plan(schema, table, operation, mask, pk)
  orm_assert(
    mapping == plan.mapping,
    "Mapping name differs from exact SQL family",
  )
  orm_equal(
    required(batch, "originalSql", "batch"),
    plan.original.to_json(),
    "original SQL",
  )
  orm_equal(
    required(batch, "executedSql", "batch"),
    plan.executed.to_json(),
    "executed SQL",
  )
  let allowed = if operation == "create" {
    [
      "id", "email", "hashed_password", "is_active", "is_superuser", "is_verified",
    ]
  } else {
    [pk]
  }
  if operation == "update" {
    for name in plan.fields {
      allowed.push(name)
    }
  }
  known_fields(params, allowed, "ORM parameters")
  orm_assert(params.length() == allowed.length(), "Missing parameter")
  ignore(orm_bound_uuid(required(params, pk, "parameters")))
  for name in allowed {
    if name == "email" || name == "hashed_password" {
      ignore(
        orm_native_text(
          required(params, name, "parameters"),
          if name == "email" {
            320
          } else {
            1024
          },
        ),
      )
    } else if name != pk {
      match required(params, name, "parameters") {
        True | False => ()
        _ => fail("Boolean ORM parameter required")
      }
    }
  }
  plan
}

///|
fn orm_raw_text(raw : Json) -> Json raise {
  if raw == Json::null() {
    return raw
  }
  let obj = orm_exact(raw, ["captureType", "base64"])
  orm_equal(
    required(obj, "captureType", "raw"),
    "bytes".to_json(),
    "raw bytes type",
  )
  let encoded = orm_text(required(obj, "base64", "raw"))
  orm_assert(encoded.length() <= 70000, "Raw source cell bound exceeded")
  let decoded = @base64.decode(encoded[:], ignore_whitespace=false)
  orm_assert(@base64.encode(decoded[:]) == encoded, "Non-canonical base64")
  let text = @utf8.decode(decoded[:], ignore_bom=false)
  orm_assert(
    orm_utf8_size(text) <= 50 * 1024,
    "Raw PGresult source cell exceeds bound",
  )
  text.to_json()
}

///|
fn orm_pg_cells(result : Json, operation : String) -> Array[Json] raise {
  let obj = orm_exact(result, [
    "status", "ntuples", "commandTuples", "commandTag", "fields",
  ])
  for name in ["ntuples", "commandTuples"] {
    orm_equal(
      required(obj, name, "result"),
      (1).to_json(),
      "actual one-row result",
    )
  }
  orm_equal(required(obj, "status", "result"), (2).to_json(), "TUPLES_OK")
  let tag = match operation {
    "get" => "SELECT 1"
    "create" => "INSERT 0 1"
    "update" => "UPDATE 1"
    "delete" => "DELETE 1"
    _ => fail("Unknown command")
  }
  orm_equal(
    orm_raw_text(required(obj, "commandTag", "result")),
    tag.to_json(),
    "actual server command tag",
  )
  let fields = orm_array(required(obj, "fields", "result"))
  orm_assert(
    fields.length() == 8,
    "Actual internal result must have eight columns",
  )
  let oids = if operation == "get" {
    [2950, 1043, 1043, 16, 16, 16, 25, 16]
  } else {
    [25, 25, 25, 16, 16, 1043, 1043, 25]
  }
  let cells : Array[Json] = []
  for i in 0..<8 {
    let field = orm_exact(fields[i], ["oid", "format", "typmod", "raw"])
    orm_equal(
      required(field, "oid", "field"),
      oids[i].to_json(),
      "PG field OID",
    )
    orm_equal(
      required(field, "format", "field"),
      (0).to_json(),
      "text wire format",
    )
    let typmod = if operation == "get" {
      if i == 1 {
        324
      } else if i == 2 {
        1028
      } else {
        -1
      }
    } else if i == 5 || i == 6 {
      12292
    } else {
      -1
    }
    orm_equal(
      required(field, "typmod", "field"),
      typmod.to_json(),
      "PG bounded typmod",
    )
    let raw = orm_raw_text(required(field, "raw", "field"))
    let bool_cell = if operation == "get" {
      i == 3 || i == 4 || i == 5 || i == 7
    } else {
      i == 3 || i == 4
    }
    if raw == Json::null() {
      cells.push(raw)
    } else if bool_cell {
      match orm_text(raw) {
        "t" => cells.push(true.to_json())
        "f" => cells.push(false.to_json())
        _ => fail("Invalid PostgreSQL boolean text")
      }
    } else if operation != "get" && (i == 5 || i == 6) {
      cells.push(guarded_json(orm_text(raw), limit=50176))
    } else if operation == "get" && i == 0 {
      let id = orm_uuid(raw)
      cells.push({ "captureType": "UUID", "value": id.to_json() })
    } else {
      cells.push(raw)
    }
  }
  cells
}

///|
fn orm_command(
  tag : String,
  count : Int,
  description : Json,
  position : Json,
) -> Json {
  {
    "tag": tag.to_json(),
    "rowcount": count.to_json(),
    "description": description,
    "rownumber": position,
  }
}

///|
fn orm_verify_batch(
  batch : Map[String, Json],
  plan : OrmPlan,
  statement : Map[String, Json],
  row : Map[String, Json],
  known : Map[String, Bool],
) -> Json raise {
  let tx = required(batch, "tx", "batch")
  orm_equal(
    required(statement, "kind", "statement"),
    "statement".to_json(),
    "statement kind",
  )
  orm_equal(required(row, "kind", "rows"), "rows".to_json(), "rows kind")
  for event in [statement, row] {
    orm_equal(required(event, "tx", "event"), tx, "same transaction")
  }
  for
    (source, target) in [
      ("originalSql", "sql"),
      ("executedSql", "executedSql"),
      ("mappingId", "mappingId"),
      ("parameters", "parameters"),
    ] {
    orm_equal(
      required(statement, target, "statement"),
      required(batch, source, "batch"),
      "statement " + target,
    )
  }
  orm_equal(
    required(row, "statement", "rows"),
    required(batch, "statement", "batch"),
    "rows statement reference",
  )
  orm_equal(
    required(row, "complete", "rows"),
    true.to_json(),
    "actual business EOF/delivery",
  )
  let observation = object_fields(
    required(batch, "observation", "batch"),
    "observation",
  )
  orm_equal(
    required(observation, "profile", "observation"),
    "fastapi-users-sqlalchemy-7.0.0-pg18/1".to_json(),
    "observation profile",
  )
  orm_equal(
    required(observation, "mappingId", "observation"),
    plan.mapping.to_json(),
    "observation mapping",
  )
  orm_equal(
    required(observation, "proposedWireOnly", "observation"),
    true.to_json(),
    "diagnostic-only source carrier",
  )
  let params = object_fields(required(batch, "parameters", "batch"), "params")
  let key = orm_bound_uuid(required(params, plan.pk_bind, "params"))
  orm_assert(known.contains(key), "Unknown UUID domain")
  let cells = orm_pg_cells(
    required(batch, "actualPGresult", "batch"),
    plan.operation,
  )
  let mut kind = ""
  let mut version = ""
  let mut data : Json = Json::null()
  if plan.operation == "get" {
    let source = orm_exact(required(observation, "source", "get"), [
      "key", "version", "present",
    ])
    orm_equal(
      required(source, "key", "source"),
      key.to_json(),
      "GET source key",
    )
    version = orm_uuid(required(source, "version", "source"))
    orm_equal(cells[6], version.to_json(), "GET raw version")
    orm_equal(
      cells[7],
      required(source, "present", "source"),
      "GET actual presence",
    )
    let present = cells[7] == true.to_json()
    orm_assert(
      present || cells[7] == false.to_json(),
      "Presence flag must be boolean",
    )
    let rows = orm_array(required(observation, "rows", "get"))
    orm_equal(required(row, "rows", "rows"), rows.to_json(), "business rows")
    orm_equal(
      required(observation, "complete", "get"),
      true.to_json(),
      "GET complete",
    )
    orm_equal(
      required(row, "columns", "rows"),
      orm_business_columns(),
      "business columns only",
    )
    let mut image : Json = Json::null()
    if present {
      orm_assert(rows.length() == 1, "Positive point GET must deliver one row")
      let business = orm_array(rows[0])
      orm_assert(business.length() == 6, "Business GET width must remain six")
      for i in 0..<6 {
        orm_equal(cells[i], business[i], "business PGresult prefix")
      }
      orm_equal(
        required(observation, "serverRows", "get"),
        [cells.to_json()].to_json(),
        "positive internal row",
      )
      orm_equal(
        required(row, "serverRows", "rows"),
        required(observation, "serverRows", "get"),
        "original positive source row",
      )
      orm_assert(
        !observation.contains("presenceRows") && !row.contains("presenceRows"),
        "Positive source cannot carry negative rows",
      )
      orm_equal(
        business[0],
        { "captureType": "UUID", "value": key.to_json() },
        "business UUID",
      )
      image = {
        "id": key.to_json(),
        "email": business[1],
        "hashed_password": business[2],
        "is_active": business[3],
        "is_superuser": business[4],
        "is_verified": business[5],
      }
      orm_image(image, key, true)
    } else {
      orm_assert(
        rows.length() == 0,
        "Negative GET must deliver no business rows",
      )
      for i in 0..<6 {
        orm_equal(cells[i], Json::null(), "negative joined source NULL")
      }
      orm_equal(
        required(observation, "presenceRows", "get"),
        [cells.to_json()].to_json(),
        "negative source row",
      )
      orm_assert(
        !observation.contains("serverRows") && !row.contains("serverRows"),
        "Negative source cannot masquerade as positive result",
      )
      image = Json::null()
    }
    let count = if present { 1 } else { 0 }
    orm_equal(
      required(batch, "businessCommand", "batch"),
      orm_command(
        "SELECT " + count.to_string(),
        count,
        orm_business_columns(),
        count.to_json(),
      ),
      "business SELECT facade",
    )
    kind = "read"
    data = {
      "key": key.to_json(),
      "version": version.to_json(),
      "present": present.to_json(),
      "image": image,
    }
  } else {
    let effects = orm_array(required(observation, "effectRows", "command"))
    orm_equal(
      effects.to_json(),
      [cells.to_json()].to_json(),
      "decoded effect row and actual result",
    )
    orm_equal(
      required(row, "rows", "rows"),
      orm_empty(),
      "command business rows empty",
    )
    orm_equal(
      required(observation, "rows", "command"),
      orm_empty(),
      "command observation rows empty",
    )
    orm_assert(
      !row.contains("serverRows") &&
      !row.contains("presenceRows") &&
      !row.contains("columns"),
      "Command cannot expose private metadata as business columns",
    )
    orm_equal(cells[0], key.to_json(), "DML bound key")
    let predecessor = orm_uuid(cells[1])
    version = orm_uuid(cells[2])
    orm_assert(version != predecessor, "Write source identity must change")
    let action = match plan.operation {
      "create" => "INSERT"
      "update" => "UPDATE"
      _ => "DELETE"
    }
    orm_equal(cells[7], action.to_json(), "DML action")
    let old_present = plan.operation != "create"
    let new_present = plan.operation != "delete"
    orm_equal(cells[3], old_present.to_json(), "DML OLD presence")
    orm_equal(cells[4], new_present.to_json(), "DML NEW presence")
    orm_image(cells[5], key, old_present)
    orm_image(cells[6], key, new_present)
    if new_present {
      let new_image = object_fields(cells[6], "NEW")
      if plan.operation == "create" {
        for
          name in [
            "email", "hashed_password", "is_active", "is_superuser", "is_verified",
          ] {
          orm_equal(
            required(new_image, name, "NEW"),
            required(params, name, "params"),
            "INSERT exact NEW parameter",
          )
        }
      } else {
        let old_image = object_fields(cells[5], "OLD")
        for
          name in [
            "email", "hashed_password", "is_active", "is_superuser", "is_verified",
          ] {
          orm_equal(
            required(new_image, name, "NEW"),
            if params.contains(name) {
              required(params, name, "params")
            } else {
              required(old_image, name, "OLD")
            },
            "UPDATE declared/unmodified field",
          )
        }
      }
    }
    let tag = if action == "INSERT" { "INSERT 0 1" } else { action + " 1" }
    let command = orm_command(tag, 1, Json::null(), Json::null())
    orm_equal(
      required(batch, "businessCommand", "batch"),
      command,
      "business command facade",
    )
    orm_equal(
      required(observation, "command", "command"),
      command,
      "observed business command facade",
    )
    kind = "write"
    data = {
      "key": key.to_json(),
      "version": version.to_json(),
      "predecessor": predecessor.to_json(),
      "action": action.to_json(),
      "oldPresent": old_present.to_json(),
      "newPresent": new_present.to_json(),
      "oldImage": cells[5],
      "newImage": cells[6],
    }
  }
  {
    "kind": kind.to_json(),
    "sourceSeq": required(batch, "sourceSeq", "batch"),
    "statement": required(batch, "statement", "batch"),
    "rows": required(batch, "businessRowsEvent", "batch"),
    "tx": tx,
    "data": data,
  }
}

///|
fn orm_empty() -> Json {
  let items : Array[Json] = []
  items.to_json()
}
