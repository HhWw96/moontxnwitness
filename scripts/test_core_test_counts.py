"""Pure release-summary count guards; no compilation or database execution."""
import ast,copy,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
source=ast.parse((ROOT/'scripts/release.py').read_bytes())
node=next(n for n in source.body if isinstance(n,ast.FunctionDef)and n.name=='validate_core_test_counts')
env={'ROOT':ROOT};exec(compile(ast.Module([node],[]),'release.py[core-count-contract-only]','exec'),env)
validate=env['validate_core_test_counts']
class SummaryCounts(unittest.TestCase):
 def setUp(self):
  # Test summary consistency without freezing the repository's growing test count.
  # The release guard reads this conditional-test inventory independently.
  self.common=100
  self.js_only=sum(line.startswith('test "') for line in (ROOT/'src/native_report_js_wbtest.mbt').read_text('utf8').splitlines())
  self.js=self.common+self.js_only
  self.valid={'executedTargets':['js','wasm-gc','wasm'],'coreTestsPerTarget':self.common,'coreTestCountsByTarget':{'js':self.js,'wasm-gc':self.common,'wasm':self.common}}
 def test_valid_and_native_target(self):
  self.assertEqual(validate(self.valid),self.js)
  self.valid['executedTargets'].append('native');self.valid['coreTestCountsByTarget']['native']=self.common;self.assertEqual(validate(self.valid),self.js)
 def test_historical_fallback(self):self.assertEqual(validate({'coreTestsPerTarget':977}),977)
 def test_tamper_wrong_js(self):
  self.valid['coreTestCountsByTarget']['js']=self.common
  with self.assertRaises(AssertionError):validate(self.valid)
 def test_tamper_missing_target(self):
  del self.valid['coreTestCountsByTarget']['wasm']
  with self.assertRaises(AssertionError):validate(self.valid)
 def test_tamper_wrong_other_target(self):
  self.valid['coreTestCountsByTarget']['wasm']=self.common+1
  with self.assertRaises(AssertionError):validate(self.valid)
 def test_tamper_wrong_common(self):
  self.valid['coreTestsPerTarget']=self.js
  with self.assertRaises(AssertionError):validate(self.valid)
if __name__=='__main__':unittest.main()
