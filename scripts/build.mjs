import { mkdirSync, copyFileSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { root, runMoon } from './moon.mjs';

runMoon(['build', '--target', 'js', '--release', '--deny-warn']);
const output = resolve(root, 'dist');
mkdirSync(output, { recursive: true });
copyFileSync(resolve(root, '_build/js/release/build/bridge/bridge.js'), resolve(output, 'core.mjs'));
copyFileSync(resolve(root, 'cmd/moontxnwitness.mjs'), resolve(output, 'moontxnwitness.mjs'));
copyFileSync(resolve(root, 'cmd/sdk.mjs'), resolve(output, 'sdk.mjs'));
const core = await import(pathToFileURL(resolve(output, 'core.mjs')).href + `?build=${Date.now()}`);
const packageVersion = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8')).version;
const sourceVersion = readFileSync(resolve(root, 'moon.mod'), 'utf8').match(/^version\s*=\s*"([^"]+)"/m)?.[1];
if (core.version() !== packageVersion || sourceVersion !== packageVersion) throw new Error('Source, package and compiled core versions differ');
const local = resolve(root, '.local-toolchain.json');
const home = process.env.MOON_HOME || (existsSync(local) ? JSON.parse(readFileSync(local, 'utf8')).moonHome : null);
let notices = 'MoonTxnWitness v' + packageVersion + '\nLicense: Apache-2.0\n\nCompiled with MoonBit. Portions of the compiled runtime use moonbitlang/core (Apache-2.0).\nSource: https://github.com/moonbitlang/core\n';
let runtimeLicense = false;
if (home) {
  const license = resolve(home, 'lib/core/LICENSE');
  if (existsSync(license)) { notices += '\n' + readFileSync(license, 'utf8'); runtimeLicense = true; }
  const notice = resolve(home, 'lib/core/NOTICE');
  if (existsSync(notice)) notices += '\n' + readFileSync(notice, 'utf8');
}
if (!runtimeLicense) notices += '\n' + readFileSync(resolve(root, 'LICENSE'), 'utf8');
writeFileSync(resolve(output, 'THIRD_PARTY_NOTICES.txt'), notices);
console.log(`Built MoonTxnWitness v${core.version()}: portable MoonBit core + local Node.js CLI.`);
