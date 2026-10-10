///|
#export_name("version")
pub fn version() -> String {
  @txn.version()
}

///|
#export_name("shrink_json")
pub fn shrink_json(text : String) -> String {
  @txn.shrink_json(text)
}

///|
#export_name("replay_report_json")
pub fn replay_report_json(history : String, report : String) -> String {
  @txn.replay_report_json(history, report)
}

///|
#export_name("capsule_content_json")
pub fn capsule_content_json(text : String) -> String {
  @txn.capsule_content_json(text)
}

///|
#export_name("compare_models_json")
pub fn compare_models_json(text : String) -> String {
  @txn.compare_models_json(text)
}

///|
#export_name("analyze_json")
pub fn analyze_json(text : String) -> String {
  @txn.analyze_json(text)
}

///|
#export_name("verify_certificate_json")
pub fn verify_certificate_json(
  history : String,
  certificate : String,
) -> String {
  @txn.verify_certificate_json(history, certificate)
}

///|
#export_name("run_json")
pub fn run_json(text : String, format : String) -> String {
  @txn.run_json(text, format)
}
