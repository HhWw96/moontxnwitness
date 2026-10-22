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


if __name__ == '__main__':
    unittest.main()
