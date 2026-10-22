"""Bounded admission and one-attempt initialization for the isolated candidate.

The confirmation is bounded collector diagnostics, not an addition to traceSchema
1/2 and not an authenticated SQL/core proof or a crash-durability guarantee.
"""
from .capture import _status
from ._provenance import ProvenanceError


def bounded_keys(values):
    """Admit 1..64 distinct native text keys, consuming at most 65 items."""
    if isinstance(values, (str, bytes, bytearray)):
        raise ValueError("Pass an iterable of 1..64 distinct text keys")
    iterator = iter(values)
    items = []
    for _ in range(65):
        try:
            item = next(iterator)
        except StopIteration:
            break
        items.append(item)
    if not 1 <= len(items) <= 64:
        raise ValueError("Declare 1..64 distinct text keys")
    # Exact native strings avoid application-defined hash/encoding callbacks.
    if any(type(item) is not str or not 0 < len(item) <= 512 or "\x00" in item
           for item in items):
        raise ValueError("Keys must be nonempty native text without NUL")
    try:
        valid = all(len(item.encode("utf8")) <= 512 for item in items)
    except UnicodeError:
        valid = False
    if not valid or len(set(items)) != len(items):
        raise ValueError("Distinct UTF-8 keys of at most 512 bytes required")
    return tuple(items)


def _safe_gap(capture, code, message):
    # This runs only in failure/diagnostic paths. An observer fault must not
    # replace a primary business-driver exception, including BaseException.
    try:
        capture.gap(code, message)
    except BaseException:
        pass


def begin_initialization(capture, connection):
    with capture._lock:
        if getattr(capture, "_initialization_attempted", False):
            raise ProvenanceError("Initialization is one attempt; create a new observer after failure")
        capture._initialization_attempted = True
        capture._initialization_failed = False
        capture._initialization_ack = None
        try:
            if capture._closed or capture._capture_exhausted or capture._log_failed or capture._gaps:
                raise ProvenanceError("Initialize only a fresh usable observer")
            capture._check_initialization(connection)
        except BaseException:
            capture._initialization_failed = True
            _safe_gap(capture, "initialization_failed", "Setup admission failed; this observer cannot retry.")
            raise


def confirm_initial_commit(capture, connection):
    """Observe the actual COMMIT result before any snapshot is published."""
    before = _status(connection)
    try:
        result = connection.execute("COMMIT")
        tag, status = result.statusmessage, result.pgresult.status
        description, after = result.description, _status(connection)
    except BaseException:
        _safe_gap(capture, "initialization_commit_unknown", "Setup COMMIT did not supply a usable confirmation.")
        raise
    bounded_tag = type(tag) is str and len(tag) <= 128
    native_status = isinstance(status, int) and type(status) is not bool
    status_value = int(status) if native_status else None
    confirmed = (before == 2 and after == 0 and bounded_tag and tag == "COMMIT"
                 and native_status and status_value == 1 and description is None)
    capture._initialization_ack = {
        "sql": "COMMIT", "statusBefore": before, "statusAfter": after,
        "commandTag": tag if bounded_tag else None,
        "pgStatus": status_value, "noRows": description is None,
        "actualCommitConfirmed": confirmed,
    }
    if not confirmed:
        _safe_gap(capture, "initialization_ack_invalid", "Setup COMMIT tag/result/status did not confirm initialization.")
        raise ProvenanceError("Initial COMMIT requires INTRANS, COMMIT/COMMAND_OK, no rows and IDLE")


def fail_initialization(capture, connection):
    """Called inside the original except; never replace its active exception."""
    capture._initialization_failed = True
    capture._initialized = False
    capture.installation = None
    _safe_gap(capture, "initialization_failed", "Owned setup and initial snapshot were not established; no retry is allowed.")
    try:
        connection.rollback()
    except BaseException:
        _safe_gap(capture, "initialization_rollback_unknown", "Cleanup rollback was not acknowledged; inspect the owned schema.")
