"""Independent elementary-cycle oracle for the proposed six-model graph layer.

This is not a history/source validator or the independent SI abstract-execution
oracle. No production/classifier/Elle code is imported or executed.
"""
import json

MODELS=('adya-pl-1-v1','adya-pl-2-v1','adya-pl-2.99-v1','elle-generalized-si-v1','adya-pl-3-v1','strict-pl-ss-v1')
D={'ww','wr'}
A={'rw-item','rw-predicate'}


def cycles(nodes,edges):
    """Enumerate elementary directed cycles with each actual parallel edge choice."""
    adjacency={n:[] for n in nodes}
    for e in edges:adjacency[e['from']].append(e)
    out=[]
    for start in sorted(nodes):
        def visit(current,path,seen):
            for edge in adjacency[current]:
                target=edge['to']
                if target==start:out.append(path+[edge])
                elif target>start and target not in seen:visit(target,path+[edge],seen|{target})
        visit(start,[],{start})
    return out


def analyze(graph):
    nodes,edges=graph['nodes'],graph['edges']
    assert len(nodes)==len(set(nodes)) and len(nodes)<=5
    assert len({e['id'] for e in edges})==len(edges)
    assert all(e['kind'] in D|A|{'rt'} and e['from'] in nodes and e['to'] in nodes and e['from']!=e['to'] for e in edges)
    assert not cycles(nodes,[e for e in edges if e['kind']=='rt']),'RT itself must be a prevalidated strict partial order'
    ordinary=cycles(nodes,[e for e in edges if e['kind']!='rt'])
    all_cycles=cycles(nodes,edges)
    only=lambda c,kinds:all(e['kind'] in kinds for e in c)
    no_adjacent=lambda c:all(not(c[i]['kind'] in A and c[(i+1)%len(c)]['kind'] in A) for i in range(len(c)))
    witnesses={
        MODELS[0]:next((c for c in ordinary if only(c,{'ww'})),None),
        MODELS[1]:next((c for c in ordinary if only(c,D)),None),
        MODELS[2]:next((c for c in ordinary if only(c,D) or any(e['kind']=='rw-item' for e in c)),None),
        MODELS[3]:next((c for c in ordinary if no_adjacent(c)),None),
        MODELS[4]:next(iter(ordinary),None),
        MODELS[5]:next(iter(all_cycles),None),
    }
    # A separate relation-composition crosscheck consumes original edge IDs.
    # Keep self loops in H and never silently prune the expanded closed walk.
    macro=[]
    for first in edges:
        if first['kind'] not in D:continue
        macro.append({'id':'d:'+first['id'],'from':first['from'],'to':first['to'],'parts':[first]})
        for second in edges:
            if second['kind'] in A and first['to']==second['from']:
                macro.append({'id':'da:'+first['id']+':'+second['id'],'from':first['from'],'to':second['to'],'parts':[first,second]})
    h_cycles=cycles(nodes,macro)
    assert bool(h_cycles)==(witnesses[MODELS[3]] is not None),'H vs elementary nonadjacency mismatch'
    expanded=None
    if h_cycles:
        expanded=[part for m in h_cycles[0] for part in m['parts']]
        assert all(expanded[i]['to']==expanded[(i+1)%len(expanded)]['from'] for i in range(len(expanded)))
        assert no_adjacent(expanded)
    return {'refuted':[m for m in MODELS if witnesses[m] is not None],
            'witnesses':{m:[e['id'] for e in c] for m,c in witnesses.items() if c is not None},
            'elementaryCycles':len(ordinary),'macroCycles':len(h_cycles),
            'macroExpandedClosedWalk':None if expanded is None else [e['id'] for e in expanded],
            'scope':'Prevalidated complete committed typed graph only; G1a/G1b/INT/source coverage are separate unmet gates',
            'siAbstractExecutionOracleExecuted':False}


if __name__=='__main__':
    import sys
    print(json.dumps(analyze(json.load(open(sys.argv[1],encoding='utf8'))),separators=(',',':')))
