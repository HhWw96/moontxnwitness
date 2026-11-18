///|
#export_name("analyze_configured_window_v2_json")
pub fn window_analysis(
  config : String,
  policy : String,
  bundle : String,
  options : String,
) -> String {
  @txn.analyze_configured_window_structured_v2_json(
    config, policy, bundle, options,
  )
}

///|
#export_name("verify_configured_window_v2_json")
pub fn window_verification(
  config : String,
  policy : String,
  bundle : String,
  report : String,
  options : String,
) -> String {
  @txn.verify_configured_window_structured_v2_json(
    config, policy, bundle, report, options,
  )
}

///|
#export_name("reduce_configured_window_v2_json")
pub fn window_reduction(
  config : String,
  policy : String,
  bundle : String,
  options : String,
) -> String {
  @txn.reduce_configured_window_structured_v2_json(
    config, policy, bundle, options,
  )
}

///|
#export_name("verify_configured_window_reduction_v2_json")
pub fn window_reduction_verification(
  config : String,
  policy : String,
  bundle : String,
  report : String,
  options : String,
) -> String {
  @txn.verify_configured_window_reduction_structured_v2_json(
    config, policy, bundle, report, options,
  )
}
