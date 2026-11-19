"""Optional configured point-CRUD candidate recognition; no SQL is executed.

V2 is a distinct, deliberately narrower contract than configured_sql/v1.
Importing this module imports no optional parser, driver, ORM or database.
Candidates and typed input logs produce no source facts or model coverage.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import json
import re
import threading
import uuid

from .configured_sql import (
    ColumnConfig, ScalarRef, Projection, PredicateTerm, CacheInfo,
    RecognitionError, OptionalParserUnavailable, SQLGLOT_VERSION, TEXT_COMPARISON,
    _Builder, _BIND, _args, _canonical, _dependency, _fields, _identifier,
    _integer, _sha, _text, _value,
)

CONFIG_FORMAT = 'moontxnwitness-configured-sql/v2'
PLAN_FORMAT = 'moontxnwitness-sql-point-crud-candidate/v2'
PARSER_CONTRACT = 'sqlglot-30.26-postgres-single-table-point-crud/v2'
_LIMITS = ('max_sql_bytes', 'max_tokens', 'max_ast_nodes', 'max_nesting', 'max_text_bytes')
_UUID_TEXT = re.compile(r'(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\Z')


@dataclass(frozen=True, slots=True)
class PrimaryKeyConfigV2:
    name: str
    type: str
    comparison: str | None = None

    def __post_init__(self):
        _identifier(self.name)
        if self.type not in ('int64', 'text', 'uuid'):
            raise ValueError('A V2 primary key must be int64, text or uuid')
        if self.type == 'text':
            if self.comparison != TEXT_COMPARISON:
                raise ValueError('Text identity requires an explicit PostgreSQL C / UTF-8 declaration')
        elif self.comparison is not None:
            raise ValueError('Only text identity has a comparison declaration')

    def to_dict(self):
        return {'name': self.name, 'type': self.type, 'comparison': self.comparison}


@dataclass(frozen=True, slots=True)
class TableConfigV2:
    schema: str
    table: str
    key: PrimaryKeyConfigV2
    business_columns: tuple[ColumnConfig, ...]

    def __post_init__(self):
        _identifier(self.schema)
        _identifier(self.table)
        if type(self.key) is not PrimaryKeyConfigV2:
            raise ValueError('An immutable PrimaryKeyConfigV2 is required')
        if type(self.business_columns) is not tuple or not 1 <= len(self.business_columns) <= 16:
            raise ValueError('Use an immutable tuple of 1..16 business columns')
        if any(type(column) is not ColumnConfig for column in self.business_columns):
            raise ValueError('Business columns must be non-NULL int64, bool or C / UTF-8 text ColumnConfig values')
        names = [column.name for column in self.columns]
        if len(set(names)) != len(names):
            raise ValueError('The primary key and business columns must have distinct names')

    @property
    def primary_key(self):
        return self.key.name

    @property
    def columns(self):
        """Configured full-row order, including the separately declared key."""
        return (self.key,) + self.business_columns

    def column(self, name):
        for column in self.columns:
            if column.name == name:
                return column
        raise RecognitionError('unknown-column', 'Column is outside the configured table: ' + name)

    def to_dict(self):
        return {'schema': self.schema, 'table': self.table, 'primaryKey': self.key.to_dict(),
                'businessColumns': [column.to_dict() for column in self.business_columns]}


@dataclass(frozen=True, slots=True)
class SQLCaptureConfigV2:
    table: TableConfigV2
    default_schema: str | None = None
    max_sql_bytes: int = 65536
    max_tokens: int = 8192
    max_ast_nodes: int = 4096
    max_nesting: int = 64
    max_text_bytes: int = 65536

    def __post_init__(self):
        if type(self.table) is not TableConfigV2:
            raise ValueError('Exactly one immutable TableConfigV2 per capture window is required')
        if self.default_schema is not None:
            _identifier(self.default_schema)
        for name, minimum, maximum in [('max_sql_bytes', 1, 1048576), ('max_tokens', 1, 32768),
                ('max_ast_nodes', 1, 32768), ('max_nesting', 1, 128), ('max_text_bytes', 1, 1048576)]:
            _integer(getattr(self, name), minimum, maximum, name)

    @property
    def tables(self):
        return (self.table,)

    @property
    def max_terms(self):
        return 1

    @property
    def max_insert_rows(self):
        return 1

    def to_dict(self):
        return {'format': CONFIG_FORMAT, 'table': self.table.to_dict(), 'defaultSchema': self.default_schema,
                'limits': {name: getattr(self, name) for name in _LIMITS}}

    @property
    def sha256(self):
        return _sha(_canonical(self.to_dict()))

    @classmethod
    def from_json(cls, text):
        _text(text, 'Configuration JSON', 262144)
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('Duplicate configuration key: ' + key)
                result[key] = value
            return result
        def nonfinite(_):
            raise ValueError('Nonfinite configuration JSON')
        try:
            document = json.loads(text, object_pairs_hook=unique, parse_constant=nonfinite)
        except (json.JSONDecodeError, RecursionError) as error:
            raise ValueError('Invalid or excessively nested configuration JSON') from error
        _fields(document, {'format', 'table', 'defaultSchema', 'limits'}, 'V2 configuration', required={'format', 'table'})
        if document['format'] != CONFIG_FORMAT:
            raise ValueError('Unknown V2 configuration format')
        table = document['table']
        _fields(table, {'schema', 'table', 'primaryKey', 'businessColumns'}, 'V2 table',
                required={'schema', 'table', 'primaryKey', 'businessColumns'})
        key = table['primaryKey']
        _fields(key, {'name', 'type', 'comparison'}, 'V2 primary key', required={'name', 'type'})
        if type(table['businessColumns']) is not list:
            raise ValueError('businessColumns must be an array')
        columns = []
        for column in table['businessColumns']:
            _fields(column, {'name', 'type', 'comparison'}, 'V2 business column', required={'name', 'type'})
            columns.append(ColumnConfig(column['name'], column['type'], column.get('comparison')))
        limits = document.get('limits', {})
        _fields(limits, set(_LIMITS), 'V2 limits')
        return cls(TableConfigV2(table['schema'], table['table'],
            PrimaryKeyConfigV2(key['name'], key['type'], key.get('comparison')), tuple(columns)),
            document.get('defaultSchema'), **limits)


def _input_value(value, kind, text_limit):
    """Validate and return immutable logging values, without changing call args."""
    if kind != 'uuid':
        _value(value, kind, text_limit)
        return value
    if type(value) is uuid.UUID:
        return str(value)
    if type(value) is str and _UUID_TEXT.fullmatch(value):
        return str(uuid.UUID(value))
    raise RecognitionError('parameter-type', 'A UUID object, 32-hex or hyphenated UUID text is required for UUID identity')


@dataclass(frozen=True, slots=True)
class RecognizedSQLV2:
    original_sql: str
    config_sha256: str
    table: TableConfigV2
    operation: str
    projections: tuple[Projection, ...]
    predicates: tuple[PredicateTerm, ...]
    assignments: tuple[tuple[str, ScalarRef], ...]
    insert_columns: tuple[str, ...]
    insert_rows: tuple[tuple[ScalarRef, ...], ...]
    returning: tuple[Projection, ...]
    parameters: tuple[ScalarRef, ...]
    schema_resolution: str
    requires_no_parameter_argument: bool
    max_text_bytes: int

    @property
    def key_reference(self):
        if self.operation == 'insert':
            return self.insert_rows[0][self.insert_columns.index(self.table.primary_key)]
        return self.predicates[0].value

    def to_dict(self):
        return {'format': PLAN_FORMAT, 'parserContract': PARSER_CONTRACT, 'sqlglotVersion': SQLGLOT_VERSION,
            'configSha256': self.config_sha256, 'sqlSha256': _sha(self.original_sql), 'originalSql': self.original_sql,
            'table': self.table.to_dict(), 'operation': self.operation, 'schemaResolution': self.schema_resolution,
            'keyReference': self.key_reference.to_dict(),
            'projections': [p.to_dict() for p in self.projections], 'predicates': [p.to_dict() for p in self.predicates],
            'assignments': [{'column': name, 'value': value.to_dict()} for name, value in self.assignments],
            'insertColumns': list(self.insert_columns), 'insertRows': [[v.to_dict() for v in row] for row in self.insert_rows],
            'returning': [p.to_dict() for p in self.returning], 'parameters': [p.to_dict() for p in self.parameters],
            'requiresNoParameterArgument': self.requires_no_parameter_argument,
            'databaseSyntaxValidated': False, 'sourceAuthenticated': False,
            'captureFactsProduced': False, 'sourceFactsProduced': False, 'modelCoverageAccepted': False,
            'moonbitProjectionVerified': False, 'returningIsPredicateRead': False,
            'requiredProofs': ['independent-MoonBit-v2-original-SQL-and-parameter-projection',
                'catalog-types-nonnull-primary-key-text-collation-and-DDL-epoch', 'session-schema-and-encoding',
                'actual-execution-success-delivered-full-row-and-complete-fetch',
                'same-statement-or-native-observed-read-version-identity',
                'initialized-snapshot-dynamic-absence-and-complete-source-window',
                'installed-unique-version-sources-effective-writes-and-rollback-journal',
                'model-specific-projection-and-coverage']}

    def bind(self, parameters=None):
        """Typed input log only; UUIDs canonicalize in the returned copy.

        Does not invoke a driver, consume an iterator, or modify the original
        parameter mapping/list/tuple. Binding does not prove execution success.
        """
        if self.requires_no_parameter_argument and parameters is not None:
            raise RecognitionError('driver-format-ambiguity', 'Percent text outside bind slots requires parameters=None')
        kinds = {reference.kind for reference in self.parameters}
        if not kinds:
            if parameters is not None and not (type(parameters) in (tuple, list, dict) and len(parameters) == 0):
                raise RecognitionError('parameter-arity', 'Statement has no bind slots')
            return ()
        if kinds == {'named'}:
            if type(parameters) is not dict or set(parameters) != {p.value for p in self.parameters}:
                raise RecognitionError('parameter-arity', 'Exact original named parameters required')
            values = [parameters[p.value] for p in self.parameters]
        elif kinds == {'positional'}:
            if type(parameters) not in (tuple, list) or len(parameters) != len(self.parameters):
                raise RecognitionError('parameter-arity', 'Exact materialized positional parameters required')
            values = parameters
        else:
            raise RecognitionError('mixed-parameters', 'Mixed parameter styles are unsupported')
        return tuple((reference, _input_value(value, reference.type, self.max_text_bytes))
                     for reference, value in zip(self.parameters, values))


class _PointBuilderV2(_Builder):
    def scalar(self, node, column):
        e = self.exp
        while type(node) is e.Paren:
            _args(node, {'this'})
            node = node.this
        if type(node) is e.Cast:
            _args(node, {'this', 'to'})
            target = node.args.get('to')
            if type(target) is not e.DataType:
                raise RecognitionError('bind-cast', 'A supported built-in scalar cast is required')
            _args(target, {'this', 'nested'})
            uuid_key = column.type == 'uuid' and target.this == e.DataType.Type.UUID
            varchar_value = (column.type == 'text' and column.name != self.table.primary_key
                             and target.this == e.DataType.Type.VARCHAR)
            if target.args.get('nested') or not (uuid_key or varchar_value):
                raise RecognitionError('bind-cast', 'Use a UUID key cast or an unbounded VARCHAR cast on a text assignment')
            node = node.this
            if type(node) is not e.Placeholder:
                raise RecognitionError('bind-cast', 'Casts require a direct original bind slot')
        if column.type == 'uuid' and type(node) is not e.Placeholder:
            raise RecognitionError('uuid-identity', 'UUID identity requires an original parameter binding')
        return super().scalar(node, column)

    def predicates(self, where):
        if where is None:
            return ()
        result = super().predicates(where)
        if len(result) != 1 or result[0].operator != 'eq' or result[0].column != self.table.primary_key:
            raise RecognitionError('point-key-equality', 'Exactly one primary-key equality and no extra predicates required')
        return result

    def build(self, ast, stray_percent):
        plan = super().build(ast, stray_percent)
        if plan.ordering:
            raise RecognitionError('point-ordering', 'Point candidates have no ordering clause')
        if plan.operation != 'insert' and len(plan.predicates) != 1:
            raise RecognitionError('point-key-equality', 'A point candidate requires one primary-key equality')
        if plan.operation == 'select':
            expected = {column.name for column in self.table.columns}
            if len(plan.projections) != len(expected) or {p.column for p in plan.projections} != expected:
                raise RecognitionError('full-row-select', 'A point SELECT must project every configured column exactly once')
        for projections in (plan.projections, plan.returning):
            if len({p.output_name for p in projections}) != len(projections) or len({p.column for p in projections}) != len(projections):
                raise RecognitionError('projection-shape', 'Repeated result columns or output names are unsupported')
        if plan.operation == 'update' and any(value.kind == 'literal' for _, value in plan.assignments):
            raise RecognitionError('parameter-assignment', 'V2 UPDATE assignments require original parameter bindings')
        if plan.operation == 'insert':
            if set(plan.insert_columns) != {column.name for column in self.table.columns}:
                raise RecognitionError('full-row-insert', 'V2 INSERT requires an explicit key and all business columns')
            if any(value.kind == 'literal' for value in plan.insert_rows[0]):
                raise RecognitionError('parameter-assignment', 'V2 INSERT values require original parameter bindings')
        return RecognizedSQLV2(plan.original_sql, plan.config_sha256, self.table, plan.operation,
            plan.projections, plan.predicates, plan.assignments, plan.insert_columns, plan.insert_rows,
            plan.returning, plan.parameters, plan.schema_resolution, plan.requires_no_parameter_argument, plan.max_text_bytes)


def _recognize_v2(config, sql):
    sqlglot, exp, Dialect = _dependency()
    try:
        tokens = sqlglot.tokenize(sql, read='postgres')
        if len(tokens) > config.max_tokens:
            raise RecognitionError('token-budget', 'SQL token budget exhausted')
        depth, slots, covered = 0, [], set()
        for token in tokens:
            name = token.token_type.name
            if name in ('L_PAREN', 'L_BRACKET'):
                depth += 1
                if depth > config.max_nesting:
                    raise RecognitionError('nesting-budget', 'SQL nesting budget exhausted')
            elif name in ('R_PAREN', 'R_BRACKET'):
                depth -= 1
            if name == 'MOD':
                match = _BIND.match(sql, token.start)
                if not match:
                    raise RecognitionError('parameter-format', 'Exact psycopg %s or %(name)s slots required')
                slots.append(('named', match.group(1)) if match.group(1) else ('positional', None))
                covered.add(token.start)
        stray_percent = any(char == '%' and index not in covered for index, char in enumerate(sql))
        statements = Dialect.get_or_raise('postgres').parser(error_level=sqlglot.ErrorLevel.RAISE).parse(tokens, sql)
        if len(statements) != 1 or statements[0] is None:
            raise RecognitionError('statement-count', 'Exactly one statement required')
        ast = statements[0]
        # SQLGlot also normalizes quoted type names and VARCHAR2 to VARCHAR.
        # Count only the original unquoted PostgreSQL ::VARCHAR spelling.
        original_varchar = sum(
            previous.token_type.name == 'DCOLON'
            and token.token_type.name == 'VARCHAR'
            and sql[token.start:token.end + 1].lower() == 'varchar'
            for previous, token in zip(tokens, tokens[1:])
        )
        ast_varchar = 0
        for index, node in enumerate(ast.walk(), 1):
            if index > config.max_ast_nodes:
                raise RecognitionError('ast-budget', 'AST node budget exhausted')
            if isinstance(node, exp.Null):
                raise RecognitionError('null-semantics', 'NULL is outside V2 point CRUD')
            if isinstance(node, exp.Func) and type(node) not in (exp.And, exp.Collate, exp.Cast):
                raise RecognitionError('sql-function', 'Functions are outside V2 point CRUD')
            if isinstance(node, (exp.Join, exp.Subquery, exp.CTE, exp.Union, exp.Intersect, exp.Except)):
                raise RecognitionError('multi-relation', 'Only one configured base table is supported')
            if type(node) is exp.Cast and type(node.to) is exp.DataType and node.to.this == exp.DataType.Type.VARCHAR:
                ast_varchar += 1
        if ast_varchar != original_varchar:
            raise RecognitionError('bind-cast', 'Text assignments support only the original unquoted ::VARCHAR spelling')
        plan = _PointBuilderV2(config, sql, exp, slots).build(ast, stray_percent)
        result = ast if plan.operation == 'select' else ast.args.get('returning')
        # A quoted identifier containing '*' is not a wildcard node.
        star = result is not None and any(type(node) is exp.Star
            for expression in result.expressions for node in expression.walk())
        return plan, star
    except RecognitionError:
        raise
    except (sqlglot.errors.SqlglotError, RecursionError, ValueError, TypeError, AttributeError) as error:
        raise RecognitionError('parse-or-shape', 'SQLGlot V2 candidate parsing failed: ' + type(error).__name__) from error


class ConfiguredSQLParserV2:
    """Bounded structural cache; holds no input values, results or key universe."""
    def __init__(self, config, *, cache_entries=256, cache_bytes=4 * 1024 * 1024):
        if type(config) is not SQLCaptureConfigV2:
            raise ValueError('An immutable SQLCaptureConfigV2 is required')
        _integer(cache_entries, 0, 4096, 'cache_entries')
        _integer(cache_bytes, 0, 16 * 1024 * 1024, 'cache_bytes')
        self._config, self._entries, self._maximum = config, cache_entries, cache_bytes
        self._cache, self._bytes, self._hits, self._misses = OrderedDict(), 0, 0, 0
        self._lock = threading.RLock()

    @property
    def config(self):
        return self._config

    def recognize(self, sql):
        return self._recognize_with_shape(sql)[0]

    def _recognize_with_shape(self, sql):
        if type(sql) is not str:
            raise RecognitionError('sql-type', 'Original plain SQL text is required')
        try:
            _text(sql, 'Original SQL', self._config.max_sql_bytes)
        except ValueError as error:
            raise RecognitionError('sql-budget-or-encoding', str(error)) from error
        with self._lock:
            cached = self._cache.get(sql)
            if cached is not None:
                self._cache.move_to_end(sql)
                self._hits += 1
                return cached[0]
            self._misses += 1
        recognized = _recognize_v2(self._config, sql)
        plan, _ = recognized
        size = len(_canonical(plan.to_dict()).encode('utf-8')) + len(sql.encode('utf-8'))
        with self._lock:
            if self._entries and size <= self._maximum:
                prior = self._cache.pop(sql, None)
                if prior is not None:
                    self._bytes -= prior[1]
                while self._cache and (len(self._cache) >= self._entries or self._bytes + size > self._maximum):
                    _, (_, removed) = self._cache.popitem(last=False)
                    self._bytes -= removed
                self._cache[sql] = (recognized, size)
                self._bytes += size
        return recognized

    def cache_info(self):
        with self._lock:
            return CacheInfo(len(self._cache), self._bytes, self._hits, self._misses)
