import { spawnSync } from 'node:child_process';
import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { root } from './moon.mjs';

await import('./build.mjs');
const local = resolve(root, '.local-toolchain.json');
const home = process.env.MOON_HOME || (existsSync(local) ? JSON.parse(readFileSync(local, 'utf8')).moonHome : '');
const result = spawnSync(process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3'), [resolve(root, 'scripts/package_release.py')], { cwd: root, stdio: 'inherit', env: { ...process.env, MTW_TOOLCHAIN_HOME: home, MTW_NODE: process.execPath } });
if (result.error) throw result.error;
if (result.status !== 0) throw new Error(`Package verification exited with ${result.status}`);
