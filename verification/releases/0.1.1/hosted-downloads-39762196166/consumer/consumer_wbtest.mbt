///|
fn load(text : String) -> @txn.History {
  match @txn.parse_history(text) {
    Ok(h) => h
    Err(_) => abort("Published fixture parse failed")
  }
}

///|
test "published exact version and positive history" {
  assert_eq(installed_version(), "0.1.1")
  assert_true(@txn.analyze(load("{\n  \"schemaVersion\": 1,\n  \"name\": \"Two committed transactions with a valid serial order\",\n  \"initial\": {\"x\": \"x0\", \"y\": \"y0\"},\n  \"transactions\": [\n    {\"id\": \"T1\", \"status\": \"committed\", \"ops\": [{\"type\": \"read\", \"key\": \"x\", \"version\": \"x0\"}, {\"type\": \"write\", \"key\": \"y\", \"version\": \"y1\"}]},\n    {\"id\": \"T2\", \"status\": \"committed\", \"ops\": [{\"type\": \"read\", \"key\": \"y\", \"version\": \"y1\"}, {\"type\": \"write\", \"key\": \"x\", \"version\": \"x1\"}]}\n  ]\n}\n")).outcome == @txn.Consistent)
}

///|
test "published shortest cycle provenance" {
  let h = load("{\n  \"schemaVersion\": 1,\n  \"name\": \"Synthetic two-key write skew\",\n  \"initial\": {\"x\": \"x0\", \"y\": \"y0\"},\n  \"transactions\": [\n    {\"id\": \"T1\", \"status\": \"committed\", \"ops\": [{\"type\": \"read\", \"key\": \"x\", \"version\": \"x0\"}, {\"type\": \"write\", \"key\": \"y\", \"version\": \"y1\"}]},\n    {\"id\": \"T2\", \"status\": \"committed\", \"ops\": [{\"type\": \"read\", \"key\": \"y\", \"version\": \"y0\"}, {\"type\": \"write\", \"key\": \"x\", \"version\": \"x1\"}]}\n  ]\n}\n")
  let r = @txn.analyze(h)
  assert_true(r.outcome == @txn.Violation)
  assert_eq(r.witness.length(), 2)
  assert_true(@txn.verify_cycle(h, r.witness))
}

///|
test "published missing-order completion and exhaustive failure" {
  assert_true(@txn.analyze(load("{\n  \"schemaVersion\": 1,\n  \"name\": \"No evidence establishes the order of two versions\",\n  \"initial\": {\"x\": \"x0\"},\n  \"transactions\": [\n    {\"id\": \"W1\", \"status\": \"committed\", \"ops\": [{\"type\": \"write\", \"key\": \"x\", \"version\": \"x1\"}]},\n    {\"id\": \"W2\", \"status\": \"committed\", \"ops\": [{\"type\": \"write\", \"key\": \"x\", \"version\": \"x2\"}]}\n  ]\n}\n")).outcome == @txn.Consistent)
  let r = @txn.analyze(load("{\n  \"schemaVersion\": 1,\n  \"name\": \"Synthetic mixed versions from two atomic writers; missing version orders\",\n  \"initial\": {\"x\": \"x0\", \"y\": \"y0\"},\n  \"transactions\": [\n    {\"id\": \"A\", \"status\": \"committed\", \"ops\": [{\"type\": \"write\", \"key\": \"x\", \"version\": \"x1\"}, {\"type\": \"write\", \"key\": \"y\", \"version\": \"y1\"}]},\n    {\"id\": \"B\", \"status\": \"committed\", \"ops\": [{\"type\": \"write\", \"key\": \"x\", \"version\": \"x2\"}, {\"type\": \"write\", \"key\": \"y\", \"version\": \"y2\"}]},\n    {\"id\": \"R\", \"status\": \"committed\", \"ops\": [{\"type\": \"read\", \"key\": \"x\", \"version\": \"x1\"}, {\"type\": \"read\", \"key\": \"y\", \"version\": \"y2\"}]}\n  ]\n}\n"))
  assert_true(r.outcome == @txn.Violation)
  assert_eq(r.search.status, "exhausted")
  assert_true(r.witness.is_empty())
}

