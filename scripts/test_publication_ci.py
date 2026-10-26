"""Offline CI metadata regressions; synthetic reads and virtual time only."""
import ast
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import publication_ci as observed

SHA = 'a' * 40
OTHER = 'b' * 40
HERE = Path(__file__).resolve().parent


class Clock:
    def __init__(self):
        self.now = 0
        self.sleeps = []
    def monotonic(self):
        return self.now
    def sleep(self, seconds):
        assert seconds > 0
        self.sleeps.append(seconds)
        self.now += seconds


def job(*, status='completed', conclusion='success', native=True):
    return {'status': status, 'conclusion': conclusion,
            'steps': [{'name': 'Execute Native core on Linux', 'conclusion': 'success'}]
            if native else [{'name': 'Other step', 'conclusion': 'success'}]}


def details(**changes):
    value = {'headSha': SHA, 'conclusion': 'success', 'jobs': [job(), job(native=False)]}
    value.update(changes)
    return value


def row(*, sha=SHA, status='completed', conclusion='success', event='push'):
    return {'headSha': sha, 'status': status, 'conclusion': conclusion,
            'databaseId': 7, 'event': event}


def wait_function(clock, read):
    """Execute only the actual publisher's wait function, with all IO injected."""
    parsed = ast.parse((HERE/'release.py').read_text(encoding='utf-8'))
    function = next(node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name == 'wait_for_ci')
    namespace = {'time': clock, 'run': read, 'json': json, 'MODULE': 'HhWw96/moontxnwitness',
                 'VERSION': '0.2.0', 'ci_details_ready': observed.ci_details_ready}
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'release-wait-only', 'exec'), namespace)
    return namespace['wait_for_ci']


class CiDetailTests(unittest.TestCase):
    def test_exact_two_completed_jobs_and_native_are_ready_without_mutation(self):
        value = details()
        before = copy.deepcopy(value)
        self.assertTrue(observed.ci_details_ready(value, SHA))
        self.assertEqual(value, before)

    def test_missing_empty_and_partial_jobs_are_pending(self):
        for jobs in (None, [], [job()], [None, job()]):
            with self.subTest(jobs=jobs):
                self.assertFalse(observed.ci_details_ready(details(jobs=jobs), SHA))

    def test_job_conclusion_empty_none_or_in_progress_cannot_pass(self):
        for pending in (job(conclusion=None), job(conclusion=''),
                        job(status='in_progress'), job(status='queued')):
            self.assertFalse(observed.ci_details_ready(details(jobs=[pending, job()]), SHA))

    def test_workflow_pending_cannot_pass_even_if_jobs_are_complete(self):
        for conclusion in ('', None):
            self.assertFalse(observed.ci_details_ready(details(conclusion=conclusion), SHA))

    def test_wrong_commit_rejected_before_readiness(self):
        with self.assertRaisesRegex(AssertionError, 'exact release commit'):
            observed.ci_details_ready(details(headSha=OTHER), SHA)

    def test_workflow_failure_cancel_and_other_terminal_results_rejected(self):
        for conclusion in ('failure', 'cancelled', 'timed_out', 'action_required', 'skipped'):
            with self.subTest(conclusion=conclusion), self.assertRaises(RuntimeError):
                observed.ci_details_ready(details(conclusion=conclusion), SHA)

    def test_job_failure_rejected_even_with_partial_metadata(self):
        for conclusion in ('failure', 'cancelled', 'timed_out'):
            with self.subTest(conclusion=conclusion), self.assertRaises(RuntimeError):
                observed.ci_details_ready(details(jobs=[None, job(conclusion=conclusion)]), SHA)

    def test_more_than_two_jobs_rejected(self):
        with self.assertRaisesRegex(AssertionError, 'Exactly two'):
            observed.ci_details_ready(details(jobs=[job(), job(), job()]), SHA)

    def test_native_absent_or_skipped_rejected(self):
        skipped = job()
        skipped['steps'][0]['conclusion'] = 'skipped'
        for jobs in ([job(native=False), job(native=False)], [skipped, job(native=False)]):
            with self.subTest(jobs=jobs), self.assertRaisesRegex(AssertionError, 'Linux Native'):
                observed.ci_details_ready(details(jobs=jobs), SHA)


