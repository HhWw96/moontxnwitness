"""Distribution input closure. Pure inventory; no archive/build/database IO.

The package consumer suite validates the actual selected source and runtime ZIPs.
Historical evidence remains in Git; fixed executable inputs remain in downloads.
"""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path, PurePosixPath

EXCLUDED_DIRS = {'.git', '_build', '.mooncakes', 'node_modules', 'artifacts',
                 'dist', '__pycache__', '.venv-pg'}
EXCLUDED_NAMES = {'.local-toolchain.json', '.DS_Store'}

# Preserve complete fixed runs, not just the few trace files used by consumers.
# Their original receipts/SQL/journals/capsules continue to describe these bytes.
FIXED_VERIFICATION_ROOTS = {
    'verification/v3/tools': 'npm test: independent executable audit helpers',
    'verification/v3/synthetic-dislock-source-closure-v1': 'fingerprint and fresh-consumer v3 proof/reduction',
    'verification/business/dislock/v3-647afacfcbe14586b46714bac34c8f30': 'fingerprint and independent SQL/policy audits',
    'verification/business/dislock/v3-db5f87c5620c4f8e955172340023482c': 'fresh-consumer real dislock replay, complete original run',
    'verification/list-v3/postgres-2de835316d5f40d6b7e4bfeab4e4b8e4': 'fresh-consumer real list replay, complete public original run',
    'verification/relation-v3/postgres-2026-10-21': 'fresh-consumer relation proofs/reduction, complete original run',
    'verification/faults/mlflow/run-c7227fba032f4c92b127b7357252107c': 'fingerprint, execution-fault audit and fresh-consumer diagnostic',
    'verification/experimental-candidates/orm-source2-r3-2026-10-21': 'npm test and fresh-consumer fixed ORM source/journal fixtures',
}
FIXED_VERIFICATION_FILES = {
    'verification/relation-v3/frozen-corpus-promotion.json': 'relation oracle and acceptance read this frozen promotion',
    'verification/v3/dislock-explicit-policy-preregistration-2026-10-21.json': 'fingerprint and explicit-policy audit contract',
    'verification/v3/dislock-sql-supplement-preregistration-2026-10-21.json': 'fingerprint and SQL proof supplement provenance',
    'verification/v3/acceptance-2026-10-21T02-10-46-492Z/receipt.json': 'small original failure referenced by active lifecycle acceptance',
    'verification/v3/acceptance-2026-10-21T02-16-47-059Z/receipt.json': 'small original failure referenced by active lifecycle acceptance',
}


def safe_name(name: str) -> str:
    path = PurePosixPath(name)
    if (not name or '\\' in name or path.is_absolute() or ':' in name or
            any(p in ('', '.', '..') for p in name.split('/'))):
        raise ValueError('Unsafe distribution path: ' + name)
    return path.as_posix()


