"""Original cross-input producer CLI controls; no parser, SQL or Moon compiler."""
import argparse,ast,contextlib,io,subprocess,sys,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'scripts/configured-sql-cross-inputs.py'
def dependency_options(argv):
 tree=ast.parse(SCRIPT.read_text('utf8'));definitions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='dependency_options']
 assert len(definitions)==1
 scope={'argparse':argparse,'Path':Path,'__doc__':'Actual cross-input producer argument handling'}
 exec(compile(ast.Module(definitions,[]),str(SCRIPT)+'[actual-options-only]','exec'),scope)
 return scope['dependency_options'](argv)

class CrossInputCli(unittest.TestCase):
 def setUp(self):
  parent=ROOT/'artifacts/cross-cli-unit';parent.mkdir(parents=True,exist_ok=True);self.temp=tempfile.TemporaryDirectory(dir=parent);self.root=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def test_default_uses_standard_import_resolution_without_an_explicit_path(self):
  before=list(sys.path);self.assertIsNone(dependency_options([]));self.assertEqual(sys.path,before)
 def test_explicit_existing_dependency_root_is_preserved(self):
  self.assertEqual(dependency_options(['--dependency-root',str(self.root)]),self.root.resolve())
 def test_explicit_path_with_spaces_is_not_split_or_rewritten(self):
  path=self.root/'explicit dependency';path.mkdir();self.assertEqual(dependency_options(['--dependency-root',str(path)]),path.resolve())
 def test_missing_explicit_directory_cannot_silently_use_a_different_installation(self):
  with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as caught:dependency_options(['--dependency-root',str(self.root/'missing')])
  self.assertEqual(caught.exception.code,2)
 def test_missing_explicit_value_is_rejected(self):
  with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as caught:dependency_options(['--dependency-root'])
  self.assertEqual(caught.exception.code,2)
 def test_unknown_argument_is_rejected(self):
  with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as caught:dependency_options(['--execute-sql'])
  self.assertEqual(caught.exception.code,2)
 def test_actual_help_succeeds_without_any_optional_dependency(self):
  result=subprocess.run([sys.executable,'-I','-S','-B',str(SCRIPT),'--help'],cwd=ROOT,capture_output=True,timeout=10)
  self.assertEqual(result.returncode,0,result.stderr);self.assertIn(b'[--dependency-root DEPENDENCY_ROOT]',result.stdout)
 def test_actual_missing_explicit_path_fails_before_optional_parser_loading(self):
  result=subprocess.run([sys.executable,'-I','-S','-B',str(SCRIPT),'--dependency-root',str(self.root/'missing')],cwd=ROOT,capture_output=True,timeout=10)
  self.assertEqual(result.returncode,2);self.assertIn(b'Explicit optional dependency directory is missing',result.stderr);self.assertNotIn(b'Traceback',result.stderr)

if __name__=='__main__':unittest.main()
