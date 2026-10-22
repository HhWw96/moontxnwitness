///|
priv enum RelationV3Cell {
  Integer(Int64)
  Text(String)
  Boolean(Bool)
} derive(Eq)

///|
priv struct RelationV3Table {
  name : String
  primary : String
  primary_type : String
  columns : Array[(String, String)]
}

///|
priv struct RelationV3Key {
  table : Int
  value : RelationV3Cell
  wire : Json
}

///|
priv struct RelationV3Row {
  key : Int
  version : String
  values : Array[RelationV3Cell]
}

///|
priv struct RelationV3Source {
  row : RelationV3Row
  action : String
  predecessor : String?
  writer : String?
  seq : Int64
}

///|
priv struct RelationV3Predicate {
  column : Int
  op : String
  value : RelationV3Cell
}

///|
priv enum RelationV3Action {
  WriteRow(Int)
  QueryRows(Int, Array[RelationV3Predicate], Array[RelationV3Row], Int64)
  Mark(String)
  Undo(String)
  Release(String)
}

///|
priv struct RelationV3Program {
  id : String
  status : TxStatus
  actions : Array[RelationV3Action]
}

///|
priv struct RelationV3Parsed {
  normalized : Json
  tables : Array[RelationV3Table]
  keys : Array[RelationV3Key]
  initial : Array[Int]
  sources : Array[RelationV3Source]
  programs : Array[RelationV3Program]
  findings : Array[Json]
  source_evidence : Array[Json]
  operations : Int
}

///|
priv struct RelationV3Search {
  parsed : RelationV3Parsed
  programs : Array[RelationV3Program]
  state : Array[Int]
  sorted_keys : Array[Array[Int]]
  trail : Array[(Int, Int)]
  prefix : Array[String]
  blockers : Array[Json]
  options : ListV3Options
  mut states : Int
  mut operations : Int
  mut limited : Bool
  mut reason : String
}

///|
fn relation_v3_scalar(text : String) -> Unit raise {
  let units = text.code_units()
  let mut i = 0
  while i < units.length() {
    let unit = units[i].to_int()
    if unit >= 0xd800 && unit <= 0xdbff {
      if i + 1 >= units.length() ||
        units[i + 1] < 0xdc00 ||
        units[i + 1] > 0xdfff {
        fail("Relation text must contain valid Unicode scalar values")
      }
      i += 2
    } else {
      if unit >= 0xdc00 && unit <= 0xdfff {
        fail("Relation text must contain valid Unicode scalar values")
      }
      i += 1
    }
  }
}

///|
fn relation_v3_identifier(value : Json) -> String raise {
  let result = match value {
    String(text) if text.length() >= 1 && text.length() <= 256 => text
    _ => fail("Version identities must have 1..256 UTF-16 code units")
  }
  // Model versions are opaque Unicode scalar strings, not SQL/transaction
  // identifiers: NUL, whitespace and other scalar controls are valid identities.
  relation_v3_scalar(result)
  result
}

///|
fn relation_v3_name(value : String) -> Unit raise {
  if value.length() < 1 || value.length() > 63 {
    fail(
      "Relation and column names must have 1..63 ASCII identifier characters",
    )
  }
  for i, unit in value.code_units() {
    let ch = unit.to_int()
    if !(ch == 95 ||
      (ch >= 65 && ch <= 90) ||
      (ch >= 97 && ch <= 122) ||
      (i > 0 && ch >= 48 && ch <= 57)) {
      fail("Relation and column names must be ASCII identifiers")
    }
  }
}

///|
fn relation_v3_int64(text : String) -> Int64 raise {
  let negative = text.has_prefix("-")
  let digits = if negative { text[1:].to_owned() } else { text }
  if digits.length() == 0 || digits.length() > 19 {
    fail("Expected a canonical signed int64 decimal string")
  }
  if (digits.length() > 1 && digits[0] == 48) || (negative && digits == "0") {
    fail("Int64 strings cannot have leading zeros or negative zero")
  }
  for unit in digits.code_units() {
    if unit < 48 || unit > 57 {
      fail(
        "Int64 strings can contain only decimal digits and an optional minus",
      )
    }
  }
  let bound = if negative {
    "9223372036854775808"
  } else {
    "9223372036854775807"
  }
  if digits.length() == 19 && digits > bound {
    fail("Int64 decimal string is outside the signed 64-bit range")
  }
  // Accumulating negative values keeps -2^63 representable at every step.
  let mut result = 0L
  for unit in digits.code_units() {
    result = result * 10L - (unit.to_int() - 48).to_int64()
  }
  if negative {
    result
  } else {
    -result
  }
}

///|
fn relation_v3_cell(raw : Json, kind : String) -> RelationV3Cell raise {
  match (kind, raw) {
    ("int64", String(text)) => Integer(relation_v3_int64(text))
    ("text", String(text)) => {
      relation_v3_scalar(text)
      Text(text)
    }
    ("bool", True) => Boolean(true)
    ("bool", False) => Boolean(false)
    _ => fail("Relation value does not match its declared column type")
  }
}

///|
fn relation_v3_optional_text(value : String?) -> Json {
  match value {
    None => Json::null()
    Some(text) => text.to_json()
  }
}

