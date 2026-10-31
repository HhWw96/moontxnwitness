"""Distribution input closure. Pure inventory; no archive/build/database IO.

The package consumer suite validates the actual selected source and runtime ZIPs.
Historical evidence remains in Git; fixed executable inputs remain in downloads.
"""
from __future__ import annotations

from collections import defaultdict
import json
from evidence_json import load_receipt
from pathlib import Path, PurePosixPath
from input_cache import public_cached_entries

EXCLUDED_DIRS = {'.git', '_build', '.mooncakes', 'node_modules', 'artifacts',
                 'dist', '__pycache__', '.venv-pg'}
EXCLUDED_NAMES = {'.local-toolchain.json', '.DS_Store'}

# Current source excerpts bound by the portable anomaly audit. These are the
# current implementation, not historical source snapshots or a compiler tree.
V033_ANOMALY_AUDIT_SOURCES = (
    'src/anomalies_v4.mbt', 'src/lost_updates_v4.mbt', 'src/g_single_v4.mbt',
    'src/list_graph_v4.mbt', 'src/classification_v4.mbt', 'src/api_v4.mbt',
    'cmd/v4.mjs',
)

# Preserve complete fixed runs, not just the few trace files used by consumers.
# Their original receipts/SQL/journals/capsules continue to describe these bytes.
FIXED_VERIFICATION_ROOTS = {
    'verification/model-profile-v3/v027-initial': 'configured model host: exact original driver cases, source journals, compiled checks and retained first failures',
    'verification/configured-user-profile/v024-initial': 'configured ORM host: both exact real source packets and retained first failure receipts',
    'verification/capture-persistence/v023-initial': 'configured ORM host: exact earlier real unknown COMMIT input and collector receipts',
    'verification/experimental-candidates/v021-structured-withdrawn': 'withdrawn candidate source, runtime and test preservation; not a stable performance claim',
    'verification/releases/0.2.0/published-package-review/public-reproduction/downloaded-components/0.2.0/portable/dist': 'public20 exact six-file SDK baseline for reproducible performance',
    'verification/fixtures/v010-comparison': 'twenty pinned common control inputs; same original manifest and bytes',
    'verification/performance-v020': 'complete current baseline experiments, including failed first run and raw samples',
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
    'verification/baselines/0.2.0/manifest.json': 'pinned actual published20 provider and archive identities',
    'verification/releases/0.2.0/published-package-review/public-reproduction/evidence/published-package-210-receipt.json': 'bound anonymous public20 download review receipt',
    'verification/relation-v3/frozen-corpus-promotion.json': 'relation oracle and acceptance read this frozen promotion',
    'verification/formal-harness-fix/reproduction/original-full-capture-cost.yml.gz': 'npm test: exact original failed workflow input for job-context regression',
    'verification/v3/dislock-explicit-policy-preregistration-2026-10-21.json': 'fingerprint and explicit-policy audit contract',
    'verification/v3/dislock-sql-supplement-preregistration-2026-10-21.json': 'fingerprint and SQL proof supplement provenance',
    'verification/v3/acceptance-2026-10-21T02-10-46-492Z/receipt.json': 'small original failure referenced by active lifecycle acceptance',
    'verification/v3/acceptance-2026-10-21T02-16-47-059Z/receipt.json': 'small original failure referenced by active lifecycle acceptance',
}



