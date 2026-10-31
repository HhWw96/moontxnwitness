#!/usr/bin/env node
import { openSync, readSync, closeSync, writeFileSync, existsSync, unlinkSync } from 'node:fs';
import { resolve } from 'node:path';
import { run_json, run_options_json, verify_certificate_json, shrink_json, shrink_options_json, compare_models_json, version } from './core.mjs';
import { makeCapsule, replayCapsule, makeCapsuleV3, replayCapsuleV3 } from './evidence.mjs';
import { normalizeCaptureV3, analyzeV3, reduceV3, verifyV3, inspectExecutionFailuresV3, inspectOrmSourceV3 } from './sdk.mjs';
import { analyzeOrmProfileV3, reduceOrmProfileV3, verifyOrmProfileV3,
  makeOrmProfileCapsuleV3, makeOrmProfileReductionCapsuleV3, replayOrmProfileCapsuleV3 } from './orm-profile.mjs';
import { classifyModelsV3, verifyModelsClassificationV3, makeModelsClassificationCapsuleV3,
  replayModelsClassificationCapsuleV3 } from './classification-models.mjs';
import { classifyV3, reduceClassificationV3, verifyClassificationV3, makeClassificationCapsuleV3,
  makeClassificationReductionCapsuleV3, replayClassificationCapsuleV3 } from './classification.mjs';

import { diagnoseV3, verifyDiagnosisV3 } from './diagnosis.mjs';
import {classifyRelationPredicateV4,verifyRelationPredicateClassificationV4,makeRelationPredicateClassificationCapsuleV4,
  classifyRelationV4,verifyRelationClassificationV4,inspectCaptureAnomaliesV4,verifyCaptureAnomaliesV4,
  inspectInternalConsistencyV4,verifyInternalConsistencyV4,makeRelationClassificationCapsuleV4,makeCaptureAnomaliesCapsuleV4,
  makeInternalConsistencyCapsuleV4,replayRelationCapsuleV4,parseSourceRulesOptionsV4} from './relation-v4.mjs';
import {reduceRelationCategoryV4,verifyRelationCategoryReductionV4,makeRelationCategoryReductionCapsuleV4,
  replayRelationCategoryReductionCapsuleV4,parseRelationReductionOptionsV4} from './relation-reduction-v4.mjs';
import {analyzeV4, classifyV4, reduceV4, verifyV4, verifyClassificationV4, verifyReductionV4,
  makeCapsuleV4, makeClassificationCapsuleV4, makeReductionCapsuleV4, replayCapsuleV4,
  inspectAnomaliesV4, verifyAnomaliesV4, makeAnomaliesCapsuleV4, inspectLostUpdatesV4, verifyLostUpdatesV4, makeLostUpdatesCapsuleV4, parseOptionsV4} from './v4.mjs';

import { analyzeModelProfileV3, verifyModelProfileV3, makeModelProfileCapsuleV3,
  replayModelProfileCapsuleV3 } from './model-profile.mjs';

import {classifyModelsV4,verifyModelsV4,makeModelsCapsuleV4,replayModelsCapsuleV4,parseModelOptionsV4} from "./models-v4.mjs";

