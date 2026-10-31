"""Immutable optional PostgreSQL SQL recognition. This module executes no SQL.

A recognized AST is a candidate description, not a syntax certificate, observed
read, write effect, source proof or isolation classification. Existing profiles
are independent. Optional SQLGlot is imported only on recognize(), never while
loading this module. No driver, ORM, cursor or database connection is imported.
"""
from __future__ import annotations
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import importlib.metadata
import json
import re
import threading

CONFIG_FORMAT = 'moontxnwitness-configured-sql/v1'
PLAN_FORMAT = 'moontxnwitness-sql-ast-candidate/v1'
PARSER_CONTRACT = 'sqlglot-30.26-postgres-single-table/v1'
SQLGLOT_VERSION = '30.26.0'
TEXT_COMPARISON = 'postgres-c-utf8-v1'
_MODELS = ('point-register-v1', 'append-list-v1', 'relation-set-v1')
_TYPES = ('int64', 'bool', 'text')
_UNQUOTED = re.compile(r'[A-Za-z_][A-Za-z0-9_$]*\Z')
_BIND = re.compile(r'%s(?![A-Za-z0-9_$])|%\(([A-Za-z_][A-Za-z0-9_]{0,127})\)s(?![A-Za-z0-9_$])')


class RecognitionError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class OptionalParserUnavailable(ImportError):
    pass


def _text(value, label, maximum):
    if type(value) is not str or not value or '\x00' in value:
        raise ValueError(label + ' must be nonempty NUL-free text')
    try:
        size = len(value.encode('utf-8', errors='strict'))
    except UnicodeError as error:
        raise ValueError(label + ' must contain valid Unicode scalars') from error
    if size > maximum:
        raise ValueError(label + ' exceeds the UTF-8 byte bound')
    return value


def _identifier(value):
    return _text(value, 'PostgreSQL identifier', 63)


def _integer(value, minimum, maximum, label):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(label + ' must be an integer in the explicit bounds')
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


@dataclass(frozen=True, slots=True)
class ColumnConfig:
    name: str
    type: str
    comparison: str | None = None

    def __post_init__(self):
        _identifier(self.name)
        if self.type not in _TYPES:
            raise ValueError('Supported column types are int64, bool and text')
        if self.type == 'text':
            if self.comparison != TEXT_COMPARISON:
                raise ValueError('Text requires an explicit PostgreSQL C / UTF-8 comparison declaration')
        elif self.comparison is not None:
            raise ValueError('Comparison overrides are only defined for text')

    def to_dict(self):
        return {'name': self.name, 'type': self.type, 'comparison': self.comparison}


@dataclass(frozen=True, slots=True)
class TableConfig:
    schema: str
    table: str
    primary_key: str
    columns: tuple[ColumnConfig, ...]
    model: str = 'relation-set-v1'

    def __post_init__(self):
        for name in (self.schema, self.table, self.primary_key):
            _identifier(name)
        if type(self.columns) is not tuple or not 1 <= len(self.columns) <= 128:
            raise ValueError('Use an immutable tuple of 1..128 configured columns')
        if any(type(column) is not ColumnConfig for column in self.columns):
            raise ValueError('Each column must be a ColumnConfig')
        names = [column.name for column in self.columns]
        if len(set(names)) != len(names) or self.primary_key not in names:
            raise ValueError('Distinct columns and exactly one declared primary-key column required')
        if self.model not in _MODELS:
            raise ValueError('Unknown target model hint')

    def column(self, name):
        for column in self.columns:
            if column.name == name:
                return column
        raise RecognitionError('unknown-column', 'Column is outside the configured table: ' + name)

    def to_dict(self):
        return {'schema': self.schema, 'table': self.table, 'primaryKey': self.primary_key,
                'columns': [column.to_dict() for column in self.columns], 'model': self.model}


