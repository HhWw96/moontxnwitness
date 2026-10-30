///|
fn load(text : String) -> @txn.HistoryV4 {
  match @txn.parse_history_v4(text) {
    Ok(history) => history
    Err(message) => abort(message)
  }
}

///|
fn main {
  // Parse at the input boundary; subsequent calls reuse the opaque typed history.
  let history : @txn.HistoryV4 = load(
    (
      #|{"schemaVersion":1,"initial":{"x":"x0","y":"y0"},"transactions":[
      #|{"id":"noise","status":"committed","ops":[{"type":"read","key":"x","version":"x0"}]},
      #|{"id":"A","status":"committed","ops":[{"type":"read","key":"x","version":"x0"},{"type":"write","key":"y","version":"y1"}]},
      #|{"id":"B","status":"committed","ops":[{"type":"read","key":"y","version":"y0"},{"type":"write","key":"x","version":"x1"}]}]}
    ),
  )
  let analysis = @txn.analyze_v4(history)
  if analysis.outcome() != @txn.Violation ||
    !@txn.verify_v4(history, @txn.analysis_v4_json(analysis)) {
    abort("Register counterexample or its complete analysis did not verify")
  }
  let classification = @txn.classify_v4(history)
  if classification.status() != "refuted" ||
    !@txn.verify_classification_v4(
      history,
      @txn.classification_v4_json(classification),
    ) {
    abort("Register category witness did not verify")
  }
  // Model preservation is explicit. Category-only checks do not accept a full
  // isolation model, and no inferred version order becomes an observed fact.
  let reduced = @txn.reduce_v4(history, preserve=@txn.Serializable)
  if reduced.status() != "reduced" ||
    !reduced.one_minimal() ||
    reduced.analysis().outcome() != @txn.Violation ||
    !@txn.verify_reduction_v4(
      history,
      @txn.reduction_v4_json(reduced),
      preserve=@txn.Serializable,
    ) ||
    !@txn.verify_v4(
      reduced.history(),
      @txn.analysis_v4_json(reduced.analysis()),
    ) {
    abort("Model-preserving reduced counterexample did not verify")
  }
  println(
    "register: violation; category witness and reduced counterexample verified",
  )

  let list = load(
    (
      #|{"traceSchema":3,"dataModel":"append-list-v1","clockDomain":"example-list","scope":{"exclusiveWriters":true},"gaps":[],"events":[
      #|{"seq":1,"time":0,"kind":"snapshot","initial":{"x":[]},"consistent":true},
      #|{"seq":2,"time":1,"kind":"begin","tx":"A","connection":"a"},
      #|{"seq":3,"time":2,"kind":"append","tx":"A","key":"x","id":"i","value":"same"},
      #|{"seq":4,"time":3,"kind":"list_read","tx":"A","key":"x","items":[{"id":"i","value":"same"}]},
      #|{"seq":5,"time":4,"kind":"commit_request","tx":"A"},
      #|{"seq":6,"time":5,"kind":"commit_ok","tx":"A"}]}
    ),
  )
  let list_analysis = @txn.analyze_v4(list)
  if list.data_model() != @txn.AppendListV4 ||
    list_analysis.outcome() != @txn.Consistent ||
    !@txn.verify_v4(list, @txn.analysis_v4_json(list_analysis)) {
    abort("Append-list replay did not verify")
  }
  println("append-list: consistent; complete analysis verified")

  let relation = load(
    (
      #|{"traceSchema":3,"dataModel":"relation-set-v1","clockDomain":"example-relation","relationSchema":{"accounts":{"primaryKey":"id","columns":{"id":"int64","balance":"int64"}}},"scope":{"exclusiveWriters":true,"completeSnapshotTables":["accounts"]},"gaps":[],"events":[
      #|{"seq":1,"time":0,"kind":"snapshot","initial":{"accounts":[]},"consistent":true}]}
    ),
  )
  let relation_analysis = @txn.analyze_v4(relation)
  if relation.data_model() != @txn.RelationSetV4 ||
    relation_analysis.outcome() != @txn.Consistent ||
    !@txn.verify_v4(relation, @txn.analysis_v4_json(relation_analysis)) ||
    @txn.classify_v4(relation).status() != "unsupported" {
    abort("Relation analysis or its explicit classification boundary changed")
  }
  println(
    "relation-set: consistent; category classification unsupported in this version",
  )
}
