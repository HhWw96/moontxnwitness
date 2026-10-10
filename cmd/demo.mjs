#!/usr/bin/env node
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs';
import { resolve, basename } from 'node:path';
import { fileURLToPath } from 'node:url';
import { analyze, shrink, compareModels, version } from './sdk.mjs';
import { run_json } from './core.mjs';
import { makeCapsule, replayCapsule } from './evidence.mjs';

try {
  const args = process.argv.slice(2);
  if (args.length > 1 || (args.length === 1 && args[0] !== '--json')) throw new Error('用法：node dist/demo.mjs [--json]');
  const examples = fileURLToPath(new URL('../examples/', import.meta.url));
  const fixture = name => readFileSync(resolve(examples, name + '.json'), 'utf8');
  const cycle = analyze(fixture('write-skew'));
  const completion = analyze(fixture('unknown-order'));
  const impossible = analyze(fixture('fractured-observation'));
  const reduction = shrink(fixture('noisy-write-skew'));
  const models = compareModels(fixture('strict-realtime'));
  if (cycle.status !== 'violation' || cycle.witness?.edges.length !== 2 || completion.status !== 'consistent' || impossible.status !== 'violation' || reduction.status !== 'reduced' || !reduction.oneMinimal || reduction.reducedHistory.transactions.length !== 2 || models.classification !== 'realtime-only-violation') throw new Error('演示结果与示例预期不符');
  const miniText = JSON.stringify(reduction.reducedHistory, null, 2) + '\n';
  const rendered = JSON.parse(run_json(miniText, 'markdown'));
  const capsule = makeCapsule(miniText, rendered.report);
  const replay = replayCapsule(capsule);
  if (!replay.valid) throw new Error('演示复现包未通过复核');
  // Each invocation owns a fresh directory; existing reports are never overwritten.
  const directory = mkdtempSync(resolve(process.cwd(), 'moontxnwitness-demo-'));
  const artifacts = new Map([
    ['report.md', rendered.output],
    ['report.json', JSON.stringify(rendered.report, null, 2) + '\n'],
    ['reduction.json', JSON.stringify(reduction, null, 2) + '\n'],
    ['mini.json', miniText],
    ['models.json', JSON.stringify(models, null, 2) + '\n'],
    ['case.capsule.json', capsule],
    ['replay.json', JSON.stringify(replay, null, 2) + '\n'],
  ]);
  for (const [name, text] of artifacts) writeFileSync(resolve(directory, name), text, { encoding: 'utf8', flag: 'wx' });
  const receipt = { tool: 'MoonTxnWitness', version: version(), passed: true, outputDirectory: basename(directory), files: [...artifacts.keys()], cycleTransactions: cycle.witness.transactions, completion: completion.status, impossibleCompletion: impossible.status, reducedTransactions: 2, oneMinimal: reduction.oneMinimal, classification: models.classification, replayValid: replay.valid, examples: 'synthetic histories; not a reproduced database vulnerability' };
  writeFileSync(resolve(directory, 'demo.json'), JSON.stringify(receipt, null, 2) + '\n', { encoding: 'utf8', flag: 'wx' });
  if (args[0] === '--json') console.log(JSON.stringify(receipt));
  else console.log(`MoonTxnWitness v${version()} 演示完成\n1. 写偏斜：找到两事务异常环。\n2. 缺少版本顺序：搜索可行执行，并识别无解的混合观察。\n3. 日志缩减：7 个事务缩成 2 个，单事务删除检查通过。\n4. 模型对比：定位由实时先后约束造成的严格模型异常。\n5. 自包含复现包：摘要和核心判断复核通过。\n报告与证据已保存到 ${receipt.outputDirectory}，先打开 report.md 查看。\n这些异常均为合成示例。实际 SQLite 并发采集方法见 docs/sqlite-capture.md。`);
} catch (error) {
  console.error(`MoonTxnWitness demo: ${error.message}`);
  process.exitCode = 2;
}