///|
test "published transaction reduction" {
  let r = @txn.reduce_history(load("{\n  \"schemaVersion\": 1,\n  \"name\": \"Synthetic two-transaction violation hidden among harmless transactions\",\n  \"initial\": {\"x\": \"x0\", \"y\": \"y0\"},\n  \"transactions\": [\n    {\"id\": \"noise-1\", \"status\": \"committed\", \"ops\": []},\n    {\"id\": \"noise-2\", \"status\": \"committed\", \"ops\": []},\n    {\"id\": \"T1\", \"status\": \"committed\", \"ops\": [{\"type\": \"read\", \"key\": \"x\", \"version\": \"x0\"}, {\"type\": \"write\", \"key\": \"y\", \"version\": \"y1\"}]},\n    {\"id\": \"noise-3\", \"status\": \"committed\", \"ops\": []},\n    {\"id\": \"T2\", \"status\": \"committed\", \"ops\": [{\"type\": \"read\", \"key\": \"y\", \"version\": \"y0\"}, {\"type\": \"write\", \"key\": \"x\", \"version\": \"x1\"}]},\n    {\"id\": \"noise-4\", \"status\": \"committed\", \"ops\": []},\n    {\"id\": \"noise-5\", \"status\": \"committed\", \"ops\": []}\n  ]\n}\n"))
  assert_true(r.one_minimal)
  assert_eq(r.history.transactions.length(), 2)
  assert_true(r.report.outcome == @txn.Violation)
}

///|
test "published model comparison" {
  let j = @txn.compare_models(load("{\n  \"schemaVersion\": 1,\n  \"name\": \"Synthetic stale read after a completed write\",\n  \"model\": \"strict-serializable\",\n  \"initial\": {\"x\": \"x0\"},\n  \"transactions\": [\n    {\"id\": \"W\", \"status\": \"committed\", \"start\": 1, \"end\": 2, \"ops\": [{\"type\": \"write\", \"key\": \"x\", \"version\": \"x1\"}]},\n    {\"id\": \"R\", \"status\": \"committed\", \"start\": 3, \"end\": 4, \"ops\": [{\"type\": \"read\", \"key\": \"x\", \"version\": \"x0\"}]}\n  ]\n}\n"))
  assert_true(j is Object(m) && m.get("classification") == Some("realtime-only-violation".to_json()))
}

///|
test "published semantic report replay" {
  let text = "{\n  \"schemaVersion\": 1,\n  \"name\": \"Synthetic two-key write skew\",\n  \"initial\": {\"x\": \"x0\", \"y\": \"y0\"},\n  \"transactions\": [\n    {\"id\": \"T1\", \"status\": \"committed\", \"ops\": [{\"type\": \"read\", \"key\": \"x\", \"version\": \"x0\"}, {\"type\": \"write\", \"key\": \"y\", \"version\": \"y1\"}]},\n    {\"id\": \"T2\", \"status\": \"committed\", \"ops\": [{\"type\": \"read\", \"key\": \"y\", \"version\": \"y0\"}, {\"type\": \"write\", \"key\": \"x\", \"version\": \"x1\"}]}\n  ]\n}\n"
  let r = @txn.analyze(load(text))
  let j = @json.parse(@txn.replay_report_json(text, @txn.report_json(r).stringify()))
  assert_true(j is Object(m) && m.get("valid") == Some(true.to_json()))
}

///|
test "published balanced profile and v2 replay" {
  let text = "{\n  \"schemaVersion\": 1,\n  \"name\": \"Synthetic mixed versions from two atomic writers; missing version orders\",\n  \"initial\": {\"x\": \"x0\", \"y\": \"y0\"},\n  \"transactions\": [\n    {\"id\": \"A\", \"status\": \"committed\", \"ops\": [{\"type\": \"write\", \"key\": \"x\", \"version\": \"x1\"}, {\"type\": \"write\", \"key\": \"y\", \"version\": \"y1\"}]},\n    {\"id\": \"B\", \"status\": \"committed\", \"ops\": [{\"type\": \"write\", \"key\": \"x\", \"version\": \"x2\"}, {\"type\": \"write\", \"key\": \"y\", \"version\": \"y2\"}]},\n    {\"id\": \"R\", \"status\": \"committed\", \"ops\": [{\"type\": \"read\", \"key\": \"x\", \"version\": \"x1\"}, {\"type\": \"read\", \"key\": \"y\", \"version\": \"y2\"}]}\n  ]\n}\n"
  let result = @txn.analyze_with_options(load(text))
  assert_true(result.report.outcome == @txn.Violation)
  assert_eq(result.report.search.status, "exhausted")
  let j = @txn.analysis_result_json(result)
  let replay = @json.parse(@txn.replay_report_json(text, j.stringify()))
  assert_true(replay is Object(m) && m.get("valid") == Some(true.to_json()))
}

///|
test "published balanced reduction" {
  let result = @txn.reduce_with_options(load("{\n  \"schemaVersion\": 1,\n  \"name\": \"Synthetic two-transaction violation hidden among harmless transactions\",\n  \"initial\": {\"x\": \"x0\", \"y\": \"y0\"},\n  \"transactions\": [\n    {\"id\": \"noise-1\", \"status\": \"committed\", \"ops\": []},\n    {\"id\": \"noise-2\", \"status\": \"committed\", \"ops\": []},\n    {\"id\": \"T1\", \"status\": \"committed\", \"ops\": [{\"type\": \"read\", \"key\": \"x\", \"version\": \"x0\"}, {\"type\": \"write\", \"key\": \"y\", \"version\": \"y1\"}]},\n    {\"id\": \"noise-3\", \"status\": \"committed\", \"ops\": []},\n    {\"id\": \"T2\", \"status\": \"committed\", \"ops\": [{\"type\": \"read\", \"key\": \"y\", \"version\": \"y0\"}, {\"type\": \"write\", \"key\": \"x\", \"version\": \"x1\"}]},\n    {\"id\": \"noise-4\", \"status\": \"committed\", \"ops\": []},\n    {\"id\": \"noise-5\", \"status\": \"committed\", \"ops\": []}\n  ]\n}\n"))
  assert_true(result.reduction.one_minimal)
  assert_eq(result.reduction.history.transactions.length(), 2)
  assert_true(result.analysis.report.outcome == @txn.Violation)
}

