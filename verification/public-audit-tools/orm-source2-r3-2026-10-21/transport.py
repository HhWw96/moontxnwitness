"""Bounded read-only GitHub Actions transport; never local gh authentication.

This module performs GET requests only. It deliberately does not call /user:
the workflow token is a repository token, not a personal HhWw96 credential.
"""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import re
import selectors
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPOSITORY = 'HhWw96/moontxnwitness'
CHUNK = 65536
JSON_MAX = 32 * 1024 * 1024


def guard_environment(env=None, need_token=False):
    env = os.environ if env is None else env
    if env.get('GITHUB_ACTIONS') != 'true' or env.get('GITHUB_REPOSITORY') != REPOSITORY:
        raise ValueError('This explicit mode requires the exact GitHub Actions repository environment')
    if need_token and not env.get('GITHUB_TOKEN'):
        raise ValueError('The fetch phase requires the read-only workflow GITHUB_TOKEN')


def child_environment(env=None):
    env = os.environ if env is None else env
    private = ('TOKEN', 'SECRET', 'PASSWORD', 'AUTHORIZATION', 'PRIVATE_KEY')
    return {k: v for k, v in env.items()
            if not any(word in k.upper() for word in private)
            and k not in ('GH_ENTERPRISE_TOKEN', 'GH_TOKEN')}


def file_binding(path, maximum=1024 * 1024 * 1024):
    h, count = hashlib.sha256(), 0
    with Path(path).open('rb') as stream:
        while block := stream.read(CHUNK):
            count += len(block)
            if count > maximum:
                raise ValueError('File exceeds the declared audit byte bound')
            h.update(block)
    return {'bytes': count, 'sha256': h.hexdigest()}


def file_sha(path):
    return file_binding(path)['sha256']


def read_bounded(path, maximum=JSON_MAX):
    path = Path(path)
    if path.stat().st_size > maximum:
        raise ValueError('Metadata exceeds the declared in-memory byte bound')
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('Metadata grew beyond the declared byte bound')
    return raw


def immutable(path, value):
    path = Path(path)
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2, ensure_ascii=True) + '\n').encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
    return file_binding(path)


def copy_stream(response, path, maximum, deadline):
    count, h = 0, hashlib.sha256()
    with Path(path).open('xb') as output:
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError('The declared whole-transfer deadline expired')
            block = response.read(CHUNK)
            if not block:
                break
            count += len(block)
            if count > maximum:
                raise ValueError('The declared download byte bound was exceeded')
            output.write(block)
            h.update(block)
        output.flush()
        os.fsync(output.fileno())
    return {'bytes': count, 'sha256': h.hexdigest()}


