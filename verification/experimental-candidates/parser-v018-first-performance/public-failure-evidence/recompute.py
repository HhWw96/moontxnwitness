"""Read-only arithmetic audit of existing files. Never launches a process or SDK."""
from pathlib import Path
import argparse,json,hashlib,statistics,math,collections
ROOT=Path(__file__).resolve().parent
SHA=lambda b:hashlib.sha256(b).hexdigest()
load=lambda p:json.loads(Path(p).read_bytes())
def same(a,b):
 if isinstance(a,dict):assert isinstance(b,dict) and a.keys()==b.keys(),('keys',a.keys(),b.keys());[same(a[k],b[k]) for k in a]
 elif isinstance(a,list):assert isinstance(b,list) and len(a)==len(b);[same(x,y) for x,y in zip(a,b)]
 elif isinstance(a,(int,float)) and not isinstance(a,bool):assert math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-9),(a,b)
 else:assert a==b,(a,b)
def p95(xs):return sorted(xs)[math.ceil(len(xs)*.95)-1]
def pairs(ps):
 d={}
 for k,v in ps:assert k not in d,'duplicate JSON key';d[k]=v
 return d
def projected(raw,version):
 text=raw.decode('utf-8');x=json.loads(text,object_pairs_hook=pairs);assert x['tool']=='MoonTxnWitness' and x['schemaVersion']==2 and x['algorithm']=='bounded-register-v2.1' and x['version']==version
 decoder=json.JSONDecoder();i=0
 def white(i):
  while i<len(text) and text[i] in ' \t\r\n':i+=1
  return i
 i=white(i);assert text[i]=='{';i+=1;spans=[]
 while True:
  i=white(i)
  if text[i]=='}':i+=1;break
  k,ke=decoder.raw_decode(text,i);keyraw=text[i:ke];i=white(ke);assert text[i]==':';start=white(i+1);_,end=decoder.raw_decode(text,start)
  if k=='version':assert keyraw=='"version"' and text[start:end]==json.dumps(version);spans.append((start,end))
  i=white(end)
  if text[i]==',':i+=1;continue
  assert text[i]=='}';i+=1;break
 assert white(i)==len(text) and len(spans)==1;a,b=spans[0]
 return (text[:a]+'"__ENGINE_METADATA_VERSION__"'+text[b:]).encode('utf-8')

def safe(name):
 p=(ROOT/str(name).replace('\\','/')).resolve();assert p.is_relative_to(ROOT),name;return p
