#!/usr/bin/env node
import { openSync, readSync, closeSync, writeFileSync, existsSync, unlinkSync } from 'node:fs';
import { resolve } from 'node:path';
import { run_json, run_options_json, verify_certificate_json, shrink_json, compare_models_json, version } from './core.mjs';
import { makeCapsule, replayCapsule } from './evidence.mjs';

const help = `MoonTxnWitness v${version()}
用法：
  node dist/moontxnwitness.mjs check HISTORY.json [--format text|json|markdown|dot] [--output FILE] [--witness FILE]
  node dist/moontxnwitness.mjs verify HISTORY.json CERTIFICATE.json
  node dist/moontxnwitness.mjs shrink HISTORY.json [--output REDUCTION.json] [--history MINI.json]
  node dist/moontxnwitness.mjs compare-models HISTORY.json [--output COMPARISON.json]
  node dist/moontxnwitness.mjs replay CAPSULE.json
  check 也支持 --capsule FILE 导出含日志、报告和 SHA-256 的自包含复现包。
  check 支持 --profile balanced 使用 12 事务搜索和 v2 证据；默认 compat 保留旧接口行为。
  node dist/moontxnwitness.mjs --help | --version

check 支持以 - 从标准输入读取 UTF-8 JSON。模型由输入中的 model 选择。
输出文件必须尚不存在；不会覆盖输入或现有报告。--witness 导出精简环证据。
退出码：0 符合所选模型；1 确定异常；2 输入/执行/证据无效；3 无法判定。
结果只针对提供的唯一版本读写历史及版本顺序约束。不会连接数据库或上传数据。
`;

function readBounded(path, maximum) {
  const fd = path === '-' ? 0 : openSync(path, 'r');
  const chunks = [];
  let total = 0;
  try {
    for (;;) {
      const buffer = Buffer.alloc(Math.min(65536, maximum + 1 - total));
      const count = readSync(fd, buffer, 0, buffer.length, null);
      if (!count) break;
      total += count;
      if (total > maximum) throw new Error(`输入超过 ${maximum} 字节限制`);
      chunks.push(buffer.subarray(0, count));
    }
  } finally { if (fd !== 0) closeSync(fd); }
  return new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks));
}

function checkOutput(path, inputPaths, otherOutputs) {
  const absolute = resolve(path);
  if (inputPaths.some(p => p !== '-' && resolve(p) === absolute)) throw new Error('输出路径不能与输入相同');
  if (otherOutputs.includes(absolute)) throw new Error('报告和证据必须使用不同路径');
  if (existsSync(absolute)) throw new Error(`输出已存在，未覆盖：${path}`);
  otherOutputs.push(absolute);
}

function saveArtifacts(artifacts) {
  const owned = [];
  try {
    // Reserve every requested new file before writing either report or witness.
    for (const [path, content] of artifacts) owned.push({ path, content, fd: openSync(path, 'wx') });
    for (const item of owned) writeFileSync(item.fd, item.content, 'utf8');
  } catch (error) {
    for (const item of owned) {
      closeSync(item.fd); item.fd = null;
      unlinkSync(item.path);
    }
    throw error;
  } finally {
    for (const item of owned) if (item.fd !== null) closeSync(item.fd);
  }
}

function localArgs(tokens, allowed, count) {
  const options = Object.create(null);
  const paths = [];
  let literal = false;
  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];
    if (!literal && token === '--') { literal = true; continue; }
    if (!literal && allowed.includes(token)) {
      if (options[token] !== undefined) throw new Error(`选项重复：${token}`);
      if (!tokens[i + 1] || tokens[i + 1].startsWith('--')) throw new Error(`选项缺少值：${token}`);
      options[token] = tokens[++i];
    } else if (!literal && token.startsWith('-') && token !== '-') throw new Error(`未知选项：${token}`);
    else paths.push(token);
  }
  if (paths.length !== count) throw new Error(`需要 ${count} 个输入路径`);
  return { paths, options };
}

function emitJSON(result, output, inputs, companions = []) {
  const text = JSON.stringify(result, null, 2) + '\n';
  const paths = [];
  const artifacts = [...companions];
  if (output) artifacts.push([output, text]);
  for (const [path] of artifacts) checkOutput(path, inputs, paths);
  saveArtifacts(artifacts);
  if (output) {
    console.error(`结果已保存：${output}`);
  } else process.stdout.write(text);
}