///|
fn relation_v3_wire(cell : RelationV3Cell) -> Json {
  match cell {
    Integer(value) => value.to_string().to_json()
    Text(value) => value.to_json()
    Boolean(value) => value.to_json()
  }
}

///|
fn relation_v3_text_compare(a : String, b : String) -> Int {
  let aa = a.code_units()
  let bb = b.code_units()
  let mut i = 0
  let mut j = 0
  while i < aa.length() && j < bb.length() {
    let mut av = aa[i].to_int()
    let mut bv = bb[j].to_int()
    i += 1
    j += 1
    if av >= 0xd800 && av <= 0xdbff {
      av = 0x10000 + (av - 0xd800) * 1024 + aa[i].to_int() - 0xdc00
      i += 1
    }
    if bv >= 0xd800 && bv <= 0xdbff {
      bv = 0x10000 + (bv - 0xd800) * 1024 + bb[j].to_int() - 0xdc00
      j += 1
    }
    if av < bv {
      return -1
    }
    if av > bv {
      return 1
    }
  }
  if i < aa.length() {
    1
  } else if j < bb.length() {
    -1
  } else {
    0
  }
}

///|
fn relation_v3_compare(a : RelationV3Cell, b : RelationV3Cell) -> Int {
  match (a, b) {
    (Integer(a), Integer(b)) => if a < b { -1 } else if a > b { 1 } else { 0 }
    (Text(a), Text(b)) => relation_v3_text_compare(a, b)
    (Boolean(a), Boolean(b)) => if a == b { 0 } else if a { 1 } else { -1 }
    _ => abort("Relation typed comparison invariant")
  }
}

///|
fn relation_v3_schema(raw : Json) -> Array[RelationV3Table] raise {
  let fields = object_fields(raw, "relationSchema")
  if fields.length() < 1 || fields.length() > 8 {
    fail("relationSchema must declare 1..8 relations")
  }
  let result : Array[RelationV3Table] = []
  for name, raw_table in fields {
    relation_v3_name(name)
    let table = object_fields(raw_table, "relation schema")
    known_fields(table, ["primaryKey", "columns"], "relation schema")
    let primary = identifier(
      required(table, "primaryKey", "relation schema"),
      "primaryKey",
    )
    relation_v3_name(primary)
    let columns = object_fields(
      required(table, "columns", "relation schema"),
      "columns",
    )
    if columns.length() < 1 || columns.length() > 16 {
      fail("Each relation must declare 1..16 columns")
    }
    let primary_type = identifier(
      required(columns, primary, "columns"),
      "primary type",
    )
    if primary_type != "int64" && primary_type != "text" {
      fail("Primary keys must be int64 or text")
    }
    let non_primary : Array[(String, String)] = []
    for column, raw_type in columns {
      relation_v3_name(column)
      let kind = identifier(raw_type, "column type")
      if !["int64", "text", "bool"].contains(kind) {
        fail("Only int64, text and bool columns are supported")
      }
      if column != primary {
        non_primary.push((column, kind))
      }
    }
    result.push({ name, primary, primary_type, columns: non_primary, })
  }
  result
}

///|
fn relation_v3_values(
  raw : Json,
  table : RelationV3Table,
) -> Array[RelationV3Cell] raise {
  let fields = object_fields(raw, "row.values")
  if fields.length() != table.columns.length() {
    fail("Row values must contain exactly every non-primary column")
  }
  table.columns.map(column => {
    relation_v3_cell(required(fields, column.0, "row.values"), column.1)
  })
}

///|
fn relation_v3_key(
  raw : Json,
  table_index : Int,
  tables : Array[RelationV3Table],
  keys : Array[RelationV3Key],
  indices : Map[String, Int],
) -> Int raise {
  let table = tables[table_index]
  let cell = relation_v3_cell(raw, table.primary_type)
  // JSON array framing includes relation, type and exact value. No delimiter
  // concatenation can alias a second relation or a distinct text/int64 key.
  let encoded : Json = [table.name.to_json(), table.primary_type.to_json(), raw]
  let encoded = encoded.stringify()
  match indices.get(encoded) {
    Some(index) => index
    None => {
      if keys.length() >= 1024 {
        fail("At most 1,024 distinct relation keys are supported")
      }
      let index = keys.length()
      keys.push({ table: table_index, value: cell, wire: raw, })
      indices[encoded] = index
      index
    }
  }
}

///|
fn relation_v3_row(
  raw : Json,
  table_index : Int,
  tables : Array[RelationV3Table],
  keys : Array[RelationV3Key],
  indices : Map[String, Int],
) -> RelationV3Row raise {
  let fields = object_fields(raw, "row")
  known_fields(fields, ["key", "version", "values"], "row")
  {
    key: relation_v3_key(
      required(fields, "key", "row"),
      table_index,
      tables,
      keys,
      indices,
    ),
    version: relation_v3_identifier(required(fields, "version", "row")),
    values: relation_v3_values(
      required(fields, "values", "row"),
      tables[table_index],
    ),
  }
}