class RunListTests(unittest.TestCase):
    def test_empty_wrong_sha_pending_then_real_success(self):
        clock = Clock()
        snapshots = [[], [row(sha=OTHER)], [row(status='in_progress', conclusion=None)], [row()]]
        original = copy.deepcopy(snapshots)
        budgets = []
        def read(remaining):
            budgets.append(remaining)
            return snapshots[len(budgets)-1]
        actual = observed.wait_for_successful_run_list(read, SHA, timeout=10, interval=2,
                                                     clock=clock.monotonic, sleep=clock.sleep)
        self.assertEqual(actual, snapshots[-1])
        self.assertEqual(budgets, [10, 8, 6, 4])
        self.assertEqual(snapshots, original)

    def test_completed_failure_or_cancel_returns_no_success_without_wait(self):
        for conclusion in ('failure', 'cancelled'):
            clock = Clock()
            actual = observed.wait_for_successful_run_list(lambda remaining: [row(conclusion=conclusion)],
                SHA, clock=clock.monotonic, sleep=clock.sleep)
            self.assertEqual(actual, [])
            self.assertEqual(clock.sleeps, [])

    def test_completed_but_missing_conclusion_is_pending_not_failure(self):
        clock = Clock()
        rows = [[row(conclusion=None)], [row()]]
        def read(remaining):
            return rows.pop(0)
        self.assertEqual(observed.wait_for_successful_run_list(read, SHA,
            clock=clock.monotonic, sleep=clock.sleep), [row()])
        self.assertEqual(clock.sleeps, [5])

    def test_wrong_sha_success_never_passes_and_observation_expires(self):
        clock = Clock()
        budgets = []
        def read(remaining):
            budgets.append(remaining)
            return [row(sha=OTHER)]
        self.assertEqual(observed.wait_for_successful_run_list(read, SHA, timeout=11, interval=5,
            clock=clock.monotonic, sleep=clock.sleep), [])
        self.assertEqual(budgets, [11, 6, 1])
        self.assertEqual(clock.sleeps, [5, 5, 1])
        self.assertEqual(clock.now, 11)

    def test_late_success_after_deadline_cannot_pass(self):
        clock = Clock()
        def read(remaining):
            self.assertEqual(remaining, 3)
            clock.now += 4
            return [row()]
        self.assertEqual(observed.wait_for_successful_run_list(read, SHA, timeout=3,
            clock=clock.monotonic, sleep=clock.sleep), [])
        self.assertEqual(clock.sleeps, [])

    def test_transport_error_propagates_and_no_retry_swallows_it(self):
        clock = Clock()
        def read(remaining):
            raise RuntimeError('original read failure')
        with self.assertRaisesRegex(RuntimeError, 'original read failure'):
            observed.wait_for_successful_run_list(read, SHA, clock=clock.monotonic, sleep=clock.sleep)
        self.assertEqual(clock.sleeps, [])

    def test_malformed_list_and_nonpositive_budgets_rejected(self):
        with self.assertRaises(TypeError):
            observed.wait_for_successful_run_list(lambda remaining: None, SHA)
        for options in ({'timeout':0}, {'interval':0}, {'timeout':-1}):
            with self.assertRaises(ValueError):
                observed.wait_for_successful_run_list(lambda remaining: self.fail('no query'), SHA, **options)


