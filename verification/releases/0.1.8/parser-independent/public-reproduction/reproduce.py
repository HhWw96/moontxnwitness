from pathlib import Path
import argparse,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parent
SHA=lambda b:hashlib.sha256(b).hexdigest()
def main():
 a=argparse.ArgumentParser();a.add_argument('--closure-sha256',required=True);a.add_argument('--verify-only',action='store_true');x=a.parse_args();raw=(ROOT/'public-closure.json').read_bytes();assert SHA(raw)==x.closure_sha256;m=json.loads(raw)
 for row in m['files']:
  p=(ROOT/row['file']).resolve();assert p.is_relative_to(ROOT);b=p.read_bytes();assert len(b)==row['bytes'] and SHA(b)==row['sha256'],row['file']
 if x.verify_only:print(json.dumps({'passed':True,'files':len(m['files']),'SDKImported':False,'stable18Executed':False}));return 0
 f=ROOT/'public-root-freeze.json';p=ROOT/'review/preparation-manifest.json'
 r=subprocess.run([sys.executable,'-B',str(ROOT/'review/run-review.py'),'--freeze',str(f),'--freeze-sha256',SHA(f.read_bytes()),'--preparation-sha256',SHA(p.read_bytes())],cwd=ROOT)
 for row in m['files']:
  b=(ROOT/row['file']).read_bytes();assert len(b)==row['bytes'] and SHA(b)==row['sha256'],row['file']
 return r.returncode
if __name__=='__main__':raise SystemExit(main())