@dataclass(frozen=True, slots=True)
class SQLCaptureConfig:
    tables: tuple[TableConfig, ...]
    default_schema: str | None = None
    max_sql_bytes: int = 65536
    max_tokens: int = 8192
    max_ast_nodes: int = 4096
    max_nesting: int = 64
    max_terms: int = 128
    max_insert_rows: int = 128
    max_text_bytes: int = 65536

    def __post_init__(self):
        if type(self.tables) is not tuple or not 1 <= len(self.tables) <= 128 or any(type(t) is not TableConfig for t in self.tables):
            raise ValueError('Use an immutable tuple of 1..128 TableConfig values')
        identities = [(table.schema, table.table) for table in self.tables]
        if len(set(identities)) != len(identities):
            raise ValueError('Duplicate configured relation identity')
        if self.default_schema is not None:
            _identifier(self.default_schema)
        for name, minimum, maximum in [('max_sql_bytes', 1, 1048576), ('max_tokens', 1, 32768),
                ('max_ast_nodes', 1, 32768), ('max_nesting', 1, 128), ('max_terms', 1, 1024),
                ('max_insert_rows', 1, 1024), ('max_text_bytes', 1, 1048576)]:
            _integer(getattr(self, name), minimum, maximum, name)

    def to_dict(self):
        return {'format': CONFIG_FORMAT, 'tables': [table.to_dict() for table in self.tables],
                'defaultSchema': self.default_schema,
                'limits': {name: getattr(self, name) for name in ('max_sql_bytes', 'max_tokens', 'max_ast_nodes',
                    'max_nesting', 'max_terms', 'max_insert_rows', 'max_text_bytes')}}

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
            value = json.loads(text, object_pairs_hook=unique, parse_constant=nonfinite)
        except (json.JSONDecodeError, RecursionError) as error:
            raise ValueError('Invalid or excessively nested configuration JSON') from error
        _fields(value, {'format', 'tables', 'defaultSchema', 'limits'}, 'configuration', required={'format', 'tables'})
        if value['format'] != CONFIG_FORMAT or type(value['tables']) is not list:
            raise ValueError('Unknown configuration format')
        tables = []
        for table in value['tables']:
            _fields(table, {'schema', 'table', 'primaryKey', 'columns', 'model'}, 'table', required={'schema', 'table', 'primaryKey', 'columns'})
            if type(table['columns']) is not list:
                raise ValueError('columns must be an array')
            columns = []
            for column in table['columns']:
                _fields(column, {'name', 'type', 'comparison'}, 'column', required={'name', 'type'})
                columns.append(ColumnConfig(column['name'], column['type'], column.get('comparison')))
            tables.append(TableConfig(table['schema'], table['table'], table['primaryKey'], tuple(columns), table.get('model', 'relation-set-v1')))
        limits = value.get('limits', {})
        _fields(limits, {'max_sql_bytes', 'max_tokens', 'max_ast_nodes', 'max_nesting', 'max_terms', 'max_insert_rows', 'max_text_bytes'}, 'limits')
        return cls(tuple(tables), value.get('defaultSchema'), **limits)


def _fields(value, allowed, label, *, required=frozenset()):
    if type(value) is not dict or set(value) - allowed or required - set(value):
        raise ValueError('Missing or unknown ' + label + ' fields')


@dataclass(frozen=True, slots=True)
class ScalarRef:
    kind: str
    value: str | int | bool
    type: str

    def to_dict(self):
        value = str(self.value) if self.kind == 'literal' and self.type == 'int64' else self.value
        return {'kind': self.kind, 'value': value, 'type': self.type}


@dataclass(frozen=True, slots=True)
class PredicateTerm:
    column: str
    operator: str
    value: ScalarRef
    collation: str | None = None

    def to_dict(self):
        return {'column': self.column, 'operator': self.operator, 'value': self.value.to_dict(), 'collation': self.collation}


