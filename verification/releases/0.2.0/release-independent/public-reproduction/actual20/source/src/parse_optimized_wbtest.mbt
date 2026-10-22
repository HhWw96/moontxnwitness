///|
test "typed parser preserves Unicode escapes and exact safe-integer intervals" {
  let h = hist([
    tx(
      "quote\"\\😀",
      [write_op("x", "x1")],
      start=Some(9007199254740990L),
      end=Some(9007199254740991L),
    ),
  ])
  let text = history_json(h).stringify()
  match parse_history_optimized(text) {
    Ok(parsed) => assert_true(parsed == h)
    Err(_) => abort("Valid Unicode history")
  }
  assert_true(benchmark_parser_agreement(text).contains("true"))
}

///|
test "typed parser fallback retains legacy duplicate and syntax errors" {
  for
    text in [
      "{\"initial\":{},\"transactions\":[],\"initial\":{}}", "{\"initial\":{},\"transactions\":[,]}",
      "{\"initial\":{\"x\":\"v0\",\"\\u0078\":\"v1\"},\"transactions\":[]}",
    ] {
    match (parse_history_optimized(text), parse_history(text)) {
      (Err(a), Err(b)) => assert_eq(a, b)
      _ => abort("Malformed input must remain invalid")
    }
  }
}
