///|
pub fn installed_version() -> String { @txn.version() }

///|
pub fn analyze_history(text : String) -> Json {
  @json.parse(@txn.analyze_json(text)) catch { _ => abort("Unexpected report JSON") }
}
