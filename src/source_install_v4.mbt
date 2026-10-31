///|
pub struct SourceInstallationCheckV4 {
  priv record : Json
  priv config : SQLConfigV1
  priv installed_catalogs : Array[Json]
  priv initial_versions : Map[String, Json]
  priv log_digest : String
}

///|
pub fn source_installation_check_v4_json(
  result : SourceInstallationCheckV4,
) -> Json {
  v4_json_copy(result.record)
}

///|
fn source_install_record_fields_v4() -> Array[String] {
  [
    "format", "config", "policy", "configSha256", "sourceFactsProduced", "sourceAuthenticated",
    "moonbitCatalogVerified", "catalogVerified", "initialSnapshotVerified", "writerWindowVerified",
    "driverFetchVerified", "status", "gaps", "environment", "initializationLocks",
    "sourceCatalog", "sourceScope", "initialLedger", "actualCommitConfirmed", "initialRows",
    "initialSnapshotSha256", "tables", "log",
  ]
}

///|
fn source_ddl_ack_v4(command : SourceCommandV4) -> Unit raise {
  let n = source_object_v4(command.native)
  let sql = command.sql
  if n.at("status") != Json(1) || n.at("fields") != Json(0) {
    fail("mismatch:source-DDL-status")
  }
  let tag = sql_string_v1(n.at("tag"))
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
  } else if sql.has_prefix("UPDATE ") {
    "UPDATE"
  } else {
    fail("unsupported:source-DDL-command")
  }
  if expected == "UPDATE" {
    if !tag.has_prefix("UPDATE ") || !sql_digits_v1(tag[7:].to_owned()) {
      fail("mismatch:source-DDL-update-tag")
    }
  } else if tag != expected {
    fail("mismatch:source-DDL-tag")
  }
}

///|
fn source_version_after_v4(value : String, previous : String) -> Bool {
  value.length() > previous.length() ||
  (value.length() == previous.length() && value > previous)
}

