"""Offline GitHub job-env context guard; reference: official Context availability table."""
from pathlib import Path
import re,gzip,unittest
ROOT=Path(__file__).resolve().parents[2]
JOB_ENV_ALLOWED={'github','needs','strategy','matrix','vars','secrets','inputs'}
def contexts(text):
 env=text.split('    env:\n',1)[1].split('    steps:\n',1)[0]
 return {m.group(1)for m in re.finditer(r'\$\{\{\s*([A-Za-z_][A-Za-z0-9_]*)[.\[]',env)},env
class Tests(unittest.TestCase):
 def test_actual_first_failed_workflow_rejects_runner_context_in_job_env(self):
  text=gzip.decompress((ROOT/'verification/formal-harness-fix/reproduction/original-full-capture-cost.yml.gz').read_bytes()).decode();used,_=contexts(text);self.assertEqual(used-JOB_ENV_ALLOWED,{'runner'})
 def test_current_job_env_only_uses_allowed_contexts(self):
  used,env=contexts((ROOT/'.github/workflows/full-capture-cost.yml').read_text(encoding='utf8'));self.assertFalse(used-JOB_ENV_ALLOWED);self.assertNotIn('MTW_PG_CONNECTION_FILE:',env);self.assertNotIn('MTW_JOURNAL_TEST_ROOT:',env)
 def test_scratch_paths_are_configured_by_shell_in_first_step(self):
  text=(ROOT/'.github/workflows/full-capture-cost.yml').read_text(encoding='utf8');steps=text.split('    steps:\n',1)[1];first=steps.split('      - ',2)[1];self.assertIn('Configure runner-local scratch paths',first);self.assertIn('MTW_PG_CONNECTION_FILE=$RUNNER_TEMP/mtw-cost-connection.json',first);self.assertIn('MTW_JOURNAL_TEST_ROOT=$RUNNER_TEMP/mtw-cost-units',first);self.assertEqual(first.count('>> "$GITHUB_ENV"'),2)
 def test_validator_also_rejects_step_only_contexts(self):
  used,_=contexts('    env:\n      X: ${{ steps.fake.outputs.value }}\n    steps:\n');self.assertEqual(used-JOB_ENV_ALLOWED,{'steps'})
if __name__=='__main__':unittest.main(verbosity=2)