def run_bounded(command, *, cwd, env, output_prefix, timeout=120, maximum=8 * 1024 * 1024):
    """Linux-only child supervision; retain bounded raw output even on first failure."""
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Actual runtime checks require the independent Linux runner')
    output_prefix = Path(output_prefix)
    paths = {name: output_prefix.with_name(output_prefix.name + '.' + name) for name in ('stdout', 'stderr')}
    streams, counts = {}, {'stdout': 0, 'stderr': 0}
    process = None
    multiplex = selectors.DefaultSelector()
    try:
        for name, path in paths.items():
            streams[name] = path.open('xb')
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        for name in ('stdout', 'stderr'):
            multiplex.register(getattr(process, name), selectors.EVENT_READ, name)
        deadline = time.monotonic() + timeout
        while multiplex.get_map():
            if time.monotonic() >= deadline:
                raise TimeoutError('Bounded runtime check timed out')
            for key, _ in multiplex.select(min(0.25, max(0, deadline - time.monotonic()))):
                block = os.read(key.fileobj.fileno(), CHUNK)
                if not block:
                    multiplex.unregister(key.fileobj)
                    continue
                name = key.data
                remaining = maximum - counts[name]
                streams[name].write(block[:remaining])
                counts[name] += min(len(block), remaining)
                if len(block) > remaining:
                    raise ValueError('Bounded runtime output exceeded its declared byte limit')
        returncode = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        for stream in streams.values():
            stream.flush()
        return subprocess.CompletedProcess(command, returncode,
            read_bounded(paths['stdout'], maximum).decode('utf-8', 'replace'),
            read_bounded(paths['stderr'], maximum).decode('utf-8', 'replace'))
    except Exception as error:
        for stream in streams.values():
            stream.flush()
        immutable(output_prefix.with_name(output_prefix.name + '.failure.json'),
                  {'complete': False, 'errorClass': type(error).__name__, 'maximumBytesPerStream': maximum,
                   'retainedBytes': counts, 'outputMayBeIncomplete': True})
        raise
    finally:
        if process is not None:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            for name in ('stdout', 'stderr'):
                getattr(process, name).close()
        multiplex.close()
        for stream in streams.values():
            stream.close()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class Transport:
    def __init__(self, token, work):
        self.token, self.work = token, Path(work)
        self.requests = []
        self.opener = urllib.request.build_opener(NoRedirect)
        self.deadline = time.monotonic() + 1200

    def open(self, original):
        url = 'https://api.github.com' + original if original.startswith('/') else original
        for count in range(6):
            if time.monotonic() > self.deadline:
                raise TimeoutError('Whole fetch deadline expired')
            parts = urllib.parse.urlsplit(url)
            if parts.scheme != 'https' or parts.username or parts.password:
                raise ValueError('Only normal HTTPS redirects are accepted')
            headers = {'User-Agent': 'MoonTxnWitness-independent-public-audit',
                       'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
            if parts.hostname == 'api.github.com':
                if not parts.path.startswith('/repos/' + REPOSITORY + '/'):
                    raise ValueError('API access is restricted to this repository')
                headers['Authorization'] = 'Bearer ' + self.token
            # Do not retain url/Location/query/header values: redirects can be signed.
            self.requests.append({'host': parts.hostname, 'redirect': count,
                                  'authenticated': parts.hostname == 'api.github.com'})
            try:
                response = self.opener.open(urllib.request.Request(url, headers=headers, method='GET'), timeout=20)
                if response.status != 200:
                    response.close()
                    raise ValueError('Unexpected successful HTTP response status')
                return response
            except urllib.error.HTTPError as error:
                if error.code not in (301, 302, 303, 307, 308):
                    raise RuntimeError('HTTP status ' + str(error.code)) from None
                target = error.headers.get('Location')
                error.close()
                if not target:
                    raise ValueError('Redirect without a location')
                url = urllib.parse.urljoin(url, target)
            except urllib.error.URLError as error:
                raise RuntimeError('HTTPS transport failure (' + type(error.reason).__name__ + ')') from None
        raise ValueError('Redirect bound exhausted')

    def json(self, route, name):
        path = self.work / name
        pending = self.work / (name + '.pending')
        with self.open(route) as response:
            binding = copy_stream(response, pending, 4 * 1024 * 1024, min(time.monotonic() + 60, self.deadline))
        value = json.loads(read_bounded(pending, 4 * 1024 * 1024))
        os.link(pending, path)
        return value, binding

    def download(self, route, name, maximum, expected_digest=None, expected_bytes=None):
        attempts = []
        for number in range(1, 4):
            path = self.work / (name + '.attempt-' + str(number) + '.part')
            start = time.monotonic()
            try:
                with self.open(route) as response:
                    actual = copy_stream(response, path, maximum, min(start + 300, self.deadline))
                if expected_bytes is not None and actual['bytes'] != expected_bytes:
                    raise ValueError('Downloaded length differs from GitHub artifact metadata')
                if expected_digest is not None and expected_digest != 'sha256:' + actual['sha256']:
                    raise ValueError('Downloaded SHA-256 differs from GitHub artifact digest')
                attempts.append({'attempt': number, 'complete': True, **actual})
                destination = self.work / name
                os.link(path, destination)  # Cannot overwrite a prior accepted file.
                return {'file': name, **actual, 'githubDigest': expected_digest, 'attempts': attempts}
            except Exception as error:
                partial = file_binding(path, maximum + CHUNK) if path.exists() else {'bytes': 0, 'sha256': None}
                attempts.append({'attempt': number, 'complete': False, **partial,
                                 'errorClass': type(error).__name__, 'elapsedSeconds': time.monotonic() - start})
                immutable(self.work / (name + '.attempt-' + str(number) + '.failure.json'), attempts[-1])
                # A digest disagreement is evidence failure, not a reason to retry different bytes.
                if isinstance(error, ValueError) or number == 3:
                    immutable(self.work / (name + '.failed.json'), {'complete': False, 'attempts': attempts,
                              'expectedBytes': expected_bytes, 'expectedGithubDigest': expected_digest,
                              'maximumBytes': maximum})
                    raise RuntimeError('Bounded download failed: ' + name) from None


def safe_extract(archive, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    deadline = time.monotonic() + 300
    with zipfile.ZipFile(archive) as zipped:
        infos = zipped.infolist()
        if len(infos) > 20000 or len({i.filename for i in infos}) != len(infos):
            raise ValueError('ZIP entry count/identity bound')
        if sum(i.file_size for i in infos) > 1024 * 1024 * 1024:
            raise ValueError('ZIP expanded-byte bound')
        for info in infos:
            if time.monotonic() > deadline:
                raise TimeoutError('ZIP extraction deadline expired')
            name = info.filename.replace('\\', '/')
            relative = PurePosixPath(name)
            if (not name or len(name) > 512 or relative.is_absolute() or '..' in relative.parts
                    or re.match(r'^[A-Za-z]:', name) or (info.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('Unsafe ZIP entry')
            if info.file_size > 64 * 1024 * 1024:
                raise ValueError('ZIP individual-file bound')
        for info in infos:
            path = destination.joinpath(*PurePosixPath(info.filename.replace('\\', '/')).parts)
            if info.is_dir():
                path.mkdir(parents=True, exist_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            with zipped.open(info) as source, path.open('xb') as output:
                written = 0
                while block := source.read(CHUNK):
                    if time.monotonic() > deadline:
                        raise TimeoutError('ZIP extraction deadline expired')
                    written += len(block)
                    if written > info.file_size:
                        raise ValueError('ZIP entry grew beyond declared size')
                    output.write(block)
                if written != info.file_size:
                    raise ValueError('ZIP entry ended before declared size')


def fetch(work, profile):
    guard_environment(need_token=True)
    work = Path(work)
    work.mkdir(parents=True, exist_ok=False)
    immutable(work / 'fetch-start.json', {'complete': False, 'sourceCommit': profile['sourceCommit'],
                                         'laterChecks': 'not-executed'})
    transport = Transport(os.environ['GITHUB_TOKEN'], work)
    runs, jobs, artifacts, downloads = [], [], [], []
    try:
        for run_id, workflow in [(profile['coreRun'], '.github/workflows/ci.yml'),
                                 (profile['postgresRun'], '.github/workflows/postgres.yml')]:
            run, _ = transport.json('/repos/' + REPOSITORY + '/actions/runs/' + str(run_id), 'run-' + str(run_id) + '.json')
            assert run['id'] == run_id and run['head_sha'] == profile['sourceCommit']
            assert run['repository']['full_name'] == REPOSITORY and run['path'] == workflow
            assert run['status'] == 'completed' and run['conclusion'] == 'success'
            runs.append(run)
            group, _ = transport.json('/repos/' + REPOSITORY + '/actions/runs/' + str(run_id) + '/jobs?per_page=100', 'jobs-' + str(run_id) + '.json')
            assert group['total_count'] == len(group['jobs']) <= 10
            assert all(j['conclusion'] == 'success' for j in group['jobs'])
            jobs.extend(group['jobs'])
            group, _ = transport.json('/repos/' + REPOSITORY + '/actions/runs/' + str(run_id) + '/artifacts?per_page=100', 'artifacts-' + str(run_id) + '.json')
            assert group['total_count'] == len(group['artifacts']) <= 10
            expected = {'evidence-ubuntu-24.04', 'evidence-windows-2022'} if run_id == profile['coreRun'] else {'actual-postgresql-evidence'}
            assert {a['name'] for a in group['artifacts']} == expected
            for a in group['artifacts']:
                assert not a['expired'] and re.fullmatch(r'sha256:[0-9a-f]{64}', a['digest'])
                assert a['workflow_run']['head_sha'] == profile['sourceCommit']
                assert 0 < a['size_in_bytes'] <= 128 * 1024 * 1024
                downloads.append(transport.download('/repos/' + REPOSITORY + '/actions/artifacts/' + str(a['id']) + '/zip',
                                                   a['name'] + '.zip', 128 * 1024 * 1024, a['digest'], a['size_in_bytes']))
            artifacts.extend(group['artifacts'])
        assert len(jobs) == 3 and len(artifacts) == 3
        for job in jobs:
            downloads.append(transport.download('/repos/' + REPOSITORY + '/actions/jobs/' + str(job['id']) + '/logs',
                                                'job-' + str(job['id']) + '.log', 4 * 1024 * 1024))
        downloads.append(transport.download('/repos/' + REPOSITORY + '/zipball/' + profile['sourceCommit'],
                                            'source-' + profile['sourceCommit'] + '.zip', 180 * 1024 * 1024))
        immutable(work / 'completed-run-states.json', runs)
        immutable(work / 'transport-audit.json', {'sourceCommit': profile['sourceCommit'], 'jobs': jobs, 'artifacts': artifacts,
            'downloads': downloads, 'requests': transport.requests, 'complete': True, 'authenticationMode': 'explicit-repository-workflow-token',
            'personalUserIdentityCheckRequired': False, 'tokenPersisted': False, 'signedUrlPersisted': False,
            'authenticatedRedirectForwarding': False, 'tlsVerificationDisabled': False, 'chunkBytes': CHUNK,
            'downloadAttemptsMaximum': 3, 'wholeAttemptSecondsMaximum': 320})
        for name, folder in [('evidence-ubuntu-24.04.zip', 'artifact-ubuntu-24.04'),
                             ('evidence-windows-2022.zip', 'artifact-windows-2022'),
                             ('actual-postgresql-evidence.zip', 'artifact-postgres'),
                             ('source-' + profile['sourceCommit'] + '.zip', 'source')]:
            safe_extract(work / name, work / folder)
        immutable(work / 'fetch-complete.json', {'complete': True, 'files': len(downloads), 'extractions': 4})
    except Exception as error:
        immutable(work / 'fetch-failed.json', {'complete': False, 'passed': False, 'errorClass': type(error).__name__,
                  'acceptedDownloads': downloads, 'tokenPersisted': False, 'signedUrlPersisted': False,
                  'laterChecks': 'not-executed'})
        raise
