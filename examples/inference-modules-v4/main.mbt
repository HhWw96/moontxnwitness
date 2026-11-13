///|
// These two functions are registered by this consumer, not loaded from a report.
// Both inspect the same original view and replay constraints already proved by
// its source adapter. No callback consumes another callback's output.
fn original_read_sources() -> @txn.InferenceModuleV4 {
  @txn.inference_module_v4(
    "example-read-sources",
    "example-original-wr-replay/v1",
    fn(view, _parameters, budget) {
      let edges : Array[@txn.ScopedDataEdgeInputV4] = []
      for edge in view.data_edges() {
        if !budget.charge() {
          break
        }
        if edge.kind == @txn.ScopedWRItem {
          edges.push(edge)
        }
      }
      Ok({ data_edges: edges, order_edges: [], gaps: [], })
    },
    algorithm=Some("example-read-sources-1"),
  ).unwrap()
}

///|
fn original_version_constraints(mode : String) -> @txn.InferenceModuleV4 {
  @txn.inference_module_v4(
    "example-version-constraints",
    "example-original-version-replay/v1",
    fn(view, parameters, budget) {
      let edges : Array[@txn.ScopedDataEdgeInputV4] = []
      for edge in view.data_edges() {
        if !budget.charge() {
          break
        }
        if edge.kind == @txn.ScopedWWItem ||
          (parameters == Json("ww-and-rw") && edge.kind == @txn.ScopedRWItem) {
          edges.push(edge)
        }
      }
      Ok({ data_edges: edges, order_edges: [], gaps: [], })
    },
    parameters=Json(mode),
    algorithm=Some("example-version-constraints-1"),
  ).unwrap()
}

///|
fn main {
  let raw =
    #|{"traceSchema":3,"dataModel":"point-register-v1","clockDomain":"registered-module-example","scope":{"exclusiveWriters":true},"gaps":[],"events":[
    #|{"seq":1,"time":0,"kind":"snapshot","consistent":true,"initial":{"x":"x0"}},
    #|{"seq":2,"time":1,"kind":"begin","tx":"A","connection":"physical-A"},
    #|{"seq":3,"time":2,"kind":"read","tx":"A","key":"x","version":"x0"},
    #|{"seq":4,"time":3,"kind":"write","tx":"A","key":"x","version":"x1","predecessor":"x0"},
    #|{"seq":5,"time":4,"kind":"commit_request","tx":"A"},
    #|{"seq":6,"time":5,"kind":"commit_ok","tx":"A"},
    #|{"seq":7,"time":6,"kind":"begin","tx":"B","connection":"physical-B"},
    #|{"seq":8,"time":7,"kind":"read","tx":"B","key":"x","version":"x1"},
    #|{"seq":9,"time":8,"kind":"write","tx":"B","key":"x","version":"x2","predecessor":"x1"},
    #|{"seq":10,"time":9,"kind":"commit_request","tx":"B"},
    #|{"seq":11,"time":10,"kind":"commit_ok","tx":"B"}]}
  let facts = @txn.model_facts_v4(@txn.parse_history_v4(raw).unwrap()).unwrap()
  let options = @txn.model_options_v4(models=[@txn.ElleSerializable]).unwrap()
  let readers = original_read_sources()
  let versions = original_version_constraints("ww-and-rw")
  let builtin_readers = @txn.builtin_inference_module_v4(
    @txn.InferenceReadSources,
  )
  let builtin_versions = @txn.builtin_inference_module_v4(
    @txn.InferenceGivenVersions,
  )
  let modules = [readers, versions, builtin_readers, builtin_versions]
  let report = @txn.inference_classification_v4_json(
    @txn.classify_with_inference_v4(
      facts,
      modules,
      options~,
      max_inference_checks=1000000,
    ).unwrap(),
  )
  let compatible = match report {
    Object(fields) => fields.get("status") == Some(Json("checked-compatible"))
    _ => false
  }
  if !compatible ||
    !@txn.verify_with_inference_v4(
      facts,
      report,
      modules,
      options~,
      max_inference_checks=1000000,
    ) {
    abort("The original-source composition must independently verify")
  }
  let changed = [
    readers,
    original_version_constraints("ww-only"),
    builtin_readers,
    builtin_versions,
  ]
  if @txn.verify_with_inference_v4(facts, report, changed, options~) ||
    @txn.verify_with_inference_v4(facts, report, [readers], options~) ||
    @txn.verify_with_inference_v4(
      facts,
      report,
      modules,
      options~,
      max_inference_checks=0,
    ) {
    abort("A verifier must enforce its own selected modules and budget")
  }
  println(
    "registered modules: serializable checked-compatible; two independent modules and builtins verified",
  )
  println(
    "verification policy: changed module, removed modules and changed budget rejected",
  )
}
