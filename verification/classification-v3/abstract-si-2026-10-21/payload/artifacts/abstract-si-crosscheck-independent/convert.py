"""Independent explicit-final-order point-history adapter. No oracle imports/results.
Initial/transaction array ordering never creates dependency edges.
"""
from pathlib import Path
from datetime import datetime,timezone
import collections,gzip,hashlib,json
ROOT=Path.cwd();HERE=Path(__file__).resolve().parent;INPUT=ROOT/'artifacts/abstract-si-v3-independent-draft'
SHA=lambda b:hashlib.sha256(b).hexdigest()
class Outside(ValueError):pass
def require(x,reason):
 if not x:raise Outside(reason)
def identity(x):
 return type(x)is str and bool(x) and all(not 0xd800<=ord(c)<=0xdfff for c in x) and len(x.encode('utf-16-le'))//2<=256
def closure(n,arcs):
 a=[[False]*n for _ in range(n)]
 for i,j in arcs:a[i][j]=True
 for k in range(n):
  for i in range(n):
   if a[i][k]:
    for j in range(n):a[i][j]|=a[k][j]
 return any(a[i][i] for i in range(n))
def graph_truth(g):
 ix={x:i for i,x in enumerate(g['nodes'])};d={(ix[e['from']],ix[e['to']]) for e in g['edges'] if e['kind']in('ww','wr')};rw={(ix[e['from']],ix[e['to']]) for e in g['edges'] if e['kind']=='rw-item'}
 h=d|{(a,c) for a,b in d for b2,c in rw if b==b2}
 return {'dCycle':closure(len(ix),d),'serialRejected':closure(len(ix),d|rw),'gsiRejected':closure(len(ix),h),'hArcCount':len(h),'originalEdgeCounts':dict(collections.Counter(e['kind'] for e in g['edges']))}
def convert(t):
 out={'eligible':False,'reason':None,'directObligations':[],'graph':None,'truth':None}
 try:
  require(type(t)is dict and set(t)=={'schema','dataModel','complete','initial','versionOrders','transactions'},'structure_root_fields')
  require(type(t['schema'])is int and t['schema']==1 and type(t['complete'])is bool,'structure_schema_complete')
  require(t['dataModel']=='point-register-v1','unsupported_data_model')
  init,orders,txs=t['initial'],t['versionOrders'],t['transactions'];require(type(init)is dict and type(orders)is dict and type(txs)is list,'structure_collections')
  require(all(identity(k) and identity(v) for k,v in init.items()),'identity_initial')
  require(len(init)<=128,'capacity_keys');require(len(txs)<=6,'capacity_transactions')
  txids=[];writes={};final={};totalops=0
  for ti,tx in enumerate(txs):
   require(type(tx)is dict and set(tx)=={'id','status','ops'} and identity(tx['id']) and type(tx['ops'])is list,'structure_transaction')
   require(tx['id']not in txids,'duplicate_transaction_id');txids.append(tx['id']);require(tx['status']=='committed','outcome_not_committed')
   local={};totalops+=len(tx['ops'])
   for oi,op in enumerate(tx['ops']):
    require(type(op)is dict and set(op)=={'type','key','version'},'unsupported_or_malformed_program')
    require(op['type']in('read','write'),'unsupported_scope_program')
    k,v=op['key'],op['version'];require(identity(k) and identity(v),'identity_operation');require(k in init,'uninitialized_key')
    if op['type']=='write':
     require(v!=init[k] and (k,v)not in writes,'duplicate_version_producer');writes[k,v]={'tx':tx['id'],'txIndex':ti,'opIndex':oi};local[k]=(v,oi)
   for k,(v,oi) in local.items():final[k,tx['id']]={'version':v,'opIndex':oi}
  require(totalops<=128,'capacity_operations');require(t['complete'],'coverage_incomplete')
  require(set(orders)==set(init),'missing_or_extra_key_order')
  ranks={}
  for k,vs in orders.items():
   require(type(vs)is list and len(vs)>0 and all(identity(v) for v in vs),'structure_order')
   require(vs[0]==init[k] and len(vs)==len(set(vs)),'illformed_order_initial_or_duplicate')
   expected={init[k]}|{f['version'] for (fk,tx),f in final.items() if fk==k}
   for v in vs[1:]:
    require((k,v)in writes,'missing_order_source')
    require(final[k,writes[k,v]['tx']]['version']==v,'nonfinal_version_in_final_order')
   require(set(vs)==expected,'partial_final_order')
   ranks[k]={v:i for i,v in enumerate(vs)}
  for tx in txs:
   last={}
   for oi,op in enumerate(tx['ops']):
    k,v=op['key'],op['version']
    if op['type']=='read':
     require(v==init[k] or (k,v)in writes,'missing_read_source')
     source=None if v==init[k] else writes[k,v]
     if k in last and last[k]['version']!=v:out['directObligations'].append({'kind':'INT','tx':tx['id'],'opIndex':oi,'key':k,'version':v,'priorOpIndex':last[k]['opIndex'],'priorVersion':last[k]['version']})
     if source is not None:
      if source['tx']==tx['id'] and source['opIndex']>oi:out['directObligations'].append({'kind':'own_future_source','tx':tx['id'],'opIndex':oi,'key':k,'version':v,'source':source})
      if source['tx']!=tx['id'] and final[k,source['tx']]['version']!=v:out['directObligations'].append({'kind':'external_intermediate_source','tx':tx['id'],'opIndex':oi,'key':k,'version':v,'source':source})
    last[k]={'version':v,'opIndex':oi}
  if out['directObligations']:out['reason']='direct_semantic_obligations';return out
  mapping=[{'node':'n'+str(i),'transaction':txid} for i,txid in enumerate(txids)];node={r['transaction']:r['node'] for r in mapping};edges=[]
  def edge(kind,a,b,source):
   if a==b:return
   edges.append({'id':'e'+str(len(edges)),'from':node[a],'to':node[b],'kind':kind,'source':source})
  for k,vs in orders.items():
   for i in range(1,len(vs)-1):
    a,b=writes[k,vs[i]],writes[k,vs[i+1]]
    edge('ww',a['tx'],b['tx'],{'kind':'factual-adjacent-final-order','key':k,'leftVersion':vs[i],'rightVersion':vs[i+1],'leftOrderIndex':i,'rightOrderIndex':i+1,'leftProducer':a,'rightProducer':b})
  for tx in txs:
   for oi,op in enumerate(tx['ops']):
    if op['type']!='read':continue
    k,v=op['key'],op['version'];src=None if v==init[k] else writes[k,v]
    if src is not None and src['tx']==tx['id']:continue
    if src is not None:edge('wr',src['tx'],tx['id'],{'kind':'external-final-read-source','key':k,'version':v,'read':{'tx':tx['id'],'opIndex':oi},'producer':src})
    rank=ranks[k][v]
    if rank+1<len(orders[k]):
     successor=orders[k][rank+1];writer=writes[k,successor]
     edge('rw-item',tx['id'],writer['tx'],{'kind':'read-and-factual-immediate-successor','key':k,'readVersion':v,'readOrderIndex':rank,'successorVersion':successor,'successorOrderIndex':rank+1,'read':{'tx':tx['id'],'opIndex':oi},'producer':src,'successorProducer':writer})
  g={'nodes':[m['node'] for m in mapping],'edges':edges,'complete':True}
  out.update(eligible=True,reason='common_complete_supported',nodeMapping=mapping,graph=g,truth=graph_truth(g));return out
 except Outside as e:out['reason']=str(e);return out

