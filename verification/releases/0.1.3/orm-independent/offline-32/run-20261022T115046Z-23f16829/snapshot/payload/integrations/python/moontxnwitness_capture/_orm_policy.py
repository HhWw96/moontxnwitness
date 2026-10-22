"""Relocated fixed ORM SQL and source decoders; no general SQL coverage."""
from __future__ import annotations
import asyncio
from contextlib import contextmanager
import json
import threading
import uuid
import sqlalchemy
from sqlalchemy import Boolean, Column, MetaData, String, Table, bindparam, delete, insert, select, update
from sqlalchemy.dialects.postgresql import UUID, psycopg as pg_dialect
from .capture import CaptureSession, _Budget, _CaptureBudgetError, _measure_json
from .orm import (CoverageRequired, UserScope, PlanKey, SQLPlan, SQLContext,
    DEFAULT_CONTEXT, PROFILE, FIELDS, VALUES, VERSION, PAYLOAD_CHARS)

def _table(scope):
    return Table(scope.table, MetaData(schema=scope.schema),
        Column("id", UUID(as_uuid=True), primary_key=True),
        Column("email", String(320), nullable=False),
        Column("hashed_password", String(1024), nullable=False),
        Column("is_active", Boolean, nullable=False),
        Column("is_superuser", Boolean, nullable=False),
        Column("is_verified", Boolean, nullable=False))


def _payload(prefix):
    pairs = ["'id'", prefix + '.id::uuid::text']
    for field in VALUES:
        pairs += ["'" + field + "'", prefix + "." + field]
    # This bounds the observer's byte copy before PGresult.get_value; values
    # still must validate against the full six-column relation contract.
    return "jsonb_build_object(" + ",".join(pairs) + ")::text::varchar(" + str(PAYLOAD_CHARS) + ")"


def build(scope, operation, fields=(), pk_bind="id_1", *, context=DEFAULT_CONTEXT):
    if type(context) is not SQLContext or sqlalchemy.__version__ != context.sqlalchemy_version:
        raise CoverageRequired("The fixed ORM compiler requires SQLAlchemy " + context.sqlalchemy_version)
    if operation not in ("get", "create", "update", "delete"):
        raise CoverageRequired("Only exact base-user point CRUD is supported")
    canonical = tuple(field for field in VALUES if field in fields)
    if operation == "update" and (not canonical or len(canonical) != len(fields) or len(set(fields)) != len(fields)):
        raise CoverageRequired("Update must use declared non-PK fields exactly once")
    if operation != "update" and fields:
        raise CoverageRequired("Unexpected projection/update fields")
    allowed_pk = {"get": ("id_1", "pk_1"), "create": ("id",),
        "update": (scope.table + "_id", scope.schema + "_" + scope.table + "_id"), "delete": ("id",)}[operation]
    if pk_bind not in allowed_pk:
        raise CoverageRequired("Unrecognized pinned SQLAlchemy bind layout")
    table, dialect = _table(scope), pg_dialect.dialect()
    if operation == "get":
        statement = select(table).where(table.c.id == bindparam(pk_bind, type_=UUID()))
    elif operation == "create":
        statement = insert(table).values({field: bindparam(field) for field in FIELDS})
    elif operation == "update":
        statement = update(table).where(table.c.id == bindparam(pk_bind, type_=UUID())).values({field: bindparam(field) for field in canonical})
    else:
        statement = delete(table).where(table.c.id == bindparam(pk_bind, type_=UUID()))
    original = str(statement.compile(dialect=dialect))
    prepared = dialect.identifier_preparer
    qualified = prepared.format_table(table)
    state = prepared.quote_schema(scope.schema) + '.' + prepared.quote("_mtw_orm_state")
    predecessor = prepared.quote_schema(scope.schema) + '.' + prepared.quote("_mtw_orm_predecessor")
    deleted = prepared.quote_schema(scope.schema) + '.' + prepared.quote("_mtw_orm_deleted_version")
    version = prepared.quote(VERSION)
    if operation == "get":
        # Known-key metadata is the left side: a negative observation comes
        # from this same snapshot, not a later mutable-state query.
        selected = ", ".join(qualified + "." + field for field in FIELDS)
        observed = ("SELECT " + selected + ", _mtw_scope.token::uuid::text, _mtw_scope.present\nFROM " + state
            + " AS _mtw_scope LEFT JOIN " + qualified + " ON " + qualified + ".id = _mtw_scope.key::uuid\nWHERE _mtw_scope.key = %(" + pk_bind + ")s::UUID::text")
        mode, business = "row-or-absence", 6
    else:
        new_token, old_token = "NEW." + version + "::uuid::text", "OLD." + version + "::uuid::text"
        if operation == "create":
            images = ["NEW.id::uuid::text", predecessor + "(" + new_token + ")::uuid::text", new_token,
                "false", "true", "NULL::varchar(" + str(PAYLOAD_CHARS) + ")", _payload("NEW"), "'INSERT'::text"]
        elif operation == "update":
            images = ["OLD.id::uuid::text", old_token, new_token, "true", "true", _payload("OLD"), _payload("NEW"), "'UPDATE'::text"]
        else:
            images = ["OLD.id::uuid::text", old_token, deleted + "(OLD.id::uuid::text," + old_token + ")::uuid::text",
                "true", "false", _payload("OLD"), "NULL::varchar(" + str(PAYLOAD_CHARS) + ")", "'DELETE'::text"]
        observed, mode, business = original + " RETURNING " + ",".join(images), "command", 0
    key = PlanKey(scope.schema, scope.table, operation, canonical, pk_bind)
    bits = sum(1 << i for i, field in enumerate(VALUES) if field in canonical)
    return SQLPlan(key, original, observed, "fastapi-users.base-user." + operation + "." + str(bits) + "/1", business, mode, context)


