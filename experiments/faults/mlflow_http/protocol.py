"""Pure protocol for original MLflow HTTP execution-fault experiments.
No DB, server, MLflow import, or invented transaction/model evidence here.
"""
from __future__ import annotations
import hashlib,json,os,random,re,stat,threading
from pathlib import Path

COMMITS={'before':'c2dcdb96c62c75f35af3f28b5d493c0cf139a856','fixed':'40c146a23518813e8488e55fc9752e08c3a8bad5'}
SEEDS=tuple(0x4D545700+i for i in range(30))
ROUTE='/api/2.0/mlflow/runs/log-batch'
STRATEGY='native-latest-metrics-first-lock-v1'
PREDICATE='original-http-native-40P01-three-repetitions-v1'
MAX_CHECKS=256

def encoded(value):return (json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode('utf-8')
def digest(raw):return hashlib.sha256(raw).hexdigest()
def file_digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def ordinary(path):
    p=Path(path).absolute()
    for q in [p,*p.parents]:
        if q.exists() and getattr(q.lstat(),'st_file_attributes',0)&0x400:raise ValueError('Reparse path refused')
        if q.is_symlink():raise ValueError('Symlink path refused')
    return p

def save_new(path,value,raw=False):
    path=ordinary(path);path.parent.mkdir(parents=True,exist_ok=True)
    b=value if raw else encoded(value)
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    if file_digest(path)!=digest(b):raise OSError('Evidence read-back differs')
    return {'path':str(path),'bytes':len(b),'sha256':digest(b)}

def new_directory(path):
    p=ordinary(path);p.mkdir(parents=True,exist_ok=False);return p

import math

LOG_FILES={"sql":"sql.jsonl","http":"http.jsonl","schedule":"schedule.jsonl","calls":"native-calls.jsonl"}
REQUIRED_ARTIFACTS={"native-route.json","final-rows.json","final-native-http-run.json","capture.json"}
MAX_ARTIFACT_FILES=2048
MAX_ARTIFACT_BYTES=128*1024*1024


def strict_json(raw):
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:raise ValueError('Duplicate JSON field')
            value[key]=item
        return value
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda value:(_ for _ in ()).throw(ValueError('Nonfinite JSON value')))

def read_json(path,maximum=8*1024*1024):
    with ordinary(path).open('rb') as stream:raw=stream.read(maximum+1)
    if len(raw)>maximum:raise ValueError('JSON evidence over budget')
    return strict_json(raw.decode('utf8'))

def relative_file(root,name):
    if not isinstance(name,str) or not name or '\\' in name or ':' in name or name.startswith('/') or any(part in ('','.','..') for part in name.split('/')):raise ValueError('Unsafe relative evidence path')
    root=ordinary(root).resolve();path=ordinary(root/name)
    if not path.resolve().is_relative_to(root):raise ValueError('Evidence path escaped its directory')
    return path

class Log:
    """Bounded append-only observations; an acknowledged append is not durable close."""
    def __init__(self,path,*,max_bytes=32*1024*1024,max_record=512*1024):
        if type(max_bytes) is not int or not 4096<=max_bytes<=32*1024*1024 or type(max_record) is not int or not 128<=max_record<=min(512*1024,max_bytes-2048):raise ValueError('Invalid observation log budget')
        self.path=ordinary(path);self.file=self.path.open('xb');self.lock=threading.RLock()
        self.size=0;self.count=0;self.hash=hashlib.sha256();self.failed=False;self.closed=False
        self.max_bytes=max_bytes;self.max_record=max_record
    def append(self,item):
        with self.lock:
            try:
                if self.closed or self.failed or not isinstance(item,dict):raise ValueError('Observation log not writable')
                if 'seq' in item or item.get('kind')=='seal':raise ValueError('Caller may not set sequence or seal')
                raw=encoded({'seq':self.count+1,**item})
                if len(raw)>self.max_record or self.size+len(raw)>self.max_bytes-2048:raise ValueError('Observation budget exhausted')
                if self.file.write(raw)!=len(raw):raise OSError('Short observation write')
                self.count+=1;self.size+=len(raw);self.hash.update(raw);return True
            except Exception:self.failed=True;return False
    def close(self):
        with self.lock:
            if not self.closed:
                seal=encoded({'seq':self.count+1,'kind':'seal','records':self.count,'prefixSha256':self.hash.hexdigest(),'complete':not self.failed})
                try:
                    if self.size+len(seal)>self.max_bytes:raise ValueError('Seal exceeded observation budget')
                    if self.file.write(seal)!=len(seal):raise OSError('Short seal write')
                    self.file.flush();os.fsync(self.file.fileno())
                except Exception:self.failed=True
                finally:self.closed=True;self.file.close()
            return {'sealed':not self.failed,'records':self.count,'bytes':self.path.stat().st_size,'sha256':file_digest(self.path)}

