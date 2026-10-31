"""Synthetic boundary tests for compatibility staging, without public-runtime acceptance."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'artifacts' / 'independent-compat032-staging'
PREFIX = 'MoonTxnWitness-v0.3.2/'
COMMIT = '1234567890abcdef1234567890abcdef12345678'
SHA = lambda raw: hashlib.sha256(raw).hexdigest()
NODE = os.environ.get('MTW_TEST_NODE') or shutil.which('node')
if not NODE:
    raise RuntimeError('Node.js is required for compatibility staging tests')


def junction(link, target):
    if os.name == 'nt':
        quote = lambda p: "'" + str(p).replace("'", "''") + "'"
        result = subprocess.run(['powershell', '-NoProfile', '-Command',
            'New-Item -ItemType Junction -Path ' + quote(link) + ' -Target ' + quote(target) + ' | Out-Null'], capture_output=True, text=True)
        if result.returncode:
            raise unittest.SkipTest('Directory junction unavailable: ' + result.stderr.strip())
    else:
        link.symlink_to(target, target_is_directory=True)


class StagingTests(unittest.TestCase):
    def setUp(self):
        PARENT.mkdir(parents=True, exist_ok=True)
        self.assertGreater(shutil.disk_usage(PARENT).free, 500 * 1024 * 1024)
        self.base = Path(tempfile.mkdtemp(prefix='case-', dir=PARENT))
        self.links = []

    def tearDown(self):
        # Unlink only junctions made by this test before removing its private tree.
        for link in reversed(self.links):
            if link.is_symlink():
                link.unlink()
            elif os.path.lexists(link):
                os.rmdir(link)
        self.assertEqual(self.base.parent, PARENT)
        shutil.rmtree(self.base)

    def portable(self, changes=None, extra=None):
        pool = self.base / 'pool'; (pool / 'legacy/v031').mkdir(parents=True)
        legacy = b'export const frozen = true;\n'
        (pool / 'legacy/v031/core.mjs').write_bytes(legacy)
        entries = {'LICENSE': b'Synthetic fixture license\n',
            'dist/build-manifest.json': b'{"version":"0.3.2"}',
            **{'dist/' + name: ('export const fixture = ' + json.dumps(name) + ';\n').encode()
               for name in ['sdk.mjs', 'core.mjs', 'capture-core.mjs', 'legacy-v031.mjs', 'legacy-v031-binding.mjs', 'v4.mjs']},
            'dist/legacy/v031/core.mjs': legacy}
        entries.update(changes or {})
        archive = self.base / 'portable.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for rel, raw in entries.items(): z.writestr(PREFIX + rel, raw)
            for rel, raw in extra or []: z.writestr(PREFIX + rel, raw)
        return archive, pool, entries

    def freeze(self, archive, pool, output=None, checksum=None, commit=COMMIT):
        output = output or self.base / 'component.zip'
        command = [sys.executable, '-B', '-X', 'utf8', str(ROOT / 'scripts/freeze_public032.py'),
            '--portable', str(archive), '--sha256', checksum or SHA(archive.read_bytes()),
            '--commit', commit, '--pool-root', str(pool), '--output', str(output)]
        return subprocess.run(command, capture_output=True, text=True), output

    def installation(self, marker=None):
        source = self.base / 'source'; cmd = source / 'cmd'; cmd.mkdir(parents=True)
        output = self.base / 'installed'; output.mkdir()
        raw = b'export const original = 32;\n'
        component = cmd / 'legacy-components/v032/core.mjs'; component.parent.mkdir(parents=True); component.write_bytes(raw)
        pin = {'version': '0.3.2', 'files': {'core.mjs': {'bytes': len(raw), 'sha256': SHA(raw), 'source': 'legacy-components/v032/core.mjs'}}}
        prefix = '' if marker is None else "import {writeFileSync} from 'node:fs';writeFileSync(" + json.dumps(str(marker)) + ",'executed');\n"
        (cmd / 'legacy-v032-binding.mjs').write_text(prefix + 'export const PUBLIC032=Object.freeze(' + json.dumps(pin, separators=(',', ':')) + ');\nfor(const e of Object.values(PUBLIC032.files))Object.freeze(e);\nObject.freeze(PUBLIC032.files);\n', encoding='utf-8', newline='\n')
        (cmd / 'legacy-v032.mjs').write_text('export const syntheticWorker = true;\n', encoding='utf-8', newline='\n')
        (cmd / 'compact-runtime.mjs').write_text('export function createCompactRuntimeLoader(pin,options){return {get(){return options.installationRoot},cleanup(){}}}\n', encoding='utf-8', newline='\n')
        return source, output, raw

    def install(self, source, output, patch=''):
        code = """
