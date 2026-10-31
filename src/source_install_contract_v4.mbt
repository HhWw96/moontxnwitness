///|
priv struct SourcePolicyV4 {
  source_schema : String
  writers : Array[String]
  max_initial : Int32
  max_log_bytes : Int32
  record : Json
}

///|
fn source_policy_v4(value : Json) -> SourcePolicyV4 raise {
  let p = orm_exact(value, [
    "namespace", "writers", "maxInitialRows", "maxLogBytes",
  ])
  let source_schema = sql_identifier_v1(p.at("namespace"))
  if !source_schema.has_prefix("mtw_source_") {
    fail("mismatch:explicit-source-namespace")
  }
  let writers : Array[String] = []
  for raw in orm_array(p.at("writers")) {
    let writer = sql_identifier_v1(raw)
    if writers.contains(writer) {
      fail("mismatch:duplicate-writer")
    }
    writers.push(writer)
  }
  if writers.is_empty() || writers.length() > 16 {
    fail("unsupported:writer-count")
  }
  let max_initial = fetch_number_v1(p.at("maxInitialRows"), 16384)
  let max_log_bytes = fetch_number_v1(p.at("maxLogBytes"), 67108864)
  if max_initial < 1 || max_log_bytes < 1048576 {
    fail("mismatch:source-policy-limits")
  }
  {
    source_schema,
    writers,
    max_initial,
    max_log_bytes,
    record: v4_json_copy(value),
  }
}

///|
fn source_literal_v4(value : String) -> String {
  "'" + value.replace_all(old="'", new="''") + "'"
}

///|
fn source_target_v4(table : SQLTableV1) -> String raise {
  v3_dislock_quote(table.schema) + "." + v3_dislock_quote(table.name)
}

///|
fn source_functions_v4(policy : SourcePolicyV4) -> (String, String) raise {
  let q = v3_dislock_quote(policy.source_schema)
  let v = "\"__mtw_source_version\""
  let seq = source_literal_v4(q + ".versions")
  let roles = "ARRAY[" +
    policy.writers.map(source_literal_v4).join(",") +
    "]::text[]"
  let guard_sql = "IF NOT (SESSION_USER::text COLLATE pg_catalog.\"C\" = ANY(" +
    roles +
    ")) THEN RAISE EXCEPTION 'writer login outside source scope' USING ERRCODE='42501'; END IF; " +
    "IF NOT EXISTS(SELECT 1 FROM " +
    q +
    ".scope WHERE relation_oid=TG_RELID AND primary_key=TG_ARGV[0]) THEN RAISE EXCEPTION 'relation outside source scope' USING ERRCODE='42501'; END IF; "
  let before = "BEGIN " +
    guard_sql +
    "NEW." +
    v +
    " := pg_catalog.nextval(" +
    seq +
    "::pg_catalog.regclass); RETURN NEW; END;"
  let after = "DECLARE v bigint; b bigint; k jsonb; oldk jsonb; vals jsonb; BEGIN " +
    guard_sql +
    "IF TG_OP='DELETE' THEN v:=pg_catalog.nextval(" +
    seq +
    "::pg_catalog.regclass); b:=OLD." +
    v +
    "; k:=pg_catalog.to_jsonb(OLD)->TG_ARGV[0]; oldk:=k; vals:=NULL; " +
    "ELSE v:=NEW." +
    v +
    "; k:=pg_catalog.to_jsonb(NEW)->TG_ARGV[0]; vals:=pg_catalog.to_jsonb(NEW)-'__mtw_source_version'; IF TG_OP='UPDATE' THEN b:=OLD." +
    v +
    "; oldk:=pg_catalog.to_jsonb(OLD)->TG_ARGV[0]; ELSE b:=NULL; oldk:=NULL; END IF; END IF; " +
    "INSERT INTO " +
    q +
    ".effects(version,base_version,relation_oid,operation,writer_xid,writer_login,writer_pid,row_key,old_key,row_values) VALUES(v,b,TG_RELID,TG_OP,pg_catalog.pg_current_xact_id()::text,SESSION_USER,pg_catalog.pg_backend_pid(),k,oldk,vals); RETURN NULL; END;"
  (before, after)
}