def read_log(path,maximum=32*1024*1024):
    if type(maximum) is not int or not 0<maximum<=32*1024*1024:raise ValueError('Invalid observation read budget')
    with ordinary(path).open('rb') as stream:raw=stream.read(maximum+1)
    if len(raw)>maximum:raise ValueError('Observation log over budget')
    lines=raw.splitlines(keepends=True)
    if not lines or any(not line.endswith(b'\n') or len(line)>512*1024 for line in lines):raise ValueError('Truncated or oversized observation record')
    rows=[strict_json(line.decode('utf8')) for line in lines];seal=rows[-1]
    if any(not isinstance(row,dict) or type(row.get('seq')) is not int or row['seq']!=i for i,row in enumerate(rows,1)):raise ValueError('Observation sequence differs')
    if set(seal)!={'seq','kind','records','prefixSha256','complete'} or seal['kind']!='seal' or type(seal['records']) is not int or seal['records']!=len(rows)-1 or seal['prefixSha256']!=digest(b''.join(lines[:-1])) or seal['complete'] is not True or any(row.get('kind')=='seal' for row in rows[:-1]):raise ValueError('Unsealed, incomplete or altered observations')
    return rows[:-1]

def workload(seed,keys=None,workers=('A','B')):
    if type(seed) is not int or seed not in SEEDS:raise ValueError('Seed must be preregistered')
    if list(workers) not in [['A','B'],['A'],['B']]:raise ValueError('Only original request subsequences are accepted')
    a=[f'a{i:04d}' for i in range(500)];b=[f'b{i:04d}' for i in range(500)]
    rng=random.Random(seed);rng.shuffle(a);rng.shuffle(b)
    original=a+b
    selected=set(original if keys is None else keys)
    if keys is not None and (not isinstance(keys,list) or len(keys)!=len(selected) or not selected.issubset(original)):raise ValueError('Reduction must only delete original metric keys')
    orders={'A':[k for k in a+b if k in selected],'B':[k for k in b+a if k in selected]}
    templates={w:{'metrics':[{'key':k,'value':1.0 if w=='A' else 2.0,'timestamp':seed*10+(1 if w=='A' else 2),'step':1 if w=='A' else 2} for k in orders[w]],'params':[],'tags':[]} for w in workers}
    return {'format':'moontxnwitness-mlflow-http-workload/v1','seed':seed,'strategy':STRATEGY,'route':ROUTE,'workers':list(workers),'keys':[k for k in original if k in selected],'requests':templates,'clientRetries':0,'upstreamLockBatchSizeUnchanged':500,'businessSourceModified':False}


def request_body(case,worker,run_id):
    if worker not in case['workers'] or not re.fullmatch(r'[a-fA-F0-9]{32}',run_id):raise ValueError('Invalid native run identity or worker')
    return {'run_id':run_id,**case['requests'][worker]}


def is_lock(statement):
    return isinstance(statement,str) and bool(re.search(r'\blatest_metrics\b',statement,re.I)) and bool(re.search(r'\bFOR\s+UPDATE\b',statement,re.I))



def classify(case,meta,http,sql,final_rows):
    responses=[r for r in http if r.get('kind')=='response' and r.get('worker') in case['workers'] and r.get('path')==ROUTE]
    native=[r for r in sql if r.get('phase')=='error' and r.get('worker') in case['workers'] and r.get('targetLock') is True and is_lock(r.get('sql')) and r.get('sqlstate')=='40P01' and r.get('diagSqlstate')=='40P01' and r.get('nativePgResult') is True and (r.get('exceptionModule')=='psycopg' or str(r.get('exceptionModule','')).startswith('psycopg.'))]
    failures={r['worker'] for r in responses if type(r.get('status')) is int and 500<=r['status']<600}
    matched=[r for r in native if r['worker'] in failures]
    full=(meta.get('actualHttpExecution') is True and meta.get('actualDatabaseExecution') is True and meta.get('nativeRouteVerified') is True and meta.get('sourceUnchanged') is True and meta.get('collectionComplete') is True and meta.get('controllerComplete') is True and meta.get('serviceStopped') is True and meta.get('caseError') is None and not meta.get('threadsStillAlive') and len(responses)==len(case['workers']) and {r['worker'] for r in responses}==set(case['workers']) and all(type(r.get('status')) is int and 100<=r['status']<=599 for r in responses) and all(isinstance(r,(list,tuple)) and len(r)==4 for r in final_rows) and {r[0] for r in final_rows}==set(case['keys']) and len(final_rows)==len(case['keys']))
    fault=bool(matched)
    return {'format':'moontxnwitness-mlflow-http-fault-result/v1','executionComplete':bool(full),'nativeTargetDeadlocks':len(native),'failedHttpWorkers':sorted(failures),'unrecoveredNativeDeadlockWorkers':sorted({r['worker'] for r in matched}),'recoveredDeadlockWorkers':sorted({r['worker'] for r in native}-failures),'faultPredicate':bool(full and fault),'predicateDisposition':'reproduced' if full and fault else 'not-reproduced' if full else 'unknown','httpStatusByWorker':{r['worker']:r['status'] for r in responses},'executionFault':'deadlock' if native else None,'isolationViolationClaim':False,'G2Claim':False,'semanticTransactionHistorySynthesized':False}