///|
test "published complete capture normalizes to analyzable history" {
  let result = @json.parse(@txn.normalize_capture_json("{\"traceSchema\": 1, \"clockDomain\": \"synthetic-example-clock\", \"scope\": {\"exclusiveWriters\": true}, \"gaps\": [], \"events\": [{\"seq\": 1, \"kind\": \"snapshot\", \"time\": 0, \"consistent\": true, \"initial\": {\"x\": \"x0\", \"y\": \"y0\"}}, {\"seq\": 2, \"kind\": \"begin\", \"tx\": \"A\", \"time\": 1}, {\"seq\": 3, \"kind\": \"begin\", \"tx\": \"B\", \"time\": 2}, {\"seq\": 4, \"kind\": \"op\", \"tx\": \"A\", \"time\": 3, \"op\": {\"type\": \"read\", \"key\": \"x\", \"version\": \"x0\"}}, {\"seq\": 5, \"kind\": \"op\", \"tx\": \"B\", \"time\": 4, \"op\": {\"type\": \"read\", \"key\": \"y\", \"version\": \"y0\"}}, {\"seq\": 6, \"kind\": \"op\", \"tx\": \"A\", \"time\": 5, \"op\": {\"type\": \"write\", \"key\": \"y\", \"version\": \"y1\"}}, {\"seq\": 7, \"kind\": \"op\", \"tx\": \"B\", \"time\": 6, \"op\": {\"type\": \"write\", \"key\": \"x\", \"version\": \"x1\"}}, {\"seq\": 8, \"kind\": \"end\", \"tx\": \"A\", \"time\": 7, \"status\": \"committed\"}, {\"seq\": 9, \"kind\": \"end\", \"tx\": \"B\", \"time\": 8, \"status\": \"committed\"}]}"))
  match result {
    Object(fields) => {
      assert_eq(fields.get("status"), Some("ready".to_json()))
      assert_true(fields.get("coverage") is Some(Object(coverage)) && coverage.get("complete") == Some(true.to_json()))
      let h = load(fields.at("history").stringify())
      assert_true(@txn.analyze(h).outcome == @txn.Violation)
    }
    _ => abort("Normalized capture object required")
  }
}

///|
test "published incomplete capture refuses a history" {
  let result = @json.parse(@txn.normalize_capture_json("{\"traceSchema\": 1, \"clockDomain\": \"synthetic-example-clock\", \"scope\": {\"exclusiveWriters\": true}, \"gaps\": [], \"events\": [{\"seq\": 1, \"kind\": \"snapshot\", \"time\": 0, \"consistent\": true, \"initial\": {\"x\": \"x0\", \"y\": \"y0\"}}, {\"seq\": 2, \"kind\": \"begin\", \"tx\": \"A\", \"time\": 1}, {\"seq\": 3, \"kind\": \"begin\", \"tx\": \"B\", \"time\": 2}, {\"seq\": 4, \"kind\": \"op\", \"tx\": \"A\", \"time\": 3, \"op\": {\"type\": \"read\", \"key\": \"x\", \"version\": \"x0\"}}, {\"seq\": 5, \"kind\": \"op\", \"tx\": \"B\", \"time\": 4, \"op\": {\"type\": \"read\", \"key\": \"y\", \"version\": \"y0\"}}, {\"seq\": 6, \"kind\": \"op\", \"tx\": \"A\", \"time\": 5, \"op\": {\"type\": \"write\", \"key\": \"y\", \"version\": \"y1\"}}, {\"seq\": 7, \"kind\": \"op\", \"tx\": \"B\", \"time\": 6, \"op\": {\"type\": \"write\", \"key\": \"x\", \"version\": \"x1\"}}, {\"seq\": 8, \"kind\": \"end\", \"tx\": \"A\", \"time\": 7, \"status\": \"committed\"}]}"))
  match result {
    Object(fields) => {
      assert_eq(fields.get("status"), Some("inconclusive".to_json()))
      assert_eq(fields.get("history"), Some(Json::null()))
      assert_true(fields.get("coverage") is Some(Object(coverage)) && coverage.get("complete") == Some(false.to_json()))
    }
    _ => abort("Normalized capture object required")
  }
}
