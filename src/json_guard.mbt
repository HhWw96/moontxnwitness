///| A bounded structural scan rejects duplicate object keys before Json's map decoding.

///|
/// Keys are decoded with the official parser, including escaped equivalent spellings.
priv struct JsonScan {
  chars : Array[Char]
  mut pos : Int
  mut depth : Int
}

///|
fn JsonScan::white(self : JsonScan) -> Unit {
  while self.pos < self.chars.length() &&
        [' ', '\n', '\r', '\t'].contains(self.chars[self.pos]) {
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
        let key = match @json.parse(raw_key) {
          String(s) => s
          _ => fail("Invalid object key")
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
    let _ = self.string_token()
  } else {
    let start = self.pos
    while self.pos < self.chars.length() &&
          ![',', '}', ']', ' ', '\n', '\r', '\t'].contains(self.chars[self.pos]) {
      self.pos += 1
    }
    if self.pos == start {
      fail("Invalid JSON value")
    }
  }
}

///|
fn guarded_json(text : String, limit? : Int = 1048576) -> Json raise {
  if text.length() > limit {
    fail("JSON input exceeds the size limit")
  }
  let scan : JsonScan = { chars: text.iter().collect(), pos: 0, depth: 0, }
  scan.value()
  scan.white()
  if scan.pos != scan.chars.length() {
    fail("Trailing JSON content")
  }
  @json.parse(text)
}

///|
fn valid_identifier(s : String) -> Bool {
  s.length() > 0 &&
  s.length() <= 256 &&
  !s.iter().any(c => c.to_int() < 32 || c.to_int() == 127)
}
