///|
fn effects_snapshot_sql_v4(policy : SourcePolicyV4) -> String raise {
  let source = v3_dislock_quote(policy.source_schema)
  "SELECT CASE WHEN pg_catalog.octet_length(p.payload)>16384 THEN '{\"kind\":\"effect-row-budget\"}' " +
  "ELSE p.payload END FROM (SELECT e.version,pg_catalog.jsonb_build_object('kind','effect'," +
  "'version',e.version::text,'baseVersion',e.base_version::text,'relationOid',e.relation_oid::bigint," +
  "'operation',e.operation,'writerXid',e.writer_xid,'writerLogin',e.writer_login,'writerPid',e.writer_pid," +
  "'rowKey',e.row_key,'oldKey',e.old_key,'rowValues',e.row_values)::text AS payload FROM " +
  source +
  ".effects e WHERE e.version>%s::bigint AND e.operation<>'INITIAL' " +
  "ORDER BY e.version LIMIT 8) p ORDER BY p.version"
}

///|
fn effects_scope_sql_v4(policy : SourcePolicyV4) -> String raise {
  "SELECT pg_catalog.jsonb_build_object('relation_oid',s.relation_oid::bigint," +
  "'relation_schema',s.relation_schema,'relation_table',s.relation_table," +
  "'primary_key',s.primary_key,'config_sha256',s.config_sha256)::text FROM " +
  v3_dislock_quote(policy.source_schema) +
  ".scope s ORDER BY relation_schema,relation_table"
}

///|
fn effects_decimal_v4(value : Json, ceiling : String) -> String raise {
  let text = sql_string_v1(value)
  if !sql_digits_v1(text) ||
    text.has_prefix("0") ||
    source_version_after_v4(text, ceiling) {
    fail("mismatch:effect-positive-decimal")
  }
  text
}

///|
priv struct EffectVersionV4 {
  oid : Json
  key : Json
  live : Bool
}

///|
fn effects_check_row_v4(
  value : Json,
  previous : String,
  installation : SourceInstallationCheckV4,
  policy : SourcePolicyV4,
  tables : Map[String, (SQLTableV1, String)],
  versions : Map[String, EffectVersionV4],
  consumed : Map[String, Bool],
  work : SourceWorkV4,
) -> String raise {
  work.charge()
  let row = source_object_v4(value)
  if row.get("kind") == Some(Json("effect-row-budget")) {
    fail("budget:effect-native-row")
  }
  let e = orm_exact(value, [
    "kind", "version", "baseVersion", "relationOid", "operation", "writerXid", "writerLogin",
    "writerPid", "rowKey", "oldKey", "rowValues",
  ])
  let version = effects_decimal_v4(e.at("version"), "9223372036854775807")
  if e.at("kind") != Json("effect") ||
    !source_version_after_v4(version, previous) ||
    installation.initial_versions.contains(version) {
    fail("mismatch:effect-version-enumeration")
  }
  let _ = effects_decimal_v4(e.at("writerXid"), "18446744073709551615")
  if !policy.writers.contains(sql_string_v1(e.at("writerLogin"))) ||
    fetch_number_v1(e.at("writerPid"), 2147483647) == 0 {
    fail("mismatch:effect-writer-identity")
  }
  let oid = e.at("relationOid")
  let (table, kind) = match tables.get(source_positive_v4(oid)) {
    Some(table) => table
    None => fail("mismatch:effect-relation")
  }
  let key = sql_typed_value_v1(e.at("rowKey"), kind, 65536)
  let operation = sql_string_v1(e.at("operation"))
  match operation {
    "INSERT" =>
      if e.at("baseVersion") != Json::null() || e.at("oldKey") != Json::null() {
        fail("mismatch:effect-insert-base")
      }
    "UPDATE" | "DELETE" => {
      let base = effects_decimal_v4(e.at("baseVersion"), "9223372036854775807")
      if consumed.contains(base) {
        fail("mismatch:effect-reused-predecessor")
      }
      let predecessor = match versions.get(base) {
        Some(seen) => seen
        None =>
          match installation.initial_versions.get(base) {
            Some(initial) => {
              let original = source_object_v4(initial)
              if original.at("tableOid") != oid {
                fail("mismatch:effect-predecessor-key-or-table")
              }
              let original_row = source_object_v4(original.at("row"))
              {
                oid: original.at("tableOid"),
                key: sql_typed_value_v1(original_row.at(table.key), kind, 65536),
                live: true,
              }
            }
            None => fail("mismatch:effect-missing-predecessor")
          }
      }
      let old_key = sql_typed_value_v1(e.at("oldKey"), kind, 65536)
      if !predecessor.live ||
        predecessor.oid != oid ||
        predecessor.key != old_key {
        fail("mismatch:effect-predecessor-key-or-table")
      }
      if operation == "DELETE" && old_key != key {
        fail("mismatch:effect-delete-key")
      }
      consumed[base] = true
    }
    _ => fail("mismatch:effect-operation")
  }
  if operation == "DELETE" {
    if e.at("rowValues") != Json::null() {
      fail("mismatch:effect-tombstone-values")
    }
  } else {
    let values = orm_exact(
      e.at("rowValues"),
      table.columns.map(column => column.name),
    )
    for column in table.columns {
      work.charge()
      let value = values.at(column.name)
      if value != Json::null() || column.name == table.key {
        let _ = sql_typed_value_v1(value, column.kind, 65536)
      }
    }
    if sql_typed_value_v1(values.at(table.key), kind, 65536) != key {
      fail("mismatch:effect-current-key")
    }
  }
  versions[version] = { oid, key, live: operation != "DELETE", }
  version
}