///|
fn relation_v3_predicates(
  raw : Json,
  table : RelationV3Table,
) -> Array[RelationV3Predicate] raise {
  let items = presence_capture_array(raw, "predicate")
  if items.length() > 8 {
    fail("At most 8 AND predicate terms are supported")
  }
  items.map(raw => {
    let item = object_fields(raw, "predicate term")
    known_fields(item, ["column", "op", "value"], "predicate term")
    let column = identifier(
      required(item, "column", "predicate term"),
      "column",
    )
    let op = identifier(required(item, "op", "predicate term"), "op")
    if !["eq", "lt", "le", "gt", "ge"].contains(op) {
      fail("Unsupported predicate operator")
    }
    let mut index = -1
    let mut kind = table.primary_type
    if column != table.primary {
      index = -2
      for i, entry in table.columns {
        if entry.0 == column {
          index = i
          kind = entry.1
        }
      }
      if index == -2 {
        fail("Predicate references an undeclared column")
      }
    }
    if kind == "bool" && op != "eq" {
      fail("Bool predicates support only eq")
    }
    {
      column: index,
      op,
      value: relation_v3_cell(required(item, "value", "predicate term"), kind),
    }
  })
}

///|
fn relation_v3_predicate_matches(
  predicate : RelationV3Predicate,
  row : RelationV3Row,
  keys : Array[RelationV3Key],
) -> Bool {
  let actual = if predicate.column == -1 {
    keys[row.key].value
  } else {
    row.values[predicate.column]
  }
  let comparison = relation_v3_compare(actual, predicate.value)
  match predicate.op {
    "eq" => comparison == 0
    "lt" => comparison < 0
    "le" => comparison <= 0
    "gt" => comparison > 0
    "ge" => comparison >= 0
    _ => false
  }
}

///|
fn relation_v3_values_json(
  source : RelationV3Source,
  tables : Array[RelationV3Table],
  keys : Array[RelationV3Key],
) -> Json {
  if source.action == "delete" {
    return Json::null()
  }
  let result : Map[String, Json] = Map([])
  for i, column in tables[keys[source.row.key].table].columns {
    result[column.0] = relation_v3_wire(source.row.values[i])
  }
  Json::object(result)
}

///|
fn relation_v3_finding(
  code : String,
  tx : String,
  seq : Int64,
  table : String,
  key : Json,
  version : String,
) -> Json {
  {
    "code": code.to_json(),
    "tx": tx.to_json(),
    "seq": seq.to_double().to_json(),
    "relation": table.to_json(),
    "key": key,
    "version": version.to_json(),
  }
}

///|
fn relation_v3_invalid(text : String, message : String) -> Json {
  let observations = object_fields(guarded_json(text, limit=8388608), "trace").get_or_default(
    "events",
    Json::null(),
  ) catch {
    _ => Json::null()
  }
  {
    "schema": 3,
    "dataModel": "relation-set-v1",
    "algorithm": "v3-relation-lifecycle-1",
    "status": "invalid",
    "coverage": {
      "complete": false,
      "gaps": [capture_gap("invalid_relation_capture_v3", message)],
    },
    "observations": observations,
    "effects": [],
    "transactions": [],
    "history": Json::null(),
  }
}