///|
fn source_ddl_v4(
  config : SQLConfigV1,
  policy : SourcePolicyV4,
) -> Array[String] raise {
  let q = v3_dislock_quote(policy.source_schema)
  let v = "\"__mtw_source_version\""
  let sequence = source_literal_v4(q + ".versions")
  let (before, after) = source_functions_v4(policy)
  let statements : Array[String] = [
    "CREATE SCHEMA " + q,
    "REVOKE ALL ON SCHEMA " + q + " FROM PUBLIC",
    "CREATE SEQUENCE " + q + ".versions AS bigint NO CYCLE",
    "CREATE TABLE " +
    q +
    ".scope(relation_oid oid PRIMARY KEY, relation_schema text COLLATE pg_catalog.\"C\" NOT NULL, relation_table text COLLATE pg_catalog.\"C\" NOT NULL, primary_key text COLLATE pg_catalog.\"C\" NOT NULL, config_sha256 text COLLATE pg_catalog.\"C\" NOT NULL)",
    "CREATE TABLE " +
    q +
    ".effects(version bigint PRIMARY KEY, base_version bigint, relation_oid oid NOT NULL, operation text NOT NULL, writer_xid text NOT NULL, writer_login text NOT NULL, writer_pid integer NOT NULL, row_key jsonb NOT NULL, old_key jsonb, row_values jsonb)",
    "CREATE FUNCTION " +
    q +
    ".before_write() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET standard_conforming_strings=on AS " +
    source_literal_v4(before),
    "CREATE FUNCTION " +
    q +
    ".after_write() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET standard_conforming_strings=on AS " +
    source_literal_v4(after),
  ]
  for table in config.tables {
    let t = source_target_v4(table)
    let digest = v3_dislock_sha256(table.schema + "\u0000" + table.name)
    let index = v3_dislock_quote("__mtw_source_idx_" + digest[0:16].to_owned())
    for
      statement in [
        "ALTER TABLE " + t + " ADD COLUMN " + v + " bigint",
        "UPDATE " +
        t +
        " SET " +
        v +
        "=pg_catalog.nextval(" +
        sequence +
        "::pg_catalog.regclass)",
        "ALTER TABLE " + t + " ALTER COLUMN " + v + " SET NOT NULL",
        "CREATE UNIQUE INDEX " + index + " ON " + t + "(" + v + ")",
        "CREATE TRIGGER \"__mtw_source_before\" BEFORE INSERT OR UPDATE ON " +
        t +
        " FOR EACH ROW EXECUTE FUNCTION " +
        q +
        ".before_write(" +
        source_literal_v4(table.key) +
        ")",
        "CREATE TRIGGER \"__mtw_source_after\" AFTER INSERT OR UPDATE OR DELETE ON " +
        t +
        " FOR EACH ROW EXECUTE FUNCTION " +
        q +
        ".after_write(" +
        source_literal_v4(table.key) +
        ")",
        "ALTER TABLE " + t + " ENABLE ALWAYS TRIGGER \"__mtw_source_before\"",
        "ALTER TABLE " + t + " ENABLE ALWAYS TRIGGER \"__mtw_source_after\"",
      ] {
      statements.push(statement)
    }
  }
  let roles = ["PUBLIC"]
  for writer in policy.writers {
    roles.push(v3_dislock_quote(writer))
  }
  for role in roles {
    for category in ["TABLES", "SEQUENCES", "FUNCTIONS"] {
      statements.push(
        "REVOKE ALL ON ALL " + category + " IN SCHEMA " + q + " FROM " + role,
      )
    }
    if role != "PUBLIC" {
      statements.push("REVOKE ALL ON SCHEMA " + q + " FROM " + role)
    }
  }
  statements
}

///|
fn source_snapshot_sql_v4(table : SQLTableV1) -> String raise {
  let terms : Array[String] = []
  for column in table.columns {
    if column.kind == "text" {
      terms.push(
        "pg_catalog.octet_length(t." + v3_dislock_quote(column.name) + ")>65536",
      )
    }
  }
  let big = if terms.is_empty() { "FALSE" } else { terms.join(" OR ") }
  "SELECT CASE WHEN (" +
  big +
  ") THEN pg_catalog.jsonb_build_object('kind','initial-row-budget') " +
  "WHEN pg_catalog.octet_length(pg_catalog.to_jsonb(t)::text)>65536 THEN pg_catalog.jsonb_build_object('kind','initial-row-budget') " +
  "ELSE pg_catalog.jsonb_build_object('kind','initial-row','row',pg_catalog.to_jsonb(t)) END::text FROM " +
  source_target_v4(table) +
  " t WHERE t.\"__mtw_source_version\">%s ORDER BY t.\"__mtw_source_version\" LIMIT 1"
}
