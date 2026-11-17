import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import * as core from './core.mjs';
import * as sdk from './sdk.mjs';

/** Discover declarations and loaded exports without running a history checker. */
export function capabilities() {
  // The build copies these exact declaration bytes beside this module. Do not
  // resolve against cwd or fall back to a source checkout in a portable install.
  const bytes = readFileSync(new URL('./feature-matrix-v4.json', import.meta.url));
  const declaration = JSON.parse(bytes.toString('utf8'));
  if (declaration.format !== 'moontxnwitness-feature-declaration/v1' ||
      declaration.semanticNamespace !== 'v4' || !Array.isArray(declaration.profiles) ||
      !Array.isArray(declaration.models)) throw new Error('Unsupported capability declaration');
  const declaredApis = [...new Set([
    ...declaration.profiles.map(profile => profile.modelApi),
    declaration.predicateProfile.api,
    declaration.relationPredicateModels.classify,
    declaration.relationPredicateModels.verify,
    declaration.relationPredicateModels.reduction.entry,
    declaration.relationPredicateModels.reduction.verify,
    ...(declaration.configuredWindows ? [declaration.configuredWindows.analyze, declaration.configuredWindows.verify] : []),
  ])].sort();
  const runtimeModels = Array.isArray(sdk.ELLE_CORE_MODELS_V4) ? [...sdk.ELLE_CORE_MODELS_V4] : [];
  return {
    format: 'moontxnwitness-capabilities/v1', schemaVersion: 1,
    tool: 'MoonTxnWitness', version: core.version(),
    analysisPerformed: false,
    runtime: {
      sdkFunctionExports: Object.keys(sdk).filter(name => typeof sdk[name] === 'function').sort(),
      declaredSdkApis: Object.fromEntries(declaredApis.map(name => [name, typeof sdk[name] === 'function'])),
      modelNames: runtimeModels,
      declaredModelNamesMatchRuntime: JSON.stringify(declaration.models.map(model => model.name)) === JSON.stringify(runtimeModels),
      nativeModelReportExports: Object.fromEntries([
        'classify_models_v4_native', 'classify_relation_models_v4_native',
      ].map(name => [name, typeof core[name] === 'function'])),
    },
    declaration: {
      asset: 'feature-matrix-v4.json',
      sha256: createHash('sha256').update(bytes).digest('hex'),
      ...declaration,
    },
    boundaries: {
      discovery: 'Metadata and loaded exports only; no analysis, database connection, network request, migration or file write.',
      diagnostics: 'General SQL/ORM instrumentation and configured-session diagnosis record execution and coverage gaps; they do not establish source closure or isolationAnalysisReady.',
      closedSourceAnalysis: 'Analysis requires the selected profile, original observations, confirmed outcomes, source-closed window and its model-specific facts and budgets.',
      verdicts: 'Missing facts, unsupported inputs and incomplete budgets remain unknown; export availability is not a model verdict or evidence of observation authenticity.',
      reference: 'Fourteen selectable definitions do not establish arbitrary SQL support or complete Elle equivalence. Reference comparisons are not reexecuted by this command.',
      nativeReports: 'Native object reports are JavaScript exports; their availability does not expand data-model or source coverage.',
    },
  };
}

export function formatCapabilitiesText(report) {
  const availability = entries => Object.entries(entries).map(([name, available]) => `  ${name}: ${available ? 'available' : 'unavailable'}`);
  return [
    `MoonTxnWitness v${report.version} capabilities`,
    `Declaration: ${report.declaration.asset} (SHA-256 ${report.declaration.sha256})`,
    'Source profiles (declared requirements; no history analyzed):',
    ...report.declaration.profiles.map(profile => `  ${profile.id}: ${profile.dataModel}; ${profile.sourceProfile}`),
    `Selectable model definitions (${report.declaration.models.length}): ${report.declaration.models.map(model => model.name).join(', ')}`,
    `Declared model names match runtime: ${report.runtime.declaredModelNamesMatchRuntime}`,
    'Declared SDK entry points:', ...availability(report.runtime.declaredSdkApis),
    'JavaScript native model-report exports:', ...availability(report.runtime.nativeModelReportExports),
    ...Object.values(report.boundaries),
    'Use --format json for complete declaration requirements, limits and loaded SDK function exports.',
    '',
  ].join('\n');
}
