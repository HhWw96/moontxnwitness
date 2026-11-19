"""Offline point-CRUD candidate checks. No DB connections or execution."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
import uuid

from .configured_sql import ColumnConfig, TEXT_COMPARISON, RecognitionError, OptionalParserUnavailable
from .configured_sql_v2 import (
    SQLCaptureConfigV2, TableConfigV2, PrimaryKeyConfigV2, ConfiguredSQLParserV2,
    CONFIG_FORMAT, PLAN_FORMAT, PARSER_CONTRACT,
)


def column(name, kind='text'):
    return ColumnConfig(name, kind, TEXT_COMPARISON if kind == 'text' else None)


def layouts():
    return (
        TableConfigV2('ledger', 'accounts', PrimaryKeyConfigV2('account_no', 'int64'),
            (column('balance', 'int64'), column('active', 'bool'), column('label'))),
        TableConfigV2('App-X', 'Customer.Space', PrimaryKeyConfigV2('User ID', 'text', TEXT_COMPARISON),
            (column('quota', 'int64'), column('live', 'bool'), column('zone'), column('score', 'int64'), column('note'))),
        TableConfigV2('identity', 'members', PrimaryKeyConfigV2('member_uuid', 'uuid'),
            (column('email'), column('is_active', 'bool'))),
    )


def quote(value):
    return '"' + value.replace('"', '""') + '"'


def target(table):
    return quote(table.schema) + '.' + quote(table.table)


def fields(table):
    return ','.join(quote(c.name) for c in table.columns)


def key_bind(table, name=None):
    slot = '%s' if name is None else '%(' + name + ')s'
    return slot + ('::UUID' if table.key.type == 'uuid' else '')


def read_sql(table):
    return 'SELECT ' + fields(table) + ' FROM ' + target(table) + ' WHERE ' + quote(table.primary_key) + '=' + key_bind(table)


def values(table):
    return tuple(uuid.UUID('A8098C1A-F86E-11DA-BD1A-00112444BE1E') if c.type == 'uuid'
        else '测试值' if c.type == 'text' else True if c.type == 'bool' else 8 for c in table.columns)


class ConfigV2Tests(unittest.TestCase):
    def test_distinct_versioned_contract_and_strict_v1_boundary(self):
        from .configured_sql import SQLCaptureConfig, TableConfig, ConfiguredSQLParser, CONFIG_FORMAT as V1_FORMAT
        config = SQLCaptureConfigV2(layouts()[0])
        self.assertNotEqual(CONFIG_FORMAT, V1_FORMAT)
        self.assertIn('/v2', PARSER_CONTRACT)
        self.assertIn('/v2', PLAN_FORMAT)
        with self.assertRaises(ValueError): SQLCaptureConfig.from_json(json.dumps(config.to_dict()))
        old = SQLCaptureConfig((TableConfig('s', 't', 'id', (column('id', 'int64'), column('n', 'int64'))),))
        with self.assertRaises(ValueError): SQLCaptureConfigV2.from_json(json.dumps(old.to_dict()))
        with self.assertRaises(ValueError): ConfiguredSQLParserV2(old)
        with self.assertRaises(ValueError): ConfiguredSQLParser(config)
        with self.assertRaises(ValueError): column('uuid', 'uuid')
        # Existing V1 multirow and literal-assignment behavior remains available.
        self.assertEqual(len(ConfiguredSQLParser(old).recognize('INSERT INTO s.t(id,n) VALUES(1,2),(3,4)').insert_rows), 2)
        self.assertEqual(ConfiguredSQLParser(old).recognize('UPDATE s.t SET n=2 WHERE id=1').operation, 'update')

    def test_config_roundtrip_fingerprint_and_immutable_detached_values(self):
        for table in layouts():
            config = SQLCaptureConfigV2(table)
            restored = SQLCaptureConfigV2.from_json(json.dumps(config.to_dict()))
            self.assertEqual(config, restored)
            self.assertEqual(config.sha256, restored.sha256)
            detached = config.to_dict(); detached['table']['businessColumns'].clear()
            self.assertTrue(table.business_columns)
            with self.assertRaises(FrozenInstanceError): config.default_schema = 'elsewhere'
            with self.assertRaises(FrozenInstanceError): table.key.type = 'text'
            with self.assertRaises(FrozenInstanceError): table.business_columns[0].name = 'renamed'
            self.assertNotEqual(config.sha256, replace(config, default_schema='other').sha256)
            self.assertNotEqual(config.sha256, replace(config, max_text_bytes=100).sha256)

    def test_one_table_and_one_to_sixteen_business_fields(self):
        table = layouts()[0]
        for invalid in [None, layouts(), [table]]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError): SQLCaptureConfigV2(invalid)
        for invalid in [(), list(table.business_columns), tuple(column('v' + str(i), 'int64') for i in range(17))]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError): replace(table, business_columns=invalid)
        self.assertEqual(len(replace(table, business_columns=tuple(column('v' + str(i), 'int64') for i in range(16))).columns), 17)
        with self.assertRaises(ValueError): replace(table, business_columns=(column(table.primary_key),))
        with self.assertRaises(ValueError): replace(table, business_columns=(column('n'), column('n')))
        with self.assertRaises(ValueError): replace(table, key=column('id', 'int64'))

    def test_primary_key_types_and_comparison_are_explicit(self):
        for args in [('id','bool'), ('id','uuid',TEXT_COMPARISON), ('id','text'), ('id','text','default')]:
            with self.subTest(args=args), self.assertRaises(ValueError): PrimaryKeyConfigV2(*args)
        for kind in ['json', 'uuid']:
            with self.subTest(kind=kind), self.assertRaises(ValueError): column('data', kind)

    def test_unknown_and_duplicate_config_fields_rejected(self):
        base = SQLCaptureConfigV2(layouts()[0]).to_dict()
        for path in [(), ('table',), ('table','primaryKey'), ('table','businessColumns',0), ('limits',)]:
            document = json.loads(json.dumps(base)); obj = document
            for key in path: obj = obj[key]
            obj['assumeSourceVerified'] = True
            with self.subTest(path=path), self.assertRaises(ValueError): SQLCaptureConfigV2.from_json(json.dumps(document))
        for text in ['{"format":"x","for\\u006dat":"x"}', '{"format":NaN}', '[]']:
            with self.subTest(text=text), self.assertRaises(ValueError): SQLCaptureConfigV2.from_json(text)


class PointCandidateV2Tests(unittest.TestCase):
    def test_three_structurally_distinct_layouts_use_same_parser_for_crud(self):
        for table in layouts():
            parser = ConfiguredSQLParserV2(SQLCaptureConfigV2(table))
            row = values(table)
            insert_slots = ','.join(key_bind(table) if c.name == table.primary_key else '%s' for c in table.columns)
            samples = [
                (read_sql(table), 'select', (row[0],)),
                ('INSERT INTO ' + target(table) + '(' + fields(table) + ') VALUES(' + insert_slots + ') RETURNING ' + fields(table), 'insert', row),
                ('UPDATE ' + target(table) + ' SET ' + quote(table.business_columns[0].name) + '=%s WHERE ' + quote(table.primary_key) + '=' + key_bind(table) + ' RETURNING ' + quote(table.primary_key), 'update', (row[1], row[0])),
                ('DELETE FROM ' + target(table) + ' WHERE ' + quote(table.primary_key) + '=' + key_bind(table), 'delete', (row[0],)),
            ]
            for sql, operation, params in samples:
                with self.subTest(table=table.table, operation=operation):
                    plan = parser.recognize(sql)
                    self.assertEqual(plan.table, table)
                    self.assertEqual(plan.operation, operation)
                    self.assertEqual(plan.original_sql, sql)
                    self.assertEqual(len(plan.bind(params)), len(params))
                    self.assertEqual(plan.key_reference.type, table.key.type)
                    for claim in ['sourceFactsProduced','captureFactsProduced','sourceAuthenticated','modelCoverageAccepted','moonbitProjectionVerified','databaseSyntaxValidated','returningIsPredicateRead']:
                        self.assertIs(plan.to_dict()[claim], False)

    def test_no_key_universe_and_absence_remains_unproved(self):
        for table in layouts():
            parser = ConfiguredSQLParserV2(SQLCaptureConfigV2(table))
            plan = parser.recognize(read_sql(table))
            for n in range(40):
                key = n if table.key.type == 'int64' else 'never-seeded-' + str(n) if table.key.type == 'text' else uuid.UUID(int=n)
                self.assertEqual(len(plan.bind((key,))), 1)
                self.assertIs(parser.recognize(read_sql(table)), plan)
            self.assertFalse(hasattr(parser.config, 'known_ids'))
            self.assertFalse(hasattr(plan, 'rows'))
            self.assertFalse(plan.to_dict()['sourceFactsProduced'])

    def test_sqlalchemy_2055_entity_refresh_and_insert(self):
        # Compile the real pinned ORM without an engine.
        self.assertEqual(importlib.metadata.version('sqlalchemy'), '2.0.55')
        import sqlalchemy as sa
        from sqlalchemy.dialects.postgresql import psycopg
        from sqlalchemy.orm import DeclarativeBase, mapped_column
        class Base(DeclarativeBase): pass
        class Member(Base):
            __tablename__ = 'members'
            __table_args__ = {'schema': 'identity'}
            member_uuid = mapped_column(sa.Uuid, primary_key=True)
            email = mapped_column(sa.String(320), nullable=False)
            is_active = mapped_column(sa.Boolean, nullable=False)
        parser = ConfiguredSQLParserV2(SQLCaptureConfigV2(layouts()[2]))
        mapper = sa.inspect(Member)
        refresh_clause, _ = mapper._get_clause
        statements = [sa.select(Member).where(Member.member_uuid == sa.bindparam('id')),
                      sa.select(Member).where(refresh_clause)]
        for statement in statements:
            compiled = statement.compile(dialect=psycopg.dialect())
            sql = str(compiled)
            self.assertIn('::UUID', sql)
            plan = parser.recognize(sql)
            params = {name: uuid.UUID(int=17) for name in compiled.params}
            self.assertEqual(plan.bind(params)[0][1], '00000000-0000-0000-0000-000000000011')
            self.assertEqual([p.column for p in plan.projections], ['member_uuid','email','is_active'])
        params = {'member_uuid': uuid.UUID(int=17), 'email': '用户🙂', 'is_active': True}
        insert = sa.insert(Member).values(**params).returning(Member.member_uuid).compile(dialect=psycopg.dialect())
        self.assertIn('%(email)s::VARCHAR', str(insert))
        self.assertEqual([raw for _, raw in parser.recognize(str(insert)).bind(insert.params)],
            [str(params['member_uuid']), params['email'], params['is_active']])

    def test_varchar_cast_is_limited_to_unquoted_unbounded_assignment_binds(self):
        parser = ConfiguredSQLParserV2(SQLCaptureConfigV2(layouts()[0]))
        update = 'UPDATE ledger.accounts SET label={} WHERE account_no=%s'
        value = '原始🙂 '
        plan = parser.recognize(update.format('(%s::vArChAr)'))
        self.assertEqual([raw for _, raw in plan.bind((value, 7))], [value, 7])
        for expr in ['%s::varchar(3)', '%s::varchar2', '%s::"varchar"', '%s::aux.varchar',
                     'CAST(%s AS VARCHAR)', '%s::character varying', '%s::varchar[]', "'x'::varchar"]:
            with self.subTest(expr=expr), self.assertRaises(RecognitionError):
                parser.recognize(update.format(expr))
        with self.assertRaises(RecognitionError):
            parser.recognize('UPDATE ledger.accounts SET balance=%s::varchar WHERE account_no=%s')
        with self.assertRaises(RecognitionError):
            ConfiguredSQLParserV2(SQLCaptureConfigV2(layouts()[1])).recognize(read_sql(layouts()[1]) + '::varchar')

    def test_uuid_canonical_log_identity_keeps_business_arguments(self):
        table = layouts()[2]
        parser = ConfiguredSQLParserV2(SQLCaptureConfigV2(table))
        plan = parser.recognize('SELECT * FROM identity.members WHERE member_uuid=%(pk_1)s::UUID')
        canonical = 'a8098c1a-f86e-11da-bd1a-00112444be1e'
        for raw in [uuid.UUID(canonical), canonical, canonical.upper(), canonical.replace('-',''), canonical.upper().replace('-','')]:
            with self.subTest(raw=raw):
                params = {'pk_1': raw}
                self.assertEqual(plan.bind(params)[0][1], canonical)
                self.assertIs(params['pk_1'], raw)
                self.assertEqual(set(params), {'pk_1'})
        uncast = parser.recognize('SELECT * FROM identity.members WHERE member_uuid=%s')
        cast = parser.recognize('SELECT * FROM identity.members WHERE member_uuid=CAST(%s AS UUID)')
        original = [uuid.UUID(canonical)]
        self.assertEqual(uncast.bind(original), cast.bind(original))
        self.assertIsInstance(original[0], uuid.UUID)

    def test_aliases_projection_order_and_full_row_star(self):
        parser = ConfiguredSQLParserV2(SQLCaptureConfigV2(layouts()[0]))
        for projection in ['a.*', 'a.label AS name,a.active AS enabled,a.account_no AS pk,a.balance AS amount']:
            plan = parser.recognize('SELECT ' + projection + ' FROM ledger.accounts AS a WHERE a.account_no=%s')
            self.assertEqual({p.column for p in plan.projections}, {'label','active','account_no','balance'})
        self.assertEqual(parser.recognize('SELECT * FROM ledger.accounts WHERE (account_no=(%s))').bind((3,))[0][1], 3)

    def test_named_original_lexical_parameter_order_and_repeated_bind(self):
        parser = ConfiguredSQLParserV2(SQLCaptureConfigV2(layouts()[0]))
        plan = parser.recognize('UPDATE ledger.accounts SET label=%(Name)s,balance=%(same)s WHERE account_no=%(same)s')
        params = {'same': 12, 'Name': '100% raw %(same)s'}
        self.assertEqual([(r.value,v) for r,v in plan.bind(params)], [('Name',params['Name']),('same',12),('same',12)])
        self.assertEqual(params, {'same':12,'Name':'100% raw %(same)s'})
        self.assertEqual([r.value for r in plan.parameters], ['Name','same','same'])
        with self.assertRaises(RecognitionError): plan.bind({'same':12,'name':'lowercase'})

    def test_write_returning_is_only_projection_and_no_execution_surface(self):
        parser = ConfiguredSQLParserV2(SQLCaptureConfigV2(layouts()[0]))
        sql = 'DELETE /* untouched %s comment */ FROM ledger.accounts WHERE account_no=7 RETURNING *'
        plan = parser.recognize(sql)
        self.assertEqual(plan.original_sql, sql)
        self.assertEqual(plan.bind(), ())
        self.assertFalse(plan.to_dict()['returningIsPredicateRead'])
        with self.assertRaises(RecognitionError): plan.bind(())
        for name in ['execute','fetchone','fetchall','install','ddl','source_facts','model_coverage']:
            self.assertFalse(hasattr(parser, name))

    def test_nonnull_exact_parameter_types_and_no_argument_mutation_on_failure(self):
        for table in layouts():
            parser = ConfiguredSQLParserV2(SQLCaptureConfigV2(table))
            plan = parser.recognize(read_sql(table))
            invalid = [None, True, 1.5, b'bad', object()]
            invalid += [2**63, -2**63-1] if table.key.type == 'int64' else ['\ud800','x\x00y']
            if table.key.type == 'uuid': invalid += ['not-uuid', '{00000000-0000-0000-0000-000000000001}', 'urn:uuid:00000000-0000-0000-0000-000000000001']
            for raw in invalid:
                args = [raw]
                with self.subTest(table=table.table, raw=repr(raw)), self.assertRaises(RecognitionError): plan.bind(args)
                self.assertIs(args[0], raw)
            with self.assertRaises(RecognitionError): plan.bind(iter(values(table)))
            with self.assertRaises(RecognitionError): plan.bind(())
        parser = ConfiguredSQLParserV2(SQLCaptureConfigV2(layouts()[0], max_text_bytes=4))
        update = parser.recognize('UPDATE ledger.accounts SET label=%s,active=%s WHERE account_no=%s')
        update.bind(('text', True, 0))
        for args in [('too long',True,0), ('x',1,0), ('x',None,0)]:
            with self.subTest(args=args), self.assertRaises(RecognitionError): update.bind(args)

    def test_int64_literals_remain_lossless_and_text_identity_is_case_sensitive(self):
        parser = ConfiguredSQLParserV2(SQLCaptureConfigV2(layouts()[0]))
        for n in [-(2**63), 2**63-1]:
            plan = parser.recognize('SELECT * FROM ledger.accounts WHERE account_no=' + str(n))
            self.assertEqual(plan.key_reference.to_dict()['value'], str(n))
        table = layouts()[1]
        plan = ConfiguredSQLParserV2(SQLCaptureConfigV2(table)).recognize(read_sql(table))
        self.assertNotEqual(plan.bind(('AbC',)), plan.bind(('abc',)))

    def test_cache_limits_and_distinct_config_contexts(self):
        table = layouts()[0]
        parser = ConfiguredSQLParserV2(SQLCaptureConfigV2(table), cache_entries=2, cache_bytes=15000)
        for n in range(10): parser.recognize('SELECT * FROM ledger.accounts WHERE account_no=' + str(n))
        self.assertLessEqual(parser.cache_info().entries, 2)
        self.assertLessEqual(parser.cache_info().bytes, 15000)
        plan = parser.recognize(read_sql(table))
        plan.bind((987654321,))
        self.assertNotIn('987654321', json.dumps(plan.to_dict()))
        self.assertIs(parser.recognize(read_sql(table)), plan)
        self.assertGreater(parser.cache_info().hits, 0)
        disabled = ConfiguredSQLParserV2(SQLCaptureConfigV2(table), cache_bytes=0)
        disabled.recognize(read_sql(table)); self.assertEqual(disabled.cache_info().entries, 0)
        other = ConfiguredSQLParserV2(replace(parser.config, max_text_bytes=42)).recognize(read_sql(table))
        self.assertNotEqual(plan.config_sha256, other.config_sha256)

    def test_resource_checks_and_dependency_failures_are_explicit(self):
        table = layouts()[0]
        for options, sql in [({'max_sql_bytes':10},read_sql(table)), ({'max_tokens':5},read_sql(table)),
                             ({'max_ast_nodes':5},read_sql(table)), ({'max_nesting':2},'SELECT * FROM ledger.accounts WHERE (((account_no=%s)))')]:
            with self.subTest(options=options), self.assertRaises(RecognitionError):
                ConfiguredSQLParserV2(SQLCaptureConfigV2(table, **options)).recognize(sql)
        parser = ConfiguredSQLParserV2(SQLCaptureConfigV2(table))
        for sql in ['', 'SELECT \ud800', b'SELECT *', 'SELECT \x00']:
            with self.subTest(sql=repr(sql)), self.assertRaises(RecognitionError): parser.recognize(sql)
        with mock.patch.dict(sys.modules, {'sqlglot': None}):
            with self.assertRaises(OptionalParserUnavailable): parser.recognize(read_sql(table))
        with mock.patch('moontxnwitness_capture.configured_sql.importlib.metadata.version', return_value='99'):
            with self.assertRaises(OptionalParserUnavailable): parser.recognize(read_sql(table))

    def test_cold_import_without_optional_dependency_driver_or_orm(self):
        root = str(Path(__file__).resolve().parents[1])
        script = '''import sys
sys.path.insert(0,sys.argv[1])
from moontxnwitness_capture.configured_sql_v2 import *
assert not any(n == 'sqlglot' or n.startswith('sqlglot.') or n == 'psycopg' or n.startswith('psycopg.') or n == 'sqlalchemy' or n.startswith('sqlalchemy.') for n in sys.modules)
p=ConfiguredSQLParserV2(SQLCaptureConfigV2(TableConfigV2('s','t',PrimaryKeyConfigV2('k','uuid'),(ColumnConfig('v','int64'),))))
try: p.recognize('SELECT * FROM s.t WHERE k=%s::UUID')
except OptionalParserUnavailable: pass
else: raise AssertionError('missing optional parser did not refuse')
'''
        result = subprocess.run([sys.executable,'-I','-S','-B','-c',script,root], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)


_REJECTED = {
    'partial_select':'SELECT account_no FROM ledger.accounts WHERE account_no=%s',
    'no_key':'SELECT * FROM ledger.accounts',
    'extra_business_predicate':'SELECT * FROM ledger.accounts WHERE account_no=%s AND active=%s',
    'extra_key_predicate':'SELECT * FROM ledger.accounts WHERE account_no=%s AND account_no=%s',
    'non_key_equality':'SELECT * FROM ledger.accounts WHERE balance=%s',
    'range_key':'SELECT * FROM ledger.accounts WHERE account_no>%s',
    'or':'SELECT * FROM ledger.accounts WHERE account_no=%s OR account_no=%s',
    'in':'SELECT * FROM ledger.accounts WHERE account_no IN (%s)',
    'null':'SELECT * FROM ledger.accounts WHERE account_no=NULL',
    'is_null':'SELECT * FROM ledger.accounts WHERE label IS NULL',
    'join':'SELECT a.* FROM ledger.accounts a JOIN ledger.accounts b ON a.account_no=b.account_no WHERE a.account_no=%s',
    'comma_join':'SELECT * FROM ledger.accounts,ledger.accounts WHERE account_no=%s',
    'function':'SELECT lower(label),account_no,balance,active FROM ledger.accounts WHERE account_no=%s',
    'aggregate':'SELECT count(*) FROM ledger.accounts WHERE account_no=%s',
    'where_function':'SELECT * FROM ledger.accounts WHERE abs(account_no)=%s',
    'subquery':'SELECT * FROM ledger.accounts WHERE account_no=(SELECT 1)',
    'cte':'WITH x AS (SELECT * FROM ledger.accounts) SELECT * FROM x WHERE account_no=%s',
    'union':'SELECT * FROM ledger.accounts WHERE account_no=%s UNION SELECT * FROM ledger.accounts WHERE account_no=%s',
    'duplicate_projection':'SELECT account_no,balance,active,label,label FROM ledger.accounts WHERE account_no=%s',
    'duplicate_output':'SELECT account_no AS a,balance AS a,active,label FROM ledger.accounts WHERE account_no=%s',
    'limit':'SELECT * FROM ledger.accounts WHERE account_no=%s LIMIT 1',
    'order':'SELECT * FROM ledger.accounts WHERE account_no=%s ORDER BY label',
    'lock':'SELECT * FROM ledger.accounts WHERE account_no=%s FOR UPDATE',
    'unknown_column':'SELECT missing FROM ledger.accounts WHERE account_no=%s',
    'unknown_table':'SELECT * FROM ledger.other WHERE account_no=%s',
    'missing_schema':'SELECT * FROM accounts WHERE account_no=%s',
    'pk_mutation':'UPDATE ledger.accounts SET account_no=%s WHERE account_no=%s',
    'literal_assignment':'UPDATE ledger.accounts SET balance=1 WHERE account_no=%s',
    'arithmetic_assignment':'UPDATE ledger.accounts SET balance=balance+%s WHERE account_no=%s',
    'null_assignment':'UPDATE ledger.accounts SET label=NULL WHERE account_no=%s',
    'duplicate_assignment':'UPDATE ledger.accounts SET balance=%s,balance=%s WHERE account_no=%s',
    'no_update_key':'UPDATE ledger.accounts SET balance=%s',
    'no_delete_key':'DELETE FROM ledger.accounts',
    'delete_extra_predicate':'DELETE FROM ledger.accounts WHERE account_no=%s AND active=%s',
    'update_from':'UPDATE ledger.accounts SET balance=%s FROM ledger.other WHERE account_no=%s',
    'delete_using':'DELETE FROM ledger.accounts USING ledger.other WHERE account_no=%s',
    'multirow':'INSERT INTO ledger.accounts(account_no,balance,active,label) VALUES(%s,%s,%s,%s),(%s,%s,%s,%s)',
    'partial_insert':'INSERT INTO ledger.accounts(account_no,balance) VALUES(%s,%s)',
    'implicit_insert':'INSERT INTO ledger.accounts VALUES(%s,%s,%s,%s)',
    'missing_insert_key':'INSERT INTO ledger.accounts(balance,active,label) VALUES(%s,%s,%s)',
    'literal_insert':'INSERT INTO ledger.accounts(account_no,balance,active,label) VALUES(1,%s,%s,%s)',
    'insert_null':'INSERT INTO ledger.accounts(account_no,balance,active,label) VALUES(%s,%s,%s,NULL)',
    'upsert':'INSERT INTO ledger.accounts(account_no,balance,active,label) VALUES(%s,%s,%s,%s) ON CONFLICT(account_no) DO NOTHING',
    'default_insert':'INSERT INTO ledger.accounts DEFAULT VALUES',
    'returning_function':'DELETE FROM ledger.accounts WHERE account_no=%s RETURNING now()',
    'wrong_cast':'SELECT * FROM ledger.accounts WHERE account_no=%s::UUID',
    'bigint_cast':'SELECT * FROM ledger.accounts WHERE account_no=%s::bigint',
    'cast_projection':'SELECT CAST(account_no AS UUID),balance,active,label FROM ledger.accounts WHERE account_no=%s',
    'mixed_parameters':'UPDATE ledger.accounts SET balance=%s WHERE account_no=%(id)s',
    'numbered_bind':'SELECT * FROM ledger.accounts WHERE account_no=$1',
    'colon_bind':'SELECT * FROM ledger.accounts WHERE account_no=:id',
    'binary_bind':'SELECT * FROM ledger.accounts WHERE account_no=%b',
    'percent_ambiguity':'SELECT /* 10% */ * FROM ledger.accounts WHERE account_no=%s',
    'multi_statement':'SELECT * FROM ledger.accounts WHERE account_no=%s; DELETE FROM ledger.accounts',
    'ddl':'CREATE TABLE ledger.accounts(id bigint)',
}


class RejectedPointV2Tests(unittest.TestCase):
    pass


def reject_case(sql):
    def test(self):
        parser = ConfiguredSQLParserV2(SQLCaptureConfigV2(layouts()[0]))
        with self.assertRaises(RecognitionError): parser.recognize(sql)
        self.assertEqual(parser.cache_info().entries, 0)
    return test


for _name, _sql in _REJECTED.items():
    setattr(RejectedPointV2Tests, 'test_' + _name, reject_case(_sql))


class RejectedUUIDV2Tests(unittest.TestCase):
    def test_only_direct_uuid_bind_cast_is_accepted(self):
        parser = ConfiguredSQLParserV2(SQLCaptureConfigV2(layouts()[2]))
        for sql in [
            "SELECT * FROM identity.members WHERE member_uuid='00000000-0000-0000-0000-000000000001'::UUID",
            'SELECT * FROM identity.members WHERE member_uuid=%s::text',
            'SELECT * FROM identity.members WHERE member_uuid=%s::UUID[]',
            'SELECT * FROM identity.members WHERE member_uuid=CAST(%s::text AS UUID)',
            'SELECT * FROM identity.members WHERE member_uuid=uuid_generate_v4()',
            'UPDATE identity.members SET email=%s::UUID WHERE member_uuid=%s::UUID',
        ]:
            with self.subTest(sql=sql), self.assertRaises(RecognitionError): parser.recognize(sql)
