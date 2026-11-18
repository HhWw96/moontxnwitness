"""Pure PostgreSQL 18 point-CRUD projection construction; executes no SQL.

The descriptor is a deterministic construction claim. It is neither a source
fact nor evidence that the configured version column exists or is maintained.
No driver, ORM, installer, cursor or result-row adapter is exposed here.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import uuid

from .configured_sql import RecognitionError, OptionalParserUnavailable, _canonical, _dependency, _identifier, _integer, _sha
from .configured_sql_v2 import RecognizedSQLV2, SQLCaptureConfigV2, ConfiguredSQLParserV2

PROJECTION_FORMAT = 'moontxnwitness-sql-point-projection/v2'
PROJECTION_CONTRACT = 'postgres18-point-crud-same-statement-row-versions/v1'


@dataclass(frozen=True, slots=True)
class PointProjectionOptionsV2:
    config: SQLCaptureConfigV2
    version_column: str = '__mtw_source_version'
    version_type: str = 'int64'
    star_contract: str | None = None
    business_star_columns: tuple[str, ...] | None = None
    max_projected_sql_bytes: int = 131072
    max_descriptor_bytes: int = 16 * 1024 * 1024

    def __post_init__(self):
        if type(self.config) is not SQLCaptureConfigV2:
            raise ValueError('Independent immutable SQLCaptureConfigV2 required')
        _identifier(self.version_column)
        if self.version_column in {c.name for c in self.config.table.columns}:
            raise ValueError('The independent version column must not collide with a business/key column')
        if self.version_type != 'int64':
            raise ValueError('This projection contract requires an int64 / PostgreSQL bigint version column')
        if self.star_contract is None:
            if self.business_star_columns is not None:
                raise ValueError('Business star columns require an explicit preinstallation business-view contract')
        elif self.star_contract != 'preinstallation-business-schema/v1' or type(self.business_star_columns) is not tuple or self.business_star_columns != tuple(c.name for c in self.config.table.columns):
            raise ValueError('Explicit preinstallation star columns must match configured key/business column order without metadata')
        _integer(self.max_projected_sql_bytes, 1, 2 * 1024 * 1024, 'max_projected_sql_bytes')
        _integer(self.max_descriptor_bytes, 1, 64 * 1024 * 1024, 'max_descriptor_bytes')

    def to_dict(self):
        return {'config': self.config.to_dict(), 'versionColumn': self.version_column,
                'versionType': self.version_type, 'starContract': self.star_contract,
                'businessStarColumns': None if self.business_star_columns is None else list(self.business_star_columns),
                'maxProjectedSqlBytes': self.max_projected_sql_bytes,
                'maxDescriptorBytes': self.max_descriptor_bytes}


@dataclass(frozen=True, slots=True)
class ProjectedSQLV2:
    sql: str
    parameters: tuple
    descriptor_json: str

    def to_dict(self):
        """A detached description; changing it cannot change SQL or arguments."""
        return json.loads(self.descriptor_json)


def _atom(value):
    # Preserve raw UUID text spelling separately from its declared SQL identity.
    # No UUID canonicalization or int64 -> float conversion reaches call args.
    if type(value) is bool:
        return {'pythonType': 'bool', 'value': value}
    if type(value) is int:
        return {'pythonType': 'int', 'decimal': str(value)}
    if type(value) is str:
        return {'pythonType': 'str', 'value': value}
    if type(value) is uuid.UUID:
        return {'pythonType': 'uuid.UUID', 'value': str(value)}
    raise RecognitionError('projection-parameter-type', 'Materialized immutable scalar arguments required')


def _original_parameters(parameters):
    if parameters is None:
        return {'container': 'none', 'items': []}
    if type(parameters) is dict:
        return {'container': 'dict', 'items': [{'name': key, 'value': _atom(value)}
                for key, value in parameters.items()]}
    return {'container': 'tuple' if type(parameters) is tuple else 'list',
            'items': [_atom(value) for value in parameters]}


def _quote(name):
    # Every generated statement has positional arguments. Psycopg requires a
    # literal % to be doubled even inside a quoted identifier.
    return '"' + name.replace('"', '""').replace('%', '%%') + '"'


def _fresh(base, used):
    name, suffix = base, 0
    while name in used:
        suffix += 1
        name = base + '_' + str(suffix)
    used.add(name)
    return name


def _confirmed_plan(plan, options):
    if type(plan) is not RecognizedSQLV2 or type(options) is not PointProjectionOptionsV2:
        raise RecognitionError('projection-input', 'RecognizedSQLV2 and independent PointProjectionOptionsV2 required')
    # A frozen dataclass is still caller-constructible. Reparse original text;
    # neither its embedded fingerprint nor its operation can authorize a rewrite.
    actual = ConfiguredSQLParserV2(options.config, cache_entries=0).recognize(plan.original_sql)
    try:
        equal = _canonical(actual.to_dict()) == _canonical(plan.to_dict())
    except (ValueError, TypeError, AttributeError, IndexError):
        equal = False
    if not equal:
        raise RecognitionError('projection-candidate-mismatch', 'Candidate differs from independent original-SQL recognition')
    return actual


def _has_star(plan):
    # Examine only original result expressions after independent V2 recognition.
    # A quoted identifier or string containing '*' is not a wildcard node.
    sqlglot, exp, _ = _dependency()
    ast = sqlglot.parse_one(plan.original_sql, read='postgres')
    result = ast if plan.operation == 'select' else ast.args.get('returning')
    return result is not None and any(type(node) is exp.Star
        for expression in result.expressions for node in expression.walk())


def build_point_projection(plan, original_parameters, options):
    """Construct SQL/args and a bounded descriptor from independent inputs.

    SELECT reads retain the complete business projection and append the same
    row's configured version column. DML RETURNING contains business outputs
    first, then explicit OLD/NEW row images and versions as write observations.
    """
    plan = _confirmed_plan(plan, options)
    star = _has_star(plan)
    if star and options.star_contract is None:
        raise RecognitionError('projection-star-view-required', 'Star projection requires an explicit preinstallation business-schema view')
    bindings = plan.bind(original_parameters)
    table = plan.table
    used = {table.schema, table.table, options.version_column,
            *(c.name for c in table.columns),
            *(p.output_name for p in plan.projections + plan.returning)}
    old_alias = _fresh('__mtw_v2_old', used)
    new_alias = _fresh('__mtw_v2_new', used)
    values, mapping = [], []

    def scalar(reference):
        if reference.kind == 'named':
            value = original_parameters[reference.value]
            origin = {'kind': 'named', 'name': reference.value}
        elif reference.kind == 'positional':
            value = original_parameters[reference.value]
            origin = {'kind': 'positional', 'index': reference.value}
        else:
            value = reference.value
            origin = {'kind': 'literal', 'value': _atom(value)}
        index = len(values)
        values.append(value)
        mapping.append({'projectedIndex': index, 'original': origin,
                        'sqlType': reference.type, 'value': _atom(value),
                        'cast': 'uuid' if reference.type == 'uuid' else None})
        return 'CAST(%s AS UUID)' if reference.type == 'uuid' else '%s'

    target = _quote(table.schema) + '.' + _quote(table.table)
    if plan.operation == 'insert':
        sql = 'INSERT INTO ' + target + ' (' + ', '.join(_quote(c) for c in plan.insert_columns)
        sql += ') VALUES (' + ', '.join(scalar(r) for r in plan.insert_rows[0]) + ')'
    else:
        if plan.operation == 'select':
            sql = 'SELECT ' + ', '.join(_quote(p.column) + ' AS ' + _quote(p.output_name)
                                       for p in plan.projections)
            read_alias = _fresh('__mtw_v2_read_version', used)
            sql += ', ' + _quote(options.version_column) + ' AS ' + _quote(read_alias) + ' FROM ' + target
        elif plan.operation == 'update':
            sql = 'UPDATE ' + target + ' SET ' + ', '.join(_quote(c) + ' = ' + scalar(r)
                                                          for c, r in plan.assignments)
        else:
            sql = 'DELETE FROM ' + target
        predicate = plan.predicates[0]
        sql += ' WHERE ' + _quote(predicate.column)
        if predicate.collation is not None:
            sql += ' COLLATE ' + _quote(predicate.collation)
        sql += ' = ' + scalar(predicate.value)

    business = plan.projections if plan.operation == 'select' else plan.returning
    business_result = {'mode': 'rows' if business else 'no-result',
        'rowImage': 'read' if plan.operation == 'select' else 'old' if plan.operation == 'delete' else 'new',
        'columns': [{'nativeIndex': i, 'column': p.column, 'outputName': p.output_name}
                    for i, p in enumerate(business)],
        'requiresProjectionBeforeDelivery': True, 'nativeResultDirectlyDeliverable': False}
    hidden = []
    if plan.operation == 'select':
        hidden.append({'image': 'read', 'role': 'positive-read-version-candidate',
            'columns': [{'column': c.name, 'nativeIndex': next(i for i, p in enumerate(business) if p.column == c.name)}
                        for c in table.columns],
            'version': {'column': options.version_column, 'type': 'int64',
                        'nativeIndex': len(business), 'outputName': read_alias}})
    else:
        aliases = {'old': old_alias, 'new': new_alias}
        image = 'old' if plan.operation == 'delete' else 'new'
        returning = [(_quote(aliases[image]) + '.' + _quote(p.column) + ' AS ' + _quote(p.output_name))
                     for p in business]
        for image in (('old', 'new') if plan.operation == 'update' else ('new',) if plan.operation == 'insert' else ('old',)):
            columns = []
            for column in table.columns:
                name = _fresh('__mtw_v2_' + image + '_' + str(len(columns)), used)
                columns.append({'column': column.name, 'nativeIndex': len(returning), 'outputName': name})
                returning.append(_quote(aliases[image]) + '.' + _quote(column.name) + ' AS ' + _quote(name))
            name = _fresh('__mtw_v2_' + image + '_version', used)
            version = {'column': options.version_column, 'type': 'int64',
                       'nativeIndex': len(returning), 'outputName': name}
            returning.append(_quote(aliases[image]) + '.' + _quote(options.version_column) + ' AS ' + _quote(name))
            hidden.append({'image': image, 'role': 'write-effect-observation-only',
                           'columns': columns, 'version': version})
        sql += ' RETURNING WITH (OLD AS ' + _quote(old_alias) + ', NEW AS ' + _quote(new_alias) + ') '
        sql += ', '.join(returning)

    if len(sql.encode('utf-8')) > options.max_projected_sql_bytes:
        raise RecognitionError('projection-sql-budget', 'Projected SQL exceeds the independent byte limit')
    document = {
        'format': PROJECTION_FORMAT, 'projectionContract': PROJECTION_CONTRACT,
        'postgresqlMajor': 18, 'driverFormat': 'psycopg-positional-s-with-percent-escaping/v1',
        'originalSql': plan.original_sql, 'originalSqlSha256': _sha(plan.original_sql),
        'candidate': plan.to_dict(), 'configSha256': options.config.sha256,
        'originalParameters': _original_parameters(original_parameters),
        'typedInputBindings': [{'reference': ref.to_dict(), 'value': _atom(value)} for ref, value in bindings],
        'independentOptions': options.to_dict(), 'optionsSha256': _sha(_canonical(options.to_dict())),
        'projectedSql': sql, 'projectedSqlSha256': _sha(sql), 'parameterMap': mapping,
        'businessResult': business_result, 'hiddenResults': hidden,
        'businessStarView': None if not star else {
            'contract': options.star_contract, 'columns': list(options.business_star_columns),
            'catalogVerified': False, 'installationVerified': False,
            'equivalentToCurrentNativeStar': False},
        'returningAliases': None if plan.operation == 'select' else {'old': old_alias, 'new': new_alias},
        'nativeColumnCount': len(business) + 1 if plan.operation == 'select' else len(returning),
        'zeroRowsPolicy': 'diagnostic-only-no-absence-source',
        'returningIsPredicateRead': False, 'writeImagesAreSelectFacts': False,
        'producesDeletionVersion': False, 'databaseExecuted': False,
        'databaseSyntaxValidated': False, 'sourceAuthenticated': False,
        'captureFactsProduced': False, 'sourceFactsProduced': False,
        'completeWindow': False, 'modelCoverageAccepted': False, 'moonbitProjectionVerified': False,
        'requiredProofs': [
            'independent-MoonBit-original-SQL-parameters-and-projection-recomputation',
            'PostgreSQL18-catalog-key-types-business-types-text-comparison-and-column-order',
            'installed-bigint-version-column-nonnull-unique-per-change-and-effective-write-journal',
            'session-schema-server-encoding-permissions-triggers-rules-and-DDL-epoch',
            'actual-statement-success-native-result-types-command-tag-and-complete-fetch',
            'original-business-row-and-no-result-delivery-projection',
            'initialized-snapshot-negative-read-sources-and-closed-writer-window',
        ],
    }
    if star:
        document['requiredProofs'].extend([
            'preinstallation-physical-columns-and-order-equal-declared-business-star-view',
            'version-column-newly-installed-and-not-an-original-business-column',
            'postinstallation-only-declared-version-column-added-to-original-table-schema',
            'independent-MoonBit-catalog-installation-and-business-star-projection-recomputation',
        ])
    descriptor = _canonical(document)
    if len(descriptor.encode('utf-8')) > options.max_descriptor_bytes:
        raise RecognitionError('projection-descriptor-budget', 'Projection descriptor exceeds the independent byte limit')
    return ProjectedSQLV2(sql, tuple(values), descriptor)


def verify_point_projection(descriptor, plan, original_parameters, independent_options):
    """Rebuild from caller inputs; embedded options never authorize verification.

    A true result means descriptor reproduction only, with no SQL execution or
    source/model/Window acceptance. No native result rows are accepted here.
    """
    try:
        expected = build_point_projection(plan, original_parameters, independent_options)
        if type(descriptor) is str:
            if len(descriptor.encode('utf-8')) > independent_options.max_descriptor_bytes:
                raise ValueError('Descriptor exceeds independent byte limit')
            def unique(pairs):
                value = {}
                for key, item in pairs:
                    if key in value:
                        raise ValueError('Duplicate descriptor key')
                    value[key] = item
                return value
            descriptor = json.loads(descriptor, object_pairs_hook=unique)
        if type(descriptor) is not dict:
            raise ValueError('Descriptor must be an object')
        actual = _canonical(descriptor)
        if len(actual.encode('utf-8')) > independent_options.max_descriptor_bytes:
            raise ValueError('Descriptor exceeds independent byte limit')
        valid = actual == expected.descriptor_json
        return {'valid': valid, 'scope': 'projection-descriptor-reproduction-only',
                'databaseExecuted': False, 'sourceFactsProduced': False,
                'completeWindow': False, 'modelCoverageAccepted': False}
    except (ValueError, TypeError, AttributeError, RecursionError, UnicodeError, IndexError, OptionalParserUnavailable) as error:
        return {'valid': False, 'reason': str(error), 'scope': 'projection-descriptor-reproduction-only',
                'databaseExecuted': False, 'sourceFactsProduced': False,
                'completeWindow': False, 'modelCoverageAccepted': False}
