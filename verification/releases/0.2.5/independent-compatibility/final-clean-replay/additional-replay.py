from pathlib import Path
import shutil,json,hashlib,subprocess,os,sys
NODE=sys.argv[1]if len(sys.argv)>1 else "node"
base=Path(__file__).resolve().parent;repo=base/'integrated';work=base/'additional-work';work.mkdir();runtime=work/'runtime';shutil.copytree(repo/'dist',runtime);fixtures=repo/'fixtures/compat-v024';marker=work/'untrusted-executed.marker';evil=work/'evil.cjs';evil.write_bytes(('globalThis.__mtw_untrusted_loaded=true;require("node:fs").writeFileSync('+json.dumps(str(marker))+',"untrusted");module.exports={};\n').encode())
sha=lambda b:hashlib.sha256(b).hexdigest();out=base/'additional-first';out.mkdir();cases=[];manifest={p.relative_to(runtime).as_posix():sha(p.read_bytes())for p in runtime.rglob('*')if p.is_file()};legacy=runtime/'legacy/v024'
def run(name,mode,missing=None,tamper=None):
 moved=None;old=None
 try:
  if missing:
   q=runtime/missing;dest=q.with_name(q.name+'.held-'+name);assert q.resolve().is_relative_to(work.resolve())and dest.absolute().is_relative_to(work.absolute());q.rename(dest);moved=(q,dest)
  if tamper:
   q=legacy/tamper;old=(q,q.read_bytes());q.write_bytes(old[1]+b'\n;globalThis.__mtw_untrusted_loaded=true;\n')
  r=subprocess.run([NODE,str(base/'additional-worker.mjs'),mode,str(runtime),str(fixtures),str(marker)],cwd=base,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
  (out/(name+'.stdout.json')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr)
  cases.append({'name':name,'mode':mode,'missing':missing,'tamper':tamper,'passed':r.returncode==0,'exitCode':r.returncode,'stdoutSha256':sha(r.stdout),'stderrSha256':sha(r.stderr)})
 finally:
  if old:old[0].write_bytes(old[1])
  if moved:moved[1].rename(moved[0])
run('ordinary-current-with-no-legacy-files','normal-missing-legacy',missing='legacy/v024')
run('unknown-engine-cannot-select-module-even-when-legacy-absent','unknown-engine-missing-legacy',missing='legacy/v024')
run('known-engine-extra-module-path-cannot-execute-code','known-engine-untrusted-path')
run('retagging-old-engine-does-not-migrate-report','retagged-old-as-current')
run('old-source-text-mismatch-rejected','old-report-wrong-envelope')
run('missing-executable-core-refused','reject-original',missing='legacy/v024/core.cjs')
for name in ['core.cjs','orm-profile.cjs','core.mjs','orm-profile.mjs','origin.json','manifest.json']:
 run('tampered-'+name.replace('.','-')+'-refused-before-execution','reject-original',tamper=name)
run('valid-old-replay-is-synchronous-and-cached','cache')
assert manifest=={p.relative_to(runtime).as_posix():sha(p.read_bytes())for p in runtime.rglob('*')if p.is_file()}
result={'format':'independent-current-v025-lazy-orm-extra-probes/v1','passed':all(x['passed']for x in cases),'checks':len(cases),'cases':cases,'mockedCore':False,'restoredRuntimeBytesUnchanged':True,'capsuleSelectedExecutablePaths':False,'databaseExecuted':False,'formalPerformanceMeasurement':False};(out/'receipt.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result));raise SystemExit(0 if result['passed']else 1)