def _image(value, key):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != set(FIELDS) or value["id"] != key:
        raise CoverageRequired("Source row is not the exact six-column image")
    if not isinstance(value["email"], str) or len(value["email"]) > 320 or not isinstance(value["hashed_password"], str) or len(value["hashed_password"]) > 1024:
        raise CoverageRequired("Business string violates strict relation lengths")
    if any(type(value[name]) is not bool for name in VALUES[2:]):
        raise CoverageRequired("Actual base-user flags must be booleans")
    return value


def observe_command(scope, plan, result, *, byte_budget=128 * 1024, node_budget=128):
    """Inspect immutable PGresult cells only; never call cursor.fetch*.

    Returned proposed wire stays outside traces until public v3/core support is
    added. A zero affected-row result is a gap, never a fabricated absence read.
    """
    if plan.result_mode != "command" or (plan.key.schema, plan.key.table) != (scope.schema, scope.table) or type(byte_budget) is not int or not 128 <= byte_budget <= 256 * 1024 or type(node_budget) is not int or not 16 <= node_budget <= 1024:
        raise CoverageRequired("Command plan and shared bounded source budget required")
    expected_action = {"create": "INSERT", "update": "UPDATE", "delete": "DELETE"}[plan.key.operation]
    if result.status != 2 or result.nfields != 8 or result.ntuples not in (0, 1) or result.command_tuples != result.ntuples:
        raise CoverageRequired("Actual internal command result has unexpected cardinality/status")
    tag = result.command_status.decode("ascii")
    expected_tag = ("INSERT 0 " if expected_action == "INSERT" else expected_action + " ") + str(result.ntuples)
    if tag != expected_tag:
        raise CoverageRequired("Actual command tag and affected rowcount disagree")
    if result.ntuples == 0:
        raise CoverageRequired("Zero-row conditional write has no same-statement absence source")
    remaining, nodes, cells = byte_budget, node_budget, []
    for column in range(8):
        if result.fformat(column) != 0:
            raise CoverageRequired("Only exact text-format metadata is supported")
        expected_oid = 16 if column in (3, 4) else 1043 if column in (5, 6) else 25
        if result.ftype(column) != expected_oid:
            raise CoverageRequired("Unexpected actual internal-source field OID")
        if column in (5, 6) and result.fmod(column) != PAYLOAD_CHARS + 4:
            raise CoverageRequired("Missing SQL-side bound on payload source copies")
        raw = result.get_value(0, column)
        nodes -= 1
        if nodes < 0 or raw is not None and len(raw) > remaining:
            raise CoverageRequired("Aggregate internal-source byte/node budget exhausted")
        if raw is not None:
            remaining -= len(raw)
            text = raw.decode("utf-8", errors="strict")
            if column in (5, 6):
                value = json.loads(text)
                nodes -= 2 * len(value) + 1 if isinstance(value, dict) else 1
                if nodes < 0:
                    raise CoverageRequired("Aggregate decoded image node budget exhausted")
            elif column in (3, 4):
                if text not in ("t", "f"):
                    raise CoverageRequired("Unexpected boolean wire value")
                value = text == "t"
            else:
                value = text
        else:
            value = None
        cells.append(value)
    key, predecessor, version, old_present, new_present, old, new, action = cells
    if scope.key(key) != key or str(uuid.UUID(predecessor)) != predecessor or str(uuid.UUID(version)) != version or predecessor == version or action != expected_action:
        raise CoverageRequired("Invalid canonical key/version/action provenance")
    _image(old, key); _image(new, key)
    expected_presence = {"INSERT": (False, True), "UPDATE": (True, True), "DELETE": (True, False)}[action]
    if (old_present, new_present) != expected_presence or (old is not None) != old_present or (new is not None) != new_present:
        raise CoverageRequired("Source row presence/images disagree")
    observation = {"profile": PROFILE, "mappingId": plan.mapping_id, "proposedWireOnly": True,
        "rows": [], "effectRows": [cells], "command": {"tag": tag, "rowcount": 1, "description": None, "rownumber": None},
        "usedBytes": 0, "usedNodes": 0,
        "coverageGap": "orm_effect_wire_and_core_proof_not_implemented"}
    # The one budget includes business rows, effect rows, command metadata and
    # every key/string/node; it is not a separate allowance per container.
    try:
        for _ in range(4):
            measure = _Budget(node_budget, byte_budget)
            _measure_json(observation, measure)
            values = measure.used_bytes, measure.used_nodes
            if values == (observation["usedBytes"], observation["usedNodes"]):
                return observation
            observation["usedBytes"], observation["usedNodes"] = values
    except _CaptureBudgetError as error:
        raise CoverageRequired("Shared effect/business/command encoding budget exhausted") from error
    raise CoverageRequired("Resource counter encoding did not stabilize")


