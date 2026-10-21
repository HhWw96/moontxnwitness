"""Bind the original restore helper too, then freeze this review's own files."""
from pathlib import Path
import ast,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SOURCE='e63df4b815f130674bc0f10939d8513e534679a8'
HELPER='verification/experimental-candidates/plain-journal-r2-2026-10-21/restore_and_run.py'
RUNNER='scripts/experimental_plain_epoch_r2_ci.py'
def bind(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def git_blob(path):
    raw=subprocess.check_output(['git','-c','core.longpaths=true','ls-tree',SOURCE,'--',path],cwd=ROOT)
    meta,name=raw.rstrip(b'\n').split(b'\t');mode,kind,oid=meta.split()
    assert mode==b'100644' and kind==b'blob' and name.decode()==path
    value=subprocess.check_output(['git','cat-file','blob',oid.decode()],cwd=ROOT)
    return oid.decode(),value
helper_oid,helper=git_blob(HELPER);runner_oid,runner=git_blob(RUNNER)
tree=ast.parse(runner.decode())
expected=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign)
              and any(isinstance(t,ast.Name) and t.id=='EXPECTED_RESTORE' for t in node.targets))
assert expected==bind(helper)['sha256']=='999a594b22dca95f1ee6ea6a854e065b12609ccd566a83db9fd26450f0f5c408'
assert b"if binding(old)['sha256'] != EXPECTED_RESTORE:" in runner
assert b'spec.loader.exec_module(helper)' in runner
assert b"if stage.get('exitCode') != 0:" in runner
receipt=json.loads((HERE/'receipt-first.json').read_text())
assert receipt['passed'] is True and receipt['checkCount']==2760 and receipt['failedChecks']==0
supplement={'schema':1,'passed':True,'kind':'additional-immutable-helper-binding','sourceCommit':SOURCE,
            'helper':{'path':HELPER,'gitBlob':helper_oid,**bind(helper)},
            'runner':{'path':RUNNER,'gitBlob':runner_oid,**bind(runner)},
            'actualHelperReadDirectlyFromRunnerFileSystem':False,
            'executionLink':'Immutable runner requires exact original helper hash before import; original retained execution stages completed with exit0.',
            'newCandidateExecuted':False,'newTestsExecuted':False,'newDatabaseExecuted':False}
with (HERE/'supplemental-helper-binding.json').open('x',encoding='utf8') as stream:json.dump(supplement,stream,indent=2);stream.write('\n')
files={p.name:bind(p.read_bytes()) for p in sorted(HERE.iterdir()) if p.is_file()}
value={'schema':1,'kind':'immutable-independent-R2-limited-audit-index','passed':True,'primaryReceipt':'receipt-first.json',
       'primaryChecks':2760,'failedChecks':0,'zipMembers':791,'primaryImmutableGitBlobs':84,'supplementalImmutableHelperBlobs':1,
       'jobCompletionMetadataVerified':False,'overallWorkflowAcceptance':False,'releaseAcceptance':False,
       'files':files,'notes':['Public run endpointsuccess and public job endpointsin_progress/null are retained without substitution.',
                             'Source/test/raw-observation obligations passed; no candidate imports or executions in this independent audit.',
                             'No source closure, general SQL proof, per-record fsync/crash durability, formal performance, stable release or human/organizer acceptance.']}
with (HERE/'audit-index.json').open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')
print(json.dumps({'passed':True,'primaryChecks':2760,'auditIndex':bind((HERE/'audit-index.json').read_bytes()),'primaryReceipt':bind((HERE/'receipt-first.json').read_bytes()),
                  'auditTool':bind((HERE/'audit-first.py').read_bytes()),'overallJobCompletionMetadataVerified':False}))
