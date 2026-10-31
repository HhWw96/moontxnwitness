"""Pure release-summary count guards; no compilation or database execution."""
import ast,copy,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
source=ast.parse((ROOT/'scripts/release.py').read_bytes())
node=next(n for n in source.body if isinstance(n,ast.FunctionDef)and n.name=='validate_core_test_counts')
env={'ROOT':ROOT};exec(compile(ast.Module([node],[]),'release.py[core-count-contract-only]','exec'),env)
validate=env['validate_core_test_counts']
class SummaryCounts(unittest.TestCase):
 def setUp(self):self.valid={'executedTargets':['js','wasm-gc','wasm'],'coreTestsPerTarget':1841,'coreTestCountsByTarget':{'js':1853,'wasm-gc':1841,'wasm':1841}}
 def test_valid_and_native_target(self):
  self.assertEqual(validate(self.valid),1853)
  self.valid['executedTargets'].append('native');self.valid['coreTestCountsByTarget']['native']=1841;self.assertEqual(validate(self.valid),1853)
 def test_historical_fallback(self):self.assertEqual(validate({'coreTestsPerTarget':977}),977)
 def test_tamper_wrong_js(self):
  self.valid['coreTestCountsByTarget']['js']=1841
  with self.assertRaises(AssertionError):validate(self.valid)
 def test_tamper_missing_target(self):
  del self.valid['coreTestCountsByTarget']['wasm']
  with self.assertRaises(AssertionError):validate(self.valid)
 def test_tamper_wrong_other_target(self):
  self.valid['coreTestCountsByTarget']['wasm']=1842
  with self.assertRaises(AssertionError):validate(self.valid)
 def test_tamper_wrong_common(self):
  self.valid['coreTestsPerTarget']=1853
  with self.assertRaises(AssertionError):validate(self.valid)
if __name__=='__main__':unittest.main()
