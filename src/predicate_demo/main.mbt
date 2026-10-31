///|
fn main {
  let source =
    #|{"traceSchema":3,"dataModel":"relation-set-v1","clockDomain":"predicate-example","scope":{"exclusiveWriters":true,"completeSnapshotTables":["items"]},"relationSchema":{"items":{"primaryKey":"id","columns":{"id":"int64","value":"text"}}},"gaps":[],"events":[
    #|{"seq":1,"time":0,"kind":"snapshot","consistent":true,"initial":{"items":[]}},
    #|{"seq":2,"time":1,"kind":"begin","tx":"A","connection":"A"},{"seq":3,"time":2,"kind":"begin","tx":"B","connection":"B"},
    #|{"seq":4,"time":3,"kind":"row_read","tx":"A","relation":"items","predicate":[{"column":"value","op":"eq","value":"yes"}],"rows":[],"complete":true},
    #|{"seq":5,"time":4,"kind":"row_read","tx":"B","relation":"items","predicate":[{"column":"value","op":"eq","value":"yes"}],"rows":[],"complete":true},
    #|{"seq":6,"time":5,"kind":"row_write","tx":"A","relation":"items","key":"1","action":"insert","version":"a1","predecessor":null,"values":{"value":"yes"}},
    #|{"seq":7,"time":6,"kind":"row_write","tx":"B","relation":"items","key":"2","action":"insert","version":"b1","predecessor":null,"values":{"value":"yes"}},
    #|{"seq":8,"time":7,"kind":"commit_request","tx":"A"},{"seq":9,"time":8,"kind":"commit_ok","tx":"A"},{"seq":10,"time":9,"kind":"commit_request","tx":"B"},{"seq":11,"time":10,"kind":"commit_ok","tx":"B"}]}
  let history = @txn.parse_history_v4(source).unwrap()
  let predicate = @txn.classify_relation_predicate_v4(
    history,
    @txn.ScopedG2,
    rule_set=@txn.Adya2000Mixed,
  ).unwrap()
  let item = @txn.classify_relation_predicate_v4(
    history,
    @txn.ScopedG2Item,
    rule_set=@txn.Adya2000Mixed,
  ).unwrap()
  let report = @txn.relation_predicate_classification_v4_json(predicate)
  if predicate.status() != "refuted" || item.status() != "checked-compatible" {
    abort("Expected a predicate-only anti-dependency cycle")
  }
  if !@txn.verify_relation_predicate_classification_v4(
      history,
      report,
      @txn.ScopedG2,
      rule_set=@txn.Adya2000Mixed,
    ) {
    abort("Predicate category evidence did not verify")
  }
  println(report.stringify())
}
