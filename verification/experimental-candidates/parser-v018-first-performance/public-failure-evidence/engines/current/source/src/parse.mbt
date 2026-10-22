///|
fn object_fields(j : Json, path : String) -> Map[String, Json] raise {
  match j {
    Object(m) => m
    _ => fail(path + " must be an object")
  }
}

///|
fn known_fields(
  m : Map[String, Json],
  allowed : Array[String],
  path : String,
) -> Unit raise {
  for k, _ in m {
    if !allowed.contains(k) {
      fail(path + ": unknown field " + k)
    }
  }
}

///|
fn required(m : Map[String, Json], k : String, path : String) -> Json raise {
  match m.get(k) {
    Some(v) => v
    None => fail(path + ": missing field " + k)
  }
}

///|
fn identifier(j : Json, path : String) -> String raise {
  match j {
    String(s) => {
      if !valid_identifier(s) {
        fail(path + " must have 1..256 UTF-16 code units")
      }
      s
    }
    _ => fail(path + " must be a string")
  }
}

///|
fn timestamp(m : Map[String, Json], k : String, path : String) -> Int64? raise {
  match m.get(k) {
    None | Some(Null) => None
    Some(Number(n, ..)) => {
      if n < 0.0 || n > 9007199254740991.0 || n.to_int64().to_double() != n {
        fail(path + "." + k + " must be a non-negative safe integer")
      }
      Some(n.to_int64())
    }
    _ => fail(path + "." + k + " must be an integer or null")
  }
}

///|
/// Parse the versioned-register input schema. Unknown fields are rejected.
pub fn parse_history(text : String) -> Result[History, String] {
  if text.length() > 1048576 {
    return Err("Input exceeds 1,048,576 UTF-16 code units")
  }
  try {
    let j = guarded_json(text)
    let root = object_fields(j, "history")
    known_fields(
      root,
      [
        "schemaVersion", "name", "model", "initial", "versionOrders", "transactions",
      ],
      "history",
    )
    match root.get("schemaVersion") {
      None => ()
      Some(Number(n, ..)) if n == 1.0 => ()
      _ => fail("schemaVersion must be 1")
    }
    match root.get("name") {
      None => ()
      Some(String(_)) => ()
      _ => fail("name must be a string")
    }
    let model = match root.get("model") {
      None | Some(String("serializable")) => Serializable
      Some(String("strict-serializable")) => StrictSerializable
      _ => fail("model must be serializable or strict-serializable")
    }
    let raw_initial = object_fields(
      required(root, "initial", "history"),
      "initial",
    )
    let initial : Map[String, String] = Map([])
    for k, v in raw_initial {
      let _ = identifier(k.to_json(), "initial key")
      initial[k] = identifier(v, "initial." + k)
    }
    let orders : Map[String, Array[String]] = Map([])
    match root.get("versionOrders") {
      None => ()
      Some(v) => {
        let raw_orders = object_fields(v, "versionOrders")
        for k, value in raw_orders {
          let items = match value {
            Array(a) => a
            _ => fail("versionOrders." + k + " must be an array")
          }
          let order : Array[String] = []
          for item in items {
            order.push(identifier(item, "versionOrders." + k))
          }
          orders[k] = order
        }
      }
    }
    let txs = match required(root, "transactions", "history") {
      Array(a) => a
      _ => fail("transactions must be an array")
    }
    if txs.length() > 512 {
      fail("At most 512 transactions are supported in v0.0.1")
    }
    let transactions : Array[Transaction] = []
    let mut total_ops = 0
    for i, raw_tx in txs {
      let path = "transactions[" + i.to_string() + "]"
      let tx = object_fields(raw_tx, path)
      known_fields(tx, ["id", "status", "ops", "start", "end"], path)
      let id = identifier(required(tx, "id", path), path + ".id")
      let status = match required(tx, "status", path) {
        String("committed") => Committed
        String("aborted") => Aborted
        String("unknown") => Unknown
        _ => fail(path + ".status must be committed, aborted or unknown")
      }
      let raw_ops = match required(tx, "ops", path) {
        Array(a) => a
        _ => fail(path + ".ops must be an array")
      }
      total_ops += raw_ops.length()
      if total_ops > 10000 {
        fail("At most 10,000 operations are supported")
      }
      let ops : Array[Operation] = []
      for oi, raw_op in raw_ops {
        let op_path = path + ".ops[" + oi.to_string() + "]"
        let op = object_fields(raw_op, op_path)
        known_fields(op, ["type", "key", "version"], op_path)
        let kind = match required(op, "type", op_path) {
          String("read") => Read
          String("write") => Write
          _ => fail(op_path + ".type must be read or write")
        }
        ops.push({
          kind,
          key: identifier(required(op, "key", op_path), op_path + ".key"),
          version: identifier(
            required(op, "version", op_path),
            op_path + ".version",
          ),
        })
      }
      transactions.push({
        id,
        status,
        ops,
        start: timestamp(tx, "start", path),
        end: timestamp(tx, "end", path),
      })
    }
    Ok({ model, initial, version_orders: orders, transactions, })
  } catch {
    e => Err(e.to_string())
  }
}

