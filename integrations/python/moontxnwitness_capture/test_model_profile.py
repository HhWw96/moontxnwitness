"""Light protocol/plan tests; never labeled real database validation."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from moontxnwitness_capture.profiles.model_sql import ModelScope,plans,ddl,control_sql,validate_parameters
from moontxnwitness_capture.profiles.model_profile import ModelResultView,ModelCursor


class ModelPlanTests(unittest.TestCase):
    def setUp(self):
        self.l=ModelScope('unit_list','append-list-v1',('x','y'))
        self.r=ModelScope('unit_rows','relation-set-v1',(1,2,3),((('active','eq'),('balance','ge')),))
    def test_scope_immutable(self):
        with self.assertRaises(AttributeError):self.l.model='relation-set-v1'
    def test_bad_identifiers(self):
        for name in ('x;DROP SCHEMA z','UPPER','a'*41,'"x"'):
            with self.subTest(name=name),self.assertRaises(ValueError):ModelScope(name,'append-list-v1',('x',))
    def test_list_single_append_only(self):
        p=plans(self.l)[1]
        for items in ([],[{'id':'a','value':'v'},{'id':'b','value':'v'}],[{'id':'a','value':'v','unknown':1}]):
            with self.subTest(items=items),self.assertRaises(ValueError):validate_parameters(self.l,p,(json.dumps(items),'x'))
    def test_duplicate_values_distinct_identity(self):
        p=plans(self.l)[1]
        for identity in ('one','two'):
            self.assertEqual(validate_parameters(self.l,p,(json.dumps([{'id':identity,'value':'same'}]),'x'))[1],'x')
    def test_list_value_is_string(self):
        for value in (None,True,1,{},[]):
            with self.subTest(value=value),self.assertRaises(ValueError):validate_parameters(self.l,plans(self.l)[1],(json.dumps([{'id':'a','value':value}]),'x'))
    def test_list_absent_key_not_registered(self):
        with self.assertRaises(ValueError):validate_parameters(self.l,plans(self.l)[0],('outside',))
    def test_relation_full_int64(self):
        scope=ModelScope('extreme','relation-set-v1',(-(1<<63),(1<<63)-1))
        self.assertEqual(validate_parameters(scope,plans(scope)[1],(-(1<<63),(1<<63)-1,False,'😀'))[0],-(1<<63))
    def test_bool_not_int64(self):
        with self.assertRaises(ValueError):ModelScope('bad','relation-set-v1',(True,))
    def test_integer_overflow(self):
        with self.assertRaises(ValueError):validate_parameters(self.r,plans(self.r)[0],(1<<63,))
    def test_null_unsupported(self):
        with self.assertRaises(ValueError):validate_parameters(self.r,plans(self.r)[1],(1,1,True,None))
    def test_invalid_text_unsupported(self):
        for text in ('\x00','\ud800','a'*1025):
            with self.subTest(text=repr(text)),self.assertRaises(ValueError):validate_parameters(self.r,plans(self.r)[1],(1,1,True,text))
    def test_predicate_arity_and_type(self):
        predicate=plans(self.r)[-1]
        self.assertEqual(validate_parameters(self.r,predicate,(True,-9)),(True,-9))
        for params in ((True,),('true',1),(True,False)):
            with self.subTest(params=params),self.assertRaises(ValueError):validate_parameters(self.r,predicate,params)
    def test_bool_range_not_registered(self):
        with self.assertRaises(ValueError):ModelScope('bad','relation-set-v1',(1,),((('active','gt'),),))
    def test_point_writes_only(self):
        statements=plans(self.r)
        self.assertTrue(all('WHERE id=%s' in p.sql for p in statements if p.operation in ('row-update','row-delete')))
        self.assertTrue(all('LIMIT' not in p.sql for p in statements if p.operation=='row-read'))
    def test_write_result_is_not_predicate(self):
        self.assertTrue(all(not p.predicate for p in plans(self.r) if p.operation!='row-read'))
    def test_same_statement_metadata(self):
        for p in plans(self.r):
            self.assertIn('version',p.executed_sql)
            self.assertNotIn(';',p.executed_sql)
    def test_business_sql_unchanged_catalog(self):
        for p in plans(self.r):self.assertNotIn('version',p.sql)
        self.assertEqual(plans(self.l)[0].sql,plans(self.l)[0].executed_sql)
    def test_ddl_owned_and_before_seed_triggers(self):
        for scope in (self.l,self.r):
            statements=ddl(scope)
            self.assertTrue(statements[0].startswith('CREATE SCHEMA '))
            self.assertTrue(all(s.startswith('CREATE TRIGGER ') for s in statements[-2:]))
            self.assertNotIn('SECURITY DEFINER','\n'.join(statements))
            self.assertIn('SET search_path=pg_catalog','\n'.join(statements))
    def test_whole_source_lock(self):
        self.assertIn('"identities"',control_sql(self.l)['lock'])
        self.assertIn('"candidates"',control_sql(self.r)['lock'])
        self.assertTrue(control_sql(self.r)['lock'].endswith('IN ACCESS EXCLUSIVE MODE'))
    def test_no_semantic_fields_in_producer(self):
        source=(Path(__file__).parent/'profiles/model_profile.py').read_text(encoding='utf8')
        self.assertNotIn("emit('row_read'",source)
        self.assertNotIn("emit('row_write'",source)
        self.assertNotIn("emit('list_read'",source)
        self.assertNotIn("emit('append'",source)
    def test_hidden_native_fields_stay_outside_business_result(self):
        class Actual:
            nfields=6;ntuples=1;command_status=b'UPDATE 1'
            def get_value(self,row,column):return [b'3',b'9',b't',b'west',b'unique-version',b'old-version'][column]
            def ftype(self,column):return [20,20,16,25,2950,2950][column]
        original=Actual();view=ModelResultView(original,4)
        self.assertEqual(view.nfields,4);self.assertEqual(original.nfields,6)
        self.assertEqual(view.get_value(0,3),b'west');self.assertEqual(view.ftype(0),20)
        self.assertEqual(view.command_status,b'UPDATE 1')
        for column in (-1,4,5):
            with self.subTest(column=column),self.assertRaises(IndexError):view.get_value(0,column)
    def test_cursor_connection_preserves_observed_factory_path(self):
        cursor=object.__new__(ModelCursor);connection=object()
        cursor._connection=connection
        self.assertIs(cursor.connection,connection)


if __name__=='__main__':unittest.main(verbosity=2)
