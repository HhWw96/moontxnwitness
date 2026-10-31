"""One configured diagnostic session, with optional explicit source installation.

No global driver patches, business SQL rewriting, eager result consumption or
model fact promotion. Default construction performs no database operation.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
import hashlib
import inspect
import json
import os
from pathlib import Path
import stat
from .configured_sql import SQLCaptureConfig, ColumnConfig, TableConfig, ConfiguredSQLParser
from .configured_fetch import ConfiguredInstrumentation, StoredColumnObservation
from .configured_source import SourceInstallPolicy, VERSION_COLUMN, install_configured_source

INPUT_FORMAT = 'moontxnwitness-configured-session-input/v1'
INSTALL_INPUT_FORMAT = 'moontxnwitness-configured-installation-input/v1'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def read_text(path, maximum):
    path = Path(path)
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or getattr(st, 'st_file_attributes', 0) & 0x400:
        raise ValueError('A regular retained observation file is required')
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('Original observation text exceeds its verifier bound; no truncation is permitted')
    return raw.decode('utf-8', errors='strict')


def write_new(path, raw):
    path = Path(path)
    if type(raw) is str:
        raw = raw.encode('utf-8')
    with path.open('xb') as stream:
        if stream.write(raw) != len(raw):
            raise OSError('Short diagnostic artifact write')
        stream.flush()
        os.fsync(stream.fileno())


def augmented_source_config(config):
    """Derive the installed-column grammar, never rewrite a business statement."""
    if type(config) is not SQLCaptureConfig:
        raise ValueError('Immutable SQLCaptureConfig required')
    tables = []
    for table in config.tables:
        if len(table.columns) >= 128 or any(c.name == VERSION_COLUMN for c in table.columns):
            raise ValueError('Installed metadata collides with business columns or exceeds fetch capacity')
        tables.append(TableConfig(table.schema, table.table, table.primary_key,
                                  table.columns + (ColumnConfig(VERSION_COLUMN, 'int64'),), table.model))
    return replace(config, tables=tuple(tables))


@dataclass(frozen=True, slots=True)
class InstallationInputs:
    policy_text: str
    log_text: str
    receipt_text: str
    context_text: str

    def to_dict(self):
        return {'format': INSTALL_INPUT_FORMAT, 'policyText': self.policy_text,
                'logText': self.log_text, 'receiptText': self.receipt_text,
                'sourceContextText': self.context_text}

    @classmethod
    def from_attempt(cls, path, policy):
        """Preserve exact original bytes; Python receipt booleans grant no fact."""
        if type(policy) is not SourceInstallPolicy:
            raise ValueError('Immutable explicit source policy required')
        path = Path(path)
        original_log = read_text(path / 'source-install.jsonl', 8 * 1024 * 1024)
        original_receipt = read_text(path / 'receipt.json', 2 * 1024 * 1024)
        decoded = json.loads(original_receipt)
        database_oid = decoded.get('environment', {}).get('databaseOid')
        if type(database_oid) is not int or not 0 < database_oid < 2**32:
            raise ValueError('Observed installation database OID is unavailable')
        context = {'format': 'caller-asserted-installation-epoch/v1',
                   'installationLogSha256': hashlib.sha256(original_log.encode('utf-8')).hexdigest(),
                   'databaseOid': database_oid}
        return cls(canonical(policy.to_dict()), original_log, original_receipt, canonical(context))


class ConfiguredDiagnosticSession:
    """Install before first borrow; close after workers stop, then seal a bundle.

    Application connection and result ownership stay with the application.
    Unknown SQL is still executed by the existing observer and remains diagnostic.
    """
    def __init__(self, output, config, *, installation=None, **observer_options):
        if type(config) is not SQLCaptureConfig:
            raise ValueError('Immutable SQLCaptureConfig required')
        if installation is not None and type(installation) is not InstallationInputs:
            raise ValueError('Explicit original installation inputs required')
        self.config = config
        self.capture_config = augmented_source_config(config) if installation is not None else config
        self.installation = installation
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        declarations = tuple(StoredColumnObservation(t.schema, t.table, VERSION_COLUMN)
                             for t in self.capture_config.tables) if installation is not None else ()
        self.observer = ConfiguredInstrumentation(self.output / 'capture', self.capture_config,
                                                  stored_columns=declarations, **observer_options)
        self._sealed = False

    def psycopg_factory(self, factory, *, asynchronous=False):
        return self.observer.psycopg_factory(factory, asynchronous=asynchronous)

    def instrument_engine(self, engine):
        self.observer.attach_engine(engine)
        return self

    def wrap_connection(self, raw, *, asynchronous=False):
        return self.observer.wrap_async(raw) if asynchronous else self.observer.wrap(raw)

    def seal(self):
        if self._sealed:
            raise ValueError('Diagnostic session already sealed')
        self.observer.close()  # never source_closed=True
        trace_path = self.output / 'diagnostic-trace.json'
        trace_receipt = self.observer.export_diagnostic(trace_path)
        lifecycle_text = read_text(self.output / 'capture/lifecycle.jsonl', 8 * 1024 * 1024)
        trace_text = read_text(trace_path, 8 * 1024 * 1024)
        bundle = {'format': INPUT_FORMAT, 'configText': canonical(self.config.to_dict()),
                  'lifecycleText': lifecycle_text, 'diagnosticTraceText': trace_text,
                  'sourceInputsText': canonical(self.installation.to_dict()) if self.installation else 'null'}
        text = canonical(bundle) + '\n'
        if len(text.encode('utf-8')) > 32 * 1024 * 1024:
            raise ValueError('Combined original bundle exceeds bound; raw source files are preserved')
        target = self.output / 'configured-session-input.json'
        write_new(target, text)
        receipt = {'format': 'configured-session-producer-receipt/v1', 'diagnosticOnly': True,
                   'sourceFactsProduced': False, 'writerWindowVerified': False,
                   'sourceAuthenticated': False, 'serverInstanceIdentityAuthenticated': False, 'isolationModelChecked': False,
                   'isolationAnalysisReady': False, 'bundleSha256': hashlib.sha256(text.encode()).hexdigest(),
                   'lifecycleSha256': hashlib.sha256(lifecycle_text.encode()).hexdigest(),
                   'diagnosticTrace': trace_receipt,
                   'controlConnectionClaimIsAuthentication': False}
        write_new(self.output / 'session-receipt.json', canonical(receipt) + '\n')
        self._sealed = True
        return target


def install_and_capture_initial_reads(connection, output, config, policy, queries, *, opt_in=False):
    """Explicit read-only smoke controller on one caller-owned physical connection.

    Tables/roles must already be configured in an owned PostgreSQL 18 database.
    The controller does not create a server, table, business row or test account.
    Same-object reuse is a producer observation, not server authentication.
    """
    if opt_in is not True:
        raise ValueError('Explicit opt_in=True is required before source DDL')
    capture_config = augmented_source_config(config)  # before any database operation
    if type(policy) is not SourceInstallPolicy or type(queries) is not tuple or not 1 <= len(queries) <= 128:
        raise ValueError('Explicit policy and 1..128 immutable original SELECT requests required')
    parser = ConfiguredSQLParser(capture_config)
    for sql, parameters in queries:
        plan = parser.recognize(sql)
        if plan.operation != 'select':
            raise ValueError('The owned same-connection smoke controller executes only supported original SELECTs')
        plan.bind(parameters)  # invalid SQL/parameters cannot follow a committed migration
    if inspect.iscoroutinefunction(connection.commit) or inspect.iscoroutinefunction(connection.cursor):
        raise ValueError('Explicit initial-read installation controller requires a synchronous dedicated connection')
    if not connection.autocommit or int(connection.info.transaction_status) != 0:
        raise ValueError('Dedicated idle autocommit installation connection required')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    attempt = output / 'installation'
    installed = install_configured_source(connection, attempt, config, policy, opt_in=True).to_dict()
    context = InstallationInputs.from_attempt(attempt, policy)
    if installed.get('actualCommitConfirmed') is not True or int(connection.info.transaction_status) != 0:
        raise ValueError('Source installation COMMIT is unresolved; inspect this owned attempt before retry')
    expected_pid = installed['environment']['backendPid']
    if getattr(connection.info, 'backend_pid', None) != expected_pid:
        raise ValueError('Physical connection changed after installation')
    connection.autocommit = False
    session = None
    delivered = []
    try:
        session = ConfiguredDiagnosticSession(output / 'diagnostic', config, installation=context)
        wrapped = session.wrap_connection(connection)
        for sql, parameters in queries:
            cursor = wrapped.cursor()
            try:
                cursor.execute(sql, parameters)
                rows = cursor.fetchall()  # this explicit demo is the real result consumer
                delivered.append({'sqlSha256': hashlib.sha256(sql.encode()).hexdigest(),
                                  'actualReturnedRows': len(rows)})
            finally:
                cursor.close()
        wrapped.rollback()
        bundle = session.seal()
        write_new(output / 'same-connection-execution.json', canonical({
            'format': 'configured-same-connection-execution/v1', 'actualDatabaseExecution': True,
            'originalQueriesExecutedUnchanged': True, 'samePhysicalConnectionReused': True,
            'observedBackendPid': expected_pid, 'returnedResults': delivered,
            'sourceFactsProduced': False, 'writerWindowVerified': False,
            'sourceAuthenticated': False, 'serverInstanceIdentityAuthenticated': False, 'isolationModelChecked': False,
            'isolationAnalysisReady': False,
            'scope': 'actual same-object installation and initial reads; no complete writer window or authentication'}) + '\n')
        return bundle
    finally:
        if session is not None and not session._sealed:
            try:
                session.observer.close()
            except BaseException:
                pass
        try:
            connection.rollback()
            if int(connection.info.transaction_status) == 0:
                connection.autocommit = True
        except BaseException:
            pass  # no unresolved response is changed into a confirmed outcome
