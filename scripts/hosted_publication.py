"""Hosted public-download verification controller; original tag verifier stays intact."""
from __future__ import annotations
import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

REPOSITORY = 'HhWw96/moontxnwitness'
TOKEN_NAMES = {'GH_ACTIONS_READ_TOKEN', 'GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN'}


@dataclass(frozen=True)
class Inputs:
    version: str
    expected_tag_sha: str
    expected_registry_sha256: str
    workflow_commit: str


def validate_inputs(version, tag_sha, registry_sha, workflow_commit):
    if not isinstance(version, str) or len(version) > 32 or not re.fullmatch(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)', version):
        raise ValueError('version must be a canonical stable x.y.z')
    for name, value, length in [('expected_tag_sha', tag_sha, 40), ('expected_registry_sha256', registry_sha, 64), ('workflowCommit', workflow_commit, 40)]:
        if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{' + str(length) + '}', value):
            raise ValueError(name + ' must be complete lowercase hexadecimal')
    return Inputs(version, tag_sha, registry_sha, workflow_commit)


def inputs_from_environment():
    if os.environ.get('MTW_WORKFLOW_REPOSITORY') != REPOSITORY:
        raise ValueError('Run this controller in the declared repository')
    return validate_inputs(os.environ.get('MTW_VERSION'), os.environ.get('MTW_EXPECTED_TAG_SHA'),
        os.environ.get('MTW_EXPECTED_REGISTRY_SHA256'), os.environ.get('MTW_WORKFLOW_COMMIT'))


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for raw in iter(lambda: stream.read(64 * 1024), b''):
            result.update(raw)
    return result.hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def clean_environment(environment):
    return {key: value for key, value in environment.items() if key not in TOKEN_NAMES}


def attest_source(source, control, inputs):
    source, control = Path(source).resolve(), Path(control).resolve()
    git = lambda root, *args: subprocess.check_output(['git', *args], cwd=root, text=True).strip()
    actual = git(source, 'rev-parse', 'HEAD')
    tag = git(source, 'rev-parse', '--verify', 'refs/tags/v' + inputs.version + '^{commit}')
    if actual != inputs.expected_tag_sha or tag != inputs.expected_tag_sha:
        raise AssertionError('Checked-out HEAD/tag differs from independent expected_tag_sha')
    if git(control, 'rev-parse', 'HEAD') != inputs.workflow_commit:
        raise AssertionError('Controller checkout differs from workflowCommit')
    if json.loads((source / 'package.json').read_text(encoding='utf8'))['version'] != inputs.version:
        raise AssertionError('Tag package version differs from requested version')
    bindings = {}
    for name in ('scripts/verify_publication.py', 'scripts/publication_download.py'):
        raw = subprocess.check_output(['git', 'show', 'HEAD:' + name], cwd=source)
        if (source / name).read_bytes() != raw:
            raise AssertionError('Original tag verification code changed: ' + name)
        bindings[name] = hashlib.sha256(raw).hexdigest()
    return {'version': inputs.version, 'sourceCommit': actual, 'resolvedTagCommit': tag,
        'workflowCommit': inputs.workflow_commit, 'controllerSha256': digest(Path(__file__)),
        'originalVerifierBindings': bindings, 'expectedPublisherSha256': inputs.expected_registry_sha256}