def main():
 files={'frozen-boundaries-v1.json':'7458e741068467c8042b529454ca4be5131b4d944ddecc9845557499b8b4a2e7','generated-inputs-v1.jsonl':'ffa93f0ce528a40aa9b9fb09d5491100c7320e0c857ea1a6e195bbef3429053e'}
 for name,h in files.items():require(SHA((INPUT/name).read_bytes())==h,'input_file_changed')
 boundary=json.loads((INPUT/'frozen-boundaries-v1.json').read_bytes())['fixtures'];generated=[json.loads(x) for x in (INPUT/'generated-inputs-v1.jsonl').read_bytes().splitlines()]
 records=[]
 for bundle,items,sort in [('boundary',boundary,False),('generated',generated,True)]:
  for r in items:
   text=json.dumps(r['input'],ensure_ascii=True,sort_keys=sort,separators=(',',':'));require(SHA(text.encode())==r['inputSha256'],'per_input_hash_changed')
   records.append({'id':r['id'],'bundle':bundle,'inputSha256':r['inputSha256'],'inputText':text,'options':r.get('options',{}),'conversion':convert(r['input'])})
 require(len(records)==1052 and len(generated)==1000,'input_count');require(len({r['inputSha256'] for r in records if r['bundle']=='generated'})==1000,'generated_input_duplicate')
 target=HERE/'converted-inputs-v1.jsonl.gz'
 with target.open('xb') as raw:
  with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as zipped:
   for r in records:zipped.write((json.dumps(r,ensure_ascii=True,sort_keys=True,separators=(',',':'))+'\n').encode())
 manifest={'schema':1,'kind':'independent-source-graph-conversion-freeze','productionOracleImplementationRead':False,'productionOracleResultsRead':False,'inputRecords':1052,'generatedDistinctInputSha256Count':1000,'counts':dict(collections.Counter(r['conversion']['reason'] for r in records)),'files':{'convert.py':{'bytes':Path(__file__).stat().st_size,'sha256':SHA(Path(__file__).read_bytes())},target.name:{'bytes':target.stat().st_size,'sha256':SHA(target.read_bytes())}},'protocolSha256':SHA((HERE/'protocol-freeze.json').read_bytes()),'frozenAt':datetime.now(timezone.utc).isoformat()}
 b=(json.dumps(manifest,indent=2)+'\n').encode();(HERE/'conversion-freeze.json').open('xb').write(b);print(json.dumps({'passed':True,'inputs':len(records),'counts':manifest['counts'],'manifestSha256':SHA(b)}))
if __name__=='__main__':main()
