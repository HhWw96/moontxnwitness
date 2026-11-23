// CI may pass only on a source-verified Serializable result.
import {readFile} from 'node:fs/promises';
import {parseArgs} from 'node:util';
import {replayConfiguredWindowCapsuleV4} from '../dist/configured-window-v2-capsule.mjs';

try {
  const {positionals, values} = parseArgs({allowPositionals: true, options: {
    config: {type: 'string'}, policy: {type: 'string'}, 'max-point-checks': {type: 'string'},
  }});
  if (positionals.length !== 1 || !values.config || !values.policy) {
    throw new Error('Use check-point-window.mjs --config FILE --policy FILE [--max-point-checks N] CAPSULE');
  }
  const budget = values['max-point-checks'] ?? '1000000';
  if (!/^(?:0|[1-9][0-9]{0,6})$/.test(budget) || Number(budget) > 1_000_000) {
    throw new RangeError('max-point-checks must be an integer from 0 to 1000000');
  }
  const [capsule, config, policy] = await Promise.all(
    [positionals[0], values.config, values.policy].map(path => readFile(path, 'utf8')));
  const {report, ...proof} = replayConfiguredWindowCapsuleV4(capsule, {
    config, policy, maxPointChecks: Number(budget),
  });
  const complete = proof.valid && proof.reportMatches && report.coverageComplete === true &&
    report.sourceMappingVerified === true && report.writerWindowVerified === true;
  const accepted = complete && proof.status === 'checked-compatible' &&
    report.modelDecision?.status === 'checked-compatible';
  const refuted = complete && proof.status === 'refuted' && report.modelDecision?.status === 'refuted';
  console.log(JSON.stringify({accepted, verifiedRefutation: refuted,
    model: 'serializable', status: proof.status ?? 'unknown', reportMatches: proof.reportMatches,
    sourceCoverageComplete: Boolean(complete), sourceAuthenticated: proof.sourceAuthenticated,
    bundleSha256: proof.bundleSha256, reason: proof.reason}));
  process.exitCode = accepted ? 0 : refuted ? 1 : 2;
} catch (error) {
  console.error(error.message);
  process.exitCode = 2;
}
