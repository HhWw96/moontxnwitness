///|
/// Opt-in policy is an execution choice, never a collected database fact.
fn v3_sql_proof_requested(options : Map[String, Json]) -> Bool raise {
  match options.get("sqlProof") {
    None => false
    Some(String("dislock-f9946f0-sql-proof-1")) => true
    _ => fail("Unsupported v3 SQL proof policy")
  }
}

///|
fn v3_register_options(text : String) -> (AnalysisOptions, Bool) raise {
  let raw = object_fields(guarded_json(text, limit=4096), "v3 options")
  let requested = v3_sql_proof_requested(raw)
  let ordinary : Map[String, Json] = Map([])
  for key, value in raw {
    if key != "sqlProof" {
      ordinary[key] = value
    }
  }
  (parse_analysis_options(Json::object(ordinary).stringify()), requested)
}

///|
fn v3_sql_proof_evidence(
  proof : V3DislockSQLProof,
  root : Map[String, Json],
) -> Json {
  let statements : Array[Int64] = []
  let facts : Array[Int64] = []
  let profiles : Array[String] = []
  for seq, _ in proof.verified_statements {
    statements.push(seq)
  }
  for seq, _ in proof.verified_facts {
    facts.push(seq)
  }
  for name, _ in proof.verified_profiles {
    profiles.push(name)
  }
  statements.sort()
  facts.sort()
  profiles.sort()
  {
    "policy": "dislock-f9946f0-sql-proof-1",
    "verifiedStatements": statements.map(seq => seq.to_double()).to_json(),
    "verifiedFacts": facts.map(seq => seq.to_double()).to_json(),
    "verifiedProfiles": profiles.to_json(),
    "gaps": proof.gaps.to_json(),
    "profileEvidence": root.get_or_default("sqlProfiles", Json::array([])),
    "scope": "Semantic validation of supplied SQL and source observations; no database authenticity or unobserved-writer claim",
  }
}

///|
pub fn normalize_capture_v3_options_json(
  text : String,
  options_text : String,
) -> String {
  try {
    let options = object_fields(
      guarded_json(options_text, limit=4096),
      "normalization options",
    )
    known_fields(options, ["sqlProof"], "normalization options")
    let requested = v3_sql_proof_requested(options)
    if v3_is_list_capture(text) {
      if requested {
        fail("The dislock SQL proof cannot be mixed with append-list-v1")
      }
      normalize_list_capture_v3_json(text)
    } else {
      normalize_register_capture_v3_json(text, use_sql_proof=requested)
    }
  } catch {
    error => {
      let result : Json = {
        "schema": 3,
        "algorithm": "v3-lifecycle-sql-1",
        "status": "invalid",
        "coverage": {
          "complete": false,
          "gaps": [capture_gap("invalid_sql_proof_options", error.to_string())],
        },
        "observations": Json::null(),
        "effects": [],
        "transactions": [],
        "history": Json::null(),
        "error": error.to_string().to_json(),
      }
      result.stringify(indent=2)
    }
  }
}
