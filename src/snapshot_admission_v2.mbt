///|
pub struct SnapshotAdmissionV2 {
  priv record : Json
  // Preserve original row/effect observations with their control-log locations.
  priv rows : Map[String, Json]
  priv effects : Map[String, Json]
  priv peer : Json
  priv snapshot : Json
  priv log_digest : String
}

///|
pub fn snapshot_admission_v2_json(check : SnapshotAdmissionV2) -> Json {
  let record = object_fields_unchecked_v3(v4_json_copy(check.record))
  record["snapshot"] = v4_json_copy(check.snapshot)
  record["snapshotLogSha256"] = Json(check.log_digest)
  Json(record)
}

///|
fn snapshot_mode_sql_v2() -> String {
  "SELECT pg_catalog.jsonb_build_object('isolation',pg_catalog.current_setting('transaction_isolation')," +
  "'readOnly',pg_catalog.current_setting('transaction_read_only')," +
  "'snapshot',pg_catalog.pg_current_snapshot()::text)::text"
}

///|
fn snapshot_ledger_sql_v2(policy : SourcePolicyV4) -> String {
  "SELECT CASE WHEN pg_catalog.octet_length(p.payload)>65536 THEN '{\"kind\":\"effect-budget\"}' ELSE p.payload END FROM " +
  "(SELECT e.version,pg_catalog.jsonb_build_object('kind','effect','version',e.version::text," +
  "'baseVersion',e.base_version::text,'relationOid',e.relation_oid::bigint,'operation',e.operation," +
  "'writerXid',e.writer_xid,'writerLogin',e.writer_login,'writerPid',e.writer_pid," +
  "'rowKey',e.row_key,'oldKey',e.old_key,'rowValues',e.row_values)::text payload FROM " +
  point_quote_v2(policy.source_schema) +
  ".effects e WHERE e.version>%s::bigint ORDER BY e.version LIMIT 1) p"
}

///|
fn snapshot_scope_sql_v2(policy : SourcePolicyV4) -> String {
  "SELECT pg_catalog.jsonb_build_object('relation_oid',s.relation_oid::bigint,'relation_schema',s.relation_schema,'relation_table',s.relation_table,'primary_key',s.primary_key,'config_sha256',s.config_sha256)::text FROM " +
  point_quote_v2(policy.source_schema) +
  ".scope s ORDER BY relation_schema,relation_table"
}

///|
fn snapshot_scalar_v2(
  config : SQLConfigV2,
  column : SQLColumnV1,
  value : Json,
) -> Json raise {
  let typed = sql_typed_value_v2(
    value,
    column.kind,
    config.parser_config.limits.at("max_text_bytes"),
  )
  if column.kind == "uuid" && value != source_object_v4(typed).at("value") {
    fail("mismatch:snapshot-native-canonical-UUID")
  }
  typed
}

///|
fn snapshot_business_row_v2(
  config : SQLConfigV2,
  raw : Json,
  expected_key : Json,
  work : SourceWorkV4,
) -> Unit raise {
  let table = config.parser_config.tables[0]
  let values = orm_exact(raw, table.columns.map(c => c.name))
  for column in table.columns {
    work.charge()
    let typed = snapshot_scalar_v2(config, column, values.at(column.name))
    if column.name == table.key {
      source_equal_v4(typed, expected_key, "snapshot-complete-row-key")
    }
  }
}

///|
fn snapshot_key_v2(config : SQLConfigV2, raw : Json) -> Json raise {
  let table = config.parser_config.tables[0]
  let column = match table.columns.iter().find_first(c => c.name == table.key) {
    Some(column) => column
    None => fail("invalid:snapshot-primary-key-config")
  }
  snapshot_scalar_v2(config, column, raw)
}

///|
fn snapshot_initial_effect_v2(
  installation : SourceAdmissionV2,
  version : String,
  effect : Map[String, Json],
  work : SourceWorkV4,
) -> Unit raise {
  work.charge()
  let initial = match installation.initial_effects.get(version) {
    Some(value) => source_object_v4(value)
    None => fail("mismatch:snapshot-initial-version-not-installed")
  }
  if initial.at("kind") != Json("initial-ledger") ||
    source_positive_v4(initial.at("version")) != version {
    fail("mismatch:snapshot-initial-ledger-identity")
  }
  for
    name in [
      "baseVersion", "relationOid", "operation", "writerXid", "writerLogin", "writerPid",
      "rowKey", "oldKey", "rowValues",
    ] {
    work.charge()
    source_equal_v4(
      effect.at(name),
      initial.at(name),
      "snapshot-initial-ledger-" + name,
    )
  }
}