///|
fn check_effect_snapshot_v4(
  installation : SourceInstallationCheckV4,
  installation_receipt : Json,
  policy : SourcePolicyV4,
  log : String,
  receipt : Json,
  max_rows : Int32,
  work : SourceWorkV4,
) -> Json raise {
  let i = source_object_v4(installation.record)
  if i.at("valid") != Json(true) {
    if source_object_v4(i.at("execution")).at("limited") == Json(true) {
      fail("budget:effect-installation-checks")
    }
    fail("mismatch:effect-installation-evidence")
  }
  let r = orm_exact(receipt, [
    "format", "status", "installationLogSha256", "configSha256", "maxRows", "effectsObserved",
    "sourceFactsProduced", "writerWindowVerified", "isolationAnalysisReady", "log",
  ])
  if r.at("format") != Json("moontxnwitness-configured-effects-snapshot/v1") ||
    r.at("status") != Json("observed-snapshot") ||
    r.at("maxRows") != Json(max_rows) ||
    r.at("installationLogSha256") != Json(installation.log_digest) ||
    r.at("configSha256") != i.at("configSha256") ||
    ["sourceFactsProduced", "writerWindowVerified", "isolationAnalysisReady"].any(key => {
        r.at(key) != Json(false)
      },
    ) {
    fail("mismatch:effect-receipt-binding")
  }
  let stream = source_parse_stream_v4(log, receipt, policy, work)
  if stream.commit_request_seq != 0 {
    fail("mismatch:effect-unexpected-commit-marker")
  }
  source_command_ack_v4(
    stream.next(
      "begin",
      "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY",
      Json::null(),
    ),
    "BEGIN",
  )
  source_command_ack_v4(
    stream.next(
      "effects-safe-path",
      "SET LOCAL search_path TO pg_catalog, pg_temp",
      Json::null(),
    ),
    "SET",
  )
  let mode = orm_exact(
    stream.one(
      "effects-snapshot-mode",
      "SELECT pg_catalog.jsonb_build_object('isolation',pg_catalog.current_setting('transaction_isolation')," +
      "'readOnly',pg_catalog.current_setting('transaction_read_only')," +
      "'snapshot',pg_catalog.pg_current_snapshot()::text)::text",
      Json::null(),
    ),
    ["isolation", "readOnly", "snapshot"],
  )
  let snapshot = sql_string_v1(mode.at("snapshot"))
  if mode.at("isolation") != Json("repeatable read") ||
    mode.at("readOnly") != Json("on") ||
    snapshot.is_empty() {
    fail("mismatch:effect-read-only-snapshot")
  }
  let environment = stream.one(
    "environment",
    source_v4_environment_sql(),
    Json([Json(policy.writers)]),
  )
  let owner = source_environment_v4(environment, policy, work)
  let current = source_object_v4(environment)
  let installed = source_object_v4(i.at("environment"))
  for key in ["database", "databaseOid", "owner"] {
    source_equal_v4(
      current.at(key),
      installed.at(key),
      "effect-environment-" + key,
    )
  }
  let catalog = stream.one(
    "source-catalog",
    source_v4_source_catalog_sql(),
    Json([Json(policy.source_schema)]),
  )
  source_private_catalog_v4(catalog, policy, owner, work)
  let scope = stream.next(
    "source-scope",
    effects_scope_sql_v4(policy),
    Json::null(),
  )
  source_equal_v4(
    Json(scope.decoded),
    source_object_v4(installation_receipt).at("sourceScope"),
    "effect-scope",
  )
  let tables : Map[String, (SQLTableV1, String)] = Map([])
  for index, table in installation.config.tables {
    let observed = stream.one(
      "installed-catalog",
      source_v4_table_catalog_sql(),
      Json([Json(table.schema), Json(table.name)]),
    )
    let oid = source_table_catalog_v4(
      table, policy, owner, observed, true, work,
    )
    source_equal_v4(
      Json(oid),
      Json(
        source_positive_v4(
          source_object_v4(installation.installed_catalogs[index]).at("oid"),
        ),
      ),
      "effect-installed-table",
    )
    for column in table.columns {
      if column.name == table.key {
        tables[oid] = (table, column.kind)
      }
    }
  }
  let observations : Array[Json] = []
  let versions : Map[String, EffectVersionV4] = Map([])
  let consumed : Map[String, Bool] = Map([])
  let writers : Map[String, (Json, Json)] = Map([])
  let mut previous = "0"
  let sql = effects_snapshot_sql_v4(policy)
  while true {
    let page = stream.next("effects-page", sql, Json([Json(previous)]))
    if source_object_v4(page.native).at("fields") != Json(1) ||
      page.decoded.length() > 8 {
      fail("mismatch:effect-page-shape")
    }
    if page.decoded.is_empty() {
      break
    }
    for index, row in page.decoded {
      if observations.length() >= max_rows {
        fail("budget:effect-rows")
      }
      previous = effects_check_row_v4(
        row, previous, installation, policy, tables, versions, consumed, work,
      )
      let effect = source_object_v4(row)
      let xid = sql_string_v1(effect.at("writerXid"))
      let identity = (effect.at("writerLogin"), effect.at("writerPid"))
      match writers.get(xid) {
        Some(previous) if previous != identity =>
          fail("mismatch:effect-writer-XID-identity")
        None => writers[xid] = identity
        _ => ()
      }
      observations.push({
        "version": Json(previous),
        "baseVersion": effect.at("baseVersion"),
        "relationOid": effect.at("relationOid"),
        "operation": effect.at("operation"),
        "writerXid": Json(xid),
        "writerLogin": effect.at("writerLogin"),
        "writerPid": effect.at("writerPid"),
        "requestSeq": Json(page.request_seq),
        "resultSeq": Json(page.result_seq),
        "rowIndex": Json(index),
      })
    }
  }
  if stream.next_index + 1 != stream.commands.length() {
    fail("mismatch:effect-missing-finish-or-extra-command")
  }
  let finish = stream.commands[stream.next_index]
  if finish.query_id != "effects-finish" ||
    finish.sql != "ROLLBACK" ||
    finish.parameters != Json::null() ||
    finish.before != 2 ||
    finish.after != 0 {
    fail("mismatch:effect-finish")
  }
  source_command_ack_v4(finish, "ROLLBACK")
  source_equal_v4(
    r.at("effectsObserved"),
    Json(observations.length()),
    "effect-row-count",
  )
  {
    "snapshot": Json(snapshot),
    "effectsObserved": Json(observations.length()),
    "observations": Json(observations),
  }
}