# Source audits intentionally stay out of the portable runtime-only package.
RELATION034_SOURCE_INPUTS = (
    'scripts/v034-source-rules-sdk-test.mjs',
    'scripts/relation-predicate-sdk-test.mjs',
    'scripts/relation-category-reduction-sdk-test.mjs',
    'scripts/v034-public-boundary-independent-test.mjs',
    'scripts/v034-maintenance-bindings.mjs',
    'scripts/v034-maintenance-bindings-test.mjs',
    'scripts/build-fingerprint.mjs',
    'cmd/relation-v4.mjs', 'cmd/relation-reduction-v4.mjs',
    'cmd/sdk.mjs', 'cmd/moontxnwitness.mjs', 'moon.mod', 'package.json',
)
RELATION034_PORTABLE_INPUTS = (
    'scripts/v034-portable-runtime-test.mjs',
    'examples/relation-predicate-categories.mjs',
    'examples/relation-predicate-categories.json',
    'examples/source-rules-v4-roundtrip.mjs',
    'examples/relation-category-reduction.mjs',
    'examples/relation-category-reduction.json',
)
RELATION034_RUNTIME_INPUTS = (
    'dist/core.mjs', 'dist/capture-core.mjs', 'dist/sdk.mjs',
    'dist/moontxnwitness.mjs', 'dist/relation-v4.mjs',
    'dist/relation-reduction-v4.mjs', 'dist/build-manifest.json',
)


