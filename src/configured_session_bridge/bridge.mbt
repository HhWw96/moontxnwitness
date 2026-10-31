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
