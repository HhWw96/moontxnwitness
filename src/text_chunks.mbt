///|
/// A JS block keeps the fragment array bounded instead of copying all fragments
/// into a second large FixedArray at the end. FFI only joins text, never analyzes.
#cfg(target="js")
priv struct JsonText {
  blocks : Array[String]
  fragments : FixedArray[String]
  mut used : Int32
}

///|
#cfg(target="js")
fn json_text() -> JsonText {
  { blocks: [], fragments: FixedArray::make(1024, ""), used: 0, }
}

///|
#cfg(target="js")
fn JsonText::write_string(self : JsonText, value : String) -> Unit {
  if self.used == self.fragments.length() {
    self.blocks.push(join_json_chunks(self.fragments))
    self.used = 0
  }
  self.fragments[self.used] = value
  self.used += 1
}

///|
#cfg(target="js")
fn JsonText::write_char(self : JsonText, value : Char) -> Unit {
  self.write_string(value.to_string())
}

///|
#cfg(target="js")
fn JsonText::to_string(self : JsonText) -> String {
  let tail = join_json_chunks(
    FixedArray::makei(self.used, i => self.fragments[i]),
  )
  if self.blocks.is_empty() {
    return tail
  }
  join_json_chunks(
    FixedArray::makei(self.blocks.length() + 1, i => {
      if i == self.blocks.length() {
        tail
      } else {
        self.blocks[i]
      }
    }),
  )
}

///|
/// Preserve the existing encoding path on other targets.
#cfg(not(target="js"))
priv struct JsonText {
  chunks : Array[String]
}

///|
#cfg(not(target="js"))
fn json_text() -> JsonText {
  { chunks: [], }
}

///|
#cfg(not(target="js"))
fn JsonText::write_string(self : JsonText, value : String) -> Unit {
  self.chunks.push(value)
}

///|
#cfg(not(target="js"))
fn JsonText::write_char(self : JsonText, value : Char) -> Unit {
  self.chunks.push(value.to_string())
}

///|
#cfg(not(target="js"))
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
