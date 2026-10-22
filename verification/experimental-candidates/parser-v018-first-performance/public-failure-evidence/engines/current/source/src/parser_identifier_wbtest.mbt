///|
fn identifier_fixture(encoded_id : String) -> String {
  "{\"initial\":{\"x\":\"x0\"},\"transactions\":[{\"id\":" +
  encoded_id +
  ",\"status\":\"committed\",\"ops\":[{\"type\":\"read\",\"key\":\"x\",\"version\":\"x0\"}],\"start\":7,\"end\":9}]}"
}

///|
test "every ASCII code retains identifier acceptance and legacy rejection semantics" {
  for code in 0..<128 {
    let id = code.unsafe_to_char().to_string()
    let text = identifier_fixture(id.to_json().stringify())
    if code >= 32 && code < 127 {
      match (direct_history(text), parse_history(text)) {
        (Ok(fast), Ok(reference)) => assert_true(fast == reference)
        _ => abort("Printable ASCII identifiers must remain valid")
      }
    } else {
      assert_true(direct_history(text) is Err(_))
      match (parse_history_optimized(text), parse_history(text)) {
        (Err(fast), Err(reference)) => assert_eq(fast, reference)
        _ => abort("ASCII controls and DEL must remain invalid")
      }
    }
  }
}

///|
test "ASCII identifier scan accepts the existing inclusive length and printable boundaries" {
  for id in [" ", "~", "a".repeat(255), "z".repeat(256)] {
    let text = identifier_fixture(id.to_json().stringify())
    match (direct_history(text), parse_history(text)) {
      (Ok(fast), Ok(reference)) => {
        assert_true(fast == reference)
        assert_eq(fast.transactions[0].id, id)
        assert_true(fast.transactions[0].start == Some(7L))
        assert_true(fast.transactions[0].end == Some(9L))
      }
      _ => abort("Printable identifier must be accepted by both parsers")
    }
  }
}

///|
test "late Unicode and escape fallbacks retain decoded identifiers and following fields" {
  for
    encoded in [
      "\"a\\u0062\"",
      "\"quote\\\"slash\\\\\"",
      "\"长🙂\"",
      "\"" + "a".repeat(255) + "\\u0062\"",
      "\"" + "a".repeat(254) + "长\"",
    ] {
    let text = identifier_fixture(encoded)
    match (direct_history(text), parse_history(text)) {
      (Ok(fast), Ok(reference)) => {
        assert_true(fast == reference)
        assert_eq(fast.transactions[0].ops.length(), 1)
        assert_true(fast.transactions[0].end == Some(9L))
      }
      _ => abort("Valid decoded identifier must remain supported")
    }
  }
}

///|
test "identifier rejection preserves canonical legacy errors for controls lengths and malformed escapes" {
  let encoded_ids = [
    "\"\"",
    "\"" + "a".repeat(257) + "\"",
    "\"" + "a".repeat(256) + "\\u0062\"",
    "\"a\\u0000b\"",
    "\"a\\u007fb\"",
    "\"a\\q\"",
    "\"unterminated",
    "false",
  ]
  for code in [0, 31, 127] {
    encoded_ids.push("\"a" + code.unsafe_to_char().to_string() + "b\"")
  }
  for encoded in encoded_ids {
    let text = identifier_fixture(encoded)
    assert_true(direct_history(text) is Err(_))
    match (parse_history_optimized(text), parse_history(text)) {
      (Err(fast), Err(reference)) => assert_eq(fast, reference)
      _ => abort("Rejected identifiers must retain legacy error behavior")
    }
  }
}

///|
test "typed caller identifier validation remains independent from JSON scanning" {
  for
    id in ["", "a".repeat(257), "a" + (127).unsafe_to_char().to_string() + "b"] {
    let result = analyze(hist([tx(id, [])]))
    assert_true(result.outcome == Invalid)
    assert_true(has_code(result, "invalid_identifier"))
  }
}