///|
/// Validate typed inputs too, so constructing History directly cannot bypass constraints.
fn validate_history(h : History) -> Array[Finding] {
  let errors : Array[Finding] = []
  if h.transactions.length() > 512 {
    errors.push(
      issue("resource_limit", "error", "At most 512 transactions are supported"),
    )
  }
  let ids : Map[String, Bool] = Map([])
  let writes : Map[String, Map[String, Bool]] = Map([])
  let mut op_count = 0
  for tx in h.transactions {
    if !valid_identifier(tx.id) {
      errors.push(
        issue("invalid_identifier", "error", "Invalid transaction identifier"),
      )
    }
    if ids.contains(tx.id) {
      errors.push(
        issue(
          "duplicate_transaction",
          "error",
          "Transaction identifiers must be unique",
          txs=[tx.id],
        ),
      )
    }
    ids[tx.id] = true
    op_count += tx.ops.length()
    match (tx.start, tx.end) {
      (Some(s), Some(e)) if s < 0L || e < s || e > 9007199254740991L =>
        errors.push(
          issue("invalid_interval", "error", "Invalid transaction interval", txs=[
            tx.id,
          ]),
        )
      (Some(s), None) if s < 0L || s > 9007199254740991L =>
        errors.push(
          issue("invalid_interval", "error", "Invalid start timestamp", txs=[
            tx.id,
          ]),
        )
      (None, Some(e)) if e < 0L || e > 9007199254740991L =>
        errors.push(
          issue("invalid_interval", "error", "Invalid end timestamp", txs=[
            tx.id,
          ]),
        )
      _ => ()
    }
    for oi, op in tx.ops {
      if !valid_identifier(op.key) || !valid_identifier(op.version) {
        errors.push(
          issue(
            "invalid_identifier",
            "error",
            "Invalid operation key or version",
            txs=[tx.id],
            ops=[oi],
          ),
        )
      }
      if !h.initial.contains(op.key) {
        errors.push(
          issue(
            "missing_initial",
            "error",
            "Every operated key requires an initial version",
            txs=[tx.id],
            key=Some(op.key),
            ops=[oi],
          ),
        )
      }
      if op.kind == Write {
        let versions = writes.get_or_default(op.key, Map([]))
        if versions.contains(op.version) {
          errors.push(
            issue(
              "duplicate_write_version",
              "error",
              "A version must identify exactly one write on its key",
              txs=[tx.id],
              key=Some(op.key),
              ops=[oi],
            ),
          )
        }
        if h.initial.get(op.key) == Some(op.version) {
          errors.push(
            issue(
              "initial_version_reused",
              "error",
              "An initial version cannot be written again",
              txs=[tx.id],
              key=Some(op.key),
              ops=[oi],
            ),
          )
        }
        versions[op.version] = true
        writes[op.key] = versions
      }
    }
  }
  if op_count > 10000 {
    errors.push(
      issue(
        "resource_limit", "error", "At most 10,000 operations are supported",
      ),
    )
  }
  for k, v in h.initial {
    if !valid_identifier(k) || !valid_identifier(v) {
      errors.push(
        issue(
          "invalid_identifier",
          "error",
          "Invalid initial key or version",
          key=Some(k),
        ),
      )
    }
  }
  errors
}
