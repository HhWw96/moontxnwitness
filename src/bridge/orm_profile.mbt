///|
/// Independent configured fixed-CRUD source promotion; legacy proof entries remain diagnostic.
#export_name("orm_profile_source_v3_json")
pub fn orm_profile_source_v3_json(text : String, options : String) -> String {
  @txn.orm_profile_source_v3_json(text, options)
}