@dataclass(frozen=True, slots=True)
class Projection:
    column: str
    output_name: str

    def to_dict(self):
        return {'column': self.column, 'outputName': self.output_name}


@dataclass(frozen=True, slots=True)
class SortTerm:
    column: str
    descending: bool
    nulls_first: bool

    def to_dict(self):
        return {'column': self.column, 'descending': self.descending, 'nullsFirst': self.nulls_first}


@dataclass(frozen=True, slots=True)
class RecognizedSQL:
    original_sql: str
    config_sha256: str
    table: TableConfig
    operation: str
    projections: tuple[Projection, ...]
    predicates: tuple[PredicateTerm, ...]
    assignments: tuple[tuple[str, ScalarRef], ...]
    insert_columns: tuple[str, ...]
    insert_rows: tuple[tuple[ScalarRef, ...], ...]
    returning: tuple[Projection, ...]
    ordering: tuple[SortTerm, ...]
    parameters: tuple[ScalarRef, ...]
    schema_resolution: str
    requires_no_parameter_argument: bool
    max_text_bytes: int

    def to_dict(self):
        return {'format': PLAN_FORMAT, 'parserContract': PARSER_CONTRACT, 'sqlglotVersion': SQLGLOT_VERSION,
                'configSha256': self.config_sha256, 'sqlSha256': _sha(self.original_sql), 'originalSql': self.original_sql,
                'table': self.table.to_dict(), 'operation': self.operation, 'schemaResolution': self.schema_resolution,
                'projections': [p.to_dict() for p in self.projections], 'predicates': [p.to_dict() for p in self.predicates],
                'assignments': [{'column': c, 'value': v.to_dict()} for c, v in self.assignments],
                'insertColumns': list(self.insert_columns), 'insertRows': [[v.to_dict() for v in row] for row in self.insert_rows],
                'returning': [p.to_dict() for p in self.returning], 'ordering': [term.to_dict() for term in self.ordering],
                'parameters': [p.to_dict() for p in self.parameters], 'requiresNoParameterArgument': self.requires_no_parameter_argument,
                'databaseSyntaxValidated': False, 'sourceAuthenticated': False, 'captureFactsProduced': False,
                'moonbitProjectionVerified': False, 'returningIsPredicateRead': False,
                'requiredProofs': ['catalog-types-primary-key-and-text-collation', 'session-schema-resolution', 'server-encoding-and-string-literal-rules',
                    'actual-execution-and-delivered-result-shape', 'complete-fetch-for-predicate-read',
                    'installed-unique-version-sources-and-effective-write-ledger', 'same-statement-or-native-observed-read-version-identity', 'complete-source-window-and-writer-scope',
                    'independent-MoonBit-original-SQL-parameters-source-projection']}

    def bind(self, parameters=None):
        """Validate supplied materialized parameters, never consume an iterator.

        Returned immutable typed bindings are not actual driver observations.
        No SQL rendering, execution, result inspection or history construction.
        """
        if self.requires_no_parameter_argument and parameters is not None:
            raise RecognitionError('driver-format-ambiguity', 'Percent text outside bind slots requires parameters=None')
        kinds = {p.kind for p in self.parameters}
        if not kinds:
            if parameters is not None and not (type(parameters) in (tuple, list, dict) and len(parameters) == 0):
                raise RecognitionError('parameter-arity', 'Statement has no bind slots')
            return ()
        if kinds == {'named'}:
            required = {p.value for p in self.parameters}
            if type(parameters) is not dict or set(parameters) != required:
                raise RecognitionError('parameter-arity', 'Exact original named parameters required')
            values = [parameters[p.value] for p in self.parameters]
        elif kinds == {'positional'}:
            if type(parameters) not in (tuple, list) or len(parameters) != len(self.parameters):
                raise RecognitionError('parameter-arity', 'Exact materialized positional parameters required')
            values = parameters
        else:
            raise RecognitionError('mixed-parameters', 'Mixed named/positional parameters are unsupported')
        result = []
        for reference, value in zip(self.parameters, values):
            _value(value, reference.type, self.max_text_bytes)
            result.append((reference, value))
        return tuple(result)


