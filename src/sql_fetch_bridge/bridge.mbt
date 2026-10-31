///|
#export_name("verify_configured_fetch_v1_json")
pub fn verify(
  config : String,
  execution : String,
  native : String,
  deliveries : String,
  options : String,
) -> String {
  @txn.verify_configured_fetch_v1_json(
    config, execution, native, deliveries, options,
  )
}
