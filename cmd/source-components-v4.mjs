const names = ['verify_source_installation_v4_json','verify_source_installation_report_v4_json','verify_source_fetch_mapping_v4_json','verify_source_fetch_mapping_report_v4_json'];
function text(value, limit, label) {
  const result = typeof value === 'string' ? value : JSON.stringify(value, (_key,item) => { if (typeof item === 'number' && !Number.isSafeInteger(item)) throw new TypeError('Use original JSON text for exact numbers outside the JavaScript safe integer range'); return item; });
  if (typeof result !== 'string' || !result.isWellFormed() || Buffer.byteLength(result, 'utf8') > limit) throw new TypeError(`${label} exceeds the input contract`);
  return result;
}
const configuration = v => text(v,262144,'configuration');
const policy = v => text(v,8192,'source policy');
const log = v => { if (typeof v !== 'string') throw new TypeError('original log must be text'); return text(v,8388608,'original log'); };
const receipt = v => text(v,2097152,'installation receipt');
const options = v => text(v ?? {},8192,'caller options');
const execution = v => text(v,1048576,'original execution');
const native = v => text(v,524288,'native result');
const delivery = v => text(v,2097152,'actual deliveries');
const context = v => text(v,8192,'installation context');
const report = v => text(v,4194304,'component report');
function result(value) {
  if (typeof value !== 'string' || Buffer.byteLength(value,'utf8') > 4194304) throw new TypeError('invalid core response');
  return JSON.parse(value);
}
export function createSourceComponentsV4(core) {
  for (const name of names) if (typeof core[name] !== 'function') throw new TypeError(`missing source component entry ${name}`);
  const installArgs = input => [configuration(input.config),policy(input.policy),log(input.log),receipt(input.receipt)];
  const mappingArgs = input => [...installArgs(input),execution(input.execution),native(input.native),delivery(input.deliveries),context(input.sourceContext)];
  return Object.freeze({
    verifySourceInstallationV4(input, callerOptions = {}) {
      return result(core.verify_source_installation_v4_json(...installArgs(input),options(callerOptions)));
    },
    verifySourceInstallationReportV4(input, suppliedReport, expectedOptions = {}) {
      return core.verify_source_installation_report_v4_json(...installArgs(input),report(suppliedReport),options(expectedOptions)) === true;
    },
    mapInitialSourceFetchV4(input, callerOptions = {}) {
      return result(core.verify_source_fetch_mapping_v4_json(...mappingArgs(input),options(callerOptions)));
    },
    verifyInitialSourceFetchReportV4(input, suppliedReport, expectedOptions = {}) {
      return core.verify_source_fetch_mapping_report_v4_json(...mappingArgs(input),report(suppliedReport),options(expectedOptions)) === true;
    },
  });
}
