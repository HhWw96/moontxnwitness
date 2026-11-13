///|
#export_name("inference_options_v4_content_json")
pub fn inference_options_v4_content_json(text : String) -> String {
  @txn.inference_options_v4_content_json(text)
}

///|
#export_name("infer_dependencies_v4_json")
pub fn infer_dependencies_v4_json(text : String, options : String) -> String {
  @txn.infer_dependencies_v4_json(text, options)
}

///|
#export_name("classify_with_inference_v4_json")
pub fn classify_with_inference_v4_json(
  text : String,
  options : String,
) -> String {
  @txn.classify_with_inference_v4_json(text, options)
}

///|
#export_name("verify_inference_v4_json")
pub fn verify_inference_v4_json(
  text : String,
  report : String,
  expected_options : String,
) -> String {
  @txn.verify_inference_v4_json(text, report, expected_options)
}

///|
#export_name("verify_with_inference_v4_json")
pub fn verify_with_inference_v4_json(
  text : String,
  report : String,
  expected_options : String,
) -> String {
  @txn.verify_with_inference_v4_json(text, report, expected_options)
}

///|
#export_name("inference_report_v4_content_json")
pub fn inference_report_v4_content_json(text : String) -> String {
  @txn.inference_report_v4_content_json(text)
}
