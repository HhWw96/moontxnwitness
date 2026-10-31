"""Offline configured SQL candidate tests. No DB, driver, cursor or ORM is used."""
from __future__ import annotations
from dataclasses import FrozenInstanceError, replace
import json
import sys
import threading
import unittest
from unittest import mock

from .configured_sql import (ColumnConfig, TableConfig, SQLCaptureConfig,
    ConfiguredSQLParser, RecognitionError, OptionalParserUnavailable,
    TEXT_COMPARISON, PARSER_CONTRACT, PLAN_FORMAT)


def column(name, kind='text'):
    return ColumnConfig(name, kind, TEXT_COMPARISON if kind == 'text' else None)


def tables():
    return (
        TableConfig('ledger', 'accounts', 'account_no', (column('account_no', 'int64'), column('balance', 'int64'), column('active', 'bool'), column('label'))),
        TableConfig('app', 'flags', 'feature_key', (column('feature_key'), column('enabled', 'bool'))),
        TableConfig('App-X', 'Customer.Space', 'User ID', (column('User ID'), column('quota', 'int64'), column('live', 'bool'), column('zone'), column('score', 'int64'), column('note'))),
    )


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def target(table):
    return quote(table.schema) + '.' + quote(table.table)


class ConfigTests(unittest.TestCase):
    def test_configuration_and_nested_values_are_immutable(self):
        config = SQLCaptureConfig(tables())
        with self.assertRaises(FrozenInstanceError): config.default_schema = 'other'
        with self.assertRaises(FrozenInstanceError): config.tables[0].primary_key = 'label'
        with self.assertRaises(FrozenInstanceError): config.tables[0].columns[0].type = 'text'
        with self.assertRaises(ValueError): SQLCaptureConfig(list(tables()))
        with self.assertRaises(ValueError): TableConfig('s', 't', 'id', [column('id')])

    def test_config_roundtrip_and_detached_dictionary(self):
        config = SQLCaptureConfig(tables(), default_schema='app')
        self.assertEqual(SQLCaptureConfig.from_json(json.dumps(config.to_dict())), config)
        detached = config.to_dict();detached['tables'][0]['columns'].clear()
        self.assertEqual(len(config.tables[0].columns), 4)
        self.assertEqual(config.sha256, SQLCaptureConfig.from_json(json.dumps(config.to_dict())).sha256)

    def test_config_duplicate_escaped_keys_rejected(self):
        with self.assertRaises(ValueError): SQLCaptureConfig.from_json('{"format":"x","for\\u006dat":"x","tables":[]}')
        with self.assertRaises(ValueError): SQLCaptureConfig.from_json('{"format":"x","tables":NaN}')

    def test_unknown_fields_at_all_config_levels_rejected(self):
        base = SQLCaptureConfig(tables()).to_dict()
        for part in ('root', 'table', 'column', 'limits'):
            document = json.loads(json.dumps(base))
            obj = document if part == 'root' else document['tables'][0] if part == 'table' else document['tables'][0]['columns'][0] if part == 'column' else document['limits']
            obj['inferredComplete'] = True
            with self.subTest(part=part), self.assertRaises(ValueError): SQLCaptureConfig.from_json(json.dumps(document))

    def test_types_comparisons_and_primary_key_are_explicit(self):
        for args in [('name', 'text', None), ('name', 'uuid', None), ('name', 'text', 'locale-default'), ('name', 'bool', TEXT_COMPARISON)]:
            with self.subTest(args=args), self.assertRaises(ValueError): ColumnConfig(*args)
        with self.assertRaises(ValueError): TableConfig('s', 't', 'missing', (column('id'),))
        with self.assertRaises(ValueError): TableConfig('s', 't', 'id', (column('id'), column('id')))
        with self.assertRaises(ValueError): SQLCaptureConfig((tables()[0], tables()[0]))

    def test_identifier_unicode_bound_and_no_delimiter_key_collision(self):
        for value in ['', 'a\x00b', '\ud800', '界' * 22]:
            with self.subTest(value=repr(value)), self.assertRaises(ValueError): column(value)
        a = TableConfig('a.b', 'c', 'id', (column('id'),))
        b = TableConfig('a', 'b.c', 'id', (column('id'),))
        parser = ConfiguredSQLParser(SQLCaptureConfig((a,b)))
        self.assertEqual(parser.recognize('SELECT id FROM "a.b".c').table, a)
        self.assertEqual(parser.recognize('SELECT id FROM a."b.c"').table, b)

    def test_different_configs_have_different_fingerprints_and_cache_domains(self):
        base = SQLCaptureConfig(tables())
        changed = replace(base, default_schema='app')
        self.assertNotEqual(base.sha256, changed.sha256)
        self.assertNotEqual(base.sha256, replace(base, max_tokens=100).sha256)
        table = replace(tables()[0], model='point-register-v1')
        self.assertNotEqual(SQLCaptureConfig((table,)).sha256, SQLCaptureConfig((tables()[0],)).sha256)


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.config = SQLCaptureConfig(tables(), default_schema='ledger')
        self.parser = ConfiguredSQLParser(self.config)

    def test_three_different_structures_use_one_parser_for_all_four_operations(self):
        for table in tables():
            fields = ','.join(quote(c.name) for c in table.columns)
            pk = quote(table.primary_key)
            writable = table.columns[1]
            samples = [('SELECT ' + fields + ' FROM ' + target(table) + ' WHERE ' + pk + '=%s', 'select'),
                ('INSERT INTO ' + target(table) + '(' + fields + ') VALUES(' + ','.join('%s' for _ in table.columns) + ') RETURNING ' + fields, 'insert'),
                ('UPDATE ' + target(table) + ' SET ' + quote(writable.name) + '=%s WHERE ' + pk + '=%s RETURNING ' + pk, 'update'),
                ('DELETE FROM ' + target(table) + ' WHERE ' + pk + '=%s RETURNING ' + pk, 'delete')]
            for sql, operation in samples:
                with self.subTest(table=table.table, operation=operation):
                    plan = self.parser.recognize(sql)
                    self.assertEqual(plan.table, table);self.assertEqual(plan.operation, operation)
                    self.assertEqual(plan.original_sql, sql)
                    values = [('sample' if c.type == 'text' else True if c.type == 'bool' else 12) for c in table.columns]
                    bindings = values if operation == 'insert' else [values[1], values[0]] if operation == 'update' else [values[0]]
                    self.assertEqual(len(plan.bind(tuple(bindings))), len(bindings))

    def test_more_than_eight_different_keys_and_more_than_four_columns(self):
        sql = 'SELECT * FROM "App-X"."Customer.Space" WHERE "User ID"=%s'
        plan = self.parser.recognize(sql)
        self.assertEqual(len(plan.projections), 6)
        for key in range(100): self.assertEqual(plan.bind((str(key),))[0][1], str(key))
        self.assertEqual(self.parser.cache_info().entries, 1)

    def test_ranges_and_parenthesized_and_preserve_parameter_order(self):
        plan = self.parser.recognize('SELECT account_no,balance FROM ledger.accounts WHERE (balance >= %s AND (balance < %s AND active = %s)) ORDER BY account_no DESC')
        self.assertEqual([(p.column,p.operator) for p in plan.predicates], [('balance','ge'),('balance','lt'),('active','eq')])
        self.assertEqual([p.value.value for p in plan.predicates], [0,1,2])
        self.assertEqual([value for _,value in plan.bind((1,20,True))], [1,20,True])
        self.assertTrue(plan.ordering[0].descending)

    def test_positional_update_assignments_precede_where_parameters(self):
        plan = self.parser.recognize('UPDATE ledger.accounts SET balance=%s, active=%s WHERE account_no=%s RETURNING label,account_no')
        self.assertEqual([r.value for _,r in plan.assignments], [0,1]);self.assertEqual(plan.predicates[0].value.value,2)
        self.assertEqual([v for _,v in plan.bind((99,False,7))], [99,False,7])
        self.assertEqual([r.column for r in plan.returning], ['label','account_no'])
        self.assertFalse(plan.to_dict()['returningIsPredicateRead'])

    def test_named_parameters_are_case_sensitive_and_repeated_refs_allowed(self):
        plan = self.parser.recognize('SELECT account_no FROM ledger.accounts WHERE account_no=%(Who)s AND balance>=%(Who)s')
        self.assertEqual([r.value for r in plan.parameters], ['Who','Who'])
        self.assertEqual([v for _,v in plan.bind({'Who':3})], [3,3])
        for bad in ({'who':3},{'Who':3,'extra':4},None,(3,)):
            with self.subTest(value=bad), self.assertRaises(RecognitionError): plan.bind(bad)

    def test_literals_do_not_become_parameter_slots(self):
        plan = self.parser.recognize("SELECT account_no FROM ledger.accounts WHERE balance >= -9223372036854775808 AND active=true AND label='中''文'")
        self.assertEqual(plan.parameters,());self.assertEqual(plan.predicates[0].value.value,-(1<<63))
        self.assertEqual(plan.predicates[0].value.to_dict()['value'],str(-(1<<63)))
        self.assertEqual(plan.predicates[2].value.value,"中'文");self.assertEqual(plan.bind(),())

    def test_literal_percent_is_not_a_bind_when_no_parameter_argument_exists(self):
        plan = self.parser.recognize("SELECT feature_key FROM app.flags WHERE feature_key='literal%s'")
        self.assertEqual(plan.parameters,());self.assertEqual(plan.bind(),())
        with self.assertRaises(RecognitionError): plan.bind(())

    def test_multirow_insert_retains_row_and_bind_order(self):
        plan = self.parser.recognize('INSERT INTO app.flags(feature_key,enabled) VALUES(%s,%s),(%s,%s) RETURNING feature_key,enabled')
        self.assertEqual([[r.value for r in row] for row in plan.insert_rows], [[0,1],[2,3]])
        self.assertEqual([v for _,v in plan.bind(('a',True,'b',False))], ['a',True,'b',False])
        self.assertEqual(plan.predicates,())

    def test_aliases_case_folding_and_actual_column_identity(self):
        plan = self.parser.recognize('SELECT a.ACCOUNT_NO AS "Result ID",a.balance FROM LEDGER.ACCOUNTS AS a WHERE a.account_no=%s')
        self.assertEqual(plan.projections[0].output_name,'Result ID');self.assertEqual(plan.projections[0].column,'account_no')
        with self.assertRaises(RecognitionError): self.parser.recognize('SELECT accounts.account_no FROM ledger.accounts AS a')

    def test_quoted_embedded_quotes_and_unicode_identifiers(self):
        table = TableConfig('模式', 't"x', 'k|v', (column('k|v'),))
        parser = ConfiguredSQLParser(SQLCaptureConfig((table,)))
        plan = parser.recognize('SELECT "k|v" FROM "模式"."t""x" WHERE "k|v"=%s')
        self.assertEqual(plan.table,table);self.assertEqual(plan.bind(('🙂',))[0][1],'🙂')

    def test_configured_unqualified_schema_is_a_proof_requirement_not_search_path_fact(self):
        plan = self.parser.recognize('SELECT account_no FROM accounts')
        self.assertEqual(plan.schema_resolution,'configured-default-schema-requires-session-proof')
        parser = ConfiguredSQLParser(replace(self.config,default_schema=None))
        with self.assertRaises(RecognitionError): parser.recognize('SELECT account_no FROM accounts')

    def test_text_collation_is_explicit_and_requires_catalog_evidence(self):
        plan = self.parser.recognize('SELECT feature_key FROM app.flags WHERE feature_key COLLATE "C" >= %s')
        self.assertEqual(plan.predicates[0].collation,'C');self.assertIn('catalog-types-primary-key-and-text-collation',plan.to_dict()['requiredProofs'])

    def test_descriptors_and_plans_cannot_be_mutated_through_returned_json(self):
        plan = self.parser.recognize('SELECT * FROM app.flags')
        detached = plan.to_dict();detached['table']['columns'].clear();detached['projections'].clear()
        self.assertEqual(len(plan.projections),2)
        with self.assertRaises(FrozenInstanceError): plan.operation='insert'

    def test_no_implicit_history_or_server_validation_claim(self):
        plan = self.parser.recognize('DELETE FROM app.flags WHERE enabled=false RETURNING *')
        for field in ['databaseSyntaxValidated','sourceAuthenticated','captureFactsProduced','moonbitProjectionVerified','returningIsPredicateRead']:
            self.assertIs(plan.to_dict()[field],False)
        self.assertEqual(plan.to_dict()['parserContract'],PARSER_CONTRACT)
        self.assertEqual(plan.to_dict()['format'],PLAN_FORMAT)

    def test_parameter_types_are_exact_and_null_is_unsupported(self):
        plan = self.parser.recognize('UPDATE ledger.accounts SET active=%s,label=%s WHERE account_no=%s')
        for values in [(1,'x',1),(True,None,1),(True,'x',True),(True,'\x00',1),(True,'\ud800',1),(True,'x',1<<63)]:
            with self.subTest(values=repr(values)),self.assertRaises(RecognitionError):plan.bind(values)

    def test_materialized_parameters_only_no_generator_consumption(self):
        plan = self.parser.recognize('SELECT feature_key FROM app.flags WHERE feature_key=%s')
        consumed=[]
        def values():
            consumed.append(True);yield 'x'
        with self.assertRaises(RecognitionError):plan.bind(values())
        self.assertEqual(consumed,[])

    def test_no_parameter_or_result_data_retained_in_cache(self):
        sql='SELECT feature_key FROM app.flags WHERE feature_key=%s'
        first=self.parser.recognize(sql);first.bind(('secret-business-value',))
        second=self.parser.recognize(sql)
        self.assertIs(first,second);self.assertNotIn('secret-business-value',json.dumps(second.to_dict()))
        self.assertEqual(self.parser.cache_info().hits,1)


