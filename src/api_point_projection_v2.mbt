///|
fn point_projection_options_wire_v2(
  config : SQLConfigV2,
  text : String,
) -> PointProjectionOptionsV2 raise {
  let fields = object_fields(
    sql_json_v1(text, 524288),
    "independent projection options",
  )
  known_fields(
    fields,
    [
      "config", "versionColumn", "versionType", "starContract", "businessStarColumns",
      "maxProjectedSqlBytes", "maxDescriptorBytes",
    ],
    "independent projection options",
  )
  match fields.get("config") {
    None => ()
    Some(value) => {
      let supplied = match parse_sql_config_v2(value.stringify()) {
        Ok(value) => value
        Err(reason) => fail("invalid:projection-options-config:" + reason)
      }
      if sql_canonical_v1(supplied.record) != sql_canonical_v1(config.record) {
        fail("invalid:independent-projection-config-conflict")
      }
    }
  }
  let version_column = sql_string_v1(
    fields.get_or_default("versionColumn", Json("__mtw_source_version")),
  )
  let version_type = sql_string_v1(
    fields.get_or_default("versionType", Json("int64")),
  )
  let star_contract = match fields.get("starContract") {
    None | Some(Null) => None
    Some(value) => Some(sql_string_v1(value))
  }
  let columns = match fields.get("businessStarColumns") {
    None | Some(Null) => None
    Some(value) => Some(orm_array(value).map(item => sql_string_v1(item)))
  }
  fn limit(name : String, fallback : Int32, maximum : Int32) -> Int32 raise {
    match fields.get(name) {
      None => fallback
      Some(value) => {
        let number = fetch_number_v1(value, maximum)
        if number < 1 {
          fail("invalid:projection-options-byte-limits")
        }
        number
      }
    }
  }
  let sql_limit = limit("maxProjectedSqlBytes", 131072, 2097152)
  let descriptor_limit = limit("maxDescriptorBytes", 16777216, 67108864)
  match
    point_projection_options_v2(
      config,
      version_column~,
      version_type~,
      star_contract~,
      business_star_columns=columns,
      max_projected_sql_bytes=sql_limit,
      max_descriptor_bytes=descriptor_limit,
    ) {
    Ok(options) => options
    Err(reason) => fail(reason)
  }
}

///|
fn point_projection_budget_wire_v2(
  text : String,
) -> PointProjectionVerificationOptionsV2 raise {
  let fields = object_fields(
    sql_json_v1(text, 8192),
    "projection verification budget",
  )
  known_fields(
    fields,
    ["maxChecks", "grammarOptions"],
    "projection verification budget",
  )
  point_projection_verification_options_v2(
    max_checks=match fields.get("maxChecks") {
      None => 1000000
      Some(value) => fetch_number_v1(value, 1000000)
    },
    grammar_options=match fields.get("grammarOptions") {
      None => sql_verification_options_v2()
      Some(value) => sql_wire_options_v2(value.stringify())
    },
  )
}

///|
pub fn verify_point_projection_v2_json(
  config_text : String,
  source : String,
  typed_parameters_text : String,
  independent_options_text : String,
  supplied_descriptor_text : String,
  budget_text : String,
) -> String {
  try {
    let config = match parse_sql_config_v2(config_text) {
      Ok(value) => value
      Err(reason) => fail(reason)
    }
    let options = point_projection_options_wire_v2(
      config, independent_options_text,
    )
    let budget = point_projection_budget_wire_v2(budget_text)
    point_projection_check_v2_json(
      verify_point_projection_v2(
        config,
        source,
        sql_json_v1(typed_parameters_text, 1048576),
        options,
        sql_json_v1(supplied_descriptor_text, options.max_descriptor_bytes),
        budget~,
      ),
    ).stringify()
  } catch {
    error =>
      (
        {
          "format": "moontxnwitness-point-projection-verification/v2",
          "status": Json(
            if error.to_string().contains("budget:") {
              "unknown"
            } else {
              "invalid"
            },
          ),
          "valid": false,
          "descriptorRecomputed": false,
          "databaseExecuted": false,
          "databaseSyntaxValidated": false,
          "sourceAuthenticated": false,
          "captureFactsProduced": false,
          "sourceFactsProduced": false,
          "completeWindow": false,
          "modelCoverageAccepted": false,
          "moonbitProjectionVerified": false,
          "commitVerified": false,
          "gaps": [Json(error.to_string())],
        } : Json).stringify()
  }
}
