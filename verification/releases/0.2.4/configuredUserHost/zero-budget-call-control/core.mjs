import * as real from './real-core.mjs';
export const calls=[];
export const version=real.version;
export function orm_profile_source_v3_json(...args){calls.push('orm_profile_source_v3_json');return real.orm_profile_source_v3_json(...args);}
export function shrink_options_json(...args){calls.push('shrink_options_json');return real.shrink_options_json(...args);}
export function analyze_options_json(...args){calls.push('analyze_options_json');return real.analyze_options_json(...args);}
export function replay_report_json(...args){calls.push('replay_report_json');return real.replay_report_json(...args);}
