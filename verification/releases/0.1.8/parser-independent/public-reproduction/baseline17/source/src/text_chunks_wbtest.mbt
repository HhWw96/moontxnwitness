///|
test "fragment blocks retain exact boundaries and permit append after inspection" {
  for count in [0, 1, 1023, 1024, 1025, 2048, 2049, 4097] {
    let text = json_text()
    let expected = StringBuilder()
    for i in 0..<count {
      let fragment = if i % 3 == 0 {
        "键🙂\\\""
      } else if i % 3 == 1 {
        ""
      } else {
        i.to_string()
      }
      text.write_string(fragment)
      expected.write_string(fragment)
    }
    let before = expected.to_string()
    assert_eq(text.to_string(), before)
    assert_eq(text.to_string(), before)
    text.write_string("append🙂")
    assert_eq(text.to_string(), before + "append🙂")
  }
}

///|
test "chunked JSON preserves escaping and every element across repeated flushes" {
  let text = json_text()
  let values : Array[Json] = []
  text.write_char('[')
  for i in 0..<5000 {
    if i > 0 {
      text.write_char(',')
    }
    let value = "line\n\t\"\\🙂\{i}"
    values.push(value.to_json())
    text.write_string(value.to_json().stringify())
  }
  text.write_char(']')
  assert_eq(@json.parse(text.to_string()), Json::array(values))
}
