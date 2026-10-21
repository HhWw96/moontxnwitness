///|
fn v3_is_list_capture(text : String) -> Bool {
  try {
    let root = object_fields(guarded_json(text, limit=8388608), "capture")
    root.get("dataModel") == Some("append-list-v1".to_json())
  } catch {
    _ => false
  }
}

///|
pub fn normalize_capture_v3_json(text : String) -> String {
  if v3_is_list_capture(text) {
    normalize_list_capture_v3_json(text)
  } else {
    normalize_register_capture_v3_json(text)
  }
}
