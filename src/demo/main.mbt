///|
fn main {
  let input =
    #|{"schemaVersion":1,"initial":{"x":"x0","y":"y0"},"transactions":[
    #|{"id":"T1","status":"committed","ops":[{"type":"read","key":"x","version":"x0"},{"type":"write","key":"y","version":"y1"}]},
    #|{"id":"T2","status":"committed","ops":[{"type":"read","key":"y","version":"y0"},{"type":"write","key":"x","version":"x1"}]}]}
  let history = match @txn.parse_history(input) {
    Ok(history) => history
    Err(message) => abort(message)
  }
  let result = @txn.analyze_with_options(history)
  if result.report.outcome != @txn.Violation {
    abort("Expected a write-skew counterexample")
  }
  if !@txn.verify_cycle(history, result.report.witness) {
    abort("The dependency witness did not verify")
  }
  let reduced = @txn.reduce_with_options(history)
  if reduced.reduction.history.transactions.length() != 2 ||
    reduced.reduction.report.outcome != @txn.Violation {
    abort("Reduction did not preserve the two-transaction anomaly")
  }
  println(@txn.render_report(result.report, "text"))
  println(@txn.reduction_result_json(reduced).stringify())
}
