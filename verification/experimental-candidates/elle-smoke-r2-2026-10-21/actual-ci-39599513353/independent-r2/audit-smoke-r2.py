"""Independently read actual fixed-Elle evidence; never invoke either checker."""
from pathlib import Path
import collections
import hashlib
import itertools
import json
import re
import zipfile
import subprocess
import io
import tarfile
from datetime import datetime, timezone
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PRIOR=ROOT/'artifacts/elle-independent-actual-smoke-39599513353'
ACTUAL=ROOT/'artifacts/remote-ci-39599513353/extracted'
ZIP=ROOT/'artifacts/remote-ci-39599513353/downloads/artifact.zip'
BUNDLE=ROOT/'verification/experimental-candidates/elle-smoke-r2-2026-10-21'
checks=[]
def binding(path):
    h=hashlib.sha256();n=0
    with path.open('rb') as stream:
        while b:=stream.read(65536):n+=len(b);h.update(b)
    return {'bytes':n,'sha256':h.hexdigest()}
def sha(data):return hashlib.sha256(data).hexdigest()
def load(path):return json.loads(path.read_bytes())
def check(name,value):
    checks.append({'name':name,'passed':bool(value)})
    if not value:raise AssertionError(name)

class Invalid(ValueError):pass
class Outside(ValueError):pass

def require(value):
    if not value:raise Invalid('Original schema/domain violates fixed common profile')
def identity(value):
    require(type(value) is str and 0<len(value.encode('utf-16-le'))<=512 and
            all(ord(c)>=32 and ord(c)!=127 and not 0xd800<=ord(c)<=0xdfff for c in value))
    return value

def convert(trace):
    require(type(trace) is dict and set(trace)=={'traceSchema','dataModel','clockDomain','scope','events','gaps'})
    require(type(trace['traceSchema']) is int and trace['traceSchema']==3);identity(trace['clockDomain'])
    model=trace['dataModel']
    if model not in ('point-register-v1','append-list-v1'):raise Outside('model')
    require(type(trace['scope']) is dict and set(trace['scope'])=={'exclusiveWriters'})
    if trace['scope']['exclusiveWriters'] is not True or trace['gaps']!=[]:raise Outside('scope')
    events=trace['events'];require(type(events) is list and 1<=len(events)<=512)
    previous=-1
    for seq,e in enumerate(events,1):
        require(type(e) is dict and type(e.get('seq')) is int and e['seq']==seq)
        require(type(e.get('time')) is int and previous<=e['time']<=9007199254740991);previous=e['time']
    first=events[0];require(set(first)=={'seq','time','kind','initial','consistent'} and first['kind']=='snapshot')
    if first['consistent'] is not True:raise Outside('snapshot')
    initial=first['initial'];require(type(initial) is dict and len(initial)<=128)
    for key in initial:identity(key)
    sources={};writers=set()
    if model=='point-register-v1':
        for key,v in initial.items():identity(v);require(v not in sources);sources[v]=(key,None)
    else:
        require(all(type(a) is list for a in initial.values()))
        if any(initial.values()):raise Outside('nonemptyinitial')
    txs={};conn={};process={};ops=[];mapping=[];data=0
    for e in events[1:]:
        kind=e['kind']
        if kind not in ('begin','read','write','append','list_read','commit_request','commit_ok'):raise Outside('lifecycle')
        tx=identity(e.get('tx'))
        if kind=='begin':
            require(set(e)=={'seq','time','kind','tx','connection'});connection=identity(e['connection'])
            require(tx not in txs and connection not in conn)
            if len(txs)>=6:raise Outside('capacity')
            process.setdefault(connection,len(process));txs[tx]={'state':'active','connection':connection,'mops':[],'invoke':len(ops)};conn[connection]=tx
            ops.append({'index':len(ops),'process':process[connection],'type':'invoke','f':'txn','value':[]});mapping.append({'checkerIndex':len(ops)-1,'rawSeq':e['seq'],'tx':tx});continue
        require(tx in txs);t=txs[tx]
        if kind=='commit_request':require(set(e)=={'seq','time','kind','tx'} and t['state']=='active');t['state']='committing';continue
        if kind=='commit_ok':
            require(set(e)=={'seq','time','kind','tx'} and t['state']=='committing');t['state']='committed';conn.pop(t['connection'])
            ops[t['invoke']]['value']=[[f,k,None if f=='r' else v] for f,k,v in t['mops']]
            ops.append({'index':len(ops),'process':process[t['connection']],'type':'ok','f':'txn','value':t['mops']});mapping.append({'checkerIndex':len(ops)-1,'rawSeq':e['seq'],'tx':tx});continue
        require(t['state']=='active');key=identity(e.get('key'));data+=1
        if key not in initial or data>128:raise Outside('key/opcapacity')
        if model=='point-register-v1':
            require(kind in ('read','write'));require(set(e)=={'seq','time','kind','tx','key','version'}|({'predecessor'} if kind=='write' else set()));v=identity(e['version'])
            if kind=='write':
                pred=identity(e['predecessor']);require(v not in sources)
                if key in writers or pred!=initial[key]:raise Outside('writeorder')
                writers.add(key);sources[v]=(key,tx);mop=['w',key,v]
            else:
                if v not in sources or sources[v][0]!=key:raise Outside('readsource')
                mop=['r',key,None if v==initial[key] else v]
        else:
            require(kind in ('append','list_read'))
            if kind=='append':
                require(set(e)=={'seq','time','kind','tx','key','id','value'});v=identity(e['id']);require(type(e['value']) is str and v not in sources)
                sources[v]=(key,e['value']);mop=['append',key,v]
            else:
                require(set(e)=={'seq','time','kind','tx','key','items'} and type(e['items']) is list and len(e['items'])<=128);items=[]
                for item in e['items']:
                    require(type(item) is dict and set(item)=={'id','value'});v=identity(item['id']);require(type(item['value']) is str)
                    if sources.get(v)!=(key,item['value']):raise Outside('listsource')
                    items.append(v)
                mop=['r',key,items]
        t['mops'].append(mop)
    if any(t['state']!='committed' for t in txs.values()):raise Outside('outcome')
    return {'model':model,'operations':ops,'originalSeqMapping':mapping,'initialRegisterVersionRenaming':initial if model=='point-register-v1' else None}