class PublisherIntegrationTests(unittest.TestCase):
    def test_actual_wait_rechecks_metadata_without_resetting_deadline(self):
        clock = Clock()
        pending = [details(jobs=[]), details(jobs=None),
                   details(jobs=[job(status='in_progress', conclusion=''), job()]), details()]
        calls = []
        def read(args, **options):
            self.assertGreater(options['timeout'], 0)
            self.assertLessEqual(options['timeout'], 300)
            calls.append(args)
            if args[2] == 'list':
                return json.dumps([row()])
            return json.dumps(pending.pop(0))
        with redirect_stdout(io.StringIO()):
            wait_function(clock, read)(SHA)
        self.assertEqual(clock.now, 45)
        self.assertEqual(sum(args[2]=='view' for args in calls), 4)
        self.assertEqual(sum(args[2]=='list' and args[args.index('--workflow')+1]=='postgres.yml' for args in calls), 1)

    def test_actual_wait_pending_times_out_at_original_1800_seconds(self):
        clock = Clock()
        calls = []
        def read(args, **options):
            calls.append((args, options))
            self.assertLessEqual(options['timeout'], 1800-clock.now)
            return json.dumps([row()] if args[2]=='list' else details(jobs=None))
        with self.assertRaisesRegex(TimeoutError, 'observation window'):
            wait_function(clock, read)(SHA)
        self.assertEqual(clock.now, 1800)
        self.assertEqual(sum(args[2]=='view' for args,_ in calls), 120)
        self.assertFalse(any('postgres.yml' in args for args,_ in calls))

    def test_actual_wait_rejects_failed_and_cancelled_push_runs(self):
        for conclusion in ('failure', 'cancelled'):
            clock = Clock()
            def read(args, **options):
                return json.dumps([row(conclusion=conclusion)])
            with self.subTest(conclusion=conclusion), self.assertRaisesRegex(RuntimeError, 'Public CI failed'):
                wait_function(clock, read)(SHA)
            self.assertEqual(clock.now, 0)

    def test_actual_wait_does_not_accept_other_sha_or_dispatch(self):
        for run in (row(sha=OTHER), row(event='workflow_dispatch')):
            clock = Clock()
            def read(args, **options):
                self.assertEqual(args[2], 'list', 'nonmatching runs must not reach detail acceptance')
                return json.dumps([run])
            with self.subTest(run=run), self.assertRaises(TimeoutError):
                wait_function(clock, read)(SHA)
            self.assertEqual(clock.now, 1800)

    def test_actual_wait_rejects_wrong_detail_sha(self):
        clock = Clock()
        def read(args, **options):
            return json.dumps([row()] if args[2]=='list' else details(headSha=OTHER))
        with self.assertRaisesRegex(AssertionError, 'exact release commit'):
            wait_function(clock, read)(SHA)

    def test_actual_wait_never_accepts_response_arriving_after_deadline(self):
        clock = Clock()
        def read(args, **options):
            self.assertEqual(args[2], 'list')
            clock.now = 1801
            return json.dumps([row()])
        with self.assertRaises(TimeoutError):
            wait_function(clock, read)(SHA)

    def test_actual_verifier_postgres_lookup_uses_read_budget_and_exact_sha(self):
        tree = ast.parse((HERE/'verify_publication.py').read_text(encoding='utf-8'))
        statement = next(node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                         and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                         and node.value.func.id == 'wait_for_successful_run_list')
        clock = Clock()
        reads = []
        def read(args, **options):
            self.assertIn('postgres.yml', args)
            self.assertEqual(args[args.index('--commit')+1], SHA)
            self.assertEqual(args[args.index('--json')+1], 'databaseId,status,conclusion,headSha')
            reads.append(options['timeout'])
            return json.dumps([] if len(reads)==1 else [row(sha=OTHER), row()])
        namespace = {'run':read,'json':json,'MODULE':'HhWw96/moontxnwitness',
                     'tag_sha':SHA,'wait_for_successful_run_list':observed.wait_for_successful_run_list}
        with patch.object(observed.time,'monotonic',clock.monotonic), patch.object(observed.time,'sleep',clock.sleep):
            exec(compile(ast.Module(body=[statement],type_ignores=[]),'verifier-pg-lookup-only','exec'), namespace)
        self.assertEqual(namespace['successful'], [row()])
        self.assertEqual(reads, [60,55])


def current_release_gate():
    """Execute only the new publisher gate; no publisher import or external IO."""
    parsed = ast.parse((HERE/'release.py').read_text(encoding='utf8'))
    function = next(n for n in parsed.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'validate_scoped_acceptance')
    gates = [n for n in function.body if isinstance(n, ast.If)
             and isinstance(n.test, ast.Compare)
             and isinstance(n.test.comparators[0], ast.Tuple)
             and ast.literal_eval(n.test.comparators[0]) == (0, 2, 8)]
    assert len(gates) == 1
    return ast.fix_missing_locations(ast.Module(body=gates, type_ignores=[]))


