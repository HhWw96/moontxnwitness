///|
#export_name("normalize_capture_json")
pub fn normalize_capture_json(text : String) -> String {
  @txn.normalize_capture_json(text)
}

///|
#export_name("inspect_execution_failures_v3_json")
pub fn inspect_execution_failures_v3_json(text : String) -> String {
  @txn.inspect_execution_failures_v3_json(text)
}

///|
#export_name("normalize_capture_v3_json")
pub fn normalize_capture_v3_json(text : String) -> String {
  @txn.normalize_capture_v3_json(text)
}

///|
#export_name("dislock_sql_v3_proof_json")
pub fn dislock_sql_v3_proof_json(text : String) -> String {
  @txn.dislock_sql_v3_proof_json(text)
}

///|
#export_name("normalize_capture_v3_options_json")
pub fn normalize_capture_v3_options_json(
  text : String,
  options : String,
) -> String {
  @txn.normalize_capture_v3_options_json(text, options)
}

///|
#export_name("normalize_presence_json")
pub fn normalize_presence_json(text : String) -> String {
  @txn.normalize_presence_capture_json(text)
}
