///|
fn draft_rt_text(edge : Edge) -> String {
  let text = json_text()
  write_edge(text, edge, Map([]))
  text.to_string()
}

///|
test "draft RT shell retains all complete wire fields in the same order" {
  let edge : Edge = {
    from: "A",
    to: "B",
    kind: RT,
    key: None,
    from_op: None,
    to_op: None,
    from_version: None,
    to_version: None,
    reason: "The source completed before the target began on the asserted common observer clock.",
  }
  assert_eq(
    draft_rt_text(edge),
    "{\"from\":\"A\",\"to\":\"B\",\"kind\":\"rt\",\"key\":null,\"fromOp\":null,\"toOp\":null,\"fromVersion\":null,\"toVersion\":null,\"reason\":\"The source completed before the target began on the asserted common observer clock.\"}",
  )
}

///|
test "draft RT shell still uses official escaping for transaction identities" {
  let edge : Edge = {
    from: "a\"\\月",
    to: "b\n🙂",
    kind: RT,
    key: None,
    from_op: None,
    to_op: None,
    from_version: None,
    to_version: None,
    reason: "The source completed before the target began on the asserted common observer clock.",
  }
  assert_eq(@json.parse(draft_rt_text(edge)), edge_json(edge))
}

///|
test "draft RT shell falls back for nonstandard provenance fields" {
  let edge : Edge = {
    from: "A",
    to: "B",
    kind: RT,
    key: Some("x"),
    from_op: Some(0),
    to_op: Some(2),
    from_version: Some("v\""),
    to_version: Some("v2"),
    reason: "The source completed before the target began on the asserted common observer clock.",
  }
  assert_eq(@json.parse(draft_rt_text(edge)), edge_json(edge))
}

///|
test "draft RT shell preserves a custom reason rather than substituting it" {
  let edge : Edge = {
    from: "A",
    to: "B",
    kind: RT,
    key: None,
    from_op: None,
    to_op: None,
    from_version: None,
    to_version: None,
    reason: "custom\n月",
  }
  assert_eq(@json.parse(draft_rt_text(edge)), edge_json(edge))
}