///|
fn relation_v3_parse(text : String) -> RelationV3Parsed raise {
  let root = object_fields(guarded_json(text, limit=8388608), "relation trace")
  known_fields(
    root,
    [
      "traceSchema", "dataModel", "relationSchema", "clockDomain", "scope", "events",
      "gaps",
    ],
    "relation trace",
  )
  if required(root, "traceSchema", "relation trace") != (3).to_json() ||
    required(root, "dataModel", "relation trace") != "relation-set-v1".to_json() {
    fail("Expected traceSchema 3 and dataModel relation-set-v1")
  }
  let tables = relation_v3_schema(
    required(root, "relationSchema", "relation trace"),
  )
  let table_indices : Map[String, Int] = Map([])
  for i, table in tables {
    table_indices[table.name] = i
  }
  let scope = object_fields(required(root, "scope", "relation trace"), "scope")
  known_fields(scope, ["exclusiveWriters", "completeSnapshotTables"], "scope")
  let complete_tables : Map[String, Bool] = Map([])
  match scope.get("completeSnapshotTables") {
    Some(raw) =>
      for item in presence_capture_array(raw, "completeSnapshotTables") {
        let name = identifier(item, "completeSnapshotTables member")
        if !table_indices.contains(name) || complete_tables.contains(name) {
          fail(
            "Complete snapshot tables must be unique declared relation names",
          )
        }
        complete_tables[name] = true
      }
    None => ()
  }
  let observations = required(root, "events", "relation trace")
  let events = presence_capture_array(observations, "events")
  if events.length() > 65536 {
    fail("At most 65,536 relation events are supported")
  }
  let keys : Array[RelationV3Key] = []
  let key_indices : Map[String, Int] = Map([])
  let sources : Array[RelationV3Source] = []
  let versions : Map[String, Int] = Map([])
  let writes : Map[Int64, Int] = Map([])
  let actions : Map[Int64, RelationV3Action] = Map([])
  let initial_pairs : Array[(Int, Int)] = []
  let mut snapshot_seen = false
  let mut operations = 0
  let mut references = 0
  let mut write_number = 0
  let mut needs_sentinel = false
  for raw in events {
    let event = object_fields(raw, "event")
    let kind = identifier(required(event, "kind", "event"), "kind")
    let seq = v3_capture_seq(required(event, "seq", "event"), "seq")
    if kind == "snapshot" {
      known_fields(
        event,
        ["kind", "seq", "time", "initial", "consistent"],
        "snapshot",
      )
      if snapshot_seen {
        fail("Exactly one relation snapshot is required")
      }
      snapshot_seen = true
      let initial = object_fields(
        required(event, "initial", "snapshot"),
        "initial",
      )
      if initial.length() != tables.length() {
        fail("Snapshot must explicitly include every declared relation")
      }
      for table_index, table in tables {
        for
          raw_row in presence_capture_array(
            required(initial, table.name, "initial"),
            "initial relation rows",
          ) {
          let row = relation_v3_row(
            raw_row, table_index, tables, keys, key_indices,
          )
          if initial_pairs.any(pair => pair.0 == row.key) {
            fail("Duplicate initial primary key")
          }
          if versions.contains(row.version) {
            fail("Producer versions must be globally unique")
          }
          versions[row.version] = sources.length()
          initial_pairs.push((row.key, sources.length()))
          sources.push({
            row,
            action: "snapshot",
            predecessor: None,
            writer: None,
            seq,
          })
        }
      }
    } else if kind == "row_write" {
      known_fields(
        event,
        [
          "kind", "seq", "time", "tx", "relation", "key", "action", "version", "predecessor",
          "values",
        ],
        "row_write",
      )
      let relation = identifier(required(event, "relation", kind), "relation")
      let table = match table_indices.get(relation) {
        Some(index) => index
        None => fail("Operation references an undeclared relation")
      }
      let tx = identifier(required(event, "tx", kind), "tx")
      let action = identifier(required(event, "action", kind), "action")
      if !["insert", "update", "delete"].contains(action) {
        fail("Unsupported row action")
      }
      let predecessor = match required(event, "predecessor", kind) {
        Null if action == "insert" => None
        String(value) => Some(relation_v3_identifier(value.to_json()))
        _ =>
          fail(
            "Update and delete require a nonempty predecessor version; only insert accepts null",
          )
      }
      let key = relation_v3_key(
        required(event, "key", kind),
        table,
        tables,
        keys,
        key_indices,
      )
      let version = relation_v3_identifier(required(event, "version", kind))
      let raw_values = required(event, "values", kind)
      let values = if action == "delete" {
        if raw_values != Json::null() {
          fail("Delete values must be null")
        }
        []
      } else {
        relation_v3_values(raw_values, tables[table])
      }
      if versions.contains(version) {
        fail("Producer versions must be globally unique")
      }
      versions[version] = sources.length()
      writes[seq] = sources.length()
      actions[seq] = WriteRow(sources.length())
      sources.push({
        row: { key, version, values, },
        action,
        predecessor,
        writer: Some(tx),
        seq,
      })
      write_number += 1
      operations += 1
    } else if kind == "row_read" {
      known_fields(
        event,
        [
          "kind", "seq", "time", "tx", "relation", "predicate", "rows", "complete",
        ],
        "row_read",
      )
      let relation = identifier(required(event, "relation", kind), "relation")
      let table = match table_indices.get(relation) {
        Some(index) => index
        None => fail("Operation references an undeclared relation")
      }
      let _ = identifier(required(event, "tx", kind), "tx")
      let predicate = relation_v3_predicates(
        required(event, "predicate", kind),
        tables[table],
      )
      let rows = presence_capture_array(required(event, "rows", kind), "rows").map(raw => {
          references += 1
          if references > 100000 {
            fail("At most 100,000 returned row references are supported")
          }
          relation_v3_row(raw, table, tables, keys, key_indices)
        },
      )
      match required(event, "complete", kind) {
        True | False => ()
        _ => fail("row_read.complete must be boolean")
      }
      actions[seq] = QueryRows(table, predicate, rows, seq)
      operations += 1
      needs_sentinel = true
    } else if kind == "read" ||
      kind == "write" ||
      kind == "append" ||
      kind == "list_read" {
      fail(
        "Relation operations cannot be mixed with register or append-list operations",
      )
    }
  }
  if !snapshot_seen {
    fail("Exactly one relation snapshot is required")
  }
  if operations > 10000 {
    fail("At most 10,000 semantic relation operations are supported")
  }
  let lifecycle_initial : Map[String, String] = Map([])
  for i in 0..<write_number {
    lifecycle_initial["relation-life-key-" + i.to_string()] = "relation-life-initial-" +
      i.to_string()
  }
  if needs_sentinel {
    lifecycle_initial["relation-life-read-key"] = "relation-life-read-initial"
  }
  let metadata : Array[Json] = []
  let mut write_index = 0
  for raw in events {
    let event = object_fields(raw, "event")
    let kind = identifier(required(event, "kind", "event"), "kind")
    let copy = list_v3_copy(event)
    if kind == "snapshot" {
      copy["initial"] = lifecycle_initial.to_json()
      metadata.push(Json::object(copy))
    } else if kind == "row_write" {
      metadata.push({
        "seq": event.at("seq"),
        "time": event.at("time"),
        "kind": "write",
        "tx": event.at("tx"),
        "key": ("relation-life-key-" + write_index.to_string()).to_json(),
        "version": ("relation-life-write-" + write_index.to_string()).to_json(),
        "predecessor": ("relation-life-initial-" + write_index.to_string()).to_json(),
      })
      write_index += 1
    } else if kind == "row_read" {
      metadata.push({
        "seq": event.at("seq"),
        "time": event.at("time"),
        "kind": "read",
        "tx": event.at("tx"),
        "key": "relation-life-read-key",
        "version": "relation-life-read-initial",
      })
    } else if kind == "condition" {
      known_fields(
        event,
        ["seq", "time", "kind", "tx", "predicate", "matched", "sourceVersion"],
        "condition",
      )
      let safe : Map[String, Json] = Map([])
      for key, value in copy {
        if key != "sourceVersion" {
          safe[key] = value
        }
      }
      match event.get("sourceVersion") {
        Some(value) => {
          let _ = relation_v3_identifier(value)
        }
        None => ()
      }
      metadata.push(Json::object(safe))
    } else {
      metadata.push(Json::object(copy))
    }
  }
  let life_trace : Json = {
    "traceSchema": 3,
    "clockDomain": required(root, "clockDomain", "relation trace"),
    "scope": {
      "exclusiveWriters": required(scope, "exclusiveWriters", "scope"),
    },
    "events": metadata.to_json(),
    "gaps": required(root, "gaps", "relation trace"),
  }
  let life = object_fields(
    guarded_json(
      normalize_register_capture_v3_json(life_trace.stringify()),
      limit=33554432,
    ),
    "lifecycle",
  )
  if life.at("status") == "invalid".to_json() {
    fail("Invalid relation transaction lifecycle")
  }
  let coverage = object_fields(life.at("coverage"), "coverage")
  let gaps = presence_capture_array(coverage.at("gaps"), "gaps").copy()
  for table in tables {
    if !complete_tables.contains(table.name) {
      gaps.push(
        capture_gap(
          "incomplete_relation_snapshot", "A declared relation lacks a complete initial snapshot",
        ),
      )
    }
  }
  let raw_transactions = presence_capture_array(
    life.at("transactions"),
    "transactions",
  )
  let programs : Array[RelationV3Program] = []
  let program_indices : Map[String, Int] = Map([])
  let outcomes : Map[String, TxStatus] = Map([])
  for raw in raw_transactions {
    let fields = object_fields(raw, "transaction")
    let id = identifier(fields.at("id"), "transaction.id")
    let status = match fields.at("status") {
      String("committed") => Committed
      String("aborted") => Aborted
      _ => Unknown
    }
    program_indices[id] = programs.length()
    outcomes[id] = status
    programs.push({ id, status, actions: [], })
  }
  let effects : Array[Json] = []
  let revoked : Map[Int64, Int64?] = Map([])
  for raw in presence_capture_array(life.at("effects"), "effects") {
    let effect = object_fields(raw, "effect")
    let seq = v3_capture_seq(effect.at("seq"), "effect.seq")
    let source = sources[writes.at(seq)]
    let key = keys[source.row.key]
    let reverted = effect.at("revertedBy")
    revoked[seq] = match reverted {
      Null => None
      value => Some(v3_capture_seq(value, "revertedBy"))
    }
    effects.push({
      "seq": seq.to_double().to_json(),
      "tx": source.writer.unwrap().to_json(),
      "relation": tables[key.table].name.to_json(),
      "key": key.wire,
      "action": source.action.to_json(),
      "version": source.row.version.to_json(),
      "predecessor": relation_v3_optional_text(source.predecessor),
      "values": relation_v3_values_json(source, tables, keys),
      "revertedBy": reverted,
    })
  }
  let transactions : Array[Json] = []
  for raw in raw_transactions {
    let tx = list_v3_copy(object_fields(raw, "transaction"))
    let id = identifier(tx.at("id"), "transaction.id")
    let last : Map[Int, Int64] = Map([])
    for source in sources {
      if source.writer == Some(id) && revoked.get(source.seq) == Some(None) {
        last[source.row.key] = source.seq
      }
    }
    let finals : Array[Json] = []
    for source in sources {
      if source.writer == Some(id) &&
        last.get(source.row.key) == Some(source.seq) {
        finals.push(source.seq.to_double().to_json())
      }
    }
    tx["finalWrites"] = finals.to_json()
    transactions.push(Json::object(tx))
  }
  let findings : Array[Json] = []
  for raw in events {
    let event = object_fields(raw, "event")
    let kind = identifier(event.at("kind"), "kind")
    if !["row_write", "row_read", "savepoint", "rollback_to", "release"].contains(
        kind,
      ) {
      continue
    }
    let seq = v3_capture_seq(event.at("seq"), "seq")
    let tx = identifier(event.at("tx"), "tx")
    let program = programs[program_indices.at(tx)]
    if kind == "row_write" {
      let source = sources[writes.at(seq)]
      match source.predecessor {
        None => ()
        Some(predecessor) =>
          match versions.get(predecessor) {
            None =>
              gaps.push(
                capture_gap(
                  "missing_predecessor_source", "A row predecessor has no earlier observed producer",
                ),
              )
            Some(index) => {
              let prior = sources[index]
              if prior.seq >= seq {
                gaps.push(
                  capture_gap(
                    "missing_predecessor_source", "A row predecessor producer was not observed before the write",
                  ),
                )
              }
              if program.status == Committed {
                let key = keys[source.row.key]
                let code = if keys[prior.row.key].table != key.table {
                  "predecessor_relation_mismatch"
                } else if prior.row.key != source.row.key {
                  "predecessor_key_mismatch"
                } else {
                  ""
                }
                if code != "" {
                  findings.push(
                    relation_v3_finding(
                      code,
                      tx,
                      seq,
                      tables[key.table].name,
                      key.wire,
                      predecessor,
                    ),
                  )
                }
                match prior.writer {
                  Some(writer) => {
                    if writer != tx && outcomes.get(writer) == Some(Aborted) {
                      findings.push(
                        relation_v3_finding(
                          "write_from_aborted_predecessor",
                          tx,
                          seq,
                          tables[key.table].name,
                          key.wire,
                          predecessor,
                        ),
                      )
                    }
                    match revoked.get(prior.seq) {
                      Some(Some(at)) if writer != tx || at < seq =>
                        findings.push(
                          relation_v3_finding(
                            "write_from_reverted_predecessor",
                            tx,
                            seq,
                            tables[key.table].name,
                            key.wire,
                            predecessor,
                          ),
                        )
                      _ => ()
                    }
                  }
                  None => ()
                }
              }
            }
          }
      }
    } else if kind == "row_read" {
      if event.at("complete") != true.to_json() {
        gaps.push(
          capture_gap(
            "incomplete_query", "A relation query was not fully delivered",
          ),
        )
      }
      match actions.at(seq) {
        QueryRows(table, predicate, rows, _) => {
          let seen : Map[Int, Bool] = Map([])
          for row in rows {
            let key = keys[row.key]
            if program.status == Committed {
              if seen.contains(row.key) {
                findings.push(
                  relation_v3_finding(
                    "duplicate_result_key",
                    tx,
                    seq,
                    tables[table].name,
                    key.wire,
                    row.version,
                  ),
                )
              }
              if !predicate.all(term => {
                  relation_v3_predicate_matches(term, row, keys)
                }) {
                findings.push(
                  relation_v3_finding(
                    "row_predicate_mismatch",
                    tx,
                    seq,
                    tables[table].name,
                    key.wire,
                    row.version,
                  ),
                )
              }
            }
            seen[row.key] = true
            match versions.get(row.version) {
              None =>
                gaps.push(
                  capture_gap(
                    "missing_row_source", "A returned row version has no earlier captured source",
                  ),
                )
              Some(index) => {
                let source = sources[index]
                if source.seq >= seq {
                  gaps.push(
                    capture_gap(
                      "missing_row_source", "A returned row producer was not observed before the query",
                    ),
                  )
                }
                if program.status == Committed {
                  let code = if keys[source.row.key].table != table {
                    "row_relation_mismatch"
                  } else if source.row.key != row.key {
                    "row_key_mismatch"
                  } else if source.action == "delete" {
                    "read_from_tombstone"
                  } else if source.row.values != row.values {
                    "row_value_mismatch"
                  } else {
                    ""
                  }
                  if code != "" {
                    findings.push(
                      relation_v3_finding(
                        code,
                        tx,
                        seq,
                        tables[table].name,
                        key.wire,
                        row.version,
                      ),
                    )
                  }
                  match source.writer {
                    Some(writer) => {
                      if writer != tx && outcomes.get(writer) == Some(Aborted) {
                        findings.push(
                          relation_v3_finding(
                            "read_from_aborted_row",
                            tx,
                            seq,
                            tables[table].name,
                            key.wire,
                            row.version,
                          ),
                        )
                      }
                      match revoked.get(source.seq) {
                        Some(Some(at)) if writer != tx || at < seq =>
                          findings.push(
                            relation_v3_finding(
                              "read_from_reverted_row",
                              tx,
                              seq,
                              tables[table].name,
                              key.wire,
                              row.version,
                            ),
                          )
                        _ => ()
                      }
                    }
                    None => ()
                  }
                }
              }
            }
          }
        }
        _ => ()
      }
    }
    let action : RelationV3Action = match kind {
      "savepoint" => Mark(identifier(event.at("instance"), "instance"))
      "rollback_to" => Undo(identifier(event.at("instance"), "instance"))
      "release" => Release(identifier(event.at("instance"), "instance"))
      _ => actions.at(seq)
    }
    program.actions.push(action)
  }
  let initial = Array::make(keys.length(), -1)
  for pair in initial_pairs {
    initial[pair.0] = pair.1
  }
  let source_evidence = sources.map(source => {
    let key = keys[source.row.key]
    (
      {
        "relation": tables[key.table].name.to_json(),
        "key": key.wire,
        "version": source.row.version.to_json(),
        "values": relation_v3_values_json(source, tables, keys),
        "action": source.action.to_json(),
        "predecessor": relation_v3_optional_text(source.predecessor),
        "sourceSeq": source.seq.to_double().to_json(),
        "writer": relation_v3_optional_text(source.writer),
        "revertedBy": match revoked.get(source.seq) {
          Some(Some(at)) => at.to_double().to_json()
          _ => Json::null()
        },
      } : Json)
  })
  let status = if gaps.is_empty() { "ready" } else { "inconclusive" }
  let normalized : Json = {
    "schema": 3,
    "dataModel": "relation-set-v1",
    "algorithm": "v3-relation-lifecycle-1",
    "status": status.to_json(),
    "relationSchema": root.at("relationSchema"),
    "coverage": {
      "complete": gaps.is_empty().to_json(),
      "gaps": gaps.to_json(),
    },
    "observations": observations,
    "effects": effects.to_json(),
    "transactions": transactions.to_json(),
    "history": Json::null(),
  }
  {
    normalized,
    tables,
    keys,
    initial,
    sources,
    programs,
    findings,
    source_evidence,
    operations,
  }
}