class CommandResultFacade:
    """Minimal draft command-result surface; full PGresult parity is unaccepted."""
    def __init__(self, result):
        self._result = result
    status, ntuples, nfields, binary_tuples = 1, 0, 0, 0
    def get_value(self, row, column):
        return None
    def __getattr__(self, name):
        return getattr(self._result, name)


class _CommandView:
    """One completed rewritten command, not a reusable execute wrapper."""
    def __init__(self, cursor):
        self._raw, self._actual = cursor, cursor.pgresult
        self._facade = CommandResultFacade(self._actual)
    @property
    def pgresult(self):
        return self._facade
    @property
    def description(self):
        return None
    @property
    def rownumber(self):
        return None
    @property
    def rowcount(self):
        return self._raw.rowcount
    @property
    def statusmessage(self):
        return self._raw.statusmessage
    @contextmanager
    def _native_command(self):
        if self._raw.pgresult is not self._actual:
            raise CoverageRequired("Command view cannot outlive its original result")
        self._raw.pgresult = self._facade
        try:
            yield
        finally:
            self._raw.pgresult = self._actual


class SyncCommandCursorView(_CommandView):
    def __init__(self, cursor):
        super().__init__(cursor)
        self._lock = threading.RLock()
    def fetchone(self):
        with self._lock, self._native_command():
            return self._raw.fetchone()
    def fetchmany(self, *args):
        with self._lock, self._native_command():
            return self._raw.fetchmany(*args)
    def fetchall(self):
        with self._lock, self._native_command():
            return self._raw.fetchall()


class AsyncCommandCursorView(_CommandView):
    def __init__(self, cursor):
        super().__init__(cursor)
        self._lock = asyncio.Lock()
    async def fetchone(self):
        async with self._lock:
            with self._native_command():
                return await self._raw.fetchone()
    async def fetchmany(self, *args):
        async with self._lock:
            with self._native_command():
                return await self._raw.fetchmany(*args)
    async def fetchall(self):
        async with self._lock:
            with self._native_command():
                return await self._raw.fetchall()


class _TypedEncoder:
    _value = CaptureSession._value


def _typed_observation(value, byte_budget, node_budget):
    try:
        return _TypedEncoder()._value(value, _Budget(node_budget, byte_budget))
    except _CaptureBudgetError as error:
        raise CoverageRequired("Shared business/presence/source byte/node budget exhausted") from error