def disposition(trace):
    try:return 'eligible',convert(trace)
    except Outside:return 'outside',None
    except (Invalid,KeyError,TypeError,UnicodeError):return 'invalid',None

class EDN:
    def __init__(self,text):self.text=text;self.at=0;self.nodes=0
    def white(self):
        while self.at<len(self.text) and self.text[self.at] in ' \t\r\n,':self.at+=1
    def value(self,depth=0):
        self.nodes+=1
        if depth>64 or self.nodes>65536:raise ValueError('Bounded EDN data only')
        self.white();s=self.text;c=s[self.at]
        if c=='"':v,n=json.JSONDecoder().raw_decode(s,self.at);self.at=n;return v
        if s.startswith('#{',self.at):
            self.at+=2;out=[]
            while True:
                self.white()
                if s[self.at]=='}':self.at+=1;return frozenset(out)
                out.append(self.value(depth+1))
        if c in '[({':
            self.at+=1;end={'[':']','(':')','{':'}'}[c];out=[]
            while True:
                self.white()
                if s[self.at]==end:self.at+=1;break
                out.append(self.value(depth+1))
            if c=='{':
                assert len(out)%2==0;d={}
                for k,v in zip(out[::2],out[1::2]):assert k not in d;d[k]=v
                return d
            return out
        stop=self.at
        while self.at<len(s) and s[self.at] not in ' \t\r\n,[](){}':self.at+=1
        token=s[stop:self.at]
        if token=='nil':return None
        if token=='true':return True
        if token=='false':return False
        if re.fullmatch('-?[0-9]+',token):return int(token)
        if token.startswith(':'):return token
        raise ValueError('Unsupported EDN symbol '+token)
    def parse(self):
        v=self.value();self.white();assert self.at==len(self.text);return v

def serial_programs(trace):
    txs={}
    for e in trace['events']:
        if e['kind']=='begin':txs[e['tx']]=[]
        elif e['kind'] in ('read','write','append','list_read'):txs[e['tx']].append(e)
    return txs

def replays(trace,order):
    programs=serial_programs(trace)
    if len(order)!=len(programs) or set(order)!=set(programs):return False
    state=json.loads(json.dumps(trace['events'][0]['initial']))
    for tx in order:
        for e in programs[tx]:
            kind=e['kind'];key=e['key']
            if kind=='read' and state[key]!=e['version']:return False
            if kind=='write':state[key]=e['version']
            if kind=='append':state[key].append({'id':e['id'],'value':e['value']})
            if kind=='list_read' and state[key]!=e['items']:return False
    return True

