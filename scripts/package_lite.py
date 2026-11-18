"""Build and smoke-test a current-runtime ZIP after the standard build."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
import zipfile

from package_archive import sha256, write_archive
from publication_privacy import private_home_paths
from configured_window_runtime import (configured_window_v2_available, verify_configured_window_v2_runtime,
                                       structured_window_available, verify_structured_window_runtime,
                                       configured_window_capsule_available, verify_configured_window_capsule_runtime)


ROOT = Path(__file__).resolve().parent.parent
NODE = os.environ.get('MTW_NODE', 'node')


def run_node(root, args, expected=0):
    result = subprocess.run([NODE, *args], cwd=root, capture_output=True,
                            encoding='utf-8', timeout=60)
    if result.returncode != expected:
        raise RuntimeError(f'{args[0]} exited {result.returncode}: {result.stderr}')
    return result.stdout


def package_lite(output):
    dist = ROOT / 'dist'
    manifest_path = dist / 'build-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    package = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))
    version = package['version']
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version):
        raise ValueError('Expected an x.y.z module version')
    prefix = f'MoonTxnWitness-v{version}-lite'
    if manifest['version'] != version:
        raise ValueError('Run the standard build for the current source first')
    fingerprint = run_node(ROOT, ['--input-type=module', '-e',
        "import {sourceFingerprint} from './scripts/build-fingerprint.mjs';console.log(sourceFingerprint(process.cwd()));"])
    if fingerprint.strip() != manifest['sourceSha256']:
        raise ValueError('Built core does not match current source')
    cores = {'core.mjs': manifest['coreSha256'], 'capture-core.mjs': manifest['captureCoreSha256'],
             **manifest['configuredCoreSha256']}
    if configured_window_v2_available(ROOT):
        window_runtime = verify_configured_window_v2_runtime(ROOT, manifest)
        cores.update({name: digest for name, digest in window_runtime.items() if name.endswith('-core.mjs')})
    structured_window = structured_window_available(ROOT)
    if structured_window:
        structured_runtime = verify_structured_window_runtime(ROOT, manifest)
        cores.update({name: digest for name, digest in structured_runtime.items() if name.endswith('-core.mjs')})
    window_capsule = configured_window_capsule_available(ROOT)
    if window_capsule:
        capsule_runtime = verify_configured_window_capsule_runtime(ROOT, manifest)
    for name, digest in cores.items():
        if sha256(dist / name) != digest:
            raise ValueError(f'Runtime digest mismatch: {name}')
    # Current JS wrappers are copied from cmd by the standard build. Legacy
    # loaders are small and remain linked, while their payload directories are absent.
    wrappers = {p.name for p in (ROOT / 'cmd').glob('*.mjs') if (dist / p.name).is_file()}
    for name in wrappers:
        if sha256(ROOT / 'cmd' / name) != sha256(dist / name):
            raise ValueError(f'Rebuild stale runtime wrapper: {name}')
    files = {f'dist/{name}' for name in wrappers.union(cores)} | {
        'dist/build-manifest.json', 'dist/THIRD_PARTY_NOTICES.txt', 'LICENSE',
        'THIRD_PARTY.md', 'docs/portable-lite.md', 'examples/write-skew.json',
        'examples/models-v4-roundtrip.mjs', 'examples/models-v4-register.json',
        'examples/models-v4-list.json', 'examples/relation-predicate-categories.mjs',
        'examples/relation-predicate-categories.json',
    }
    if structured_window:
        files.add('scripts/configured-window-structured-test.mjs')
    if window_capsule:
        files.update(('scripts/configured-window-v2-capsule-test.mjs', 'docs/configured-window-v2-capsule.md'))
    output = output.resolve()
    output.mkdir()
    archive = output / f'{prefix}.zip'
    private_values = {str(ROOT), ROOT.as_posix(), *private_home_paths(str(Path.home()))}
    receipt = write_archive(ROOT, files, archive, prefix, private_values)
    with TemporaryDirectory(prefix='consumer-', dir=output) as temp:
        root = Path(temp) / prefix
        with zipfile.ZipFile(archive) as zipped:
            if sorted(zipped.namelist()) != sorted(f'{prefix}/{name}' for name in files):
                raise ValueError('Unexpected lightweight archive members')
            zipped.extractall(temp)
        cli = ['dist/moontxnwitness.mjs']
        if run_node(root, [*cli, '--version']).strip() != version:
            raise ValueError('Unexpected lightweight runtime version')
        register = run_node(root, [*cli, 'check', 'examples/write-skew.json', '--profile', 'balanced', '--format', 'json'], 1)
        if json.loads(register)['status'] != 'violation':
            raise ValueError('Register example did not report its expected violation')
        run_node(root, ['examples/models-v4-roundtrip.mjs'])
        run_node(root, ['examples/relation-predicate-categories.mjs'])
        selector = ['--category', 'G2', '--rule-set', 'adya-2000-scoped-categories-v1']
        run_node(root, [*cli, 'reduce-relation-category-v4', 'examples/relation-predicate-categories.json',
                        *selector, '--capsule', 'case.json'], 1)
        run_node(root, [*cli, 'replay-relation-category-reduction-v4', 'case.json', *selector])
        if configured_window_v2_available(ROOT):
            run_node(root, ['--input-type=module', '-e',
                "import assert from 'node:assert/strict';import * as sdk from './dist/sdk.mjs';"
                "import * as standalone from './dist/configured-window-v2-standalone.mjs';"
                "const options={config:'{}',policy:'{}'};"
                "const report=sdk.analyzeConfiguredWindowV4('{}',options);"
                "assert.equal(report.status,'invalid');assert.equal(report.coverageComplete,false);"
                "assert.deepEqual(standalone.analyzeConfiguredWindowV4('{}',options),report);"
                "for(const api of [sdk,standalone]){assert.equal(api.verifyConfiguredWindowV4('{}',report,options).valid,false);"
                "const target={...options,preserveModel:'serializable'},reduced=api.reduceConfiguredWindowV4('{}',target);"
                "assert.equal(reduced.refutationPreserved,false);assert.equal(reduced.oneMinimal,false);"
                "assert.equal(api.verifyConfiguredWindowReductionV4('{}',reduced,target).valid,false);}"])
        if structured_window:
            structured_consumer = json.loads(run_node(root, ['scripts/configured-window-structured-test.mjs']))
            if not structured_consumer['passed'] or structured_consumer['originalCases'] != 0:
                raise ValueError('Explicit structured profile consumer checks failed')
            for name, digest in manifest['structuredWindowRuntimeSha256'].items():
                if structured_consumer['runtimeSha256'].get(name) != digest:
                    raise ValueError('Structured profile consumer runtime differs: ' + name)
        if window_capsule:
            capsule_consumer = json.loads(run_node(root, ['scripts/configured-window-v2-capsule-test.mjs']))
            if not capsule_consumer['passed'] or capsule_consumer['checks'] != 7 or capsule_consumer['originalCases'] != 0:
                raise ValueError('Configured window capsule consumer checks failed')
            for name, digest in capsule_runtime.items():
                if capsule_consumer['runtimeSha256'].get(name) != digest:
                    raise ValueError('Capsule consumer runtime differs: ' + name)
    receipt.update(version=version, sourceFingerprint=manifest['sourceSha256'],
                   coreSha256=manifest['coreSha256'], legacyPayloadsIncluded=False,
                   cleanConsumerChecks=(7 if configured_window_v2_available(ROOT) else 6) + int(structured_window) + int(window_capsule))
    if structured_window:
        receipt['structuredWindowConsumer'] = structured_consumer
    if window_capsule:
        receipt['configuredWindowCapsuleConsumer'] = capsule_consumer
    (output / 'lite-package.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='new output directory')
    print(json.dumps(package_lite(parser.parse_args().output)))
