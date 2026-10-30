///|
/// Transport bindings are checked here without treating a mapping name or a
/// self-described installation as proof of SQL semantics.
fn v3_sql_profiles(
  root : Map[String, Json],
  gaps : Array[Json],
  verified : Map[String, Bool],
) -> Unit raise {
  match root.get("sqlProfiles") {
    None => ()
    Some(value) => {
      let profiles = presence_capture_array(value, "sqlProfiles")
      if profiles.length() > 16 {
        fail("At most 16 SQL profiles are supported")
      }
      let names : Map[String, Bool] = Map([])
      for value in profiles {
        let profile = object_fields(value, "SQL profile")
        known_fields(
          profile,
          [
            "profile", "schema", "table", "knownKeys", "metadata", "effectLedger",
            "initialState",
          ],
          "SQL profile",
        )
        let name = identifier(
          required(profile, "profile", "SQL profile"),
          "SQL profile.profile",
        )
        let schema = identifier(
          required(profile, "schema", "SQL profile"),
          "SQL profile.schema",
        )
        let table = identifier(
          required(profile, "table", "SQL profile"),
          "SQL profile.table",
        )
        let identity = Json([Json(name), Json(schema), Json(table)]).stringify()
        if names.contains(identity) {
          fail("Duplicate SQL profile installation")
        }
        names[identity] = true
        let keys = presence_capture_array(
          required(profile, "knownKeys", "SQL profile"),
          "SQL profile.knownKeys",
        )
        if keys.length() > 10000 {
          fail("At most 10,000 SQL profile keys are supported")
        }
        let unique : Map[String, Bool] = Map([])
        for value in keys {
          let key = identifier(value, "SQL profile key")
          if unique.contains(key) {
            fail("SQL profile keys must be unique")
          }
          unique[key] = true
        }
        let _ = object_fields(
          required(profile, "metadata", "SQL profile"),
          "SQL profile.metadata",
        )
        for field in ["effectLedger", "initialState"] {
          match profile.get(field) {
            Some(value) => {
              let items = presence_capture_array(value, "SQL profile." + field)
              if items.length() > 10000 {
                fail("SQL profile evidence exceeds 10,000 rows")
              }
              for row in items {
                let _ = object_fields(row, "SQL profile evidence row")
              }
            }
            None => ()
          }
        }
        if !verified.contains(identity) {
          gaps.push(
            capture_gap(
              "unverified_sql_profile", "Installation metadata and source ledgers are retained but not yet independently proved by this algorithm",
            ),
          )
        }
      }
    }
  }
}

///|
fn v3_sql_statement_metadata(event : Map[String, Json]) -> Unit raise {
  match (event.get("mappingId"), event.get("executedSql")) {
    (None, None) => ()
    (Some(value), Some(String(_))) => {
      let _ = identifier(value, "statement.mappingId")
    }
    _ => fail("A statement mapping needs both mappingId and executedSql text")
  }
}

///|
fn v3_sql_fact_metadata(
  event : Map[String, Json],
  seq : Int64,
  tx : String,
  statements : Map[Int64, String],
  gaps : Array[Json],
  verified : Bool,
) -> Unit raise {
  match
    (event.get("statement"), event.get("mappingId"), event.get("evidence")) {
    (None, None, None) => ()
    (Some(value), Some(mapping), Some(proof)) => {
      let statement = v3_capture_seq(value, "fact.statement")
      if statement >= seq || statements.get(statement) != Some(tx) {
        fail(
          "A SQL fact must bind a preceding statement in the same transaction",
        )
      }
      let _ = identifier(mapping, "fact.mappingId")
      let _ = object_fields(proof, "fact.evidence")
      if !verified {
        gaps.push(
          capture_gap(
            "unverified_sql_mapping", "A transport-bound SQL fact still requires independently validated SQL, results and source evidence",
          ),
        )
      }
    }
    _ => fail("A SQL fact needs statement, mappingId and evidence together")
  }
}

///|
fn v3_sql_rows_metadata(
  event : Map[String, Json],
  rows : Array[Json],
) -> Unit raise {
  match event.get("serverRows") {
    Some(value) => {
      let server = presence_capture_array(value, "rows.serverRows")
      if server.length() != rows.length() {
        fail("Server and delivered row batches must have equal length")
      }
      for row in server {
        let _ = presence_capture_array(row, "server row")
      }
    }
    None => ()
  }
  match event.get("columns") {
    Some(value) => {
      let columns = presence_capture_array(value, "rows.columns")
      if columns.length() > 64 {
        fail("At most 64 business result columns are supported")
      }
      for value in columns {
        let column = object_fields(value, "result column")
        known_fields(column, ["name", "typeCode"], "result column")
        match required(column, "name", "result column") {
          String(name) if name.length() <= 1024 => ()
          _ => fail("Column names must be bounded text")
        }
        match required(column, "typeCode", "result column") {
          Number(n, ..) if n >= 0.0 &&
            n <= 4294967295.0 &&
            n.to_int64().to_double() == n => ()
          _ => fail("Column typeCode must be a PostgreSQL OID")
        }
      }
      for row in rows {
        if presence_capture_array(row, "delivered row").length() !=
          columns.length() {
          fail("Delivered rows must match the business column description")
        }
      }
    }
    None => ()
  }
  match event.get("error") {
    Some(value) => {
      let error = object_fields(value, "rows.error")
      known_fields(error, ["class", "sqlstate"], "rows.error")
      let _ = identifier(
        required(error, "class", "rows.error"),
        "rows.error.class",
      )
      match required(error, "sqlstate", "rows.error") {
        Null => ()
        String(code) if code.length() == 5 &&
          code.iter().all(c => (c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z')) =>
          ()
        _ => fail("SQLSTATE must be five ASCII letters/digits or null")
      }
    }
    None => ()
  }
}