def _value(value, kind, text_limit):
    if kind == 'int64':
        valid = type(value) is int and -(1 << 63) <= value < (1 << 63)
    elif kind == 'bool':
        valid = type(value) is bool
    else:
        valid = type(value) is str and '\x00' not in value
        if valid:
            try:
                valid = len(value.encode('utf-8', errors='strict')) <= text_limit
            except UnicodeError:
                valid = False
    if not valid:
        raise RecognitionError('parameter-type', 'An exact non-NULL ' + kind + ' value is required')


def _dependency():
    try:
        import sqlglot
        from sqlglot import exp
        from sqlglot.dialects import Dialect
        version = importlib.metadata.version('sqlglot')
    except (ImportError, importlib.metadata.PackageNotFoundError) as error:
        raise OptionalParserUnavailable('Install the hash-pinned optional SQLGlot 30.26.0 dependency explicitly') from error
    if version != SQLGLOT_VERSION or not hasattr(sqlglot, 'tokenize'):
        raise OptionalParserUnavailable('This parser contract requires exactly SQLGlot 30.26.0')
    return sqlglot, exp, Dialect


def _active(value):
    return value is not None and value is not False and value != []


def _args(node, allowed):
    extra = [key for key, value in node.args.items() if key not in allowed and _active(value)]
    if extra:
        raise RecognitionError('unsupported-clause', 'Unsupported ' + type(node).__name__ + ' clauses: ' + ','.join(extra))


