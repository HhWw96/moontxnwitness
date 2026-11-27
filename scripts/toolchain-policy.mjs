import {spawnSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const lock = JSON.parse(readFileSync(new URL('../.moonbit-toolchain.json', import.meta.url), 'utf8'));
export const MINIMUM_COMPILER = lock.minimumCompiler;
export const PINNED_COMPILER = lock.compiler;

const compilerVersion = /^(v?((?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*)){2})(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?)(?:\s|$)/;

function parseCompilerVersion(output) {
  const match = compilerVersion.exec(output.trim());
  if (!match) throw Error('Cannot identify a MoonBit compiler version');
  const release = match[2].split('.').map(Number);
  const prerelease = match[3]?.split('.') ?? [];
  if (release.some(n => !Number.isSafeInteger(n)) || prerelease.some(entry => /^0\d+$/.test(entry))) {
    throw Error('Invalid compiler version');
  }
  return {version: match[1], release, prerelease};
}

function comparePrereleases(left, right) {
  if (!left.length || !right.length) return Number(!left.length) - Number(!right.length);
  for (let index = 0; index < Math.min(left.length, right.length); index++) {
    const a = left[index], b = right[index];
    if (a === b) continue;
    const numericA = /^\d+$/.test(a), numericB = /^\d+$/.test(b);
    if (numericA !== numericB) return numericA ? -1 : 1;
    if (numericA && a.length !== b.length) return a.length - b.length;
    return a < b ? -1 : 1;
  }
  return left.length - right.length;
}

const minimum = parseCompilerVersion(MINIMUM_COMPILER);

export function assertCompilerVersion(output) {
  const actual = parseCompilerVersion(output);
  const releaseDifference = actual.release.map((value, index) => value - minimum.release[index]).find(value => value !== 0);
  const comparison = releaseDifference ?? comparePrereleases(actual.prerelease, minimum.prerelease);
  if (comparison < 0) {
    throw Error(`MoonBit compiler >= ${MINIMUM_COMPILER} is required; found ${actual.version}`);
  }
  return actual.version;
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