result={'schema':1,'kind':'independent-AI-actual-fixed-Elle-smoke-review-r2','run':39599513353,
        'reviewer':'/root/elle_acceptance','reviewedAt':datetime.now(timezone.utc).isoformat(),
        'priorPartialReceipt':binding(PRIOR/'independent-smoke-receipt.json'),
        'priorAuditSource':binding(PRIOR/'audit-smoke.py'),
        'priorVerifierCorrection':'Identity-domain success label valid was incorrectly compared as eligible in the prior reviewer; no fixture, input, expected result or author evidence was changed.',
        'passed':False,'complete':False,'scope':'Frozen15 original inputs /8 common serializable histories; experiment only',
        'checks':checks,'cases':[],'localJVMNodeCompileDBExecuted':False,'sixModelParity':False,'stableReleaseAccepted':False,
        'comparedToolSource':'b6638ee56395a14284d1440a92a0d975c4ea4073f42ccab6d8d39e359d928096',
        'newEc35MainlineAcceptedByThisSmoke':False,'expansion2000GeneratedOrExecuted':False,
        'independentDependencyBinaryBytesRehashed':False,
        'dependencyLimit':'141 resolved JAR/POM SHA/size metadata and real dependency-tree/version logs audited; binary dependency payloads are not in this small artifact.'}
