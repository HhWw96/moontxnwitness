from pathlib import Path
import argparse,hashlib,json,subprocess,sys,os
ROOT=Path(__file__).resolve().parent
SHA=lambda b:hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--closure-sha256',required=True);p.add_argument('--verify-only',action='store_true');p.add_argument('--node');a=p.parse_args();raw=(ROOT/'public-closure.json').read_bytes();assert SHA(raw)==a.closure_sha256;m=json.loads(raw)
 for row in m['files']:
  f=(ROOT/row['file']).resolve();assert f.is_relative_to(ROOT);b=f.read_bytes();assert len(b)==row['bytes'] and SHA(b)==row['sha256'],row['file']
 if a.verify_only:print(json.dumps({'passed':True,'files':len(m['files']),'SDKImported':False,'actual20Executed':False}));return 0
 f=ROOT/'public-root-freeze.json';p=ROOT/'review/preparation-manifest.json';env=dict(os.environ)
 if a.node:env['PATH']=str(Path(a.node).resolve().parent)+os.pathsep+env.get('PATH','')
 r=subprocess.run([sys.executable,'-B',str(ROOT/'review/run-review.py'),'--freeze',str(f),'--freeze-sha256',SHA(f.read_bytes()),'--preparation-sha256',SHA(p.read_bytes())],cwd=ROOT,env=env)
 for row in m['files']:
  b=(ROOT/row['file']).read_bytes();assert len(b)==row['bytes'] and SHA(b)==row['sha256'],row['file']
 return r.returncode
if __name__=='__main__':raise SystemExit(main())
