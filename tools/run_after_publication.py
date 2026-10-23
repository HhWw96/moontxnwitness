"""Future anonymous public25 production. No execution before actual release verification."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,re,subprocess,sys
VERSION='0.2.5';REPO='https://github.com/HhWw96/moontxnwitness';HERE=Path(__file__).resolve().parent
sha=lambda raw:hashlib.sha256(raw).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['publication-receipt','publisher-upload-reference','expected-source','expected-sums-sha256','out']:p.add_argument('--'+n,required=True)
 p.add_argument('--execute-after-publication',action='store_true');a=p.parse_args()
 if not a.execute_after_publication:raise ValueError('Only prepare this tool until actual public25 publication is verified; explicit --execute-after-publication required')
 assert re.fullmatch('[0-9a-f]{40}',a.expected_source) and re.fullmatch('[0-9a-f]{64}',a.expected_sums_sha256)
 out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=False);(out/'downloads').mkdir()
 receipt={'format':'moontxnwitness-actual-public025-producer-run/v1','version':VERSION,'expectedSourceCommit':a.expected_source,'passed':False,'startedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'authorizationHeaderSentForPublicDownloads':False,'cookieHeaderSentForPublicDownloads':False,'compilerExecuted':False,'actualDatabaseExecutedHere':False,'authorDistRead':False,'stages':[]}
 env={k:v for k,v in os.environ.items() if k not in ['GH_TOKEN','GITHUB_TOKEN','GH_ACTIONS_READ_TOKEN','MOONCAKES_TOKEN']};env.update(TEMP=str(out),TMP=str(out))
 def stage(name,args,seconds):
  try:
   r=subprocess.run(args,cwd=HERE,env=env,capture_output=True,timeout=seconds);stdout=r.stdout;stderr=r.stderr;code=r.returncode
  except subprocess.TimeoutExpired as e:stdout=e.stdout or b'';stderr=e.stderr or b'';code=None
  for label,raw in [('stdout',stdout),('stderr',stderr)]:
   with (out/(name+'.'+label+'.log')).open('xb') as f:f.write(raw)
  receipt['stages'].append({'name':name,'exitCode':code,'timedOut':code is None,'stdoutSha256':sha(stdout),'stderrSha256':sha(stderr)})
  if code!=0:raise RuntimeError(name+' failed/timed out; original partial output retained')
  return stdout
 curl=['curl','-q','-4','--proto','=https','--proto-redir','=https','--location','--fail','--silent','--show-error','--connect-timeout','20']
 try:
  publication_raw=Path(a.publication_receipt).read_bytes();publication=json.loads(publication_raw);publisher_raw=Path(a.publisher_upload_reference).read_bytes();publisher=json.loads(publisher_raw)
  assert publication['passed'] and publication['version']==VERSION and publication['account']=='HhWw96'
  assert publication['github']['ci']['headSha']==publication['github']['postgresCi']['sourceCommit']==a.expected_source
  assert publisher['sourceCommit']==a.expected_source and publisher['version']==VERSION and publisher['recordedBeforePublicDownload']
  (out/'publication.json').write_bytes(publication_raw);(out/'publisher-upload.json').write_bytes(publisher_raw)
  tag_path=out/'tag-response.json';stage('anonymous-tag',curl+['--max-time','60','--output',str(tag_path),'https://api.github.com/repos/HhWw96/moontxnwitness/git/ref/tags/v'+VERSION],70)
  tag=json.loads(tag_path.read_bytes());assert tag['ref']=='refs/tags/v'+VERSION and tag['object']['type']=='commit' and tag['object']['sha']==a.expected_source
  items=[dict(r) for r in publication['github']['assets']]
  assert {x['name'] for x in items}=={f'MoonTxnWitness-v{VERSION}-{k}.zip' for k in ['source','portable']}
  for r in items:assert r['anonymousDownload'] and r['url']==REPO+'/releases/download/v'+VERSION+'/'+r['name']
  items.append({'name':f'MoonTxnWitness-v{VERSION}-SHA256SUMS.txt','url':REPO+'/releases/download/v'+VERSION+f'/MoonTxnWitness-v{VERSION}-SHA256SUMS.txt','sha256':a.expected_sums_sha256})
  c=publication['mooncakes'];assert c['sha256']==publisher['actualUploadedSha256'];items.append({'name':'registry.zip','url':c['download'],'sha256':c['sha256'],'bytes':c['bytes']})
  downloads=[]
  for i,item in enumerate(items):
   name=item['name'];assert Path(name).name==name and ':' not in name and '\\' not in name;path=out/'downloads'/name
   stage('anonymous-asset-'+str(i),curl+['--max-time','240','--max-filesize','268435456','--output',str(path),'--write-out','%{http_code}|%{size_download}|%{time_total}',item['url']],250)
   raw=path.read_bytes();assert len(raw)<=256*1024*1024 and sha(raw)==item['sha256']
   if 'bytes' in item:assert len(raw)==item['bytes']
   downloads.append({'file':name,'url':item['url'],'bytes':len(raw),'sha256':sha(raw),'anonymous':True})
  transport={**receipt,'passed':True,'downloads':downloads,'scope':'Anonymous source/portable/checksum/registry downloads only; no producer or future compatibility claim'}
  (out/'download-receipt.json').write_text(json.dumps(transport,indent=2)+'\n',encoding='utf8',newline='\n')
  provider=out/'provider';fixtures=out/'fixtures'
  args=[sys.executable,'-I','-B',str(HERE/'prepare_public025_provider.py'),'--publication-receipt',str(out/'publication.json'),'--publisher-upload-reference',str(out/'publisher-upload.json'),'--transport-receipt',str(out/'download-receipt.json'),'--tag-response',str(tag_path),'--expected-source',a.expected_source,'--expected-sums-sha256',a.expected_sums_sha256,'--source',str(out/'downloads'/f'MoonTxnWitness-v{VERSION}-source.zip'),'--portable',str(out/'downloads'/f'MoonTxnWitness-v{VERSION}-portable.zip'),'--sums',str(out/'downloads'/f'MoonTxnWitness-v{VERSION}-SHA256SUMS.txt'),'--registry',str(out/'downloads/registry.zip'),'--out',str(provider)]
  stage('prepare-provider',args,120)
  stage('generate-public25',['node',str(HERE/'generate_public025_fixtures.mjs'),'--provider',str(provider),'--expected-source',a.expected_source,'--out',str(fixtures)],180)
  manifest=json.loads((fixtures/'manifest.json').read_bytes());assert manifest['actualPublishedProducer'] and manifest['producerEngineVersion']==VERSION and manifest['sourceCommit']==a.expected_source and len(manifest['cases'])==21
  receipt.update(passed=True,actualPublishedProducer=True,existingFamilies=15,categoryCases=6,totalCases=21,downloads=downloads,providerSha256=sha((provider/'provider.json').read_bytes()),fixtureManifestSha256=sha((fixtures/'manifest.json').read_bytes()),rawEsmIdentityPreserved=True,future26CompatibilityAccepted=False)
 except BaseException as error:receipt['failure']={'class':type(error).__name__,'message':str(error)}
 finally:
  receipt['finishedAt']=datetime.datetime.now(datetime.timezone.utc).isoformat();(out/'producer-run-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8',newline='\n');print(json.dumps({k:receipt.get(k) for k in ['passed','version','expectedSourceCommit','totalCases','failure']}))
 return 0 if receipt['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