def tag_downloader(source):
    spec = importlib.util.spec_from_file_location('tag_publication_download', Path(source) / 'scripts/publication_download.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.download_file


def anchor_registry(source, evidence, inputs, downloader=None):
    """Verify an independent publisher digest BEFORE creating the expected path."""
    source, evidence = Path(source), Path(evidence)
    reference = evidence / 'publisher-reference'
    reference.mkdir(parents=True, exist_ok=False)
    target = source / '_build/publish' / ('HhWw96-moontxnwitness-' + inputs.version + '.zip')
    if target.exists() or target.is_symlink():
        raise AssertionError('Expected upload reference path must start absent')
    downloaded = reference / 'registry.zip'
    url = 'https://download.mooncakes.io/user/' + REPOSITORY + '/' + inputs.version + '.zip'
    downloader = downloader or tag_downloader(source)
    downloader(url, downloaded, expected_sha256=inputs.expected_registry_sha256,
        user_agent='MoonTxnWitness-hosted-publisher-reference/' + inputs.version)
    observed = digest(downloaded)
    if observed != inputs.expected_registry_sha256:
        raise AssertionError('Public registry bytes differ from independent publisher SHA-256')
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive copy only after the independent comparison, then verify the copy.
    with downloaded.open('rb') as incoming, target.open('xb') as outgoing:
        shutil.copyfileobj(incoming, outgoing, length=64 * 1024)
    if digest(target) != inputs.expected_registry_sha256:
        raise AssertionError('Publisher reference copy changed')
    receipt = {'version': inputs.version, 'anonymousDownload': True, 'url': url,
        'expectedPublisherSha256': inputs.expected_registry_sha256, 'observedSha256': observed,
        'matchedIndependentInputBeforeStaging': True,
        'referenceKind': 'Public bytes independently matched to the supplied actual publisher archive digest; not an original publisher file possession claim',
        'stagedRelativePath': target.relative_to(source).as_posix(), 'bytes': downloaded.stat().st_size}
    save(reference / 'receipt.json', receipt)
    return receipt


def create_gh_wrapper(directory, real_gh, token):
    """Only the real gh read-Actions subprocess receives GH_TOKEN."""
    directory = Path(directory)
    token_path = directory / 'actions-read-token'
    with token_path.open('x', encoding='utf8') as stream:
        stream.write(token)
    token_path.chmod(0o600)
    wrapper = directory / 'gh'
    code = '''#!/usr/bin/env python3
import os
from pathlib import Path
import sys
args = sys.argv[1:]
if len(args) < 2 or args[:2] not in (['run','list'],['run','view'],['run','download']):
    raise SystemExit('Only read-only Actions run list/view/download is permitted')
if '--repo' not in args or args.index('--repo')+1 >= len(args) or args[args.index('--repo')+1] != REPO:
    raise SystemExit('Only the declared repository is permitted')
env = {k:v for k,v in os.environ.items() if k not in ('GH_ACTIONS_READ_TOKEN','GH_TOKEN','GITHUB_TOKEN','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN')}
env['GH_TOKEN'] = Path(TOKEN_FILE).read_text(encoding='utf8')
env['GH_CONFIG_DIR'] = CONFIG_DIR
env['GH_HOST'] = 'github.com'
env['GH_PROMPT_DISABLED'] = '1'
os.execve(REAL_GH, [REAL_GH, *args], env)
'''
    constants = '\n'.join(name + '=' + repr(value) for name, value in {
        'REPO': REPOSITORY, 'TOKEN_FILE': str(token_path), 'CONFIG_DIR': str(directory / 'gh-config'), 'REAL_GH': str(real_gh)}.items()) + '\n'
    code = code.replace('import sys\n', 'import sys\n' + constants, 1)
    wrapper.write_text(code, encoding='utf8')
    wrapper.chmod(0o700)
    return wrapper


def invoke_original(source, evidence, inputs, token, *, temp_parent=None):
    source, evidence = Path(source), Path(evidence)
    before = {p.name for p in (source / 'artifacts/public-verification').glob('run-*')}
    save(evidence / 'execution-start.json', {'beforeRuns': sorted(before),
        'sourceCommit': inputs.expected_tag_sha, 'workflowCommit': inputs.workflow_commit})
    original_hash = digest(source / 'scripts/verify_publication.py')
    real_gh = shutil.which('gh')
    if not real_gh or not token:
        raise RuntimeError('Read-only Actions token and gh executable are required')
    evidence.mkdir(parents=True, exist_ok=True)
    # Wrapper/token are outside the uploaded evidence tree, removed on all exits.
    with tempfile.TemporaryDirectory(prefix='mtw-actions-read-', dir=temp_parent) as private:
        Path(private).chmod(0o700)
        create_gh_wrapper(private, real_gh, token)
        environment = clean_environment(os.environ)
        environment['PATH'] = private + os.pathsep + environment.get('PATH', '')
        command = [sys.executable, '-u', 'scripts/verify_publication.py', inputs.version]
        with (evidence / 'verification.log').open('w', encoding='utf8') as log:
            process = subprocess.Popen(command, cwd=source, env=environment, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding='utf8', errors='replace')
            for line in process.stdout:
                log.write(line)
                log.flush()
                print(line, end='', flush=True)
            status = process.wait()
    if digest(source / 'scripts/verify_publication.py') != original_hash:
        raise AssertionError('Original verifier changed during execution')
    runs = sorted(p.name for p in (source / 'artifacts/public-verification').glob('run-*') if p.name not in before)
    save(evidence / 'execution.json', {'version': inputs.version, 'exitCode': status,
        'passed': status == 0, 'originalVerifierUnmodified': True, 'sourceCommit': inputs.expected_tag_sha,
        'workflowCommit': inputs.workflow_commit, 'publicVerificationRuns': runs,
        'ghTokenScope': 'Only wrapper exec of read-only gh Actions subcommands; absent from verifier, urllib and Moon subprocess environments'})
    return status


def collect_evidence(source, evidence, inputs):
    """Copy only original generated receipts, consumer source and registry bytes."""
    source, evidence = Path(source).resolve(), Path(evidence).resolve()
    record = evidence / 'execution.json'
    runs = json.loads(record.read_text(encoding='utf8')).get('publicVerificationRuns', []) if record.exists() else []
    started = evidence / 'execution-start.json'
    if not record.exists() and started.exists():
        before = set(json.loads(started.read_text(encoding='utf8'))['beforeRuns'])
        runs = sorted(p.name for p in (source / 'artifacts/public-verification').glob('run-*') if p.name not in before)
    for run in runs:
        if not re.fullmatch(r'run-[A-Za-z0-9_-]+', run):
            raise AssertionError('Unexpected original verifier work directory name')
        work = source / 'artifacts/public-verification' / run
        for name in ('registry.zip',):
            path = work / name
            if path.is_file() and not path.is_symlink():
                target = evidence / 'original-verifier' / run / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        consumer = work / 'consumer'
        for path in consumer.glob('*'):
            if path.is_file() and not path.is_symlink() and (path.suffix in ('.mbt', '.mbti', '.json') or path.name in ('moon.mod', 'moon.pkg', 'moon.lock')):
                target = evidence / 'original-verifier' / run / 'consumer' / path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
    # Only receipt names written by this exact invocation are selected. An old
    # committed publication failure is not presented as a newly generated one.
    baseline_path = evidence / 'receipt-baseline.json'
    baseline = json.loads(baseline_path.read_text(encoding='utf8')) if baseline_path.exists() else {}
    release = source / 'verification/releases' / inputs.version
    receipts = [*release.glob('publication*.json'), release / 'postgres-linux.json', release / 'postgres-linux-server.txt']
    for path in receipts:
        name = path.relative_to(source).as_posix()
        if path.is_file() and not path.is_symlink() and baseline.get(name) != digest(path):
            target = evidence / 'receipts' / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    return runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('attest', 'anchor-registry', 'verify', 'collect'))
    parser.add_argument('--source-root', type=Path, default=Path('release-source'))
    parser.add_argument('--evidence-root', type=Path, default=Path('publication-evidence'))
    args = parser.parse_args()
    inputs = inputs_from_environment()
    source, evidence = args.source_root.resolve(), args.evidence_root.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    if args.phase == 'attest':
        save(evidence / 'source-attestation.json', attest_source(source, Path(__file__).resolve().parents[1], inputs))
        save(evidence / 'independent-inputs.json', asdict(inputs))
        release = source / 'verification/releases' / inputs.version
        receipts = [*release.glob('publication*.json'), release / 'postgres-linux.json', release / 'postgres-linux-server.txt']
        save(evidence / 'receipt-baseline.json', {p.relative_to(source).as_posix(): digest(p) for p in receipts if p.is_file()})
    elif args.phase == 'anchor-registry':
        attest_source(source, Path(__file__).resolve().parents[1], inputs)
        anchor_registry(source, evidence, inputs)
    elif args.phase == 'verify':
        attest_source(source, Path(__file__).resolve().parents[1], inputs)
        expected = source / '_build/publish' / ('HhWw96-moontxnwitness-' + inputs.version + '.zip')
        if not expected.is_file() or digest(expected) != inputs.expected_registry_sha256:
            raise AssertionError('Independent publisher anchor must be complete before original verification')
        token = os.environ.pop('GH_ACTIONS_READ_TOKEN', '')
        status = invoke_original(source, evidence, inputs, token, temp_parent=os.environ.get('RUNNER_TEMP'))
        collect_evidence(source, evidence, inputs)
        return status
    else:
        collect_evidence(source, evidence, inputs)
        save(evidence / 'hosted-run.json', {'version': inputs.version, 'sourceCommit': inputs.expected_tag_sha,
            'workflowCommit': inputs.workflow_commit, 'verifierOutcome': os.environ.get('MTW_VERIFIER_OUTCOME', 'not-run'),
            'finishedAt': datetime.now(timezone.utc).isoformat(),
            'actualHostedWorkflow': os.environ.get('GITHUB_ACTIONS') == 'true',
            'originalVerifierChecksSkipped': False})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
