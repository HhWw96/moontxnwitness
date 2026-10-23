// Independently synthetic wire observations derived from a real fixture.
// This never connects to PostgreSQL or claims these changed rows were observed.
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const hash=text=>createHash('sha256').update(text).digest('hex');
const sorted=value=>Array.isArray(value)?value.map(sorted):value!==null&&typeof value==='object'
  ?Object.fromEntries(Object.keys(value).sort().map(key=>[key,sorted(value[key])])):value;
const wire=value=>JSON.stringify(sorted(value));

export function syntheticNonrepeatableProfile(originalEnvelopeText,originalSegmentText){
  const envelope=JSON.parse(originalEnvelopeText),trace=JSON.parse(envelope.traceText);
  const sources=envelope.sourceJournalText.trimEnd().split('\n').map(JSON.parse);
  const update=sources.find(row=>row.kind==='source-batch'&&row.operation==='update');
  if(!update)throw Error('Expected real supported update fixture');
  const effect=update.observation.effectRows[0],key=effect[0],oldVersion=effect[1],newVersion=effect[2];
  const reads=sources.filter(row=>row.kind==='source-batch'&&row.operation==='get'&&row.observation.source?.key===key);
  const earlier=reads.find(row=>row.observation.source.version===oldVersion);
  const changed=reads.find(row=>row.observation.source.version===newVersion);
  if(!earlier||!changed||earlier.tx===changed.tx||!reads.some(row=>row!==changed&&row.tx===changed.tx&&row.observation.source.version===newVersion))throw Error('Expected repeated positive read of the updated known ID');
  changed.observation=structuredClone(earlier.observation);
  changed.actualPGresult=structuredClone(earlier.actualPGresult);
  const delivered=trace.events.find(event=>event.seq===changed.businessRowsEvent);
  if(!delivered||delivered.kind!=='rows'||delivered.statement!==changed.statement||delivered.tx!==changed.tx)throw Error('Expected original delivered-row reference');
  delivered.rows=structuredClone(changed.observation.rows);
  delivered.serverRows=structuredClone(changed.observation.serverRows);
  const prefix=sources.slice(0,-1).map(row=>wire(row)+'\n').join('');
  sources.at(-1).prefixSha256=hash(prefix);
  envelope.sourceJournalText=prefix+wire(sources.at(-1))+'\n';
  envelope.traceText=wire(trace)+'\n';
  const segments=originalSegmentText.trimEnd().split('\n').map(JSON.parse);
  const raw=segments.find(event=>event.seq===delivered.seq);
  if(!raw||raw.kind!=='rows')throw Error('Expected raw original segment row');
  raw.rows=structuredClone(delivered.rows);raw.serverRows=structuredClone(delivered.serverRows);
  const segmentText=segments.map(row=>wire(row)+'\n').join('');
  const index=JSON.parse(envelope.journalIndexText);
  if(index.segments.length!==1)throw Error('First synthetic fixture requires original one-segment packet');
  index.segments[0].bytes=Buffer.byteLength(segmentText);index.segments[0].sha256=hash(segmentText);
  index.stats.bytesWritten=Buffer.byteLength(segmentText);
  delete index.indexSha256;index.indexSha256=hash(wire(index));
  envelope.journalIndexText=wire(index)+'\n';
  const envelopeText=wire(envelope)+'\n';
  return {envelopeText,segmentText,manifest:{schema:1,kind:'synthetic-nonrepeatable-read-from-actual-base-user-parameters',
    actualDatabaseExecution:false,actualPostgresAnomaly:false,databaseAuthenticityClaim:false,
    originalEnvelopeSha256:hash(originalEnvelopeText),originalSegmentSha256:hash(originalSegmentText),
    envelopeSha256:hash(envelopeText),segmentSha256:hash(segmentText),
    changedSourceSeq:changed.sourceSeq,changedStatement:changed.statement,changedRowsSeq:changed.businessRowsEvent,
    changedTransaction:changed.tx,copiedObservationSourceSeq:earlier.sourceSeq,key,
    replacedFirstReadVersion:newVersion,syntheticFirstReadVersion:oldVersion,secondReadRetainsVersion:newVersion,
    explanation:'Copies an earlier known committed version and its six delivered/eight native fields into the first of two reads in one later transaction. The second read retains its new version, producing nonrepeatable-read evidence. SQL, parameters, all write effects, version chains, initialization/finalization and lifecycle remain from the fixture. Source seal and changed segment/index are recomputed. This is synthetic wire evidence, not an actual PostgreSQL execution or authenticated capture.'}};
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const args=process.argv.slice(2),options={};
  for(let i=0;i<args.length;i+=2){if(!['--source','--segment','--output'].includes(args[i])||!args[i+1]||options[args[i]])throw Error('Expected --source FILE --segment FILE --output NEW_DIRECTORY');options[args[i]]=resolve(args[i+1]);}
  if(!options['--source']||!options['--segment']||!options['--output'])throw Error('All three explicit paths required');
  const result=syntheticNonrepeatableProfile(readFileSync(options['--source'],'utf8'),readFileSync(options['--segment'],'utf8'));
  mkdirSync(options['--output']);
  for(const [name,text] of [['profile-source.json',result.envelopeText],['segment-000001.jsonl',result.segmentText],['manifest.json',JSON.stringify(result.manifest,null,2)+'\n']])writeFileSync(resolve(options['--output'],name),text,{flag:'wx'});
  console.log(JSON.stringify(result.manifest,null,2));
}
