"""Thin integration of a frozen, unmodified upstream lease business component.

The upstream package is imported only when load_upstream()/LeaseClient is used.
No installer, CLI, subprocess command or heartbeat service is started here.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tarfile
import threading
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
COMMIT = "f9946f07159054433d9071c3805e41223cb47856"
ARCHIVE_SHA256 = "78f9be44f0bf0095b64e8c767f933d155d85092c8328afdf5b9749e97c9922d0"
_IMPORT_LOCK = threading.Lock()
_UPSTREAM = None


class SourceIntegrityError(RuntimeError):
    pass


def verify_sources(folder=HERE / "upstream"):
    """Compare extracted files directly to the pinned archive, not just a flag."""
    folder = Path(folder).resolve()
    lock = json.loads((folder / "lock.json").read_text(encoding="utf-8"))
    if lock.get("commit") != COMMIT or lock.get("archiveSha256") != ARCHIVE_SHA256:
        raise SourceIntegrityError("Upstream commit/archive identity changed")
    archive_path = folder / ("dislock-" + COMMIT + ".tar.gz")
    if archive_path.stat().st_size > 4 * 1024 * 1024:
        raise SourceIntegrityError("Upstream archive exceeded the source budget")
    raw = archive_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA256:
        raise SourceIntegrityError("Pinned upstream archive bytes changed")
    archived = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive.getmembers():
            parts = PurePosixPath(member.name).parts
            if len(parts) < 2:
                continue
            relative = str(PurePosixPath(*parts[1:]))
            wanted = relative in ("LICENSE", "README.md", "pyproject.toml") or (
                len(parts) == 3 and parts[1] == "dislock" and parts[-1].endswith(".py"))
            if wanted:
                if not member.isfile() or member.size > 1024 * 1024 or relative in archived:
                    raise SourceIntegrityError("Unexpected upstream archive entry")
                with archive.extractfile(member) as source:
                    archived[relative] = source.read(1024 * 1024 + 1)
    if set(lock["files"]) != set(archived):
        raise SourceIntegrityError("Upstream source manifest set changed")
    for relative, content in archived.items():
        target = folder / "source" / relative
        if not target.is_file() or target.is_symlink() or target.read_bytes() != content:
            raise SourceIntegrityError("Upstream source differs from the fixed archive: " + relative)
        if lock["files"][relative] != {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}:
            raise SourceIntegrityError("Upstream source manifest hash changed")
    actual_python = {p.relative_to(folder / "source").as_posix()
                     for p in (folder / "source" / "dislock").glob("*.py")}
    if actual_python != {p for p in archived if p.endswith(".py")}:
        raise SourceIntegrityError("Unexpected Python module in the frozen package")
    return {"repository": "Actticus/dislock", "commit": COMMIT,
            "archiveSha256": ARCHIVE_SHA256, "archiveBytes": len(raw), "license": "MIT",
            "files": lock["files"], "sourceModified": False}


def load_upstream():
    global _UPSTREAM
    with _IMPORT_LOCK:
        if _UPSTREAM is not None:
            return _UPSTREAM
        evidence = verify_sources()
        package_path = HERE / "upstream" / "source" / "dislock"
        name = "_mtw_frozen_dislock_" + COMMIT
        if name in sys.modules:
            raise SourceIntegrityError("An unexpected module already occupies the frozen import namespace")
        spec = importlib.util.spec_from_file_location(name, package_path / "__init__.py",
                                                      submodule_search_locations=[str(package_path)])
        package = importlib.util.module_from_spec(spec)
        sys.modules[name] = package
        try:
            spec.loader.exec_module(package)
            core = sys.modules[name + ".core"]
            queries = sys.modules[name + "._queries"]
        except BaseException:
            for key in tuple(sys.modules):
                if key == name or key.startswith(name + "."):
                    del sys.modules[key]
            raise
        _UPSTREAM = SimpleNamespace(package=package, core=core, queries=queries, evidence=evidence)
        return _UPSTREAM


class LeaseClient:
    """Delegate SQL and renewal behavior to the original source functions.

    Commit/rollback remain the caller's responsibility, just as for core's
    renew_lease() helper. This does not start the CLI or full LeaseLock service.
    """
    def __init__(self, schema, table="key_value"):
        self.table_parts = [schema, table]
        self.upstream = load_upstream()

    def read_query(self):
        return self.upstream.queries.read_current_query(self.table_parts)

    def renew_query(self):
        return self.upstream.queries.renew_lease_query(self.table_parts)

    def read_current(self, connection, key):
        with connection.cursor() as cursor:
            cursor.execute(self.read_query(), (key,))
            return cursor.fetchone()

    def renew(self, connection, key, ttl_seconds, owner):
        return self.upstream.core.renew_lease(connection, self.table_parts, key, ttl_seconds, owner)

    def acquire_before_capture(self, connection, key, ttl_seconds, owner):
        return self.upstream.core.try_acquire_run_lock(connection, self.table_parts, key, ttl_seconds, owner)


def observed_sql(read_sql, write_sql, version_identifier):
    """Edit only two literal projections known from the frozen source.

    This is not a parser. A changed upstream shape fails instead of guessing.
    """
    read_marker, write_marker = "SELECT expire_at, value", "RETURNING expire_at;"
    if read_sql.count(read_marker) != 1 or write_sql.count(write_marker) != 1:
        raise SourceIntegrityError("Frozen upstream SQL projection shape changed")
    read = read_sql.replace(read_marker, read_marker + "," + version_identifier + "::text", 1)
    write = write_sql.replace(write_marker, "RETURNING expire_at,OLD." + version_identifier
                             + "::text,NEW." + version_identifier + "::text;", 1)
    return read, write


def make_capture(setup, schema, *, table="key_value", keys, exclusive_writers=False, **budgets):
    """Prepare root's explicit RETURNING profile; initialize() is still required."""
    provenance = REPO_ROOT / "experiments" / "provenance"
    if str(provenance) not in sys.path:
        sys.path.insert(0, str(provenance))
    from prototype import Names, identifier
    from returning_profile import ReturningColumnCapture, ReturningPointProfile
    client = LeaseClient(schema, table)
    n = Names(schema, table, "column", "key", "expire_at")
    read = client.read_query().as_string(setup)
    write = client.renew_query().as_string(setup)
    observed_read, observed_write = observed_sql(read, write, identifier(n.version_column))
    profile = ReturningPointProfile(schema=schema, table=table, key_column="key", value_column="expire_at",
        read_sql=read, write_sql=write, observed_read_sql=observed_read, observed_write_sql=observed_write,
        read_columns=2, returning_columns=1, write_key_parameter=1)
    capture = ReturningColumnCapture(profile, keys=keys, exclusive_writers=exclusive_writers, **budgets)
    return capture, client
