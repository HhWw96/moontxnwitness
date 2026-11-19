import {spawnSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const lock = JSON.parse(readFileSync(new URL('../.moonbit-toolchain.json', import.meta.url), 'utf8'));
export const MINIMUM_COMPILER = lock.minimumCompiler;
export const PINNED_COMPILER = lock.compiler;

export function assertCompilerVersion(output) {
  const match = /^v?(\d+)\.(\d+)\.(\d+)(?:\+[A-Za-z0-9._]+)?(?:\s|$)/.exec(output.trim());
  if (!match) throw Error('Cannot identify a stable MoonBit compiler version');
  const actual = match.slice(1,4).map(Number), minimum = MINIMUM_COMPILER.split('.').map(Number);
  if (actual.some(n=>!Number.isSafeInteger(n))) throw Error('Invalid compiler version');
  let comparison=0;
  for(let i=0;i<3&&!comparison;i++)comparison=Math.sign(actual[i]-minimum[i]);
  if(comparison<0)throw Error(`MoonBit compiler >= ${MINIMUM_COMPILER} is required; found ${match[0].trim()}`);
  return match[0].trim();
}

export function assertPinnedCompilerVersion(output) {
  const actual = assertCompilerVersion(output);
  if (actual.replace(/^v/, '') !== PINNED_COMPILER) {
    throw Error(`MoonBit compiler ${PINNED_COMPILER} is required for CI; found ${actual}`);
  }
  return actual;
}

export function checkToolchain(home) {
  const suffix=process.platform==='win32'?'.exe':'';
  const binary=home?resolve(home,'bin/moonc'+suffix):'moonc';
  const result=spawnSync(binary,['-v'],{encoding:'utf8',windowsHide:true,env:{...process.env,...(home?{MOON_HOME:home}:{})}});
  if(result.error||result.status!==0)throw Error('Cannot execute the selected MoonBit compiler');
  const verify = process.env.CI === 'true' ? assertPinnedCompilerVersion : assertCompilerVersion;
  return verify(result.stdout+result.stderr);
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  try{console.log(JSON.stringify({compiler:checkToolchain(process.env.MOON_HOME),minimum:MINIMUM_COMPILER,pinned:PINNED_COMPILER}));}
  catch(error){console.error(error.message);process.exitCode=1;}
}
