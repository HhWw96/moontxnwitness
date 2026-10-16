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
#export_name("analyze_options_json")
pub fn analyze_options_json(text : String, options : String) -> String {
  @txn.analyze_options_json(text, options)
}

///|
#export_name("run_options_json")
pub fn run_options_json(text : String, format : String) -> String {
  @txn.run_options_json(text, format)
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

///|
#export_name("benchmark_parse")
pub fn benchmark_parse(text : String) -> @txn.History {
  match @txn.parse_history(text) {
    Ok(h) => h
    Err(_) => abort("Invalid benchmark fixture")
  }
}

///|
#export_name("benchmark_infer")
pub fn benchmark_infer(h : @txn.History) -> @txn.Report {
  @txn.benchmark_infer(h)
}

///|
#export_name("benchmark_cycle")
pub fn benchmark_cycle(h : @txn.History, r : @txn.Report) -> Int {
  @txn.benchmark_cycle(h, r)
}

///|
#export_name("benchmark_search")
pub fn benchmark_search(h : @txn.History, r : @txn.Report) -> Int {
  @txn.benchmark_search(h, r)
}

///|
#export_name("benchmark_search_balanced")
pub fn benchmark_search_balanced(h : @txn.History, r : @txn.Report) -> Int {
  @txn.benchmark_search_balanced(h, r)
}

///|
#export_name("benchmark_render")
pub fn benchmark_render(r : @txn.Report) -> String {
  @txn.benchmark_render(r)
}

///|
#export_name("benchmark_reduce")
pub fn benchmark_reduce(h : @txn.History) -> @txn.Reduction {
  @txn.reduce_history(h)
}