///|
pub fn normalize_relation_capture_v3_json(text : String) -> String {
  relation_v3_parse(text).normalized.stringify(indent=2) catch {
    error => relation_v3_invalid(text, error.to_string()).stringify(indent=2)
  }
}

///|
fn relation_v3_budget(ctx : RelationV3Search) -> Bool {
  if ctx.operations >= ctx.options.max_operations {
    ctx.limited = true
    ctx.reason = "operation_budget"
    false
  } else {
    ctx.operations += 1
    true
  }
}

///|
fn relation_v3_undo(ctx : RelationV3Search, mark : Int) -> Unit {
  while ctx.trail.length() > mark {
    let (key, old) = ctx.trail.pop().unwrap()
    ctx.state[key] = old
  }
}

///|
fn relation_v3_blocker(
  ctx : RelationV3Search,
  tx : String,
  seq : Int64,
  code : String,
) -> Bool {
  if ctx.blockers.length() < 16 {
    ctx.blockers.push({
      "tx": tx.to_json(),
      "seq": seq.to_double().to_json(),
      "code": code.to_json(),
    })
  }
  false
}

///|
fn relation_v3_execute(
  ctx : RelationV3Search,
  program : RelationV3Program,
) -> Bool {
  let scopes : Array[(String, Int)] = []
  for action in program.actions {
    if !relation_v3_budget(ctx) {
      return false
    }
    match action {
      WriteRow(index) => {
        let source = ctx.parsed.sources[index]
        let key = source.row.key
        let old = ctx.state[key]
        let present = old >= 0 && ctx.parsed.sources[old].action != "delete"
        let predecessor = if old < 0 {
          None
        } else {
          Some(ctx.parsed.sources[old].row.version)
        }
        if (source.action == "insert" && present) ||
          (source.action != "insert" && !present) ||
          predecessor != source.predecessor {
          return relation_v3_blocker(
            ctx,
            program.id,
            source.seq,
            "row_write_state_mismatch",
          )
        }
        ctx.trail.push((key, old))
        ctx.state[key] = index
      }
      QueryRows(table, predicate, rows, seq) => {
        let actual : Array[Int] = []
        for key in ctx.sorted_keys[table] {
          let index = ctx.state[key]
          if index < 0 || ctx.parsed.sources[index].action == "delete" {
            continue
          }
          let row = ctx.parsed.sources[index].row
          let mut matches = true
          for term in predicate {
            if !relation_v3_budget(ctx) {
              return false
            }
            if !relation_v3_predicate_matches(term, row, ctx.parsed.keys) {
              matches = false
              break
            }
          }
          if matches {
            actual.push(index)
          }
        }
        if !relation_v3_budget(ctx) {
          return false
        }
        if actual.length() != rows.length() {
          return relation_v3_blocker(
            ctx,
            program.id,
            seq,
            "query_result_length_mismatch",
          )
        }
        let expected = rows.copy()
        expected.sort_by((a, b) => {
          relation_v3_compare(
            ctx.parsed.keys[a.key].value,
            ctx.parsed.keys[b.key].value,
          )
        })
        for i, observed in expected {
          let current = ctx.parsed.sources[actual[i]].row
          if !relation_v3_budget(ctx) {
            return false
          }
          if current.key != observed.key {
            return relation_v3_blocker(
              ctx,
              program.id,
              seq,
              "query_key_mismatch",
            )
          }
          if !relation_v3_budget(ctx) {
            return false
          }
          if current.version != observed.version {
            return relation_v3_blocker(
              ctx,
              program.id,
              seq,
              "query_version_mismatch",
            )
          }
          for j, value in observed.values {
            if !relation_v3_budget(ctx) {
              return false
            }
            if current.values[j] != value {
              return relation_v3_blocker(
                ctx,
                program.id,
                seq,
                "query_value_mismatch",
              )
            }
          }
        }
      }
      Mark(instance) => scopes.push((instance, ctx.trail.length()))
      Undo(instance) | Release(instance) => {
        let mut found = -1
        for i, scope in scopes {
          if scope.0 == instance {
            found = i
          }
        }
        if found < 0 {
          ctx.limited = true
          ctx.reason = "invalid_scope_program"
          return false
        }
        match action {
          Undo(_) => relation_v3_undo(ctx, scopes[found].1)
          _ => ()
        }
        let retained = match action {
          Undo(_) => found + 1
          _ => found
        }
        while scopes.length() > retained {
          let _ = scopes.pop()
        }
      }
    }
  }
  true
}

