"""Anonymous actual-public24 producer, with retained first failures. No compiler/DB."""
import datetime,hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE='d583cb4f3cb1c4da4cc63e2ce255cc8834b08e2a'
OUT=ROOT/'artifacts/public024-compat';OUT.mkdir(parents=True,exist_ok=False)
(OUT/'downloads').mkdir()
receipt={'schema':1,'kind':'actual-public024-anonymous-producer-ci','expectedSourceCommit':SOURCE,
 'producerWorkflowCommit':os.environ.get('GITHUB_SHA'),'startedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'actualDatabaseExecution':False,'compilerExecuted':False,'authorDistRead':False,
 'authorizationHeaderSentForPublicDownloads':False,'cookieHeaderSentForPublicDownloads':False,
 'passed':False,'stages':[]}
sha=lambda raw:hashlib.sha256(raw).hexdigest()
def stage(name,command,seconds):
 try:
  result=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=seconds)
 except subprocess.TimeoutExpired as error:
  stdout=error.stdout or b'';stderr=error.stderr or b''
  (OUT/(name+'.stdout.log')).write_bytes(stdout);(OUT/(name+'.stderr.log')).write_bytes(stderr)
  receipt['stages'].append({'name':name,'exitCode':None,'timedOut':True,'timeoutSeconds':seconds,'stdoutSha256':sha(stdout),'stderrSha256':sha(stderr)})
  raise RuntimeError(name+' exceeded its deadline; original partial output retained') from error
 (OUT/(name+'.stdout.log')).write_bytes(result.stdout);(OUT/(name+'.stderr.log')).write_bytes(result.stderr)
 receipt['stages'].append({'name':name,'exitCode':result.returncode,'stdoutSha256':sha(result.stdout),'stderrSha256':sha(result.stderr)})
 if result.returncode:raise RuntimeError(name+' failed; original output retained')
 return result
try:
 if os.environ.get('EXPECTED_PUBLIC_SOURCE')!=SOURCE:raise ValueError('Wrong explicit public source pin')
 publication_raw=(ROOT/'ci/v024-publication.json').read_bytes();publication=json.loads(publication_raw)
 (OUT/'publication.json').write_bytes(publication_raw)
 if publication['github']['ci']['headSha']!=SOURCE or publication['github']['postgresCi']['sourceCommit']!=SOURCE:raise ValueError('Publication source pin differs')
 tag_path=OUT/'tag-response.json'
 stage('anonymous-tag',['curl','-q','-4','--proto','=https','--proto-redir','=https','--location','--fail','--silent','--show-error','--connect-timeout','20','--max-time','60','--output',str(tag_path),'https://api.github.com/repos/HhWw96/moontxnwitness/git/ref/tags/v0.2.4'],70)
 tag=json.loads(tag_path.read_bytes())
 if tag.get('ref')!='refs/tags/v0.2.4' or tag.get('object',{}).get('type')!='commit' or tag['object']['sha']!=SOURCE:raise ValueError('Actual anonymous tag differs')
 items=[next(a for a in publication['github']['assets'] if a['name']=='MoonTxnWitness-v0.2.4-portable.zip'),{'name':'HhWw96-moontxnwitness-0.2.4-registry.zip','url':publication['mooncakes']['download'],'bytes':publication['mooncakes']['bytes'],'sha256':publication['mooncakes']['sha256']}]
 downloads=[]
 for ordinal,item in enumerate(items):
  path=OUT/'downloads'/item['name']
  stage('anonymous-download-'+str(ordinal),['curl','-q','-4','--proto','=https','--proto-redir','=https','--location','--fail','--silent','--show-error','--connect-timeout','20','--max-time','180','--max-filesize','134217728','--output',str(path),'--write-out','%{http_code}|%{size_download}|%{time_total}',item['url']],190)
  row={'url':item['url'],'file':path.name,'bytes':path.stat().st_size,'sha256':sha(path.read_bytes()),'anonymous':True}
  downloads.append(row)
  if row['bytes']!=item['bytes'] or row['sha256']!=item['sha256']:raise ValueError('Actual anonymously downloaded asset bytes differ')
 receipt['downloads']=downloads
 provider=OUT/'provider';fixtures=OUT/'fixtures';checks=OUT/'checks'
 stage('prepare-provider',[sys.executable,'-I','-B','scripts/prepare-v024-public-provider.py','--publication-receipt',str(OUT/'publication.json'),'--expected-source',SOURCE,'--portable',str(OUT/'downloads'/items[0]['name']),'--registry',str(OUT/'downloads'/items[1]['name']),'--out',str(provider)],120)
 stage('generate-original-fixtures',['node','scripts/generate-v024-compatibility.mjs','--provider',str(provider),'--expected-source',SOURCE,'--out',str(fixtures)],120)
 stage('public77-contracts',['node','scripts/v024-public-compatibility-test.mjs',str(provider),str(fixtures),SOURCE,str(checks)],120)
 checked=json.loads((checks/'receipt.json').read_bytes())
 if checked.get('passed') is not True or checked.get('checkCount')!=77:raise ValueError('Original producer contracts incomplete')
 receipt.update(passed=True,authenticPublic24FixturesGenerated=True,originalProducerFamilies=15,publicProducerChecks=77,fixtureManifestSha256=sha((fixtures/'manifest.json').read_bytes()),providerSha256=sha((provider/'provider.json').read_bytes()))
except BaseException as error:
 receipt['failure']={'class':type(error).__name__,'message':str(error)}
finally:
 receipt['finishedAt']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 (OUT/'ci-run-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8',newline='\n')
 print(json.dumps({k:receipt.get(k) for k in ['passed','expectedSourceCommit','originalProducerFamilies','publicProducerChecks','failure']}))
raise SystemExit(0 if receipt['passed'] else 1)