///|
pub fn verify_source_installation_v4(
  config : SQLConfigV1,
  policy_value : Json,
  original_log : String,
  receipt : Json,
  max_checks~ : Int32 = 1000000,
) -> SourceInstallationCheckV4 {
  let work : SourceWorkV4 = { limit: max_checks, checks: 0, }
  let catalogs : Array[Json] = []
  let initial : Map[String, Json] = Map([])
  let mut rows = 0
  let mut reason = ""
  let mut environment : Json = Json::null()
  let mut final_request_seq = 0
  let mut final_result_seq = 0
  let mut bindings : Array[Json] = []
  let status = try {
    if max_checks < 0 || max_checks > 1000000 {
      fail("invalid:source-caller-budget")
    }
    work.charge()
    let policy = source_policy_v4(policy_value)
    if config.tables.is_empty() ||
      config.tables.length() > 16 ||
      config.tables.any(t => {
        t.columns.any(c => c.name == "__mtw_source_version")
      }) {
      fail("unsupported:source-configured-scope")
    }
    let r = source_object_v4(receipt)
    known_fields(r, source_install_record_fields_v4(), "source-install-receipt")
    source_equal_v4(
      r.at("format"),
      Json("configured-source-installation/v1"),
      "receipt-format",
    )
    source_equal_v4(r.at("config"), config.record, "caller-config")
    source_equal_v4(r.at("configSha256"), Json(config.digest), "config-digest")
    source_equal_v4(r.at("policy"), policy.record, "caller-policy")
    // Component booleans such as catalogVerified never authorize these checks.
    for
      flag in [
        "sourceFactsProduced", "sourceAuthenticated", "moonbitCatalogVerified", "writerWindowVerified",
        "driverFetchVerified",
      ] {
      source_equal_v4(r.at(flag), Json(false), "unproven-producer-claim")
    }
    let stream = source_parse_stream_v4(original_log, receipt, policy, work)
    source_command_ack_v4(stream.next("begin", "BEGIN", Json::null()), "BEGIN")
    source_command_ack_v4(
      stream.next(
        "standard-strings",
        "SET LOCAL standard_conforming_strings=on",
        Json::null(),
      ),
      "SET",
    )
    let sorted_tables = config.tables.map(t => t)
    sorted_tables.sort_by((a, b) => {
      let schema_order = relation_v3_text_compare(a.schema, b.schema)
      if schema_order == 0 {
        relation_v3_text_compare(a.name, b.name)
      } else {
        schema_order
      }
    })
    let targets : Array[String] = []
    for table in sorted_tables {
      targets.push(source_target_v4(table))
    }
    source_command_ack_v4(
      stream.next(
        "install-lock",
        "LOCK TABLE " + targets.join(",") + " IN ACCESS EXCLUSIVE MODE NOWAIT",
        Json::null(),
      ),
      "LOCK TABLE",
    )
    environment = stream.one(
      "environment",
      source_v4_environment_sql(),
      Json([Json(policy.writers.map(writer => Json(writer)))]),
    )
    let owner = source_environment_v4(environment, policy, work)
    source_equal_v4(r.at("environment"), environment, "receipt-environment")
    let before_catalogs : Array[Json] = []
    let oids : Array[Json] = []
    let oid_texts : Array[String] = []
    for table in config.tables {
      let catalog = stream.one(
        "before-catalog",
        source_v4_table_catalog_sql(),
        Json([Json(table.schema), Json(table.name)]),
      )
      let oid = source_table_catalog_v4(
        table, policy, owner, catalog, false, work,
      )
      if oid_texts.contains(oid) {
        fail("mismatch:source-duplicate-table-OID")
      }
      oid_texts.push(oid)
      oids.push(source_object_v4(catalog).at("oid"))
      before_catalogs.push(catalog)
      for writer in policy.writers {
        let target = source_target_v4(table)
        let privileges = stream.one(
          "business-writer-privileges",
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
        let p = orm_exact(privileges, [
          "role", "table", "trigger", "truncate", "ownerMembership",
        ])
        if p.at("role") != Json(writer) || p.at("table") != Json(target) {
          fail("mismatch:source-permission-identity")
        }
        for flag in ["trigger", "truncate", "ownerMembership"] {
          if p.at(flag) != Json(false) {
            fail("unsupported:source-permission-bypass")
          }
        }
      }
    }
    let held = stream.one(
      "held-install-locks",
      source_v4_locks_sql(),
      Json([Json(oids)]),
    )
    let h = orm_exact(held, ["pid", "locks"])
    source_equal_v4(
      h.at("pid"),
      source_object_v4(environment).at("backendPid"),
      "lock-backend",
    )
    let locked : Array[String] = []
    for lock in orm_array(h.at("locks")) {
      work.charge()
      let l = orm_exact(lock, ["relation", "mode", "granted"])
      let oid = source_oid_v4(l.at("relation"))
      if !oid_texts.contains(oid) {
        fail("mismatch:source-unrequested-lock")
      }
      if l.at("mode") == Json("AccessExclusiveLock") &&
        l.at("granted") == Json(true) {
        if locked.contains(oid) {
          fail("mismatch:source-duplicate-lock")
        }
        locked.push(oid)
      }
    }
    if locked.length() != oids.length() {
      fail("mismatch:source-initialization-locks")
    }
    source_equal_v4(r.at("initializationLocks"), held, "receipt-locks")
    let ddl_update_counts : Array[String] = []
    for statement in source_ddl_v4(config, policy) {
      let command = stream.next("install-ddl", statement, Json::null())
      source_ddl_ack_v4(command)
      if statement.has_prefix("UPDATE ") {
        ddl_update_counts.push(
          sql_string_v1(source_object_v4(command.native).at("tag"))[7:].to_owned(),
        )
      }
    }
    let initial_digest = StringBuilder()
    let keys : Map[String, Bool] = Map([])
    let expected_scope : Array[Json] = []
    let receipt_tables : Array[Json] = []
    let q = v3_dislock_quote(policy.source_schema)
    for index, table in config.tables {
      work.charge()
      let oid = oids[index]
      source_command_ack_v4(
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
      let initial_ledger = stream.next(
        "initial-ledger",
        "INSERT INTO " +
        q +
        ".effects(version,base_version,relation_oid,operation,writer_xid,writer_login,writer_pid,row_key,old_key,row_values) SELECT \"__mtw_source_version\",NULL,%s,'INITIAL',pg_catalog.pg_current_xact_id()::text,SESSION_USER,pg_catalog.pg_backend_pid(),pg_catalog.to_jsonb(t)->%s,NULL,pg_catalog.to_jsonb(t)-%s FROM " +
        source_target_v4(table) +
        " t",
        Json([oid, Json(table.key), Json("__mtw_source_version")]),
      )
      let mut previous : Json = Json(0)
      let mut previous_text = "0"
      let mut count = 0
      while true {
        let snapshot = stream.next(
          "initial-snapshot",
          source_snapshot_sql_v4(table),
          Json([previous]),
        )
        if snapshot.decoded.length() > 1 {
          fail("mismatch:source-snapshot-paging")
        }
        if snapshot.decoded.is_empty() {
          break
        }
        let observation = orm_exact(snapshot.decoded[0], ["kind", "row"])
        if observation.at("kind") != Json("initial-row") {
          fail("unsupported:source-row-budget-marker")
        }
        let row = source_object_v4(observation.at("row"))
        let expected_names = table.columns.map(c => c.name)
        expected_names.push("__mtw_source_version")
        known_fields(row, expected_names, "source-initial-row")
        if row.length() != expected_names.length() {
          fail("mismatch:source-initial-columns")
        }
        let version = source_positive_v4(row.at("__mtw_source_version"))
        if !source_version_after_v4(version, previous_text) ||
          initial.contains(version) {
          fail("mismatch:source-initial-version")
        }
        for column in table.columns {
          work.charge()
          let _ = sql_typed_value_v1(row.at(column.name), column.kind, 65536)
        }
        let mut key_kind = ""
        for column in table.columns {
          if column.name == table.key {
            key_kind = column.kind
          }
        }
        if key_kind.is_empty() {
          fail("mismatch:source-key-config")
        }
        let key = sql_canonical_v1(
          Json([
            Json(table.schema),
            Json(table.name),
            sql_typed_value_v1(row.at(table.key), key_kind, 65536),
          ]),
        )
        if keys.contains(key) {
          fail("mismatch:source-duplicate-initial-key")
        }
        keys[key] = true
        let source : Json = {
          "schema": Json(table.schema),
          "table": Json(table.name),
          "tableOid": oid,
          "version": row.at("__mtw_source_version"),
          "row": observation.at("row"),
          "requestSeq": Json(snapshot.request_seq),
          "resultSeq": Json(snapshot.result_seq),
        }
        initial[version] = source
        initial_digest.write_string(
          sql_canonical_v1({
            "schema": Json(table.schema),
            "table": Json(table.name),
            "row": observation.at("row"),
          }),
        )
        initial_digest.write_string("\n")
        previous = row.at("__mtw_source_version")
        previous_text = version
        count += 1
        rows += 1
        if rows > policy.max_initial {
          fail("budget:source-initial-rows")
        }
      }
      source_command_ack_v4(initial_ledger, "INSERT 0 " + count.to_string())
      if index >= ddl_update_counts.length() ||
        ddl_update_counts[index] != count.to_string() {
        fail("mismatch:source-initial-update-count")
      }
      let after = stream.one(
        "installed-catalog",
        source_v4_table_catalog_sql(),
        Json([Json(table.schema), Json(table.name)]),
      )
      if source_table_catalog_v4(table, policy, owner, after, true, work) !=
        oid_texts[index] {
        fail("mismatch:source-catalog-OID-changed")
      }
      let before_fields = source_object_v4(before_catalogs[index])
      let before_columns = orm_array(before_fields.at("columns"))
      let after_fields = source_object_v4(after)
      let after_columns = orm_array(after_fields.at("columns"))
      for column_index, original_column in before_columns {
        work.charge()
        source_equal_v4(
          after_columns[column_index],
          original_column,
          "business-column-changed",
        )
      }
      source_equal_v4(
        after_fields.at("primaryKeys"),
        before_fields.at("primaryKeys"),
        "primary-key-changed",
      )
      catalogs.push(after)
      receipt_tables.push({ "catalog": after, "initialRows": Json(count) })
      bindings.push({
        "schema": Json(table.schema),
        "table": Json(table.name),
        "tableOid": oid,
        "versionColumn": "__mtw_source_version",
        "versionColumnPosition": Json(table.columns.length() + 1),
        "initialRows": Json(count),
      })
      expected_scope.push({
        "relation_oid": oid,
        "relation_schema": Json(table.schema),
        "relation_table": Json(table.name),
        "primary_key": Json(table.key),
        "config_sha256": Json(config.digest),
      })
    }
    let source_catalog = stream.one(
      "source-catalog",
      source_v4_source_catalog_sql(),
      Json([Json(policy.source_schema)]),
    )
    source_private_catalog_v4(source_catalog, policy, owner, work)
    source_equal_v4(
      r.at("sourceCatalog"),
      source_catalog,
      "receipt-private-catalog",
    )
    let ordered_scope : Array[Json] = []
    for table in sorted_tables {
      for item in expected_scope {
        work.charge()
        let entry = source_object_v4(item)
        if entry.at("relation_schema") == Json(table.schema) &&
          entry.at("relation_table") == Json(table.name) {
          ordered_scope.push(item)
        }
      }
    }
    let scope = stream.next(
        "source-scope",
        "SELECT pg_catalog.jsonb_build_object('relation_oid',s.relation_oid::bigint,'relation_schema',s.relation_schema,'relation_table',s.relation_table,'primary_key',s.primary_key,'config_sha256',s.config_sha256)::text FROM " +
        q +
        ".scope s ORDER BY relation_schema,relation_table",
        Json::null(),
      ).decoded
    source_equal_v4(Json(scope), Json(ordered_scope), "scope-inventory")
    source_equal_v4(r.at("sourceScope"), Json(scope), "receipt-scope")
    let ledger = stream.one(
      "initial-ledger-count",
      "SELECT pg_catalog.jsonb_build_object('rows',count(*),'nonInitial',count(*) FILTER(WHERE operation<>'INITIAL'))::text FROM " +
      q +
      ".effects",
      Json::null(),
    )
    source_equal_v4(
      ledger,
      { "rows": Json(rows), "nonInitial": 0 },
      "initial-ledger",
    )
    source_equal_v4(r.at("initialLedger"), ledger, "receipt-initial-ledger")
    let commit = stream.next("installation-commit", "COMMIT", Json::null())
    source_command_ack_v4(commit, "COMMIT")
    if stream.commit_request_seq != commit.request_seq - 1 ||
      stream.next_index != stream.commands.length() {
      fail("mismatch:source-commit-order-or-extra-command")
    }
    final_request_seq = commit.request_seq
    final_result_seq = commit.result_seq
    source_equal_v4(
      r.at("actualCommitConfirmed"),
      Json(true),
      "receipt-commit-ack",
    )
    source_equal_v4(r.at("initialRows"), Json(rows), "receipt-initial-count")
    source_equal_v4(
      r.at("initialSnapshotSha256"),
      Json(v3_dislock_sha256(initial_digest.to_string())),
      "receipt-initial-digest",
    )
    source_equal_v4(
      r.at("tables"),
      Json(receipt_tables),
      "receipt-installed-tables",
    )
    "matched-components"
  } catch {
    error => {
      reason = error.to_string()
      if reason.contains("mismatch:") || reason.contains("parameter:") {
        "mismatch"
      } else if reason.contains("invalid:") {
        "invalid"
      } else {
        "unknown"
      }
    }
  }
  let complete = status == "matched-components"
  if !complete {
    bindings = []
  }
  {
    record: {
      "format": "moontxnwitness-source-installation-check/v4",
      "semanticContract": "configured-installation-components/v4-1",
      "algorithm": "independent-control-native-catalog-initial-1",
      "counterContract": "source-component-check-counters/v4-1",
      "status": Json(status),
      "valid": Json(complete),
      "catalogComponentVerified": Json(complete),
      "initialSnapshotComponentVerified": Json(complete),
      "actualCommitResponseVerified": Json(complete),
      "sourceFactsProduced": false,
      "sourceAuthenticated": false,
      "writerWindowVerified": false,
      "driverFetchVerified": false,
      "isolationModelChecked": false,
      "configSha256": Json(config.digest),
      "installationLogSha256": Json(v3_dislock_sha256(original_log)),
      "installationReceiptCanonicalSha256": Json(
        v3_dislock_sha256(sql_canonical_v1(receipt)),
      ),
      "initialRows": Json(rows),
      "bindings": Json(bindings),
      "environment": if complete {
        environment
      } else {
        Json::null()
      },
      "commitRequestSeq": Json(final_request_seq),
      "commitResultSeq": Json(final_result_seq),
      "execution": {
        "checks": Json(work.checks),
        "maxChecks": Json(max_checks),
        "limited": Json(reason.contains("budget:")),
      },
      "gaps": Json([
        Json("writer-window-not-closed"),
        Json("privileged-DDL-exclusion-not-proven"),
        Json("business-fetch-source-projection-not-connected"),
      ]),
      "reason": Json(reason),
    },
    config,
    installed_catalogs: catalogs,
    initial_versions: initial,
    log_digest: v3_dislock_sha256(original_log),
  }
}
