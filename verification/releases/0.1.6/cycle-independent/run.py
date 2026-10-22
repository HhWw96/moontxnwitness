from pathlib import Path
import datetime, hashlib, json, subprocess, sys
OUT=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
def binding(p):
    b=p.read_bytes()
    return {'bytes':len(b),'sha256':sha(b)}
def write_json(p,x):
    with p.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(x,f,ensure_ascii=False,indent=2)
        f.write('\n')
assert not (OUT/'execution.json').exists()
command=[r'D:\nodejs\node.exe','check.mjs','--main-root','../..','--output-root','./runs']
prep=json.loads((OUT/'preparation.json').read_text(encoding='utf-8'))
plan={'schema':1,'startedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
      'command':command,'cwd':'review directory','checker':binding(OUT/'check.mjs'),
      'preparation':binding(OUT/'preparation.json'),'actualManifest':prep['actualManifest'],
      'scope':'132 frozen history expectations and all source mappings; savepoints; unknown and budgets; 11 derived / 8 source mutations; old capsules; unchanged example.',
      'expectedGroups':10,'frozenExpectedHistoryInputs':132,'frozenOldCapsuleInputs':287,
      'mainRegressionReference':binding(OUT/'main-regression-reference.json'),
      'newCoreBuild':False,'newDatabaseExecution':False,'newElleExecution':False,'formalPerformanceMeasurement':False}
write_json(OUT/'execution-started.json',plan)
with (OUT/'execution.stdout.txt').open('xb') as so,(OUT/'execution.stderr.txt').open('xb') as se:
    process=subprocess.run(command,cwd=OUT,stdout=so,stderr=se)
plan.update(exitCode=process.returncode,stdout=binding(OUT/'execution.stdout.txt'),stderr=binding(OUT/'execution.stderr.txt'))
write_json(OUT/'execution.json',plan)
print((OUT/'execution.stdout.txt').read_text(encoding='utf-8',errors='replace')[-6000:])
print((OUT/'execution.stderr.txt').read_text(encoding='utf-8',errors='replace')[-6000:],file=sys.stderr)
print(json.dumps({'exitCode':process.returncode}))
sys.exit(process.returncode)
