///|
pub struct SourceAdmissionV2 {
  priv record : Json
  priv config : SQLConfigV2
  priv policy : SourcePolicyV4
  priv catalog : Json
  priv initial_versions : Map[String, Json]
  priv initial_effects : Map[String, Json]
  priv log_digest : String
  priv environment : Json
}

///|
pub fn source_admission_v2_json(value : SourceAdmissionV2) -> Json {
  v4_json_copy(value.record)
}

///|
fn admission_compare_catalogs_v2(
  config : SQLConfigV2,
  before : Json,
  after : Json,
  work : SourceWorkV4,
) -> Json raise {
  let old = source_object_v4(before)
  let new = source_object_v4(after)
  source_equal_v4(old.at("oid"), new.at("oid"), "V2-installation-OID")
  let a = orm_array(old.at("columns"))
  let b = orm_array(new.at("columns"))
  if b.length() != a.length() + 1 {
    fail("mismatch:admission-only-version-added")
  }
  for index, column in a {
    work.charge()
    source_equal_v4(column, b[index], "V2-business-column-unchanged")
  }
  let last = source_object_v4(b[b.length() - 1])
  if last.at("name") != Json("__mtw_source_version") ||
    fetch_number_v1(last.at("number"), 32767) <=
    fetch_number_v1(source_object_v4(a[a.length() - 1]).at("number"), 32767) {
    fail("mismatch:admission-version-appended")
  }
  let names = a.map(raw => source_object_v4(raw).at("name"))
  let configured = config.parser_config.tables[0].columns.map(c => Json(c.name))
  {
    "format": "moontxnwitness-v2-star-catalog-comparison/v2",
    "beforePhysicalColumns": Json(names),
    "afterPhysicalColumns": Json(b.map(raw => source_object_v4(raw).at("name"))),
    "onlyVersionColumnAdded": true,
    "declaredBusinessViewMatchesBeforeOrder": Json(names == configured),
    "catalogInstallationSourceAuthorized": false,
    "moonbitProjectionVerified": false,
  }
}

