///|
fn main {
  let raw = "{\"traceSchema\":3,\"dataModel\":\"relation-set-v1\",\"relationSchema\":{\"items\":{\"primaryKey\":\"id\",\"columns\":{\"id\":\"int64\",\"value\":\"text\"}}},\"clockDomain\":\"atomic-row-example\",\"scope\":{\"exclusiveWriters\":true,\"completeSnapshotTables\":[\"items\"]},\"gaps\":[],\"events\":[{\"kind\":\"snapshot\",\"consistent\":true,\"initial\":{\"items\":[{\"key\":\"1\",\"version\":\"v0\",\"values\":{\"value\":\"before\"}}]},\"seq\":1,\"time\":0},{\"kind\":\"begin\",\"tx\":\"A\",\"connection\":\"physical-A\",\"seq\":2,\"time\":1},{\"kind\":\"row_read\",\"tx\":\"A\",\"relation\":\"items\",\"predicate\":[{\"column\":\"id\",\"op\":\"eq\",\"value\":\"1\"}],\"rows\":[{\"key\":\"1\",\"version\":\"v0\",\"values\":{\"value\":\"before\"}}],\"complete\":true,\"seq\":3,\"time\":2},{\"kind\":\"row_write\",\"tx\":\"A\",\"relation\":\"items\",\"key\":\"1\",\"action\":\"update\",\"version\":\"v1\",\"predecessor\":\"v0\",\"values\":{\"value\":\"after\"},\"seq\":4,\"time\":3},{\"kind\":\"row_read\",\"tx\":\"A\",\"relation\":\"items\",\"predicate\":[{\"column\":\"id\",\"op\":\"eq\",\"value\":\"1\"}],\"rows\":[{\"key\":\"1\",\"version\":\"v1\",\"values\":{\"value\":\"after\"}}],\"complete\":true,\"seq\":5,\"time\":4},{\"kind\":\"commit_request\",\"tx\":\"A\",\"seq\":6,\"time\":5},{\"kind\":\"commit_ok\",\"tx\":\"A\",\"seq\":7,\"time\":6}]}"
  let history = @txn.parse_history_v4(raw).unwrap()
  let original = @txn.history_v4_json(history)
  let projection = @txn.project_relation_rows_v4(history).unwrap()
  let facts = @txn.model_facts_v4(
    history,
    clients=[{ id: "declared-logical-A", transactions: ["A"], }],
    clients_complete=true,
  ).unwrap()
  let options = @txn.model_options_v4(
    models=@txn.elle_core_models_v4(),
    relation_profile=@txn.ModelRelationAtomicRows,
  ).unwrap()
  let report = @txn.model_classification_v4_json(
    @txn.classify_models_v4(facts, options),
  )
  let compatible = match report {
    Object(fields) => fields.get("status") == Some(Json("checked-compatible"))
    _ => false
  }
  let certificate : Json = {
    "commitOrder": ["A"],
    "visibilityPrefixes": [
      {
        "transaction": "A",
        "visiblePrefixLength": 0,
        "visibleTransactions": [],
      },
    ],
  }
  let serial = @txn.replay_relation_program_v4(
    history,
    certificate,
    mode=@txn.RelationSerialOrder,
  ).unwrap()
  if !projection.is_projected() ||
    !compatible ||
    !@txn.verify_models_v4(facts, report, options) ||
    serial.status() != "checked-compatible" ||
    @txn.history_v4_json(history) != original {
    abort("row source or original program certificate did not verify")
  }
  println(
    "atomic row: original point queries and row effects retained; independent row program replay and requested model obligations verified",
  )
}