def relation034_available(root, version):
    """Activate by stable version or the actual current host API exports."""
    if tuple(map(int, version.split('.'))) >= (0, 3, 4):
        return True
    sdk = Path(root) / 'cmd/sdk.mjs'
    if not sdk.is_file():
        return False
    text = sdk.read_text(encoding='utf8')
    return all(name in text for name in ('classifyRelationV4', 'reduceRelationCategoryV4'))


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
    cached = public_cached_entries(root)
    public_names = {safe_name(n) for n in public_names} | set(cached)
    tested_files = {safe_name(n): value for n, value in tested_files.items()}
    reasons = defaultdict(set)
    required = set()
    missing = []

    def require(name, reason):
        name = safe_name(name)
        path = root / name
        if not path.is_file() or path.is_symlink():
            missing.append({'file': name, 'reason': reason, 'problem': 'missing or non-regular input'})
        elif name in cached and (path.stat().st_size != cached[name]['bytes'] or tested_files.get(name) != cached[name]['sha256']):
            missing.append({'file': name, 'reason': reason, 'problem': 'frozen input differs from independently verified fingerprint'})
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

    public024_compatibility = (tuple(map(int, version.split('.'))) >= (0, 2, 5)
                               or 'cmd/legacy/v024/manifest.json' in public_names)
    if public024_compatibility:
        require_tree('cmd/legacy/v024', 'exact public24 original and derived synchronous ORM replay dependency closure')
        require_tree('fixtures/compat-v024', 'immutable actual public24 producer expectations and original five-module provenance')
        require_tree('verification/compatibility/public-v024-producer-2026-10-23', 'anonymous public24 download and producer evidence')

    public025_compatibility = (tuple(map(int, version.split('.'))) >= (0, 2, 6)
                               or 'cmd/legacy/v025/manifest.json' in public_names)
    if public025_compatibility:
        require_tree('cmd/legacy/v025', 'exact genuine public25 ESM and licence closure for fixed historical worker')
        for name in ('manifest.json', 'core.mjs', 'orm-profile.mjs', 'classification.mjs',
                     'legacy-v024.mjs', 'build-manifest.json', 'LICENSE',
                     'THIRD_PARTY_NOTICES.txt', 'origin.json'):
            require('cmd/legacy/v025/' + name, 'mandatory fixed public25 replay and licence bytes')
        runtime_manifest = root / 'cmd/legacy/v025/manifest.json'
        if runtime_manifest.is_file():
            try:
                runtime_files = json.loads(runtime_manifest.read_text(encoding='utf8')).get('files', {})
                for name in runtime_files:
                    require('cmd/legacy/v025/' + safe_name(name), 'every bound historical25 manifest member')
            except (ValueError, TypeError, AttributeError):
                missing.append({'file': 'cmd/legacy/v025/manifest.json',
                                'problem': 'invalid historical runtime file inventory'})
        require_tree('fixtures/compat-v025', 'immutable genuine public25 producer reports/capsules and runtime provenance')
        require_tree('verification/compatibility/public-v025-producer-2026-10-24', 'original anonymous public25 producer transport and provenance')
        for name in ('cmd/legacy-v025.mjs', 'cmd/legacy-v025-runtime.mjs',
                     'cmd/legacy-v025-worker.mjs', 'cmd/legacy-v025-binding.mjs',
                     'scripts/legacy-v025-runtime.mjs', 'scripts/compat-v025-test.mjs'):
            require(name, 'fixed public25 replay dispatch and fresh-consumer exact compatibility')

    public026_compatibility = (tuple(map(int, version.split('.'))) >= (0, 2, 7)
                               or 'cmd/legacy/v026/manifest.json' in public_names)
    if public026_compatibility:
        require_tree('cmd/legacy/v026', 'exact genuine public26 ESM and licence closure for fixed historical worker')
        for name in ('manifest.json', 'core.mjs', 'orm-profile.mjs', 'classification.mjs',
                     'classification-models.mjs', 'legacy-v024.mjs', 'legacy-v025.mjs',
                     'legacy-v025-runtime.mjs', 'legacy-v025-worker.mjs', 'legacy-v025-binding.mjs',
                     'build-manifest.json', 'LICENSE', 'THIRD_PARTY_NOTICES.txt', 'origin.json'):
            require('cmd/legacy/v026/' + name, 'mandatory fixed public26 replay and licence bytes')
        runtime_manifest26 = root / 'cmd/legacy/v026/manifest.json'
        if runtime_manifest26.is_file():
            try:
                runtime_files26 = json.loads(runtime_manifest26.read_text(encoding='utf8')).get('files', {})
                for name in runtime_files26:
                    require('cmd/legacy/v026/' + safe_name(name), 'every bound historical26 manifest member')
            except (ValueError, TypeError, AttributeError):
                missing.append({'file': 'cmd/legacy/v026/manifest.json', 'problem': 'invalid historical runtime file inventory'})
        require_tree('fixtures/compat-v026', 'immutable genuine public26 producer reports/capsules and raw runtime provenance')
        require_tree('verification/compatibility/public-v026-producer-2026-10-24', 'original anonymous public26 producer transport and provenance')
        for name in ('legacy-v026.mjs', 'legacy-v026-runtime.mjs', 'legacy-v026-worker.mjs', 'legacy-v026-binding.mjs'):
            require('cmd/' + name, 'fixed public26 strict verify/replay dispatch')
            require('dist/' + name, 'installed fixed public26 strict verify/replay dispatch')
        for name in ('scripts/legacy-v026-runtime.mjs', 'scripts/freeze-public026-runtime.mjs',
                     'scripts/legacy-v026-worker-test.mjs', 'scripts/freeze-public026-runtime-test.mjs',
                     'scripts/compat-v026-test.mjs', 'scripts/public026-fixture-binding.mjs'):
            require(name, 'fixed public26 freezing, protocol and fresh-consumer exact compatibility')

    public027_compatibility = (tuple(map(int, version.split('.'))) >= (0, 2, 8)
                               or 'cmd/legacy/v027/manifest.json' in public_names)
    if public027_compatibility:
        require_tree('cmd/legacy/v027', 'exact genuine public27 ESM and licence closure for fixed historical worker')
        for name in ('manifest.json', 'core.mjs', 'orm-profile.mjs', 'classification.mjs',
                     'classification-models.mjs', 'model-profile.mjs', 'capture-core.mjs', 'legacy-v026.mjs',
                     'legacy-v026-runtime.mjs', 'legacy-v026-worker.mjs', 'legacy-v026-binding.mjs', 'legacy-v024.mjs', 'legacy-v025.mjs',
                     'legacy-v025-runtime.mjs', 'legacy-v025-worker.mjs', 'legacy-v025-binding.mjs',
                     'build-manifest.json', 'LICENSE', 'THIRD_PARTY_NOTICES.txt', 'origin.json'):
            require('cmd/legacy/v027/' + name, 'mandatory fixed public27 replay and licence bytes')
        runtime_manifest27 = root / 'cmd/legacy/v027/manifest.json'
        if runtime_manifest27.is_file():
            try:
                runtime_files27 = json.loads(runtime_manifest27.read_text(encoding='utf8')).get('files', {})
                for name in runtime_files27:
                    require('cmd/legacy/v027/' + safe_name(name), 'every bound historical27 manifest member')
            except (ValueError, TypeError, AttributeError):
                missing.append({'file': 'cmd/legacy/v027/manifest.json', 'problem': 'invalid historical runtime file inventory'})
        require_tree('fixtures/compat-v027', 'immutable genuine public27 producer reports/capsules and raw runtime provenance')
        require('fixtures/compat-v027/manifest.json', 'mandatory public27 consumer fixture identity')
        require_tree('verification/compatibility/public-v027-producer-2026-10-26', 'original anonymous public27 producer transport and provenance')
        for name in ('legacy-v027.mjs', 'legacy-v027-runtime.mjs', 'legacy-v027-worker.mjs', 'legacy-v027-binding.mjs'):
            require('cmd/' + name, 'fixed public27 strict verify/replay dispatch')
            require('dist/' + name, 'installed fixed public27 strict verify/replay dispatch')
        for name in ('scripts/legacy-v027-runtime.mjs', 'scripts/freeze-public027-runtime.mjs',
                     'scripts/legacy-v027-worker-test.mjs', 'scripts/public027-worker-smoke.mjs',
                     'scripts/compat-v027-test.mjs', 'scripts/public027-fixture-binding.mjs'):
            require(name, 'fixed public27 freezing, protocol and fresh-consumer exact compatibility')

    if tuple(map(int, version.split('.'))) >= (0, 3, 0):
        require_tree('cmd/legacy/v028', 'exact three genuine public28 runtime contexts and licence closure')
        require_tree('fixtures/compat-v028', 'all original Linux, NTFS and source-filesystem public28 expectations')
        for name in ('compat-v028-test.mjs', 'public028-fixture-binding.mjs'):
            require('scripts/' + name, 'fresh-consumer public28 original fixtures and strict integrity bindings')
        require('examples/mlflow-http-roundtrip.mjs', 'offline replay of the identical real HTTP final623 case')
        require_tree('fixtures/execution-v3/mlflow-http-623', 'unchanged actual HTTP before/fixed observations and original case binding')
        # Full case records remain in Git, rather than multiplying 584 MB of raw
        # logs into every SDK download. Keep their complete original file index.
        for name in ('EVIDENCE-INDEX.json', 'ORIGINAL-FILES-MANIFEST.json',
                     'PUBLIC-COPY-OFFLINE-VERIFY.json', 'independent-review.derived.json',
                     'reduction-16-candidates/ORIGINAL-FILES-MANIFEST.json',
                     'final623-fixed-three/ORIGINAL-FILES-MANIFEST.json',
                     'DELIVERY-STATUS.json', 'PRIVACY-SCAN.json', 'README.md'):
            require('verification/faults/mlflow-http/' + name, 'native HTTP complete original evidence index; full records available in Git')

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

    if tuple(map(int, version.split('.'))) >= (0, 2, 7):
        for name in ('cmd/model-profile.mjs', 'dist/model-profile.mjs',
                     'docs/configured-model-profile.md', 'docs/model-profile-sdk.md',
                     'examples/model-profile-roundtrip.mjs'):
            require(name, 'mandatory configured list/relation source mapping and replay interface')

    diagnosis_available = 'cmd/diagnosis.mjs' in public_names or (root / 'cmd/diagnosis.mjs').is_file()
    if diagnosis_available:
        for name in ('cmd/diagnosis.mjs', 'dist/diagnosis.mjs', 'scripts/diagnosis-sdk-test.mjs', 'docs/diagnosis-sdk.md'):
            require(name, 'mandatory combined diagnosis host, verification and documented scope')
        require_tree('fixtures/diagnosis-v3', 'immutable original observed histories for diagnosis consumers')
        for name in ('manifest.json', 'register-0.json', 'register-4.json', 'register-80.json'):
            require('fixtures/diagnosis-v3/' + name, 'fixed original diagnosis source and provenance bytes')

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
                    evidence = load_receipt(root / target)
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

    relation034 = relation034_available(root, version)
    if relation034:
        for name in RELATION034_SOURCE_INPUTS:
            require(name, 'current relation/source SDK audits require complete source and command inputs')
        require_tree('src', 'current-build relation audit must recompute the complete MoonBit source fingerprint')
        for name in RELATION034_PORTABLE_INPUTS:
            require(name, 'runtime-only relation/source functionality, actual CLI and capsule consumer closure')
        for name in RELATION034_RUNTIME_INPUTS:
            require(name, 'actual compiled relation/source interfaces and shipped build identities')

    if (root/'cmd/sdk.mjs').is_file() and 'classifyModelsV4' in (root/'cmd/sdk.mjs').read_text(encoding='utf8'):
        for name in ('cmd/models-v4.mjs', 'scripts/models-v4-sdk-test.mjs', 'dist/models-v4.mjs',
                     'docs/model-obligations-v4.md', 'examples/models-v4-roundtrip.mjs',
                     'examples/models-v4-register.json', 'examples/models-v4-list.json'):
            require(name, 'current model namespace requires its SDK, audit and offline source-bound consumer')

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
    source.difference_update(cached)

    portable = {'README.md', 'LICENSE', 'CHANGELOG.md', 'THIRD_PARTY.md', 'run-demo.cmd'}
    for folder in ('dist', 'docs', 'examples', 'integrations', 'experiments'):
        for item in (root / folder).rglob('*'):
            name = item.relative_to(root).as_posix()
            if (item.is_file() and not item.is_symlink() and '__pycache__' not in item.parts
                    and item.name != 'package.json' and (folder == 'dist' or name in public_names)):
                portable.add(name)
    portable.update(n for n in required if n.startswith(('verification/', 'dist/')))
    if (root/'cmd/sdk.mjs').is_file() and 'classifyModelsV4' in (root/'cmd/sdk.mjs').read_text(encoding='utf8'):
        portable.add('scripts/models-v4-sdk-test.mjs')
    if tuple(map(int, version.split('.'))) >= (0, 2, 1):
        # Explicit small consumer inputs; no baseline binaries or historical runs.
        for name in ('scripts/v020-compatibility-test.mjs', 'scripts/v020-invalid-compatibility-test.mjs'):
            require(name, 'fresh-consumer actual published20 compatibility')
            portable.add(name)
        for folder in ('fixtures/compat-v020', 'fixtures/compat-v020-invalid', 'fixtures/compat-v020-list-wrapper'):
            require_tree(folder, 'fresh-consumer original published20 capsules')
            portable.update(n for n in public_names if n.startswith(folder + '/'))
    if tuple(map(int, version.split('.'))) >= (0, 2, 2):
        require('scripts/v021-compatibility-test.mjs', 'fresh-consumer actual published21 compatibility')
        portable.add('scripts/v021-compatibility-test.mjs')
        require_tree('fixtures/compat-v021', 'fresh-consumer original published21 capsules')
        portable.update(n for n in public_names if n.startswith('fixtures/compat-v021/'))
    if tuple(map(int, version.split('.'))) >= (0, 2, 3):
        require('scripts/v022-compatibility-test.mjs', 'fresh-consumer actual published22 compatibility')
        portable.add('scripts/v022-compatibility-test.mjs')
        require_tree('fixtures/compat-v022', 'fresh-consumer original published22 capsules')
        portable.update(n for n in public_names if n.startswith('fixtures/compat-v022/'))
    if tuple(map(int, version.split('.'))) >= (0, 2, 4):
        require('scripts/v023-compatibility-test.mjs', 'fresh-consumer actual published23 compatibility')
        portable.add('scripts/v023-compatibility-test.mjs')
        require_tree('fixtures/compat-v023', 'fresh-consumer original published23 capsules')
        portable.update(n for n in public_names if n.startswith('fixtures/compat-v023/'))
    # The standalone execution example consumes exact frozen traces and licenses.
    portable.update(n for n in public_names if n.startswith('fixtures/execution-v3/'))
    if public024_compatibility:
        portable.update(n for n in public_names if n.startswith('fixtures/compat-v024/'))
        portable.add('scripts/compat-v024-test.mjs')
    if public025_compatibility:
        portable.update(n for n in public_names if n.startswith('fixtures/compat-v025/'))
        portable.add('scripts/compat-v025-test.mjs')
    if public026_compatibility:
        portable.update(n for n in public_names if n.startswith('fixtures/compat-v026/'))
        portable.add('scripts/compat-v026-test.mjs')
        portable.add('scripts/public026-fixture-binding.mjs')
    if public027_compatibility:
        portable.update(n for n in public_names if n.startswith('fixtures/compat-v027/'))
        portable.add('scripts/compat-v027-test.mjs')
        portable.add('scripts/public027-fixture-binding.mjs')
    if tuple(map(int, version.split('.'))) >= (0, 3, 0):
        portable.update(n for n in public_names if n.startswith('fixtures/compat-v028/'))
        portable.update(('scripts/compat-v028-test.mjs', 'scripts/public028-fixture-binding.mjs'))
    if tuple(map(int, version.split('.'))) >= (0, 3, 2):
        require('scripts/public031-compatibility-test.mjs', 'fresh-consumer exact public031 runtime compatibility')
        portable.add('scripts/public031-compatibility-test.mjs')
        require('scripts/v4-sdk-test.mjs', 'fresh-consumer typed v4 interfaces and explicit-budget replay')
        portable.add('scripts/v4-sdk-test.mjs')
        require('scripts/register-direct-v4-audit.mjs', 'fresh-consumer independent direct-register category reference')
        portable.add('scripts/register-direct-v4-audit.mjs')
    if tuple(map(int, version.split('.'))) >= (0, 3, 3):
        for name in ('scripts/v033-sdk-test.mjs', 'scripts/lost-update-sdk-test.mjs',
                     'scripts/list-effective-sdk-test.mjs', 'scripts/v033-independent-anomalies-test.mjs',
                     'scripts/public032-compatibility-test.mjs', 'scripts/public032-compatibility-groups.mjs'):
            require(name, 'fresh-consumer current source profiles and exact public032 compatibility')
            portable.add(name)
    if tuple(map(int, version.split('.'))) >= (0, 3, 3):
        for name in V033_ANOMALY_AUDIT_SOURCES:
            require(name, 'portable anomaly audit: exact current source byte bindings')
            portable.add(name)
    if relation034:
        portable.update(RELATION034_PORTABLE_INPUTS)
    portable.update(n for n in public_names if n.startswith('fixtures/orm-profile-v3/'))
    portable.update(n for n in public_names if n.startswith('fixtures/classification-v3/'))
    portable.update(n for n in public_names if n.startswith('fixtures/classification-models-v3/'))
    if diagnosis_available:
        portable.update(n for n in public_names if n.startswith('fixtures/diagnosis-v3/'))
    for name in sorted(source | portable):
        if not (root / name).is_file() or (root / name).is_symlink():
            missing.append({'file': name, 'problem': 'selected item missing or non-regular'})
        elif name in cached and ((root / name).stat().st_size != cached[name]['bytes'] or tested_files.get(name) != cached[name]['sha256']):
            missing.append({'file': name, 'problem': 'selected frozen input lacks its verified fingerprint'})
    return {'source': sorted(source), 'portable': sorted(portable),
            'requiredInputs': sorted(required), 'retainedVerification': sorted(n for n in required if n.startswith('verification/')),
            'reasons': {n: sorted(v) for n, v in sorted(reasons.items())}, 'missingInputs': missing}


def assert_complete(selection):
    if selection['missingInputs']:
        raise AssertionError('Distribution input closure is incomplete: ' + json.dumps(selection['missingInputs'], ensure_ascii=True))
