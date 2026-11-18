"""Pure construction/descriptor regression; no database or SQL execution."""
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import subprocess
import sys
import unittest
import uuid

from .configured_sql import ColumnConfig, RecognitionError, TEXT_COMPARISON
from .configured_sql_v2 import ConfiguredSQLParserV2, SQLCaptureConfigV2, TableConfigV2, PrimaryKeyConfigV2
from .configured_point_projection_v2 import (
    PointProjectionOptionsV2, _build_captured_projection, build_point_projection, verify_point_projection,
)


def column(name, kind):
    return ColumnConfig(name, kind, TEXT_COMPARISON if kind == 'text' else None)


def layouts():
    return (
        TableConfigV2('ledger', 'accounts', PrimaryKeyConfigV2('account_no', 'int64'),
                      (column('balance', 'int64'), column('active', 'bool'), column('label', 'text'))),
        TableConfigV2('应用-甲', '顾客.资料', PrimaryKeyConfigV2('User "ID', 'text', TEXT_COMPARISON),
                      (column('名 字', 'text'), column('可用', 'bool'), column('额度', 'int64'), column('备注', 'text'))),
        TableConfigV2('identity', 'members', PrimaryKeyConfigV2('member_uuid', 'uuid'),
                      (column('email', 'text'), column('is_active', 'bool'))),
    )


def q(name):
    return '"' + name.replace('"', '""') + '"'


def target(table):
    return q(table.schema) + '.' + q(table.table)


def setup(table=None):
    config = SQLCaptureConfigV2(table or layouts()[0])
    return ConfiguredSQLParserV2(config), PointProjectionOptionsV2(config,
        star_contract='preinstallation-business-schema/v1',
        business_star_columns=tuple(c.name for c in config.table.columns))


def row(table):
    return tuple(uuid.UUID(int=17) if c.type == 'uuid' else 17 if c.type == 'int64'
                 else True if c.type == 'bool' else '原样🙂 %(same)s 100% \\ \'文本' for c in table.columns)


