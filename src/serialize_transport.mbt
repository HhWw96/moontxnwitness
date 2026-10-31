///|
/// The compact report is shared by both transport fields. Keep the full report
/// and presentation while avoiding a second materialized edge JSON object tree.
/// Escaping remains the standard Json string serializer on every target.
fn report_transport_string(
  report : Report,
  format : String,
  extras~ : Map[String, Json] = Map([]),
) -> String {
  let encoded = report_string(report, extras~)
  let output = if format == "json" {
    encoded + "\n"
  } else {
    render_report(report, format)
  }
  let builder = StringBuilder()
  builder.write_string("{\"report\":")
  builder.write_string(encoded)
  builder.write_string(",\"output\":")
  builder.write_string(Json(output).stringify())
  builder.write_string(",\"exitCode\":")
  builder.write_string(exit_code(report.outcome).to_string())
  builder.write_char('}')
  builder.to_string()
}
