///|
/// JS StringBuilder concatenation retains deep ropes until a host consumes them.
/// Collect complete JSON fragments and flatten once; no analysis runs in the FFI.
priv struct JsonText {
  chunks : Array[String]
}

///|
fn json_text() -> JsonText {
  { chunks: [], }
}

///|
fn JsonText::write_string(self : JsonText, value : String) -> Unit {
  self.chunks.push(value)
}

///|
fn JsonText::write_char(self : JsonText, value : Char) -> Unit {
  self.chunks.push(value.to_string())
}

///|
fn JsonText::to_string(self : JsonText) -> String {
  join_json_chunks(FixedArray::makei(self.chunks.length(), i => self.chunks[i]))
}

///|
#cfg(target="js")
extern "js" fn join_json_chunks(parts : FixedArray[String]) -> String =
  #| (parts) => parts.join("")

///|
#cfg(not(target="js"))
fn join_json_chunks(parts : FixedArray[String]) -> String {
  let b = StringBuilder()
  for part in parts {
    b.write_string(part)
  }
  b.to_string()
}