def current_release_fixture():
    # Synthetic receipt-shape fixture, not an executed SDK/DB/package receipt.
    root = Path('synthetic-release-root')
    hashes = {str(root/name): value * 64 for name, value in (
        ('dist/model-profile.mjs', '1'), ('dist/diagnosis.mjs', '2'),
        ('fixtures/compat-v026/manifest.json', '3'),
        ('fixtures/diagnosis-v3/register-0.json', '4'),
        ('fixtures/diagnosis-v3/register-4.json', '5'),
        ('fixtures/diagnosis-v3/register-80.json', '6'))}
    hashes[str(root/'fixtures/compat-v027/manifest.json')] = 'f196ee5fc21e3fe78ea75ee3c73e904206e1a0f24dd8e847a0e6fe504461eba8'
    manifest = {'coreSha256': 'a'*64, 'captureCoreSha256': 'b'*64}
    compatibility = lambda number, count, families: {
        'format': 'genuine-public0'+number+'-current-consumer/v1',
        'passed': True, 'currentRuntimeVersion': '0.2.8',
        'expectedRegenerated': False, 'normalAnalysisHistoricalWorkersStarted': 0,
        'originalReportsAndCapsulesRemainByteIdentical': True,
        'verificationResponseOnlyCurrentEngineDeltaAllowedFor': ['v1', 'v2'],
        'originalProducerFamilies': families, 'checkCount': count,
        'checks': [{'name': 'actual current runtime version core and capture manifest bindings'
                    if i == 0 else 'synthetic-shape-check-'+str(i), 'passed': True}
                   for i in range(count)]}
    original26 = compatibility('26', 623, 35)
    original26.update(currentCoreSha256=manifest['coreSha256'],
        originalFixtureManifestSha256=hashes[str(root/'fixtures/compat-v026/manifest.json')],
        originalModelFamilies=14)
    original27 = compatibility('27', 418, 46)
    original27['originalModelProfileFamilies'] = 11
    model = {'passed': True, 'cases': 50, 'failures': [],
             'compiledCoreSha256': manifest['coreSha256'],
             'hostSourceSha256': hashes[str(root/'dist/model-profile.mjs')],
             'actualDatabaseExecution': False, 'formalPerformanceMeasurement': False,
             'sourceClosedReductionClaimed': False}
    diagnostic = {'passed': True, 'version': '0.2.8', 'checks': 66,
                  'cases': [{'name': 'synthetic-shape-check-'+str(i), 'passed': True} for i in range(66)],
                  'coreSha256': manifest['coreSha256'], 'captureCoreSha256': manifest['captureCoreSha256'],
                  'diagnosisHostSha256': hashes[str(root/'dist/diagnosis.mjs')],
                  'newDatabaseExecution': False, 'newMoonCompilation': False,
                  'formalPerformanceMeasured': False, 'public027BaselineCompared': False,
                  'originalSerialAndModelReportsAndCapsulesPreserved': True, 'syntheticCases': 7,
                  'frozenOriginalCases': [{'id': name, 'sha256': hashes[str(root/('fixtures/diagnosis-v3/'+name+'.json'))]}
                                          for name in ('register-0', 'register-4', 'register-80')]}
    summary = {'configuredModelProfileHostTests': model,
               'configuredModelProfileDriverTests': {'passed': True, 'actualDatabaseExecution': False},
               'publicV026CompatibilityTests': original26, 'publicV027CompatibilityTests': original27,
               'diagnosisHostTests': diagnostic}
    for number in ('26', '27'):
        summary['historicalWorker0'+number+'ProtocolTests'] = {
            'format': 'synthetic-public'+number+'-worker-framework-tests/v1',
            'passed': True, 'checks': 42, 'frameworkOnly': True,
            'actualPublicFixturesExecuted': False, 'realSdkImported': False}
    descriptions = [
        'actual public26 35-family fixed-runtime exact compatibility and tamper controls',
        'exact genuine public027 full46 compatibility and configured model-profile replay',
        'configured list/relation original-source model projection and complete capsule replay',
        'combined diagnosis preserves original unknown analysis and verifies direct INT evidence']
    package = {'checks': [kind+' '+description for kind in ('source', 'portable') for description in descriptions]}
    return {'VERSION': '0.2.8', 'ROOT': root, 'manifest': manifest,
            'summary': summary, 'package': package, 'sha256': lambda path: hashes[str(path)]}, hashes


