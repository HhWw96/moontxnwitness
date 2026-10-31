///|
pub struct SQLCandidateCheckV1 {
  priv record : Json
}

///|
pub fn sql_candidate_check_v1_json(result : SQLCandidateCheckV1) -> Json {
  v4_json_copy(result.record)
}

///|
fn sql_input_candidate_v1(
  config : SQLConfigV1,
  source : String,
  parameters : Json,
  descriptor : Json,
  bindings : Json,
) -> Json {
  {
    "format": "moontxnwitness-sql-binding-candidate/v1",
    "descriptor": descriptor,
    "bindings": bindings,
    "configSha256": Json(config.digest),
    "sqlSha256": Json(v3_dislock_sha256(source)),
    "parametersSha256": Json(v3_dislock_sha256(sql_canonical_v1(parameters))),
  }
}

///|
fn sql_check_work_v1(
  config : SQLConfigV1,
  source : String,
  parameters : Json,
  candidate : Json?,
  options : SQLVerificationOptionsV1,
) -> SQLCandidateCheckV1 {
  let work : SQLParseWorkV1 = {
    config,
    options,
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
  let mut expected : Json = Json::null()
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
    if !sql_well_formed_utf16_v1(source) {
      fail("invalid:SQL-Unicode")
    }
    if orm_utf8_size(source) > options.max_sql_bytes ||
      orm_utf8_size(source) > config.limits.at("max_sql_bytes") {
      fail("budget:SQL-bytes")
    }
    sql_charge_v1(work)
    sql_lex_v1(work, source)
    descriptor = work.descriptor(source)
    bindings = work.bindings(parameters)
    expected = sql_input_candidate_v1(
      config, source, parameters, descriptor, bindings,
    )
    match candidate {
      None => "recognized"
      Some(actual) =>
        if sql_canonical_v1(actual) == sql_canonical_v1(expected) {
          "matched"
        } else {
          reason = "candidate differs from independent grammar, configuration or original parameter binding"
          "mismatch"
        }
    }
  } catch {
    error => {
      reason = error.to_string()
      if reason.contains("invalid:") {
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
      "format": "moontxnwitness-sql-candidate-verification/v1",
      "semanticContract": "moonbit-independent-configured-sql/v1",
      "algorithm": "moonbit-configured-single-table-grammar-1",
      "status": Json(status),
      "valid": Json(status == "matched" || status == "recognized"),
      "grammarVerified": Json(status == "matched" || status == "recognized"),
      "candidateCompared": Json(candidate is Some(_)),
      "captureFactsProduced": false,
      "actualDriverResultsVerified": false,
      "sourceWindowVerified": false,
      "sourceAuthenticated": false,
      "scope": "independent configured SQL grammar and supplied parameter-claim consistency only; not SQL execution, same-statement read-version provenance, complete fetch or isolation analysis",
      "descriptor": descriptor,
      "bindings": bindings,
      "expectedCandidate": expected,
      "gaps": if status == "matched" || status == "recognized" {
        []
      } else {
        [Json(reason)]
      },
      "execution": {
        "counterContract": "configured-sql-lexer-parser-step-checks-1",
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
        "astBudgetScope": "conservative two units per lexical token plus root accounting, not SQLGlot AST counter equivalence",
      },
    },
  }
}

///|
pub fn normalize_sql_candidate_v1(
  config : SQLConfigV1,
  source : String,
  parameters : Json,
  options~ : SQLVerificationOptionsV1 = sql_verification_options_v1(),
) -> SQLCandidateCheckV1 {
  sql_check_work_v1(config, source, parameters, None, options)
}

///|
pub fn verify_sql_candidate_v1(
  config : SQLConfigV1,
  source : String,
  parameters : Json,
  candidate : Json,
  options~ : SQLVerificationOptionsV1 = sql_verification_options_v1(),
) -> SQLCandidateCheckV1 {
  sql_check_work_v1(config, source, parameters, Some(candidate), options)
}

///|
fn sql_wire_options_v1(text : String) -> SQLVerificationOptionsV1 raise {
  let fields = object_fields(
    sql_json_v1(text, 8192),
    "SQL verification options",
  )
  known_fields(
    fields,
    ["maxChecks", "maxTokens", "maxSqlBytes"],
    "SQL verification options",
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
  sql_verification_options_v1(
    max_checks=integer("maxChecks", 1000000, 1000000),
    max_tokens=integer("maxTokens", 8192, 32768),
    max_sql_bytes=integer("maxSqlBytes", 65536, 1048576),
  )
}

///|
fn sql_wire_error_v1(reason : String) -> String {
  (
    {
      "format": "moontxnwitness-sql-candidate-verification/v1",
      "status": "invalid",
      "valid": false,
      "captureFactsProduced": false,
      "sourceAuthenticated": false,
      "gaps": [Json(reason)],
    } : Json).stringify(indent=2)
}

///|
pub fn normalize_configured_sql_v1_json(
  config_text : String,
  source : String,
  parameters_text : String,
  options_text : String,
) -> String {
  try {
    let config = match parse_sql_config_v1(config_text) {
      Ok(config) => config
      Err(reason) => fail(reason)
    }
    let options = sql_wire_options_v1(options_text)
    sql_candidate_check_v1_json(
      normalize_sql_candidate_v1(
        config,
        source,
        sql_json_v1(parameters_text, 1048576),
        options~,
      ),
    ).stringify(indent=2)
  } catch {
    error => sql_wire_error_v1(error.to_string())
  }
}

///|
pub fn verify_configured_sql_v1_json(
  config_text : String,
  source : String,
  parameters_text : String,
  candidate_text : String,
  options_text : String,
) -> String {
  try {
    let config = match parse_sql_config_v1(config_text) {
      Ok(config) => config
      Err(reason) => fail(reason)
    }
    let options = sql_wire_options_v1(options_text)
    sql_candidate_check_v1_json(
      verify_sql_candidate_v1(
        config,
        source,
        sql_json_v1(parameters_text, 1048576),
        sql_json_v1(candidate_text, 8388608),
        options~,
      ),
    ).stringify(indent=2)
  } catch {
    error => sql_wire_error_v1(error.to_string())
  }
}

///|
/// Comparison helper only. PostgreSQL encoding/collation/catalog proof is external.
pub fn compare_configured_c_text_v1(a : String, b : String) -> Int32 {
  relation_v3_text_compare(a, b)
}

///|
pub fn normalize_sql_config_v1_json(text : String) -> String {
  match parse_sql_config_v1(text) {
    Err(reason) => sql_wire_error_v1(reason)
    Ok(config) =>
      (
        {
          "valid": true,
          "config": config.record,
          "canonicalText": Json(sql_canonical_v1(config.record)),
          "configSha256": Json(config.digest),
        } : Json).stringify()
  }
}
