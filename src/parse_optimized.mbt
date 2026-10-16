///|
/// Schema-directed parsing avoids a temporary JSON object tree on valid input.
/// Official scalar decoding and the legacy error path remain the reference.
priv struct HistoryScan {
  text : String
  strings : Map[String, String]
  mut pos : Int
  mut operations : Int
}

///|
fn HistoryScan::peek(self : HistoryScan) -> Int {
  if self.pos >= self.text.length() {
    -1
  } else {
    self.text.unsafe_get(self.pos).to_int()
  }
}

///|
fn HistoryScan::white(self : HistoryScan) -> Unit {
  while true {
    let c = self.peek()
    if c == 32 || c == 9 || c == 10 || c == 13 {
      self.pos += 1
    } else {
      break
    }
  }
}

///|
fn HistoryScan::expect(self : HistoryScan, code : Int) -> Unit raise {
  self.white()
  if self.peek() != code {
    fail("Unexpected history token")
  }
  self.pos += 1
}

///|
fn HistoryScan::slice(self : HistoryScan, start : Int) -> String raise {
  match self.text.get_view(start~, end=self.pos) {
    Some(view) => view.to_owned()
    None => fail("Invalid string boundary")
  }
}

///|
fn HistoryScan::string(self : HistoryScan) -> String raise {
  self.white()
  let start = self.pos
  if self.peek() != 34 {
    fail("Expected string")
  }
  self.pos += 1
  let mut plain_ascii = true
  while true {
    let c = self.peek()
    if c == -1 {
      break
    }
    self.pos += 1
    if c == 34 {
      if plain_ascii {
        return match self.text.get_view(start=start + 1, end=self.pos - 1) {
          Some(view) => view.to_owned()
          None => fail("Invalid ASCII boundary")
        }
      }
      let raw = self.slice(start)
      return match self.strings.get(raw) {
        Some(value) => value
        None => {
          let value = match @json.parse(raw) {
            String(s) => s
            _ => fail("Expected string")
          }
          self.strings[raw] = value
          value
        }
      }
    }
    if c < 32 {
      fail("Unescaped control character")
    }
    if c > 127 {
      plain_ascii = false
    }
    if c == 92 {
      plain_ascii = false
      if self.peek() == -1 {
        fail("Truncated escape")
      }
      self.pos += 1
    }
  }
  fail("Unclosed string")
}

///|
fn HistoryScan::identifier(self : HistoryScan) -> String raise {
  let value = self.string()
  if !valid_identifier(value) {
    fail("Invalid identifier")
  }
  value
}

///|
fn HistoryScan::field(self : HistoryScan, first : Bool) -> String? raise {
  self.white()
  if self.peek() == 125 {
    self.pos += 1
    return None
  }
  if !first {
    self.expect(44)
  }
  let key = self.string()
  self.expect(58)
  Some(key)
}

///|
fn HistoryScan::element(self : HistoryScan, first : Bool) -> Bool raise {
  self.white()
  if self.peek() == 93 {
    self.pos += 1
    return false
  }
  if !first {
    self.expect(44)
  }
  self.white()
  if self.peek() == 93 {
    fail("Trailing array comma")
  }
  true
}

///|
fn HistoryScan::number(self : HistoryScan) -> Double raise {
  self.white()
  let start = self.pos
  while self.peek() >= 0 &&
        self.peek() != 44 &&
        self.peek() != 125 &&
        self.peek() != 93 &&
        self.peek() != 32 &&
        self.peek() != 9 &&
        self.peek() != 10 &&
        self.peek() != 13 {
    self.pos += 1
  }
  if start == self.pos {
    fail("Missing number")
  }
  match @json.parse(self.slice(start)) {
    Number(n, ..) => n
    _ => fail("Expected number")
  }
}

///|
fn HistoryScan::timestamp(self : HistoryScan) -> Int64? raise {
  self.white()
  if self.peek() == 110 {
    for code in [110, 117, 108, 108] {
      if self.peek() != code {
        fail("Invalid null")
      }
      self.pos += 1
    }
    return None
  }
  let n = self.number()
  if n < 0.0 || n > 9007199254740991.0 || n.to_int64().to_double() != n {
    fail("Invalid timestamp")
  }
  Some(n.to_int64())
}

///|
fn mark_field(seen : Int, flag : Int) -> Int raise {
  if (seen & flag) != 0 {
    fail("Duplicate history field")
  }
  seen | flag
}

///|
fn HistoryScan::operation(self : HistoryScan) -> Operation raise {
  self.expect(123)
  let mut first = true
  let mut seen = 0
  let mut kind = Read
  let mut key = ""
  let mut version = ""
  while true {
    let name = match self.field(first) {
      Some(name) => name
      None => break
    }
    first = false
    match name {
      "type" => {
        seen = mark_field(seen, 1)
        kind = match self.string() {
          "read" => Read
          "write" => Write
          _ => fail("Invalid operation kind")
        }
      }
      "key" => {
        seen = mark_field(seen, 2)
        key = self.identifier()
      }
      "version" => {
        seen = mark_field(seen, 4)
        version = self.identifier()
      }
      _ => fail("Unknown operation field")
    }
  }
  if seen != 7 {
    fail("Missing operation field")
  }
  self.operations += 1
  if self.operations > 10000 {
    fail("Operation limit")
  }
  { kind, key, version, }
}

