"""Application startup integration. No connection, query or source DDL on import."""
from pathlib import Path
from moontxnwitness_capture.configured_sql import SQLCaptureConfig
from moontxnwitness_capture.configured_session import ConfiguredDiagnosticSession


def observe_native_factory(factory, output, configuration):
    config = SQLCaptureConfig.from_json(Path(configuration).read_text(encoding="utf-8"))
    session = ConfiguredDiagnosticSession(output, config)
    return session, session.psycopg_factory(factory)


def observe_async_factory(factory, output, configuration):
    config = SQLCaptureConfig.from_json(Path(configuration).read_text(encoding="utf-8"))
    session = ConfiguredDiagnosticSession(output, config)
    return session, session.psycopg_factory(factory, asynchronous=True)


def observe_engine(engine, output, configuration):
    # Install before the application's first connection borrow. Existing borrowed
    # connections cannot be retroactively included in a complete observation.
    config = SQLCaptureConfig.from_json(Path(configuration).read_text(encoding="utf-8"))
    session = ConfiguredDiagnosticSession(output, config)
    session.instrument_engine(engine)  # sync or AsyncEngine via the same adapter
    return session

# Application retains original execution, result-consumption and connection
# ownership. After its workers stop, call session.seal(), then the independent
# diagnostic replay command. A SQLAlchemy hook alone grants no source facts.
