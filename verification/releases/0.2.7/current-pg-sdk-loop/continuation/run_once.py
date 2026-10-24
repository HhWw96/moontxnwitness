from pathlib import Path
import ctypes,hashlib,json,os,subprocess,datetime
HERE=Path(__file__).resolve().parent
OUT=HERE/'continuation-first';OUT.mkdir(exist_ok=False)
NODE=Path(r'D:\nodejs\node.exe');RUNNER=HERE/'verify-current-pg-sdk-loop.mjs';PLAN=HERE/'PLAN.json'
EXPECTED_RUNNER='118106a1c373ec1e82555edb24890259a62a44158cffaf9e42251576b32366c0'
EXPECTED_PLAN='a2bd2e5b362237c187c5fb11d76b02b03d22f2ffb9b88279916ab572207e542f'
def bind(p):
 b=p.read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def write(name,value):
 with(OUT/name).open('x',encoding='utf8',newline='\n')as f:f.write(json.dumps(value,indent=2)+'\n')
assert bind(RUNNER)['sha256']==EXPECTED_RUNNER and bind(PLAN)['sha256']==EXPECTED_PLAN
class Memory(ctypes.Structure):
 _fields_=[('dwLength',ctypes.c_ulong),('dwMemoryLoad',ctypes.c_ulong),('ullTotalPhys',ctypes.c_ulonglong),('ullAvailPhys',ctypes.c_ulonglong),('ullTotalPageFile',ctypes.c_ulonglong),('ullAvailPageFile',ctypes.c_ulonglong),('ullTotalVirtual',ctypes.c_ulonglong),('ullAvailVirtual',ctypes.c_ulonglong),('ullAvailExtendedVirtual',ctypes.c_ulonglong)]
m=Memory();m.dwLength=ctypes.sizeof(m);assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
resources={'availablePhysicalBytes':m.ullAvailPhys,'minimumPhysicalBytes':1073741824,'passed':m.ullAvailPhys>=1073741824,'checkedBeforeNodeSdkProcess':True,'nodeHeapMiB':384};write('RESOURCES-FIRST.json',resources)
env=dict(os.environ);env.pop('NODE_OPTIONS',None);env.pop('NODE_PATH',None)
syntax=None;process=None;status='resource-refused';started=datetime.datetime.now(datetime.timezone.utc).isoformat()
if resources['passed']:
 syntax=subprocess.run([str(NODE),'--check',str(RUNNER)],cwd=HERE,env=env,capture_output=True,timeout=30)
 (OUT/'syntax.stdout.log').write_bytes(syntax.stdout);(OUT/'syntax.stderr.log').write_bytes(syntax.stderr)
 if syntax.returncode==0:
  args=[str(NODE),'--max-old-space-size=384',str(RUNNER),'--plan',str(PLAN),'--plan-sha256',EXPECTED_PLAN,'--runtime',r'D:\CodexScratch\MoonTxnWitness-v027-evidence-adoption-20261024-ah\actual-ci-runtime','--inputs',r'D:\CodexScratch\MoonTxnWitness-release-20261023\verification\model-profile-v3\postgres-ci','--output',str(OUT/'results')]
  try:
   with(OUT/'first.stdout.log').open('xb')as stdout,(OUT/'first.stderr.log').open('xb')as stderr:
    process=subprocess.run(args,cwd=HERE,env=env,stdout=stdout,stderr=stderr,timeout=180)
   status='passed'if process.returncode==0 else 'failed'
  except subprocess.TimeoutExpired:status='timeout'
 else:status='syntax-failed'
report={'format':'current027-pg-sdk-loop-first-process/v1','status':status,'passed':status=='passed','startedAt':started,'finishedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exitCode':process.returncode if process else None,'syntaxExitCode':syntax.returncode if syntax else None,'resourceCheck':resources,'runner':bind(RUNNER),'plan':bind(PLAN),'runtime':'D:/CodexScratch/MoonTxnWitness-v027-evidence-adoption-20261024-ah/actual-ci-runtime','originalInputs':'D:/CodexScratch/MoonTxnWitness-release-20261023/verification/model-profile-v3/postgres-ci','currentRawOriginalsRewritten':False,'newDatabaseRun':False,'sourceClosedReductionClaimed':False,'packageOrPublicationAccepted':False}
write('PROCESS-FIRST.json',report)
print(json.dumps({'status':status,'receipt':bind(OUT/'PROCESS-FIRST.json'),'sdkReceiptExists':(OUT/'results/receipt.json').is_file()}))
if(OUT/'first.stdout.log').is_file():print((OUT/'first.stdout.log').read_text(encoding='utf8'))
if(OUT/'first.stderr.log').is_file():print((OUT/'first.stderr.log').read_text(encoding='utf8'))
raise SystemExit(0 if status=='passed' else 1)
