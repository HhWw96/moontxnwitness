///|
#export_name("classify_relation_models_v4_json")
pub fn classify_relation_models_v4_json(
  text : String,
  options : String,
) -> String {
  @txn.classify_relation_models_v4_json(text, options)
}

///|
#export_name("verify_relation_models_v4_json")
pub fn verify_relation_models_v4_json(
  text : String,
  report : String,
  expected_options : String,
) -> String {
  @txn.verify_relation_models_v4_json(text, report, expected_options)
}

///|
#export_name("relation_model_options_v4_content_json")
pub fn relation_model_options_v4_content_json(text : String) -> String {
  @txn.relation_model_options_v4_content_json(text)
}

///|
#export_name("relation_model_report_v4_content_json")
pub fn relation_model_report_v4_content_json(text : String) -> String {
  @txn.relation_model_report_v4_content_json(text)
}

///|
#export_name("relation_model_capsule_v4_content_json")
pub fn relation_model_capsule_v4_content_json(text : String) -> String {
  @txn.relation_model_capsule_v4_content_json(text)
}