class _Builder:
    def __init__(self, config, sql, exp, slots):
        self.config, self.sql, self.exp, self.slots = config, sql, exp, slots
        self.parameters = []
        self.table = self.alias = self.resolution = None

    def name(self, node):
        if not isinstance(node, self.exp.Identifier):
            raise RecognitionError('identifier-shape', 'Simple PostgreSQL identifiers required')
        _args(node, {'this', 'quoted'})
        value = node.this
        _identifier(value)
        if node.args.get('quoted'):
            return value
        if not _UNQUOTED.fullmatch(value):
            raise RecognitionError('unquoted-identifier', 'Non-ASCII identifiers must be quoted to avoid locale folding assumptions')
        return value.lower()

    def relation(self, node):
        if not isinstance(node, self.exp.Table):
            raise RecognitionError('single-table', 'A single configured base table is required')
        _args(node, {'this', 'db', 'alias'})
        table = self.name(node.this)
        if node.args.get('db') is None:
            schema = self.config.default_schema
            if schema is None:
                raise RecognitionError('schema-resolution', 'Unqualified SQL requires an explicit configured default schema')
            self.resolution = 'configured-default-schema-requires-session-proof'
        else:
            schema = self.name(node.args['db'])
            self.resolution = 'explicit-schema'
        for item in self.config.tables:
            if (item.schema, item.table) == (schema, table):
                self.table = item
                break
        if self.table is None:
            raise RecognitionError('unknown-table', 'Table is outside the immutable configuration')
        alias = node.args.get('alias')
        if alias is not None:
            _args(alias, {'this'})
            self.alias = self.name(alias.this)

    def column(self, node, *, star=False):
        if not isinstance(node, self.exp.Column):
            raise RecognitionError('column-shape', 'Only configured direct column references are supported')
        _args(node, {'this', 'table', 'db'})
        qualifier = node.args.get('table')
        if qualifier is not None and self.name(qualifier) != (self.alias or self.table.table):
            raise RecognitionError('column-qualifier', 'Column does not refer to the selected table or alias')
        schema = node.args.get('db')
        if schema is not None and (self.alias is not None or self.name(schema) != self.table.schema or qualifier is None):
            raise RecognitionError('column-qualifier', 'Invalid schema-qualified column')
        if star and isinstance(node.this, self.exp.Star):
            _args(node.this, set())
            return None
        return self.table.column(self.name(node.this))

    def projections(self, nodes):
        result = []
        for node in nodes:
            output = None
            if isinstance(node, self.exp.Alias):
                _args(node, {'this', 'alias'})
                output = self.name(node.args['alias'])
                node = node.this
            if isinstance(node, self.exp.Star):
                _args(node, set())
                column = None
            else:
                column = self.column(node, star=True)
            if column is None:
                if output is not None:
                    raise RecognitionError('projection-shape', 'Star aliases are unsupported')
                result.extend(Projection(c.name, c.name) for c in self.table.columns)
            else:
                result.append(Projection(column.name, output or column.name))
        if not result:
            raise RecognitionError('projection-shape', 'At least one direct result column required')
        return tuple(result)

    def scalar(self, node, column):
        e = self.exp
        while isinstance(node, e.Paren):
            _args(node, {'this'})
            node = node.this
        if isinstance(node, e.Placeholder):
            _args(node, {'this'})
            raw = node.args.get('this')
            if raw is None:
                reference = ScalarRef('positional', len(self.parameters), column.type)
            elif isinstance(raw, e.Identifier) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', str(raw.this)):
                reference = ScalarRef('named', raw.this, column.type)
            else:
                raise RecognitionError('parameter-shape', 'Exact psycopg named or positional s placeholders required')
            self.parameters.append(reference)
            return reference
        negative = isinstance(node, e.Neg)
        if negative:
            _args(node, {'this'})
            node = node.this
        if isinstance(node, e.Literal):
            _args(node, {'this', 'is_string'})
            if node.is_string and not negative:
                value = node.this
            elif not node.is_string and re.fullmatch(r'[0-9]{1,19}', str(node.this)):
                value = int(node.this) * (-1 if negative else 1)
            else:
                raise RecognitionError('scalar-expression', 'Only canonical int64, bool and text literals are supported')
        elif isinstance(node, e.Boolean) and not negative:
            _args(node, {'this'})
            value = node.this
        else:
            raise RecognitionError('scalar-expression', 'Functions, NULL, column expressions, casts and native numbered binds are unsupported')
        _value(value, column.type, self.config.max_text_bytes)
        return ScalarRef('literal', value, column.type)

    def predicates(self, where):
        if where is None:
            return ()
        _args(where, {'this'})
        pending = [where.this]
        result = []
        operations = {self.exp.EQ: 'eq', self.exp.LT: 'lt', self.exp.LTE: 'le', self.exp.GT: 'gt', self.exp.GTE: 'ge'}
        while pending:
            node = pending.pop()
            if isinstance(node, self.exp.Paren):
                _args(node, {'this'});pending.append(node.this);continue
            if isinstance(node, self.exp.And):
                _args(node, {'this', 'expression'});pending.extend([node.expression, node.this]);continue
            operation = operations.get(type(node))
            if operation is None:
                raise RecognitionError('predicate-shape', 'Only equality/range comparisons combined with AND are supported')
            _args(node, {'this', 'expression'})
            left, collation = node.this, None
            if isinstance(left, self.exp.Collate):
                _args(left, {'this', 'expression'})
                collation = self.name(left.expression)
                if collation != 'C':
                    raise RecognitionError('text-collation', 'Only explicit COLLATE "C" is supported')
                left = left.this
            column = self.column(left)
            if collation is not None and column.type != 'text':
                raise RecognitionError('text-collation', 'COLLATE requires a configured text column')
            if column.type == 'bool' and operation != 'eq':
                raise RecognitionError('predicate-type', 'Boolean predicates support equality only')
            result.append(PredicateTerm(column.name, operation, self.scalar(node.expression, column), collation))
            if len(result) > self.config.max_terms:
                raise RecognitionError('predicate-budget', 'AND term budget exhausted')
        return tuple(result)

    def build(self, ast, stray_percent):
        e = self.exp
        operation = type(ast)
        if operation is e.Select:
            _args(ast, {'expressions', 'from_', 'where', 'order'})
            source = ast.args.get('from_')
            if source is None:
                raise RecognitionError('single-table', 'SELECT must read one configured table')
            _args(source, {'this'})
            self.relation(source.this)
            projections = self.projections(ast.expressions)
        elif operation in (e.Insert, e.Update, e.Delete):
            _args(ast, {'this', 'expression', 'expressions', 'where', 'returning'})
            target = ast.this.this if isinstance(ast.this, e.Schema) else ast.this
            self.relation(target)
            projections = ()
        else:
            raise RecognitionError('statement-kind', 'Only SELECT/INSERT/UPDATE/DELETE are supported')
        assignments, columns, rows = [], [], []
        if operation is e.Insert:
            if not isinstance(ast.this, e.Schema):
                raise RecognitionError('insert-columns', 'INSERT requires explicit configured columns')
            _args(ast.this, {'this', 'expressions'})
            columns = [self.name(column) for column in ast.this.expressions]
            if not columns or len(set(columns)) != len(columns) or self.table.primary_key not in columns:
                raise RecognitionError('insert-columns', 'Distinct explicit columns including the primary key are required')
            configured = [self.table.column(column) for column in columns]
            values = ast.args.get('expression')
            if not isinstance(values, e.Values):
                raise RecognitionError('insert-values', 'Only bounded VALUES rows are supported')
            _args(values, {'expressions'})
            if not 1 <= len(values.expressions) <= self.config.max_insert_rows:
                raise RecognitionError('insert-budget', 'INSERT row budget exhausted')
            for row in values.expressions:
                if not isinstance(row, e.Tuple) or len(row.expressions) != len(columns):
                    raise RecognitionError('insert-arity', 'Each VALUES row must match the explicit column list')
                _args(row, {'expressions'})
                rows.append(tuple(self.scalar(node, column) for node, column in zip(row.expressions, configured)))
        elif operation is e.Update:
            for assignment in ast.expressions:
                if not isinstance(assignment, e.EQ):
                    raise RecognitionError('assignment-shape', 'Direct scalar assignments required')
                _args(assignment, {'this', 'expression'})
                column = self.column(assignment.this)
                if column.name == self.table.primary_key:
                    raise RecognitionError('primary-key-update', 'Primary-key mutation is outside this candidate profile')
                if column.name in {name for name, _ in assignments}:
                    raise RecognitionError('duplicate-assignment', 'Duplicate UPDATE column')
                assignments.append((column.name, self.scalar(assignment.expression, column)))
            if not assignments:
                raise RecognitionError('assignment-shape', 'UPDATE requires assignments')
        predicates = self.predicates(ast.args.get('where'))
        returning = ast.args.get('returning')
        if returning is not None:
            _args(returning, {'expressions'})
            returning = self.projections(returning.expressions)
        else:
            returning = ()
        ordering = []
        order = ast.args.get('order')
        if order is not None:
            _args(order, {'expressions'})
            for term in order.expressions:
                _args(term, {'this', 'desc', 'nulls_first'})
                column = self.column(term.this)
                ordering.append(SortTerm(column.name, bool(term.args.get('desc')), bool(term.args.get('nulls_first'))))
        lexical = [(kind, name) for kind, name in self.slots]
        actual = [(p.kind, p.value if p.kind == 'named' else None) for p in self.parameters]
        if actual != lexical:
            raise RecognitionError('parameter-projection', 'AST bind slots do not preserve original lexical parameter order')
        if len({p.kind for p in self.parameters}) > 1:
            raise RecognitionError('mixed-parameters', 'Mixed named and positional placeholders are unsupported')
        if stray_percent and self.parameters:
            raise RecognitionError('driver-format-ambiguity', 'Percent escapes/text beside binds require a separate verified driver-format contract')
        return RecognizedSQL(self.sql, self.config.sha256, self.table, operation.__name__.lower(), projections,
            predicates, tuple(assignments), tuple(columns), tuple(rows), returning, tuple(ordering),
            tuple(self.parameters), self.resolution, bool(stray_percent), self.config.max_text_bytes)