def main():
 a=argparse.ArgumentParser();a.add_argument('--manifest-sha256',required=True);x=a.parse_args();raw=(ROOT/'public-manifest.json').read_bytes();assert SHA(raw)==x.manifest_sha256;m=json.loads(raw)
 for row in m['files']:
  b=safe(row['file']).read_bytes();assert len(b)==row['bytes'] and SHA(b)==row['sha256'],row['file']
 origin=load(ROOT/'origin-to-public.json');orig={r['file']:r for r in origin['files']}
 for name,row in orig.items():
  b=safe(name).read_bytes();assert len(b)==row['publicBytes'] and SHA(b)==row['publicSha256'];assert row['allNumericAndNonStringTextUnchanged'] and row['nonpathStringTokensUnchanged']
 receipt=load(ROOT/'data/receipt.json');protocol=load(ROOT/'protocol/preparation-manifest.v3-final.json');lineage=load(ROOT/'metadata/lineage.json');auth=load(ROOT/'metadata/historical-authorization.json');binding=load(ROOT/'metadata/historical-runtime-source-binding.json')
 assert orig['data/receipt.json']['originalSha256']=='d0dcafc4e9589c18adb4bb81de19d01a899dd1194eba4a4e2630bd1dff58289c';assert orig['metadata/historical-authorization.json']['originalSha256']==receipt['authorizationSha256']=='8d733aa3413fcfe7150363499a3e1e356698cd418491f09683d0fa7e7673c374';assert orig['metadata/historical-runtime-source-binding.json']['originalSha256']==receipt['runtimeSourceBindingSha256']==auth['runtimeSourceBindingSha256']=='72e1eccf6a998262fd27434fdeed869ab80a84a114188f50323668d28838699b'
 assert SHA((ROOT/'protocol/preparation-manifest.v3-final.json').read_bytes())==receipt['preparationManifestSha256']=='08733784a7aba7dddc1b340c87cf7fd2acfb909c29314a118bca842cd47d9103'
 for row in protocol['files']:
  b=safe('protocol/'+row['file']).read_bytes();assert len(b)==row['bytes'] and SHA(b)==row['sha256']
 assert len(protocol['files'])==38;assert auth['runPerformanceNow'] and auth['exclusiveMachine'] and auth['allAgentsStopped'] and auth['runningNonMeasurementAgents']==[]
 assert lineage['authorization']['historicalOnly'] and not lineage['authorization']['freshMeasurementAuthorizedByThisClosure']
 pub=load(ROOT/'metadata/baseline17-publication.json');assert pub['version']=='0.1.7' and pub['passed'] is True;assert orig['metadata/baseline17-publication.json']['originalSha256']==binding['baselinePublicationReceipt']['sha256']
 assert binding['baselineVersion']=='0.1.7' and binding['currentVersion']=='0.1.8' and binding['baselineReleasedByRoot'] is True
 for eng,version in [('baseline','0.1.7'),('current','0.1.8')]:
  e=binding['engines'][eng];assert e['version']==version;assert SHA(safe(e['core']['path']).read_bytes())==e['core']['sha256']==SHA((ROOT/f'data/{eng}.mjs').read_bytes());build=load(ROOT/f'engines/{eng}/build-manifest.json');assert SHA((ROOT/f'engines/{eng}/build-manifest.json').read_bytes())==e['buildManifest']['sha256'];assert build['version']==version and build['sourceSha256']==e['source']['sourceFingerprint'] and build['coreSha256']==e['core']['sha256']
  source=e['source'];h=hashlib.sha256()
  for row in source['files']:
   b=safe(str(source['root'])+'/'+row['file']).read_bytes();assert len(b)==row['bytes'] and SHA(b)==row['sha256']
  for name in sorted(['moon.mod']+[r['file'] for r in source['files'] if r['file'].startswith('src/') and (r['file'].endswith('.mbt') or r['file'].endswith('/moon.pkg'))]):h.update(name.encode()+b'\0');h.update(safe(str(source['root'])+'/'+name).read_bytes());h.update(b'\0')
  assert h.hexdigest()==source['sourceFingerprint']
 assert lineage['rejectedCandidate']['sourceFingerprint']=='5999060f42d1f6159450fc24c876840fc80a1d991faf046c479559df0ec7d54b';assert lineage['rejectedCandidate']['coreSha256']=='5b63c815caae7246198582d9289a0c5ef8ee6c170513f8f176a2ecd0779406e5'
 counts=collections.Counter();samples=0;failed=[];seen=set();order=0;cases={r['name']:r for r in protocol['cases']};eq_by={(e['case'],e['phase']):e for e in receipt['fullOutputEquivalence']};assert len(cases)==7 and len(eq_by)==14 and len(receipt['results'])==14
 for case in receipt['results']:
  name,phase=case['case'],case['phase'];assert (name,phase) not in seen;seen.add((name,phase));eq=eq_by[(name,phase)];assert eq['passed'];source_case=cases[name]
  for eng in ['baseline','current']:
   times=[];cold=[]
   for mode,batches in [('equivalence',[-1]),('warm',range(3)),('cold',range(3))]:
    for batch in batches:
     stem=f'{name}-{phase}-{mode}-{batch}-{eng}';job=load(ROOT/f'data/{stem}.job.json');worker=load(ROOT/f'data/{stem}.json');parent=load(ROOT/f'data/{stem}.parent.json');counts[mode]+=1
     assert (job['engine'],job['phase'],job['mode'],job['batch'])==(eng,phase,mode,batch);assert (worker['engine'],worker['phase'],worker['mode'],worker['batch'])==(eng,phase,mode,batch);assert job['warmups']==5 and job['samples']==30
     assert worker['passed'] and worker['exactCompleteOutputValidated'];assert worker['version']==binding['engines'][eng]['version'];assert job['inputSha256']==worker['inputSha256']==source_case['inputSha256']==SHA(safe(job['inputPath']).read_bytes());assert job['coreSha256']==worker['coreSha256']==binding['engines'][eng]['core']['sha256'];assert worker['fullOutputSha256']==eq['outputSha256'];assert worker['rawFullOutputSha256']==eq[eng+'RawOutputSha256']
     pure=dict(parent);wall=pure.pop('externalProcessWallMs');same(worker,pure);same(max(worker['rssSamplesBytes']),worker['maxObservedRssBytes'])
     if mode=='warm':
      assert worker['warmups']==5 and worker['measuredSamples']==30 and len(worker['timesMs'])==30 and len(worker['rssSamplesBytes'])==31;same(parent,case['rawWarm'][eng][batch]);same(statistics.median(worker['timesMs']),worker['medianMs']);same(p95(worker['timesMs']),worker['p95Ms']);times+=worker['timesMs'];samples+=30
     else:assert worker['warmups']==0 and worker['measuredSamples']==0 and worker['timesMs']==[]
     if mode=='cold':same(parent,case['rawCold'][eng][batch]);cold.append(wall)
     if mode=='equivalence':
      native=(ROOT/f'data/{stem}.full-output.txt').read_bytes();project=(ROOT/f'data/{stem}.projected-output.txt').read_bytes();assert SHA(native)==worker['rawFullOutputSha256'] and len(native)==worker['outputBytes'];assert SHA(project)==worker['fullOutputSha256'];assert project==(projected(native,worker['version']) if phase=='full' else native)
     else:assert job['expectedOutputSha256']==eq['outputSha256'] and job['expectedRawOutputSha256']==eq[eng+'RawOutputSha256']
   summary=case['summary'][eng];assert len(times)==90;same(statistics.median(times),summary['medianMs']);same(p95(times),summary['p95Ms']);same(statistics.median(cold),summary['coldExternalProcessMedianMs']);same(statistics.median([r['lifetimePeakRssKiB'] for r in case['rawWarm'][eng]]),summary['medianLifetimePeakRssKiB'])
  for batch in range(3):
   engines=['baseline','current'] if batch%2==0 else ['current','baseline']
   for mode in ['warm','cold']:
    mt=[orig[f'data/{name}-{phase}-{mode}-{batch}-{eng}.job.json']['originalFileMtimeNs'] for eng in engines];assert mt[0]<mt[1];order+=1
  if case['group']=='control':
   for metric,r in case['controlRegression'].items():
    before=case['summary']['baseline'][metric];after=case['summary']['current'][metric];allow=max(2,before*.1);same(r['baseline'],before);same(r['current'],after);same(r['deltaMs'],after-before);same(r['allowedRegressionMs'],allow);assert r['passed']==(after-before<=allow)
    if not r['passed']:failed.append({'case':name,'phase':phase,'metric':metric,'baseline':before,'current':after,'deltaMs':after-before,'allowedRegressionMs':allow,'excessMs':after-before-allow})
 assert counts=={'equivalence':28,'warm':84,'cold':84} and samples==2520 and len(failed)==2
 assert receipt['passed'] is False and receipt['correctnessPassed'] is True and receipt['protocolCompleted'] is True and receipt['controlRegressionPassed'] is False and receipt['performanceImprovementClaim'] is False
 print(json.dumps({'dataRecomputationPassed':True,'originalPerformanceGatePassed':False,'records':dict(counts),'measuredSamples':samples,'equivalencePairs':14,'failedControlMetrics':failed,'originalFileTimeOrderPairsConsistent':order,'executionOrderCryptographicallyProven':False,'exclusiveEnvironmentIndependentlyProven':False,'historicalAuthorizationOnly':True,'newMeasurementOrSDKBuildDatabaseNetworkExecuted':False,'futureStable18BuildAccepted':False},indent=2))
if __name__=='__main__':main()