class BoundsAndCacheTests(unittest.TestCase):
    def setUp(self):
        self.config=SQLCaptureConfig(tables(),default_schema='ledger')

    def test_utf8_sql_bytes_apply_before_cache_lookup(self):
        parser=ConfiguredSQLParser(replace(self.config,max_sql_bytes=30))
        with self.assertRaises(RecognitionError):parser.recognize('SELECT account_no FROM ledger.accounts')
        with self.assertRaises(RecognitionError):parser.recognize('界'*11)
        self.assertEqual(parser.cache_info().misses,0)

    def test_token_ast_nesting_and_predicate_budgets(self):
        for kwargs,sql in [({'max_tokens':2},'SELECT account_no FROM ledger.accounts'),
                ({'max_ast_nodes':2},'SELECT account_no FROM ledger.accounts'),
                ({'max_nesting':2},'SELECT account_no FROM ledger.accounts WHERE (((account_no=1)))'),
                ({'max_terms':1},'SELECT account_no FROM ledger.accounts WHERE account_no=1 AND active=true')]:
            with self.subTest(kwargs=kwargs),self.assertRaises(RecognitionError):ConfiguredSQLParser(replace(self.config,**kwargs)).recognize(sql)

    def test_insert_row_text_and_arity_budgets(self):
        parser=ConfiguredSQLParser(replace(self.config,max_insert_rows=1,max_text_bytes=3))
        with self.assertRaises(RecognitionError):parser.recognize("INSERT INTO app.flags(feature_key,enabled) VALUES('a',true),('b',false)")
        with self.assertRaises(RecognitionError):parser.recognize("SELECT feature_key FROM app.flags WHERE feature_key='界界'")
        plan=parser.recognize('SELECT feature_key FROM app.flags WHERE feature_key=%s')
        with self.assertRaises(RecognitionError):plan.bind(('界界',))
        with self.assertRaises(RecognitionError):plan.bind(('a','b'))

    def test_count_lru_and_byte_budget_are_bounded(self):
        parser=ConfiguredSQLParser(self.config,cache_entries=2,cache_bytes=20000)
        for number in range(10):parser.recognize('SELECT account_no FROM ledger.accounts WHERE account_no='+str(number))
        self.assertEqual(parser.cache_info().entries,2);self.assertLessEqual(parser.cache_info().bytes,20000)
        parser.recognize('SELECT account_no FROM ledger.accounts WHERE account_no=9')
        self.assertEqual(parser.cache_info().hits,1)
        for kwargs in ({'cache_entries':0},{'cache_bytes':1}):
            cold=ConfiguredSQLParser(self.config,**kwargs);cold.recognize('SELECT account_no FROM ledger.accounts')
            self.assertEqual(cold.cache_info().entries,0)

    def test_cache_context_is_local_and_immutable(self):
        first=ConfiguredSQLParser(self.config)
        second=ConfiguredSQLParser(replace(self.config,default_schema='app'))
        self.assertEqual(first.recognize('SELECT account_no FROM accounts').table.schema,'ledger')
        with self.assertRaises(RecognitionError):second.recognize('SELECT account_no FROM accounts')
        with self.assertRaises(AttributeError):first.config=second.config

    def test_cache_thread_safety_keeps_immutable_plans_and_limits(self):
        parser=ConfiguredSQLParser(self.config,cache_entries=4,cache_bytes=30000);failures=[]
        def work(number):
            try:
                plan=parser.recognize('SELECT account_no FROM ledger.accounts WHERE account_no='+str(number%8))
                self.assertEqual(plan.table,tables()[0])
            except Exception as error:failures.append(error)
        workers=[threading.Thread(target=work,args=(n,)) for n in range(24)]
        for thread in workers:thread.start()
        for thread in workers:thread.join()
        self.assertEqual(failures,[]);self.assertLessEqual(parser.cache_info().entries,4);self.assertLessEqual(parser.cache_info().bytes,30000)

    def test_missing_optional_dependency_and_wrong_version_are_explicit(self):
        parser=ConfiguredSQLParser(self.config)
        with mock.patch.dict(sys.modules,{'sqlglot':None}):
            with self.assertRaises(OptionalParserUnavailable):parser.recognize('SELECT account_no FROM ledger.accounts')
        with mock.patch('moontxnwitness_capture.configured_sql.importlib.metadata.version',return_value='0.0.0'):
            with self.assertRaises(OptionalParserUnavailable):parser.recognize('SELECT account_no FROM ledger.accounts')

    def test_no_rewrite_api_or_cursor_execution_surface_exists(self):
        parser=ConfiguredSQLParser(self.config)
        for name in ['execute','fetchone','fetchall','install','initialize','ddl']:
            self.assertFalse(hasattr(parser,name))
        raw='SELECT /* original */ account_no FROM ledger.accounts WHERE account_no=%s;'
        plan=parser.recognize(raw);self.assertEqual(plan.original_sql,raw)
        self.assertFalse(hasattr(plan,'executed_sql'))

    def test_original_fixed_profiles_keep_their_old_behavior(self):
        from .profiles.model_sql import ModelScope
        from .orm import FIELDS
        self.assertEqual(ModelScope('scope','relation-set-v1',(1,)).target,'"scope"."business"')
        with self.assertRaises(ValueError):ModelScope('scope','relation-set-v1',tuple(range(9)))
        self.assertEqual(FIELDS,('id','email','hashed_password','is_active','is_superuser','is_verified'))


