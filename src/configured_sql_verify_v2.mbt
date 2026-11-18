///|
pub struct SQLCandidateCheckV2 {
  priv record : Json
}

///|
pub fn sql_candidate_check_v2_json(result : SQLCandidateCheckV2) -> Json {
  v4_json_copy(result.record)
}

///|
fn sql_check_work_v2(
  config : SQLConfigV2,
  source : String,
  parameters : Json,
  candidate : Json?,
  options : SQLVerificationOptionsV2,
) -> SQLCandidateCheckV2 {
  let work : SQLParseWorkV1 = {
    config: config.parser_config,
    options: sql_verification_options_v1(
      max_checks=options.max_checks,
      max_tokens=options.max_tokens,
      max_sql_bytes=options.max_sql_bytes,
    ),
    tokens: [],
    refs: [],
    pos: 0,
    checks: 0,
    table: None,
    table_alias: None,
    resolution: "",
    style: "",
    stray_percent: false,
  }
  let mut descriptor : Json = Json::null()
  let mut bindings : Json = Json::null()
  let mut parameters_digest : Json = Json::null()
  let mut reason = ""
  let status = try {
    if options.max_checks < 0 ||
      options.max_checks > 1000000 ||
      options.max_tokens < 0 ||
      options.max_tokens > 32768 ||
      options.max_sql_bytes < 0 ||
      options.max_sql_bytes > 1048576 {
      fail("invalid:caller-budget")
    }
    if !sql_well_formed_utf16_v1(source) || source.contains("\u0000") {
      fail("invalid:SQL-Unicode-or-NUL")
    }
    if orm_utf8_size(source) > options.max_sql_bytes ||
      orm_utf8_size(source) > config.parser_config.limits.at("max_sql_bytes") {
      fail("budget:SQL-bytes")
    }
    sql_charge_v1(work)
    sql_lex_shared_v1(work, source, true)
    descriptor = sql_descriptor_v2(work, config, source)
    bindings = sql_bindings_v2(work, parameters)
    let canonical_parameters = sql_canonical_v1(parameters)
    if orm_utf8_size(canonical_parameters) > 1048576 {
      fail("budget:parameters-bytes")
    }
    parameters_digest = Json(v3_dislock_sha256(canonical_parameters))
    match candidate {
      None => "recognized"
      Some(actual) => {
        let canonical_candidate = sql_canonical_v1(actual)
        if orm_utf8_size(canonical_candidate) > 8388608 {
          fail("budget:candidate-bytes")
        }
        if canonical_candidate == sql_canonical_v1(descriptor) {
          "matched"
        } else {
          reason = "V2 candidate differs from independent config, original SQL or bind-reference projection"
          "mismatch"
        }
      }
    }
  } catch {
    error => {
      reason = error.to_string()
      if reason.contains("budget:") {
        "unknown"
      } else if reason.contains("invalid:") {
        "invalid"
      } else if reason.contains("mismatch:") || reason.contains("parameter:") {
        "mismatch"
      } else {
        "unknown"
      }
    }
  }
  {
    record: {
      "format": "moontxnwitness-sql-candidate-verification/v2",
      "semanticContract": "moonbit-independent-configured-point-crud/v2",
      "algorithm": "moonbit-configured-point-crud-grammar-2",
      "status": Json(status),
      "valid": Json(status == "matched" || status == "recognized"),
      "grammarVerified": Json(status == "matched" || status == "recognized"),
      "candidateCompared": Json(candidate is Some(_)),
      "configSha256": Json(config.digest),
      "sqlSha256": Json(v3_dislock_sha256(source)),
      "originalParametersSha256": parameters_digest,
      "originalParameters": v4_json_copy(parameters),
      "descriptor": descriptor,
      "bindings": bindings,
      "databaseSyntaxValidated": false,
      "captureFactsProduced": false,
      "sourceFactsProduced": false,
      "actualDriverResultsVerified": false,
      "sourceWindowVerified": false,
      "sourceAuthenticated": false,
      "modelCoverageAccepted": false,
      "moonbitProjectionVerified": false,
      "scope": "independent V2 point-CRUD grammar and supplied original parameter consistency only; source, execution, absence, complete-fetch and model facts remain unproved",
      "gaps": if status == "matched" || status == "recognized" {
        []
      } else {
        [Json(reason)]
      },
      "requiredSourceProofs": [
        "catalog-and-session", "actual-success-and-complete-delivery", "observed-unique-read-version",
        "initialized-dynamic-absence-and-complete-window", "effective-writes-and-rollback-journal",
        "model-projection-and-coverage",
      ],
      "execution": {
        "counterContract": "configured-point-crud-lexer-parser-step-checks-2",
        "checks": Json(work.checks),
        "tokens": Json(
          if !work.tokens.is_empty() &&
            work.tokens[work.tokens.length() - 1].kind == "eof" {
            work.tokens.length() - 1
          } else {
            work.tokens.length()
          },
        ),
        "limits": {
          "maxChecks": Json(options.max_checks),
          "maxTokens": Json(options.max_tokens),
          "maxSqlBytes": Json(options.max_sql_bytes),
        },
        "astBudgetScope": "conservative two units per lexical token plus root; not SQLGlot AST equivalence",
      },
    },
  }
}

