import {spawnSync} from 'node:child_process';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

export const MINIMUM_COMPILER = '0.10.16';
export const PINNED_COMPILER = '0.10.16+b1a0e846e';

export function assertCompilerVersion(output) {
  const match = /^v?(\d+)\.(\d+)\.(\d+)(?:\+[A-Za-z0-9._]+)?(?:\s|$)/.exec(output.trim());
  if (!match) throw Error('Cannot identify a stable MoonBit compiler version');
  const actual = match.slice(1,4).map(Number), minimum = [0,10,16];
  if (actual.some(n=>!Number.isSafeInteger(n))) throw Error('Invalid compiler version');
  let comparison=0;
  for(let i=0;i<3&&!comparison;i++)comparison=Math.sign(actual[i]-minimum[i]);
  if(comparison<0)throw Error(`MoonBit compiler >= ${MINIMUM_COMPILER} is required; found ${match[0].trim()}`);
  return match[0].trim();
}

export function checkToolchain(home) {
  const suffix=process.platform==='win32'?'.exe':'';
  const binary=home?resolve(home,'bin/moonc'+suffix):'moonc';
  const result=spawnSync(binary,['-v'],{encoding:'utf8',windowsHide:true,env:{...process.env,...(home?{MOON_HOME:home}:{})}});
  if(result.error||result.status!==0)throw Error('Cannot execute the selected MoonBit compiler');
  return assertCompilerVersion(result.stdout+result.stderr);
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  try{console.log(JSON.stringify({compiler:checkToolchain(process.env.MOON_HOME),minimum:MINIMUM_COMPILER}));}
  catch(error){console.error(error.message);process.exitCode=1;}
}
