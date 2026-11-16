///|
// Convert our own report records without serializing and reparsing the complete
// document. This host type does not expose MoonBit collection representations.
#cfg(target="js")
extern "js" fn native_model_null() -> NativeReportObject =
  #| () => null

///|
#cfg(target="js")
extern "js" fn native_model_object() -> NativeReportObject =
  #| () => ({})

///|
#cfg(target="js")
extern "js" fn native_model_array() -> NativeReportObject =
  #| () => []

///|
#cfg(target="js")
extern "js" fn native_model_string(value : String) -> NativeReportObject =
  #| value => value

///|
#cfg(target="js")
extern "js" fn native_model_bool(value : Bool) -> NativeReportObject =
  #| value => value

///|
// Parse only a numeric token, preserving the existing JSON number conversion
// including -0 and numbers whose source representation exceeds safe integers.
#cfg(target="js")
extern "js" fn native_model_number(text : String) -> NativeReportObject =
  #| text => JSON.parse(text)

///|
#cfg(target="js")
extern "js" fn native_model_set(
  object : NativeReportObject,
  key : String,
  value : NativeReportObject,
) -> Unit =
  #| (object, key, value) => { Object.defineProperty(object, key, {value, enumerable:true, writable:true, configurable:true}); }

///|
#cfg(target="js")
extern "js" fn native_model_push(
  array : NativeReportObject,
  value : NativeReportObject,
) -> Unit =
  #| (array, value) => { array.push(value); }

///|
// Exact UTF-8 byte count of a quoted JSON string. Invalid surrogate sequences
// use the original text path, which retains its existing Unicode checks.
#cfg(target="js")
extern "js" fn native_model_string_bytes(value : String) -> Int32 =
  #| value => {
  #|   let bytes = 2;
  #|   for (let i = 0; i < value.length; i++) {
  #|     const c = value.charCodeAt(i);
  #|     if (c === 34 || c === 92 || c === 8 || c === 9 || c === 10 || c === 12 || c === 13) bytes += 2;
  #|     else if (c < 32) bytes += 6;
  #|     else if (c < 128) bytes++;
  #|     else if (c < 2048) bytes += 2;
  #|     else if (c >= 0xd800 && c <= 0xdbff) {
  #|       const low = value.charCodeAt(++i);
  #|       if (!(low >= 0xdc00 && low <= 0xdfff)) return -1;
  #|       bytes += 4;
  #|     } else if (c >= 0xdc00 && c <= 0xdfff) return -1;
  #|     else bytes += 3;
  #|   }
  #|   return bytes;
  #| }

///|
#cfg(target="js")
priv struct NativeModelBudget {
  mut remaining : Int32
}

///|
#cfg(target="js")
fn NativeModelBudget::charge(
  self : NativeModelBudget,
  bytes : Int32,
) -> Unit raise {
  if bytes < 0 || bytes > self.remaining {
    fail("Native model report requires the bounded text path")
  }
  self.remaining -= bytes
}

///|
#cfg(target="js")
fn native_model_value(
  value : Json,
  budget : NativeModelBudget,
  depth : Int32,
) -> NativeReportObject raise {
  if depth >= 64 {
    match value {
      Array(_) | Object(_) =>
        fail("Native model report nesting requires the text path")
      _ => ()
    }
  }
  match value {
    Null => {
      budget.charge(4)
      native_model_null()
    }
    True => {
      budget.charge(4)
      native_model_bool(true)
    }
    False => {
      budget.charge(5)
      native_model_bool(false)
    }
    String(text) => {
      budget.charge(native_model_string_bytes(text))
      native_model_string(text)
    }
    Number(_, ..) => {
      let token = value.stringify()
      budget.charge(token.length())
      native_model_number(token)
    }
    Array(items) => {
      budget.charge(2)
      let array = native_model_array()
      for index, item in items {
        if index > 0 {
          budget.charge(1)
        }
        budget.charge(1 + 2 * (depth + 1))
        native_model_push(array, native_model_value(item, budget, depth + 1))
      }
      if !items.is_empty() {
        budget.charge(1 + 2 * depth)
      }
      array
    }
    Object(fields) => {
      budget.charge(2)
      let object = native_model_object()
      let mut first = true
      for key, item in fields {
        if !first {
          budget.charge(1)
        }
        first = false
        budget.charge(1 + 2 * (depth + 1))
        budget.charge(native_model_string_bytes(key))
        budget.charge(2)
        native_model_set(
          object,
          key,
          native_model_value(item, budget, depth + 1),
        )
      }
      if !fields.is_empty() {
        budget.charge(1 + 2 * depth)
      }
      object
    }
  }
}

///|
#cfg(target="js")
fn native_model_record(
  value : Json,
  limit~ : Int32 = 33554432,
) -> NativeReportObject raise {
  // Match the original pretty report's limit, not a smaller compact encoding.
  native_model_value(value, { remaining: limit, }, 0)
}

///|
/// JS-only trusted output transport. Null requests the unchanged text fallback.
#cfg(target="js")
pub fn classify_models_v4_native(
  text : String,
  options_text : String,
) -> NativeReportObject {
  try {
    let wire = wire_model_options_v4(options_text)
    native_model_record(
      model_classification_v4_json(
        classify_models_v4(wire_model_facts_v4(text, wire), wire.options),
      ),
    )
  } catch {
    _ => native_model_null()
  }
}

///|
/// The relation classifier uses the same source checks, rules and counters.
#cfg(target="js")
pub fn classify_relation_models_v4_native(
  text : String,
  options_text : String,
) -> NativeReportObject {
  try {
    let wire = wire_relation_models_options_v4(options_text)
    match
      classify_relation_models_v4(
        wire_relation_models_facts_v4(text, wire),
        wire.wire.options,
        realtime_known=wire.realtime_known,
      ) {
      Ok(result) =>
        native_model_record(relation_model_classification_v4_json(result))
      Err(_) => native_model_null()
    }
  } catch {
    _ => native_model_null()
  }
}