///|
pub fn verify_source_admission_v2(
  config : SQLConfigV2,
  policy_value : Json,
  original_log : String,
  receipt : Json,
  max_checks~ : Int32 = 1000000,
) -> SourceAdmissionV2 {
  let work : SourceWorkV4 = { limit: max_checks, checks: 0, }
  let mut policy : SourcePolicyV4 = {
    source_schema: "",
    writers: [],
    max_initial: 0,
    max_log_bytes: 0,
    record: policy_value,
  }
  let mut catalog : Json = Json::null()
  let mut environment : Json = Json::null()
  let initial : Map[String, Json] = Map([])
  let initial_effects : Map[String, Json] = Map([])
  let mut reason = ""
  let mut count = 0
  let mut owner = ""
  let status = try {
    if max_checks < 0 || max_checks > 1000000 {
      fail("invalid:admission-caller-budget")
    }
    work.charge()
    policy = source_policy_v4(policy_value)
    let table = config.parser_config.tables[0]
    if table.columns.any(c => c.name == "__mtw_source_version") {
      fail("invalid:admission-version-collision")
    }
    let r = source_object_v4(receipt)
    known_fields(
      r,
      [
        "format", "contract", "config", "configSha256", "policy", "versionColumn",
        "versionType", "status", "catalogComponentsChecked", "initialSnapshotComponentsChecked",
        "initialLedgerComponentsChecked", "actualCommitAcknowledged", "actualCommitConfirmed",
        "sourceFactsProduced", "captureFactsProduced", "sourceAuthenticated", "moonbitCatalogVerified",
        "moonbitProjectionVerified", "writerWindowVerified", "completeWindow", "modelCoverageAccepted",
        "driverFetchVerified", "commitVerified", "deleteLedgerIdentity", "gaps",
        "environment", "beforeCatalog", "writerPrivileges", "initializationLocks",
        "afterCatalog", "starCatalogComparison", "sourceCatalog", "sourceScope",
        "initialLedger", "initialRows", "initialSnapshotSha256", "log",
      ],
      "V2-installation-receipt",
    )
    if r.at("format") !=
      Json("moontxnwitness-configured-source-installation/v2") ||
      r.at("contract") !=
      Json("postgres18-explicit-point-source-installation-components/v2") ||
      r.at("versionColumn") != Json("__mtw_source_version") ||
      r.at("versionType") != Json("int64") {
      fail("mismatch:admission-installation-contract")
    }
    source_equal_v4(r.at("config"), config.record, "V2-caller-config")
    source_equal_v4(
      r.at("configSha256"),
      Json(config.digest),
      "V2-config-digest",
    )
    source_equal_v4(r.at("policy"), policy.record, "V2-caller-policy")
    for
      flag in [
        "sourceFactsProduced", "captureFactsProduced", "sourceAuthenticated", "moonbitCatalogVerified",
        "moonbitProjectionVerified", "writerWindowVerified", "completeWindow", "modelCoverageAccepted",
        "driverFetchVerified", "commitVerified",
      ] {
      source_equal_v4(r.at(flag), Json(false), "V2-producer-non-authority")
    }
    if r.at("deleteLedgerIdentity") !=
      Json("ledger-event-only-not-a-new-deleted-row-version") {
      fail("mismatch:admission-delete-identity")
    }
    if orm_utf8_size(original_log) > policy.max_log_bytes {
      fail("budget:admission-policy-log-bytes")
    }
    let stream = source_parse_control_v2(
      original_log,
      r.at("log"),
      "moontxnwitness-source-installation-log/v2",
      "postgres18-explicit-point-source-installation-components/v2",
      work,
      allow_commit_request=true,
    )
    source_control_ack_v2(
      stream.next("begin", "BEGIN", Json::null(), before=0),
      "BEGIN",
    )
    source_control_ack_v2(
      stream.next(
        "standard-strings",
        "SET LOCAL standard_conforming_strings=on",
        Json::null(),
      ),
      "SET",
    )
    if stream.next_index >= stream.commands.length() ||
      stream.commands[stream.next_index].query_id != "safe-search-path" {
      fail("unsupported:admission-safe-search-path-unobserved")
    }
    source_control_ack_v2(
      stream.next(
        "safe-search-path",
        "SET LOCAL search_path TO pg_catalog, pg_temp",
        Json::null(),
      ),
      "SET",
    )
    source_control_ack_v2(
      stream.next(
        "install-lock",
        "LOCK TABLE " +
        source_target_v4(table) +
        " IN ACCESS EXCLUSIVE MODE NOWAIT",
        Json::null(),
      ),
      "LOCK TABLE",
    )
    environment = stream.one(
      "environment",
      source_v4_environment_sql(),
      Json([Json(policy.writers.map(writer => Json(writer)))]),
    )
    owner = source_environment_v4(environment, policy, work)
    if source_version_after_v4(
        source_positive_v4(source_object_v4(environment).at("backendPid")),
        "2147483647",
      ) {
      fail("mismatch:admission-backend-pid")
    }
    source_equal_v4(r.at("environment"), environment, "V2-receipt-environment")
    let before = stream.one(
      "before-catalog",
      source_v4_table_catalog_sql(),
      Json([Json(table.schema), Json(table.name)]),
    )
    let oid_text = admission_catalog_v2(
      config, policy, owner, before, false, work,
    )
    let oid = source_object_v4(before).at("oid")
    source_equal_v4(r.at("beforeCatalog"), before, "V2-before-catalog")
    let privileges : Array[Json] = []
    for writer in policy.writers {
      let target = source_target_v4(table)
      let value = stream.one(
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
      )
      let p = orm_exact(value, [
        "role", "table", "trigger", "truncate", "ownerMembership",
      ])
      if p.at("role") != Json(writer) ||
        p.at("table") != Json(target) ||
        ["trigger", "truncate", "ownerMembership"].any(key => {
          p.at(key) != Json(false)
        }) {
        fail("mismatch:admission-writer-privileges")
      }
      privileges.push(value)
    }
    source_equal_v4(
      r.at("writerPrivileges"),
      Json(privileges),
      "V2-writer-privileges",
    )
    let held = stream.one(
      "held-locks",
      source_v4_locks_sql(),
      Json([Json([oid])]),
    )
    let h = orm_exact(held, ["pid", "locks"])
    source_equal_v4(
      h.at("pid"),
      source_object_v4(environment).at("backendPid"),
      "V2-lock-backend",
    )
    let mut locked = false
    for raw in orm_array(h.at("locks")) {
      work.charge()
      let l = orm_exact(raw, ["relation", "mode", "granted"])
      if source_oid_v4(l.at("relation")) != oid_text {
        fail("mismatch:admission-lock-scope")
      }
      if l.at("mode") == Json("AccessExclusiveLock") &&
        l.at("granted") == Json(true) {
        if locked {
          fail("mismatch:admission-duplicate-lock")
        }
        locked = true
      }
    }
    if !locked {
      fail("mismatch:admission-exclusive-initialization-lock")
    }
    source_equal_v4(r.at("initializationLocks"), held, "V2-installation-locks")
    let mut update_count : String? = None
    for sql in admission_ddl_v2(config, policy) {
      let command = stream.next("install-ddl", sql, Json::null())
      let tag = source_control_tag_v2(command)
      if sql.has_prefix("UPDATE ") {
        update_count = source_control_count_v2(command)
        match update_count {
          Some(n) => source_control_ack_v2(command, "UPDATE " + n)
          None => fail("mismatch:admission-initial-update-count")
        }
      } else {
        let expected = if sql.has_prefix("CREATE SCHEMA ") {
          "CREATE SCHEMA"
        } else if sql.has_prefix("CREATE SEQUENCE ") {
          "CREATE SEQUENCE"
        } else if sql.has_prefix("CREATE TABLE ") {
          "CREATE TABLE"
        } else if sql.has_prefix("CREATE FUNCTION ") {
          "CREATE FUNCTION"
        } else if sql.has_prefix("CREATE UNIQUE INDEX ") {
          "CREATE INDEX"
        } else if sql.has_prefix("CREATE TRIGGER ") {
          "CREATE TRIGGER"
        } else if sql.has_prefix("ALTER TABLE ") {
          "ALTER TABLE"
        } else if sql.has_prefix("REVOKE ") {
          "REVOKE"
        } else {
          fail("invalid:admission-DDL-constructor")
        }
        source_control_ack_v2(command, expected)
      }
      let _ = tag
    }
    let q = admission_qi_v2(policy.source_schema)
    let v = admission_qi_v2("__mtw_source_version")
    source_control_ack_v2(
      stream.next(
        "install-scope",
        "INSERT INTO " + q + ".scope VALUES(%s,%s,%s,%s,%s)",
        Json([
          oid,
          Json(table.schema),
          Json(table.name),
          Json(table.key),
          Json(config.digest),
        ]),
      ),
      "INSERT 0 1",
    )
    let ledger = stream.next(
      "initial-ledger",
      "INSERT INTO " +
      q +
      ".effects(version,base_version,relation_oid,operation,writer_xid,writer_login,writer_pid,row_key,old_key,row_values) SELECT " +
      v +
      ",NULL,%s,'INITIAL',pg_catalog.pg_current_xact_id()::text,SESSION_USER,pg_catalog.pg_backend_pid(),pg_catalog.to_jsonb(t)->%s,NULL,pg_catalog.to_jsonb(t)-%s FROM " +
      admission_target_v2(table) +
      " t",
      Json([oid, Json(table.key), Json("__mtw_source_version")]),
    )
    let keys : Map[String, Bool] = Map([])
    let initial_digest = StringBuilder()
    let mut previous : Json = Json(0)
    let mut previous_text = "0"
    while true {
      let command = stream.next(
        "initial-snapshot",
        admission_snapshot_sql_v2(config),
        Json([previous]),
      )
      if command.decoded.is_empty() {
        break
      }
      let observation = orm_exact(command.decoded[0], ["kind", "row"])
      if observation.at("kind") != Json("initial-row") {
        fail("unsupported:admission-initial-row-budget")
      }
      let row = observation.at("row")
      let (version, key) = admission_row_v2(config, row, work)
      if !source_version_after_v4(version, previous_text) ||
        initial.contains(version) {
        fail("mismatch:admission-initial-version-order")
      }
      let identity = sql_canonical_v1(key)
      if keys.contains(identity) {
        fail("mismatch:admission-duplicate-initial-key")
      }
      keys[identity] = true
      initial[version] = row
      initial_digest.write_string(
        sql_canonical_v1({
          "schema": Json(table.schema),
          "table": Json(table.name),
          "row": row,
        }),
      )
      initial_digest.write_string("\n")
      previous = source_object_v4(row).at("__mtw_source_version")
      previous_text = version
      count += 1
      if count > policy.max_initial {
        fail("budget:admission-initial-rows")
      }
    }
    if update_count != Some(count.to_string()) ||
      source_control_count_v2(ledger) != Some(count.to_string()) {
      fail("mismatch:admission-initial-inventory-counts")
    }
    source_control_ack_v2(ledger, "INSERT 0 " + count.to_string())
    catalog = stream.one(
      "installed-catalog",
      source_v4_table_catalog_sql(),
      Json([Json(table.schema), Json(table.name)]),
    )
    if admission_catalog_v2(config, policy, owner, catalog, true, work) !=
      oid_text {
      fail("mismatch:admission-installed-OID")
    }
    let comparison = admission_compare_catalogs_v2(
      config, before, catalog, work,
    )
    source_equal_v4(r.at("afterCatalog"), catalog, "V2-installed-catalog")
    source_equal_v4(
      r.at("starCatalogComparison"),
      comparison,
      "V2-business-star-view",
    )
    let sidecar = stream.one(
      "source-catalog",
      source_v4_source_catalog_sql(),
      Json([Json(policy.source_schema)]),
    )
    source_private_catalog_v4(sidecar, policy, owner, work)
    source_equal_v4(r.at("sourceCatalog"), sidecar, "V2-source-catalog")
    let scope = stream.one(
      "source-scope",
      admission_scope_sql_v2(policy),
      Json::null(),
    )
    let expected_scope : Json = {
      "relation_oid": oid,
      "relation_schema": Json(table.schema),
      "relation_table": Json(table.name),
      "primary_key": Json(table.key),
      "config_sha256": Json(config.digest),
    }
    source_equal_v4(scope, expected_scope, "V2-source-scope-row")
    source_equal_v4(
      r.at("sourceScope"),
      Json([scope]),
      "V2-source-scope-receipt",
    )
    previous = Json(0)
    previous_text = "0"
    let mut writer : Json = Json::null()
    while true {
      let command = stream.next(
        "verify-initial-ledger",
        admission_initial_ledger_sql_v2(policy),
        Json([previous]),
      )
      if command.decoded.is_empty() {
        break
      }
      let raw = command.decoded[0]
      let e = orm_exact(raw, [
        "kind", "version", "baseVersion", "relationOid", "operation", "writerXid",
        "writerLogin", "writerPid", "rowKey", "oldKey", "rowValues",
      ])
      let version = source_positive_v4(e.at("version"))
      if !source_version_after_v4(version, previous_text) ||
        !initial.contains(version) ||
        initial_effects.contains(version) {
        fail("mismatch:admission-initial-ledger-inventory")
      }
      let values = source_object_v4(initial.at(version))
      let business : Map[String, Json] = Map([])
      for column in table.columns {
        work.charge()
        business[column.name] = values.at(column.name)
      }
      if e.at("kind") != Json("initial-ledger") ||
        e.at("operation") != Json("INITIAL") ||
        e.at("relationOid") != oid ||
        e.at("baseVersion") != Json::null() ||
        e.at("oldKey") != Json::null() {
        fail("mismatch:admission-initial-ledger-source")
      }
      source_equal_v4(
        e.at("rowKey"),
        values.at(table.key),
        "V2-initial-ledger-key",
      )
      source_equal_v4(
        e.at("rowValues"),
        Json(business),
        "V2-initial-ledger-row",
      )
      let _ = effects_xid_v4(e.at("writerXid"))
      let _ = sql_identifier_v2(e.at("writerLogin"))
      source_equal_v4(
        e.at("writerPid"),
        source_object_v4(environment).at("backendPid"),
        "V2-initial-writer-pid",
      )
      let current_writer = Json([
        e.at("writerXid"),
        e.at("writerLogin"),
        e.at("writerPid"),
      ])
      if writer != Json::null() {
        source_equal_v4(current_writer, writer, "V2-initial-writer-stability")
      }
      writer = current_writer
      initial_effects[version] = raw
      previous = e.at("version")
      previous_text = version
    }
    if initial_effects.length() != initial.length() {
      fail("mismatch:admission-missing-initial-ledger-source")
    }
    let counts = stream.one(
      "initial-ledger-count",
      "SELECT pg_catalog.jsonb_build_object('rows',count(*),'nonInitial',count(*) FILTER(WHERE operation<>'INITIAL'))::text FROM " +
      q +
      ".effects",
      Json::null(),
    )
    source_equal_v4(
      counts,
      { "rows": Json(count), "nonInitial": 0 },
      "V2-complete-initial-ledger",
    )
    source_equal_v4(r.at("initialLedger"), counts, "V2-initial-ledger-receipt")
    let commit = stream.next(
      "installation-commit",
      "COMMIT",
      Json::null(),
      after=0,
    )
    source_control_ack_v2(commit, "COMMIT")
    if stream.commit_request_seq == 0 ||
      commit.request_seq != stream.commit_request_seq + 1 ||
      stream.next_index != stream.commands.length() {
      fail("mismatch:admission-commit-lifecycle")
    }
    for
      flag in [
        "catalogComponentsChecked", "initialSnapshotComponentsChecked", "initialLedgerComponentsChecked",
        "actualCommitAcknowledged", "actualCommitConfirmed",
      ] {
      source_equal_v4(r.at(flag), Json(true), "V2-acknowledged-installation")
    }
    source_equal_v4(
      r.at("status"),
      Json("installed-components-only"),
      "V2-successful-component-receipt",
    )
    source_equal_v4(r.at("initialRows"), Json(count), "V2-initial-row-count")
    source_equal_v4(
      r.at("initialSnapshotSha256"),
      Json(v3_dislock_sha256(initial_digest.to_string())),
      "V2-initial-snapshot-digest",
    )
    "verified"
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
  let log_digest = v3_dislock_sha256(original_log)
  {
    config,
    policy,
    catalog,
    initial_versions: initial,
    initial_effects,
    log_digest,
    environment,
    record: {
      "format": "moontxnwitness-source-installation-admission/v2",
      "semanticContract": "postgres18-independent-point-source-installation/v2",
      "algorithm": "moonbit-source-installation-triples-2",
      "status": Json(status),
      "installationVerified": Json(status == "verified"),
      "valid": Json(status == "verified"),
      "configSha256": Json(config.digest),
      "installationLogSha256": Json(log_digest),
      "catalog": catalog,
      "environment": environment,
      "initialVersions": Json(initial),
      "initialEffects": Json(initial_effects),
      "initialRows": Json(count),
      "sourceAuthenticated": false,
      "sourceFactsProduced": false,
      "captureFactsProduced": false,
      "completeWindow": false,
      "writerWindowVerified": false,
      "modelCoverageAccepted": false,
      "commitVerified": false,
      "execution": {
        "checks": Json(work.checks),
        "limit": Json(max_checks),
        "maxChecks": Json(max_checks),
      },
      "gaps": [
        Json(
          if reason.is_empty() {
            "installation-verified-source-window-and-model-admission-separate"
          } else {
            reason
          },
        ),
      ],
    },
  }
}