///|
fn relation_v3_search(ctx : RelationV3Search, selected : Int) -> Array[String]? {
  if ctx.prefix.length() == ctx.programs.length() {
    return Some(ctx.prefix.copy())
  }
  for i, program in ctx.programs {
    let bit = 1 << i
    if (selected & bit) != 0 {
      continue
    }
    if ctx.states >= ctx.options.max_states {
      ctx.limited = true
      ctx.reason = "state_budget"
      return None
    }
    ctx.states += 1
    let mark = ctx.trail.length()
    if relation_v3_execute(ctx, program) {
      ctx.prefix.push(program.id)
      let result = relation_v3_search(ctx, selected | bit)
      let _ = ctx.prefix.pop()
      relation_v3_undo(ctx, mark)
      if result is Some(_) {
        return result
      }
    } else {
      relation_v3_undo(ctx, mark)
    }
    if ctx.limited {
      return None
    }
  }
  None
}

///|
fn relation_v3_report(
  normalized : Json,
  status : String,
  evidence : Json,
  options : ListV3Options,
  states : Int,
  operations : Int,
  complete : Bool,
  reason : String,
) -> Json {
  {
    "schemaVersion": 3,
    "tool": "MoonTxnWitness",
    "version": version().to_json(),
    "algorithm": "v3-relation-1",
    "status": status.to_json(),
    "modelDefinition": {
      "id": "relation-set-serializable-v1",
      "scope": "complete relation snapshots and committed full row-query/write/savepoint journals; no SQL mapping, opacity, isolation-level classification or real-time claim",
    },
    "coverage": object_fields_unchecked_v3(normalized).at("coverage"),
    "normalized": normalized,
    "evidence": evidence,
    "execution": {
      "lifecycleAdapter": "register-v3-lifecycle-metadata-1",
      "analysisOptions": {
        "maxStates": options.max_states.to_json(),
        "maxOperationChecks": options.max_operations.to_json(),
      },
      "effectiveLimits": {
        "committedTransactions": 6,
        "operations": 128,
        "states": options.max_states.to_json(),
        "operationChecks": options.max_operations.to_json(),
        "budgetScope": "serial-search-only",
        "relations": 8,
        "columns": 16,
        "inputUtf16Units": 8388608,
        "transactions": 512,
        "events": 65536,
        "semanticOperations": 10000,
        "distinctKeys": 1024,
        "returnedRowReferences": 100000,
      },
      "metrics": {
        "states": states.to_json(),
        "operationChecks": operations.to_json(),
        "complete": complete.to_json(),
        "reason": reason.to_json(),
      },
    },
  }
}

