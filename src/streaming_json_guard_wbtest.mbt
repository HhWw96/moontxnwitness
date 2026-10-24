///|
fn streaming_guard_result(text : String, limit : Int) -> Result[Json, String] {
  Ok(guarded_json(text, limit~)) catch {
    error => Err(error.to_string())
  }
}

///|
test "streaming guard preserves Unicode values and official parsed results" {
  for
    text in [
      "null", "true", "-12.5e2", "\"\"", "\"a\\\"b\\\\c\"", "{\"长🙂\":[null,true,1]}",
      "{\"\\u0061\":\"\\ud83d\\ude00\"}", "[\"🙂\",\"𐐷\",\"é\"]",
    ] {
    match streaming_guard_result(text, 1048576) {
      Ok(value) => assert_true(value == @json.parse(text))
      Err(message) => abort(message)
    }
  }
}

///|
test "streaming guard rejects escaped equivalent duplicate keys" {
  for
    text in [
      "{\"a\":0,\"\\u0061\":1}", "{\"a/\":0,\"a\\/\":1}", "{\"🙂\":0,\"\\ud83d\\ude42\":1}",
      "{\"\":0,\"\":1}", "{\"长\":0,\"\\u957f\":1}",
    ] {
    match streaming_guard_result(text, 1048576) {
      Err(message) => assert_true(message.contains("Duplicate JSON object key"))
      _ => abort("Escaped equivalent duplicate keys must fail")
    }
  }
}

///|
test "streaming guard retains malformed and truncated rejection" {
  for
    text in [
      "", "\"", "\"abc\\", "{\"a\":", "{\"a\":1", "[1,", "{\"a\" 1}", "[1 2]", "true false",
      "{\"a\":\"\\q\"}",
    ] {
    assert_true(streaming_guard_result(text, 1048576) is Err(_))
  }
}

///|
test "streaming guard keeps inclusive 64 level depth boundary" {
  for depth in [63, 64] {
    let text = "[".repeat(depth) + "0" + "]".repeat(depth)
    assert_true(streaming_guard_result(text, 1048576) is Ok(_))
  }
  let text = "[".repeat(65) + "0" + "]".repeat(65)
  assert_true(streaming_guard_result(text, 1048576) is Err(_))
}

///|
test "streaming guard still limits original UTF16 length" {
  let text = "\"🙂\""
  assert_eq(text.length(), 4)
  assert_true(streaming_guard_result(text, 4) is Ok(_))
  assert_true(streaming_guard_result(text, 3) is Err(_))
}

///|
test "streaming scanner positions count Unicode scalar items and EOF is stable" {
  let scan = StreamingJsonScan::new("\"🙂\" \t0")
  scan.skip_string()
  assert_eq(scan.pos, 3)
  assert_true(scan.current == Some(' '))
  scan.white()
  assert_eq(scan.pos, 5)
  assert_true(scan.current == Some('0'))
  scan.value()
  assert_eq(scan.pos, 6)
  assert_true(scan.current == None)
  scan.advance()
  assert_eq(scan.pos, 6)
}

///|
test "streaming scanner empty input has no materialized characters" {
  let scan = StreamingJsonScan::new("")
  assert_true(scan.current == None)
  assert_eq(scan.pos, 0)
  scan.advance()
  assert_true(scan.current == None)
  assert_eq(scan.pos, 0)
}

///|
test "raw index checksum still preserves original scalar slices and text" {
  let body = "{\"note\":\"🙂\",\"n\":1234567890123456789}"
  let digest = v3_dislock_sha256(body)
  let members = "\"note\":\"🙂\",\"n\":1234567890123456789"
  let hash_member = "\"indexSha256\":\"" + digest + "\""
  for
    text in [
      "{" + hash_member + "," + members + "}\n",
      "{" + members + "," + hash_member + "}\n",
      "{\"note\":\"🙂\"," + hash_member + ",\"n\":1234567890123456789}\n",
    ] {
    orm_profile_index_digest_v3(
      text,
      object_fields(guarded_json(text), "index"),
    )
  }
}