def select_distribution_files(root, public_names, tested_files, version):
    """Return source/portable inventories and explicit reasons; fail on missing input.

    tested_files is the existing verificationFingerprint result already checked by
    package_release.py, not a second approximation of its input rules.
    """
    root = Path(root).resolve()
    public_names = {safe_name(n) for n in public_names}
    tested_files = {safe_name(n): value for n, value in tested_files.items()}
    reasons = defaultdict(set)
    required = set()
    missing = []

    def require(name, reason):
        name = safe_name(name)
        path = root / name
        if not path.is_file() or path.is_symlink():
            missing.append({'file': name, 'reason': reason, 'problem': 'missing or non-regular input'})
        elif name not in public_names and not name.startswith('dist/'):
            missing.append({'file': name, 'reason': reason, 'problem': 'not in public inventory; never add ignored private evidence'})
        else:
            required.add(name)
            reasons[name].add(reason)

    def require_tree(folder, reason):
        folder = safe_name(folder).rstrip('/')
        names = sorted(n for n in public_names if n.startswith(folder + '/') and '__pycache__' not in PurePosixPath(n).parts)
        if not names:
            missing.append({'file': folder + '/', 'reason': reason, 'problem': 'required public directory is empty/missing'})
        for name in names:
            require(name, reason)

    def receipt_pointer(value, parent, reason, tree=False):
        # Receipt-relative ../../summary.json is valid, but cannot escape the
        # verification tree, reference an absolute host path, or add private IO.
        if not isinstance(value, str) or not value or '\\' in value or ':' in value or value.startswith('/'):
            missing.append({'file': str(value), 'reason': reason, 'problem': 'invalid local evidence pointer'})
            return None
        path = (root / parent / value).resolve()
        if not path.is_relative_to(root / 'verification'):
            missing.append({'file': value, 'reason': reason, 'problem': 'evidence pointer escapes verification'})
            return None
        name = path.relative_to(root).as_posix()
        if tree:
            require_tree(name, reason)
        else:
            require(name, reason)
        return name

    for name in tested_files:
        require(name, 'exact existing verificationFingerprint input')
    for folder, reason in FIXED_VERIFICATION_ROOTS.items():
        require_tree(folder, reason)
    for name, reason in FIXED_VERIFICATION_FILES.items():
        require(name, reason)

    relation_manifest = root / 'fixtures/relation-v3/manifest.json'
    if relation_manifest.is_file():
        for archive in json.loads(relation_manifest.read_text(encoding='utf8'))['historyArchives']:
            require(archive['file'], 'relation oracle/acceptance: exact historyArchives manifest dependency')
    else:
        missing.append({'file': 'fixtures/relation-v3/manifest.json', 'problem': 'cannot expand relation history archive closure'})
    supplement = root / 'verification/v3/dislock-sql-supplement-preregistration-2026-10-21.json'
    if supplement.is_file():
        plan = json.loads(supplement.read_text(encoding='utf8'))
        for field in ('originalFailureReceipt', 'originalAuditImplementation'):
            require(plan[field]['path'], 'small original failure/source referenced by SQL supplement contract')

    pg = 'verification/releases/' + safe_name(version) + '/postgres/'
    for name in sorted(public_names):
        if name.startswith(pg):
            require(name, 'current-version actual PostgreSQL reproduction bundle, including original failed attempts')
        elif name.startswith('verification/') and '/' not in name[len('verification/'):]:
            if name != 'verification/package.json':
                require(name, 'small top-level release/test/compatibility receipt')
    for suffix in ('receipt.json', 'capture.json', 'rr.capsule.json', 'serial.capsule.json', 'mini.capsule.json'):
        require(pg + suffix, 'mandatory current-version real PostgreSQL bundle input')

    # Current release claims are small receipt roots, not the entire development
    # history. Follow their direct evidence pointers and whole recorded run dirs.
    # The same path convention accommodates a later actual presence run.
    acceptance_name = 'verification/releases/' + safe_name(version) + '/acceptance.json'
    if acceptance_name in public_names:
        require(acceptance_name, 'current scoped release acceptance declaration')
        acceptance = json.loads((root / acceptance_name).read_text(encoding='utf8'))
        parent = str(PurePosixPath(acceptance_name).parent)
        for field in ('databaseEvidence', 'historicalRoadmapCheckpoint'):
            if isinstance(acceptance.get(field), str):
                target = receipt_pointer(acceptance[field], parent, 'current acceptance direct ' + field + ' receipt')
                if field == 'databaseEvidence' and target in required:
                    evidence = json.loads((root / target).read_text(encoding='utf8'))
                    for label, record in evidence.get('receipts', {}).items():
                        if isinstance(record, dict) and isinstance(record.get('path'), str):
                            receipt_pointer(record['path'], 'verification', 'current database ' + label + ' complete public recorded run', tree=True)
        for field in ('tests', 'independentReview'):
            record = acceptance.get(field)
            if isinstance(record, dict) and isinstance(record.get('receipt'), str):
                receipt_pointer(record['receipt'], parent, 'current acceptance ' + field + ' receipt')
    capture_receipt = 'verification/capture-postgres.json'
    if capture_receipt in public_names:
        capture = json.loads((root / capture_receipt).read_text(encoding='utf8'))
        if isinstance(capture.get('path'), str):
            receipt_pointer(capture['path'], 'verification', 'complete public actual capture run referenced by capture-postgres.json', tree=True)

    source = set()
    for name in public_names:
        path = PurePosixPath(name)
        if any(p in EXCLUDED_DIRS or p.startswith(('moontxnwitness-demo-', 'moontxnwitness-postgres-')) for p in path.parts):
            continue
        if path.name in EXCLUDED_NAMES or path.suffix in ('.log', '.pyc') or name == 'verification/package.json':
            continue
        if not name.startswith('verification/') or name in required:
            if (root / name).is_file():
                source.add(name)
    # Source consumers build dist themselves, but every non-dist fingerprint input
    # must survive, even if a future fixed input uses a formerly excluded suffix.
    source.update(n for n in required if not n.startswith('dist/'))

    portable = {'README.md', 'LICENSE', 'CHANGELOG.md', 'THIRD_PARTY.md', 'run-demo.cmd'}
    for folder in ('dist', 'docs', 'examples', 'integrations', 'experiments'):
        for item in (root / folder).rglob('*'):
            name = item.relative_to(root).as_posix()
            if (item.is_file() and not item.is_symlink() and '__pycache__' not in item.parts
                    and item.name != 'package.json' and (folder == 'dist' or name in public_names)):
                portable.add(name)
    portable.update(n for n in required if n.startswith(('verification/', 'dist/')))
    for name in sorted(source | portable):
        if not (root / name).is_file() or (root / name).is_symlink():
            missing.append({'file': name, 'problem': 'selected item missing or non-regular'})
    return {'source': sorted(source), 'portable': sorted(portable),
            'requiredInputs': sorted(required), 'retainedVerification': sorted(n for n in required if n.startswith('verification/')),
            'reasons': {n: sorted(v) for n, v in sorted(reasons.items())}, 'missingInputs': missing}


def assert_complete(selection):
    if selection['missingInputs']:
        raise AssertionError('Distribution input closure is incomplete: ' + json.dumps(selection['missingInputs'], ensure_ascii=True))