try:
    run=load(PRIOR/'run.json');metadata=load(PRIOR/'artifacts.json')['artifacts'][0];jobs=load(PRIOR/'jobs.json')['jobs']
    check('Actual GitHub run/head/job and ZIP digest',run['conclusion']=='success' and run['head_sha']=='eb6727eafd330c5b4dad8381e15a3576d97d3f6d' and
          len(jobs)==1 and jobs[0]['conclusion']=='success' and metadata['digest']=='sha256:'+binding(ZIP)['sha256'] and metadata['size_in_bytes']==binding(ZIP)['bytes'])
    with zipfile.ZipFile(ZIP) as archive:
        names=[i for i in archive.infolist() if not i.is_dir()];assert len({i.filename for i in names})==len(names)==42
        for info in names:
            assert not Path(info.filename).is_absolute() and '..' not in Path(info.filename).parts
            h=hashlib.sha256();n=0
            with archive.open(info) as stream:
                while data:=stream.read(65536):h.update(data);n+=len(data)
            assert binding(ACTUAL/info.filename)=={'bytes':n,'sha256':h.hexdigest()}
    check('All42 extracted actual evidence files equal official ZIP bytes',True)
    execution=load(ACTUAL/'execution-receipt.json');original=load(ACTUAL/'original-inputs.json');adapter=load(ACTUAL/'prepared/adapter-receipt.json')
    requests=load(ACTUAL/'prepared/requests.json');elle=load(ACTUAL/'elle-result.json');comparison=load(ACTUAL/'comparison-first.json')
    check('Original raw15 and expectations unchanged from preregistration',binding(ACTUAL/'original-inputs.json')==binding(BUNDLE/'smoke-inputs-v1.json') and
          binding(ACTUAL/'original-inputs.json')['sha256']=='e9430dbf5faca86c337fca8a090464004a362370c6e134f710a344f5b8ef8d90' and len(original['cases'])==15)
    # Rebind immutable official metadata already independently downloaded by prior reviewer.
    api_binding=load(PRIOR/'independent-api-binding.json')
    check('Independent raw API run/artifact/job identity fields match exact completed run',
          run['id']==39599513353 and run['repository']['full_name']=='HhWw96/moontxnwitness' and
          run['path']=='.github/workflows/experimental-elle-smoke.yml' and run['status']=='completed' and
          run['event']=='workflow_dispatch' and run['run_attempt']==1 and
          metadata['id']==12345523067 and metadata['name']=='actual-fixed-elle-first-smoke' and not metadata['expired'] and
          metadata['workflow_run']['id']==run['id'] and metadata['workflow_run']['head_sha']==run['head_sha'] and
          jobs[0]['run_id']==run['id'] and jobs[0]['head_sha']==run['head_sha'] and jobs[0]['id']==119220142921 and
          jobs[0]['labels']==['ubuntu-24.04'] and all(x['status']=='completed' and x['conclusion']=='success' for x in jobs[0]['steps']))
    check('Previously independently downloaded API digest and actual ZIP bytes match recomputation',
          api_binding['complete'] is True and api_binding['headSha']==run['head_sha'] and
          api_binding['githubArtifact']['digest']==metadata['digest'] and api_binding['localActualZip']==binding(ZIP) and
          binding(ZIP)=={'bytes':394194,'sha256':'213998d2b7209fe5068b2fd0d6971bacc9471f103f7a0857a251753f1a7c3517'})
    check('Independent and author downloads contain identical immutable API raw documents and job log bytes',
          all(binding(PRIOR/n)==binding(ROOT/'artifacts/remote-ci-39599513353/downloads'/n)
              for n in ['run.json','artifacts.json','jobs.json','job-119220142921.log']))
    index=load(BUNDLE/'candidate-index-static-v2.json')
    check('Frozen candidate index and additive execution amendment bytes unchanged',
          binding(BUNDLE/'candidate-index-static-v2.json')['sha256']=='79181c62e4499b14a420810758d68c31df70d93bd3f950692f71c9b1ca0acf80' and
          binding(BUNDLE/'execution-profile-amendment.json')['sha256']=='947c79d7e875b376aa3099f64b8b8afeb68b988d21c11e5cfbd52bf6047f5d81')
    check('All39 fixed candidate file sizes and SHA256 match actual CI candidate bindings',
          len(index['files'])==index['fileCount']==39 and sum(v['bytes'] for v in index['files'].values())==index['totalBytes']==564987 and
          index['files']==execution['candidateFiles'] and all(binding(BUNDLE/n)==v for n,v in index['files'].items()))
    pins=load(BUNDLE/'source-pins.json')
    check('All9 official original raw downloads rehashed against frozen source pins and actual checkout metadata',
          pins['fixedCommit']=='4e359e597c52938b0afebb8bc42273914d68a424' and len(pins['files'])==9 and
          pins['files']==execution['actualUpstreamSources'] and sum(v['bytes'] for v in pins['files'].values())==349893 and
          all(binding(PRIOR/'official-upstream-sources'/n)==v for n,v in pins['files'].items()))
    check('Retain anonymous upstream API403 failure without converting it into source success',
          load(PRIOR/'upstream-tree-first-network-failure.json')['status']==403 and
          load(PRIOR/'upstream-tree-first-network-failure.json')['complete'] is False and
          api_binding['authenticatedRequestsToRawSourceHost'] is False and api_binding['tokenPersisted'] is False and api_binding['signedUrlPersisted'] is False)
    for stage in execution['stages']:assert stage['exitCode']==0 and stage['status']=='passed' and binding(ACTUAL/stage['log'])==stage['logBinding']
    check('Actual17 stage logs independently rebound, not only passed flags',len(execution['stages'])==17)
    for name,pin in execution['actualUpstreamSources'].items():
        check('Official fixed4e source pin '+name,binding(PRIOR/'official-upstream-sources'/name)==pin==binding(BUNDLE/'primary-references'/name))
    check('All9 official source pins and actual upstream commit fixed',len(execution['actualUpstreamSources'])==9 and
          (ACTUAL/'identify-fixed-upstream.log').read_text().strip()=='4e359e597c52938b0afebb8bc42273914d68a424')
    check('Exact actual Java21 /Clojure1.12.6 /Lein2.11.2 and additive +dev profile',
          'openjdk version "21.0.12.1"' in (ACTUAL/'actual-java-version.log').read_text() and
          'Leiningen 2.11.2 on Java 21.0.12.1' in (ACTUAL/'actual-lein-version.log').read_text() and
          execution['actualLeinProfile']=='+dev' and execution['executionAmendment']['sha256']=='947c79d7e875b376aa3099f64b8b8afeb68b988d21c11e5cfbd52bf6047f5d81' and
          all(c['java']=='21.0.12.1' and c['clojure']=='1.12.6' for c in elle['cases']))
    deps=execution['actualRuntimeDependencyBindings'];tree=(ACTUAL/'actual-dependency-tree.log').read_text()
    check('Resolved dependency inventory includes141 real recorded bindings/50JAR/91POM',len(deps)==141 and sum(x.endswith('.jar') for x in deps)==50 and
          sum(x.endswith('.pom') for x in deps)==91 and all(re.fullmatch('[0-9a-f]{64}',v['sha256']) and v['bytes']>0 for v in deps.values()))
    primary={'org.clj-commons/slingshot':'0.13.0','org.clojure/clojure':'1.12.6','dom-top':'1.0.11','hiccup':'2.0.0',
             'org.clojure/tools.logging':'1.3.1','rhizome':'0.2.9','io.jepsen/history':'0.1.9','io.jepsen/generator':'0.1.6','jepsen.txn':'0.1.3'}
    check('All9 frozen direct upstream deps and required unilog +dev found in actual tree',all('['+k+' "'+v+'"' in tree for k,v in primary.items()) and '[spootnik/unilog "0.7.32"' in tree)
    check('Actual Clojure and standalone JAR hash metadata exact',deps['runtime-home/.m2/repository/org/clojure/clojure/1.12.6/clojure-1.12.6.jar']['sha256']=='21b578db389a8e74b286ce79c4a7f86ec641e26d88b12f18d69030916b0e18ca' and
          execution['actualLeinStandaloneBinding']['sha256']=='7d31ae23ae769e927438b0cd55d15a93e7dabab09fd4fc15877979161e108774')
    for name,pin in execution['actualSdkBindings'].items():check('Actual SDK byte payload '+name,binding(ACTUAL/'actual-sdk'/name)==pin)
    build=load(ACTUAL/'actual-sdk/build-manifest.json')
    check('Actual6file SDK is fixed7863550/b663 and previously independently verified Linux core bytes',len(execution['actualSdkBindings'])==6 and
          execution['comparedSdkCommit']=='78635505e4c189c402ba70600632aeaef71ef206' and
          (ACTUAL/'identify-fixed-sdk.log').read_text().strip()==execution['comparedSdkCommit'] and build['sourceSha256']==result['comparedToolSource'] and
          build['coreSha256']=='91ab0675e06e7f468692df0cb40bca250b2971c3f19c9d8fd8968448bc70d447' and
          build['captureCoreSha256']=='8807017be4619f6e7d062d9d503815494ab8e83cd15474573d91d53b77de1b10' and comparison['actualBuildManifest']==build)
    check('Actual licenses retained without relabeling',binding(ACTUAL/'ELLE-UPSTREAM-LICENSE')==binding(PRIOR/'official-upstream-sources/LICENSE') and
          binding(ACTUAL/'LEININGEN-UPSTREAM-COPYING')==binding(BUNDLE/'primary-references/LEININGEN-COPYING'))
    check('Raw checker input EDN hash binds actual checker/output',binding(ACTUAL/'prepared/requests.edn')['sha256']==elle['inputEdnSha256'])
    request_edn=[EDN(line).parse() for line in (ACTUAL/'prepared/requests.edn').read_text().splitlines()]
    check('All8 EDN transport values exactly equal original converted JSON',request_edn==requests and len(requests)==8)
    request_map={x['id']:x for x in requests};adapter_map={x['id']:x for x in adapter['cases']};elle_map={x['id']:x for x in elle['cases']};comparison_map={x['id']:x for x in comparison['cases']}
    counts=collections.Counter();validity=collections.Counter();completed=0
    for case in original['cases']:
        name=case['id'];disp,converted=disposition(case['input']);a=adapter_map[name];c=comparison_map[name]
        check(name+': independent raw-domain disposition matches original manual expectation and actual adapter',disp==case['expected']['adapter']==a['disposition']==c['disposition'])
        counts[disp]+=1
        if disp!='eligible':
            assert name not in request_map and name not in elle_map and c['checkerExecuted'] is False
            result['cases'].append({'id':name,'disposition':disp,'actualDualCheck':False});continue
        request=request_map[name]
        check(name+': original events independently produce identical invoke/ok, nil/source IDs and mappings',request=={'id':name,**converted,'expectedElleValid':case['expected']['elleValid']} and a['converted']==converted)
        upstream=elle_map[name];raw=EDN((ACTUAL/'elle-raw-results'/upstream['rawResultFile']).read_text()).parse()
        raw_valid='unknown' if raw[':valid?']==':unknown' else raw[':valid?']
        anomalies=[x[1:] for x in raw.get(':anomaly-types',[])]
        check(name+': actual raw EDN validity/anomalies matches raw JSON and frozen expectation',raw_valid==upstream['valid']==case['expected']['elleValid'] and
              anomalies==upstream['anomalyTypes'] and 'cycle-search-timeout' not in anomalies and c['actualElleResult']==raw_valid)
        status=c['actualMoonBitStatus'];report=c['report'];trace=case['input'];programs=serial_programs(trace)
        possible=next((order for order in itertools.permutations(programs) if replays(trace,order)),None)
        check(name+': independent original-program exhaustive serial replay agrees with tool/frozen status',status==case['expected']['toolStatus'] and
              ((status=='consistent')==(possible is not None)) and report['normalized']['observations']==trace['events'])
        if status=='consistent':check(name+': actual returned serial witness independently replays original complete programs',replays(trace,report['evidence']['serialOrder']))
        if trace['dataModel']=='point-register-v1':
            flat=report['normalized']['history'];orders={key:[v] for key,v in trace['events'][0]['initial'].items()}
            for event in trace['events']:
                if event['kind']=='write':orders[event['key']].append(event['version'])
            check(name+': point projection contains no ACK times or search-created version-order facts',flat['versionOrders']==orders and all(t['start'] is None and t['end'] is None for t in flat['transactions']) and
                  all(edge['kind'] in ('wr','rw','ww') for edge in report['evidence']['edges']))
        if raw_valid is False:
            if 'duplicate-elements' in anomalies:
                for finding in raw[':anomalies'][':duplicate-elements']:
                    op=finding[':op'];actual_op=converted['operations'][op[':index']]
                    mops=[[x[0][1:],x[1],x[2]] for x in op[':value']]
                    assert op[':type']==':ok' and actual_op['value']==mops
                    mop=finding[':mop'];assert dict(collections.Counter(mop[2]))==finding[':duplicates']
            else:
                for anomaly in raw[':anomalies'].values():
                    for witness in anomaly:
                        cycle=witness[':cycle'];steps=witness[':steps'];assert cycle[0]==cycle[-1] and len(steps)==len(cycle)-1
                        for op in cycle:
                            original_op=converted['operations'][op[':index']]
                            assert original_op['type']=='ok' and op[':time']==-1 and op[':process']==original_op['process'] and [[m[0][1:],m[1],m[2]] for m in op[':value']]==original_op['value']
                        for left,right,step in zip(cycle,cycle[1:],steps):
                            a=left[':value'][step[':a-mop-index']];b=right[':value'][step[':b-mop-index']];assert a[1]==b[1]==step[':key']
                            if step[':type']==':wr':assert a[0] in (':w',':append') and b[0]==':r' and (a[2]==b[2] if a[0]==':w' else a[2] in b[2]) and a[2]==step[':value']
                            elif step[':type']==':rw':assert a[0]==':r' and a[2] is None and b[0]==':w' and step[':value'] is None and step[":value'"]==b[2]
                            else:raise AssertionError('Unexpected shared-profile witness relation')
            check(name+': every actual negative EDN witness binds real original completion/mop/source facts',True)
        if raw_valid=='unknown':assert anomalies==['empty-transaction-graph'] and raw[':anomalies']=={':empty-transaction-graph':True} and status=='consistent'
        validity[str(raw_valid).lower()]+=1;completed+=1
        result['cases'].append({'id':name,'disposition':'eligible','actualElleValid':raw_valid,'actualAnomalies':anomalies,'actualToolStatus':status,
             'independentSerialExecutionExists':possible is not None,'unknownIsCoverageDifferenceNotAgreement':raw_valid=='unknown',
             'originalInputSha256':sha(json.dumps(trace,sort_keys=True,ensure_ascii=True,separators=(',',':')).encode()),'rawEDN':binding(ACTUAL/'elle-raw-results'/upstream['rawResultFile'])})
    check('Exactly8 dual checks,5outside2invalid,2true4false2unknown accounted without dropping',counts=={'eligible':8,'outside':5,'invalid':2} and validity=={'true':2,'false':4,'unknown':2} and completed==8)
    boundaries=load(ACTUAL/'identity-boundaries.json');fixtures=load(BUNDLE/'identity-boundaries-v2.json');actual_boundary={c['id']:c for c in boundaries['cases']}
    for case in fixtures['identityCases']:
        try:identity(case['value']);outcome='valid'
        except (Invalid,UnicodeError):outcome='invalid'
        assert actual_boundary[case['id']]['actual']==case['expected']==outcome
    for case in fixtures['traceCases']:assert disposition(case['input'])[0]==case['expected']==actual_boundary[case['id']]['actual']
    check('All69 actual adapter domain outcomes independently checked against original raw boundary values',len(actual_boundary)==69 and boundaries['checks']==69 and boundaries['fixtureSha256']==binding(BUNDLE/'identity-boundaries-v2.json')['sha256'])
    check('Actual frozen checker options still explicit serializable and no RT/SO/order inference',elle['automaticAdditionalGraphCount']==0 and
          binding(BUNDLE/'elle_smoke.clj')['sha256']==execution['candidateFiles']['elle_smoke.clj']['sha256'] and
          ':consistency-models [:serializable]' in (BUNDLE/'elle_smoke.clj').read_text() and
          ':linearizable-keys? false' in (BUNDLE/'elle_smoke.clj').read_text() and ':sequential-keys? false' in (BUNDLE/'elle_smoke.clj').read_text() and
          ':wfr-keys? false' in (BUNDLE/'elle_smoke.clj').read_text() and ':transaction-order' not in (BUNDLE/'elle_smoke.clj').read_text())
    check('SDK manifest/core/capture/entry bytes and complete15 comparison bindings agree',
          binding(ACTUAL/'actual-sdk/core.mjs')['sha256']==build['coreSha256']==comparison['actualCoreSha256'] and
          binding(ACTUAL/'actual-sdk/capture-core.mjs')['sha256']==build['captureCoreSha256']==comparison['actualCaptureCoreSha256'] and
          binding(ACTUAL/'actual-sdk/sdk.mjs')['sha256']==comparison['sdkFileSha256'] and
          binding(ACTUAL/'comparison-first.json')==execution['actualComparisonBinding'] and
          binding(ACTUAL/'elle-result.json')['sha256']==comparison['elleResultSha256'] and
          len(comparison_map)==15 and len(elle_map)==8 and len(request_map)==8 and len(adapter_map)==15 and
          all(c.get('report',{}).get('status')==c['actualMoonBitStatus'] and c.get('verification',{}).get('valid') is True
              and c['knownCoverageDifference']==(c['actualElleResult']=='unknown') for c in comparison['cases'] if c['disposition']=='eligible'))
    # Read-only git objects: no checkout, build, compiler or checker invocation.
    def git_read(args,maximum):
        p=subprocess.run(['git','--no-optional-locks',*args],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,check=True)
        assert len(p.stdout)<=maximum and len(p.stderr)<=65536
        return p.stdout
    def committed_source_fingerprint(commit):
        tree=git_read(['ls-tree','-r','-l',commit,'--','moon.mod','src'],262144).decode().splitlines()
        selected=[];total=0
        for row in tree:
            meta,name=row.split('\t',1);mode,kind,oid,size=meta.split()
            if name=='moon.mod' or name.endswith('.mbt') or name.endswith('/moon.pkg'):
                assert mode=='100644' and kind=='blob';total+=int(size);selected.append(name)
        assert 1<len(selected)<512 and total<8*1024*1024
        raw=git_read(['archive','--format=tar',commit,'--','moon.mod','src'],12*1024*1024)
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            payloads={m.name:archive.extractfile(m).read() for m in archive.getmembers() if m.isfile() and m.name in selected}
        assert set(payloads)==set(selected)
        digest=hashlib.sha256()
        for name in sorted(selected):digest.update(name.encode()+b'\0'+payloads[name]+b'\0')
        return {'fingerprint':digest.hexdigest(),'sourceFiles':len(selected),'sourceBytes':total}
    sdkfp=committed_source_fingerprint('78635505e4c189c402ba70600632aeaef71ef206')
    workflowfp=committed_source_fingerprint(run['head_sha'])
    check('Authoritative fixed7863550 and workflow Git source objects independently reproduce b663 fingerprint',
          sdkfp['fingerprint']==workflowfp['fingerprint']==execution['workflowSourceSha256']==execution['sourceSha256']==build['sourceSha256']==result['comparedToolSource'])
    wrapper=git_read(['show',run['head_sha']+':scripts/experimental_elle_smoke_ci.py'],65536).decode()
    helper=git_read(['show',run['head_sha']+':scripts/experimental_orm_ci.py'],65536).decode()
    check('Actual committed wrapper verifies source baseline before and after plus additive Xvfb +dev execution',
          'workflow_source_before = fingerprint(ROOT)' in wrapper and 'assert fingerprint(sdk_source) == SOURCE_BASELINE' in wrapper and
          'fingerprint(ROOT) == workflow_source_before' in wrapper and 'fingerprint(sdk_source) == SOURCE_BASELINE' in wrapper and
          'result["passed"] = result["passed"] and result["sourceBindingsUnchanged"]' in wrapper and
          '"with-profile", "+dev", "run"' in wrapper and '[xvfb, "-a"' in wrapper and
          'env.pop("PYTHONPATH", None)' in wrapper and 'HOME=str(owned_home)' in wrapper and
          execution['sourceBindingsUnchanged'] is True and execution['comparedSdkSourceUnchanged'] is True and
          'hashed.update(name.encode() + b"\\0")' in helper)
    for number,run_id,head,signature,zipsha in [
       (1,39595030624,'7e8728a5294f8e05b001eb53a5cdb52e9225bab5','HeadlessException','42ae938471725cca5bd921aa744a71aa6c7a94a10912db934708a1c21ec2d2ce'),
       (2,39596518361,'3a395bb9f788c536b774fe3dec4847aeb87e27c5','Could not locate unilog/config','b1dc7e413b189c631feec1330bee9c2daf29c4355ca78329400f5c64f3bbdb24')]:
        folder=BUNDLE/('first-ci-'+str(run_id) if number==1 else 'second-ci-'+str(run_id))
        oldrun=load(folder/'run.json');oldart=load(folder/'artifacts.json')['artifacts'][0];oldexec=load(folder/'execution-receipt.json')
        with zipfile.ZipFile(folder/'artifact.zip') as archive:
            oldlog=archive.read('actual-elle-checkers.log').decode()
            assert signature.lower() in oldlog.lower() and 'elle-result.json' not in archive.namelist() and not any(n.startswith('elle-raw-results/') for n in archive.namelist())
            assert archive.read('execution-receipt.json')==(folder/'execution-receipt.json').read_bytes()
            assert archive.read('original-inputs.json')==(BUNDLE/'smoke-inputs-v1.json').read_bytes()
            assert load(folder/'execution-receipt.json')['candidateFiles']==index['files']
        check('Retained setup failure '+str(run_id)+' exact ZIP digest/input/head/error and zero checker results',
              oldrun['id']==run_id and oldrun['head_sha']==head and oldrun['conclusion']=='failure' and oldexec['passed'] is False and
              oldexec['candidateIndexSha256']==execution['candidateIndexSha256'] and
              binding(folder/'artifact.zip')['sha256']==zipsha and oldart['digest']=='sha256:'+zipsha)
    check('Original direct unilog load failure corroborated by complete second exception and exact official dev profile',
          'unilog/config' in (BUNDLE/'second-ci-39596518361/jvm-temp/clojure-830575053980772772.edn').read_text() and
          '[unilog.config' in (PRIOR/'official-upstream-sources/src/elle/txn.clj').read_text() and
          'spootnik/unilog "0.7.32"' in (PRIOR/'official-upstream-sources/project.clj').read_text())
    result.update(sourceFingerprints={'fixedSdk':sdkfp,'workflowCommit':workflowfp},
                  auditSource=binding(HERE/'audit-smoke-r2.py'),reusedOfficialApiDocuments={n:binding(PRIOR/n) for n in ['run.json','jobs.json','artifacts.json','job-119220142921.log','independent-api-binding.json']},
                  freshNetworkRequestsPerformedByThisReviewer=False,officialRawSourceFilesRehashed=9,officialRawSourceBytesRehashed=349893,
                  originalSetupFailuresRetained=[39595030624,39596518361],
                  localGitObjectReadsOnly=True,allReportsFullBytesBound=True,localSdkVerifierExecuted=False,
                  evidenceLimit='Full reports and CI verifier outputs are preserved and byte-bound; this independent local reviewer exhaustively replayed original committed programs and checked raw negative witnesses, but did not locally execute SDK/JVM or rederive every report field.',
                  expansionGenerationGate='smoke-prerequisite-accepted-only; a separate1000+1000 preregistration/freeze and independently validated expansion remain required')
    result.update(passed=True,complete=True,artifact=binding(ZIP),actualWorkflowHead=run['head_sha'],actualCheckerInputs=8,adapterOnlyOutside=5,adapterOnlyInvalid=2,
                  actualValidityCounts=dict(validity),booleanAgreementCases=6,unknownCoverageDifferences=2,independentAIReview=True,
                  independentHumanReview=False,upstreamSourcesIndependentlyDownloaded=9,originalNegativeResultsPreserved=True,
                  executionReceipt=binding(ACTUAL/'execution-receipt.json'),actualComparison=binding(ACTUAL/'comparison-first.json'),
                  actualElleResult=binding(ACTUAL/'elle-result.json'),dependencyInventory={'records':141,'jars':50,'poms':91,'profile':'+dev'})
except Exception as error:result.update(errorClass=type(error).__name__,error=str(error).replace(str(ROOT),'<repository>'))
result['checksCount']=len(checks)
p=HERE/'independent-smoke-receipt-r2.json';p.open('x',encoding='utf-8',newline='\n').write(json.dumps(result,indent=2)+'\n')
print(json.dumps({'passed':result['passed'],'checks':len(checks),'receiptSha256':binding(p)['sha256']}))
raise SystemExit(0 if result['passed'] else 1)