def _recognize(config, sql):
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
                    raise RecognitionError('parameter-format', 'Only exact psycopg %s or %(name)s placeholders are supported')
                slots.append(('named', match.group(1)) if match.group(1) else ('positional', None))
                covered.add(token.start)
        stray_percent = any(char == '%' and index not in covered for index, char in enumerate(sql))
        statements = Dialect.get_or_raise('postgres').parser(error_level=sqlglot.ErrorLevel.RAISE).parse(tokens, sql)
        if len(statements) != 1 or statements[0] is None:
            raise RecognitionError('statement-count', 'Exactly one statement required')
        ast = statements[0]
        for index, node in enumerate(ast.walk(), 1):
            if index > config.max_ast_nodes:
                raise RecognitionError('ast-budget', 'AST node budget exhausted')
            if isinstance(node, exp.Null):
                raise RecognitionError('null-semantics', 'NULL semantics are outside the configured candidate profile')
            if isinstance(node, exp.Func) and type(node) not in (exp.And, exp.Collate):
                raise RecognitionError('sql-function', 'Functions, aggregates and casts are outside this candidate profile')
            if isinstance(node, (exp.Join, exp.Subquery, exp.CTE, exp.Union, exp.Intersect, exp.Except)):
                raise RecognitionError('multi-relation', 'JOIN, CTE, subquery and set operations are unsupported')
        return _Builder(config, sql, exp, slots).build(ast, stray_percent)
    except RecognitionError:
        raise
    except (sqlglot.errors.SqlglotError, RecursionError, ValueError, TypeError, AttributeError) as error:
        raise RecognitionError('parse-or-shape', 'SQLGlot candidate parsing failed: ' + type(error).__name__) from error