class PointProjectionTests(unittest.TestCase):
    def test_capture_cache_reuses_shape_and_validates_every_parameter_set(self):
        parser, options = setup()
        select = 'SELECT a.* FROM ledger.accounts AS a WHERE account_no=%s'
        update = 'UPDATE ledger.accounts SET label=%(label)s::VARCHAR WHERE account_no=%(key)s RETURNING label'
        for sql, param_sets in [(select, [[7], [9]]),
                                (update, [{'label': '首个🙂 ', 'key': 7}, {'label': '改动', 'key': 9}])]:
            for params in param_sets:
                fresh = ConfiguredSQLParserV2(options.config, cache_entries=0)
                expected = build_point_projection(fresh.recognize(sql), params, options)
                actual = _build_captured_projection(parser, sql, params, options)
                self.assertEqual(actual, expected)
        self.assertEqual(parser.cache_info().misses, 2)
        self.assertEqual(parser.cache_info().hits, 2)
        with self.assertRaises(RecognitionError):
            _build_captured_projection(parser, update, {'label': False, 'key': 9}, options)
        with self.assertRaises(RecognitionError):
            _build_captured_projection(parser, select, [7], PointProjectionOptionsV2(options.config))

    def test_three_layouts_and_all_four_operations_have_explicit_image_maps(self):
        for table in layouts():
            parser, options = setup(table)
            values = row(table)
            key = q(table.primary_key)
            cols = ','.join(q(c.name) for c in table.columns)
            cases = [
                ('select', 'SELECT * FROM ' + target(table) + ' WHERE ' + key + '=%s', [values[0]], ['read']),
                ('insert', 'INSERT INTO ' + target(table) + '(' + cols + ') VALUES(' + ','.join('%s' for _ in values) + ')', list(values), ['new']),
                ('update', 'UPDATE ' + target(table) + ' SET ' + q(table.business_columns[0].name) + '=%s WHERE ' + key + '=%s', [values[1], values[0]], ['old', 'new']),
                ('delete', 'DELETE FROM ' + target(table) + ' WHERE ' + key + '=%s', [values[0]], ['old']),
            ]
            for operation, sql, params, images in cases:
                with self.subTest(table=table.table, operation=operation):
                    before = params.copy()
                    projected = build_point_projection(parser.recognize(sql), params, options)
                    descriptor = projected.to_dict()
                    self.assertEqual(params, before)
                    self.assertEqual(projected.parameters, tuple(before))
                    self.assertTrue(all(a is b for a, b in zip(params, before)))
                    self.assertEqual(descriptor['originalSql'], sql)
                    self.assertEqual([h['image'] for h in descriptor['hiddenResults']], images)
                    self.assertTrue(all(h['version']['type'] == 'int64' for h in descriptor['hiddenResults']))
                    self.assertEqual(descriptor['businessResult']['mode'], 'rows' if operation == 'select' else 'no-result')
                    self.assertEqual(verify_point_projection(descriptor, parser.recognize(sql), params, options)['valid'], True)
                    if operation != 'select':
                        self.assertIn('RETURNING WITH (OLD AS ', projected.sql)
                        self.assertTrue(all(h['role'] == 'write-effect-observation-only' for h in descriptor['hiddenResults']))
                        self.assertFalse(descriptor['businessResult']['nativeResultDirectlyDeliverable'])

    def test_update_old_and_new_images_reference_separate_private_aliases(self):
        parser, options = setup()
        plan = parser.recognize('UPDATE ledger.accounts SET balance=%s WHERE account_no=%s RETURNING label AS title,balance AS amount')
        result = build_point_projection(plan, (5, 7), options)
        d = result.to_dict(); aliases = d['returningAliases']
        self.assertNotEqual(aliases['old'], aliases['new'])
        self.assertIn(') ' + q(aliases['new']) + '."label" AS "title", ' + q(aliases['new']) + '."balance" AS "amount", ', result.sql)
        self.assertEqual([p['outputName'] for p in d['businessResult']['columns']], ['title','amount'])
        self.assertEqual(d['businessResult']['rowImage'], 'new')
        for hidden in d['hiddenResults']:
            for field in hidden['columns'] + [hidden['version']]:
                self.assertGreaterEqual(field['nativeIndex'], 2)
                self.assertIn(q(aliases[hidden['image']]) + '.' + q(field['column']) + ' AS ' + q(field['outputName']), result.sql)
        self.assertEqual(d['hiddenResults'][1]['columns'][0]['nativeIndex'], 7)
        self.assertEqual(d['nativeColumnCount'], 12)

    def test_insert_and_delete_business_returning_uses_correct_row_image(self):
        parser, options = setup()
        samples = [
            ('INSERT INTO ledger.accounts(account_no,balance,active,label) VALUES(%s,%s,%s,%s) RETURNING *', (7,8,True,'x'), 'new'),
            ('DELETE FROM ledger.accounts WHERE account_no=%s RETURNING account_no AS removed', (7,), 'old'),
        ]
        for sql, params, image in samples:
            d = build_point_projection(parser.recognize(sql), params, options).to_dict()
            self.assertEqual(d['businessResult']['rowImage'], image)
            self.assertEqual(d['businessResult']['mode'], 'rows')
            self.assertFalse(d['producesDeletionVersion'])
            self.assertFalse(d['returningIsPredicateRead'])
            self.assertFalse(d['writeImagesAreSelectFacts'])

    def test_select_star_expands_configured_columns_and_retains_business_alias_order(self):
        parser, options = setup()
        for projection, names in [('a.*',['account_no','balance','active','label']),
                ('a.label AS title,a.active AS enabled,a.account_no AS pk,a.balance AS amount',['title','enabled','pk','amount'])]:
            plan = parser.recognize('SELECT ' + projection + ' FROM ledger.accounts AS a WHERE a.account_no=%s')
            result = build_point_projection(plan, [7], options);d = result.to_dict()
            self.assertEqual([p['outputName'] for p in d['businessResult']['columns']], names)
            self.assertNotIn('*', result.sql)
            self.assertNotIn('RETURNING', result.sql)
            self.assertEqual(d['hiddenResults'][0]['version']['nativeIndex'], 4)
            self.assertEqual([x['nativeIndex'] for x in d['hiddenResults'][0]['columns']],
                             [names.index('pk') if 'pk' in names else 0,3,1,0] if 'pk' in names else [0,1,2,3])
            self.assertEqual(d['zeroRowsPolicy'], 'diagnostic-only-no-absence-source')

    def test_repeated_named_parameters_become_occurrence_order_without_changing_raw_values(self):
        parser, options = setup()
        plan = parser.recognize('UPDATE ledger.accounts SET label=%(Name)s,balance=%(same)s WHERE account_no=%(same)s')
        raw = {'same': 12, 'Name': '100% raw %(same)s'}
        result = build_point_projection(plan, raw, options)
        self.assertEqual(raw, {'same':12, 'Name':'100% raw %(same)s'})
        self.assertEqual(result.parameters, (raw['Name'],12,12))
        self.assertEqual([x['original']['name'] for x in result.to_dict()['parameterMap']], ['Name','same','same'])
        self.assertEqual([x['name'] for x in result.to_dict()['originalParameters']['items']], ['same','Name'])

    def test_positional_order_and_literals_map_without_interpolation(self):
        parser, options = setup()
        plan = parser.recognize('UPDATE ledger.accounts SET label=%s,balance=%s WHERE account_no=9223372036854775807')
        args = ['"quoted"; DROP TABLE ledger.accounts; -- %s', -2**63]
        result = build_point_projection(plan, args, options)
        self.assertEqual(result.parameters, (args[0],-2**63,2**63-1))
        self.assertNotIn('DROP', result.sql)
        self.assertEqual([x['original']['kind'] for x in result.to_dict()['parameterMap']], ['positional','positional','literal'])
        self.assertEqual(result.to_dict()['parameterMap'][2]['value']['decimal'], str(2**63-1))

    def test_uuid_key_cast_preserves_object_or_original_text_spelling(self):
        parser, options = setup(layouts()[2]);value = uuid.UUID('A8098C1A-F86E-11DA-BD1A-00112444BE1E')
        for form in ['%s','%s::UUID','CAST(%s AS UUID)']:
            for raw in [value,str(value).upper(),str(value).replace('-','').upper()]:
                with self.subTest(form=form, raw=raw):
                    args = [raw];plan = parser.recognize('SELECT * FROM identity.members WHERE member_uuid=' + form)
                    result = build_point_projection(plan, args, options)
                    self.assertIs(result.parameters[0], raw)
                    self.assertIn('= CAST(%s AS UUID)', result.sql)
                    d = result.to_dict()
                    self.assertEqual(d['originalParameters']['items'][0]['value'], str(value) if type(raw) is uuid.UUID else raw)
                    self.assertEqual(d['hiddenResults'][0]['version']['type'], 'int64')

    def test_generated_aliases_do_not_collide_with_business_names(self):
        table = TableConfigV2('s','__mtw_v2_old',PrimaryKeyConfigV2('k','int64'),
                             (column('__mtw_v2_new','int64'),column('__mtw_v2_old_0','int64')))
        parser, options = setup(table)
        sql = 'UPDATE s.__mtw_v2_old SET __mtw_v2_new=%s WHERE k=%s RETURNING k AS __mtw_v2_old_version'
        result = build_point_projection(parser.recognize(sql),(1,2),options);d = result.to_dict()
        self.assertNotIn(d['returningAliases']['old'], {table.table,*[c.name for c in table.columns]})
        self.assertNotIn(d['returningAliases']['new'], {table.table,*[c.name for c in table.columns]})
        hidden_names = [f['outputName'] for h in d['hiddenResults'] for f in h['columns']+[h['version']]]
        self.assertEqual(len(set(hidden_names)), len(hidden_names))
        self.assertNotIn('__mtw_v2_old_version', hidden_names)

    def test_percent_in_quoted_identifiers_is_escaped_for_new_driver_arguments(self):
        table = TableConfigV2('s%','t%s',PrimaryKeyConfigV2('k','int64'),(column('v','int64'),))
        parser, options = setup(table)
        sql = 'SELECT * FROM "s%"."t%s" WHERE k=7'
        result = build_point_projection(parser.recognize(sql),None,options)
        self.assertIn('FROM "s%%"."t%%s"', result.sql)
        self.assertEqual(result.parameters,(7,))
        self.assertEqual(result.to_dict()['originalSql'],sql)

    def test_descriptor_and_independent_policy_cannot_authorize_themselves(self):
        parser, options = setup();plan = parser.recognize('SELECT * FROM ledger.accounts WHERE account_no=%s')
        result = build_point_projection(plan,[7],options);d = result.to_dict()
        for field in ['sourceFactsProduced','captureFactsProduced','sourceAuthenticated','completeWindow','modelCoverageAccepted','moonbitProjectionVerified','databaseExecuted','databaseSyntaxValidated']:
            self.assertIs(d[field], False)
            altered = result.to_dict();altered[field] = True
            self.assertFalse(verify_point_projection(altered,plan,[7],options)['valid'])
        for key in ['projectedSql','parameterMap','hiddenResults','businessResult','independentOptions']:
            altered = result.to_dict();altered[key] = 'tampered'
            self.assertFalse(verify_point_projection(altered,plan,[7],options)['valid'])
        self.assertFalse(verify_point_projection(d,plan,[8],options)['valid'])
        self.assertFalse(verify_point_projection(d,plan,[7],replace(options,version_column='other_version'))['valid'])
        raw = result.descriptor_json[:-1] + ',"sourceFactsProduced":false}'
        self.assertFalse(verify_point_projection(raw,plan,[7],options)['valid'])
        with self.assertRaises(TypeError): PointProjectionOptionsV2(options.config,source_verified=True)

    def test_star_requires_explicit_unverified_preinstallation_business_view(self):
        parser, approved = setup()
        default = PointProjectionOptionsV2(approved.config)
        for sql, params in [('SELECT * FROM ledger.accounts WHERE account_no=%s',(7,)),
                ('DELETE FROM ledger.accounts WHERE account_no=%s RETURNING *',(7,)),
                ('SELECT a.* FROM ledger.accounts a WHERE a.account_no=%s',(7,))]:
            plan = parser.recognize(sql)
            with self.subTest(sql=sql), self.assertRaisesRegex(RecognitionError,'preinstallation'):
                build_point_projection(plan,params,default)
            result = build_point_projection(plan,params,approved);d = result.to_dict()
            self.assertEqual(d['businessStarView']['contract'],'preinstallation-business-schema/v1')
            self.assertEqual(d['businessStarView']['columns'],['account_no','balance','active','label'])
            self.assertFalse(d['businessStarView']['catalogVerified'])
            self.assertFalse(d['businessStarView']['installationVerified'])
            self.assertFalse(d['businessStarView']['equivalentToCurrentNativeStar'])
            self.assertNotIn(approved.version_column,[p['column'] for p in d['businessResult']['columns']])
            self.assertTrue(any('preinstallation-physical-columns-and-order' in x for x in d['requiredProofs']))
            altered = result.to_dict();altered['businessStarView']['installationVerified'] = True
            self.assertFalse(verify_point_projection(altered,plan,params,approved)['valid'])
        fields = approved.business_star_columns
        for columns in [fields[::-1],fields + (approved.version_column,),fields[:-1] + (approved.version_column,),list(fields),()]:
            with self.subTest(columns=columns), self.assertRaises(ValueError):
                replace(approved,business_star_columns=columns)
        with self.assertRaises(TypeError): PointProjectionOptionsV2(approved.config,installation_verified=True)
        with self.assertRaises(ValueError): replace(approved,star_contract='current-native-star')
        with self.assertRaises(ValueError): replace(approved,star_contract=None)
        direct = parser.recognize('SELECT label,active,account_no,balance FROM ledger.accounts WHERE account_no=%s')
        d = build_point_projection(direct,(7,),default).to_dict()
        self.assertIsNone(d['businessStarView'])

    def test_forged_candidate_unknown_sql_and_extra_conditions_cannot_bypass_recognition(self):
        parser, options = setup();plan = parser.recognize('SELECT * FROM ledger.accounts WHERE account_no=%s')
        for forged in [replace(plan,operation='delete'),replace(plan,predicates=()),replace(plan,config_sha256='0'*64),
                       replace(plan,original_sql='SELECT * FROM ledger.accounts WHERE account_no=%s AND active=true'),
                       replace(plan,original_sql='TRUNCATE ledger.accounts')]:
            with self.subTest(sql=forged.original_sql), self.assertRaises(RecognitionError):
                build_point_projection(forged,[7],options)
        with self.assertRaises(RecognitionError): build_point_projection(plan.to_dict(),[7],options)
        with self.assertRaises(RecognitionError): build_point_projection(plan,[7],options.to_dict())

    def test_options_resource_bounds_detached_results_and_failed_args_are_unchanged(self):
        parser, options = setup();plan = parser.recognize('SELECT * FROM ledger.accounts WHERE account_no=%s')
        for version in ['account_no','balance']:
            with self.assertRaises(ValueError): replace(options,version_column=version)
        for kind in ['uuid','text','bigint']:
            with self.assertRaises(ValueError): replace(options,version_type=kind)
        for opts in [replace(options,max_projected_sql_bytes=1),replace(options,max_descriptor_bytes=1)]:
            with self.assertRaises(RecognitionError): build_point_projection(plan,[7],opts)
        for args in [[True],['bad'],[None],[],[7,8],{'k':7}]:
            before = args.copy()
            with self.assertRaises(RecognitionError): build_point_projection(plan,args,options)
            self.assertEqual(args,before)
        result = build_point_projection(plan,[7],options);detached = result.to_dict();detached.clear()
        self.assertTrue(result.to_dict())
        with self.assertRaises(FrozenInstanceError): result.sql = 'modified'

    def test_import_does_not_require_optional_parser_driver_or_orm(self):
        package_root = str(Path(__file__).resolve().parents[1])
        script = '''import sys
sys.path.insert(0,sys.argv[1])
from moontxnwitness_capture.configured_point_projection_v2 import PointProjectionOptionsV2
assert not any(n == 'sqlglot' or n.startswith('sqlglot.') or n == 'psycopg' or n.startswith('psycopg.') or n == 'sqlalchemy' or n.startswith('sqlalchemy.') for n in sys.modules)
'''
        child = subprocess.run([sys.executable,'-I','-S','-B','-c',script,package_root],capture_output=True,text=True,timeout=20)
        self.assertEqual(child.returncode,0,child.stderr)


if __name__ == '__main__':
    unittest.main()
