///|
fn result_options_wire_v2(text : String) -> ConfiguredResultOptionsV2 raise {
  let fields = object_fields(sql_json_v1(text, 8192), "V2 result options")
  known_fields(
    fields,
    [
      "maxChecks", "maxCellBytes", "maxTotalBytes", "maxDeliveryRecords", "grammarOptions",
    ],
    "V2 result options",
  )
  fn number(name : String, fallback : Int32, ceiling : Int32) -> Int32 raise {
    match fields.get(name) {
      None => fallback
      Some(value) => fetch_number_v1(value, ceiling)
    }
  }
  configured_result_options_v2(
    max_checks=number("maxChecks", 1000000, 1000000),
    max_cell_bytes=number("maxCellBytes", 65536, 65536),
    max_total_bytes=number("maxTotalBytes", 262144, 1048576),
    max_delivery_records=number("maxDeliveryRecords", 1024, 1024),
    grammar_options=match fields.get("grammarOptions") {
      None => sql_verification_options_v2()
      Some(value) => sql_wire_options_v2(value.stringify())
    },
  )
}

///|
pub fn verify_configured_result_v2_json(
  config_text : String,
  execution_text : String,
  native_text : String,
  deliveries_text : String,
  options_text : String,
) -> String {
  try {
    let config = match parse_sql_config_v2(config_text) {
      Ok(config) => config
      Err(reason) => fail(reason)
    }
    let options = result_options_wire_v2(options_text)
    configured_result_check_v2_json(
      verify_configured_result_v2(
        config,
        sql_json_v1(execution_text, 8388608),
        sql_json_v1(native_text, 2097152),
        sql_json_v1(deliveries_text, 2097152),
        options~,
      ),
    ).stringify()
  } catch {
    error =>
      (
        {
          "format": "moontxnwitness-configured-result-verification/v2",
          "status": Json(
            if error.to_string().contains("budget:") {
              "unknown"
            } else {
              "invalid"
            },
          ),
          "valid": false,
          "completeObservationVerified": false,
          "completeFetchVerified": false,
          "captureFactsProduced": false,
          "sourceFactsProduced": false,
          "sourceAuthenticated": false,
          "catalogVerified": false,
          "sourceWindowVerified": false,
          "sourceColumnMappingVerified": false,
          "modelCoverageAccepted": false,
          "commitVerified": false,
          "committedWriteEffectVerified": false,
          "moonbitProjectionVerified": false,
          "gaps": [Json(error.to_string())],
        } : Json).stringify()
  }
}
