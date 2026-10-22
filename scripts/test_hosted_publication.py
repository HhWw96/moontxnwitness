"""Offline synthetic fault checks only; no build, real download or hosted run."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import hosted_publication as hosted
WORK = ROOT / 'artifacts/hosted-publication-tests'
WORK.mkdir(parents=True, exist_ok=True)


class HostedTests(unittest.TestCase):
    def temporary(self):
        directory = tempfile.TemporaryDirectory(prefix='case-', dir=WORK)
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def inputs(self, expected=None):
        return hosted.validate_inputs('0.1.1', 'a'*40, expected or 'b'*64, 'c'*40)

    def test_input_injection_and_ambiguous_digest_rejected(self):
        for version in ('v0.1.1', '00.1.1', '0.1.1\n', '../1.2.3', '0.1.1;echo hi', '0.1.1-pre', '0.1.1 '):
            with self.subTest(version=version), self.assertRaises(ValueError):
                hosted.validate_inputs(version, 'a'*40, 'b'*64, 'c'*40)
        for tag, registry, workflow in [('A'*40,'b'*64,'c'*40), ('a'*39,'b'*64,'c'*40), ('a'*40,'b'*64+'\n','c'*40), ('a'*40,'$(token)','c'*40), ('a'*40,'b'*64,'c'*39)]:
            with self.assertRaises(ValueError):
                hosted.validate_inputs('0.1.1', tag, registry, workflow)

    def test_anchor_mismatch_never_creates_expected_upload_path(self):
        root = self.temporary()
        source, evidence = root/'source', root/'evidence'
        source.mkdir()
        def fake(url, target, **options):
            self.assertEqual(options['expected_sha256'], 'b'*64)
            Path(target).write_bytes(b'wrong-public-bytes')
        with self.assertRaisesRegex(AssertionError, 'independent publisher'):
            hosted.anchor_registry(source, evidence, self.inputs(), fake)
        self.assertFalse((source/'_build/publish/HhWw96-moontxnwitness-0.1.1.zip').exists())
        self.assertEqual((evidence/'publisher-reference/registry.zip').read_bytes(), b'wrong-public-bytes')

    def test_correct_independent_anchor_and_existing_path_refusal(self):
        root = self.temporary()
        source = root/'source'; source.mkdir()
        payload = b'fake-small-archive-for-offline-digest-test'
        sha = hashlib.sha256(payload).hexdigest()
        def fake(url, target, **options):
            self.assertEqual(url, 'https://download.mooncakes.io/user/HhWw96/moontxnwitness/0.1.1.zip')
            self.assertEqual(options['expected_sha256'], sha)
            Path(target).write_bytes(payload)
        receipt = hosted.anchor_registry(source, root/'evidence', self.inputs(sha), fake)
        self.assertTrue(receipt['matchedIndependentInputBeforeStaging'])
        self.assertEqual((source/receipt['stagedRelativePath']).read_bytes(), payload)
        with self.assertRaisesRegex(AssertionError, 'start absent'):
            hosted.anchor_registry(source, root/'other-evidence', self.inputs(sha), fake)

    def test_original_downloader_uses_anonymous_request(self):
        root = self.temporary()
        spec = importlib.util.spec_from_file_location('test_tag_downloader', ROOT/'scripts/publication_download.py')
        downloader = importlib.util.module_from_spec(spec); spec.loader.exec_module(downloader)
        payload = b'anonymous-fake-response'
        class Response:
            status = 200
            headers = {'Content-Length': str(len(payload))}
            def __enter__(self): self.left=payload; return self
            def __exit__(self,*args): pass
            def geturl(self): return 'https://download.mooncakes.io/fake.zip'
            def read(self,count): raw,self.left=self.left[:count],self.left[count:]; return raw
        def opener(request, **options):
            self.assertIsNone(request.get_header('Authorization'))
            self.assertIsNone(request.get_header('Cookie'))
            self.assertNotIn('Authorization', request.headers)
            self.assertNotIn('Cookie', request.headers)
            return Response()
        downloader.download_file('https://download.mooncakes.io/fake.zip', root/'registry.zip',
            expected_sha256=hashlib.sha256(payload).hexdigest(), opener=opener)

    def test_token_only_reaches_readonly_gh_wrapper_exec(self):
        root = self.temporary()
        wrapper = hosted.create_gh_wrapper(root, '/fake/actual-gh', 'fake-offline-actions-token')
        observed = []
        class Captured(Exception): pass
        def execve(binary, argv, environment):
            observed.append((binary,argv,environment))
            raise Captured()
        inherited = {'PATH':'fixture', 'GH_ACTIONS_READ_TOKEN':'must-remove', 'GITHUB_TOKEN':'must-remove', 'GH_TOKEN':'must-remove'}
        self.assertEqual(hosted.clean_environment(inherited), {'PATH':'fixture'})
        with patch.dict(os.environ,inherited,clear=True), patch.object(sys,'argv',[str(wrapper),'run','list','--repo',hosted.REPOSITORY]), patch('os.execve',side_effect=execve):
            with self.assertRaises(Captured): runpy.run_path(str(wrapper),run_name='__main__')
        binary,argv,environment=observed[0]
        self.assertEqual(environment['GH_TOKEN'],'fake-offline-actions-token')
        self.assertNotIn('GH_ACTIONS_READ_TOKEN',environment); self.assertNotIn('GITHUB_TOKEN',environment)
        self.assertEqual(environment['GH_HOST'],'github.com')
        for args in (['release','create','v0.1.1','--repo',hosted.REPOSITORY], ['run','list','--repo','someone/else']):
            with patch.object(sys,'argv',[str(wrapper),*args]), patch('os.execve',side_effect=AssertionError('must not execute')):
                with self.assertRaises(SystemExit): runpy.run_path(str(wrapper),run_name='__main__')

    def test_head_tag_controller_and_original_verifier_bytes(self):
        root = self.temporary(); (root/'scripts').mkdir()
        # Freeze fixture bytes on Windows too; this tests byte tampering rather
        # than the user's global Git newline conversion preference.
        (root/'.gitattributes').write_text('* -text\n',encoding='utf8')
        (root/'package.json').write_text('{"version":"0.1.1"}',encoding='utf8')
        for name in ('verify_publication.py','publication_download.py'):
            (root/'scripts'/name).write_text('# original fixture\n',encoding='utf8')
        def git(*args): return subprocess.check_output(['git',*args],cwd=root,text=True).strip()
        git('init','-q'); git('config','core.autocrlf','false'); git('config','user.email','offline@example.invalid'); git('config','user.name','Offline fixture')
        git('add','.'); git('-c','commit.gpgsign=false','commit','-qm','fixture'); git('tag','v0.1.1')
        sha=git('rev-parse','HEAD')
        inputs=hosted.validate_inputs('0.1.1',sha,'b'*64,sha)
        record=hosted.attest_source(root,root,inputs)
        self.assertEqual(record['sourceCommit'],sha); self.assertEqual(record['workflowCommit'],sha)
        with self.assertRaisesRegex(AssertionError,'HEAD/tag'):
            hosted.attest_source(root,root,self.inputs())
        (root/'scripts/verify_publication.py').write_text('# silently changed\n',encoding='utf8')
        with self.assertRaisesRegex(AssertionError,'code changed'):
            hosted.attest_source(root,root,inputs)

    def test_collection_retains_current_receipts_source_registry_but_not_large_assets(self):
        root = self.temporary(); source=root/'source'; evidence=root/'evidence'
        work=source/'artifacts/public-verification/run-fake'; (work/'consumer/_build').mkdir(parents=True)
        (work/'consumer/.mooncakes').mkdir()
        for name in ('registry.zip','MoonTxnWitness-v0.1.1-source.zip','MoonTxnWitness-v0.1.1-portable.zip'):
            (work/name).write_bytes(b'fake-bytes-not-an-archive')
        (work/'consumer/consumer_wbtest.mbt').write_text('test "fixture" {}',encoding='utf8')
        (work/'consumer/_build/private.log').write_text('exclude',encoding='utf8')
        (work/'consumer/.mooncakes/private.json').write_text('exclude',encoding='utf8')
        release=source/'verification/releases/0.1.1'; release.mkdir(parents=True)
        old=release/'publication-old.json'; old.write_text('{"passed":false}',encoding='utf8')
        new=release/'publication.json'; new.write_text('{"passed":true}',encoding='utf8')
        hosted.save(evidence/'receipt-baseline.json',{old.relative_to(source).as_posix():hosted.digest(old)})
        hosted.save(evidence/'execution.json',{'publicVerificationRuns':['run-fake']})
        hosted.collect_evidence(source,evidence,self.inputs())
        copied={p.relative_to(evidence).as_posix() for p in evidence.rglob('*') if p.is_file()}
        self.assertIn('receipts/publication.json',copied)
        self.assertNotIn('receipts/publication-old.json',copied)
        self.assertIn('original-verifier/run-fake/registry.zip',copied)
        self.assertIn('original-verifier/run-fake/consumer/consumer_wbtest.mbt',copied)
        self.assertFalse(any('-source.zip' in n or '-portable.zip' in n or 'private' in n for n in copied))

    def test_failed_synthetic_verifier_has_clean_env_and_keeps_receipt_log(self):
        root=self.temporary(); source=root/'source'; evidence=root/'evidence'
        (source/'scripts').mkdir(parents=True)
        script = '''import json,os,pathlib,sys
assert not any(k in os.environ for k in ('GH_ACTIONS_READ_TOKEN','GH_TOKEN','GITHUB_TOKEN','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN'))
root=pathlib.Path('.')
work=root/'artifacts/public-verification/run-failed'
work.mkdir(parents=True)
(work/'registry.zip').write_bytes(b'fake-registry-for-failure-collection')
receipt=root/'verification/releases/0.1.1/publication.json'
receipt.parent.mkdir(parents=True)
receipt.write_text(json.dumps({'passed':False,'failure':'synthetic'}))
print('Synthetic verifier failed after writing its original receipt')
sys.exit(7)
'''
        (source/'scripts/verify_publication.py').write_text(script,encoding='utf8')
        with patch.dict(os.environ,{'GH_ACTIONS_READ_TOKEN':'fake-secret','GH_TOKEN':'must-remove','GITHUB_TOKEN':'must-remove'}), patch.object(hosted.shutil,'which',return_value='/not-executed/gh'):
            status=hosted.invoke_original(source,evidence,self.inputs(),'fake-actions-token',temp_parent=WORK)
        self.assertEqual(status,7)
        self.assertFalse(json.loads((evidence/'execution.json').read_text(encoding='utf8'))['passed'])
        hosted.collect_evidence(source,evidence,self.inputs())
        self.assertEqual(json.loads((evidence/'receipts/publication.json').read_text(encoding='utf8'))['failure'],'synthetic')
        self.assertIn('Synthetic verifier failed',(evidence/'verification.log').read_text(encoding='utf8'))
        self.assertFalse(any('token' in p.name for p in evidence.rglob('*')))

    def test_workflow_pins_actions_and_calls_original_without_overrides(self):
        text=(ROOT/'.github/workflows/published-downloads.yml').read_text(encoding='utf8')
        import re
        uses=re.findall(r'uses: (\S+)',text)
        self.assertTrue(uses)
        self.assertTrue(all(re.fullmatch(r'actions/[a-z-]+@[0-9a-f]{40}',n) for n in uses))
        self.assertIn('actions: read',text); self.assertIn('contents: read',text)
        self.assertNotIn('contents: write',text); self.assertNotIn('continue-on-error:',text)
        code=(HERE/'hosted_publication.py').read_text(encoding='utf8')
        self.assertIn("command = [sys.executable, '-u', 'scripts/verify_publication.py', inputs.version]",code)


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(HostedTests))
    receipt={'schema':1,'kind':'offline-hosted-publication-candidate-fault-checks',
        'passed':result.wasSuccessful(),'checks':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'actualHostedWorkflowExecuted':False,'actualDownloadsExecuted':False,'actualConsumerBuildExecuted':False,
        'originalVerifierExecuted':False,'syntheticFixturesOnly':True}
    hosted.save(WORK/'offline-checks.json',receipt)
    raise SystemExit(0 if result.wasSuccessful() else 1)