class PendingGetSource:
    """One immutable source candidate; publish only upon actual row/EOF delivery."""
    __slots__ = ("scope", "plan", "cells", "key", "version", "present", "image", "published", "byte_budget", "node_budget")
    def __init__(self, scope, plan, cells, *, byte_budget, node_budget):
        self.scope, self.plan, self.cells = scope, plan, cells
        self.key, self.version, self.present = scope.known_ids[0], cells[6], cells[7]
        self.image = None if not self.present else dict(zip(FIELDS, (str(cells[0]), *cells[1:6])))
        self.published, self.byte_budget, self.node_budget = False, byte_budget, node_budget

    def deliver(self, business_rows, *, eof):
        if type(eof) is not bool or not isinstance(business_rows, (tuple, list)) or len(business_rows) > 1:
            raise CoverageRequired("Actual bounded business delivery/EOF observation required")
        if self.published:
            if business_rows:
                raise CoverageRequired("Repeated point-row delivery after source already published")
            return None
        if self.present:
            if not business_rows:
                if eof:
                    raise CoverageRequired("Actual source row was not delivered; cannot turn it into absence")
                return None
            row = business_rows[0]
            if not isinstance(row, (tuple, list)) or len(row) != 6:
                raise CoverageRequired("Actual business row has wrong prefix")
            actual = dict(zip(FIELDS, (str(row[0]), *row[1:])))
            _image(actual, self.key)
            if actual != self.image:
                raise CoverageRequired("Delivered business values differ from same-statement source")
            batch = {"rows": business_rows, "serverRows": [self.cells], "complete": eof}
        else:
            if business_rows:
                raise CoverageRequired("Negative source cannot have a delivered business row")
            if not eof:
                return None
            batch = {"rows": [], "presenceRows": [self.cells], "complete": True}
        batch.update(profile=PROFILE, mappingId=self.plan.mapping_id, proposedWireOnly=True,
            source={"key": self.key, "version": self.version, "present": self.present},
            coverageGap="orm_presence_wire_and_core_proof_not_implemented")
        encoded = _typed_observation(batch, self.byte_budget, self.node_budget)
        self.published = True
        return encoded


def observe_get(scope, plan, result, parameter, *, byte_budget=128 * 1024, node_budget=256):
    if plan.result_mode != "row-or-absence" or (plan.key.schema, plan.key.table) != (scope.schema, scope.table):
        raise CoverageRequired("Exact fixed-domain get plan required")
    if type(byte_budget) is not int or not 128 <= byte_budget <= 256 * 1024 or type(node_budget) is not int or not 32 <= node_budget <= 1024:
        raise CoverageRequired("Shared bounded read-source budget required")
    key = scope.key(parameter)
    if result.status != 2 or result.ntuples != 1 or result.nfields != 8:
        raise CoverageRequired("Known-domain state row must actually exist; rowcount is not absence proof")
    values, remaining = [], byte_budget
    for column in range(8):
        expected_oid = (2950, 1043, 1043, 16, 16, 16, 25, 16)[column]
        if result.fformat(column) != 0 or result.ftype(column) != expected_oid:
            raise CoverageRequired("Unexpected actual point-read source types/format")
        if column in (1, 2) and result.fmod(column) != (324 if column == 1 else 1028):
            raise CoverageRequired("Missing SQL/catalog bound on business read strings")
        raw = result.get_value(0, column)
        if raw is not None and len(raw) > remaining:
            raise CoverageRequired("Aggregate source bytes exhausted before further copies")
        if raw is None:
            value = None
        else:
            remaining -= len(raw)
            text = raw.decode("utf-8", errors="strict")
            if column in (3, 4, 5, 7):
                if text not in ("t", "f"):
                    raise CoverageRequired("Invalid actual boolean read source")
                value = text == "t"
            elif column == 0:
                value = uuid.UUID(text)
            else:
                value = text
        values.append(value)
    if not isinstance(values[6], str) or str(uuid.UUID(values[6])) != values[6] or type(values[7]) is not bool:
        raise CoverageRequired("Missing canonical presence/token source")
    if values[7]:
        if str(values[0]) != key:
            raise CoverageRequired("Actual business row differs from fixed UUID")
        _image(dict(zip(FIELDS, (key, *values[1:6]))), key)
    elif any(value is not None for value in values[:6]):
        raise CoverageRequired("Negative presence disagrees with actual business row")
    pending = PendingGetSource(scope, plan, values, byte_budget=byte_budget, node_budget=node_budget)
    pending.key = key
    return pending
