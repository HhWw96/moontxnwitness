///|
#export_name("normalize_capture_json")
pub fn normalize_capture_json(text : String) -> String {
  @txn.normalize_capture_json(text)
}

///|
#export_name("normalize_presence_json")
pub fn normalize_presence_json(text : String) -> String {
  @txn.normalize_presence_capture_json(text)
}
