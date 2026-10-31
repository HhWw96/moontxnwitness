///|
fn main {
  let raw = "{\"traceSchema\":3,\"clockDomain\":\"v3-test\",\"scope\":{\"exclusiveWriters\":true},\"events\":[{\"kind\":\"snapshot\",\"initial\":{\"x\":[],\"y\":[]},\"consistent\":true,\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"W\",\"connection\":\"W\",\"seq\":2,\"time\":1},{\"kind\":\"append\",\"tx\":\"W\",\"key\":\"x\",\"id\":\"w\",\"value\":\"same\",\"seq\":3,\"time\":2},{\"kind\":\"append\",\"tx\":\"W\",\"key\":\"y\",\"id\":\"y1\",\"value\":\"same\",\"seq\":4,\"time\":3},{\"kind\":\"commit_request\",\"tx\":\"W\",\"seq\":5,\"time\":4},{\"kind\":\"commit_ok\",\"tx\":\"W\",\"seq\":6,\"time\":5},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"A\",\"seq\":7,\"time\":6},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"y\",\"items\":[{\"id\":\"y1\",\"value\":\"same\"}],\"seq\":8,\"time\":7},{\"kind\":\"savepoint\",\"tx\":\"A\",\"name\":\"s\",\"instance\":\"A-s1\",\"seq\":9,\"time\":8},{\"kind\":\"append\",\"tx\":\"A\",\"key\":\"x\",\"id\":\"a\",\"value\":\"same\",\"seq\":10,\"time\":9},{\"kind\":\"list_read\",\"tx\":\"A\",\"key\":\"x\",\"items\":[{\"id\":\"w\",\"value\":\"same\"},{\"id\":\"a\",\"value\":\"same\"}],\"seq\":11,\"time\":10},{\"kind\":\"rollback_to\",\"tx\":\"A\",\"instance\":\"A-s1\",\"seq\":12,\"time\":11},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":13,\"time\":12},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":14,\"time\":13}],\"gaps\":[],\"dataModel\":\"append-list-v1\"}"
  let history = @txn.parse_history_v4(raw).unwrap()
  let original = @txn.history_v4_json(history)
  let projection = @txn.project_list_prefix_v4(history).unwrap()
  if !projection.is_projected() {
    abort("list source mapping was not proven")
  }
  let facts = @txn.model_facts_v4(history).unwrap()
  let options = @txn.model_options_v4(
    models=[@txn.ElleSnapshotIsolation],
    list_profile=@txn.ModelListPrefixStates,
  ).unwrap()
  let report = @txn.model_classification_v4_json(
    @txn.classify_models_v4(facts, options),
  )
  let complete = match report {
    Object(f) => f.get("status") == Some(Json("checked-compatible"))
    _ => false
  }
  if !complete ||
    !@txn.verify_models_v4(facts, report, options) ||
    @txn.history_v4_json(history) != original {
    abort("original list program or model evidence did not verify")
  }
  println(
    "captured list: foreign prefix inferred from delivered own read; revoked append retained as observation; original program and SI evidence verified",
  )
}
