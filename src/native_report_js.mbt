///|
/// A host object, not the representation of MoonBit Json, Option, Map or Array.
#cfg(target="js")
#external
pub type NativeReportObject

///|
#cfg(target="js")
extern "js" fn native_report_metadata(text : String) -> NativeReportObject =
  #| (text) => JSON.parse(text)

///|
/// Each optional field has a primitive presence flag. Even Some("") and Some(0)
/// are distinct from None, without exposing the Option ABI to JavaScript.
#cfg(target="js")
extern "js" fn native_report_append_edge(
  report : NativeReportObject,
  from : String,
  to : String,
  kind : String,
  has_key : Bool,
  key : String,
  has_from_op : Bool,
  from_op : Int32,
  has_to_op : Bool,
  to_op : Int32,
  has_from_version : Bool,
  from_version : String,
  has_to_version : Bool,
  to_version : String,
  reason : String,
) -> Unit =
  #| (report, from, to, kind, hasKey, key, hasFromOp, fromOp, hasToOp, toOp, hasFromVersion, fromVersion, hasToVersion, toVersion, reason) => {
  #|   report.edges.push({from, to, kind, key: hasKey ? key : null,
  #|     fromOp: hasFromOp ? fromOp : null, toOp: hasToOp ? toOp : null,
  #|     fromVersion: hasFromVersion ? fromVersion : null,
  #|     toVersion: hasToVersion ? toVersion : null, reason});
  #| }

///|
#cfg(target="js")
fn native_report_object(
  report : Report,
  extras~ : Map[String, Json] = Map([]),
) -> NativeReportObject {
  // This newly created metadata JSON contains complete findings, coverage,
  // version orders and witness. Only the largest top-level edge array is typed.
  let metadata = report_json({ ..report, edges: [], })
  match metadata {
    Object(fields) => {
      for name, value in extras {
        fields[name] = value
      }
      match fields.at("stats") {
        Object(stats) => stats["dependencies"] = Json(report.edges.length())
        _ => abort("Report stats")
      }
    }
    _ => abort("Report object")
  }
  let result = native_report_metadata(metadata.stringify())
  for edge in report.edges {
    native_report_append_edge(
      result,
      edge.from,
      edge.to,
      dependency_label(edge.kind),
      edge.key is Some(_),
      edge.key.unwrap_or(""),
      edge.from_op is Some(_),
      edge.from_op.unwrap_or(0),
      edge.to_op is Some(_),
      edge.to_op.unwrap_or(0),
      edge.from_version is Some(_),
      edge.from_version.unwrap_or(""),
      edge.to_version is Some(_),
      edge.to_version.unwrap_or(""),
      edge.reason,
    )
  }
  result
}

///|
/// Experimental JS transport. Input validation and analysis are unchanged.
#cfg(target="js")
pub fn analyze_native_js_v1(text : String) -> NativeReportObject {
  match parse_history(text) {
    Ok(history) => native_report_object(analyze(history))
    Err(message) => native_report_object(input_error_report(message))
  }
}

///|
/// The existing options parser and all effective budgets are reused exactly.
#cfg(target="js")
pub fn analyze_options_native_js_v1(
  text : String,
  options_text : String,
) -> NativeReportObject {
  let result = options_input(text, options_text)
  native_report_object(result.report, extras=analysis_extras(result))
}
