import {checkToolchain} from './toolchain-policy.mjs';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, resolve, delimiter } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

export const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
export function coreTestCount(directory = resolve(root, 'src')) {
  let count = 0;
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) count += coreTestCount(path);
    else if (entry.name.endsWith('.mbt')) count += (readFileSync(path, 'utf8').match(/^test\s+"/gm) || []).length;
  }
  return count;
}
export function runMoon(args) {
  const localPath = resolve(root, '.local-toolchain.json');
  const local = existsSync(localPath) ? JSON.parse(readFileSync(localPath, 'utf8')).moonHome : null;
  const home = process.env.MOON_HOME || local;
  checkToolchain(home);
  const env = { ...process.env };
  if (home) {
    env.MOON_HOME = home;
    const inherited = Object.entries(process.env).find(([key]) => key.toLowerCase() === 'path')?.[1] || '';
    for (const key of Object.keys(env)) if (key.toLowerCase() === 'path') delete env[key];
    env.PATH = [resolve(home, 'bin'), dirname(process.execPath), inherited].join(delimiter);
  }
  const binary = home ? resolve(home, 'bin', process.platform === 'win32' ? 'moon.exe' : 'moon') : 'moon';
  const result = spawnSync(binary, args, { cwd: root, env, stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`MoonBit exited with ${result.status}`);
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { runMoon(process.argv.slice(2)); } catch (e) { console.error(e.message); process.exitCode = 2; }
}