def render_publisher_notes(version):
    tree = ast.parse((HERE/'release.py').read_text(encoding='utf8'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'publish')
    statements = [n for n in function.body if isinstance(n, ast.If) and any(
        isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name) and call.func.value.id == 'notes'
        and call.func.attr == 'write_text' for call in ast.walk(n))]
    class Notes:
        def write_text(self, text, **options):
            self.text = text
    notes = Notes()
    namespace = {'VERSION': version, 'MODULE': 'HhWw96/moontxnwitness', 'tag': 'v'+version, 'notes': notes}
    exec(compile(ast.Module(body=statements, type_ignores=[]), 'publisher-notes-only', 'exec'), namespace)
    return notes.text


class CurrentReleaseGateTests(unittest.TestCase):
    def execute(self, namespace):
        exec(compile(current_release_gate(), 'publisher-v028-gate-only', 'exec'), namespace)

    def test_complete_synthetic_shape_passes_without_mutation_or_invented_baseline_requirement(self):
        namespace, _ = current_release_fixture()
        before = copy.deepcopy((namespace['summary'], namespace['package'], namespace['manifest']))
        self.execute(namespace)
        self.assertEqual((namespace['summary'], namespace['package'], namespace['manifest']), before)
        self.assertFalse(namespace['summary']['diagnosisHostTests']['public027BaselineCompared'])

    def test_pre028_release_retains_original_gate_behavior(self):
        self.execute({'VERSION': '0.2.7'})

    def test_every_new_summary_section_is_required(self):
        namespace, _ = current_release_fixture()
        for field in list(namespace['summary']):
            trial, _ = current_release_fixture()
            del trial['summary'][field]
            with self.subTest(missing=field), self.assertRaises((KeyError, AssertionError)):
                self.execute(trial)

    def test_missing_current_version_and_byte_binding_fields_are_rejected(self):
        fields = {
            'configuredModelProfileHostTests': ('compiledCoreSha256', 'hostSourceSha256', 'failures'),
            'publicV026CompatibilityTests': ('currentRuntimeVersion', 'currentCoreSha256', 'originalFixtureManifestSha256'),
            'publicV027CompatibilityTests': ('currentRuntimeVersion', 'originalProducerFamilies', 'originalModelProfileFamilies'),
            'diagnosisHostTests': ('version', 'coreSha256', 'captureCoreSha256', 'diagnosisHostSha256', 'frozenOriginalCases')}
        for section, names in fields.items():
            for field in names:
                namespace, _ = current_release_fixture()
                del namespace['summary'][section][field]
                with self.subTest(section=section, missing=field), self.assertRaises((KeyError, AssertionError)):
                    self.execute(namespace)

    def test_altered_core_capture_host_source_and_original_manifest_hashes_are_rejected(self):
        for section, fields in {
            'configuredModelProfileHostTests': ('compiledCoreSha256', 'hostSourceSha256'),
            'publicV026CompatibilityTests': ('currentCoreSha256', 'originalFixtureManifestSha256'),
            'diagnosisHostTests': ('coreSha256', 'captureCoreSha256', 'diagnosisHostSha256')}.items():
            for field in fields:
                namespace, _ = current_release_fixture()
                namespace['summary'][section][field] = '0'*64
                with self.subTest(section=section, field=field), self.assertRaises(AssertionError):
                    self.execute(namespace)
        namespace, hashes = current_release_fixture()
        hashes[str(namespace['ROOT']/'fixtures/compat-v027/manifest.json')] = '0'*64
        with self.assertRaises(AssertionError): self.execute(namespace)
        for field, value in (('id', 'register-forged'), ('sha256', '0'*64)):
            namespace, _ = current_release_fixture()
            namespace['summary']['diagnosisHostTests']['frozenOriginalCases'][0][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError): self.execute(namespace)

    def test_compatibility_false_version_regeneration_worker_and_evidence_claims_are_rejected(self):
        mutations = [('passed', False), ('currentRuntimeVersion', '0.2.7'), ('expectedRegenerated', True),
                     ('normalAnalysisHistoricalWorkersStarted', 1),
                     ('originalReportsAndCapsulesRemainByteIdentical', False),
                     ('verificationResponseOnlyCurrentEngineDeltaAllowedFor', ['v1', 'v2', 'model-profile']),
                     ('originalProducerFamilies', 1)]
        for section in ('publicV026CompatibilityTests', 'publicV027CompatibilityTests'):
            for field, value in mutations:
                namespace, _ = current_release_fixture()
                namespace['summary'][section][field] = value
                with self.subTest(section=section, field=field), self.assertRaises(AssertionError):
                    self.execute(namespace)
            namespace, _ = current_release_fixture()
            namespace['summary'][section]['checks'][1]['passed'] = False
            with self.assertRaises(AssertionError): self.execute(namespace)
        namespace, _ = current_release_fixture()
        namespace['summary']['publicV027CompatibilityTests']['checks'][0]['name'] = 'omitted core binding'
        with self.assertRaises(AssertionError): self.execute(namespace)

    def test_reduced_check_counts_and_missing_actual_check_rows_are_rejected(self):
        for section in ('publicV026CompatibilityTests', 'publicV027CompatibilityTests'):
            for matching_count in (True, False):
                namespace, _ = current_release_fixture()
                value = namespace['summary'][section]
                value['checks'].pop()
                if matching_count: value['checkCount'] -= 1
                with self.subTest(section=section, matching_count=matching_count), self.assertRaises(AssertionError):
                    self.execute(namespace)
        namespace, _ = current_release_fixture()
        namespace['summary']['diagnosisHostTests']['checks'] -= 1
        namespace['summary']['diagnosisHostTests']['cases'].pop()
        with self.assertRaises(AssertionError): self.execute(namespace)
        namespace, _ = current_release_fixture()
        namespace['summary']['configuredModelProfileHostTests']['cases'] = 49
        with self.assertRaises(AssertionError): self.execute(namespace)

    def test_model_profile_scope_driver_and_failure_claims_are_rejected(self):
        for section, fields in {
            'configuredModelProfileHostTests': [('actualDatabaseExecution', True), ('formalPerformanceMeasurement', True),
                                                ('sourceClosedReductionClaimed', True), ('failures', [{'passed': False}])],
            'configuredModelProfileDriverTests': [('passed', False), ('actualDatabaseExecution', True)]}.items():
            for field, value in fields:
                namespace, _ = current_release_fixture()
                namespace['summary'][section][field] = value
                with self.subTest(section=section, field=field), self.assertRaises(AssertionError): self.execute(namespace)

    def test_diagnosis_claims_versions_and_any_failed_case_are_rejected(self):
        for field, value in [('passed', False), ('version', '0.2.7'), ('newDatabaseExecution', True),
                             ('newMoonCompilation', True), ('formalPerformanceMeasured', True),
                             ('originalSerialAndModelReportsAndCapsulesPreserved', False), ('syntheticCases', 0)]:
            namespace, _ = current_release_fixture()
            namespace['summary']['diagnosisHostTests'][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError): self.execute(namespace)
        namespace, _ = current_release_fixture()
        namespace['summary']['diagnosisHostTests']['cases'][0]['passed'] = False
        with self.assertRaises(AssertionError): self.execute(namespace)

    def test_every_source_and_portable_consumer_marker_is_required(self):
        namespace, _ = current_release_fixture()
        for marker in list(namespace['package']['checks']):
            trial, _ = current_release_fixture()
            trial['package']['checks'].remove(marker)
            with self.subTest(missing=marker), self.assertRaises(AssertionError): self.execute(trial)

    def test_synthetic_worker_checks_cannot_replace_actual_compatibility_evidence(self):
        for section in ('historicalWorker026ProtocolTests', 'historicalWorker027ProtocolTests'):
            for field, value in [('passed', False), ('checks', 0), ('frameworkOnly', False),
                                 ('actualPublicFixturesExecuted', True), ('realSdkImported', True), ('format', 'other')]:
                namespace, _ = current_release_fixture()
                namespace['summary'][section][field] = value
                with self.subTest(section=section, field=field), self.assertRaises(AssertionError): self.execute(namespace)

    def test_actual_latest_notes_describe_028_and_keep_pre028_behavior(self):
        notes = render_publisher_notes('0.2.8')
        for value in ('diagnoseV3', 'verifyDiagnosisV3', '1.124x', '46 genuine', 'HTTP log_batch',
                      'Unknown analysis remains visible', 'not an overall v0.2.8 SDK'):
            self.assertIn(value, notes)
        self.assertNotIn('on the future roadmap', notes)
        self.assertIn('six-model classification', render_publisher_notes('0.2.7'))


if __name__ == '__main__':
    unittest.main()
