///|
fn projected_result_options_wire_v2(
  text : String,
) -> ProjectedResultOptionsV2 raise {
  let fields = object_fields(
    sql_json_v1(text, 16384),
    "projected result options",
  )
  known_fields(
    fields,
    [
      "maxChecks", "maxCellBytes", "maxTotalBytes", "maxDeliveryRecords", "projectionBudget",
    ],
    "projected result options",
  )
  fn limit(name : String, fallback : Int32, ceiling : Int32) -> Int32 raise {
    match fields.get(name) {
      None => fallback
      Some(value) =>
        fetch_number_v1(value, ceiling) catch {
          _ => fail("invalid:projected-result-option-range")
        }
    }
  }
  projected_result_options_v2(
    max_checks=limit("maxChecks", 1000000, 1000000),
    max_cell_bytes=limit("maxCellBytes", 65536, 65536),
    max_total_bytes=limit("maxTotalBytes", 262144, 1048576),
    max_delivery_records=limit("maxDeliveryRecords", 1024, 1024),
    projection_budget=match fields.get("projectionBudget") {
      None => point_projection_verification_options_v2()
      Some(value) =>
        point_projection_budget_wire_v2(value.stringify()) catch {
          _ => fail("invalid:projected-projection-budget-options")
        }
    },
  )
}

///|
pub fn verify_projected_result_v2_json(
  config_text : String,
  source : String,
  typed_parameters_text : String,
  independent_projection_options_text : String,
  supplied_descriptor_text : String,
  native_frame_text : String,
  deliveries_text : String,
  options_text : String,
) -> String {
  try {
    let config = match parse_sql_config_v2(config_text) {
      Ok(config) => config
      Err(reason) => fail("invalid:" + reason)
    }
    let independent_projection_options = point_projection_options_wire_v2(
      config, independent_projection_options_text,
    )
    let options = projected_result_options_wire_v2(options_text)
    projected_result_check_v2_json(
      verify_projected_result_v2(
        config,
        source,
        sql_json_v1(typed_parameters_text, 1048576),
        independent_projection_options,
        sql_json_v1(
          supplied_descriptor_text,
          independent_projection_options.max_descriptor_bytes,
        ),
        sql_json_v1(native_frame_text, 2097152),
        sql_json_v1(deliveries_text, 4194304),
        options~,
      ),
    ).stringify()
  } catch {
    error =>
      (
        {
          "format": "moontxnwitness-projected-result-verification/v2",
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
          "nativeResultVerified": false,
          "rowImageConsistencyVerified": false,
          "databaseExecuted": false,
          "databaseSyntaxValidated": false,
          "sourceFactsProduced": false,
          "captureFactsProduced": false,
          "sourceAuthenticated": false,
          "catalogVerified": false,
          "sourceColumnMappingVerified": false,
          "completeWindow": false,
          "sourceWindowVerified": false,
          "modelCoverageAccepted": false,
          "commitVerified": false,
          "committedWriteEffectVerified": false,
          "moonbitProjectionVerified": false,
          "absenceSourceVerified": false,
          "gaps": [Json(error.to_string())],
        } : Json).stringify()
  }
}
