"""Unauthenticated public metadata reads only; preserve first responses."""
from pathlib import Path
import json,urllib.request
HERE=Path(__file__).resolve().parent
items={'run':'repos/HhWw96/moontxnwitness/actions/runs/39622521792',
       'jobs':'repos/HhWw96/moontxnwitness/actions/runs/39622521792/jobs',
       'artifact':'repos/HhWw96/moontxnwitness/actions/artifacts/12355956248'}
results={}
for name,path in items.items():
    request=urllib.request.Request('https://api.github.com/'+path,headers={'User-Agent':'MoonTxnWitness-independent-readonly-review','Accept':'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(request,timeout=30) as response:raw=response.read(1048577)
        if len(raw)>1048576:raise ValueError('API metadata bound')
        data=json.loads(raw)
        with (HERE/('official-'+name+'.json')).open('xb') as stream:stream.write(raw)
        results[name]={'read':True,'status':data.get('status'),'conclusion':data.get('conclusion')}
    except Exception as error:
        with (HERE/('official-'+name+'-failure.json')).open('x',encoding='utf8') as stream:json.dump({'class':type(error).__name__},stream)
        results[name]={'read':False,'errorClass':type(error).__name__}
print(json.dumps(results))
