import ast,copy,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];tree=ast.parse((ROOT/'scripts/release.py').read_bytes());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='validate_native038_receipts');env={};exec(compile(ast.Module([node],[]),'release[native-contract]','exec'),env);validate=env['validate_native038_receipts']
class NativeContract(unittest.TestCase):
 def setUp(self):
  rows=[{'name':'case-'+str(i),'passed':True}for i in range(39)]
  current={'passed':True,'tests':39,'coreSha256':'core','sdkSha256':'sdk','formalPerformanceMeasurement':False,'results':rows}
  self.summary={'foundation038':current,'buildManifest':{'coreSha256':'core'},'testedFileSha256':{'dist/sdk.mjs':'sdk'}}
  actual={**current,'runtimeUnchanged':True,'textAPIUnchanged':True};self.package={'native038Consumers':{k:copy.deepcopy(actual)for k in ['source','portable']},'checks':[k+' native full-report SDK original 39 boundary and feature-fallback checks'for k in ['source','portable']]}
 def test_actual_full_contract_and_previous_version_fallback(self):validate(self.summary,self.package,'0.3.8');validate({}, {}, '0.3.7')
 def test_missing_compiled_feature_consumption(self):
  del self.package['native038Consumers']['portable']
  with self.assertRaises(KeyError):validate(self.summary,self.package,'0.3.8')
 def test_previous_runtime_cannot_stand_for_current(self):
  self.package['native038Consumers']['source']['coreSha256']='old'
  with self.assertRaises(AssertionError):validate(self.summary,self.package,'0.3.8')
 def test_one_omitted_original_check_is_rejected(self):
  self.package['native038Consumers']['source']['results'].pop()
  with self.assertRaises(AssertionError):validate(self.summary,self.package,'0.3.8')
 def test_local_functional_cannot_claim_formal_measurement(self):
  self.summary['foundation038']['formalPerformanceMeasurement']=True
  with self.assertRaises(AssertionError):validate(self.summary,self.package,'0.3.8')
if __name__=='__main__':unittest.main()
