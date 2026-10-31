"""Execute only the real package consumer's receipt-selection statements."""
import ast, copy, hashlib, json, tempfile, unittest
from pathlib import Path
from test_postgres_ci_import import encode

ROOT = Path(__file__).resolve().parents[1]
def selector():
    prepared = ROOT/'prepared/scripts/package_release.py'
    source = prepared if prepared.is_file() else ROOT/'scripts/package_release.py'
    parsed = ast.parse(source.read_text('utf8'))
    for node in ast.walk(parsed):
        for key in ('body','orelse'):
            body = getattr(node,key,None)
            if not isinstance(body,list): continue
            for i,statement in enumerate(body):
                if isinstance(statement,ast.Assign) and any(isinstance(x,ast.Name) and x.id == 'release_directory' for x in statement.targets):
                    selected = body[i:i+5]
                    assert len(selected) == 5 and isinstance(selected[-1],ast.If)
                    return compile(ast.fix_missing_locations(ast.Module(body=selected,type_ignores=[])),'actual-package-receipt-selection','exec')
    raise AssertionError('Actual CI reproduction fallback is missing')

class SelectionBoundaries(unittest.TestCase):
    def setUp(self):
        parent=ROOT/'artifacts/selection-unit';parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.root=Path(self.temp.name)
        self.release=self.root/'verification/releases/0.3.4';self.release.mkdir(parents=True)
        self.db={'phase':'exact-run-ci-reproduction','version':'0.3.4','passed':True,'actualDatabaseExecution':True,'releaseReady':False}
        self.repro={'format':'moontxnwitness-ci-reproduction/v1','version':'0.3.4','releaseReady':False,'databaseEvidence':'database-ci.json'}
        self.save()
    def tearDown(self):self.temp.cleanup()
    def save(self):
        raw=encode(self.db);(self.release/'database-ci.json').write_bytes(raw)
        self.repro['databaseEvidenceSha256']=hashlib.sha256(raw).hexdigest();(self.release/'reproduction.json').write_bytes(encode(self.repro))
    def run_selection(self):
        scope={'consumer':self.root,'VERSION':'0.3.4','json':json,
            'sha256':lambda path:hashlib.sha256(path.read_bytes()).hexdigest(),
            'load_receipt':lambda path:json.loads(path.read_text('utf8'))}
        exec(selector(),scope);return scope['database']
    def test_reproduction_only_selects_true_ci_and_keeps_release_ready_false(self):
        self.assertEqual(self.run_selection(),self.db)
    def test_existing_final_acceptance_uses_its_original_database_path(self):
        actual={'originalFinalGate':'unchanged'};(self.release/'final.json').write_bytes(encode(actual));(self.release/'acceptance.json').write_bytes(encode({'databaseEvidence':'final.json'}))
        self.assertEqual(self.run_selection(),actual)
    def test_reproduction_cannot_upgrade_release_ready(self):
        self.repro['releaseReady']=True;self.save()
        with self.assertRaises(AssertionError):self.run_selection()
    def test_reproduction_format_and_version_cannot_be_forged(self):
        original=copy.deepcopy(self.repro)
        for field,value in [('format','acceptance/v1'),('version','0.3.5')]:
            self.repro={**original,field:value};self.save()
            with self.assertRaises(AssertionError):self.run_selection()
    def test_reproduction_database_path_cannot_escape_or_select_other_receipt(self):
        for value in ['../../other.json','final.json']:
            self.repro['databaseEvidence']=value;self.save()
            with self.assertRaises(AssertionError):self.run_selection()
    def test_reproduction_database_digest_is_required(self):
        (self.release/'database-ci.json').write_bytes(b'{}')
        with self.assertRaises(AssertionError):self.run_selection()
    def test_database_failure_or_release_claim_is_not_promoted(self):
        original=copy.deepcopy(self.db)
        for field,value in [('passed',False),('actualDatabaseExecution',False),('releaseReady',True),('version','0.3.5'),('phase','final-release')]:
            self.db={**original,field:value};self.save()
            with self.assertRaises(AssertionError):self.run_selection()
    def test_missing_reproduction_does_not_synthesize_acceptance(self):
        (self.release/'reproduction.json').unlink()
        with self.assertRaises(FileNotFoundError):self.run_selection()
        self.assertFalse((self.release/'acceptance.json').exists())

if __name__=='__main__':unittest.main()
