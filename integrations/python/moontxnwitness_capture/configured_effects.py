"""Read-only export of effects visible in one configured PostgreSQL snapshot."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .configured_session import InstallationInputs, read_text, write_new
from .configured_source import (
    ENVIRONMENT_SQL, SOURCE_CATALOG_SQL, TABLE_CATALOG_SQL, SourceInstallError, SourceInstallPolicy,
    _Control, _one, canonical, identifier, verify_environment, verify_source_catalog, verify_table_catalog,
)
from .configured_sql import SQLCaptureConfig
from .instrumentation import _LifecycleLog


BEGIN = 'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY'
SAFE_PATH = 'SET LOCAL search_path TO pg_catalog, pg_temp'
SNAPSHOT_SQL = ("SELECT pg_catalog.jsonb_build_object('isolation',pg_catalog.current_setting('transaction_isolation'),"
                "'readOnly',pg_catalog.current_setting('transaction_read_only'),"
                "'snapshot',pg_catalog.pg_current_snapshot()::text)::text")
FORMAT = 'moontxnwitness-configured-effects-snapshot/v1'
WRITER_FORMAT = 'moontxnwitness-configured-effects-snapshot/v2'
PEER_SQL = ("pg_catalog.jsonb_build_object('databaseOid',(SELECT oid::bigint FROM pg_catalog.pg_database "
            "WHERE datname=pg_catalog.current_database()),'postmasterStartMicros',"
            "(EXTRACT(EPOCH FROM pg_catalog.pg_postmaster_start_time())*1000000)::bigint::text,"
            "'serverAddress',pg_catalog.host(pg_catalog.inet_server_addr()),'serverPort',pg_catalog.inet_server_port())")
WRITER_PROBE_SQL = ("SELECT pg_catalog.jsonb_build_object('peer'," + PEER_SQL +
                    ",'xid',pg_catalog.pg_current_xact_id_if_assigned()::text,"
                    "'login',SESSION_USER,'pid',pg_catalog.pg_backend_pid())::text")


def effects_snapshot_sql(policy):
    source = identifier(policy.namespace)
    return ("SELECT CASE WHEN pg_catalog.octet_length(p.payload)>16384 THEN '{\"kind\":\"effect-row-budget\"}' "
            "ELSE p.payload END FROM (SELECT e.version,pg_catalog.jsonb_build_object('kind','effect',"
            "'version',e.version::text,'baseVersion',e.base_version::text,'relationOid',e.relation_oid::bigint,"
            "'operation',e.operation,'writerXid',e.writer_xid,'writerLogin',e.writer_login,'writerPid',e.writer_pid,"
            "'rowKey',e.row_key,'oldKey',e.old_key,'rowValues',e.row_values)::text AS payload FROM "
            f"{source}.effects e WHERE e.version>%s::bigint AND e.operation<>'INITIAL' "
            "ORDER BY e.version LIMIT 8) p ORDER BY p.version")


def effects_scope_sql(policy):
    return ("SELECT pg_catalog.jsonb_build_object('relation_oid',s.relation_oid::bigint,"
            "'relation_schema',s.relation_schema,'relation_table',s.relation_table,"
            "'primary_key',s.primary_key,'config_sha256',s.config_sha256)::text FROM "
            f"{identifier(policy.namespace)}.scope s ORDER BY relation_schema,relation_table")


def _ack(control, query_id, sql, tag, state):
    _, response = control.command(query_id, sql, max_rows=0)
    native = response['native']
    if (native['status'], native['tag'], native['fields'], response['transactionStatusAfter']) != (1, tag, 0, state):
        raise SourceInstallError(f'Effects snapshot control acknowledgement differs: {query_id}')


def observe_configured_effects(connection, output, config, policy, installation, *, max_rows=256, opt_in=False,
                               include_writer_peer=False):
    """Seal native and delivered sidecar observations using a dedicated control connection."""
    if opt_in is not True:
        raise ValueError('Explicit opt_in=True is required for a private effects read')
    if type(config) is not SQLCaptureConfig or type(policy) is not SourceInstallPolicy or type(installation) is not InstallationInputs:
        raise ValueError('Explicit configured tables, policy and original installation are required')
    if type(max_rows) is not int or not 0 <= max_rows <= 4096:
        raise ValueError('Effects snapshot max_rows must be an integer from 0 to 4096')
    if type(include_writer_peer) is not bool:
        raise ValueError('include_writer_peer must be a boolean')
    if not connection.autocommit or int(connection.info.transaction_status) != 0:
        raise ValueError('A dedicated idle autocommit control connection is required')
    install_receipt = json.loads(installation.receipt_text)
    if (install_receipt.get('status') != 'installed-components-only'
            or install_receipt.get('actualCommitConfirmed') is not True
            or install_receipt.get('configSha256') != config.sha256
            or json.loads(installation.policy_text) != policy.to_dict()
            or install_receipt.get('policy') != policy.to_dict()):
        raise ValueError('Original confirmed installation with the selected config and policy is required')
    original_digest = hashlib.sha256(installation.log_text.encode('utf-8')).hexdigest()
    if install_receipt.get('log', {}).get('sha256') != original_digest or install_receipt['log'].get('sealed') is not True:
        raise ValueError('Original installation log digest differs')

    path = Path(output).resolve()
    path.mkdir(parents=True, exist_ok=False)
    log = _LifecycleLog(path / 'effects-snapshot.jsonl', max_bytes=min(policy.max_log_bytes, 8 * 1024 * 1024))
    control = _Control(connection, log)
    receipt = {'format': WRITER_FORMAT if include_writer_peer else FORMAT,
               'status': 'failed', 'installationLogSha256': original_digest,
               'configSha256': config.sha256, 'maxRows': max_rows, 'effectsObserved': 0,
               'sourceFactsProduced': False, 'writerWindowVerified': False, 'isolationAnalysisReady': False}
    try:
        _ack(control, 'begin', BEGIN, 'BEGIN', 2)
        _ack(control, 'effects-safe-path', SAFE_PATH, 'SET', 2)
        snapshot = _one(control, 'effects-snapshot-mode', SNAPSHOT_SQL)
        if snapshot.get('isolation') != 'repeatable read' or snapshot.get('readOnly') != 'on' or not snapshot.get('snapshot'):
            raise SourceInstallError('Read-only repeatable snapshot was not observed')
        if include_writer_peer:
            _one(control, 'effects-writer-peer', 'SELECT ' + PEER_SQL + '::text')
        environment = _one(control, 'environment', ENVIRONMENT_SQL, (list(policy.writers),))
        owner = verify_environment(policy, environment)
        if any(environment.get(key) != install_receipt['environment'].get(key) for key in ('database', 'databaseOid', 'owner')):
            raise SourceInstallError('Effects observer does not match the supplied installation identity')
        catalog = _one(control, 'source-catalog', SOURCE_CATALOG_SQL, (policy.namespace,))
        verify_source_catalog(policy, owner, catalog)
        scope, _ = control.command('source-scope', effects_scope_sql(policy), max_rows=16)
        if scope != install_receipt.get('sourceScope'):
            raise SourceInstallError('Private effect scope differs from installation')
        oids = {(row['relation_schema'], row['relation_table']): row['relation_oid'] for row in scope}
        for table in config.tables:
            identity = (table.schema, table.table)
            installed = _one(control, 'installed-catalog', TABLE_CATALOG_SQL, identity)
            if verify_table_catalog(table, policy, owner, installed, installed=True) != oids.get(identity):
                raise SourceInstallError('Effects table identity differs from installation')
        last = 0
        sql = effects_snapshot_sql(policy)
        while True:
            rows, _ = control.command('effects-page', sql, (str(last),), max_rows=8)
            if not rows:
                break
            for row in rows:
                version = row.get('version', '')
                if row.get('kind') != 'effect' or not isinstance(version, str) or not version.isascii() or not version.isdecimal() or len(version) > 19:
                    raise SourceInstallError('Effects row is oversized or has an invalid version')
                current = int(version)
                if not last < current <= 2**63 - 1 or version != str(current):
                    raise SourceInstallError('Effects enumeration did not advance')
                if receipt['effectsObserved'] == max_rows:
                    raise SourceInstallError('Effects snapshot row budget exhausted')
                receipt['effectsObserved'] += 1
                last = current
        _ack(control, 'effects-finish', 'ROLLBACK', 'ROLLBACK', 0)
        receipt['log'] = log.close()
        if not receipt['log']['sealed']:
            raise SourceInstallError('Effects snapshot log was not sealed')
        receipt['status'] = 'observed-snapshot'
    except BaseException as error:
        if int(connection.info.transaction_status) != 0:
            try:
                connection.rollback()
            except Exception:
                receipt['rollbackUnconfirmed'] = True
        receipt['errorClass'] = type(error).__name__
        try:
            receipt['log'] = log.close()
        except Exception:
            receipt['log'] = {'sealed': False}
        write_new(path / 'effects-receipt.json', canonical(receipt) + '\n')
        raise
    target = path / 'effects-receipt.json'
    write_new(target, canonical(receipt) + '\n')
    return target


def configured_effects_input(config, installation, effects_dir):
    """Build a verifier envelope containing the exact retained observation texts."""
    path = Path(effects_dir)
    return {'configText': canonical(config.to_dict()), 'policyText': installation.policy_text,
            'installationLogText': installation.log_text, 'installationReceiptText': installation.receipt_text,
            'effectsLogText': read_text(path / 'effects-snapshot.jsonl', 8 * 1024 * 1024),
            'effectsReceiptText': read_text(path / 'effects-receipt.json', 8192)}
