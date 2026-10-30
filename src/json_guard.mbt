///| A bounded structural scan rejects duplicate object keys before Json's map decoding.

///|
/// Keys are decoded with the official parser, including escaped equivalent spellings.
priv struct JsonScan {
  chars : Array[Char]
  decoded_keys : Map[String, String]
  mut pos : Int32
  mut depth : Int32
}

///|
fn json_white(c : Char) -> Bool {
  c == ' ' || c == '\n' || c == '\r' || c == '\t'
}

///|
fn JsonScan::skip_string(self : JsonScan) -> Unit raise {
  self.pos += 1
  while self.pos < self.chars.length() {
    let c = self.chars[self.pos]
    self.pos += 1
    if c == '"' {
      return
    }
    if c == '\\' {
      if self.pos >= self.chars.length() {
        fail("Truncated JSON escape")
      }
      self.pos += 1
    }
  }
  fail("Unterminated JSON string")
}

///|
fn JsonScan::white(self : JsonScan) -> Unit {
  while self.pos < self.chars.length() && json_white(self.chars[self.pos]) {
    self.pos += 1
  }
}

///|
fn JsonScan::string_token(self : JsonScan) -> String raise {
  if self.pos >= self.chars.length() || self.chars[self.pos] != '"' {
    fail("Expected JSON string")
  }
  let b = StringBuilder()
  b.write_char('"')
  self.pos += 1
  while self.pos < self.chars.length() {
    let c = self.chars[self.pos]
    self.pos += 1
    b.write_char(c)
    if c == '"' {
      return b.to_string()
    }
    if c == '\\' {
      if self.pos >= self.chars.length() {
        fail("Truncated JSON escape")
      }
      b.write_char(self.chars[self.pos])
      self.pos += 1
    }
  }
  fail("Unterminated JSON string")
}

///|
fn JsonScan::value(self : JsonScan) -> Unit raise {
  self.white()
  if self.pos >= self.chars.length() {
    fail("Truncated JSON value")
  }
  let c = self.chars[self.pos]
  if c == '{' || c == '[' {
    self.depth += 1
    if self.depth > 64 {
      fail("JSON nesting exceeds 64 levels")
    }
    self.pos += 1
    let close = if c == '{' { '}' } else { ']' }
    self.white()
    let seen : Map[String, Bool] = Map([])
    if self.pos < self.chars.length() && self.chars[self.pos] == close {
      self.pos += 1
      self.depth -= 1
      return
    }
    while self.pos < self.chars.length() {
      if c == '{' {
        self.white()
        let raw_key = self.string_token()
        let key = match self.decoded_keys.get(raw_key) {
          Some(key) => key
          None => {
            let key = match @json.parse(raw_key) {
              String(s) => s
              _ => fail("Invalid object key")
            }
            self.decoded_keys[raw_key] = key
            key
          }
        }
        if seen.contains(key) {
          fail("Duplicate JSON object key: " + key)
        }
        seen[key] = true
        self.white()
        if self.pos >= self.chars.length() || self.chars[self.pos] != ':' {
          fail("Missing JSON colon")
        }
        self.pos += 1
      }
      self.value()
      self.white()
      if self.pos >= self.chars.length() {
        fail("Unclosed JSON container")
      }
      if self.chars[self.pos] == close {
        self.pos += 1
        self.depth -= 1
        return
      }
      if self.chars[self.pos] != ',' {
        fail("Missing JSON comma")
      }
      self.pos += 1
    }
    fail("Unclosed JSON container")
  } else if c == '"' {
    self.skip_string()
  } else {
    let start = self.pos
    while self.pos < self.chars.length() &&
          self.chars[self.pos] != ',' &&
          self.chars[self.pos] != '}' &&
          self.chars[self.pos] != ']' &&
          !json_white(self.chars[self.pos]) {
      self.pos += 1
    }
    if self.pos == start {
      fail("Invalid JSON value")
    }
  }
}

///|
fn guarded_base(text : String, limit~ : Int32 = 1048576) -> Json raise {
  if text.length() > limit {
    fail("JSON input exceeds the size limit")
  }
  let scan : JsonScan = {
    chars: text.iter().collect(),
    decoded_keys: Map([]),
    pos: 0,
    depth: 0,
  }
  scan.value()
  scan.white()
  if scan.pos != scan.chars.length() {
    fail("Trailing JSON content")
  }
  @json.parse(text)
}

///|
fn valid_identifier(s : String) -> Bool {
  if s.length() == 0 || s.length() > 256 {
    return false
  }
  // The forbidden scalars are ASCII controls only. Every surrogate unit is
  // >=0xD800, so scanning UTF-16 units has exactly the same predicate as scalar
  // iteration, including supplementary characters and existing length limits.
  // Avoid an iterator/closure pair for every repeated validation of an ID.
  for i in 0..<s.length() {
    let c = s.unsafe_get(i).to_int()
    if c < 32 || c == 127 {
      return false
    }
  }
  true
}

