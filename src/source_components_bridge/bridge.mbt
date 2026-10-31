///|
#export_name("verify_source_installation_v4_json")
pub fn verify_source_installation_v4_json(
  config : String,
  policy : String,
  log : String,
  receipt : String,
  options : String,
) -> String {
  @txn.verify_source_installation_v4_json(config, policy, log, receipt, options)
}

///|
#export_name("verify_source_installation_report_v4_json")
pub fn verify_source_installation_report_v4_json(
  config : String,
  policy : String,
  log : String,
  receipt : String,
  report : String,
  expected_options : String,
) -> Bool {
  @txn.verify_source_installation_report_v4_json(
    config, policy, log, receipt, report, expected_options,
  )
}

///|
#export_name("verify_source_fetch_mapping_v4_json")
pub fn verify_source_fetch_mapping_v4_json(
  config : String,
  policy : String,
  log : String,
  receipt : String,
  execution : String,
  native : String,
  deliveries : String,
  context : String,
  options : String,
) -> String {
  @txn.verify_source_fetch_mapping_v4_json(
    config, policy, log, receipt, execution, native, deliveries, context, options,
  )
}

///|
#export_name("verify_source_fetch_mapping_report_v4_json")
pub fn verify_source_fetch_mapping_report_v4_json(
  config : String,
  policy : String,
  log : String,
  receipt : String,
  execution : String,
  native : String,
  deliveries : String,
  context : String,
  report : String,
  expected_options : String,
) -> Bool {
  @txn.verify_source_fetch_mapping_report_v4_json(
    config, policy, log, receipt, execution, native, deliveries, context, report,
    expected_options,
  )
}
