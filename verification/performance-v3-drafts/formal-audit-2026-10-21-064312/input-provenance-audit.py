"""Read-only independent input and public-baseline identity supplement."""
from pathlib import Path
from datetime import datetime,timezone
import gzip,hashlib,json

ROOT=Path(__file__).resolve().parents[3]
RECEIPT=ROOT/'verification/releases/0.1.1/performance-v010-formal-2026-10-21T06-43-12-373Z.checkpoints/000038-45942d57-a9a5-4d1a-bc59-a067a026bf88.json'
SHA=lambda raw:hashlib.sha256(raw).hexdigest()
LOAD=lambda path:json.loads(path.read_bytes())


def main():
    output={'schema':1,'passed':False,'complete':False,'scope':'Frozen inputs, outputs and pinned public engine identity; no benchmark executed',
            'implementationSha256':SHA(Path(__file__).read_bytes()),'cases':[]}
    try:
        raw=RECEIPT.read_bytes();assert SHA(raw)=='f846ae668e8bc21744f3402f634feda50891d7dc9c5a36ff2f60dc660397324c'
        r=json.loads(raw);frozen=LOAD(ROOT/'verification/baselines/0.1.0/manifest.json')
        fm=ROOT/frozen['fixtureManifest'];assert SHA(fm.read_bytes())==frozen['fixtureManifestSha256']==r['fixtureManifestSha256']
        manifest=LOAD(fm);assert manifest['allInputsFrozenBeforeOptimization'] and manifest['frozenEngineVersion']=='0.1.0'
        original=LOAD(ROOT/r['provenance']['frozenBaselineReceipt']);assert r['provenance']['frozenBaselineReceipt']==frozen['latestFormalReceipt']
        assert original['passed'] and original['formalBaselineEstablished'] and not original['smokeOnly']
        engine=r['provenance']['baseline'];assert engine['coreSha256']=='6c76b3be6c45ff633232568b3ffed3c1393ade3b4d012ee5c21c49cbb8dcf97b'
        assert engine['sourceSha256']=='dcc8653278a9f98dc6056d23c8b7d7d9db3fc6b8406b22987fc9ff03997dd830'
        assert engine['archiveSha256']=='d7495482b8267f327edf40e95111acbd2502290fc97e5f1e5e1203e7bc59488c'
        assert engine['publishedBuildManifest']['toolchain']==r['provenance']['currentBuildManifest']['toolchain']
        for item in manifest['cases']:
            fixture_raw=(ROOT/item['file']).read_bytes();assert SHA(fixture_raw)==item['fixtureSha256']
            history=LOAD(ROOT/item['file'])['history'];encoded=json.dumps(history,ensure_ascii=False,separators=(',',':')).encode()
            assert SHA(encoded)==item['historySha256']
            old=next(o for o in original['results'] if o['scenario']==item['name'])
            row=next(o for o in r['results'] if o['scenario']==item['name'])
            assert old['inputSha256']==row['inputSha256']==item['historySha256']
            h=hashlib.sha256();size=0
            with gzip.open(ROOT/old['fullOutput'],'rb') as stream:
                while block:=stream.read(65536):h.update(block);size+=len(block)
            digest=h.hexdigest();assert digest==old['fullOutputSha256']
            for side in ('baseline','current'):
                assert len(row['observations'][side])==3
                for o in row['observations'][side]:assert o['fullOutput']['frozenOutputSha256']==digest and o['fullOutput']['semanticAgreement']
            output['cases'].append({'scenario':item['name'],'fixtureSha256':item['fixtureSha256'],'historySha256':item['historySha256'],
                                    'frozenCompleteOutputSha256':digest,'frozenCompleteOutputBytes':size,'allSixWorkerReferencesAgree':True})
        assert len(output['cases'])==20
        output.update(passed=True,complete=True,fixtureManifestSha256=SHA(fm.read_bytes()),
                      frozenBaselineReceiptSha256=SHA((ROOT/r['provenance']['frozenBaselineReceipt']).read_bytes()),
                      observedSource=r['provenance']['currentBuildManifest'],publicBaseline=engine)
    except Exception as e:output.update(errorClass=type(e).__name__,error=str(e).replace(str(ROOT),'<workspace>'))
    output['verifiedAt']=datetime.now(timezone.utc).isoformat();p=Path(__file__).with_name('input-provenance-receipt.json')
    raw=(json.dumps(output,indent=2)+'\n').encode();p.open('xb').write(raw)
    print(json.dumps({'passed':output['passed'],'complete':output['complete'],'cases':len(output['cases']),'receipt':p.relative_to(ROOT).as_posix(),'sha256':SHA(raw),'error':output.get('error')}))
    return 0 if output['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
