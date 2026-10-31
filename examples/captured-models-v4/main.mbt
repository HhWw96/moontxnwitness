///|
fn main {
  let raw =
    #|{"traceSchema":3,"dataModel":"point-register-v1","clockDomain":"captured-model-example","scope":{"exclusiveWriters":true},"gaps":[],"events":[
    #|{"seq":1,"time":0,"kind":"snapshot","consistent":true,"initial":{"x":"x0"}},
    #|{"seq":2,"time":1,"kind":"begin","tx":"A","connection":"c-A"},
    #|{"seq":3,"time":2,"kind":"read","tx":"A","key":"x","version":"x0"},
    #|{"seq":4,"time":3,"kind":"savepoint","tx":"A","name":"s","instance":"A-s"},
    #|{"seq":5,"time":4,"kind":"write","tx":"A","key":"x","version":"revoked","predecessor":"x0"},
    #|{"seq":6,"time":5,"kind":"read","tx":"A","key":"x","version":"revoked"},
    #|{"seq":7,"time":6,"kind":"rollback_to","tx":"A","instance":"A-s"},
    #|{"seq":8,"time":7,"kind":"read","tx":"A","key":"x","version":"x0"},
    #|{"seq":9,"time":8,"kind":"write","tx":"A","key":"x","version":"x1","predecessor":"x0"},
    #|{"seq":10,"time":9,"kind":"commit_request","tx":"A"},
    #|{"seq":11,"time":10,"kind":"commit_ok","tx":"A"}]}
  let history = match @txn.parse_history_v4(raw) {
    Ok(h) => h
    Err(m) => abort(m)
  }
  let facts = @txn.model_facts_v4(
    history,
    clients=[{ id: "logical-client-A", transactions: ["A"], }],
    clients_complete=true,
  ).unwrap()
  let options = @txn.model_options_v4(models=@txn.elle_core_models_v4()).unwrap()
  let result = @txn.classify_models_v4(facts, options)
  let report = @txn.model_classification_v4_json(result)
  let complete = match report {
    Object(f) => f.get("status") == Some(Json("checked-compatible"))
    _ => false
  }
  if !complete || !@txn.verify_models_v4(facts, report, options) {
    abort("Source/model certificate did not verify")
  }
  println(
    "captured register: 14 model obligations completed; original rollback observations retained; evidence verified",
  )
}
