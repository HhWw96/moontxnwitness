///|
#export_name("version")
pub fn version() -> String {
  @txn.version()
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