@dataclass(frozen=True, slots=True)
class CacheInfo:
    entries: int
    bytes: int
    hits: int
    misses: int


class ConfiguredSQLParser:
    """A local structural cache bounded by count and accounted UTF-8 bytes.

    No driver parameters, result rows or mutable ASTs are kept. Accounted bytes
    are serialized plan/key bytes, not a promise about Python object RSS.
    """
    def __init__(self, config, *, cache_entries=256, cache_bytes=4 * 1024 * 1024):
        if type(config) is not SQLCaptureConfig:
            raise ValueError('An immutable SQLCaptureConfig is required')
        _integer(cache_entries, 0, 4096, 'cache_entries')
        _integer(cache_bytes, 0, 16 * 1024 * 1024, 'cache_bytes')
        self._config, self._entries, self._maximum = config, cache_entries, cache_bytes
        self._cache, self._bytes, self._hits, self._misses = OrderedDict(), 0, 0, 0
        self._lock = threading.RLock()

    @property
    def config(self):
        return self._config

    def recognize(self, sql):
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
        plan = _recognize(self._config, sql)
        size = len(_canonical(plan.to_dict()).encode('utf-8')) + len(sql.encode('utf-8'))
        with self._lock:
            if self._entries and size <= self._maximum:
                prior = self._cache.pop(sql, None)
                if prior is not None:
                    self._bytes -= prior[1]
                while self._cache and (len(self._cache) >= self._entries or self._bytes + size > self._maximum):
                    _, (_, removed) = self._cache.popitem(last=False)
                    self._bytes -= removed
                self._cache[sql] = (plan, size)
                self._bytes += size
        return plan

    def cache_info(self):
        with self._lock:
            return CacheInfo(len(self._cache), self._bytes, self._hits, self._misses)
