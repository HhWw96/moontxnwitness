"""Read-only CI observation helpers; incomplete metadata never counts as success."""
import time


def ci_details_ready(ci, sha):
    """Return False for pending metadata; reject wrong commits or terminal failures."""
    assert ci['headSha'] == sha, 'CI details differ from the exact release commit'
    conclusion = ci.get('conclusion')
    if conclusion not in (None, '', 'success'):
        raise RuntimeError('Public CI concluded unsuccessfully: ' + str(conclusion))
    jobs = ci.get('jobs')
    if jobs is None or jobs == []:
        return False
    if not isinstance(jobs, list):
        raise TypeError('CI jobs must be a list')
    for job in jobs:
        if job is None:
            continue
        conclusion = job.get('conclusion')
        if conclusion not in (None, '', 'success'):
            raise RuntimeError('Public CI job concluded unsuccessfully: ' + str(conclusion))
    if ci.get('conclusion') != 'success' or len(jobs) < 2:
        return False
    assert len(jobs) == 2, 'Exactly two successful CI jobs are required'
    if any(job is None or job.get('status') != 'completed' or job.get('conclusion') != 'success'
           for job in jobs):
        return False
    assert any(step['name'] == 'Execute Native core on Linux' and step['conclusion'] == 'success'
               for job in jobs for step in (job.get('steps') or [])), 'Linux Native must execute'
    return True


def wait_for_successful_run_list(query, sha, *, timeout=60, interval=5,
                                 clock=None, sleep=None):
    """Observe an eventually consistent run list within one fixed time budget.

    query receives the remaining seconds so its own read timeout is bounded.
    A completed matching failure returns no successes immediately; the caller's
    existing explicit historical-repair path and final rejection remain in force.
    Query/JSON/transport errors propagate instead of being turned into success.
    """
    if timeout <= 0 or interval <= 0:
        raise ValueError('CI observation timeout and interval must be positive')
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    deadline = clock() + timeout
    while clock() < deadline:
        rows = query(deadline - clock())
        if not isinstance(rows, list):
            raise TypeError('CI run query must return a list')
        if clock() >= deadline:
            return []
        matching = [row for row in rows if row['headSha'] == sha]
        successful = [row for row in matching
                      if row['conclusion'] == 'success' and row['status'] == 'completed']
        if successful:
            return successful
        if matching and all(row['status'] == 'completed' and row['conclusion'] not in (None, '')
                            for row in matching):
            return []
        remaining = deadline - clock()
        if remaining > 0:
            sleep(min(interval, remaining))
    return []