///|
/// Replays independent checks on an exported snapshot and its original installation.
pub fn verify_configured_effects_snapshot_v4_json(
  input : String,
  options : String,
) -> String {
  let format = "moontxnwitness-configured-effects-verification/v4"
  try {
    let envelope = orm_exact(sql_json_v1(input, 25165824), [
      "configText", "policyText", "installationLogText", "installationReceiptText",
      "effectsLogText", "effectsReceiptText",
    ])
    let limits = source_object_v4(sql_json_v1(options, 8192))
    known_fields(
      limits,
      ["maxRows", "maxChecks", "maxInstallationChecks"],
      "effects-options",
    )
    let max_rows = fetch_number_v1(
      limits.get_or_default("maxRows", Json(256)),
      4096,
    )
    let work : SourceWorkV4 = {
      limit: source_wire_limit_v4(limits, "maxChecks", 1000000),
      checks: 0,
    }
    let original_receipt = sql_json_v1(
      sql_string_v1(envelope.at("installationReceiptText")),
      2097152,
    )
    let policy = sql_json_v1(sql_string_v1(envelope.at("policyText")), 8192)
    let config = match
      parse_sql_config_v1(sql_string_v1(envelope.at("configText"))) {
      Ok(value) => value
      Err(reason) => fail(reason)
    }
    let installation = verify_source_installation_v4(
      config,
      policy,
      sql_string_v1(envelope.at("installationLogText")),
      original_receipt,
      max_checks=source_wire_limit_v4(limits, "maxInstallationChecks", 1000000),
    )
    let log = sql_string_v1(envelope.at("effectsLogText"))
    let receipt = sql_json_v1(
      sql_string_v1(envelope.at("effectsReceiptText")),
      8192,
    )
    let observation = check_effect_snapshot_v4(
      installation,
      original_receipt,
      source_policy_v4(policy),
      log,
      receipt,
      max_rows,
      work,
    )
    (
      {
        "format": Json(format),
        "status": "matched-snapshot-observations",
        "valid": true,
        "sourceFactsProduced": false,
        "sourceAuthenticated": false,
        "writerWindowVerified": false,
        "isolationAnalysisReady": false,
        "installationLogSha256": Json(installation.log_digest),
        "effectsLogSha256": Json(v3_dislock_sha256(log)),
        "observation": observation,
        "checks": Json(work.checks),
        "maxChecks": Json(work.limit),
        "maxRows": Json(max_rows),
      } : Json).stringify()
  } catch {
    error =>
      (
        {
          "format": Json(format),
          "status": if error.to_string().contains("budget:") {
            Json("unknown")
          } else {
            Json("invalid")
          },
          "valid": false,
          "sourceFactsProduced": false,
          "sourceAuthenticated": false,
          "writerWindowVerified": false,
          "isolationAnalysisReady": false,
          "reason": Json(error.to_string()),
        } : Json).stringify()
  }
}
