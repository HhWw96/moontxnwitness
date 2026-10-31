"""Receipt faults only; these fixtures are not actual runtime execution."""
import copy
import unittest
from shared_core_contract import SYMBOLS,validate_shared039_receipt

class SharedContract(unittest.TestCase):
    def setUp(self):
        self.manifest={'version':'0.3.9','coreSha256':'main','captureCoreSha256':'capture','configuredCoreSha256':{
            'configured-session-core.mjs':'session','source-components-core.mjs':'source',
            'sql-projection-core.mjs':'sql','sql-fetch-core.mjs':'fetch'}}
        self.value={'format':'shared-core-runtime-conformance/v1','passed':True,'checks':11,'failed':0,
            'results':[{'name':'case-'+str(i),'passed':True} for i in range(11)],'version':'0.3.9',
            'defaultSDKStaticModules':41,'defaultSDKCompiledCores':['core.mjs','capture-core.mjs'],
            'roleHashes':{'core.mjs':'main','capture-core.mjs':'capture',**self.manifest['configuredCoreSha256']},
            'sdkSha256':'sdk','runtimeBeforeAfterUnchanged':True,'primitiveCalls':dict.fromkeys(SYMBOLS,1),
            'actualDatabaseExecution':False,'formalPerformanceMeasurement':False,'sourceFactsProduced':False,'writerWindowVerified':False}
    def test_exact_receipt_contract(self):validate_shared039_receipt(self.value,self.manifest,'sdk')
    def test_prior_default_closure_cannot_stand_for_shared(self):
        for patch in [{'defaultSDKStaticModules':44},{'defaultSDKCompiledCores':['core.mjs','capture-core.mjs','configured-session-core.mjs']}]:
            with self.subTest(patch=patch),self.assertRaises(AssertionError):validate_shared039_receipt({**self.value,**patch},self.manifest,'sdk')
    def test_changed_main_or_standalone_runtime_is_rejected(self):
        for name in self.value['roleHashes']:
            value=copy.deepcopy(self.value);value['roleHashes'][name]='other'
            with self.subTest(name=name),self.assertRaises(AssertionError):validate_shared039_receipt(value,self.manifest,'sdk')
    def test_omitted_primitive_and_false_call_count_are_rejected(self):
        for bad in [0,True]:
            value=copy.deepcopy(self.value);value['primitiveCalls'][next(iter(SYMBOLS))]=bad
            with self.assertRaises(AssertionError):validate_shared039_receipt(value,self.manifest,'sdk')
        value=copy.deepcopy(self.value);value['primitiveCalls'].pop(next(iter(SYMBOLS)))
        with self.assertRaises(AssertionError):validate_shared039_receipt(value,self.manifest,'sdk')
    def test_missing_case_and_duplicate_name_are_rejected(self):
        for change in [lambda v:v['results'].pop(),lambda v:v['results'][1].update(name='case-0')]:
            value=copy.deepcopy(self.value);change(value)
            with self.assertRaises(AssertionError):validate_shared039_receipt(value,self.manifest,'sdk')
    def test_no_performance_database_or_source_authority_is_inferred(self):
        for name in ['actualDatabaseExecution','formalPerformanceMeasurement','sourceFactsProduced','writerWindowVerified']:
            with self.subTest(name=name),self.assertRaises(AssertionError):validate_shared039_receipt({**self.value,name:True},self.manifest,'sdk')
    def test_changed_sdk_or_version_and_false_zero_are_rejected(self):
        for patch in [{'sdkSha256':'old'},{'version':'0.3.8'},{'failed':False},{'runtimeBeforeAfterUnchanged':False}]:
            with self.subTest(patch=patch),self.assertRaises(AssertionError):validate_shared039_receipt({**self.value,**patch},self.manifest,'sdk')

if __name__=='__main__':unittest.main(verbosity=2)
