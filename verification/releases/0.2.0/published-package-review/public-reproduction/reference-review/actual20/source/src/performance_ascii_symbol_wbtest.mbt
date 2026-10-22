// Test-only historical experiment, preserved verbatim for boundary coverage.
// The production scanner uses the exact released v0.1.7 implementation.
// This helper has no production call site and is outside release compilation.

///|
fn history_ascii_symbol(text : String, start : Int, end : Int) -> String {
  // Called only after the unchanged scanner saw a closing quote in its
  // plain-ASCII branch. Literal reuse avoids copying every repeated schema
  // field/status/kind. Exact unit comparison prevents prefix/length aliases.
  if start < 0 || start >= end || end > text.length() {
    return ""
  }
  let first = text.unsafe_get(start).to_int()
  let token = match end - start {
    2 if first == 105 => "id"
    3 =>
      match first {
        111 => "ops"
        101 => "end"
        107 => "key"
        _ => ""
      }
    4 =>
      match first {
        110 => "name"
        116 => "type"
        114 => "read"
        _ => ""
      }
    5 =>
      match first {
        109 => "model"
        115 => "start"
        119 => "write"
        _ => ""
      }
    6 if first == 115 => "status"
    7 =>
      match first {
        105 => "initial"
        118 => "version"
        97 => "aborted"
        117 => "unknown"
        _ => ""
      }
    9 if first == 99 => "committed"
    12 =>
      match first {
        116 => "transactions"
        115 => "serializable"
        _ => ""
      }
    13 =>
      match first {
        115 => "schemaVersion"
        118 => "versionOrders"
        _ => ""
      }
    19 if first == 115 => "strict-serializable"
    _ => ""
  }
  if token.length() != end - start {
    return ""
  }
  for i in 0..<token.length() {
    if text.unsafe_get(start + i) != token.unsafe_get(i) {
      return ""
    }
  }
  token
}

///|
fn ascii_symbol_parser_agreement(text : String, valid : Bool) -> Unit raise {
  let reference = parse_history(text)
  let direct = direct_history(text)
  let public_result = parse_history_optimized(text)
  match (reference, direct, public_result) {
    (Ok(a), Ok(b), Ok(c)) => {
      assert_true(valid)
      assert_true(a == b && a == c)
    }
    (Err(a), _, Err(b)) => {
      assert_true(!valid)
      assert_eq(a, b)
    }
    _ => assert_true(false)
  }
}

///|
test "ASCII fixed symbol coverage and lookalike fallback are explicit" {
  for
    token in [
      "schemaVersion", "name", "model", "initial", "versionOrders", "transactions",
      "id", "status", "ops", "start", "end", "type", "key", "version", "read", "write",
      "committed", "aborted", "unknown", "serializable", "strict-serializable",
    ] {
    let container = "prefix" + token + "suffix"
    assert_eq(history_ascii_symbol(container, 6, 6 + token.length()), token)
  }
  for
    unknown in [
      "", "typE", "statuz", "read ", " serializable", "交易", "😀",
    ] {
    assert_eq(history_ascii_symbol(unknown, 0, unknown.length()), "")
  }
  assert_eq(history_ascii_symbol("read", -1, 4), "")
  assert_eq(history_ascii_symbol("read", 0, 5), "")
}

///|
test "ASCII symbol reuse preserves full schema and every transaction status" {
  ascii_symbol_parser_agreement(
    "{\"schemaVersion\":1,\"name\":\"ordinary\",\"model\":\"strict-serializable\",\"initial\":{\"x\":\"x0\"},\"versionOrders\":{\"x\":[\"x0\",\"x1\"]},\"transactions\":[{\"id\":\"T\",\"status\":\"committed\",\"start\":0,\"end\":1,\"ops\":[{\"type\":\"write\",\"key\":\"x\",\"version\":\"x1\"},{\"type\":\"read\",\"key\":\"x\",\"version\":\"x1\"}]},{\"id\":\"A\",\"status\":\"aborted\",\"ops\":[]},{\"id\":\"U\",\"status\":\"unknown\",\"ops\":[]}]}",
    true,
  )
}