def fixed_behavior(case,http,final_rows,final_http):
    responses=[r for r in http if r.get('kind')=='response' and r.get('worker') in case['workers'] and r.get('path')==ROUTE]
    if len(responses)!=len(case['workers']) or {r['worker'] for r in responses}!=set(case['workers']) or any(r.get('status')!=200 for r in responses):return False
    expected={}
    for worker in case['workers']:
        for metric in case['requests'][worker]['metrics']:
            value=(metric['value'],metric['step'],metric['timestamp']);previous=expected.get(metric['key'])
            if previous is None or (value[1],value[2],value[0])>(previous[1],previous[2],previous[0]):expected[metric['key']]=value
    def table(records):
        result={}
        for key,value,step,timestamp in records:
            if not isinstance(key,str) or key in result or type(value) not in (int,float) or not math.isfinite(value) or type(step) is not int or type(timestamp) is not int:return None
            result[key]=(value,step,timestamp)
        return result
    try:
        metrics=final_http['run']['data'].get('metrics',[])
        observed=[(m['key'],m['value'],m.get('step',0),m.get('timestamp',0)) for m in metrics]
        return table(final_rows)==expected and table(observed)==expected
    except (KeyError,TypeError,ValueError):return False

def artifact_paths(root):
    root=ordinary(root).resolve();pending=[root];found=[];directories=0;total=0
    excluded={'receipt.json',*LOG_FILES.values()}
    while pending:
        parent=pending.pop();directories+=1
        if directories>4096:raise ValueError('Artifact directory budget exceeded')
        for path in sorted(parent.iterdir()):
            path=ordinary(path)
            if path.is_dir():pending.append(path)
            elif path.is_file():
                name=path.relative_to(root).as_posix()
                if name in excluded:continue
                size=path.stat().st_size;total+=size
                if size>64*1024*1024 or total>MAX_ARTIFACT_BYTES or len(found)>=MAX_ARTIFACT_FILES:raise ValueError('Artifact byte or file budget exceeded')
                found.append(name)
            else:raise ValueError('Non-regular evidence file')
    return sorted(found)

def artifact_bindings(root):
    root=Path(root);names=artifact_paths(root)
    if not REQUIRED_ARTIFACTS.issubset(names):raise ValueError('Required original artifacts missing')
    return [{'file':name,'bytes':relative_file(root,name).stat().st_size,'sha256':file_digest(relative_file(root,name))} for name in names]

def validate_plan(plan):
    if not isinstance(plan,dict) or plan.get('format')!='moontxnwitness-mlflow-http-campaign/v1' or plan.get('commits')!=COMMITS or plan.get('seeds')!=list(SEEDS) or plan.get('pairs')!=30 or plan.get('clientRetries')!=0 or plan.get('sameMetricRequestsAndTimingPolicyBeforeAfter') is not True or plan.get('actualHttpExecution') is not False or plan.get('actualDatabaseExecution') is not False:raise ValueError('Campaign preregistration changed')
    rows=plan.get('cases')
    if not isinstance(rows,list) or len(rows)!=len(SEEDS):raise ValueError('Campaign cases missing')
    for seed,row in zip(SEEDS,rows):
        if not isinstance(row,dict) or set(row)!={'seed','file','sha256'} or row['seed']!=seed or row['file']!=f'case-{seed}.json' or row['sha256']!=digest(encoded(workload(seed))):raise ValueError('Frozen campaign seed, path or request differs')
    return True

