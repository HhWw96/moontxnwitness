"""Candidate fixed ORM SQL plans and bounded structural cache.

Importing this module requires neither SQLAlchemy nor psycopg. Compilation and
the optional experimental observer are loaded explicitly when requested. This
module never grants complete trace coverage or authenticates database facts.
"""
from __future__ import annotations
from collections import OrderedDict
from dataclasses import dataclass, fields as dataclass_fields, is_dataclass
import re
import sys
import threading
import uuid

PROFILE = 'fastapi-users-sqlalchemy-7.0.0-pg18/1'
FIELDS = ('id', 'email', 'hashed_password', 'is_active', 'is_superuser', 'is_verified')
VALUES = FIELDS[1:]
VERSION = '_mtw_orm_version'
PAYLOAD_CHARS = 12_288


class CoverageRequired(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SQLContext:
    """Immutable compiler/profile identity, not observed database metadata.

    A fresh catalog/installation or connection configuration must select a new
    registry_epoch. No transaction state, parameters or results belong here.
    """
    profile: str = PROFILE
    sqlalchemy_version: str = '2.0.55'
    dialect: str = 'postgresql'
    driver_contract: str = 'psycopg-3.3.6'
    postgres_major: int = 18
    payload_chars: int = PAYLOAD_CHARS
    registry_epoch: int = 0

    def __post_init__(self):
        if (any(type(value) is not str for value in (self.profile, self.sqlalchemy_version, self.dialect, self.driver_contract))
                or self.profile != PROFILE or self.sqlalchemy_version != '2.0.55'
                or self.dialect != 'postgresql' or self.driver_contract != 'psycopg-3.3.6'
                or type(self.postgres_major) is not int or self.postgres_major != 18
                or type(self.payload_chars) is not int or self.payload_chars != PAYLOAD_CHARS
                or type(self.registry_epoch) is not int or not 0 <= self.registry_epoch <= 1_000_000):
            raise ValueError('Unsupported fixed ORM compiler/profile context')


DEFAULT_CONTEXT = SQLContext()


@dataclass(frozen=True, slots=True)
class UserScope:
    schema: str
    table: str
    known_ids: tuple[str, ...]

    def __post_init__(self):
        if type(self.schema) is not str or not re.fullmatch(r'mtw_orm_v3_[a-z0-9_]{1,40}', self.schema):
            raise ValueError('Explicit controlled ORM schema required')
        if type(self.table) is not str or not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}', self.table):
            raise ValueError('Bounded native table identifier required')
        if (type(self.known_ids) is not tuple or not 1 <= len(self.known_ids) <= 128
                or any(type(key) is not str or len(key) != 36 for key in self.known_ids)
                or len(set(self.known_ids)) != len(self.known_ids)):
            raise ValueError('Declare an immutable tuple of 1..128 unique UUIDs')
        try:
            canonical = all(str(uuid.UUID(key)) == key for key in self.known_ids)
        except (ValueError, AttributeError):
            canonical = False
        if not canonical:
            raise ValueError('Known UUIDs must use canonical lowercase text')

    def key(self, value):
        try:
            canonical = str(uuid.UUID(str(value)))
        except (ValueError, TypeError, AttributeError) as error:
            raise CoverageRequired('Invalid original UUID parameter; do not rewrite') from error
        if canonical not in self.known_ids:
            raise CoverageRequired('Dynamic/out-of-domain UUID needs independent absence provenance')
        return canonical


@dataclass(frozen=True, slots=True)
class PlanKey:
    schema: str
    table: str
    operation: str
    fields: tuple[str, ...]
    pk_bind: str


@dataclass(frozen=True, slots=True)
class SQLPlan:
    key: PlanKey
    original_sql: str
    observed_sql: str
    mapping_id: str
    business_columns: int
    result_mode: str
    context: SQLContext = DEFAULT_CONTEXT


def build(scope, operation, fields=(), pk_bind='id_1', *, context=DEFAULT_CONTEXT):
    """Compile the fixed template; optional SQLAlchemy is imported on demand."""
    _shape(scope, operation, fields, pk_bind, context)
    from ._orm_policy import build as compile_plan
    return compile_plan(scope, operation, fields, pk_bind, context=context)


def _shape(scope, operation, fields, pk_bind, context):
    if type(scope) is not UserScope or type(context) is not SQLContext:
        raise CoverageRequired('Immutable exact ORM scope and compiler context required')
    if type(operation) is not str or operation not in ('get', 'create', 'update', 'delete'):
        raise CoverageRequired('Only exact base-user point CRUD is supported')
    if type(fields) not in (tuple, list) or len(fields) > len(VALUES) or any(type(field) is not str for field in fields):
        raise CoverageRequired('Bounded original update field layout required')
    canonical = tuple(field for field in VALUES if field in fields)
    if operation == 'update' and (not canonical or len(canonical) != len(fields) or len(set(fields)) != len(fields)):
        raise CoverageRequired('Update must use declared non-PK fields exactly once')
    if operation != 'update' and fields:
        raise CoverageRequired('Unexpected non-update fields, including on a cache hit')
    allowed = {'get': ('id_1', 'pk_1'), 'create': ('id',),
        'update': (scope.table + '_id', scope.schema + '_' + scope.table + '_id'), 'delete': ('id',)}[operation]
    if type(pk_bind) is not str or pk_bind not in allowed:
        raise CoverageRequired('Unrecognized pinned SQLAlchemy bind layout')
    return PlanKey(scope.schema, scope.table, operation, canonical, pk_bind)