///|
test "ASCII schema spellings used as actual IDs retain their roles" {
  ascii_symbol_parser_agreement(
    "{\"model\":\"serializable\",\"initial\":{\"type\":\"initial\",\"status\":\"version\"},\"transactions\":[{\"id\":\"committed\",\"status\":\"committed\",\"ops\":[{\"type\":\"write\",\"key\":\"type\",\"version\":\"read\"},{\"type\":\"read\",\"key\":\"type\",\"version\":\"read\"},{\"type\":\"read\",\"key\":\"status\",\"version\":\"version\"}]}]}",
    true,
  )
}

///|
test "ASCII token aliases expressed with escapes use official scalar decoding" {
  ascii_symbol_parser_agreement(
    "{\"m\\u006fdel\":\"serial\\u0069zable\",\"initial\":{\"x\":\"x0\"},\"transactions\":[{\"\\u0069d\":\"T\",\"status\":\"comm\\u0069tted\",\"ops\":[{\"ty\\u0070e\":\"r\\u0065ad\",\"key\":\"x\",\"version\":\"x0\"}]}]}",
    true,
  )
}

///|
test "ASCII escaped and literal duplicate fields keep reference errors" {
  ascii_symbol_parser_agreement(
    "{\"initial\":{},\"transactions\":[{\"id\":\"T\",\"\\u0069d\":\"other\",\"status\":\"committed\",\"ops\":[]}]}",
    false,
  )
}

///|
test "ASCII near matches never turn unknown field or value into a token" {
  for
    text in [
      "{\"initial\":{},\"transactions\":[],\"transactioNs\":[]}", "{\"initial\":{},\"transactions\":[{\"id\":\"T\",\"statuz\":\"committed\",\"ops\":[]}]}",
      "{\"initial\":{},\"transactions\":[{\"id\":\"T\",\"status\":\"committeD\",\"ops\":[]}]}",
      "{\"initial\":{\"x\":\"x0\"},\"transactions\":[{\"id\":\"T\",\"status\":\"committed\",\"ops\":[{\"type\":\"reed\",\"key\":\"x\",\"version\":\"x0\"}]}]}",
    ] {
    ascii_symbol_parser_agreement(text, false)
  }
}

///|
test "ASCII symbol fallback keeps empty ordinary strings and exact spaces" {
  ascii_symbol_parser_agreement(
    "{\"name\":\"\",\"model\":\"serializable\",\"initial\":{\" key \":\" version \"},\"transactions\":[{\"id\":\" T \",\"status\":\"committed\",\"ops\":[{\"type\":\"read\",\"key\":\" key \",\"version\":\" version \"}]}]}",
    true,
  )
}

///|
test "ASCII symbol optimization leaves supplementary quoted source IDs intact" {
  ascii_symbol_parser_agreement(
    "{\"initial\":{\"a\\\"b\":\"😀𝄞\"},\"transactions\":[{\"id\":\"中😀\",\"status\":\"committed\",\"ops\":[{\"type\":\"read\",\"key\":\"a\\\"b\",\"version\":\"\\ud83d\\ude00𝄞\"}]}]}",
    true,
  )
}

///|
test "ASCII symbol fallback keeps control and unpaired surrogate rejection" {
  for
    text in [
      "{\"initial\":{\"x\":\"x0\"},\"transactions\":[{\"id\":\"T\\u007f\",\"status\":\"committed\",\"ops\":[]}]}",
      "{\"initial\":{\"x\":\"\\ud800\"},\"transactions\":[]}", "{\"initial\":{},\"transactions\":[{\"id\":\"T\",\"status\":\" committed\",\"ops\":[]}]}",
    ] {
    ascii_symbol_parser_agreement(text, false)
  }
}
