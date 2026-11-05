///|
#export_name("version")
pub fn version() -> String {
  @txn.version()
}

///|
#export_name("analyze_v3_json")
pub fn analyze_v3_json(text : String, options : String) -> String {
  @txn.analyze_v3_json(text, options)
}

///|
#export_name("reduce_v3_json")
pub fn reduce_v3_json(text : String, options : String) -> String {
  @txn.reduce_v3_json(text, options)
}

///|
#export_name("verify_v3_json")
pub fn verify_v3_json(text : String, report : String) -> String {
  @txn.verify_v3_json(text, report)
}

///|
#export_name("capsule_v3_content_json")
pub fn capsule_v3_content_json(text : String) -> String {
  @txn.capsule_v3_content_json(text)
}

///|
#export_name("shrink_json")
pub fn shrink_json(text : String) -> String {
  @txn.shrink_json(text)
}

///|
#export_name("shrink_options_json")
pub fn shrink_options_json(text : String, options : String) -> String {
  @txn.shrink_options_json(text, options)
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
#cfg(target="js")
#export_name("analyze_native_js_v1")
pub fn analyze_native_js_v1(text : String) -> @txn.NativeReportObject {
  @txn.analyze_native_js_v1(text)
}

///|
#cfg(target="js")
#export_name("analyze_options_native_js_v1")
pub fn analyze_options_native_js_v1(
  text : String,
  options : String,
) -> @txn.NativeReportObject {
  @txn.analyze_options_native_js_v1(text, options)
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
#export_name("benchmark_parser_agreement")
pub fn benchmark_parser_agreement(text : String) -> String {
  @txn.benchmark_parser_agreement(text)
}

///|
#export_name("benchmark_parse_balanced")
pub fn benchmark_parse_balanced(text : String) -> @txn.History {
  match @txn.parse_history_optimized(text) {
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
pub fn benchmark_cycle(h : @txn.History, r : @txn.Report) -> Int32 {
  @txn.benchmark_cycle(h, r)
}

///|
#export_name("benchmark_search")
pub fn benchmark_search(h : @txn.History, r : @txn.Report) -> Int32 {
  @txn.benchmark_search(h, r)
}

///|
#export_name("benchmark_search_balanced")
pub fn benchmark_search_balanced(h : @txn.History, r : @txn.Report) -> Int32 {
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

///|
#export_name("benchmark_reduce_balanced")
pub fn benchmark_reduce_balanced(h : @txn.History) -> @txn.ReductionResult {
  @txn.benchmark_reduce_balanced(h)
}

///|
#export_name("classify_v3_json")
pub fn classify_v3_json(text : String, options : String) -> String {
  @txn.classify_v3_json(text, options)
}

///|
#export_name("reduce_classification_v3_json")
pub fn reduce_classification_v3_json(text : String, options : String) -> String {
  @txn.reduce_classification_v3_json(text, options)
}

///|
#export_name("verify_classification_v3_json")
pub fn verify_classification_v3_json(text : String, report : String) -> String {
  @txn.verify_classification_v3_json(text, report)
}

///|
#export_name("analyze_v4_json")
pub fn analyze_v4_json(text : String, options : String) -> String {
  @txn.analyze_v4_json(text, options)
}

///|
#export_name("classify_v4_json")
pub fn classify_v4_json(text : String, options : String) -> String {
  @txn.classify_v4_json(text, options)
}

///|
#export_name("reduce_v4_json")
pub fn reduce_v4_json(text : String, options : String) -> String {
  @txn.reduce_v4_json(text, options)
}

///|
#export_name("verify_v4_json")
pub fn verify_v4_json(
  text : String,
  report : String,
  options : String,
) -> String {
  @txn.verify_v4_json(text, report, options)
}

///|
#export_name("verify_classification_v4_json")
pub fn verify_classification_v4_json(
  text : String,
  report : String,
  options : String,
) -> String {
  @txn.verify_classification_v4_json(text, report, options)
}

///|
#export_name("verify_reduction_v4_json")
pub fn verify_reduction_v4_json(
  text : String,
  report : String,
  options : String,
) -> String {
  @txn.verify_reduction_v4_json(text, report, options)
}

///|
#export_name("capsule_v4_content_json")
pub fn capsule_v4_content_json(text : String) -> String {
  @txn.capsule_v4_content_json(text)
}

///|
#export_name("inspect_anomalies_v4_json")
pub fn inspect_anomalies_v4_json(text : String, options : String) -> String {
  @txn.inspect_anomalies_v4_json(text, options)
}

///|
#export_name("verify_anomalies_v4_json")
pub fn verify_anomalies_v4_json(
  text : String,
  report : String,
  options : String,
) -> String {
  @txn.verify_anomalies_v4_json(text, report, options)
}

///|
#export_name("options_v4_content_json")
pub fn options_v4_content_json(text : String) -> String {
  @txn.options_v4_content_json(text)
}

///|
#export_name("inspect_lost_updates_v4_json")
pub fn inspect_lost_updates_v4_json(text : String, options : String) -> String {
  @txn.inspect_lost_updates_v4_json(text, options)
}

///|
#export_name("verify_lost_updates_v4_json")
pub fn verify_lost_updates_v4_json(
  text : String,
  report : String,
  options : String,
) -> String {
  @txn.verify_lost_updates_v4_json(text, report, options)
}

///|
#export_name("classify_relation_v4_json")
pub fn classify_relation_v4_json(text : String, options : String) -> String {
  @txn.classify_relation_v4_json(text, options)
}

///|
#export_name("inspect_capture_anomalies_v4_json")
pub fn inspect_capture_anomalies_v4_json(
  text : String,
  options : String,
) -> String {
  @txn.inspect_capture_anomalies_v4_json(text, options)
}

///|
#export_name("inspect_internal_consistency_v4_json")
pub fn inspect_internal_consistency_v4_json(
  text : String,
  options : String,
) -> String {
  @txn.inspect_internal_consistency_v4_json(text, options)
}

///|
#export_name("verify_relation_classification_v4_json")
pub fn verify_relation_classification_v4_json(
  text : String,
  report : String,
  options : String,
) -> String {
  @txn.verify_relation_classification_v4_json(text, report, options)
}

///|
#export_name("verify_capture_anomalies_v4_json")
pub fn verify_capture_anomalies_v4_json(
  text : String,
  report : String,
  options : String,
) -> String {
  @txn.verify_capture_anomalies_v4_json(text, report, options)
}

///|
#export_name("verify_internal_consistency_v4_json")
pub fn verify_internal_consistency_v4_json(
  text : String,
  report : String,
  options : String,
) -> String {
  @txn.verify_internal_consistency_v4_json(text, report, options)
}

///|
#export_name("source_rules_report_v4_content_json")
pub fn source_rules_report_v4_content_json(text : String) -> String {
  @txn.source_rules_report_v4_content_json(text)
}

///|
#export_name("source_rules_capsule_v4_content_json")
pub fn source_rules_capsule_v4_content_json(text : String) -> String {
  @txn.source_rules_capsule_v4_content_json(text)
}

///|
#export_name("reduce_relation_category_v4_json")
pub fn reduce_relation_category_v4_json(
  text : String,
  options : String,
) -> String {
  @txn.reduce_relation_category_v4_json(text, options)
}

///|
#export_name("verify_relation_category_reduction_v4_json")
pub fn verify_relation_category_reduction_v4_json(
  text : String,
  report : String,
  options : String,
) -> String {
  @txn.verify_relation_category_reduction_v4_json(text, report, options)
}

///|
#export_name("relation_reduction_report_v4_content_json")
pub fn relation_reduction_report_v4_content_json(text : String) -> String {
  @txn.relation_reduction_report_v4_content_json(text)
}

///|
#export_name("relation_reduction_capsule_v4_content_json")
pub fn relation_reduction_capsule_v4_content_json(text : String) -> String {
  @txn.relation_reduction_capsule_v4_content_json(text)
}

///|
#export_name("classify_relation_predicate_v4_json")
pub fn classify_relation_predicate_v4_json(
  text : String,
  options : String,
) -> String {
  @txn.classify_relation_predicate_v4_json(text, options)
}

///|
#export_name("verify_relation_predicate_classification_v4_json")
pub fn verify_relation_predicate_classification_v4_json(
  text : String,
  report : String,
  options : String,
) -> String {
  @txn.verify_relation_predicate_classification_v4_json(text, report, options)
}

///|
#export_name("classify_models_v4_json")
pub fn classify_models_v4_json(text : String, options : String) -> String {
  @txn.classify_models_v4_json(text, options)
}

///|
#export_name("verify_model_classification_v4_json")
pub fn verify_model_classification_v4_json(
  text : String,
  report : String,
  options : String,
) -> String {
  @txn.verify_model_classification_v4_json(text, report, options)
}

///|
#export_name("model_options_v4_content_json")
pub fn model_options_v4_content_json(text : String) -> String {
  @txn.model_options_v4_content_json(text)
}

///|
#export_name("model_report_v4_content_json")
pub fn model_report_v4_content_json(text : String) -> String {
  @txn.model_report_v4_content_json(text)
}

///|
#export_name("model_capsule_v4_content_json")
pub fn model_capsule_v4_content_json(text : String) -> String {
  @txn.model_capsule_v4_content_json(text)
}

///|
#export_name("diagnose_configured_session_v4_json")
pub fn diagnose_configured_session_v4_json(
  a0 : String,
  a1 : String,
  a2 : String,
  a3 : String,
  a4 : String,
) -> String {
  @txn.diagnose_configured_session_v4_json(a0, a1, a2, a3, a4)
}

///|
#export_name("verify_configured_session_diagnostic_v4_json")
pub fn verify_configured_session_diagnostic_v4_json(
  a0 : String,
  a1 : String,
  a2 : String,
  a3 : String,
  a4 : String,
  a5 : String,
) -> Bool {
  @txn.verify_configured_session_diagnostic_v4_json(a0, a1, a2, a3, a4, a5)
}

///|
#export_name("configured_session_options_v4_json")
pub fn configured_session_options_v4_json(a0 : String) -> String {
  @txn.configured_session_options_v4_json(a0)
}

///|
#export_name("configured_session_bundle_v4_json")
pub fn configured_session_bundle_v4_json(a0 : String) -> String {
  @txn.configured_session_bundle_v4_json(a0)
}

///|
#export_name("normalize_sql_config_v1_json")
pub fn normalize_sql_config_v1_json(a0 : String) -> String {
  @txn.normalize_sql_config_v1_json(a0)
}

///|
#export_name("normalize_configured_sql_v1_json")
pub fn normalize_configured_sql_v1_json(
  a0 : String,
  a1 : String,
  a2 : String,
  a3 : String,
) -> String {
  @txn.normalize_configured_sql_v1_json(a0, a1, a2, a3)
}

///|
#export_name("verify_configured_sql_v1_json")
pub fn verify_configured_sql_v1_json(
  a0 : String,
  a1 : String,
  a2 : String,
  a3 : String,
  a4 : String,
) -> String {
  @txn.verify_configured_sql_v1_json(a0, a1, a2, a3, a4)
}

///|
#export_name("verify_configured_fetch_v1_json")
pub fn verify_configured_fetch_v1_json(
  a0 : String,
  a1 : String,
  a2 : String,
  a3 : String,
  a4 : String,
) -> String {
  @txn.verify_configured_fetch_v1_json(a0, a1, a2, a3, a4)
}

///|
#export_name("verify_source_installation_v4_json")
pub fn verify_source_installation_v4_json(
  a0 : String,
  a1 : String,
  a2 : String,
  a3 : String,
  a4 : String,
) -> String {
  @txn.verify_source_installation_v4_json(a0, a1, a2, a3, a4)
}

///|
#export_name("verify_source_installation_report_v4_json")
pub fn verify_source_installation_report_v4_json(
  a0 : String,
  a1 : String,
  a2 : String,
  a3 : String,
  a4 : String,
  a5 : String,
) -> Bool {
  @txn.verify_source_installation_report_v4_json(a0, a1, a2, a3, a4, a5)
}

///|
#export_name("verify_source_fetch_mapping_v4_json")
pub fn verify_source_fetch_mapping_v4_json(
  a0 : String,
  a1 : String,
  a2 : String,
  a3 : String,
  a4 : String,
  a5 : String,
  a6 : String,
  a7 : String,
  a8 : String,
) -> String {
  @txn.verify_source_fetch_mapping_v4_json(a0, a1, a2, a3, a4, a5, a6, a7, a8)
}

///|
#export_name("verify_source_fetch_mapping_report_v4_json")
pub fn verify_source_fetch_mapping_report_v4_json(
  a0 : String,
  a1 : String,
  a2 : String,
  a3 : String,
  a4 : String,
  a5 : String,
  a6 : String,
  a7 : String,
  a8 : String,
  a9 : String,
) -> Bool {
  @txn.verify_source_fetch_mapping_report_v4_json(
    a0, a1, a2, a3, a4, a5, a6, a7, a8, a9,
  )
}

///|
#export_name("compare_c_text_v1")
pub fn compare_c_text_v1(a : String, b : String) -> Int32 {
  @txn.compare_configured_c_text_v1(a, b)
}