///|
// The original JsonScan remains the exact scalar-indexed raw-index checksum
// scanner. Large guarded_json inputs only need forward traversal and use one
// Unicode Char iterator plus one current element instead of a full Char array.
priv struct StreamingJsonScan {
  chars : Iter[Char]
  decoded_keys : Map[String, String]
  mut current : Char?
  mut pos : Int32
  mut depth : Int32
}

///|
fn StreamingJsonScan::new(text : String) -> StreamingJsonScan {
  let chars = text.iter()
  { chars, decoded_keys: Map([]), current: chars.next(), pos: 0, depth: 0, }
}

///|
fn StreamingJsonScan::advance(self : StreamingJsonScan) -> Unit {
  if self.current != None {
    self.pos += 1
    self.current = self.chars.next()
  }
}

///|
fn StreamingJsonScan::skip_string(self : StreamingJsonScan) -> Unit raise {
  self.advance()
  while self.current != None {
    let c = self.current.unwrap()
    self.advance()
    if c == '"' {
      return
    }
    if c == '\\' {
      if self.current == None {
        fail("Truncated JSON escape")
      }
      self.advance()
    }
  }
  fail("Unterminated JSON string")
}

///|
fn StreamingJsonScan::white(self : StreamingJsonScan) -> Unit {
  while self.current != None && json_white(self.current.unwrap()) {
    self.advance()
  }
}

///|
fn StreamingJsonScan::string_token(self : StreamingJsonScan) -> String raise {
  if self.current == None || self.current.unwrap() != '"' {
    fail("Expected JSON string")
  }
  let b = StringBuilder()
  b.write_char('"')
  self.advance()
  while self.current != None {
    let c = self.current.unwrap()
    self.advance()
    b.write_char(c)
    if c == '"' {
      return b.to_string()
    }
    if c == '\\' {
      if self.current == None {
        fail("Truncated JSON escape")
      }
      b.write_char(self.current.unwrap())
      self.advance()
    }
  }
  fail("Unterminated JSON string")
}

///|
fn StreamingJsonScan::value(self : StreamingJsonScan) -> Unit raise {
  self.white()
  if self.current == None {
    fail("Truncated JSON value")
  }
  let c = self.current.unwrap()
  if c == '{' || c == '[' {
    self.depth += 1
    if self.depth > 64 {
      fail("JSON nesting exceeds 64 levels")
    }
    self.advance()
    let close = if c == '{' { '}' } else { ']' }
    self.white()
    let seen : Map[String, Bool] = Map([])
    if self.current != None && self.current.unwrap() == close {
      self.advance()
      self.depth -= 1
      return
    }
    while self.current != None {
      if c == '{' {
        self.white()
        let raw_key = self.string_token()
        let key = match self.decoded_keys.get(raw_key) {
          Some(key) => key
          None => {
            let key = match @json.parse(raw_key) {
              String(s) => s
              _ => fail("Invalid object key")
            }
            self.decoded_keys[raw_key] = key
            key
          }
        }
        if seen.contains(key) {
          fail("Duplicate JSON object key: " + key)
        }
        seen[key] = true
        self.white()
        if self.current == None || self.current.unwrap() != ':' {
          fail("Missing JSON colon")
        }
        self.advance()
      }
      self.value()
      self.white()
      if self.current == None {
        fail("Unclosed JSON container")
      }
      if self.current.unwrap() == close {
        self.advance()
        self.depth -= 1
        return
      }
      if self.current.unwrap() != ',' {
        fail("Missing JSON comma")
      }
      self.advance()
    }
    fail("Unclosed JSON container")
  } else if c == '"' {
    self.skip_string()
  } else {
    let start = self.pos
    while self.current != None &&
          self.current.unwrap() != ',' &&
          self.current.unwrap() != '}' &&
          self.current.unwrap() != ']' &&
          !json_white(self.current.unwrap()) {
      self.advance()
    }
    if self.pos == start {
      fail("Invalid JSON value")
    }
  }
}

///|

///|
// Valid large inputs avoid a materialized character array. Input errors use
// the original guard to preserve diagnostic priority and source coordinates.
fn guarded_json(text : String, limit~ : Int32 = 1048576) -> Json raise {
  if text.length() > limit {
    return guarded_base(text, limit~)
  }
  let scan = StreamingJsonScan::new(text)
  let parsed : Json? = try {
    scan.value()
    scan.white()
    if scan.current == None {
      Some(@json.parse(text))
    } else {
      None
    }
  } catch {
    _ => None
  }
  match parsed {
    Some(value) => value
    None => guarded_base(text, limit~)
  }
}