///|
pub fn verify_snapshot_admission_v2(
  installation : SourceAdmissionV2,
  original_log : String,
  receipt : Json,
  max_checks~ : Int32 = 1000000,
  max_rows~ : Int32 = 4096,
  max_effects~ : Int32 = 4096,
) -> SnapshotAdmissionV2 {
  let work : SourceWorkV4 = { limit: max_checks, checks: 0, }
  let rows : Map[String, Json] = Map([])
  let effects : Map[String, Json] = Map([])
  let mut peer : Json = Json::null()
  let mut snapshot : Json = Json::null()
  let mut reason = ""
  let mut control_complete = false
  let observed_versions : Array[Json] = []
  let observed_effects : Array[Json] = []
  let status = try {
    if max_checks < 0 ||
      max_checks > 1000000 ||
      max_rows < 0 ||
      max_rows > 16384 ||
      max_effects < 0 ||
      max_effects > 16384 {
      fail("invalid:snapshot-independent-budgets")
    }
    work.charge()
    let installed = source_object_v4(installation.record)
    if installed.get("installationVerified") != Some(Json(true)) {
      if installed.get("status") == Some(Json("unknown")) {
        fail("unsupported:snapshot-installation-unresolved")
      }
      fail("mismatch:snapshot-installation-not-verified")
    }
    let config = installation.config
    let policy = installation.policy
    let table = config.parser_config.tables[0]
    let r = orm_exact(receipt, [
      "format", "contract", "status", "configSha256", "installationLogSha256", "maxRows",
      "maxEffects", "sourceFactsProduced", "sourceAuthenticated", "moonbitSourceVerified",
      "completeWindow", "modelCoverageAccepted", "rowsObserved", "effectsObserved",
      "snapshot", "peer", "tableOid", "visibleRowVersions", "effectVersions", "log",
    ])
    if r.at("format") != Json("moontxnwitness-configured-source-snapshot/v2") ||
      r.at("contract") !=
      Json("postgres18-configured-point-window-observations/v2") ||
      r.at("status") != Json("observed-components-only") ||
      r.at("configSha256") != Json(config.digest) ||
      r.at("installationLogSha256") != Json(installation.log_digest) {
      fail("mismatch:snapshot-receipt-identity")
    }
    for
      key in [
        "sourceFactsProduced", "sourceAuthenticated", "moonbitSourceVerified", "completeWindow",
        "modelCoverageAccepted",
      ] {
      source_equal_v4(
        r.at(key),
        Json(false),
        "snapshot-producer-cannot-authorize-" + key,
      )
    }
    let claimed_row_limit = fetch_number_v1(r.at("maxRows"), 16384)
    let claimed_effect_limit = fetch_number_v1(r.at("maxEffects"), 16384)
    let stream = source_parse_control_v2(
      original_log,
      r.at("log"),
      "moontxnwitness-source-snapshot-log/v2",
      "postgres18-configured-point-window-observations/v2",
      work,
    )
    if stream.commit_request_seq != 0 {
      fail("mismatch:snapshot-unexpected-commit-request")
    }
    source_control_ack_v2(
      stream.next(
        "snapshot-begin",
        "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY",
        Json::null(),
        before=0,
      ),
      "BEGIN",
    )
    source_control_ack_v2(
      stream.next(
        "snapshot-safe-path",
        "SET LOCAL search_path TO pg_catalog,pg_temp",
        Json::null(),
      ),
      "SET",
    )
    snapshot = stream.one("snapshot-mode", snapshot_mode_sql_v2(), Json::null())
    let mode = orm_exact(snapshot, ["isolation", "readOnly", "snapshot"])
    if mode.at("isolation") != Json("repeatable read") ||
      mode.at("readOnly") != Json("on") {
      fail("mismatch:snapshot-read-only-repeatable-mode")
    }
    let (_, upper, active) = effects_snapshot_bounds_v4(
      sql_string_v1(mode.at("snapshot")),
      work,
    )
    source_equal_v4(r.at("snapshot"), snapshot, "snapshot-receipt-mode")
    peer = stream.one(
      "snapshot-peer",
      "SELECT " + effects_peer_sql_v4() + "::text",
      Json::null(),
    )
    effects_check_peer_v4(peer)
    source_equal_v4(r.at("peer"), peer, "snapshot-receipt-peer")
    let environment = stream.one(
      "environment",
      source_v4_environment_sql(),
      Json([Json(policy.writers)]),
    )
    let owner = source_environment_v4(environment, policy, work)
    let env = source_object_v4(environment)
    let original_env = source_object_v4(installation.environment)
    for name in ["database", "databaseOid", "owner"] {
      source_equal_v4(
        env.at(name),
        original_env.at(name),
        "snapshot-installed-environment-" + name,
      )
    }
    source_equal_v4(
      source_object_v4(peer).at("databaseOid"),
      env.at("databaseOid"),
      "snapshot-peer-database",
    )
    let private_catalog = stream.one(
      "source-catalog",
      source_v4_source_catalog_sql(),
      Json([Json(policy.source_schema)]),
    )
    source_private_catalog_v4(private_catalog, policy, owner, work)
    let catalog = stream.one(
      "table-catalog",
      source_v4_table_catalog_sql(),
      Json([Json(table.schema), Json(table.name)]),
    )
    let oid_text = admission_catalog_v2(
      config, policy, owner, catalog, true, work,
    )
    source_equal_v4(
      catalog,
      installation.catalog,
      "snapshot-unchanged-installed-catalog",
    )
    let oid = source_object_v4(catalog).at("oid")
    if source_positive_v4(oid) != oid_text {
      fail("mismatch:snapshot-table-identity")
    }
    source_equal_v4(r.at("tableOid"), oid, "snapshot-receipt-table")
    for writer in policy.writers {
      let target = source_target_v4(table)
      let privilege = orm_exact(
        stream.one(
          "writer-privileges",
          source_v4_permissions_sql(),
          Json([
            Json(writer),
            Json(target),
            Json(writer),
            Json(target),
            Json(writer),
            Json(target),
            Json(writer),
            Json(owner),
          ]),
        ),
        ["role", "table", "trigger", "truncate", "ownerMembership"],
      )
      source_equal_v4(
        privilege.at("role"),
        Json(writer),
        "snapshot-writer-role",
      )
      source_equal_v4(
        privilege.at("table"),
        Json(target),
        "snapshot-writer-table",
      )
      for name in ["trigger", "truncate", "ownerMembership"] {
        if privilege.at(name) != Json(false) {
          fail("unsupported:snapshot-writer-can-bypass-source")
        }
      }
    }
    let scope = stream.next(
      "source-scope",
      snapshot_scope_sql_v2(policy),
      Json::null(),
    )
    source_equal_v4(
      Json(scope.decoded),
      [
        {
          "relation_oid": oid,
          "relation_schema": Json(table.schema),
          "relation_table": Json(table.name),
          "primary_key": Json(table.key),
          "config_sha256": Json(config.digest),
        },
      ],
      "snapshot-complete-scope",
    )
    let row_keys : Map[String, Bool] = Map([])
    let mut previous = "0"
    let mut previous_json : Json = Json(0)
    while true {
      let page = stream.next(
        "visible-row",
        admission_snapshot_sql_v2(config),
        Json([previous_json]),
      )
      if page.decoded.is_empty() {
        break
      }
      if page.decoded.length() != 1 {
        fail("mismatch:snapshot-row-page-size")
      }
      if rows.length() >= max_rows {
        fail("budget:snapshot-visible-rows")
      }
      if rows.length() >= claimed_row_limit {
        fail("mismatch:snapshot-producer-row-limit")
      }
      let observation = orm_exact(page.decoded[0], ["kind", "row"])
      if observation.at("kind") != Json("initial-row") {
        fail("unsupported:snapshot-row-budget-marker")
      }
      let expected = table.columns.map(c => c.name)
      expected.push("__mtw_source_version")
      let values = orm_exact(observation.at("row"), expected)
      let version = source_positive_v4(values.at("__mtw_source_version"))
      let _ = effects_decimal_v4(Json(version), "9223372036854775807")
      if !source_version_after_v4(version, previous) || rows.contains(version) {
        fail("mismatch:snapshot-visible-version-order")
      }
      let key = snapshot_key_v2(config, values.at(table.key))
      let key_text = sql_canonical_v1(key)
      if row_keys.contains(key_text) {
        fail("mismatch:snapshot-duplicate-visible-key")
      }
      row_keys[key_text] = true
      for column in table.columns {
        work.charge()
        let _ = snapshot_scalar_v2(config, column, values.at(column.name))
      }
      rows[version] = {
        "row": observation.at("row"),
        "requestSeq": Json(page.request_seq),
        "resultSeq": Json(page.result_seq),
      }
      observed_versions.push(Json(version))
      previous = version
      previous_json = values.at("__mtw_source_version")
    }
    previous = "0"
    let consumed : Map[String, Bool] = Map([])
    let matched : Map[String, Bool] = Map([])
    let writers : Map[String, Json] = Map([])
    while true {
      let page = stream.next(
        "retained-effect",
        snapshot_ledger_sql_v2(policy),
        Json([Json(previous)]),
      )
      if page.decoded.is_empty() {
        break
      }
      if page.decoded.length() != 1 {
        fail("mismatch:snapshot-effect-page-size")
      }
      if effects.length() >= max_effects {
        fail("budget:snapshot-retained-effects")
      }
      if effects.length() >= claimed_effect_limit {
        fail("mismatch:snapshot-producer-effect-limit")
      }
      let effect = orm_exact(page.decoded[0], [
        "kind", "version", "baseVersion", "relationOid", "operation", "writerXid",
        "writerLogin", "writerPid", "rowKey", "oldKey", "rowValues",
      ])
      if effect.at("kind") != Json("effect") {
        fail("unsupported:snapshot-effect-budget-marker")
      }
      let version = effects_decimal_v4(
        effect.at("version"),
        "9223372036854775807",
      )
      if !source_version_after_v4(version, previous) ||
        effects.contains(version) {
        fail("mismatch:snapshot-effect-identity-order")
      }
      source_equal_v4(effect.at("relationOid"), oid, "snapshot-effect-table")
      let operation = sql_string_v1(effect.at("operation"))
      let key = snapshot_key_v2(config, effect.at("rowKey"))
      let xid = effects_xid_v4(effect.at("writerXid"))
      if !effects_xid_completed_v4(xid, upper, active) {
        fail("mismatch:snapshot-effect-not-visible-in-snapshot")
      }
      let login = sql_identifier_v1(effect.at("writerLogin"))
      let pid = fetch_number_v1(effect.at("writerPid"), 2147483647)
      if pid == 0 {
        fail("mismatch:snapshot-writer-pid")
      }
      let identity : Json = [Json(login), Json(pid)]
      match writers.get(xid) {
        Some(previous) if previous != identity =>
          fail("mismatch:snapshot-XID-writer-identity")
        None => writers[xid] = identity
        _ => ()
      }
      if operation == "INITIAL" {
        snapshot_initial_effect_v2(installation, version, effect, work)
      } else if !policy.writers.contains(login) {
        fail("mismatch:snapshot-effect-writer-outside-scope")
      }
      match operation {
        "INITIAL" | "INSERT" =>
          if effect.at("baseVersion") != Json::null() ||
            effect.at("oldKey") != Json::null() {
            fail("mismatch:snapshot-insert-initial-predecessor")
          }
        "UPDATE" | "DELETE" => {
          let base = effects_decimal_v4(
            effect.at("baseVersion"),
            "9223372036854775807",
          )
          let parent = match effects.get(base) {
            Some(value) => source_object_v4(value)
            None => fail("mismatch:snapshot-missing-retained-predecessor")
          }
          if parent.at("operation") == Json("DELETE") ||
            consumed.contains(base) ||
            snapshot_key_v2(config, parent.at("rowKey")) != key ||
            snapshot_key_v2(config, effect.at("oldKey")) != key {
            fail("mismatch:snapshot-predecessor-key-or-reuse")
          }
          consumed[base] = true
        }
        _ => fail("mismatch:snapshot-operation")
      }
      if operation == "DELETE" {
        if effect.at("rowValues") != Json::null() || rows.contains(version) {
          fail("mismatch:snapshot-deletion-is-not-live-row")
        }
      } else {
        snapshot_business_row_v2(config, effect.at("rowValues"), key, work)
        match rows.get(version) {
          Some(observed) => {
            let full = source_object_v4(source_object_v4(observed).at("row"))
            let business : Map[String, Json] = Map([])
            for column in table.columns {
              business[column.name] = full.at(column.name)
            }
            source_equal_v4(
              Json(business),
              effect.at("rowValues"),
              "snapshot-visible-row-full-source",
            )
            matched[version] = true
          }
          None => ()
        }
      }
      let retained = source_object_v4(v4_json_copy(page.decoded[0]))
      retained["requestSeq"] = Json(page.request_seq)
      retained["resultSeq"] = Json(page.result_seq)
      effects[version] = Json(retained)
      observed_effects.push(Json(version))
      previous = version
    }
    if matched.length() != rows.length() {
      fail("mismatch:snapshot-visible-row-source-missing")
    }
    // In a single fixed database snapshot every retained live version is either
    // consumed by its successor or is one of the complete current row set.
    // Allocation order is deliberately irrelevant to this bidirectional check.
    for version in effects.keys().to_array() {
      work.charge()
      let live = source_object_v4(effects.at(version)).at("operation") !=
        Json("DELETE")
      if rows.contains(version) && consumed.contains(version) {
        fail("mismatch:snapshot-visible-version-already-consumed")
      }
      if live && !consumed.contains(version) && !rows.contains(version) {
        fail("mismatch:snapshot-unconsumed-live-version-absent")
      }
    }
    for version in installation.initial_versions.keys().to_array() {
      work.charge()
      if !effects.contains(version) {
        fail("mismatch:snapshot-installed-initial-ledger-missing")
      }
    }
    source_control_ack_v2(
      stream.next("snapshot-finish", "ROLLBACK", Json::null(), after=0),
      "ROLLBACK",
    )
    if stream.next_index != stream.commands.length() {
      fail("mismatch:snapshot-extra-control-command")
    }
    control_complete = true
    source_equal_v4(
      r.at("rowsObserved"),
      Json(rows.length()),
      "snapshot-receipt-row-count",
    )
    source_equal_v4(
      r.at("effectsObserved"),
      Json(effects.length()),
      "snapshot-receipt-effect-count",
    )
    source_equal_v4(
      r.at("visibleRowVersions"),
      Json(observed_versions),
      "snapshot-receipt-row-identities",
    )
    source_equal_v4(
      r.at("effectVersions"),
      Json(observed_effects),
      "snapshot-receipt-effect-identities",
    )
    "matched"
  } catch {
    error => {
      reason = error.to_string()
      if reason.contains("budget:") || reason.contains("unsupported:") {
        "unknown"
      } else if reason.contains("mismatch:") {
        "mismatch"
      } else {
        "invalid"
      }
    }
  }
  let record : Json = {
    "format": "moontxnwitness-source-snapshot-admission/v2",
    "semanticContract": "postgres18-original-readonly-snapshot-complete-ledger/v2",
    "algorithm": "moonbit-snapshot-original-control-ledger-2",
    "status": Json(status),
    "valid": Json(status == "matched"),
    "snapshotVerified": Json(status == "matched"),
    "controlComplete": Json(control_complete),
    "rowsObserved": Json(rows.length()),
    "effectsObserved": Json(effects.length()),
    "rows": Json(rows),
    "effects": Json(effects),
    "peer": peer,
    "snapshot": snapshot,
    "snapshotLogSha256": Json(v3_dislock_sha256(original_log)),
    "installationLogSha256": Json(installation.log_digest),
    "sourceFactsProduced": false,
    "sourceAuthenticated": false,
    "completeWindow": false,
    "writerWindowVerified": false,
    "modelCoverageAccepted": false,
    "commitVerified": false,
    "execution": {
      "checks": Json(work.checks),
      "limit": Json(max_checks),
      "maxChecks": Json(max_checks),
      "maxRows": Json(max_rows),
      "maxEffects": Json(max_effects),
      "limited": Json(reason.contains("budget:")),
    },
    "gaps": [
      Json(
        if reason.is_empty() {
          "snapshot-only-capture-lifecycle-source-window-and-model-admission-remain-separate"
        } else {
          reason
        },
      ),
    ],
  }
  {
    record,
    rows,
    effects,
    peer,
    snapshot,
    log_digest: v3_dislock_sha256(original_log),
  }
}