///|
pub fn normalize_sql_candidate_v2(
  config : SQLConfigV2,
  source : String,
  parameters : Json,
  options~ : SQLVerificationOptionsV2 = sql_verification_options_v2(),
) -> SQLCandidateCheckV2 {
  sql_check_work_v2(config, source, parameters, None, options)
}

///|
pub fn verify_sql_candidate_v2(
  config : SQLConfigV2,
  source : String,
  parameters : Json,
  candidate : Json,
  options~ : SQLVerificationOptionsV2 = sql_verification_options_v2(),
) -> SQLCandidateCheckV2 {
  sql_check_work_v2(config, source, parameters, Some(candidate), options)
}

///|
fn sql_wire_options_v2(text : String) -> SQLVerificationOptionsV2 raise {
  let fields = object_fields(sql_json_v1(text, 8192), "V2 verification options")
  known_fields(
    fields,
    ["maxChecks", "maxTokens", "maxSqlBytes"],
    "V2 verification options",
  )
  fn integer(name : String, fallback : Int32, ceiling : Int32) -> Int32 raise {
    match fields.get(name) {
      None => fallback
      Some(value) => {
        let digits = sql_number_text_v1(value)
        if !sql_digits_v1(digits) || digits.length() > 7 {
          fail("invalid:caller-budget")
        }
        let mut number = 0
        for c in digits.to_array() {
          number = number * 10 + c.to_int() - 48
        }
        if number > ceiling {
          fail("invalid:caller-budget")
        }
        number
      }
    }
  }
  sql_verification_options_v2(
    max_checks=integer("maxChecks", 1000000, 1000000),
    max_tokens=integer("maxTokens", 8192, 32768),
    max_sql_bytes=integer("maxSqlBytes", 65536, 1048576),
  )
}

///|
fn sql_wire_error_v2(reason : String) -> String {
  (
    {
      "format": "moontxnwitness-sql-candidate-verification/v2",
      "status": Json(
        if reason.contains("budget:") {
          "unknown"
        } else {
          "invalid"
        },
      ),
      "valid": false,
      "grammarVerified": false,
      "databaseSyntaxValidated": false,
      "captureFactsProduced": false,
      "sourceFactsProduced": false,
      "sourceAuthenticated": false,
      "modelCoverageAccepted": false,
      "moonbitProjectionVerified": false,
      "actualDriverResultsVerified": false,
      "sourceWindowVerified": false,
      "gaps": [Json(reason)],
    } : Json).stringify(indent=2)
}

///|
pub fn normalize_configured_sql_v2_json(
  config_text : String,
  source : String,
  parameters_text : String,
  options_text : String,
) -> String {
  try {
    let config = match parse_sql_config_v2(config_text) {
      Ok(config) => config
      Err(reason) => fail(reason)
    }
    let options = sql_wire_options_v2(options_text)
    sql_candidate_check_v2_json(
      normalize_sql_candidate_v2(
        config,
        source,
        sql_json_v1(parameters_text, 1048576),
        options~,
      ),
    ).stringify(indent=2)
  } catch {
    error => sql_wire_error_v2(error.to_string())
  }
}

///|
pub fn verify_configured_sql_v2_json(
  config_text : String,
  source : String,
  parameters_text : String,
  candidate_text : String,
  options_text : String,
) -> String {
  try {
    let config = match parse_sql_config_v2(config_text) {
      Ok(config) => config
      Err(reason) => fail(reason)
    }
    let options = sql_wire_options_v2(options_text)
    sql_candidate_check_v2_json(
      verify_sql_candidate_v2(
        config,
        source,
        sql_json_v1(parameters_text, 1048576),
        sql_json_v1(candidate_text, 8388608),
        options~,
      ),
    ).stringify(indent=2)
  } catch {
    error => sql_wire_error_v2(error.to_string())
  }
}

///|
pub fn normalize_sql_config_v2_json(text : String) -> String {
  match parse_sql_config_v2(text) {
    Err(reason) => sql_wire_error_v2(reason)
    Ok(config) =>
      (
        {
          "format": "moontxnwitness-sql-config-normalization/v2",
          "valid": true,
          "config": config.record,
          "canonicalText": Json(sql_canonical_v1(config.record)),
          "configSha256": Json(config.digest),
          "captureFactsProduced": false,
          "sourceFactsProduced": false,
          "sourceAuthenticated": false,
          "modelCoverageAccepted": false,
        } : Json).stringify()
  }
}
