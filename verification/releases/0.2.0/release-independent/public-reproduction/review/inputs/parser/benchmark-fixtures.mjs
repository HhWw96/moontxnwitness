// Deterministic workload definitions; no production inference rules are reused.
const read = (key, version) => ({ type: 'read', key, version });
const write = (key, version) => ({ type: 'write', key, version });
const tx = (id, ops) => ({ id, status: 'committed', ops });
export function noisy(n) {
  const initial = { x: 'x0', y: 'y0' };
  const transactions = [];
  for (let i = 0; i < n - 2; i++) {
    initial[`noise${i}`] = 'initial';
    transactions.push(tx(`noise${i}`, [read(`noise${i}`, 'initial')]));
  }
  transactions.push(tx('A', [read('x', 'x0'), write('y', 'y1')]), tx('B', [read('y', 'y0'), write('x', 'x1')]));
  return { schemaVersion: 1, initial, transactions };
}
export function completion(n, impossible = true) {
  return { schemaVersion: 1, initial: { x: 'x0', y: 'y0', z: 'z0' }, transactions: [
    ...Array.from({ length: n - 3 }, (_, i) => tx(`N${i}`, Array.from({length: 12}, () => read('z', 'z0')))),
    tx('A', [write('x', 'x1'), write('y', 'y1')]),
    tx('B', [write('x', 'x2'), write('y', 'y2')]),
    tx('R', [read('x', 'x1'), read('y', impossible ? 'y2' : 'y1')]),
  ] };
}
export function fixtures() {
  const result = [];
  for (const n of [96,192,316]) result.push({ name: `dense-rt-${n}`, group:'graph', status:'consistent', history:{ model:'strict-serializable', initial:{}, transactions:Array.from({length:n},(_,i)=>({...tx(`T${i}`,[]),start:i*3,end:i*3+1})) } });
  const initial = {}; const transactions=[];
  for(let i=0;i<512;i++){initial[`k${i}`]='v0';transactions.push(tx(`T${i}`,[read(`k${i}`,'v0'),write(`k${i}`,'v1')]));}
  result.push({name:'sparse-512',group:'graph',status:'consistent',history:{initial,transactions}});
  for(const n of [32,128]){
    const initial=Object.fromEntries(Array.from({length:n},(_,i)=>[`k${i}`,'v0']));
    result.push({name:`long-ring-${n}`,group:'graph',status:'violation',cycle:n,history:{initial,transactions:Array.from({length:n},(_,i)=>tx(`T${i}`,[read(`k${i}`,'v0'),write(`k${(i+n-1)%n}`,'v1')]))}});
  }
  result.push({name:'small-cycle-noise-64',group:'graph',status:'violation',cycle:2,history:noisy(64)});
  for(const n of [6,7,8]) result.push({name:`completion-impossible-${n}`,group:'search',status:'violation',history:completion(n)});
  result.push({name:'completion-possible-8',group:'control',status:'consistent',history:completion(8,false)});
  result.push({name:'small-positive',group:'control',status:'consistent',history:{initial:{x:'v0'},transactions:[tx('A',[read('x','v0')])]}});
  for(const n of [7,32,64])result.push({name:`reduction-${n}`,group:'reduction',operation:'shrink',status:'reduced',history:noisy(n)});
  return result;
}
