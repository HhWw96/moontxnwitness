"""Freeze original graph shapes and independent expected results; no production."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,itertools,json,random,uuid
from graph_oracle import analyze,MODELS

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
SHA=lambda b:hashlib.sha256(b).hexdigest()


def graph(links,nodes=None):
    return {'nodes':sorted(set(nodes or [v for a,b,k in links for v in (a,b)])),
            'edges':[{'id':'e'+str(i),'from':a,'to':b,'kind':k} for i,(a,b,k) in enumerate(links)]}


def canonical(g):
    # Isomorphic relabelings do not become additional generated histories.
    return min((len(g['nodes']),tuple(sorted((permutation[g['nodes'].index(e['from'])],permutation[g['nodes'].index(e['to'])],e['kind']) for e in g['edges'])))
               for permutation in itertools.permutations(range(len(g['nodes']))))


def main():
    out=HERE/('frozen-'+uuid.uuid4().hex);out.mkdir()
    manual=[]
    def case(name,links,wanted,nodes=None):
        g=graph(links,nodes);manual.append({'id':name,'graph':g,'expectedRefuted':[m for m in MODELS if m in wanted]})
    case('empty',[],[],['A'])
    case('acyclic-ww',[('A','B','ww')],[])
    case('ww-cycle-no-wr-required',[('A','B','ww'),('B','A','ww')],MODELS)
    case('wr-cycle-not-g0',[('A','B','wr'),('B','A','wr')],MODELS[1:])
    case('item-only-adjacent-rw',[('A','B','rw-item'),('B','A','rw-item')],[MODELS[2],MODELS[4],MODELS[5]])
    case('predicate-only-adjacent-rw',[('A','B','rw-predicate'),('B','A','rw-predicate')],[MODELS[4],MODELS[5]])
    case('mixed-item-predicate-cycle',[('A','B','rw-item'),('B','A','rw-predicate')],[MODELS[2],MODELS[4],MODELS[5]])
    case('single-item-rw-cycle',[('A','B','ww'),('B','A','rw-item')],MODELS[2:])
    case('single-predicate-rw-cycle',[('A','B','wr'),('B','A','rw-predicate')],[MODELS[3],MODELS[4],MODELS[5]])
    case('alternating-two-rw',[('A','B','wr'),('B','C','rw-item'),('C','D','ww'),('D','A','rw-predicate')],MODELS[2:])
    case('wraparound-rw-adjacency',[('A','B','rw-item'),('B','C','ww'),('C','A','rw-predicate')],[MODELS[2],MODELS[4],MODELS[5]])
    case('short-allowed-si-long-forbidden-si',[('A','B','rw-item'),('B','A','rw-item'),('A','C','ww'),('C','D','rw-item'),('D','B','ww')],MODELS[2:])
    case('parallel-edge-type-choice',[('A','B','ww'),('A','B','rw-item'),('B','A','wr'),('B','A','rw-predicate')],MODELS[1:])
    case('rt-ww-cycle-is-only-strict',[('A','B','rt'),('B','A','ww')],[MODELS[5]])
    case('rt-rw-cycle-is-only-strict',[('A','B','rt'),('B','A','rw-item')],[MODELS[5]])
    case('acyclic-rt-chain',[('A','B','rt'),('B','C','rt')],[])
    case('si-macro-singleton-self-loop',[('A','B','ww'),('B','A','rw-predicate')],[MODELS[3],MODELS[4],MODELS[5]])
    case('acyclic-parallel-item-and-predicate',[('A','B','rw-item'),('A','B','rw-predicate')],[])
    # Freeze hand expectations before evaluating the reference.
    dump=lambda name,value:(out/name).write_bytes((json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode())
    dump('manual-preregistered.json',manual)
    rng=random.Random(2026102102);generated=[];seen=set()
    kinds=['ww','wr','rw-item','rw-predicate','rt']
    while len(generated)<1000:
        n=rng.choice([3,4]);nodes=['T'+str(i) for i in range(n)];links=[]
        for a in nodes:
            for b in nodes:
                if a==b:continue
                for kind in kinds:
                    if kind=='rt' and a>b:continue
                    if rng.random()<.13:links.append((a,b,kind))
        g=graph(links,nodes);identity=canonical(g)
        if identity in seen:continue
        seen.add(identity);generated.append({'id':'independent-%04d'%len(generated),'graph':g})
    dump('generated-inputs.json',generated)
    results=[];differences=[]
    for record in manual+generated:
        result=analyze(record['graph'])
        if 'expectedRefuted' in record and record['expectedRefuted']!=result['refuted']:
            differences.append({'id':record['id'],'expected':record['expectedRefuted'],'actual':result})
        results.append({'id':record['id'],'inputSha256':SHA(json.dumps(record['graph'],sort_keys=True,separators=(',',':')).encode()),'reference':result})
    dump('independent-expectations.json',results)
    source=ROOT/'artifacts/classification-v3-draft'
    references=[]
    for relative in ['contract.md','test-design.json','review-gates.md','primary-references-host/MIT-LCS-TR-786.pdf','primary-references-host/MIT-LCS-TR-786.txt','primary-references-host/txn.clj','primary-references-host/graph.clj','primary-references-host/consistency_model.clj']:
        data=(source/relative).read_bytes();references.append({'file':'artifacts/classification-v3-draft/'+relative,'bytes':len(data),'sha256':SHA(data)})
    for name in ['graph_oracle.py','freeze.py']:(out/name).write_bytes((HERE/name).read_bytes())
    manifest={'schema':1,'passed':not differences,'scope':'Independent graph-layer draft only; no classification runtime or trace/source/INT/abstract-SI acceptance',
              'proposedModelIds':list(MODELS),'modelDefinitionsFrozenAsStable':False,'manualCases':len(manual),'generatedCases':len(generated),'isomorphismDistinctGeneratedGraphs':len(seen),
              'randomSeed':2026102102,'elementaryVsMacroChecks':len(results),'differences':differences,'productionOrElleCodeImported':False,
              'siAbstractExecutionsChecked':0,'actualDatabaseExecution':False,'formalPerformanceMeasurement':False,'primaryReferences':references,
              'files':{p.name:{'sha256':SHA(p.read_bytes()),'bytes':p.stat().st_size} for p in sorted(out.iterdir())},
              'unmetGates':['History/source adapter soundness and partial orders','Scoped INT/G1a/G1b mapping','Independent INT/EXT/PREFIX/NoConflict abstract execution oracle','Six canonical definitions and per-model incomplete coverage policy','Actual fixed Elle runtime and common-range conversion','Production category and absence-certificate comparison']}
    dump('manifest.json',manifest)
    print(json.dumps({'passed':manifest['passed'],'manual':len(manual),'generated':len(generated),'distinctUpToVertexRenaming':len(seen),'differences':len(differences),'directory':str(out.relative_to(ROOT)),'manifestSha256':SHA((out/'manifest.json').read_bytes())}))
    return 0 if manifest['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
