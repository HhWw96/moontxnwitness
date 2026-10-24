"""Future anonymous public26 production; missing explicit public pins always refuses."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,runpy,subprocess,sys
VERSION='0.2.6';REPO='https://github.com/HhWw96/moontxnwitness';HERE=Path(__file__).resolve().parent
sha=lambda raw:hashlib.sha256(raw).hexdigest()

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['publication-receipt','publisher-upload-reference','asset-bindings','expected-bindings-sha256','expected-source','out']:p.add_argument('--'+name,required=True)
 p.add_argument('--execute-after-publication',action='store_true');a=p.parse_args()
 if not a.execute_after_publication:raise ValueError('Explicit execution only after actual verified public26 release')
 helper=runpy.run_path(str(HERE/'prepare_public026_provider.py'))
 bindings_raw,bindings=helper['load_bindings'](a.asset_bindings,a.expected_bindings_sha256,a.expected_source)
 publication_raw=helper['bounded_file'](a.publication_receipt,4*1024*1024);publication=json.loads(publication_raw)
 publisher_raw=helper['bounded_file'](a.publisher_upload_reference,1024*1024);publisher=json.loads(publisher_raw)
 assert publication['passed'] is True and publication['version']==VERSION and publication['account']=='HhWw96'
 assert publication['github']['repository']==REPO and publication['github']['release']==REPO+'/releases/tag/v'+VERSION
 assert publication['github']['ci']['headSha']==publication['github']['postgresCi']['sourceCommit']==a.expected_source
 assert publication['github']['ci']['conclusion']=='success' and publication['github']['postgresCi']['conclusion']=='success' and publication['github']['ci']['linuxNativeExecuted'] is True
 assert publisher['sourceCommit']==a.expected_source and publisher['version']==VERSION and publisher['recordedBeforePublicDownload'] is True
 assets={x['name']:x for x in publication['github']['assets']}
 assert set(assets)=={f'MoonTxnWitness-v{VERSION}-{kind}.zip' for kind in ['source','portable']}
 for name,row in assets.items():
  expected=bindings['assets'][name]
  assert row['anonymousDownload'] is True and {k:row[k] for k in ['url','bytes','sha256']}==expected
 cakes=publication['mooncakes'];registry=bindings['assets']['registry.zip']
 assert cakes['download']==registry['url'] and cakes['sha256']==publisher['actualUploadedSha256']==registry['sha256'] and cakes['bytes']==publisher['actualUploadedBytes']==registry['bytes']
 assert cakes['module']=='HhWw96/moontxnwitness' and cakes['version']==VERSION and cakes['uploadedBytesMatchPublicDownload'] is True
 assert cakes['registryOnlyConsumer']['passed'] is True and cakes['registryOnlyConsumer']['workspaceOverride'] is False
 # All independent public pins and original publication/upload claims are checked before any side effect.
 out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=False);(out/'downloads').mkdir()
 receipt={'format':'moontxnwitness-actual-public026-producer-run/v1','version':VERSION,'expectedSourceCommit':a.expected_source,'externalBindingsSha256':sha(bindings_raw),'passed':False,'startedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'authorizationHeaderSentForPublicDownloads':False,'cookieHeaderSentForPublicDownloads':False,'compilerExecuted':False,'actualDatabaseExecutedHere':False,'authorDistRead':False,'stages':[]}
 env={k:v for k,v in os.environ.items() if not any(t in k.upper() for t in ['TOKEN','PASSWORD','SECRET','CREDENTIAL','AUTH']) and k.upper() not in ['NODE_OPTIONS','NODE_PATH','PYTHONPATH','PYTHONSTARTUP','PYTHONOPTIMIZE']};env.update(TEMP=str(out),TMP=str(out))
 def stage(name,args,seconds):
  try:
   r=subprocess.run(args,cwd=HERE,env=env,capture_output=True,timeout=seconds);stdout=r.stdout;stderr=r.stderr;code=r.returncode
  except subprocess.TimeoutExpired as e:stdout=e.stdout or b'';stderr=e.stderr or b'';code=None
  streams={}
  for label,raw in [('stdout',stdout),('stderr',stderr)]:
   file=name+'.'+label+'.log'
   with (out/file).open('xb') as f:assert f.write(raw)==len(raw)
   streams[label]={'file':file,'bytes':len(raw),'sha256':sha(raw)}
  receipt['stages'].append({'name':name,'exitCode':code,'timedOut':code is None,**streams})
  if code!=0:raise RuntimeError(name+' failed/timed out; original partial output retained')
  return stdout
 curl=['curl','-q','-4','--proto','=https','--proto-redir','=https','--location','--fail','--silent','--show-error','--connect-timeout','20']
 try:
  (out/'publication.json').write_bytes(publication_raw);(out/'publisher-upload.json').write_bytes(publisher_raw);(out/'external-asset-bindings.json').write_bytes(bindings_raw)
  tag_path=out/'tag-response.json';stage('anonymous-tag',curl+['--max-time','60','--max-filesize','1048576','--output',str(tag_path),'https://api.github.com/repos/HhWw96/moontxnwitness/git/ref/tags/v'+VERSION],70)
  tag=json.loads(tag_path.read_bytes());assert tag['ref']=='refs/tags/v'+VERSION and tag['object']['type']=='commit' and tag['object']['sha']==a.expected_source
  downloads=[]
  names=[f'MoonTxnWitness-v{VERSION}-{kind}.zip' for kind in ['source','portable']]+[f'MoonTxnWitness-v{VERSION}-SHA256SUMS.txt','registry.zip']
  for i,name in enumerate(names):
   item=bindings['assets'][name];path=out/'downloads'/name
   stage('anonymous-asset-'+str(i),curl+['--max-time','240','--max-filesize',str(item['bytes']),'--output',str(path),'--write-out','%{http_code}|%{size_download}|%{time_total}',item['url']],250)
   raw=helper['bounded_file'](path,item['bytes']);assert len(raw)==item['bytes'] and sha(raw)==item['sha256']
   downloads.append({'file':name,'url':item['url'],'bytes':len(raw),'sha256':sha(raw),'anonymous':True})
  transport={**receipt,'passed':True,'downloads':downloads,'scope':'Anonymous source/portable/checksum/registry downloads only; no generated-capsule or next-version acceptance'}
  (out/'download-receipt.json').write_text(json.dumps(transport,indent=2)+'\n',encoding='utf8',newline='\n')
  provider=out/'provider';fixtures=out/'fixtures';sums_name=f'MoonTxnWitness-v{VERSION}-SHA256SUMS.txt'
  args=[sys.executable,'-I','-B',str(HERE/'prepare_public026_provider.py'),'--publication-receipt',str(out/'publication.json'),'--publisher-upload-reference',str(out/'publisher-upload.json'),'--transport-receipt',str(out/'download-receipt.json'),'--tag-response',str(tag_path),'--expected-source',a.expected_source,'--expected-sums-sha256',bindings['assets'][sums_name]['sha256'],'--asset-bindings',str(out/'external-asset-bindings.json'),'--expected-bindings-sha256',a.expected_bindings_sha256,'--source',str(out/'downloads'/f'MoonTxnWitness-v{VERSION}-source.zip'),'--portable',str(out/'downloads'/f'MoonTxnWitness-v{VERSION}-portable.zip'),'--sums',str(out/'downloads'/sums_name),'--registry',str(out/'downloads/registry.zip'),'--out',str(provider)]
  stage('prepare-provider',args,120)
  stage('generate-public26',['node',str(HERE/'generate_public026_fixtures.mjs'),'--provider',str(provider),'--expected-source',a.expected_source,'--out',str(fixtures)],300)
  manifest=json.loads((fixtures/'manifest.json').read_bytes());assert manifest['actualPublishedProducer'] is True and manifest['producerEngineVersion']==VERSION and manifest['sourceCommit']==a.expected_source and len(manifest['cases'])==35
  receipt.update(passed=True,actualPublishedProducer=True,existingFamilies=21,modelCases=14,totalCases=35,downloads=downloads,providerSha256=sha((provider/'provider.json').read_bytes()),fixtureManifestSha256=sha((fixtures/'manifest.json').read_bytes()),rawEsmIdentityPreserved=True,futureConsumerCompatibilityAccepted=False)
 except BaseException as error:receipt['failure']={'class':type(error).__name__,'message':str(error)}
 finally:
  receipt['finishedAt']=datetime.datetime.now(datetime.timezone.utc).isoformat();(out/'producer-run-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8',newline='\n');print(json.dumps({k:receipt.get(k) for k in ['passed','version','expectedSourceCommit','totalCases','failure']}))
 return 0 if receipt['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
