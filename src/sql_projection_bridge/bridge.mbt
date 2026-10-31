///|
#export_name("normalize_configured_sql_v1_json")
pub fn normalize(
  config : String,
  sql : String,
  parameters : String,
  options : String,
) -> String {
  @txn.normalize_configured_sql_v1_json(config, sql, parameters, options)
}

///|
#export_name("verify_configured_sql_v1_json")
pub fn verify(
  config : String,
  sql : String,
  parameters : String,
  candidate : String,
  options : String,
) -> String {
  @txn.verify_configured_sql_v1_json(
    config, sql, parameters, candidate, options,
  )
}

///|
#export_name("compare_c_text_v1")
pub fn compare(a : String, b : String) -> Int32 {
  @txn.compare_configured_c_text_v1(a, b)
}

///|
#export_name("normalize_sql_config_v1_json")
pub fn config(text : String) -> String {
  @txn.normalize_sql_config_v1_json(text)
}