///|
fn relation_v3_analysis(text : String, options_text : String) -> Json raise {
  let options = list_v3_options(options_text)
  let parsed = relation_v3_parse(text) catch {
    error =>
      return relation_v3_report(
        relation_v3_invalid(text, error.to_string()),
        "invalid",
        Json::null(),
        options,
        0,
        0,
        false,
        "invalid_capture",
      )
  }
  let committed = parsed.programs.filter(program => program.status == Committed)
  let status = object_fields_unchecked_v3(parsed.normalized).at("status")
  if committed.length() > 6 || parsed.operations > 128 {
    return relation_v3_report(
      parsed.normalized,
      "inconclusive",
      Json::null(),
      options,
      0,
      0,
      false,
      "exact_capacity",
    )
  }
  if status != "ready".to_json() {
    return relation_v3_report(
      parsed.normalized,
      identifier(status, "status"),
      Json::null(),
      options,
      0,
      0,
      false,
      "coverage_gap",
    )
  }
  if !parsed.findings.is_empty() {
    return relation_v3_report(
      parsed.normalized,
      "violation",
      {
        "kind": "source-proven-relation-anomaly",
        "findings": parsed.findings.to_json(),
        "sourceEvidence": parsed.source_evidence.to_json(),
      },
      options,
      0,
      0,
      true,
      "source_proven_anomaly",
    )
  }
  let sorted_keys : Array[Array[Int]] = parsed.tables.map(_ => [])
  for i, key in parsed.keys {
    sorted_keys[key.table].push(i)
  }
  for list in sorted_keys {
    list.sort_by((a, b) => {
      relation_v3_compare(parsed.keys[a].value, parsed.keys[b].value)
    })
  }
  let ctx : RelationV3Search = {
    parsed,
    programs: committed,
    state: parsed.initial.copy(),
    sorted_keys,
    trail: [],
    prefix: [],
    blockers: [],
    options,
    states: 0,
    operations: 0,
    limited: false,
    reason: "exhausted",
  }
  let result = relation_v3_search(ctx, 0)
  match result {
    Some(order) =>
      relation_v3_report(
        parsed.normalized,
        "consistent",
        {
          "kind": "serial-relation-replay",
          "serialOrder": order.to_json(),
          "sourceEvidence": parsed.source_evidence.to_json(),
        },
        options,
        ctx.states,
        ctx.operations,
        true,
        "found",
      )
    None if ctx.limited =>
      relation_v3_report(
        parsed.normalized,
        "inconclusive",
        {
          "kind": "search-incomplete",
          "sampleBlockers": ctx.blockers.to_json(),
          "sourceEvidence": parsed.source_evidence.to_json(),
        },
        options,
        ctx.states,
        ctx.operations,
        false,
        ctx.reason,
      )
    None =>
      relation_v3_report(
        parsed.normalized,
        "violation",
        {
          "kind": "bounded-serial-exhaustion",
          "code": "no_serial_relation_execution",
          "sampleBlockers": ctx.blockers.to_json(),
          "sourceEvidence": parsed.source_evidence.to_json(),
        },
        options,
        ctx.states,
        ctx.operations,
        true,
        "exhausted",
      )
  }
}
