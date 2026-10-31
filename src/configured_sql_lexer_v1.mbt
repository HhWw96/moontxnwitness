///|
priv struct SQLTokenV1 {
  kind : String
  value : String
}

///|
priv struct SQLParseWorkV1 {
  config : SQLConfigV1
  options : SQLVerificationOptionsV1
  tokens : Array[SQLTokenV1]
  refs : Array[Json]
  mut pos : Int32
  mut checks : Int32
  mut table : SQLTableV1?
  mut table_alias : String?
  mut resolution : String
  mut style : String
  mut stray_percent : Bool
}

///|
fn sql_charge_v1(work : SQLParseWorkV1) -> Unit raise {
  if work.checks >= work.options.max_checks {
    fail("budget:checks")
  }
  work.checks += 1
}

///|
fn sql_ascii_start_v1(c : Char) -> Bool {
  (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_'
}

///|
fn sql_ascii_tail_v1(c : Char) -> Bool {
  sql_ascii_start_v1(c) || (c >= '0' && c <= '9') || c == '$'
}

///|
fn sql_lex_v1(work : SQLParseWorkV1, source : String) -> Unit raise {
  let chars = source.to_array()
  let mut pos = 0
  let mut depth = 0
  while pos < chars.length() {
    sql_charge_v1(work)
    let c = chars[pos]
    if c == ' ' ||
      c == '\n' ||
      c == '\r' ||
      c == '\t' ||
      c == '\u000c' ||
      c == '\u000b' {
      pos += 1
      continue
    }
    if c == '\u0000' {
      fail("grammar:NUL")
    }
    if c == '-' && pos + 1 < chars.length() && chars[pos + 1] == '-' {
      pos += 2
      while pos < chars.length() && chars[pos] != '\n' {
        sql_charge_v1(work)
        if chars[pos] == '%' {
          work.stray_percent = true
        }
        pos += 1
      }
      continue
    }
    if c == '/' && pos + 1 < chars.length() && chars[pos + 1] == '*' {
      pos += 2
      let mut comments = 1
      while pos < chars.length() && comments > 0 {
        sql_charge_v1(work)
        if chars[pos] == '%' {
          work.stray_percent = true
        }
        if pos + 1 < chars.length() &&
          chars[pos] == '/' &&
          chars[pos + 1] == '*' {
          comments += 1
          pos += 2
        } else if pos + 1 < chars.length() &&
          chars[pos] == '*' &&
          chars[pos + 1] == '/' {
          comments -= 1
          pos += 2
        } else {
          pos += 1
        }
        if comments > work.config.limits.at("max_nesting") {
          fail("budget:comments")
        }
      }
      if comments != 0 {
        fail("grammar:unclosed-comment")
      }
      continue
    }
    let token = if c == '"' || c == '\'' {
      let quote = c
      pos += 1
      let builder = StringBuilder()
      let mut closed = false
      while pos < chars.length() {
        sql_charge_v1(work)
        let next = chars[pos]
        pos += 1
        if next == quote {
          if pos < chars.length() && chars[pos] == quote {
            builder.write_char(quote)
            pos += 1
          } else {
            closed = true
            break
          }
        } else {
          if next == '\u0000' || (quote == '\'' && next == '\\') {
            fail("unsupported:string-escape-or-NUL")
          }
          if next == '%' {
            work.stray_percent = true
          }
          builder.write_char(next)
        }
      }
      if !closed {
        fail("grammar:unclosed-quote")
      }
      {
        kind: if quote == '"' {
          "id"
        } else {
          "str"
        },
        value: builder.to_string(),
      }
    } else if c == '%' {
      pos += 1
      if pos < chars.length() && chars[pos] == 's' {
        pos += 1
        if pos < chars.length() && sql_ascii_tail_v1(chars[pos]) {
          fail("unsupported:bind-format")
        }
        { kind: "bind", value: "", }
      } else if pos < chars.length() && chars[pos] == '(' {
        pos += 1
        let builder = StringBuilder()
        if pos >= chars.length() || !sql_ascii_start_v1(chars[pos]) {
          fail("unsupported:named-bind")
        }
        while pos < chars.length() &&
              (
                sql_ascii_start_v1(chars[pos]) ||
                (chars[pos] >= '0' && chars[pos] <= '9')
              ) {
          sql_charge_v1(work)
          builder.write_char(chars[pos])
          pos += 1
        }
        let name = builder.to_string()
        if name.length() > 128 ||
          pos + 1 >= chars.length() ||
          chars[pos] != ')' ||
          chars[pos + 1] != 's' {
          fail("unsupported:named-bind")
        }
        pos += 2
        if pos < chars.length() && sql_ascii_tail_v1(chars[pos]) {
          fail("unsupported:bind-format")
        }
        { kind: "named", value: name, }
      } else {
        fail("unsupported:percent-format")
      }
    } else if sql_ascii_start_v1(c) {
      let builder = StringBuilder()
      while pos < chars.length() && sql_ascii_tail_v1(chars[pos]) {
        sql_charge_v1(work)
        builder.write_char(chars[pos])
        pos += 1
      }
      { kind: "word", value: builder.to_string().to_lower(), }
    } else if c >= '0' && c <= '9' {
      let builder = StringBuilder()
      while pos < chars.length() && chars[pos] >= '0' && chars[pos] <= '9' {
        sql_charge_v1(work)
        builder.write_char(chars[pos])
        pos += 1
      }
      { kind: "num", value: builder.to_string(), }
    } else {
      pos += 1
      let mut value = c.to_string()
      if (c == '<' || c == '>') && pos < chars.length() && chars[pos] == '=' {
        value += "="
        pos += 1
      }
      if !["=", "<", ">", "<=", ">=", ".", ",", "(", ")", "*", "-", ";"].contains(
          value,
        ) {
        fail("unsupported:token")
      }
      if value == "(" {
        depth += 1
        if depth > work.config.limits.at("max_nesting") {
          fail("budget:nesting")
        }
      }
      if value == ")" {
        depth -= 1
        if depth < 0 {
          fail("grammar:parenthesis")
        }
      }
      { kind: "symbol", value, }
    }
    if work.tokens.length() >= work.options.max_tokens ||
      work.tokens.length() >= work.config.limits.at("max_tokens") {
      fail("budget:tokens")
    }
    work.tokens.push(token)
  }
  if depth != 0 {
    fail("grammar:parenthesis")
  }
  work.tokens.push({ kind: "eof", value: "", })
}

///|
fn SQLParseWorkV1::peek(self : SQLParseWorkV1) -> SQLTokenV1 {
  self.tokens[self.pos]
}

///|
fn SQLParseWorkV1::take(self : SQLParseWorkV1) -> SQLTokenV1 raise {
  sql_charge_v1(self)
  let token = self.peek()
  if token.kind == "eof" {
    fail("grammar:unexpected-end")
  }
  self.pos += 1
  token
}

///|
fn SQLParseWorkV1::accept(self : SQLParseWorkV1, word : String) -> Bool raise {
  let token = self.peek()
  if (token.kind == "word" || token.kind == "symbol") && token.value == word {
    self.pos += 1
    sql_charge_v1(self)
    true
  } else {
    false
  }
}

///|
fn SQLParseWorkV1::expect(self : SQLParseWorkV1, word : String) -> Unit raise {
  if !self.accept(word) {
    fail("grammar:expected-" + word)
  }
}

///|
fn sql_reserved_v1(word : String) -> Bool {
  [
    "select", "from", "where", "and", "or", "null", "true", "false", "insert", "into",
    "update", "delete", "returning", "values", "set", "as", "order", "by", "asc",
    "desc", "collate", "join", "left", "right", "inner", "outer", "cross", "limit",
    "offset", "group", "having", "union", "with", "for", "on", "conflict", "default",
    "not", "is", "in", "between", "current_user", "session_user", "current_role",
    "user", "current_catalog", "current_schema", "current_date", "current_time",
    "current_timestamp", "localtime", "localtimestamp", "case", "when", "then", "else",
    "end", "exists", "any", "some", "all", "like", "ilike", "similar",
  ].contains(word)
}

///|
fn SQLParseWorkV1::identifier(self : SQLParseWorkV1) -> String raise {
  let token = self.take()
  if (token.kind != "id" && token.kind != "word") ||
    (token.kind == "word" && sql_reserved_v1(token.value)) {
    fail("grammar:identifier")
  }
  sql_identifier_v1(Json(token.value))
}