def _source_handle_path(stream):
    """Resolve the already-open file, not a path that may have been retargeted."""
    if os.name=='nt':
        import ctypes,msvcrt
        from ctypes import wintypes
        function=ctypes.WinDLL('kernel32',use_last_error=True).GetFinalPathNameByHandleW
        function.argtypes=(wintypes.HANDLE,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD)
        function.restype=wintypes.DWORD
        buffer=ctypes.create_unicode_buffer(32768)
        length=function(msvcrt.get_osfhandle(stream.fileno()),buffer,len(buffer),0)
        if not length or length>=len(buffer):raise OSError(ctypes.get_last_error(),'Opened source final path unavailable')
        value=buffer.value
        if value.startswith('\\\\?\\UNC\\'):value='\\\\'+value[8:]
        elif value.startswith('\\\\?\\'):value=value[4:]
        return Path(value)
    descriptor=Path('/proc/self/fd')/str(stream.fileno())
    if not descriptor.is_symlink():raise ValueError('Opened source handle path unavailable on this platform')
    return Path(os.readlink(descriptor))

def _source_identity(value):
    # Windows lstat/fstat disagree about ctime; compare it only between fd stats.
    return (value.st_dev,value.st_ino,value.st_mode,value.st_size,value.st_mtime_ns,getattr(value,'st_birthtime_ns',None))

def _source_ordinary_stat(value):
    if getattr(value,'st_file_attributes',0)&0x400 or stat.S_ISLNK(value.st_mode):
        raise ValueError('Reparse or symlink source path refused')

class _SourceTree:
    """Call-local directory metadata cache; no source-content/hash cache.

    Root and all outer ancestors retain ordinary(). Each inner directory is
    lstat checked once. Every file is independently lstat/open/fstat checked,
    bound to its actual opened final path, and completely hashed. A retargeted
    cached ancestor cannot silently redirect even a same-content source file.
    """
    def __init__(self,root):
        self.root=ordinary(root).resolve()
        if not self.root.is_dir():raise ValueError('Frozen source root is not a directory')
        self.directories={self.root};self.files=set()
    def read(self,name,expected_bytes):
        if not isinstance(name,str) or not name or '\\' in name or ':' in name or name.startswith('/') or any(part in ('','.','..') for part in name.split('/')):
            raise ValueError('Unsafe relative source path')
        if type(expected_bytes) is not int or expected_bytes<0:raise ValueError('Invalid frozen source byte count')
        parts=name.split('/');parent=self.root
        for part in parts[:-1]:
            parent=parent/part
            if parent not in self.directories:
                value=parent.lstat();_source_ordinary_stat(value)
                if not stat.S_ISDIR(value.st_mode):raise ValueError('Source ancestor is not a directory')
                self.directories.add(parent)
        path=parent/parts[-1];identity=os.path.normcase(str(path))
        if identity in self.files:raise ValueError('Duplicate frozen source path')
        self.files.add(identity)
        before=path.lstat();_source_ordinary_stat(before)
        if not stat.S_ISREG(before.st_mode) or before.st_size!=expected_bytes:
            raise ValueError('Frozen upstream source type or size changed: '+name)
        with path.open('rb') as stream:
            opened=os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or _source_identity(before)!=_source_identity(opened):
                raise ValueError('Frozen upstream source replaced before open: '+name)
            if os.path.normcase(str(_source_handle_path(stream)))!=identity:
                raise ValueError('Opened source path was redirected: '+name)
            actual=hashlib.file_digest(stream,'sha256').hexdigest()
            after=os.fstat(stream.fileno())
            if _source_identity(opened)!=_source_identity(after) or opened.st_ctime_ns!=after.st_ctime_ns:
                raise ValueError('Frozen upstream source changed during read: '+name)
        return actual

def check_sources(label,root,manifest):
    if label not in COMMITS or manifest['commits'][label]!=COMMITS[label]:raise ValueError('Wrong frozen commit')
    tree=_SourceTree(root);rows=manifest['sources'][label]['files'];actual=[];seen=set()
    for row in rows:
        if row['path'] in seen:raise ValueError('Duplicate frozen source path')
        seen.add(row['path'])
        if tree.read(row['path'],row['bytes'])!=row['sha256']:raise ValueError('Frozen upstream source changed: '+row['path'])
        actual.append({'path':row['path'],'bytes':row['bytes'],'sha256':row['sha256']})
    return {'commit':COMMITS[label],'files':len(actual),'fileTableSha256':digest(encoded(actual)),'businessSourceModified':False}
def three_repetitions(results):
    if len(results)!=3 or any(r.get('executionComplete') is not True for r in results):return 'unknown'
    return 'reproduced' if all(r.get('faultPredicate') is True for r in results) else 'not-reproduced'


