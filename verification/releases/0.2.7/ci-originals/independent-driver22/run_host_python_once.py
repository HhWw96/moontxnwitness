from pathlib import Path
import ctypes,hashlib,os,json,shutil,subprocess,re,sys
ROOT=Path(r'D:\CodexScratch\MoonTxnWitness-v027-integration-20261024-h');OUT=Path(str(ROOT)+'-receipts')/'model-profile-host-python-functional-20261024-s';TMP=OUT/'tmp';TMP.mkdir();NODE=r'D:\nodejs\node.exe';PYTHON=r'D:\Border\python\python.exe'
ENV={**os.environ,**{k:str(TMP) for k in ['TEMP','TMP','TMPDIR','MTW_JOURNAL_SCRATCH']},'MTW_MODEL_HOST_OUTPUT':str(OUT/'host50-first')}
class M(ctypes.Structure):
 _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),('totalPhys',ctypes.c_ulonglong),('availPhys',ctypes.c_ulonglong),('totalPage',ctypes.c_ulonglong),('availPage',ctypes.c_ulonglong),('totalVirtual',ctypes.c_ulonglong),('availVirtual',ctypes.c_ulonglong),('availExtended',ctypes.c_ulonglong)]
def bind(p):
 h=hashlib.sha256();size=0
 with p.open('rb') as f:
  while b:=f.read(1048576):h.update(b);size+=len(b)
 return {'bytes':size,'sha256':h.hexdigest()}
def save(name,value):
 with (OUT/name).open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(value,ensure_ascii=True,indent=2)+'\n');f.flush();os.fsync(f.fileno())
def gate(label):
 m=M();m.length=ctypes.sizeof(m);assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m));v={'profile':'functional-serial-1gib-v1','availablePhysicalMemoryBytes':m.availPhys,'cFreeBytes':shutil.disk_usage('C:\\').free,'dFreeBytes':shutil.disk_usage('D:\\').free};v['gatePassed']=m.availPhys>=1073741824 and v['cFreeBytes']>=768*1024*1024 and v['dFreeBytes']>=2147483648;save(label+'-resource.json',v);print(json.dumps({'stage':label,**v}),flush=True);assert v['gatePassed'],'resource gate failed; stop without retry'
def snapshot():
 names=['moon.mod','package.json','.github/workflows/postgres.yml']
 for folder in ['src','cmd','scripts','dist','verification/model-profile-v3/v027-initial']:
  names.extend(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
 return {n:bind(ROOT/n) for n in sorted(names)}
def run(label,args):
 with (OUT/(label+'.stdout.log')).open('xb') as a,(OUT/(label+'.stderr.log')).open('xb') as b:p=subprocess.run(args,cwd=ROOT,env=ENV,stdout=a,stderr=b,timeout=3600)
 v={'name':label,'command':args,'exitCode':p.returncode,'stdout':bind(OUT/(label+'.stdout.log')),'stderr':bind(OUT/(label+'.stderr.log'))};receipt['steps'].append(v);save(label+'-process.json',v);print(json.dumps(v),flush=True)
 assert p.returncode==0,'First functional failure at '+label+'; original logs retained; no dependent step'
receipt={'format':'v027-model-profile-current-host-and-python-first/v1','passed':False,'sourceDirectory':str(ROOT),'resourceProfile':'functional-serial-1gib-v1','parentV8MaxOldSpaceMiB':384,'sourceClosedReductionClaimed':False,'actualDatabaseExecution':False,'historicalEvidenceOnly':True,'compilerInvocations':0,'npmTestInvocations':0,'packageInvocations':0,'formalPerformanceMeasured':False,'rootProductionWrites':False,'steps':[]}
try:
 gate('host50-first');before=snapshot();save('SOURCE-RUNTIME-EVIDENCE-BEFORE.json',before)
 assert bind(ROOT/'scripts/model-profile-sdk-test.mjs')=={'bytes':9417,'sha256':'b03019466b72304a4d093759c5e218f2905c765ad480f5a1f65e9ff24a47243b'}
 run('host50-first',[NODE,'--max-old-space-size=384',str(ROOT/'scripts/model-profile-sdk-test.mjs')])
 value=json.loads((OUT/'host50-first/receipt.json').read_text(encoding='utf8'));assert value['passed'] is True and value['cases']==50 and value['output']==str(OUT/'host50-first') and value['actualDatabaseExecution'] is False and value['sourceClosedReductionClaimed'] is False
 summary=json.loads((OUT/'host50-first.stdout.log').read_text(encoding='utf8'));assert summary['output']==value['output'];receipt['hostReceipt']=bind(OUT/'host50-first/receipt.json');receipt['actualHostCases']=value['cases'];assert snapshot()==before
 gate('python-model22-first');run('python-model22-first',[PYTHON,'-B',str(ROOT/'integrations/python/moontxnwitness_capture/test_model_profile.py')])
 raw=(OUT/'python-model22-first.stdout.log').read_text(encoding='utf8')+(OUT/'python-model22-first.stderr.log').read_text(encoding='utf8');match=re.search(r'Ran\s+(\d+)\s+tests?\s+in',raw);assert match and int(match[1])==22 and re.search(r'\nOK\s*$',raw);receipt['actualPythonTests']=int(match[1]);receipt['pythonUnittestStdoutParsedAsJson']=False
 assert snapshot()==before;receipt['passed']=True
except BaseException as error:receipt['failure']={'type':type(error).__name__,'message':str(error)}
finally:
 if 'before' in locals():
  after=snapshot();save('SOURCE-RUNTIME-EVIDENCE-AFTER.json',after);receipt['sourceRuntimeAndOriginalHistoricalEvidenceUnchanged']=after==before
 receipt['driver']=bind(Path(__file__));receipt['dFreeAfter']=shutil.disk_usage('D:\\').free;save('ACTUAL-FIRST-RESULT.json',receipt);print(json.dumps({'receipt':str(OUT/'ACTUAL-FIRST-RESULT.json'),'binding':bind(OUT/'ACTUAL-FIRST-RESULT.json'),'passed':receipt['passed'],'failure':receipt.get('failure'),'hostCases':receipt.get('actualHostCases'),'pythonTests':receipt.get('actualPythonTests'),'steps':receipt['steps']}),flush=True)
if not receipt['passed']:sys.exit(2)
