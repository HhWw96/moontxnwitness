"""Verify archived data by default; optional offline rerun uses recorded public-package members."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parent
SHA=lambda b:hashlib.sha256(b).hexdigest()
def load(p):return json.loads(Path(p).read_bytes())
def verify(external):
 raw=(ROOT/'public-closure.json').read_bytes();assert SHA(raw)==external;m=json.loads(raw)
 for row in m['files']:
  p=(ROOT/row['file']).resolve();assert p.is_relative_to(ROOT);b=p.read_bytes();assert len(b)==row['bytes'] and SHA(b)==row['sha256'],row['file']
 top=load(ROOT/'evidence/published-package-210-receipt.json');assert SHA((ROOT/'evidence/published-package-210-receipt.json').read_bytes())=='7369dcc8441b33b8439c8d9c2ed6eb3b848793c66f5964fa38209640dbdd4a51'
 assert top['passed'] and top['checkCount']==210 and top['runtimeConsumersExecuted']==2 and top['allSixOriginalArchivesAndSelectedMembersUnchangedAfterConsumers']
 assert top['sourceRebuilt'] is False and top['newCoreBuild'] is False and top['actualDatabaseExecution'] is False and top['formalPerformanceMeasurement'] is False and top['authorDistRead'] is False
 lock=load(ROOT/'tools/v2/dependency-lock.json');assert len(top['consumers'])==2 and {x['variant'] for x in top['consumers']}=={'source','portable'}
 for c in top['consumers']:
  f=ROOT/'evidence/consumers'/c['variant']/'sdk105-receipt.json';b=f.read_bytes();r=json.loads(b);assert SHA(b)==c['semanticReceipt']['sha256'];assert r['passed'] and r['checkCount']==105 and r['failedCount']==0 and [x['name'] for x in r['checks']]==lock['expectedCheckNames'] and all(x['passed'] for x in r['checks'])
  assert r['version']=='0.2.0' and r['sourceSha256']=='d3adf5c906b27f2414344acef8be963f2bccb07310cebe487c9ddd14135b4b57' and r['coreSha256']=='2a6d2055a0127a0dab486389bbe169b97fc9ba50de2722400c521a1ffc915681' and r['captureCoreSha256']=='60da31aafe9d8fb034289d6deb132c36eb61cb021bf3bc0668401e27987bf5ee'
 assert len([x for x in top['downloads'] if x['url'].endswith('.zip')])==6 and all(x['passed'] and x['anonymousRequest'] and not x['authorizationHeaderUsed'] and not x['cookieJarUsed'] for x in top['downloads'])
 origins=load(ROOT/'downloaded-member-origins.json');assert origins['selectedMembers']==len(origins['members'])==269
 for row in origins['members']:
  b=(ROOT/row['publicFile']).read_bytes();assert SHA(b)==row['sha256'] and len(b)==row['bytes']
 for binding in top['releaseBindings']:
  v=binding['version'];pub=load(ROOT/'proof/releases'/v/'publication.json');pkg=load(ROOT/'proof/releases'/v/'publisher-package.json');assert pub['passed'] and pkg['passed'] and pub['version']==pkg['version']==v
  expected={x['name']:(x['sha256'],x['bytes']) for x in pub['github']['assets']};assert expected=={x['file']:(x['sha256'],x['bytes']) for x in pkg['archives']}
  assert pub['github']['ci']['headSha']==binding['tagCommit'] and load(ROOT/'proof/releases'/v/'tag-ref.json')['object']['sha']==binding['tagCommit']
  for kind,ext in binding['archives'].items():
   name='MoonTxnWitness-v'+v+'-'+kind+'.zip';assert ext['archiveSha256']==expected[name][0]
   records=[x for x in top['downloads'] if x['url'].endswith('/'+name)];assert len(records)==1 and (records[0]['sha256'],records[0]['bytes'])==expected[name]
 first=load(ROOT/'evidence/first-v1-tool-failure/receipt.json');assert first['passed'] is False and first['checkCount']==0 and first['runtimeExecutionAttempted'] is False
 before=(ROOT/'tools/v1/run-public-package-review.py').read_text(encoding='utf-8');after=(ROOT/'tools/v2/run-public-package-review.py').read_text(encoding='utf-8');assert before.count('expected[k]=')==1 and after==before.replace('expected[k]=','expected[kind]=')
 assert SHA((ROOT/'reference-review/review/run-tests.mjs').read_bytes())==lock['frozen105WorkerSha256'] and SHA((ROOT/'reference-review/review/execution-checks.mjs').read_bytes())==lock['frozenExecutionModuleSha256']
 return {'passed':True,'files':len(m['files']),'recordedGroups':210,'firstHarnessFailureRetained':True,'anonymousArchives':6,'selectedMembers':269,'SDKImportedHere':False,'networkExecutedHere':False}
def offline(parent,node):
 assert Path(parent).resolve().drive.lower()=='d:';work=Path(tempfile.mkdtemp(prefix='published020-offline-reproduction-',dir=parent));ref=ROOT/'reference-review';pm=load(ref/'review/preparation-manifest.json');results=[]
 env=dict(os.environ)
 for k in list(env):
  if k.upper() in ('NODE_OPTIONS','NODE_PATH','PYTHONOPTIMIZE','PYTHONPATH','PYTHONHOME','PYTHONSTARTUP'):env.pop(k)
 for kind in ('source','portable'):
  out=work/kind;out.mkdir();test=out/'review';test.mkdir()
  for row in pm['files']:
   src=ref/'review'/row['file'];dest=test/row['file'];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(src.read_bytes())
  (test/'preparation-manifest.json').write_bytes((ref/'review/preparation-manifest.json').read_bytes());source=ROOT/'downloaded-components/0.2.0/source';runtime=ROOT/'downloaded-components/0.2.0/portable/dist'
  if kind=='source':
   assembled=out/'runtime';assembled.mkdir()
   for r in load(ROOT/'tools/v2/dependency-lock.json')['versions']['0.2.0']['runtime']['files']:
    src=source/'cmd'/r['file'] if r['file'] in ('sdk.mjs','evidence.mjs') else runtime/r['file'];(assembled/r['file']).write_bytes(src.read_bytes())
   runtime=assembled
  f=load(ref/'public-root-freeze.json');f['source']['root']=str(source);f['runtime']['root']=str(runtime);f['baseline']={'sourceRoot':str(ROOT/'downloaded-components/0.1.7/source'),'runtimeRoot':str(ROOT/'downloaded-components/0.1.7/portable/dist')};f['additionalBaseline18']={'sourceRoot':str(ROOT/'downloaded-components/0.1.8/source'),'runtimeRoot':str(ROOT/'downloaded-components/0.1.8/portable/dist'),'sourceFingerprint':'81b2211dc07b4af3826fb13d5c20c3659010080e0d6c3d340c7df5925796fcc4'};f['nodeExecutable']=str(Path(node).resolve());launch=out/'offline-freeze.private.json';launch.write_text(json.dumps(f,indent=2)+'\n',encoding='utf-8')
  child=subprocess.run([sys.executable,'-B',str(test/'run-review.py'),'--freeze',str(launch),'--freeze-sha256',SHA(launch.read_bytes()),'--preparation-sha256',SHA((test/'preparation-manifest.json').read_bytes())],env=env,cwd=out,capture_output=True);(out/'stdout.private.log').write_bytes(child.stdout);(out/'stderr.private.log').write_bytes(child.stderr);assert child.returncode==0
  rs=list((test/'runs').glob('*/receipt.json'));assert len(rs)==1;r=load(rs[0]);assert r['passed'] and r['checkCount']==105 and r['failedCount']==0;results.append({'variant':kind,'passed':True,'checkCount':105,'receiptSha256':SHA(rs[0].read_bytes())})
 return {'passed':True,'recordedMembersOfflineRerun':True,'checkCount':210,'anonymousDownloadsExecutedHere':False,'sourceRebuilt':False,'newCoreBuild':False,'actualDatabaseExecution':False,'formalPerformanceMeasurement':False,'consumers':results,'output':str(work)}
def main():
 if not __debug__:raise RuntimeError('Unoptimized Python required')
 p=argparse.ArgumentParser();p.add_argument('--manifest-sha256',required=True);p.add_argument('--run-sdk',action='store_true');p.add_argument('--output-parent');p.add_argument('--node');a=p.parse_args();result=verify(a.manifest_sha256)
 if a.run_sdk:
  assert a.output_parent and a.node;result=offline(a.output_parent,a.node)
 print(json.dumps(result))
if __name__=='__main__':main()