def _retained_size(value, seen=None):
    """Charge entry graphs, overcount sharing between entries, plus link allowance.

    This is accounted retained-entry bytes, not a peak-RSS measurement. The
    fixed cache object/lock/container header is outside this entry budget.
    """
    seen = set() if seen is None else seen
    if id(value) in seen:
        return 0
    seen.add(id(value))
    size = sys.getsizeof(value)
    if is_dataclass(value):
        size += sum(_retained_size(getattr(value, field.name), seen) for field in dataclass_fields(value))
    elif isinstance(value, tuple):
        size += sum(_retained_size(item, seen) for item in value)
    return size


class StructuredSQLCache:
    """LRU of immutable plans, keyed by complete scope, context and SQL shape.

    prepare() admits constructor-compiled plans into this same cache. The old
    observer compiled 35 plans, then compiled each first execution again in a
    second cache. No business parameter/result/transaction enters this API.
    """
    def __init__(self, max_entries=128, max_bytes=1024 * 1024, *, enabled=True, context=DEFAULT_CONTEXT):
        if (type(max_entries) is not int or not 1 <= max_entries <= 256
                or type(max_bytes) is not int or not 4096 <= max_bytes <= 2 * 1024 * 1024
                or type(enabled) is not bool or type(context) is not SQLContext):
            raise ValueError('Explicit bounded cache settings and immutable context required')
        self._max_entries, self._max_bytes, self._enabled, self._context = max_entries, max_bytes, enabled, context
        self._values, self._bytes, self._lock = OrderedDict(), 0, threading.RLock()
        self.hits = self.misses = self.evictions = self.compilations = self.bypasses = 0

    @property
    def max_entries(self): return self._max_entries
    @property
    def max_bytes(self): return self._max_bytes
    @property
    def enabled(self): return self._enabled
    @property
    def context(self): return self._context

    def _get(self, scope, operation, fields, pk_bind, context):
        shape = _shape(scope, operation, fields, pk_bind, context)
        compiler = sys.modules.get('sqlalchemy')
        if compiler is not None and getattr(compiler, '__version__', None) != context.sqlalchemy_version:
            raise CoverageRequired('Loaded SQLAlchemy differs from this immutable compiler context')
        key = (scope, context, shape)
        with self._lock:
            if self._enabled and key in self._values:
                self.hits += 1
                self._values.move_to_end(key)
                return self._values[key][0]
            self.misses += 1
            self.compilations += 1
            # Never retain a partially constructed plan or an exception.
            plan = build(scope, operation, fields, pk_bind, context=context)
            if type(plan) is not SQLPlan or plan.key != shape or plan.context != context:
                raise CoverageRequired('Compiler returned a different immutable plan/context')
            size = _retained_size((key, plan)) + 512
            if not self._enabled or size > self._max_bytes:
                self.bypasses += 1
                return plan
            while self._values and (len(self._values) >= self._max_entries or self._bytes + size > self._max_bytes):
                _, (_, previous_size) = self._values.popitem(last=False)
                self._bytes -= previous_size
                self.evictions += 1
            self._values[key] = (plan, size)
            self._bytes += size
            return plan

    def prepare(self, scope, operation, fields=(), pk_bind='id_1', *, context=None):
        return self._get(scope, operation, fields, pk_bind, self._context if context is None else context)

    def match(self, scope, actual_sql, operation, fields=(), pk_bind='id_1', *, context=None):
        if type(actual_sql) is not str or len(actual_sql) > 65536 or len(actual_sql.encode('utf8')) > 65536:
            raise CoverageRequired('Exact original SQL must fit the 64 KiB text bound')
        plan = self._get(scope, operation, fields, pk_bind, self._context if context is None else context)
        if actual_sql != plan.original_sql:
            raise CoverageRequired('Executed text differs from the exact pinned SQL plan')
        return plan

    @property
    def retained(self):
        with self._lock:
            return {'entries': len(self._values), 'bytes': self._bytes}


def __getattr__(name):
    if name == 'ProvenanceObserver':
        from ._orm_async import ProvenanceObserver
        return ProvenanceObserver
    if name == 'SourceSink':
        from ._orm_source_sink import SourceSink
        return SourceSink
    raise AttributeError(name)


__all__ = ['UserScope', 'SQLContext', 'SQLPlan', 'PlanKey', 'StructuredSQLCache',
    'CoverageRequired', 'build', 'ProvenanceObserver', 'SourceSink']