///|
fn HistoryScan::transaction(self : HistoryScan) -> Transaction raise {
  self.expect(123)
  let mut first = true
  let mut seen = 0
  let mut id = ""
  let mut status = Committed
  let ops : Array[Operation] = []
  let mut start : Int64? = None
  let mut end : Int64? = None
  while true {
    let name = match self.field(first) {
      Some(name) => name
      None => break
    }
    first = false
    match name {
      "id" => {
        seen = mark_field(seen, 1)
        id = self.identifier()
      }
      "status" => {
        seen = mark_field(seen, 2)
        status = match self.string() {
          "committed" => Committed
          "aborted" => Aborted
          "unknown" => Unknown
          _ => fail("Invalid status")
        }
      }
      "ops" => {
        seen = mark_field(seen, 4)
        self.expect(91)
        let mut first_op = true
        while self.element(first_op) {
          first_op = false
          ops.push(self.operation())
        }
      }
      "start" => {
        seen = mark_field(seen, 8)
        start = self.timestamp()
      }
      "end" => {
        seen = mark_field(seen, 16)
        end = self.timestamp()
      }
      _ => fail("Unknown transaction field")
    }
  }
  if (seen & 7) != 7 {
    fail("Missing transaction field")
  }
  { id, status, ops, start, end, }
}

///|
fn direct_history(text : String) -> Result[History, String] {
  if text.length() > 1048576 {
    return Err("History size limit")
  }
  try {
    let scan : HistoryScan = { text, strings: Map([]), pos: 0, operations: 0, }
    scan.expect(123)
    let mut first = true
    let mut seen = 0
    let mut model = Serializable
    let initial : Map[String, String] = Map([])
    let orders : Map[String, Array[String]] = Map([])
    let txs : Array[Transaction] = []
    while true {
      let name = match scan.field(first) {
        Some(name) => name
        None => break
      }
      first = false
      match name {
        "schemaVersion" => {
          seen = mark_field(seen, 1)
          if scan.number() != 1.0 {
            fail("Invalid schema")
          }
        }
        "name" => {
          seen = mark_field(seen, 2)
          let _ = scan.string()
        }
        "model" => {
          seen = mark_field(seen, 4)
          model = match scan.string() {
            "serializable" => Serializable
            "strict-serializable" => StrictSerializable
            _ => fail("Invalid model")
          }
        }
        "initial" => {
          seen = mark_field(seen, 8)
          scan.expect(123)
          let mut first_key = true
          while true {
            let key = match scan.field(first_key) {
              Some(key) => key
              None => break
            }
            first_key = false
            if !valid_identifier(key) || initial.contains(key) {
              fail("Invalid or duplicate initial key")
            }
            initial[key] = scan.identifier()
          }
        }
        "versionOrders" => {
          seen = mark_field(seen, 16)
          scan.expect(123)
          let mut first_key = true
          while true {
            let key = match scan.field(first_key) {
              Some(key) => key
              None => break
            }
            first_key = false
            if orders.contains(key) {
              fail("Duplicate version order")
            }
            scan.expect(91)
            let values : Array[String] = []
            let mut first_value = true
            while scan.element(first_value) {
              first_value = false
              values.push(scan.identifier())
            }
            orders[key] = values
          }
        }
        "transactions" => {
          seen = mark_field(seen, 32)
          scan.expect(91)
          let mut first_tx = true
          while scan.element(first_tx) {
            first_tx = false
            if txs.length() >= 512 {
              fail("Transaction limit")
            }
            txs.push(scan.transaction())
          }
        }
        _ => fail("Unknown history field")
      }
    }
    scan.white()
    if scan.pos != text.length() || (seen & 40) != 40 {
      fail("Missing or trailing history input")
    }
    Ok({ model, initial, version_orders: orders, transactions: txs, })
  } catch {
    e => Err(e.to_string())
  }
}

///|
/// Valid-input fast path; legacy decoding retains exact errors and uncommon cases.
pub fn parse_history_optimized(text : String) -> Result[History, String] {
  match direct_history(text) {
    Ok(h) => Ok(h)
    Err(_) => parse_history(text)
  }
}

///|
pub fn benchmark_parser_agreement(text : String) -> String {
  let fast = direct_history(text)
  let reference = parse_history(text)
  let agrees = match (fast, reference) {
    (Ok(a), Ok(b)) => a == b
    (Err(_), _) => true
    _ => false
  }
  let result : Json = {
    "agrees": agrees.to_json(),
    "fastPath": (fast is Ok(_)).to_json(),
    "referenceValid": (reference is Ok(_)).to_json(),
  }
  result.stringify()
}