const help = `MoonTxnWitness v${version()}
用法：
  node dist/moontxnwitness.mjs classify-models-v4 SOURCE.json [--options OPTIONS.json] [--models elle-core|NAME,...] [--list-profile native|captured-list-prefix-state/v2|captured-list-original-serial/v1] [--output REPORT.json] [--capsule CAPSULE.json]
  node dist/moontxnwitness.mjs verify-models-v4 SOURCE.json REPORT.json [--options EXPECTED.json] [--models elle-core|NAME,...] [--list-profile PROFILE]
  node dist/moontxnwitness.mjs replay-models-v4 CAPSULE.json [--options EXPECTED.json] [--models elle-core|NAME,...] [--list-profile PROFILE]
  node dist/moontxnwitness.mjs check HISTORY.json [--format text|json|markdown|dot] [--output FILE] [--witness FILE]
  node dist/moontxnwitness.mjs verify HISTORY.json CERTIFICATE.json
  node dist/moontxnwitness.mjs reduce-relation-category-v4 SOURCE.json --category G2-item [--options OPTIONS.json] [--max-checks 256] [--output REPORT.json] [--source REDUCED.json] [--capsule CAPSULE.json]
  node dist/moontxnwitness.mjs verify-relation-category-reduction-v4 SOURCE.json REPORT.json --category G2-item [--options EXPECTED.json]
  node dist/moontxnwitness.mjs replay-relation-category-reduction-v4 CAPSULE.json --category G2-item [--options EXPECTED.json]
  node dist/moontxnwitness.mjs classify-relation-predicate-v4 SOURCE.json --options OPTIONS.json [--output REPORT.json] [--capsule CAPSULE.json]
  node dist/moontxnwitness.mjs verify-relation-predicate-v4 SOURCE.json REPORT.json --options EXPECTED.json [--output VERIFIED.json]
  node dist/moontxnwitness.mjs classify-relation-v4 SOURCE.json [--options OPTIONS.json] [--output REPORT.json] [--capsule CAPSULE.json]
  node dist/moontxnwitness.mjs verify-relation-classification-v4 SOURCE.json REPORT.json [--options EXPECTED.json] [--output VERIFIED.json]
  node dist/moontxnwitness.mjs inspect-capture-anomalies-v4 SOURCE.json [--options OPTIONS.json] [--max-checks N] [--output REPORT.json] [--capsule CAPSULE.json]
  node dist/moontxnwitness.mjs verify-capture-anomalies-v4 SOURCE.json REPORT.json [--options EXPECTED.json] [--output VERIFIED.json]
  node dist/moontxnwitness.mjs inspect-internal-consistency-v4 SOURCE.json [--options OPTIONS.json] [--max-checks N] [--output REPORT.json] [--capsule CAPSULE.json]
  node dist/moontxnwitness.mjs verify-internal-consistency-v4 SOURCE.json REPORT.json [--options EXPECTED.json] [--output VERIFIED.json]
  node dist/moontxnwitness.mjs replay-relation-v4 CAPSULE.json [--options EXPECTED.json] [--output REPLAY.json]
  node dist/moontxnwitness.mjs analyze-v4 SOURCE.json [--options OPTIONS.json] [--output REPORT.json] [--capsule CAPSULE.json]
  node dist/moontxnwitness.mjs classify-v4 SOURCE.json [--options OPTIONS.json] [--output REPORT.json] [--capsule CAPSULE.json]
  node dist/moontxnwitness.mjs reduce-v4 SOURCE.json --preserve serializable|strict-serializable [--options OPTIONS.json] [--max-checks N] [--output REPORT.json] [--source MINI.json] [--capsule CAPSULE.json]
  node dist/moontxnwitness.mjs verify-v4 SOURCE.json REPORT.json [--options EXPECTED.json] [--output VERIFIED.json]
  node dist/moontxnwitness.mjs verify-classification-v4 SOURCE.json REPORT.json [--options EXPECTED.json] [--output VERIFIED.json]
  node dist/moontxnwitness.mjs verify-reduction-v4 SOURCE.json REPORT.json --preserve serializable|strict-serializable [--options EXPECTED.json] [--output VERIFIED.json]
  node dist/moontxnwitness.mjs replay-v4 CAPSULE.json [--options EXPECTED.json] [--output REPLAY.json]
  node dist/moontxnwitness.mjs inspect-anomalies-v4 SOURCE.json [--options OPTIONS.json] [--max-checks N] [--output REPORT.json] [--capsule CAPSULE.json]
  node dist/moontxnwitness.mjs verify-anomalies-v4 SOURCE.json REPORT.json [--options EXPECTED.json] [--output VERIFIED.json]
  node dist/moontxnwitness.mjs inspect-lost-updates-v4 SOURCE.json [--options OPTIONS.json] [--max-checks N] [--output REPORT.json] [--capsule CAPSULE.json]
  node dist/moontxnwitness.mjs verify-lost-updates-v4 SOURCE.json REPORT.json [--options EXPECTED.json] [--output VERIFIED.json]
  node dist/moontxnwitness.mjs shrink HISTORY.json [--output REDUCTION.json] [--history MINI.json]
  node dist/moontxnwitness.mjs compare-models HISTORY.json [--output COMPARISON.json]
  node dist/moontxnwitness.mjs ingest TRACE.json [--output COVERAGE.json] [--history HISTORY.json]
  node dist/moontxnwitness.mjs ingest-presence TRACE2.json [--output COVERAGE.json] [--history HISTORY.json]
  node dist/moontxnwitness.mjs replay CAPSULE.json
  node dist/moontxnwitness.mjs diagnose-v3 TRACE3.json [--options OPTIONS.json] [--output REPORT.json]
  node dist/moontxnwitness.mjs verify-diagnosis-v3 TRACE3.json REPORT.json [--options OPTIONS.json] [--output VERIFIED.json]
  node dist/moontxnwitness.mjs ingest-v3 TRACE3.json [--output NORMALIZED.json]
  node dist/moontxnwitness.mjs check-v3 TRACE3.json [--output REPORT.json] [--capsule CAPSULE.json]
  node dist/moontxnwitness.mjs reduce-v3 TRACE3.json [--output REDUCTION.json] [--capture MINI.json] [--max-checks N]
  node dist/moontxnwitness.mjs verify-v3 TRACE3.json REPORT.json
  node dist/moontxnwitness.mjs replay-v3 CAPSULE.json
  node dist/moontxnwitness.mjs failures-v3 TRACE3.json [--output FAILURES.json]
  node dist/moontxnwitness.mjs inspect-orm-source-v3 TRACE3.json SOURCE2.jsonl [--output SOURCES.json]
  node dist/moontxnwitness.mjs orm-profile-v3 PROFILE_SOURCE.json [--options OPTIONS.json] [--output REPORT.json] [--capsule CAPSULE.json]
  node dist/moontxnwitness.mjs shrink-orm-profile-v3 PROFILE_SOURCE.json [--options OPTIONS.json] [--max-checks N] [--output REDUCTION.json] [--history MINI.json] [--capsule CAPSULE.json]
  node dist/moontxnwitness.mjs replay-orm-profile-v3 CAPSULE.json [--output REPLAY.json]
  node dist/moontxnwitness.mjs verify-orm-profile-v3 PROFILE_SOURCE.json REPORT.json [--options OPTIONS.json] [--output VERIFIED.json]
  node dist/moontxnwitness.mjs classify-models-v3 TRACE_OR_BOUND_SOURCE.json [--options MODELS.json] [--output REPORT.json] [--capsule CAPSULE.json]
  node dist/moontxnwitness.mjs verify-models-classification-v3 SOURCE.json REPORT.json [--options MODELS.json] [--output VERIFIED.json]
  node dist/moontxnwitness.mjs replay-models-classification-v3 CAPSULE.json [--output REPLAY.json]
  node dist/moontxnwitness.mjs classify-v3 TRACE3.json [--options OPTIONS.json] [--output REPORT.json] [--capsule CAPSULE.json]
  node dist/moontxnwitness.mjs shrink-classification-v3 TRACE3.json --category G0|G1c|G2-item [--max-checks N] [--options REDUCTION_OPTIONS.json] [--output REPORT.json] [--capture MINI.json] [--capsule CAPSULE.json]
  node dist/moontxnwitness.mjs verify-classification-v3 TRACE3.json REPORT.json [--options OPTIONS.json] [--output VERIFIED.json]
  node dist/moontxnwitness.mjs replay-classification-v3 CAPSULE.json [--output REPLAY.json]
  node dist/moontxnwitness.mjs model-profile-v3 MODEL_SOURCE.json [--options OPTIONS.json] [--output REPORT.json] [--capsule CAPSULE.json]
  node dist/moontxnwitness.mjs replay-model-profile-v3 CAPSULE.json [--output REPLAY.json]
  node dist/moontxnwitness.mjs verify-model-profile-v3 MODEL_SOURCE.json REPORT.json [--options OPTIONS.json] [--output VERIFIED.json]
  ingest-v3/check-v3/reduce-v3 可选 --sql-proof dislock-f9946f0-sql-proof-1 核验固定 SQL 来源；默认保留原 v3 规则。
  check 也支持 --capsule FILE 导出含日志、报告和 SHA-256 的自包含复现包。
  check 支持 --profile balanced 使用 12 事务搜索和 v2 证据；默认 compat 保留旧接口行为。
  node dist/moontxnwitness.mjs --help | --version

check 支持以 - 从标准输入读取 UTF-8 JSON。模型由输入中的 model 选择。
ingest 用 MoonBit 校验自动采集记录；只有 ready 状态才可导出历史。ready 不表示历史符合隔离模型。
ingest-presence 为实验入口，校验固定键普通表的存在性与版本来源；不代表支持任意 SQL。
输出文件必须尚不存在；不会覆盖输入或现有报告。--witness 导出精简环证据。
退出码：0 符合所选模型；1 确定异常；2 输入/执行/证据无效；3 无法判定。
failures-v3 的退出码 0 仅表示诊断输入有效；即使记录了故障也为 0，不表示无故障、采集完整或模型符合。
inspect-orm-source-v3 为固定 FastAPI Users SQLAlchemy 7.0.0/PG18 来源诊断；0 仅表示局部来源证明成功，完整历史仍无法判定；2 表示局部证明失败。
orm-profile-v3 是显式安装来源并完整观察engine借还窗口的base-user点CRUD入口；原通用诊断缺口保留，不代表任意ORM/SQL。
profile限制：来源包64MiB、4原文分别8/16/8/2MiB、选项4KiB、报告64MiB、胶囊128MiB；精确搜索12事务/512操作/128键，候选语义复验最多256次，缓存查找/尝试总数分列。
profile只对证明完整的原始派生事实做事务删除；无法证明/预算不足保留无法判定。profile重放退出0只表示当前算法逐项重算相符，无法判定事实保持。
classify-v3 只检查点寄存器的指定依赖环类别；checked-compatible不代表符合完整隔离模型。分类缩减固定原类别并重验来源，预算不足不宣称单最小。
分类限制：原记录8MiB、分类选项4KiB/缩减选项8KiB、核心报告32MiB、host报告64MiB、胶囊128MiB；128事务/4096操作/5万边，每类10万状态/100万边检查，256次候选检查。最终核验开销另列，不受候选次数限制。
分类退出码：1为已证伪类别（含完成缩减）；0为所选类别检查相容或重放一致；3为未知/不支持/预算不足；重放一致不将未知变为符合模型。
classify-models-v3 显式检查六个冻结模型定义；只支持所声明点寄存器/单追加列表范围，关系模型与模型保持缩减未支持。无完整来源、内部有效性、实时证据或预算时保持无法判定。
模型入口限制：原trace8MiB、严格来源包32MiB且每原文8MiB、选项8KiB、核心报告32MiB、host报告96MiB、胶囊192MiB。严格模型不会从事件time或BEGIN推断实时顺序/快照。
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
  } else if (['classify-models-v4','verify-models-v4','replay-models-v4'].includes(args[0])) {
    const command=args[0],isVerify=command==='verify-models-v4',isReplay=command==='replay-models-v4';
    const {paths,options}=localArgs(args.slice(1),['--options','--models','--list-profile','--output',...(!isVerify&&!isReplay?['--capsule']:[])],isVerify?2:1);
    const inputs=[...paths,...(options['--options']?[options['--options']]:[])];
    if(inputs.filter(p=>p==='-').length>1)throw new Error('Only one model input may use standard input');
    const requested=options['--options']?parseModelOptionsV4(readBounded(options['--options'],8192)):{};
    if(options['--models']!==undefined){if(Object.hasOwn(requested,'models'))throw new Error('models must be supplied once');requested.models=options['--models']==='elle-core'?'elle-core':options['--models'].split(',');}
    if(options['--list-profile']!==undefined){if(Object.hasOwn(requested,'listProfile'))throw new Error('listProfile must be supplied once');requested.listProfile=options['--list-profile'];}
    const source=readBounded(paths[0],isReplay?64*1024*1024:8*1024*1024),companions=[];let result;
    if(isReplay)result=replayModelsCapsuleV4(source,requested);
    else if(isVerify)result=verifyModelsV4(source,readBounded(paths[1],32*1024*1024),requested);
    else if(options['--capsule']){const capsule=makeModelsCapsuleV4(source,requested);result=JSON.parse(JSON.parse(capsule).reportText);companions.push([options['--capsule'],capsule+'\n']);}
    else result=classifyModelsV4(source,requested);
    emitJSON(result,options['--output'],inputs,companions);
    process.exitCode=isVerify||isReplay?(result.valid===true?0:2):result.status==='checked-compatible'?0:result.status==='refuted'?1:result.status==='invalid'?2:3;
  } else if (['reduce-relation-category-v4','verify-relation-category-reduction-v4','replay-relation-category-reduction-v4'].includes(args[0])) {
    const command=args[0],isVerify=command.startsWith('verify-'),isReplay=command.startsWith('replay-');
    const {paths,options}=localArgs(args.slice(1),['--category','--options','--max-checks','--output',...(!isVerify&&!isReplay?['--source','--capsule']:[])],isVerify?2:1);
    const inputs=[...paths,...(options['--options']?[options['--options']]:[])];
    if(inputs.filter(p=>p==='-').length>1)throw new Error('Only one relation reduction input may use standard input');
    const requested=options['--options']?parseRelationReductionOptionsV4(readBounded(options['--options'],8192)):{};
    if(options['--category']!==undefined){if(Object.hasOwn(requested,'category'))throw new Error('category must be specified once');requested.category=options['--category'];}
    if(options['--max-checks']!==undefined){if(Object.hasOwn(requested,'maxChecks')||!/^(0|[1-9][0-9]*)$/.test(options['--max-checks']))throw new Error('maxChecks must be specified once as an integer');requested.maxChecks=Number(options['--max-checks']);}
    const source=readBounded(paths[0],isReplay?64*1024*1024:8*1024*1024),companions=[];
    let result;
    if(isReplay)result=replayRelationCategoryReductionCapsuleV4(source,requested);
    else if(isVerify)result=verifyRelationCategoryReductionV4(source,readBounded(paths[1],32*1024*1024),requested);
    else if(options['--capsule']){const capsule=makeRelationCategoryReductionCapsuleV4(source,requested);result=JSON.parse(JSON.parse(capsule).reportText);companions.push([options['--capsule'],capsule+'\n']);}
    else result=reduceRelationCategoryV4(source,requested);
    if(options['--source'])companions.push([options['--source'],JSON.stringify(result.history,null,2)+'\n']);
    emitJSON(result,options['--output'],inputs,companions);
    process.exitCode=isVerify||isReplay?(result.valid===true?0:2):result.status==='invalid'?2:['reduced','unchanged'].includes(result.status)?1:result.status==='not-refuted'?0:3;
  } else if (['classify-relation-predicate-v4','verify-relation-predicate-v4','classify-relation-v4','verify-relation-classification-v4','inspect-capture-anomalies-v4','verify-capture-anomalies-v4','inspect-internal-consistency-v4','verify-internal-consistency-v4','replay-relation-v4'].includes(args[0])) {
    const command=args[0],isReplay=command==='replay-relation-v4',isVerify=command.startsWith('verify-');
    const predicate=command.includes('relation-predicate-v4');
    const relation=predicate||command.includes('relation-classification')||command==='classify-relation-v4';
    const internal=command.includes('internal-consistency');
    const {paths,options}=localArgs(args.slice(1),['--options','--output',...(!isReplay&&!isVerify?['--capsule']:[]),...(!isReplay&&!isVerify&&!relation?['--max-checks']:[])],isVerify?2:1);
    const inputs=[...paths,...(options['--options']?[options['--options']]:[])];
    if(inputs.filter(path=>path==='-').length>1)throw new Error('Only one source rules input may use standard input');
    const source=readBounded(paths[0],isReplay?64*1024*1024:8*1024*1024);
    let requested=options['--options']===undefined?undefined:parseSourceRulesOptionsV4(readBounded(options['--options'],8192));
    if(options['--max-checks']!==undefined){
      requested=requested===undefined?{}:requested;
      if(Object.hasOwn(requested,'maxChecks')||!/^(0|[1-9][0-9]*)$/.test(options['--max-checks']))throw new Error('maxChecks must be specified once as an integer');
      requested.maxChecks=Number(options['--max-checks']);
    }
    const companions=[];let result;
    if(isReplay)result=replayRelationCapsuleV4(source,requested);
    else if(isVerify){
      const supplied=readBounded(paths[1],32*1024*1024);
      result=predicate?verifyRelationPredicateClassificationV4(source,supplied,requested):relation?verifyRelationClassificationV4(source,supplied,requested):internal?verifyInternalConsistencyV4(source,supplied,requested):verifyCaptureAnomaliesV4(source,supplied,requested);
    }else if(options['--capsule']){
      const capsule=predicate?makeRelationPredicateClassificationCapsuleV4(source,requested):relation?makeRelationClassificationCapsuleV4(source,requested):internal?makeInternalConsistencyCapsuleV4(source,requested):makeCaptureAnomaliesCapsuleV4(source,requested);
      result=JSON.parse(JSON.parse(capsule).reportText);companions.push([options['--capsule'],capsule+'\n']);
    }else result=predicate?classifyRelationPredicateV4(source,requested):relation?classifyRelationV4(source,requested):internal?inspectInternalConsistencyV4(source,requested):inspectCaptureAnomaliesV4(source,requested);
    emitJSON(result,options['--output'],inputs,companions);
    const status=result.judgment?.status??result.status;
    process.exitCode=isVerify||isReplay?(result.valid===true?0:2):['invalid','invalid-budget'].includes(status)?2:status==='refuted'?1:['checked','checked-compatible'].includes(status)?0:3;
  } else if (['analyze-v4','classify-v4','reduce-v4','verify-v4','verify-classification-v4','verify-reduction-v4','replay-v4','inspect-anomalies-v4','verify-anomalies-v4','inspect-lost-updates-v4','verify-lost-updates-v4'].includes(args[0])) {
    const command=args[0],isVerify=command.startsWith('verify-'),isReplay=command==='replay-v4';
    const isReduction=command==='reduce-v4'||command==='verify-reduction-v4';
    const isLostUpdates=command==='inspect-lost-updates-v4'||command==='verify-lost-updates-v4';
    const isInspection=isLostUpdates||command==='inspect-anomalies-v4'||command==='verify-anomalies-v4';
    const allowed=['--options','--output',...(!isVerify&&!isReplay?['--capsule']:[]),
      ...(isReduction?['--preserve','--max-checks']:isInspection?['--max-checks']:[]),...(command==='reduce-v4'?['--source']:[])];
    const {paths,options}=localArgs(args.slice(1),allowed,isVerify?2:1);
    const inputs=[...paths,...(options['--options']?[options['--options']]:[])];
    if(inputs.filter(path=>path==='-').length>1)throw new Error('Only one v4 input may use standard input');
    const text=readBounded(paths[0],isReplay?64*1024*1024:8*1024*1024);
    let requested=options['--options']===undefined?undefined:parseOptionsV4(readBounded(options['--options'],8192));
    if(options['--preserve']!==undefined||options['--max-checks']!==undefined){
      requested=requested===undefined?{}:requested;
      if(requested===null||typeof requested!=='object'||Array.isArray(requested))throw new Error('v4 options must be an object');
      if(options['--preserve']!==undefined){
        if(Object.hasOwn(requested,'preserve'))throw new Error('preserve must be specified once');
        requested.preserve=options['--preserve'];
      }
      if(options['--max-checks']!==undefined){
        if(Object.hasOwn(requested,'maxChecks')||! /^(0|[1-9][0-9]*)$/.test(options['--max-checks']))throw new Error('maxChecks must be specified once as an integer');
        requested.maxChecks=Number(options['--max-checks']);
      }
    }
    const companions=[];
    let result;
    if(isReplay)result=replayCapsuleV4(text,requested);
    else if(isVerify){
      const supplied=readBounded(paths[1],32*1024*1024);
      result=command==='verify-v4'?verifyV4(text,supplied,requested):
        command==='verify-classification-v4'?verifyClassificationV4(text,supplied,requested):isLostUpdates?verifyLostUpdatesV4(text,supplied,requested):isInspection?verifyAnomaliesV4(text,supplied,requested):verifyReductionV4(text,supplied,requested);
    }else{
      if(options['--capsule']){
        const capsule=command==='analyze-v4'?makeCapsuleV4(text,requested):
          command==='classify-v4'?makeClassificationCapsuleV4(text,requested):isLostUpdates?makeLostUpdatesCapsuleV4(text,requested):isInspection?makeAnomaliesCapsuleV4(text,requested):makeReductionCapsuleV4(text,requested);
        result=JSON.parse(JSON.parse(capsule).reportText);
        companions.push([options['--capsule'],capsule+'\n']);
      }else result=command==='analyze-v4'?analyzeV4(text,requested):command==='classify-v4'?classifyV4(text,requested):isLostUpdates?inspectLostUpdatesV4(text,requested):isInspection?inspectAnomaliesV4(text,requested):reduceV4(text,requested);
      if(options['--source']){
        if(result.reducedSource===undefined)throw new Error('No reduced source is available');
        companions.push([options['--source'],JSON.stringify(result.reducedSource,null,2)+'\n']);
      }
    }
    emitJSON(result,options['--output'],inputs,companions);
    const status=result.judgment?.status??result.status;
    const decision=['unchanged','reduced','not-violation'].includes(status)?result.analysis?.judgment?.status:status;
    process.exitCode=isVerify||isReplay?(result.valid===true?0:2):decision==='invalid'?2:
      ['violation','refuted','findings'].includes(decision)?1:['consistent','checked-compatible','checked'].includes(decision)?0:3;
  } else if (['diagnose-v3','verify-diagnosis-v3'].includes(args[0])) {
    const command=args[0],{paths,options}=localArgs(args.slice(1),['--options','--output'],command==='verify-diagnosis-v3'?2:1);
    const inputs=[...paths,...(options['--options']?[options['--options']]:[])];
    if(inputs.filter(path=>path==='-').length>1)throw new Error('Only one diagnosis input may use standard input');
    const source=readBounded(paths[0],8*1024*1024);
    const requested=options['--options']===undefined?undefined:JSON.parse(readBounded(options['--options'],16384));
    const result=command==='verify-diagnosis-v3'?
      verifyDiagnosisV3(source,readBounded(paths[1],160*1024*1024),requested):diagnoseV3(source,requested===undefined?{}:requested);
    emitJSON(result,options['--output'],inputs);
    process.exitCode='valid' in result?(result.valid?0:2):result.status==='findings'?1:result.status==='no-findings'?0:result.status==='invalid'?2:3;
  } else if (['classify-models-v3','verify-models-classification-v3','replay-models-classification-v3'].includes(args[0])) {
    const command=args[0],allowed=command==='replay-models-classification-v3'?['--output']:
      command==='verify-models-classification-v3'?['--options','--output']:['--options','--output','--capsule'];
    const {paths,options}=localArgs(args.slice(1),allowed,command==='verify-models-classification-v3'?2:1);
    const inputs=[...paths,...(options['--options']?[options['--options']]:[])];
    if(inputs.filter(path=>path==='-').length>1)throw new Error('多个输入不能同时使用标准输入');
    const source=readBounded(paths[0],command==='replay-models-classification-v3'?192*1024*1024:32*1024*1024);
    const requested=options['--options']===undefined?{}:JSON.parse(readBounded(options['--options'],8192));
    let result;const companions=[];
    if(command==='replay-models-classification-v3')result=replayModelsClassificationCapsuleV3(source);
    else if(command==='verify-models-classification-v3')result=verifyModelsClassificationV3(source,readBounded(paths[1],96*1024*1024),options['--options']===undefined?undefined:requested);
    else if(options['--capsule']){
      const capsule=makeModelsClassificationCapsuleV3(source,requested);
      result=JSON.parse(JSON.parse(capsule).reportText);companions.push([options['--capsule'],capsule]);
    }else result=classifyModelsV3(source,requested);
    if(Buffer.byteLength(JSON.stringify(result,null,2)+'\n','utf8')>192*1024*1024)throw new Error('model classification输出超过192MiB');
    emitJSON(result,options['--output'],inputs,companions);
    process.exitCode='valid' in result?(result.valid?0:2):result.status==='checked-compatible'?0:result.status==='refuted'?1:result.status==='invalid'?2:3;
  } else if (['classify-v3','shrink-classification-v3','verify-classification-v3','replay-classification-v3'].includes(args[0])) {
    const command=args[0];
    const allowed=command==='replay-classification-v3'?['--output']:command==='verify-classification-v3'?['--options','--output']:
      command==='shrink-classification-v3'?['--category','--max-checks','--options','--output','--capsule','--capture']:['--options','--output','--capsule'];
    const {paths,options}=localArgs(args.slice(1),allowed,command==='verify-classification-v3'?2:1);
    const inputs=[...paths,...(options['--options']?[options['--options']]:[])];
    if(inputs.filter(path=>path==='-').length>1)throw new Error('多个输入不能同时使用标准输入');
    const source=readBounded(paths[0],command==='replay-classification-v3'?128*1024*1024:8*1024*1024);
    let requested=options['--options']===undefined?{}:JSON.parse(readBounded(options['--options'],command==='shrink-classification-v3'?8192:4096));
    if(command==='shrink-classification-v3'){
      if(requested===null||typeof requested!=='object'||Array.isArray(requested))throw new Error('分类缩减选项必须是对象');
      if(options['--category']!==undefined){
        if(Object.hasOwn(requested,'category'))throw new Error('不能重复指定 category');
        requested={...requested,category:options['--category']};
      }
      if(options['--max-checks']!==undefined){
        if(!/^(0|[1-9][0-9]*)$/.test(options['--max-checks'])||Number(options['--max-checks'])>256)throw new Error('max-checks 必须为0..256整数');
        if(Object.hasOwn(requested,'maxChecks'))throw new Error('不能重复指定 maxChecks');
        requested={...requested,maxChecks:Number(options['--max-checks'])};
      }
    }
    let result;const companions=[];
    if(command==='replay-classification-v3')result=replayClassificationCapsuleV3(source);
    else if(command==='verify-classification-v3')result=verifyClassificationV3(source,readBounded(paths[1],64*1024*1024),options['--options']===undefined?undefined:requested);
    else if(options['--capsule']){
      const capsule=command==='classify-v3'?makeClassificationCapsuleV3(source,requested):makeClassificationReductionCapsuleV3(source,requested);
      result=JSON.parse(JSON.parse(capsule).reportText);companions.push([options['--capsule'],capsule]);
    }else result=command==='classify-v3'?classifyV3(source,requested):reduceClassificationV3(source,requested);
    if(options['--capture']){
      if(result.sourceClosure?.complete!==true||result.finalReplay?.valid!==true||typeof result.result?.reducedTraceText!=='string')
        throw new Error('没有经完整来源和最终重放核验的分类缩减记录');
      companions.push([options['--capture'],result.result.reducedTraceText]);
    }
    if(Buffer.byteLength(JSON.stringify(result,null,2)+'\n','utf8')>128*1024*1024)throw new Error('classification输出超过128MiB');
    emitJSON(result,options['--output'],inputs,companions);
    process.exitCode='valid' in result?(result.valid?0:2):result.status==='invalid'?2:
      ['refuted','reduced','unchanged'].includes(result.status)?1:result.status==='checked-compatible'?0:
      result.status==='not-refuted'&&result.result?.report?.rules?.[result.result.category]?.status==='checked-compatible'?0:3;
  } else if (['model-profile-v3','replay-model-profile-v3','verify-model-profile-v3'].includes(args[0])) {
    const command=args[0];
    const allowed=command==='replay-model-profile-v3'?['--output']:command==='verify-model-profile-v3'?['--options','--output']:['--options','--output','--capsule'];
    const {paths,options}=localArgs(args.slice(1),allowed,command==='verify-model-profile-v3'?2:1);
    const inputs=[...paths,...(options['--options']?[options['--options']]:[])];
    if(inputs.filter(path=>path==='-').length>1)throw new Error('多个输入不能同时使用标准输入');
    const source=readBounded(paths[0],command==='replay-model-profile-v3'?128*1024*1024:64*1024*1024);
    const requested=options['--options']===undefined?{}:JSON.parse(readBounded(options['--options'],4096));
    let result;const companions=[];
    if(command==='replay-model-profile-v3')result=replayModelProfileCapsuleV3(source);
    else if(command==='verify-model-profile-v3')result=verifyModelProfileV3(source,readBounded(paths[1],64*1024*1024),options['--options']===undefined?undefined:requested);
    else if(options['--capsule']){
      const capsule=makeModelProfileCapsuleV3(source,requested);
      result=JSON.parse(JSON.parse(capsule).reportText);companions.push([options['--capsule'],capsule]);
    }else result=analyzeModelProfileV3(source,requested);
    if(Buffer.byteLength(JSON.stringify(result,null,2)+'\n','utf8')>128*1024*1024)throw new Error('model profile输出超过128MiB');
    emitJSON(result,options['--output'],inputs,companions);
    process.exitCode='valid' in result?(result.valid?0:2):result.status==='consistent'?0:result.status==='violation'?1:3;
  } else if (['orm-profile-v3','shrink-orm-profile-v3','replay-orm-profile-v3','verify-orm-profile-v3'].includes(args[0])) {
    const command=args[0];
    const allowed=command==='replay-orm-profile-v3'?['--output']:command==='verify-orm-profile-v3'?['--options','--output']:command==='shrink-orm-profile-v3'?['--options','--max-checks','--output','--history','--capsule']:['--options','--output','--capsule'];
    const {paths,options}=localArgs(args.slice(1),allowed,command==='verify-orm-profile-v3'?2:1);
    const inputs=[...paths,...(options['--options']?[options['--options']]:[])];
    if(inputs.filter(path=>path==='-').length>1)throw new Error('多个输入不能同时使用标准输入');
    const source=readBounded(paths[0],command==='replay-orm-profile-v3'?128*1024*1024:64*1024*1024);
    let requested=options['--options']===undefined?{}:JSON.parse(readBounded(options['--options'],4096));
    if(options['--max-checks']!==undefined){
      if(!/^(0|[1-9][0-9]*)$/.test(options['--max-checks'])||Number(options['--max-checks'])>256)throw new Error('max-checks 必须为 0..256 整数');
      if(requested===null||Array.isArray(requested)||typeof requested!=='object')throw new Error('缩减选项必须是对象');
      if(Object.hasOwn(requested,'maxChecks'))throw new Error('不能重复指定maxChecks');
      requested={...requested,maxChecks:Number(options['--max-checks'])};
    }
    let result;const companions=[];
    if(command==='replay-orm-profile-v3')result=replayOrmProfileCapsuleV3(source);
    else if(command==='verify-orm-profile-v3')result=verifyOrmProfileV3(source,readBounded(paths[1],64*1024*1024),options['--options']===undefined?undefined:requested);
    else if(options['--capsule']){
      const capsule=command==='orm-profile-v3'?makeOrmProfileCapsuleV3(source,requested):makeOrmProfileReductionCapsuleV3(source,requested);
      result=JSON.parse(JSON.parse(capsule).reportText);companions.push([options['--capsule'],capsule]);
    }else result=command==='orm-profile-v3'?analyzeOrmProfileV3(source,requested):reduceOrmProfileV3(source,requested);
    if(options['--history']){
      const history=result.result?.reduction?.reducedHistory;
      if(!history||result.result?.finalReplay?.valid!==true)throw new Error('没有经来源核验和最终重放确认的缩减历史可导出');
      companions.push([options['--history'],JSON.stringify(history,null,2)+'\n']);
    }
    if(Buffer.byteLength(JSON.stringify(result,null,2)+'\n','utf8')>128*1024*1024)throw new Error('profile输出超过128MiB');
    emitJSON(result,options['--output'],inputs,companions);
    process.exitCode='valid' in result?(result.valid?0:2):['consistent','reduced','unchanged'].includes(result.status)?0:result.status==='violation'?1:result.status==='invalid'?2:3;
  } else if (args[0] === 'inspect-orm-source-v3') {
    const {paths,options} = localArgs(args.slice(1),['--output'],2);
    if (paths[0] === '-' && paths[1] === '-') throw new Error('两个输入不能同时使用标准输入');
    const result = inspectOrmSourceV3({
      schema:2,profile:'fastapi-users-sqlalchemy-7.0.0-pg18/1',
      traceText:readBounded(paths[0],8*1024*1024),
      sourceJournalText:readBounded(paths[1],16*1024*1024),
    });
    emitJSON(result,options['--output'],paths);
    process.exitCode = result.controlProfileComplete === true ? 0 : 2;
  } else if (['ingest-v3', 'check-v3', 'reduce-v3', 'verify-v3', 'replay-v3', 'failures-v3'].includes(args[0])) {
    const command = args[0];
    const allowed = command === 'check-v3' ? ['--output','--capsule','--sql-proof'] : command === 'reduce-v3' ? ['--output','--capture','--max-checks','--sql-proof'] : command === 'ingest-v3' ? ['--output','--sql-proof'] : command === 'failures-v3' ? ['--output'] : [];
    const {paths,options} = localArgs(args.slice(1),allowed,command === 'verify-v3' ? 2 : 1);
    const text = readBounded(paths[0],command === 'replay-v3' ? 32*1024*1024 : 8*1024*1024);
    let result;
    const companions = [];
    const proofOptions = options['--sql-proof'] === undefined ? {} : {sqlProof:options['--sql-proof']};
    if (command === 'ingest-v3') result = normalizeCaptureV3(text,proofOptions);
    if (command === 'failures-v3') result = inspectExecutionFailuresV3(text);
    if (command === 'check-v3') {
      result = analyzeV3(text,proofOptions);
      if (options['--capsule']) companions.push([options['--capsule'],makeCapsuleV3(text,result)]);
    }
    if (command === 'reduce-v3') {
      const count = options['--max-checks'];
      if (count !== undefined && !/^(0|[1-9][0-9]*)$/.test(count)) throw new Error('max-checks 必须为 0..256 整数');
      result = reduceV3(text,{...(count === undefined ? {} : {maxChecks:Number(count)}),...(options['--sql-proof'] === undefined ? {} : {analysisOptions:proofOptions})});
      if (options['--capture']) {
        if (!result.reducedCapture) throw new Error('无有效 v3 缩减记录可导出');
        companions.push([options['--capture'],JSON.stringify(result.reducedCapture,null,2)+'\n']);
      }
    }
    if (command === 'verify-v3') result = verifyV3(text,readBounded(paths[1],32*1024*1024));
    if (command === 'replay-v3') result = replayCapsuleV3(text);
    emitJSON(result,options['--output'],paths,companions);
    process.exitCode = 'valid' in result ? (result.valid ? 0 : 2) : ['ready','consistent','reduced','unchanged'].includes(result.status) ? 0 : result.status === 'violation' ? 1 : result.status === 'invalid' ? 2 : 3;
  } else if (args[0] === 'verify') {
    if (args.length !== 3 || args[1] === '-' || args[2] === '-') throw new Error('verify 需要历史文件和证据文件两个路径');
    const result = JSON.parse(verify_certificate_json(readBounded(args[1], 2 * 1024 * 1024), readBounded(args[2], 32 * 1024 * 1024)));
    console.log(JSON.stringify(result, null, 2));
    process.exitCode = result.valid ? 0 : 2;
  } else if (args[0] === 'ingest' || args[0] === 'ingest-presence') {
    const { paths, options } = localArgs(args.slice(1), ['--output', '--history'], 1);
    const capture = await import('./capture-core.mjs');
    const normalize = args[0] === 'ingest-presence' ? capture.normalize_presence_json : capture.normalize_capture_json;
    const result = JSON.parse(normalize(readBounded(paths[0], 8 * 1024 * 1024)));
    const companions = [];
    if (options['--history']) {
      if (result.status !== 'ready' || !result.history) throw new Error('采集记录不完整或无效，未导出历史；请先查看 ingest 覆盖报告');
      companions.push([options['--history'], JSON.stringify(result.history, null, 2) + '\n']);
    }
    emitJSON(result, options['--output'], paths, companions);
    process.exitCode = result.status === 'ready' ? 0 : result.status === 'inconclusive' ? 3 : 2;
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
    const { paths, options } = localArgs(args.slice(1), ['--output', '--history', '--profile'], 1);
    const profile=options['--profile'] || 'compat';
    if (!['compat','balanced'].includes(profile)) throw new Error('profile 必须为 compat 或 balanced');
    const history=readBounded(paths[0], 2 * 1024 * 1024);
    const result = JSON.parse(profile==='balanced' ? shrink_options_json(history,'{}') : shrink_json(history));
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
