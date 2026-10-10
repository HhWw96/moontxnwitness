import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { root, runMoon, coreTestCount } from './moon.mjs';

// Default tests cover the shipped JS runtime and both bundled Wasm runtimes.
// --all also executes native tests, requiring a supported system C compiler.
const args = process.argv.slice(2);
if (args.some(a => a !== '--all') || args.length > 1) throw new Error('Usage: node scripts/test.mjs [--all]');
const targets = args.includes('--all') ? ['js', 'wasm-gc', 'wasm', 'native'] : ['js', 'wasm-gc', 'wasm'];
runMoon(['fmt', '--check']);
runMoon(['check', '--target', 'all', '--deny-warn']);
for (const target of targets) runMoon(['test', '--target', target, '--deny-warn']);
await import('./build.mjs');
const oracle = (await import('./oracle.mjs')).runOracle();
const cli = (await import('./cli-test.mjs')).runCliTests();
const receipt = { tool: 'MoonTxnWitness', version: JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8')).version, passed: true, checkedTargets: ['js', 'wasm-gc', 'wasm', 'native'], executedTargets: targets, coreTestsPerTarget: coreTestCount(), oracleHistories: oracle.counts.exhaustive + oracle.counts.generated + oracle.counts.completion, verifiedCycleCertificates: oracle.counts.certificates, cliChecks: cli.checks, node: process.version, generatedAt: new Date().toISOString(), boundaries: ['SQLite workload does not certify the database globally', 'No public publish, remote CI run, organizer submission or award verification'] };
mkdirSync(resolve(root, 'verification'), { recursive: true });
writeFileSync(resolve(root, 'verification/summary.json'), JSON.stringify(receipt, null, 2) + '\n');
console.log(`MoonTxnWitness v${receipt.version} verification complete.`);