import {createRequire,syncBuiltinESMExports} from 'node:module';
import {pathToFileURL} from 'node:url';
const fs=createRequire(import.meta.url)('node:fs');
const patch=process.argv[3];
if(patch==='link-exdev'){fs.linkSync=()=>{const e=Error('synthetic EXDEV');e.code='EXDEV';throw e};syncBuiltinESMExports()}
if(patch==='rename-fail'){fs.renameSync=()=>{const e=Error('synthetic EIO');e.code='EIO';throw e};syncBuiltinESMExports()}
const {copyPublic032}=await import(pathToFileURL(process.argv[4]).href);
try{await copyPublic032(process.argv[1],process.argv[2]);console.log(JSON.stringify({passed:true,syntheticLoader:true}));}
catch(error){console.log(JSON.stringify({passed:false,error:String(error)}));process.exitCode=3;}
"""
        return subprocess.run([NODE, '--input-type=module', '-e', code, str(source), str(output), patch,
            str(ROOT / 'scripts/legacy-v032-runtime.mjs')], capture_output=True, text=True)

    def test_freeze_explicit_commit_and_exact_top_bytes(self):
        archive, pool, entries = self.portable(); result, output = self.freeze(archive, pool)
        self.assertEqual(result.returncode, 0, result.stderr)
        meta = json.loads(output.with_suffix('.json').read_text())
        self.assertEqual(meta['binding']['sourceCommit'], COMMIT)
        self.assertFalse(meta['receipt']['publishedComponent'])
        self.assertEqual(meta['binding']['files']['legacy/v031/core.mjs']['source'], 'legacy/v031/core.mjs')
        with zipfile.ZipFile(output) as z:
            expected = {'PublicRuntime-v0.3.2/' + (name[5:] if name.startswith('dist/') else name): raw
                        for name, raw in entries.items() if not name.startswith('dist/legacy/')}
            self.assertEqual(set(z.namelist()), set(expected))
            for name, raw in expected.items(): self.assertEqual(z.read(name), raw)

    def test_freeze_content_reuse_prefers_verified_legacy_and_keeps_full_inventory(self):
        legacy = b'export const frozen = true;\n'
        archive, pool, entries = self.portable(extra=[('dist/reused.mjs', legacy), ('dist/legacy/v031/another.mjs', legacy)])
        (pool / 'legacy/v031/another.mjs').write_bytes(legacy)
        before = {path.relative_to(pool).as_posix(): SHA(path.read_bytes()) for path in pool.rglob('*') if path.is_file()}
        result, output = self.freeze(archive, pool)
        self.assertEqual(result.returncode, 0, result.stderr)
        metadata = json.loads(output.with_suffix('.json').read_text()); files = metadata['binding']['files']
        self.assertEqual(files['reused.mjs']['source'], 'legacy/v031/another.mjs')
        self.assertEqual(files['legacy/v031/core.mjs']['source'], 'legacy/v031/another.mjs')
        with zipfile.ZipFile(archive) as original:
            expected = {}
            for name in original.namelist():
                rel = name[len(PREFIX):]
                rel = rel[5:] if rel.startswith('dist/') else rel
                expected[rel] = original.read(name)
        self.assertEqual(set(files), set(expected))
        for name, raw in expected.items():
            self.assertEqual(files[name]['bytes'], len(raw)); self.assertEqual(files[name]['sha256'], SHA(raw))
        with zipfile.ZipFile(output) as component:
            self.assertNotIn('PublicRuntime-v0.3.2/reused.mjs', component.namelist())
            referenced = {row['source'][len('legacy-components/v032/'):] for row in files.values() if row['source'].startswith('legacy-components/v032/')}
            self.assertEqual(set(component.namelist()), {'PublicRuntime-v0.3.2/' + name for name in referenced})
        self.assertLess(metadata['receipt']['uniqueSourceFiles'], metadata['receipt']['fullRuntimeFiles'])
        self.assertEqual(metadata['receipt']['uniqueSourceFiles'], metadata['receipt']['uniqueContents'])
        self.assertEqual(before, {path.relative_to(pool).as_posix(): SHA(path.read_bytes()) for path in pool.rglob('*') if path.is_file()})

    def test_freeze_top_content_reuse_is_deterministic_across_archive_order(self):
        archive, pool, entries = self.portable()
        with zipfile.ZipFile(archive, 'a') as packed: packed.writestr(PREFIX + 'dist/zsdk.mjs', entries['dist/sdk.mjs'])
        result, first = self.freeze(archive, pool)
        self.assertEqual(result.returncode, 0, result.stderr)
        reverse = self.base / 'reverse.zip'
        with zipfile.ZipFile(archive) as packed, zipfile.ZipFile(reverse, 'w', zipfile.ZIP_DEFLATED) as out:
            for info in reversed(packed.infolist()): out.writestr(info.filename, packed.read(info))
        result, second = self.freeze(reverse, pool, self.base / 'second.zip')
        self.assertEqual(result.returncode, 0, result.stderr)
        a = json.loads(first.with_suffix('.json').read_text()); b = json.loads(second.with_suffix('.json').read_text())
        self.assertEqual(a['binding']['files'], b['binding']['files'])
        self.assertEqual(a['binding']['componentSha256'], b['binding']['componentSha256'])
        self.assertNotEqual(a['binding']['archiveSha256'], b['binding']['archiveSha256'])
        self.assertEqual(a['binding']['files']['zsdk.mjs']['source'], 'legacy-components/v032/sdk.mjs')
        with zipfile.ZipFile(first) as component:
            self.assertIn('PublicRuntime-v0.3.2/sdk.mjs', component.namelist())
            self.assertNotIn('PublicRuntime-v0.3.2/zsdk.mjs', component.namelist())

    def test_freeze_identical_output_is_idempotent(self):
        archive, pool, _ = self.portable(); result, output = self.freeze(archive, pool)
        self.assertEqual(result.returncode, 0, result.stderr); before = output.read_bytes()
        result, _ = self.freeze(archive, pool, output); self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_bytes(), before)

    def test_freeze_different_output_is_not_overwritten(self):
        archive, pool, _ = self.portable(); output = self.base / 'component.zip'; output.write_bytes(b'keep-me')
        result, _ = self.freeze(archive, pool, output)
        self.assertNotEqual(result.returncode, 0); self.assertEqual(output.read_bytes(), b'keep-me')

    def test_freeze_different_sidecar_is_not_overwritten(self):
        archive, pool, _ = self.portable(); sidecar = self.base / 'component.json'; sidecar.write_bytes(b'keep-sidecar')
        result, _ = self.freeze(archive, pool)
        self.assertNotEqual(result.returncode, 0); self.assertEqual(sidecar.read_bytes(), b'keep-sidecar')

    def test_freeze_same_output_two_processes_are_safe(self):
        archive, pool, _ = self.portable(); output = self.base / 'component.zip'
        command = [sys.executable, '-B', '-X', 'utf8', str(ROOT / 'scripts/freeze_public032.py'), '--portable', str(archive), '--sha256', SHA(archive.read_bytes()), '--commit', COMMIT, '--pool-root', str(pool), '--output', str(output)]
        children = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        for child in children:
            stdout, stderr = child.communicate(timeout=60)
            self.assertEqual(child.returncode, 0, stdout + stderr)
        with zipfile.ZipFile(output) as z: self.assertIsNone(z.testzip())
        self.assertEqual(json.loads(output.with_suffix('.json').read_text())['binding']['componentSha256'], SHA(output.read_bytes()))

    def test_freeze_changed_pool_bytes_are_refused(self):
        archive, pool, _ = self.portable(); (pool / 'legacy/v031/core.mjs').write_bytes(b'corrupt pool')
        result, output = self.freeze(archive, pool)
        self.assertNotEqual(result.returncode, 0); self.assertFalse(output.exists())

    def test_freeze_wrong_checksum_and_truncated_archive_are_refused(self):
        archive, pool, _ = self.portable(); result, _ = self.freeze(archive, pool, checksum='0' * 64)
        self.assertNotEqual(result.returncode, 0)
        archive.write_bytes(archive.read_bytes()[:-20]); result, output = self.freeze(archive, pool)
        self.assertNotEqual(result.returncode, 0); self.assertFalse(output.exists())

    def test_freeze_traversal_and_case_collision_are_refused(self):
        for rel in ['dist/../outside.mjs', 'dist/CORE.mjs']:
            with self.subTest(rel=rel):
                # Each loop gets a fresh pool/archive/output location.
                if (self.base / 'pool').exists(): shutil.rmtree(self.base / 'pool')
                archive, pool, _ = self.portable(extra=[(rel, b'bad')]); result, output = self.freeze(archive, pool)
                self.assertNotEqual(result.returncode, 0); self.assertFalse(output.exists())

    def test_freeze_aggregate_top_budget_is_refused(self):
        archive, pool, _ = self.portable(extra=[('dist/large' + str(i) + '.mjs', b'0' * (12 * 1024 * 1024)) for i in range(3)])
        result, output = self.freeze(archive, pool)
        self.assertNotEqual(result.returncode, 0); self.assertIn('Runtime expansion budget', result.stderr); self.assertFalse(output.exists())

    def test_freeze_pool_ancestor_junction_is_refused(self):
        archive, pool, _ = self.portable(); outside = self.base / 'outside'; shutil.move(pool / 'legacy', outside)
        link = pool / 'legacy'; junction(link, outside); self.links.append(link)
        result, output = self.freeze(archive, pool)
        self.assertNotEqual(result.returncode, 0); self.assertFalse(output.exists())

    def test_freeze_output_ancestor_junction_is_refused(self):
        archive, pool, _ = self.portable(); outside = self.base / 'outside'; outside.mkdir(); link = self.base / 'linked'
        junction(link, outside); self.links.append(link); result, _ = self.freeze(archive, pool, link / 'component.zip')
        self.assertNotEqual(result.returncode, 0); self.assertFalse((outside / 'component.zip').exists())

    def test_installer_exact_synthetic_source_and_copy_fallback(self):
        source, output, raw = self.installation(); result = self.install(source, output, 'link-exdev')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((output / 'legacy-components/v032/core.mjs').read_bytes(), raw)
        for name in ['legacy-v032.mjs', 'legacy-v032-binding.mjs', 'compact-runtime.mjs']:
            self.assertEqual((source / 'cmd' / name).read_bytes(), (output / name).read_bytes())

    def test_installer_existing_different_component_is_not_overwritten(self):
        source, output, _ = self.installation(); target = output / 'legacy-components/v032/core.mjs'; target.parent.mkdir(parents=True); target.write_bytes(b'keep-component')
        result = self.install(source, output)
        self.assertNotEqual(result.returncode, 0); self.assertEqual(target.read_bytes(), b'keep-component')

    def test_installer_helper_target_junction_is_refused(self):
        source, output, _ = self.installation(); outside = self.base / 'outside'; outside.mkdir(); sentinel = outside / 'sentinel'; sentinel.write_bytes(b'keep')
        link = output / 'legacy-v032.mjs'; junction(link, outside); self.links.append(link)
        result = self.install(source, output)
        self.assertNotEqual(result.returncode, 0); self.assertEqual(sentinel.read_bytes(), b'keep')

    def test_installer_helper_target_hardlink_does_not_mutate_external_file(self):
        source, output, _ = self.installation(); outside = self.base / 'outside.mjs'; outside.write_bytes(b'keep-outside')
        os.link(outside, output / 'legacy-v032.mjs'); result = self.install(source, output)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr); self.assertEqual(outside.read_bytes(), b'keep-outside')
        self.assertEqual((output / 'legacy-v032.mjs').read_bytes(), (source / 'cmd/legacy-v032.mjs').read_bytes())

    def test_installer_failed_rename_cleans_private_staging(self):
        source, output, _ = self.installation(); result = self.install(source, output, 'rename-fail')
        self.assertNotEqual(result.returncode, 0); self.assertFalse(list(output.glob('.compat-helper-*')))
        self.assertFalse((output / 'legacy-v032.mjs').exists())

    def test_installer_malformed_binding_cannot_write_outside_output(self):
        source, output, raw = self.installation()
        (source / 'escaped.mjs').write_bytes(raw)
        pin = {'version': '0.3.2', 'files': {'core.mjs': {'bytes': len(raw), 'sha256': SHA(raw), 'source': 'legacy-components/v032/../../../escaped.mjs'}}}
        (source / 'cmd/legacy-v032-binding.mjs').write_text('export const PUBLIC032=Object.freeze(' + json.dumps(pin, separators=(',', ':')) + ');\nfor(const e of Object.values(PUBLIC032.files))Object.freeze(e);\nObject.freeze(PUBLIC032.files);\n', encoding='utf-8', newline='\n')
        result = self.install(source, output)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.base / 'escaped.mjs').exists(), 'Malformed binding wrote outside its output directory')
        self.assertEqual(list(output.iterdir()), [], 'Malformed PIN must fail before filesystem installation')

    def test_installer_dangling_helper_target_link_is_refused(self):
        source, output, _ = self.installation(); missing = self.base / 'missing-outside.mjs'; link = output / 'legacy-v032.mjs'
        try: link.symlink_to(missing)
        except OSError as error: raise unittest.SkipTest('File symlink privilege unavailable: ' + str(error))
        self.links.append(link)
        result = self.install(source, output)
        self.assertNotEqual(result.returncode, 0); self.assertFalse(missing.exists()); self.assertTrue(link.is_symlink())

    def test_installer_oversized_helper_is_refused(self):
        source, output, _ = self.installation(); (source / 'cmd/legacy-v032.mjs').write_bytes(b'0' * (8 * 1024 * 1024 + 1))
        result = self.install(source, output)
        self.assertNotEqual(result.returncode, 0); self.assertFalse((output / 'legacy-v032.mjs').exists())

    def test_installer_executable_binding_is_refused_without_sideeffects(self):
        marker = self.base / 'executed-marker'; source, output, _ = self.installation(marker)
        result = self.install(source, output)
        self.assertNotEqual(result.returncode, 0); self.assertFalse(marker.exists())
        self.assertEqual(list(output.iterdir()), [])

    def test_installer_binding_ancestor_junction_does_not_execute_code(self):
        marker = self.base / 'executed-marker'; source, output, _ = self.installation(marker)
        outside = self.base / 'outside-cmd'; shutil.move(source / 'cmd', outside)
        link = source / 'cmd'; junction(link, outside); self.links.append(link)
        result = self.install(source, output)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(marker.exists(), 'Binding code executed through a source junction before validation')


if __name__ == '__main__':
    tracked_files = ['scripts/legacy-v032-runtime.mjs', 'scripts/freeze_public032.py', 'cmd/legacy-v032.mjs', 'cmd/compact-runtime.mjs']
    before = {name: SHA((ROOT / name).read_bytes()) for name in tracked_files}
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(StagingTests))
    PARENT.mkdir(parents=True, exist_ok=True)
    files = ['scripts/legacy-v032-runtime.mjs', 'scripts/freeze_public032.py', 'cmd/legacy-v032.mjs', 'cmd/compact-runtime.mjs']
    receipt = {'suite': 'compat032-staging-synthetic-boundaries-2', 'passed': result.wasSuccessful(),
        'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors), 'skips': len(result.skipped),
        'public032Verified': False, 'actualCompactLoaderAssemblyExecuted': False, 'fixedPinConstructorValidationUsed': True, 'actualPublicRuntimeExecuted': False,
        'scope': 'Synthetic installer/freezer boundary tests; trusted PIN metadata constructor only, stub assembly loader. No public provenance, loader-assembly acceptance or compatibility claim.',
        'testedFileSha256Before': before, 'testedFileSha256': {name: SHA((ROOT / name).read_bytes()) for name in files},
        'testFileSha256': SHA(Path(__file__).read_bytes()), 'failedCases': [{'name': str(case), 'detail': detail} for case, detail in result.failures + result.errors]}
    receipt['implementationUnchangedDuringTests'] = before == receipt['testedFileSha256']
    receipt['passed'] = receipt['passed'] and receipt['implementationUnchangedDuringTests']
    (PARENT / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(receipt, indent=2))
    sys.exit(0 if receipt['passed'] else 1)
