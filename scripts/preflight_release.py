"""Fast offline consistency checks before compiler installation or corpus tests."""
from pathlib import Path
import argparse,json,re,subprocess,sys

ROOT=Path(__file__).resolve().parents[1]

def check_pins(root=ROOT):
    config=json.loads((root/'scripts/frozen-inputs.json').read_text('utf8'))
    checked=[]
    for path in sorted((root/'scripts').glob('public*-compatibility-groups.mjs')):
        match=re.fullmatch(r'public(\d{3})-compatibility-groups\.mjs',path.name)
        if match is None: continue
        identity=match[1]
        raw=(root/('cmd/legacy-v'+identity+'-binding.mjs')).read_text('utf8')
        if len(raw.encode('utf8'))>8*1024*1024: raise ValueError('Compatibility binding exceeds its budget')
        prefix='export const PUBLIC'+identity+'=Object.freeze('
        first=raw.splitlines()[0]
        if not first.startswith(prefix) or not first.endswith(');'):
            raise ValueError('Expected a fixed data-only compatibility binding')
        pin=json.loads(first[len(prefix):-2])
        fields={'publicVersion':pin['version'],'producerSourceCommit':pin['sourceCommit'],
                'producerArchiveSha256':pin['archiveSha256'],'producerComponentSha256':pin['componentSha256']}
        text=path.read_text('utf8')
        for field,expected in fields.items():
            pattern=r'assert\.equal\(\s*result\.'+field+r'\s*,\s*([\'"])([^\'"]+)\1\s*\)'
            found=re.search(pattern,text)
            if found is None or found[2]!=expected:
                raise ValueError(path.name+' disagrees with its fixed binding: '+field)
        provider='component'+identity
        if config['providers'][provider]['sha256']!=pin['componentSha256'] or config['sourceCommits'][provider]!=pin['sourceCommit']:
            raise ValueError('Provider differs from its compatibility binding: '+provider)
        checked.append({'version':pin['version'],'componentSha256':pin['componentSha256']})
    return checked

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pins-only',action='store_true')
    args=parser.parse_args()
    pins=check_pins()
    units=[]
    if not args.pins_only:
        for pattern in ('test_publication_ci.py','test_distribution.py','test_hosted_publication.py',
                        'test_publication_download.py','test_package_archive.py','test_public025_package_gate.py',
                        'test_compat_dispatch_staging.py','test_public034_receipt_binding.py'):
            result=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','scripts','-p',pattern,'-v'],cwd=ROOT)
            if result.returncode: raise SystemExit(result.returncode)
            units.append(pattern)
    print(json.dumps({'passed':True,'phase':'pins-only' if args.pins_only else 'release-preflight',
                      'offline':True,'compilerExecuted':False,'pins':pins,'unitSuitesExecuted':units}))

if __name__=='__main__':main()
