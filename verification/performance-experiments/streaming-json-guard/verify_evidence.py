"""Read-only portable evidence verification. It never imports or runs MoonTxnWitness."""
import gzip, hashlib, json, math, pathlib, re, sys, zipfile, tarfile

def digest(raw): return hashlib.sha256(raw).hexdigest()
def stats(values):
    assert values and all(isinstance(v,(int,float)) and math.isfinite(v) and v>=0 for v in values)
    v=sorted(values);return {'count':len(v),'median':v[len(v)//2],'p95':v[math.ceil(.95*len(v))-1],'min':v[0],'max':v[-1]}
def safe(name):
    assert isinstance(name,str) and name and '\\' not in name and ':' not in name and not name.startswith('/') and all(p not in ('','.','..') for p in name.split('/'))
    return name

def run(reader,names):
    manifest=json.loads(reader('manifest.json'));files=manifest['files'];assert len(files)==len(set(files))
    assert set(names)==set(files)|{'manifest.json'},'Archive member set differs'
    for name,f in files.items():
        raw=reader(safe(name));assert len(raw)==f['bytes'] and digest(raw)==f['sha256'],name
        assert not re.search(rb'(?i)C:(?:\\+|/+)(?:Users|Documents and Settings)(?:\\+|/+)',raw),'Private C-user path in public member'
    p=json.loads(reader('protocol/plan.json'));r=json.loads(reader('results/receipt.json'))
    assert digest(reader('protocol/plan.json'))=='f1d96364ffdf8d9c2463af363276c933f73c04316cdf2b676003db9f75dbe3db'
    assert r['completed'] is True and r['outputsEquivalent'] is True
    assert r.get('failure') is None and len(r['workers'])==60 and all(w['passed'] for w in r['workers'])
    assert r['candidateAdopted'] is False
    privacy_scope=json.loads(reader('PRIVACY-SCOPE.json'))
    assert privacy_scope['correctnessOriginalFilesTotal']==605 and privacy_scope['correctnessOriginalFilesPublishedUnmodified']==604 and privacy_scope['correctnessOriginalFilesExcludedForCUserPaths']==1
    assert privacy_scope['fullyRerunnableOriginalBenchmarkClosure'] is False
    for name,ex in privacy_scope['excludedOriginals'].items():assert name not in files and len(ex['sha256'])==64
    runtime_count=0
    for role in ('baseline','candidate'):
        runtime=p['runtimes'][role]
        assert len(runtime['files'])==47
        for name,expected in runtime['files'].items():
            raw=reader('frozen/'+runtime['directory']+'/'+safe(name));assert len(raw)==expected['bytes'] and digest(raw)==expected['sha256'];runtime_count+=1
    assert runtime_count==94
    gate=json.loads(reader('frozen/correctness-evidence/gate.json'))
    assert gate['historicalManifestMatched'] is False and gate['oldManifestExpectationsChanged'] is False
    published_correctness=0;excluded_correctness=0
    for e in gate['evidenceFiles']:
        name='frozen/correctness-evidence/original/'+safe(e['name'])
        if name in privacy_scope['excludedOriginals']:
            q=privacy_scope['excludedOriginals'][name];assert q['bytes']==e['bytes'] and q['sha256']==e['sha256'];excluded_correctness+=1
        else:
            raw=reader(name);assert len(raw)==e['bytes'] and digest(raw)==e['sha256'];published_correctness+=1
    assert published_correctness==604 and excluded_correctness==1
    by={};originals=0;sample_count=0;normalized_hashes={};privacy=re.compile(rb'(?i)C:(?:\\+|/+)(?:Users|Documents and Settings)(?:\\+|/+)')
    for f in p['fixtures']:
        raw=reader('protocol/'+f['file']);assert digest(raw)==f['sha256'] and len(raw)==f['bytes']
    for w in r['workers']:
        worker=json.loads(reader('results/'+w['name']+'/receipt.json'));assert worker==w['receipt'];assert worker['sampleCount']==30 and len(worker['samplesMs'])==30 and worker['sampleStatsMs']==stats(worker['samplesMs']);sample_count+=30
        assert [c['durationMs'] for c in worker['calls'][6:]]==worker['samplesMs']
        assert worker['peakRssKiB']==worker['resourceUsageBeforeLastArchival']['maxRSS']>0
        labels=['cold']+['warmup-'+str(i+1) for i in range(5)]+['sample-'+str(i+1) for i in range(30)];assert [c['label'] for c in worker['calls']]==labels
        f=next(f for f in p['fixtures'] if f['id']==w['id']);runtime=p['runtimes'][w['role']]
        for call in worker['calls']:
            packed=reader('results/'+w['name']+'/'+safe(call['output']['file']));assert len(packed)==call['output']['gzipBytes'] and digest(packed)==call['output']['gzipSha256'];raw=gzip.decompress(packed);assert len(raw)==call['output']['bytes'] and digest(raw)==call['output']['sha256'];assert not privacy.search(raw)
            report=json.loads(raw);comparable=raw
            if f['group']=='six-models':
                assert report['engine']['version']=='0.2.6' and report['engine']['coreSha256']==runtime['files']['core.mjs']['sha256'] and report['engine']['hostSha256']==runtime['files']['classification-models.mjs']['sha256']
                assert report['coreReportReplay']['valid'] is True and set(report['result']['models'])==set(p['models'])
                before=b'"engine":{"version":"0.2.6","coreSha256":"'+runtime['files']['core.mjs']['sha256'].encode()+b'","hostSha256":'
                after=b'"engine":{"version":"0.2.6","coreSha256":"'+p['baselineCoreSha256'].encode()+b'","hostSha256":'
                assert raw.count(before)==1,'Single exact top-level engine prefix required';comparable=raw.replace(before,after,1)
            else:assert report['version']=='0.2.6' and report['status']==f['expected']['status']
            assert digest(comparable)==call['comparisonSha256'];normalized_hashes.setdefault(w['id'],set()).add(digest(comparable));originals+=1
        by.setdefault(w['id'],{})[(w['role'],w['batch'])]=worker
    assert originals==2160 and sample_count==1800 and all(len(v)==1 for v in normalized_hashes.values())
    failures=[];groups={}
    for f in p['fixtures']:
        pair=by[f['id']];a=stats([x for batch in (1,2,3) for x in pair[('baseline',batch)]['samplesMs']]);b=stats([x for batch in (1,2,3) for x in pair[('candidate',batch)]['samplesMs']]);ar=stats([pair[('baseline',batch)]['peakRssKiB'] for batch in (1,2,3)]);br=stats([pair[('candidate',batch)]['peakRssKiB'] for batch in (1,2,3)])
        g=r['groups'][f['id']];assert a==g['baseline']['samples'] and b==g['candidate']['samples'] and ar==g['baseline']['rss'] and br==g['candidate']['rss'];groups[f['id']]={'speedup':a['median']/b['median'],'rssRatio':br['median']/ar['median']}
        for role in ('baseline','candidate'):
            rows=[pair[(role,batch)] for batch in (1,2,3)]
            for key,field in [('coldLoad','coldLoadMs'),('firstCall','firstCallMs'),('processElapsedAtFirstCall','processElapsedAtFirstCallMs')]:assert stats([w[field] for w in rows])==g[role][key]
            assert stats([c['output']['bytes'] for w in rows for c in w['calls']])==g[role]['outputBytes']
        if f['id'] in p['controlIds']:
            failed_batches=[]
            for batch in (1,2,3):
                ap=pair[('baseline',batch)]['sampleStatsMs']['p95'];bp=pair[('candidate',batch)]['sampleStatsMs']['p95']
                if bp>ap+max(.1*ap,2):failed_batches.append(batch)
            pooled=b['p95']<=a['p95']+max(.1*a['p95'],2);passed=not failed_batches and pooled;assert passed==g['controlPassed']
            if not passed:failures.append({'id':f['id'],'failedBatches':failed_batches,'pooledPassed':pooled})
    target=groups['register-128-chain'];assert target['speedup']==r['narrowTarget']['speedup'] and target['rssRatio']==r['narrowTarget']['rssRatio']
    speed_passed=target['speedup']>=p['preRegisteredTarget']['speedupAtLeast'];rss_passed=target['rssRatio']<=p['preRegisteredTarget']['rssRatioAtMost'];target_passed=speed_passed or rss_passed;controls_passed=not failures
    assert r['narrowTarget']['speedupPassed']==speed_passed and r['narrowTarget']['rssPassed']==rss_passed and r['narrowTargetPassed']==target_passed
    assert r['controlsPassed']==controls_passed and r['performanceTargetsPassed']==(target_passed and controls_passed)
    assert speed_passed and not rss_passed and controls_passed
    six=[groups[f['id']] for f in p['fixtures'] if f['group']=='six-models'];speed=math.exp(sum(math.log(g['speedup']) for g in six)/6);rss=math.exp(sum(math.log(g['rssRatio']) for g in six)/6)
    assert abs(speed-r['sixModelAggregate']['geometricMeanSpeedup'])<1e-12 and abs(rss-r['sixModelAggregate']['geometricMeanRssRatio'])<1e-12
    return {'evidenceVerified':True,'originalOutputs':originals,'formalSamples':sample_count,'completedWorkers':60,'rawOutputIdentityAndSdkSelfVerificationPassed':True,'performanceGatePassed':target_passed and controls_passed,'candidateAdopted':False,'target':target,'sixModelAggregate':{'speedup':speed,'rssRatio':rss},'failedControls':failures,'runtimeFilesVerified':runtime_count,'correctnessOriginalsPublished':published_correctness,'correctnessOriginalsExcludedForPrivacy':excluded_correctness,'originalBenchmarkFullyRerunnable':False,'historicalManifestMatched':False,'sdkExecuted':False,'newPerformanceMeasurement':False}

if __name__=='__main__':
    if len(sys.argv)==2:
        if zipfile.is_zipfile(sys.argv[1]):
            with zipfile.ZipFile(sys.argv[1]) as z:
                names=z.namelist();assert len(names)==len(set(names));result=run(z.read,names)
        else:
            with tarfile.open(sys.argv[1],'r:*') as t:
                members=t.getmembers();assert all(m.isfile() for m in members);names=[m.name for m in members];assert len(names)==len(set(names))
                payloads={m.name:t.extractfile(m).read() for m in members}
                result=run(lambda name:payloads[safe(name)],names)
    elif len(sys.argv)==1:
        root=pathlib.Path(__file__).resolve().parent;names=[p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()];result=run(lambda n:(root/safe(n)).read_bytes(),names)
    else:raise SystemExit('Usage: python verify_evidence.py [EVIDENCE_TAR_XZ_OR_ZIP]')
    print(json.dumps(result,indent=2))
