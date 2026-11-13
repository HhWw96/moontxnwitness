import copy
import gzip
import importlib.util
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

SPEC = importlib.util.spec_from_file_location('github_ci_release', Path(__file__).with_name('publish-github-ci-release.py'))
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
V = '0.4.2'
SHA = 'a' * 40
RUN_ID = 123
PREFIX = '/repos/' + M.REPOSITORY


def raw(value):
    return json.dumps(value, separators=(',', ':')).encode()


def packed(files, extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        if extra:
            archive.writestr(*extra)
    return output.getvalue()


def fixture(*, index_change=None, summary_change=None, outer_extra=None, nested_extra=None,
            source_version=V, core_change=False, sums_change=False, source_additions=None,
            source_current_summary=False, outer_additions=None):
    stem = 'MoonTxnWitness-v' + V
    source = {'moon.mod': ('name = "HhWw96/moontxnwitness"\nversion = "' + source_version + '"\n').encode(),
              'src/main.mbt': b'pub fn answer() -> Int { 42 }\n', 'src/moon.pkg': b'options()\n',
              'package.json': raw({'version': source_version})}
    source.update(source_additions or {})
    fingerprint = M.hashlib.sha256()
    for name in sorted(['moon.mod', 'src/main.mbt', 'src/moon.pkg']):
        fingerprint.update(name.encode() + b'\0' + source[name] + b'\0')
    cores = {name: ('not executed: ' + name).encode() for name in ['core.mjs', 'capture-core.mjs', 'configured-session-core.mjs', 'source-components-core.mjs', 'sql-projection-core.mjs', 'sql-fetch-core.mjs']}
    manifest = {'version': V, 'sourceSha256': fingerprint.hexdigest(), 'coreSha256': M.digest(cores['core.mjs']),
                'captureCoreSha256': M.digest(cores['capture-core.mjs']),
                'configuredCoreSha256': {name: M.digest(value) for name, value in cores.items() if name not in ('core.mjs', 'capture-core.mjs')}}
    dist = {'dist/' + name: value for name, value in cores.items()}
    dist['dist/build-manifest.json'] = raw(manifest)
    tested = {name: M.digest(value) for name, value in {**source, **dist}.items()}
    summary = {'version': V, 'passed': True, 'buildManifest': manifest, 'executedTargets': ['js', 'wasm-gc', 'wasm'],
               'coreTestCountsByTarget': {'js': 3, 'wasm-gc': 3, 'wasm': 3}, 'testedFileSha256': tested}
    if summary_change:
        summary_change(summary)
    if source_current_summary:
        source['verification/summary.json'] = raw(summary)
    source_bytes = packed({stem + '/' + name: value for name, value in source.items()}, nested_extra)
    portable_bytes = packed({stem + '/' + name: value for name, value in {**dist, 'package.json': raw({'version': V})}.items()})
    records = [{'file': stem + '-source.zip', 'bytes': len(source_bytes), 'sha256': M.digest(source_bytes), 'files': len(source)},
               {'file': stem + '-portable.zip', 'bytes': len(portable_bytes), 'sha256': M.digest(portable_bytes), 'files': len(dist) + 1}]
    if nested_extra:
        records[0]['files'] += 1
    package = {'version': V, 'passed': True, 'sourceRebuilt': True, 'freshConsumerChecks': 3, 'archives': records}
    files = {**dist, 'verification/summary.json': raw(summary), 'verification/package.json': raw(package),
             'artifacts/' + records[0]['file']: source_bytes, 'artifacts/' + records[1]['file']: portable_bytes,
             'artifacts/' + stem + '-SHA256SUMS.txt': ''.join(row['sha256'] + '  ' + row['file'] + '\n' for row in records).encode()}
    files.update(outer_additions or {})
    if core_change:
        files['dist/core.mjs'] = b'forged current compiled bytes'
    if sums_change:
        files['artifacts/' + stem + '-SHA256SUMS.txt'] += b'0' * 64 + b'  unexpected.zip\n'
    index = {'schema': 1, 'version': V, 'sourceCommit': SHA, 'runId': str(RUN_ID), 'runAttempt': '1',
             'files': [{'file': name, 'bytes': len(value), 'sha256': M.digest(value)} for name, value in files.items()]}
    if index_change:
        index_change(index)
    files['current-run-index.json'] = raw(index)
    data = packed(files, outer_extra)
    run = {'id': RUN_ID, 'head_sha': SHA, 'path': M.WORKFLOW, 'workflow_id': 7, 'event': 'push',
           'status': 'completed', 'conclusion': 'success', 'run_attempt': 1,
           'repository': {'full_name': M.REPOSITORY}, 'head_repository': {'full_name': M.REPOSITORY},
           'run_started_at': '2026-11-13T01:00:00Z'}
    jobs = [{'name': 'verify (' + system + ')', 'status': 'completed', 'conclusion': 'success', 'head_sha': SHA,
             'steps': [{'name': 'Execute Native core on Linux', 'status': 'completed', 'conclusion': 'success'}] if system.startswith('ubuntu') else []}
            for system in ('ubuntu-24.04', 'windows-2022')]
    artifact = {'id': 9, 'name': M.ARTIFACT, 'expired': False, 'workflow_run': {'id': RUN_ID, 'head_sha': SHA},
                'size_in_bytes': len(data), 'digest': 'sha256:' + M.digest(data), 'created_at': '2026-11-13T02:00:00Z'}
    return data, run, jobs, artifact


class FakeGitHub:
    def __init__(self, packet=None):
        self.data, self.run, self.jobs, self.artifact = packet or fixture()
        self.tag = None
        self.release = None
        self.assets = []
        self.mutations = []
        self.downloads = 0
        with zipfile.ZipFile(io.BytesIO(self.data)) as outer:
            source = outer.read('artifacts/MoonTxnWitness-v' + V + '-source.zip')
        with zipfile.ZipFile(io.BytesIO(source)) as archive:
            self.tree = []
            for member in archive.infolist():
                name = member.filename.split('/', 1)[-1]
                content = archive.read(member)
                self.tree.append({'path': name, 'type': 'blob', 'mode': '100644', 'sha': M.git_blob(content)})

    def api(self, method, path, body=None, optional=False):
        if method != 'GET':
            self.mutations.append((method, path, copy.deepcopy(body)))
            if path == PREFIX + '/git/refs':
                self.tag = body['sha']
                return {}
            if path == PREFIX + '/releases':
                self.release = {**body, 'id': 22}
                return copy.deepcopy(self.release)
            raise AssertionError((method, path))
        if path == PREFIX + '/actions/runs/' + str(RUN_ID):
            return copy.deepcopy(self.run)
        if '/jobs?' in path:
            return {'jobs': copy.deepcopy(self.jobs)}
        if path == PREFIX + '/actions/workflows/ci.yml':
            return {'id': 7, 'path': M.WORKFLOW}
        if path == PREFIX + '/git/commits/' + SHA:
            return {'sha': SHA, 'tree': {'sha': 'c' * 40}}
        if path == PREFIX + '/git/trees/' + 'c' * 40 + '?recursive=1':
            return {'truncated': False, 'tree': copy.deepcopy(self.tree)}
        if '/artifacts?' in path:
            return {'artifacts': [copy.deepcopy(self.artifact)]}
        if path == PREFIX + '/git/ref/tags/v' + V:
            return None if self.tag is None else {'ref': 'refs/tags/v' + V, 'object': {'type': 'commit', 'sha': self.tag}}
        if path == PREFIX + '/releases/tags/v' + V:
            return copy.deepcopy(self.release)
        if path.startswith(PREFIX + '/releases/22/assets?'):
            return copy.deepcopy(self.assets)
        raise AssertionError(path)

    def download(self, artifact, target):
        self.downloads += 1
        Path(target).write_bytes(self.data)

    def upload(self, release_id, path):
        self.mutations.append(('UPLOAD', release_id, path.name))
        row = {'name': path.name, 'size': path.stat().st_size, 'digest': 'sha256:' + M.file_digest(path), 'state': 'uploaded'}
        self.assets.append(row)
        return copy.deepcopy(row)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.notes = self.root / 'notes.md'
        self.attempt = 0
        self.notes.write_text('## MoonTxnWitness v' + V + '\n\n- Verified source-bound point reads and complete reports.\n', encoding='utf8')

    def tearDown(self):
        self.temporary.cleanup()

    def prepare(self, client=None, publish=False, name='candidate', **kwargs):
        return M.prepare(client or FakeGitHub(), kwargs.get('version', V), kwargs.get('sha', SHA), RUN_ID, self.notes, self.root / name, publish)

    def reject_packet(self, **kwargs):
        self.attempt += 1
        with self.assertRaises((M.ReleaseError, zipfile.BadZipFile)):
            self.prepare(FakeGitHub(fixture(**kwargs)), name='rejected' + str(self.attempt))

    def test_dry_run_is_reviewable_and_has_no_mutations(self):
        client = FakeGitHub()
        value = self.prepare(client)
        self.assertFalse(value['published'])
        self.assertFalse(value['artifactCodeExecuted'])
        self.assertEqual(client.mutations, [])
        self.assertEqual(len(list((self.root / 'candidate/release').iterdir())), 3)
        self.assertTrue((self.root / 'candidate/evidence/index.json').exists())

    def test_explicit_publish_and_exact_idempotency(self):
        client = FakeGitHub()
        self.assertTrue(self.prepare(client, True)['published'])
        self.assertEqual(len([row for row in client.mutations if row[0] == 'UPLOAD']), 3)
        before = list(client.mutations)
        self.assertTrue(self.prepare(client, True, name='second')['published'])
        self.assertEqual(client.mutations, before)

    def test_wrong_explicit_version_or_sha(self):
        for version, sha in [('v0.4.2', SHA), ('0.4.02', SHA), (V, 'abc'), (V, 'b' * 40)]:
            with self.subTest(version=version, sha=sha), self.assertRaises(M.ReleaseError):
                self.prepare(version=version, sha=sha, name=version.replace('.', '-') + sha[:3])

    def test_failed_ci_and_pr_merge_preview(self):
        for field, value in [('conclusion', 'failure'), ('status', 'in_progress'), ('event', 'pull_request'), ('path', 'other.yml')]:
            with self.subTest(field=field):
                client = FakeGitHub()
                client.run[field] = value
                with self.assertRaises(M.ReleaseError):
                    self.prepare(client, name=field)
                self.assertEqual(client.downloads, 0)

    def test_each_platform_job_and_native_must_run(self):
        for kind in ('windows', 'linux', 'native', 'missing-native'):
            with self.subTest(kind=kind):
                client = FakeGitHub()
                if kind == 'windows':
                    client.jobs[1]['conclusion'] = 'failure'
                elif kind == 'linux':
                    client.jobs[0]['conclusion'] = 'skipped'
                elif kind == 'native':
                    client.jobs[0]['steps'][0]['conclusion'] = 'skipped'
                else:
                    client.jobs[0]['steps'] = []
                with self.assertRaises(M.ReleaseError):
                    self.prepare(client, name=kind)

    def test_forged_index_version_source_run_and_file_hash(self):
        cases = [lambda value: value.update(version='0.4.1'), lambda value: value.update(sourceCommit='b' * 40),
                 lambda value: value.update(runId='124'), lambda value: value.update(runAttempt='2'),
                 lambda value: value['files'][0].update(sha256='0' * 64)]
        for index, mutation in enumerate(cases):
            with self.subTest(index=index):
                with self.assertRaises(M.ReleaseError):
                    self.prepare(FakeGitHub(fixture(index_change=mutation)), name='index' + str(index))

    def test_original_github_digest_and_length_are_independent(self):
        for field, value in [('digest', 'sha256:' + '0' * 64), ('size_in_bytes', 2)]:
            client = FakeGitHub()
            client.artifact[field] = value
            with self.assertRaises(M.ReleaseError):
                self.prepare(client, name=field)

    def test_archive_target_digests_and_current_core_bindings(self):
        self.reject_packet(sums_change=True)
        self.reject_packet(core_change=True)

    def test_summary_package_and_tested_runtime_must_pass(self):
        mutations = [lambda value: value.update(passed=False), lambda value: value.update(version='0.4.1'),
                     lambda value: value.update(executedTargets=['js']),
                     lambda value: value['testedFileSha256'].update({'dist/core.mjs': '0' * 64})]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(M.ReleaseError):
                self.prepare(FakeGitHub(fixture(summary_change=mutation)), name='summary' + str(index))

    def test_nested_package_version_is_independent_of_index(self):
        self.reject_packet(source_version='0.4.1')

    def test_committed_source_git_blobs_are_independent_of_build_claims(self):
        client = FakeGitHub()
        client.tree[0]['sha'] = 'b' * 40
        with self.assertRaises(M.ReleaseError):
            self.prepare(client)
        self.assertFalse((self.root / 'candidate/release').exists())

    def test_present_non_moonbit_executables_are_commit_bound_even_when_all_claimed_hashes_are_recomputed(self):
        for index, name in enumerate(['cmd/ship.mjs', 'scripts/ship.py', 'integrations/python/ship.py',
                                      'examples/ship.mjs', '.github/workflows/ship.yml']):
            client = FakeGitHub(fixture(source_additions={name: b'forged but receipt-bound bytes'}))
            next(row for row in client.tree if row['path'] == name)['sha'] = M.git_blob(b'actual committed original')
            with self.subTest(name=name), self.assertRaises(M.ReleaseError):
                self.prepare(client, name='rehashed' + str(index))
            self.assertEqual(client.mutations, [])

    def test_tracked_production_source_cannot_be_silently_omitted(self):
        for index, name in enumerate(['cmd/ship.mjs', 'integrations/python/ship.py']):
            client = FakeGitHub()
            client.tree.append({'path': name, 'type': 'blob', 'mode': '100644', 'sha': M.git_blob(b'committed')})
            with self.subTest(name=name), self.assertRaises(M.ReleaseError):
                self.prepare(client, name='missing' + str(index))

    def test_explicit_commit_bound_frozen_cache_exclusion_is_preserved(self):
        cache = gzip.compress(raw({'cmd/omitted.mjs': {'sha256': '0' * 64}}), mtime=0)
        manifest = {'format': 'moontxnwitness-frozen-input-index/v1', 'index': 'inputs.json.gz',
                    'indexBytes': len(cache), 'indexSha256': M.digest(cache), 'fileCount': 1}
        client = FakeGitHub(fixture(source_additions={'scripts/frozen-inputs.json': raw(manifest), 'scripts/inputs.json.gz': cache}))
        client.tree.append({'path': 'cmd/omitted.mjs', 'type': 'blob', 'mode': '100644', 'sha': M.git_blob(b'cached')})
        self.assertFalse(self.prepare(client)['published'])

    def test_changed_generated_receipt_requires_matching_validated_outer_index(self):
        client = FakeGitHub(fixture(source_current_summary=True))
        next(row for row in client.tree if row['path'] == 'verification/summary.json')['sha'] = M.git_blob(b'old committed receipt')
        self.assertFalse(self.prepare(client)['published'])
        client = FakeGitHub(fixture(source_additions={'verification/unindexed.json': b'changed receipt'}))
        next(row for row in client.tree if row['path'] == 'verification/unindexed.json')['sha'] = M.git_blob(b'old committed receipt')
        with self.assertRaises(M.ReleaseError):
            self.prepare(client, name='unindexed-receipt')

    def test_indexed_executable_helpers_do_not_become_generated_receipt_exceptions(self):
        for index, name in enumerate(['verification/v3/tools/ship.py', 'verification/helpers/ship.mjs',
                                      'artifacts/ship.sh', 'verification/ship.mbt', 'verification/ship.ps1',
                                      'verification/ship.sql']):
            changed = b'changed executable bytes, all artifact claims recomputed'
            client = FakeGitHub(fixture(source_additions={name: changed}, outer_additions={name: changed}))
            next(row for row in client.tree if row['path'] == name)['sha'] = M.git_blob(b'actual committed executable')
            with self.subTest(name=name), self.assertRaises(M.ReleaseError):
                self.prepare(client, name='indexed-helper' + str(index))
            self.assertEqual(client.mutations, [])

    def test_outer_and_nested_zip_traversal_and_unindexed_members(self):
        for index, name in enumerate(['../evil', '/absolute', 'C:/absolute', 'a\\b', 'extra-unindexed']):
            with self.subTest(name=name), self.assertRaises(M.ReleaseError):
                self.prepare(FakeGitHub(fixture(outer_extra=(name, b'bad'))), name='outer' + str(index))
        self.reject_packet(nested_extra=('../escape', b'bad'))

    def test_outer_and_nested_symlinks(self):
        link = zipfile.ZipInfo('link')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.reject_packet(outer_extra=(link, b'target'))
        nested = zipfile.ZipInfo('MoonTxnWitness-v' + V + '/link')
        nested.create_system = 3
        nested.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.reject_packet(nested_extra=(nested, b'target'))

    def test_decoded_json_duplicates_rejected_at_every_depth(self):
        for text in [b'{"version":1,"versi\\u006fn":2}', b'{"a":{"x":1,"x":2}}']:
            with self.subTest(text=text), self.assertRaises(M.ReleaseError):
                M.strict_json(text)

    def test_zip_case_collisions_rejected(self):
        self.reject_packet(outer_extra=('CURRENT-RUN-INDEX.JSON', b'{}'))

    def test_preexisting_unexpected_tag_or_release_is_never_replaced(self):
        client = FakeGitHub()
        client.tag = 'b' * 40
        with self.assertRaises(M.ReleaseError):
            self.prepare(client)
        self.assertEqual(client.mutations, [])
        client = FakeGitHub()
        client.tag = SHA
        client.release = {'id': 22, 'tag_name': 'v' + V, 'target_commitish': SHA, 'body': 'unexpected'}
        with self.assertRaises(M.ReleaseError):
            self.prepare(client, name='unexpected-release')
        self.assertEqual(client.mutations, [])

    def test_unexpected_existing_assets_are_not_overwritten(self):
        client = FakeGitHub()
        self.prepare(client, True)
        client.assets[0]['digest'] = 'sha256:' + '0' * 64
        before = list(client.mutations)
        with self.assertRaises(M.ReleaseError):
            self.prepare(client, True, name='bad-existing-asset')
        self.assertEqual(client.mutations, before)

    def test_notes_must_be_technical_explicit_caller_content(self):
        for index, suffix in enumerate(['AI assistance', 'competition review', '比赛审核']):
            self.notes.write_text('MoonTxnWitness v' + V + '\n' + suffix, encoding='utf8')
            with self.assertRaises(M.ReleaseError):
                self.prepare(name='notes' + str(index))

    def test_notes_version_prefix_and_prerelease_do_not_match_exact_heading(self):
        for index, heading in enumerate(['## MoonTxnWitness v0.4.20', '## MoonTxnWitness v0.4.2.1',
                                         '## MoonTxnWitness v0.4.2-preview', 'MoonTxnWitness v0.4.2']):
            self.notes.write_text(heading + '\n\n- Technical changes.\n', encoding='utf8')
            with self.subTest(heading=heading), self.assertRaises(M.ReleaseError):
                self.prepare(name='heading' + str(index))


if __name__ == '__main__':
    unittest.main()