try {
  const args = process.argv.slice(2);
  if (args.length === 1 && args[0] === '--version') {
    console.log(version());
  } else if (!args.length || (args.length === 1 && args[0] === '--help')) {
    process.stdout.write(help);
  } else if (args[0] === 'verify') {
    if (args.length !== 3 || args[1] === '-' || args[2] === '-') throw new Error('verify 需要历史文件和证据文件两个路径');
    const result = JSON.parse(verify_certificate_json(readBounded(args[1], 2 * 1024 * 1024), readBounded(args[2], 32 * 1024 * 1024)));
    console.log(JSON.stringify(result, null, 2));
    process.exitCode = result.valid ? 0 : 2;
  } else if (args[0] === 'compare-models') {
    const { paths, options } = localArgs(args.slice(1), ['--output'], 1);
    const result = JSON.parse(compare_models_json(readBounded(paths[0], 2 * 1024 * 1024)));
    emitJSON(result, options['--output'], paths);
    process.exitCode = !result.valid ? 2 : result.classification === 'inconclusive' ? 3 : 0;
  } else if (args[0] === 'replay') {
    const { paths } = localArgs(args.slice(1), [], 1);
    const result = replayCapsule(readBounded(paths[0], 32 * 1024 * 1024));
    emitJSON(result, undefined, paths);
    process.exitCode = result.valid ? 0 : 2;
  } else if (args[0] === 'shrink') {
    const { paths, options } = localArgs(args.slice(1), ['--output', '--history'], 1);
    const result = JSON.parse(shrink_json(readBounded(paths[0], 2 * 1024 * 1024)));
    const companions = [];
    if (options['--history']) {
      if (!result.reducedHistory) throw new Error('无有效的缩减历史可导出');
      companions.push([options['--history'], JSON.stringify(result.reducedHistory, null, 2) + '\n']);
    }
    emitJSON(result, options['--output'], paths, companions);
    process.exitCode = ['reduced', 'unchanged'].includes(result.status) ? 0 : ['budget', 'skipped'].includes(result.status) ? 3 : 2;
  } else if (args[0] === 'check') {
    let format = 'text';
    let output;
    let witness;
    let replayFile;
    let profile = 'compat';
    let input;
    let literal = false;
    const used = new Set();
    for (let i = 1; i < args.length; i++) {
      const token = args[i];
      if (!literal && token === '--') { literal = true; continue; }
      if (!literal && ['--format', '--output', '--witness', '--capsule', '--profile'].includes(token)) {
        if (used.has(token)) throw new Error(`选项重复：${token}`);
        used.add(token);
        if (!args[i + 1] || args[i + 1].startsWith('--')) throw new Error(`选项缺少值：${token}`);
        const value = args[++i];
        if (token === '--format') format = value;
        if (token === '--output') output = value;
        if (token === '--witness') witness = value;
        if (token === '--capsule') replayFile = value;
        if (token === '--profile') profile = value;
      } else if (!literal && token.startsWith('-') && token !== '-') {
        throw new Error(`未知选项：${token}`);
      } else {
        if (input !== undefined) throw new Error('check 每次接受一个历史文件');
        input = token;
      }
    }
    if (input === undefined) throw new Error('缺少历史文件路径');
    if (!['text', 'json', 'markdown', 'dot'].includes(format)) throw new Error('format 必须为 text、json、markdown 或 dot');
    if (!['compat', 'balanced'].includes(profile)) throw new Error('profile 必须为 compat 或 balanced');
    const outputs = [];
    if (output) checkOutput(output, [input], outputs);
    if (witness) checkOutput(witness, [input], outputs);
    if (replayFile) checkOutput(replayFile, [input], outputs);
    const historyText = readBounded(input, 2 * 1024 * 1024);
    const result = JSON.parse(profile === 'balanced' ? run_options_json(historyText, format) : run_json(historyText, format));
    if (witness && !result.report.witness) throw new Error('本次结果没有依赖环证据；直接读写异常保留在 findings 中');
    const artifacts = [];
    if (replayFile) artifacts.push([replayFile, makeCapsule(historyText, result.report)]);
    if (witness) {
      const { schemaVersion, tool, version: releaseVersion, status, model, witness: proof } = result.report;
      artifacts.push([witness, JSON.stringify({ schemaVersion: 1, tool, version: releaseVersion, status, model, witness: proof }, null, 2) + '\n']);
    }
    if (output) artifacts.push([output, result.output]);
    saveArtifacts(artifacts);
    if (output) {
      console.error(`报告已保存：${output}`);
    } else process.stdout.write(result.output);
    process.exitCode = result.exitCode;
  } else throw new Error('未知命令；请使用 --help 查看用法');
} catch (error) {
  console.error(`MoonTxnWitness: ${error.message}`);
  process.exitCode = 2;
}

// The host owns only bounded local I/O, argument validation and artifact transport.
// Transaction inference, cycle search, evidence checks and report rendering are MoonBit.
