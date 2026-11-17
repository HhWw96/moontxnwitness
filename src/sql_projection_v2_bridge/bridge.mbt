///|
#export_name("normalize_configured_sql_v2_json")
pub fn normalize(
  config : String,
  sql : String,
  parameters : String,
  options : String,
) -> String {
  @txn.normalize_configured_sql_v2_json(config, sql, parameters, options)
}

///|
#export_name("verify_configured_sql_v2_json")
pub fn verify(
  config : String,
  sql : String,
  parameters : String,
  candidate : String,
  options : String,
) -> String {
  @txn.verify_configured_sql_v2_json(
    config, sql, parameters, candidate, options,
  )
}

///|
#export_name("normalize_sql_config_v2_json")
pub fn config(text : String) -> String {
  @txn.normalize_sql_config_v2_json(text)
}

///|
#export_name("verify_configured_result_v2_json")
pub fn result(
  config : String,
  execution : String,
  native : String,
  deliveries : String,
  options : String,
) -> String {
  @txn.verify_configured_result_v2_json(
    config, execution, native, deliveries, options,
  )
}

///|
#export_name("verify_point_projection_v2_json")
pub fn projection(
  config : String,
  sql : String,
  typed_parameters : String,
  options : String,
  descriptor : String,
  budget : String,
) -> String {
  @txn.verify_point_projection_v2_json(
    config, sql, typed_parameters, options, descriptor, budget,
  )
}

///|
#export_name("verify_projected_result_v2_json")
pub fn projected_result(
  config : String,
  sql : String,
  typed_parameters : String,
  projection_options : String,
  descriptor : String,
  native_frame : String,
  deliveries : String,
  options : String,
) -> String {
  @txn.verify_projected_result_v2_json(
    config, sql, typed_parameters, projection_options, descriptor, native_frame,
    deliveries, options,
  )
}

///|
#export_name("analyze_configured_window_v2_json")
pub fn window_analysis(
  config : String,
  policy : String,
  bundle : String,
  options : String,
) -> String {
  @txn.analyze_configured_window_v2_json(config, policy, bundle, options)
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
  @txn.verify_configured_window_v2_json(config, policy, bundle, report, options)
}

///|
#export_name("reduce_configured_window_v2_json")
pub fn window_reduction(
  config : String,
  policy : String,
  bundle : String,
  options : String,
) -> String {
  @txn.reduce_configured_window_v2_json(config, policy, bundle, options)
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
  @txn.verify_configured_window_reduction_v2_json(
    config, policy, bundle, report, options,
  )
}