_REJECTED_SQL = {
 'join':'SELECT a.account_no FROM ledger.accounts a JOIN app.flags f ON a.label=f.feature_key',
 'comma_join':'SELECT account_no FROM ledger.accounts,app.flags',
 'aggregate':'SELECT count(*) FROM ledger.accounts',
 'scalar_function':'SELECT lower(label) FROM ledger.accounts',
 'where_function':'SELECT account_no FROM ledger.accounts WHERE lower(label)=%s',
 'null_literal':'SELECT account_no FROM ledger.accounts WHERE label=NULL',
 'is_null':'SELECT account_no FROM ledger.accounts WHERE label IS NULL',
 'subquery':'SELECT account_no FROM ledger.accounts WHERE account_no=(SELECT account_no FROM ledger.accounts)',
 'insert_select':'INSERT INTO ledger.accounts(account_no,balance) SELECT account_no,balance FROM ledger.accounts',
 'cte':'WITH a AS (SELECT account_no FROM ledger.accounts) SELECT account_no FROM a',
 'union':'SELECT account_no FROM ledger.accounts UNION SELECT account_no FROM ledger.accounts',
 'or':'SELECT account_no FROM ledger.accounts WHERE account_no=1 OR active=true',
 'between':'SELECT account_no FROM ledger.accounts WHERE account_no BETWEEN 1 AND 3',
 'in':'SELECT account_no FROM ledger.accounts WHERE account_no IN (1,2)',
 'not_equal':'SELECT account_no FROM ledger.accounts WHERE account_no<>1',
 'bool_range':'SELECT account_no FROM ledger.accounts WHERE active>false',
 'column_comparison':'SELECT account_no FROM ledger.accounts WHERE account_no=balance',
 'unknown_column':'SELECT unknown FROM ledger.accounts',
 'unknown_table':'SELECT id FROM public.unknown',
 'catalog_qualified':'SELECT account_no FROM database.ledger.accounts',
 'foreign_column_qualifier':'SELECT other.account_no FROM ledger.accounts',
 'alias_hidden_table':'SELECT accounts.account_no FROM ledger.accounts AS a',
 'limit':'SELECT account_no FROM ledger.accounts LIMIT 1',
 'offset':'SELECT account_no FROM ledger.accounts OFFSET 1',
 'for_update':'SELECT account_no FROM ledger.accounts FOR UPDATE',
 'distinct':'SELECT DISTINCT account_no FROM ledger.accounts',
 'group_by':'SELECT account_no FROM ledger.accounts GROUP BY account_no',
 'window':'SELECT row_number() OVER () FROM ledger.accounts',
 'primary_key_mutation':'UPDATE ledger.accounts SET account_no=%s WHERE account_no=%s',
 'arithmetic_assignment':'UPDATE ledger.accounts SET balance=balance+1 WHERE account_no=%s',
 'duplicate_assignment':'UPDATE ledger.accounts SET balance=1,balance=2 WHERE account_no=1',
 'update_from':'UPDATE ledger.accounts SET balance=1 FROM app.flags WHERE account_no=1',
 'delete_using':'DELETE FROM ledger.accounts USING app.flags WHERE account_no=1',
 'returning_function':'DELETE FROM ledger.accounts WHERE account_no=1 RETURNING now()',
 'upsert':'INSERT INTO app.flags(feature_key,enabled) VALUES(%s,%s) ON CONFLICT(feature_key) DO UPDATE SET enabled=true',
 'insert_missing_pk':'INSERT INTO ledger.accounts(balance) VALUES(1)',
 'insert_duplicate_columns':'INSERT INTO app.flags(feature_key,feature_key) VALUES(\'a\',\'b\')',
 'insert_arity':'INSERT INTO app.flags(feature_key,enabled) VALUES(\'a\')',
 'default_values':'INSERT INTO app.flags DEFAULT VALUES',
 'float_literal':'SELECT account_no FROM ledger.accounts WHERE balance=1.5',
 'int_overflow':'SELECT account_no FROM ledger.accounts WHERE balance=9223372036854775808',
 'cast':'SELECT account_no FROM ledger.accounts WHERE account_no=%s::bigint',
 'numbered_parameter':'SELECT account_no FROM ledger.accounts WHERE account_no=$1',
 'binary_parameter':'SELECT account_no FROM ledger.accounts WHERE account_no=%b',
 'named_binary_parameter':'SELECT account_no FROM ledger.accounts WHERE account_no=%(x)b',
 'mixed_parameters':'SELECT account_no FROM ledger.accounts WHERE account_no=%s AND balance=%(balance)s',
 'percent_inside_literal_with_other_bind':"SELECT account_no FROM ledger.accounts WHERE label='literal%s' AND account_no=%s",
 'percent_escape_with_other_bind':"SELECT account_no FROM ledger.accounts WHERE label='literal%%' AND account_no=%s",
 'wrong_collation':'SELECT feature_key FROM app.flags WHERE feature_key COLLATE "en_US">%s',
 'multi_statement':'SELECT account_no FROM ledger.accounts; DELETE FROM ledger.accounts',
 'ddl':'CREATE TABLE ledger.new(id bigint)',
 'empty':'',
 'malformed':'SELECT ( FROM ledger.accounts',
}


class UnsupportedSQLTests(unittest.TestCase):
    pass


def _reject_case(sql):
    def test(self):
        parser=ConfiguredSQLParser(SQLCaptureConfig(tables(),default_schema='ledger'))
        with self.assertRaises(RecognitionError):parser.recognize(sql)
    return test


for _name,_sql in _REJECTED_SQL.items():
    setattr(UnsupportedSQLTests,'test_reject_'+_name,_reject_case(_sql))
