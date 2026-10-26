"""Source-buffer cost configuration: pure plans, fake controls, no DB or measurement."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest import mock
import uuid

ROOT=Path(__file__).resolve().parents[2]

def load(name,filename):
    spec=importlib.util.spec_from_file_location(name,ROOT/'experiments/provenance'/filename)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

m=load('buffer_option_cost','full_capture_cost.py')
owned=load('buffer_option_owned_cost','owned_full_capture_cost.py')
BASE=Path(os.environ.get('MTW_JOURNAL_TEST_ROOT',str(ROOT/'artifacts/source-buffer-cost-options/tests')))
RUN=BASE/('cost-buffer-'+uuid.uuid4().hex);RUN.mkdir(parents=True)
BASELINES=json.loads((ROOT/'experiments/provenance/fixtures/full_capture_default_plans.json').read_bytes())


def serialized(value):
    return (json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode('utf8')


class FakeCursor:
    def fetchone(self):return ('PostgreSQL18 fake setup; no database',)
    def fetchall(self):return []
    def executemany(self,*args):return None


class FakeSetup:
    def __init__(self):
        self.info=types.SimpleNamespace(server_version=180000,backend_pid=1)
        self.closed=False
    def execute(self,*args):return FakeCursor()
    def cursor(self):return FakeCursor()
    def close(self):self.closed=True


class Tests(unittest.TestCase):
    def args(self,**changes):
        values=dict(quick=False,profile='column',workload='all',seed=20261023,
                    experimental_budget=None,archive_cells=False,max_cells=None)
        values.update(changes)
        return argparse.Namespace(**values)

    def fresh(self,name):return RUN/(name+'-'+uuid.uuid4().hex)

    def cell(self,mode='C',size=0):
        config=next(c for c in m.plan(self.args())['cells'] if c['mode']==mode)
        if size:config['sourceWriteBufferBytes']=size
        return config

    def measured_cells(self,size=0):
        """Synthetic qualification inputs only; these are not measured receipts."""
        cells=[]
        for batch in range(3):
            for mode in ('A','B','C'):
                config={'workload':'serial','batch':batch,'mode':mode}
                if mode=='C' and size:config['sourceWriteBufferBytes']=size
                cells.append({'configuration':config,'status':'passed','formalProtocolCompleted':True,
                              'endToEndCommittedTps':100,'allAttemptP95Ns':10,'failures':0,
                              'captureBudgetExhausted':False,'protocolFailures':[]})
        return cells

    def test_omitted_and_explicit_zero_preserve_eight_old_plan_byte_hashes(self):
        for baseline in BASELINES['plans']:
            for explicit in (False,True):
                with self.subTest(baseline=baseline['id'],explicitZero=explicit):
                    args=argparse.Namespace(**baseline['args'])
                    if explicit:args.source_write_buffer_bytes=0
                    value=m.plan(args);raw=serialized(value)
                    self.assertEqual(hashlib.sha256(raw).hexdigest(),baseline['serializedPlanSha256'])
                    self.assertEqual(len(raw),baseline['bytes'])
                    self.assertNotIn('sourceWriteBufferBytes',value)
                    self.assertTrue(all('sourceWriteBufferBytes' not in c for c in value['cells']))

    def test_nonzero_plan_changes_only_top_and_twelve_c_fields(self):
        for baseline in BASELINES['plans']:
            for size in (128,65536,262144):
                with self.subTest(baseline=baseline['id'],bufferBytes=size):
                    args=argparse.Namespace(**baseline['args']);args.source_write_buffer_bytes=size
                    value=m.plan(args)
                    self.assertEqual(value.pop('sourceWriteBufferBytes'),size)
                    selected=0
                    for cell in value['cells']:
                        self.assertEqual((cell['warmupSeconds'],cell['durationSeconds'],cell['drainSeconds']),(15,60,30))
                        if cell['mode']=='C':
                            self.assertEqual(cell.pop('sourceWriteBufferBytes'),size);selected+=1
                        else:self.assertNotIn('sourceWriteBufferBytes',cell)
                    self.assertEqual((len(value['cells']),selected),(36,12))
                    self.assertEqual(hashlib.sha256(serialized(value)).hexdigest(),baseline['serializedPlanSha256'])

    def test_invalid_plan_namespace_and_worker_json_fail_before_side_effects(self):
        class IntSubclass(int):pass
        invalid=(False,True,-1,1,127,262145,0.0,None,'65536',IntSubclass(65536))
        for value in invalid:
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValueError):m.plan(self.args(source_write_buffer_bytes=value))
                config=self.cell();config['sourceWriteBufferBytes']=value
                connect=mock.Mock()
                with mock.patch.object(m.shutil,'disk_usage') as disk:
                    with self.assertRaises(ValueError):m.run_cell(config,object(),connect)
                    disk.assert_not_called()
                connect.assert_not_called()
        for mode in ('A','B'):
            with self.subTest(mode=mode):
                connect=mock.Mock()
                with self.assertRaisesRegex(ValueError,'only to C'):m.run_cell(self.cell(mode,65536),object(),connect)
                connect.assert_not_called()

    def test_c_source_factory_receives_selected_buffer_without_other_budget_changes(self):
        for size in (0,128,65536,262144):
            with self.subTest(bufferBytes=size):
                output=self.fresh('fake-c');output.mkdir();setup=FakeSetup()
                connect=mock.Mock(return_value=setup)
                sentinel=RuntimeError('stop after inspecting source factory; before any timed worker')
                with mock.patch.object(m,'Instrumentation') as observer, \
                     mock.patch.object(m,'install',return_value=types.SimpleNamespace(initial={})), \
                     mock.patch.object(m,'GroupedSourceSink',side_effect=sentinel) as sink:
                    result=m.run_cell(self.cell('C',size),output,connect)
                connect.assert_called_once_with(autocommit=True)
                sink.assert_called_once()
                expected={'max_total_bytes':1024**3,'max_records':1000000,'experimental_budget':None}
                if size:expected['write_buffer_bytes']=size
                self.assertEqual(sink.call_args.kwargs,expected)
                self.assertEqual(sink.call_args.args,(output/'sources.jsonl',))
                self.assertNotIn('write_buffer_bytes',observer.call_args.kwargs)
                self.assertEqual(result['status'],'failed')
                self.assertFalse(result['formalProtocolCompleted'])
                self.assertNotIn('warmupStartedAfterConnectionsReady',result)
                self.assertTrue(setup.closed)

    def test_plan_only_64k_declares_option_without_database(self):
        output=self.fresh('plan-only')
        env=dict(os.environ);env.pop('MTW_PG_DSN',None);env.pop('MTW_PG_CONNECTION_FILE',None)
        result=subprocess.run([sys.executable,'-B',m.__file__,'--output',str(output),
            '--plan-only','--source-write-buffer-bytes','65536'],env=env,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
        plan=json.loads((output/'plan.json').read_bytes());receipt=json.loads((output/'receipt.json').read_bytes())
        self.assertEqual(plan['sourceWriteBufferBytes'],65536)
        self.assertEqual(receipt['sourceWriteBufferBytes'],65536)
        self.assertFalse(receipt['actualDatabaseExecution']);self.assertEqual(receipt['status'],'not-executed')

    def test_both_clis_reject_invalid_values_before_creating_output_or_cluster(self):
        for filename in ('full_capture_cost.py','owned_full_capture_cost.py'):
            for value in ('-1','1','127','262145','true','0.0'):
                with self.subTest(filename=filename,value=value):
                    output=self.fresh('invalid-cli')
                    command=[sys.executable,'-B',str(Path(m.__file__).with_name(filename)),
                             '--output',str(output),'--source-write-buffer-bytes',value]
                    if filename.startswith('owned'):command+=['--exclusive-host','--bin',str(RUN/'no-binaries')]
                    else:command+=['--plan-only']
                    result=subprocess.run(command,capture_output=True)
                    self.assertEqual(result.returncode,2,result.stderr.decode(errors='replace'))
                    self.assertFalse(output.exists())

    def test_worker_uses_preregistered_json_as_sole_source_option(self):
        output=self.fresh('worker-json');config=self.cell('C',65536)
        config_path=self.fresh('worker-config');config_path.write_text(json.dumps(config),encoding='utf8')
        connect=mock.Mock()
        fake_driver=types.SimpleNamespace(__version__='3.3.6')
        result={'status':'smoke-passed','actualDatabaseExecution':False,'configuration':config}
        argv=[m.__file__,'--output',str(output),'--worker-config',str(config_path)]
        with mock.patch.object(sys,'argv',argv),mock.patch.dict(sys.modules,{'psycopg':fake_driver}), \
             mock.patch.object(m,'connect_factory',return_value=connect), \
             mock.patch.object(m,'runtime_sources',return_value=[]), \
             mock.patch.object(m,'run_cell',return_value=result) as run:
            self.assertEqual(m.main(),0)
        run.assert_called_once_with(config,output.resolve(),connect)
        self.assertEqual(json.loads((output/'receipt.json').read_bytes())['configuration']['sourceWriteBufferBytes'],65536)
        connect.assert_not_called()

    def test_worker_rejects_nonzero_cli_override_and_invalid_json_before_output(self):
        for override,value in ((65536,65536),(0,True),(0,262145)):
            output=self.fresh('rejected-worker')
            config=self.cell();config['sourceWriteBufferBytes']=value
            config_path=self.fresh('bad-worker-config');config_path.write_text(json.dumps(config),encoding='utf8')
            argv=[m.__file__,'--output',str(output),'--worker-config',str(config_path)]
            if override:argv+=['--source-write-buffer-bytes',str(override)]
            with mock.patch.object(sys,'argv',argv),self.assertRaises(SystemExit) as caught:
                m.main()
            self.assertEqual(caught.exception.code,2);self.assertFalse(output.exists())

    def test_owned_default_command_is_identical_and_nonzero_flag_is_explicit(self):
        args=argparse.Namespace(profile='column',max_cells=3)
        work=RUN/'owned-command'
        expected=[sys.executable,'-B',str(Path(owned.__file__).with_name('full_capture_cost.py')),
                  '--output',str(work/'study'),'--profile','column','--exclusive-host','--exclusive-cluster',
                  '--archive-cells','--max-cells','3']
        self.assertEqual(owned._study_command(args,work),expected)
        args.source_write_buffer_bytes=0;self.assertEqual(owned._study_command(args,work),expected)
        args.source_write_buffer_bytes=65536
        self.assertEqual(owned._study_command(args,work),expected+['--source-write-buffer-bytes','65536'])
        args.source_write_buffer_bytes=True
        with self.assertRaises(ValueError):owned._study_command(args,work)

    def test_comparison_rejects_mixed_invalid_ab_and_duplicate_cells_without_mutation(self):
        for alteration in ('mixed','invalid','A','B','duplicate'):
            with self.subTest(alteration=alteration):
                cells=self.measured_cells(65536)
                if alteration=='mixed':cells[2]['configuration'].pop('sourceWriteBufferBytes')
                elif alteration=='invalid':cells[2]['configuration']['sourceWriteBufferBytes']=True
                elif alteration in ('A','B'):cells[0 if alteration=='A' else 1]['configuration']['sourceWriteBufferBytes']=65536
                else:cells.append(copy.deepcopy(cells[2]))
                before=copy.deepcopy(cells);result=m.compare(cells)['serial']
                self.assertFalse(result['eligibleForTargets'])
                self.assertFalse(result.get('performanceTargetsPassed',False))
                self.assertEqual(cells,before)
        for size in (0,65536,262144):
            result=m.compare(self.measured_cells(size))['serial']
            self.assertTrue(result['eligibleForTargets'])
            if size:self.assertEqual(result['sourceWriteBufferBytes'],size)
            else:self.assertNotIn('sourceWriteBufferBytes',result)

    def _assert_buffered_controller_drift(self,as_float=False,matching=False):
        output=self.fresh('fake-controller');calls=[]
        def fake_child(command,**kwargs):
            config_path=Path(command[command.index('--worker-config')+1])
            config=json.loads(config_path.read_bytes());observed=copy.deepcopy(config)
            if config['mode']=='C' and not matching:
                if as_float:observed['sourceWriteBufferBytes']=float(config['sourceWriteBufferBytes'])
                else:observed.pop('sourceWriteBufferBytes')
            cell_output=Path(command[command.index('--output')+1]);cell_output.mkdir()
            value={'configuration':observed,'status':'passed','formalProtocolCompleted':True,
                   'actualDatabaseExecution':False,'failures':0,'protocolFailures':[],
                   'endToEndCommittedTps':1,'allAttemptP95Ns':1,'captureBudgetExhausted':False}
            (cell_output/'receipt.json').write_text(json.dumps(value),encoding='utf8')
            calls.append(config);return types.SimpleNamespace(returncode=0)
        argv=[m.__file__,'--output',str(output),'--source-write-buffer-bytes','65536',
              '--max-cells','3','--exclusive-host','--exclusive-cluster']
        with mock.patch.object(sys,'argv',argv),mock.patch.object(m.subprocess,'run',side_effect=fake_child), \
             mock.patch.object(m.shutil,'disk_usage',return_value=types.SimpleNamespace(free=10**12)):
            self.assertEqual(m.main(),2 if matching else 1)
        self.assertEqual([c['mode'] for c in calls],['A','B','C'])
        summary=json.loads((output/'receipt.json').read_bytes())
        self.assertEqual(summary['stopReason'],'explicit partial preregistered prefix' if matching else 'preregistered source buffer configuration mismatch')
        self.assertFalse(summary['formalProtocolCompleted']);self.assertFalse(summary['performanceTargetsPassed'])
        self.assertFalse(summary['actualDatabaseExecution'])
        original=json.loads((output/'cell-2/receipt.json').read_bytes())
        if matching:self.assertEqual(original['configuration']['sourceWriteBufferBytes'],65536)
        elif as_float:self.assertIs(type(original['configuration']['sourceWriteBufferBytes']),float)
        else:self.assertNotIn('sourceWriteBufferBytes',original['configuration'])
        self.assertEqual((output/'cell-2-source-buffer-configuration-mismatch.json').is_file(),not matching)

    def test_buffered_controller_rejects_child_configuration_drift_and_retains_receipt(self):
        for as_float in (False,True):
            with self.subTest(numericTypeDrift=as_float):self._assert_buffered_controller_drift(as_float)
        with self.subTest(matchingConfiguration=True):self._assert_buffered_controller_drift(matching=True)

    def test_workflow_preregistration_and_measurement_forward_same_option(self):
        workflow=(ROOT/'.github/workflows/full-capture-cost.yml').read_text(encoding='utf8')
        self.assertIn("default: '0'",workflow);self.assertIn("options: ['0', '65536']",workflow)
        self.assertIn('MTW_COST_SOURCE_BUFFER: ${{ inputs.source_write_buffer_bytes }}',workflow)
        self.assertEqual(workflow.count('buffer_args=(--source-write-buffer-bytes "$MTW_COST_SOURCE_BUFFER")'),2)
        commands=[line for line in workflow.splitlines() if 'python -B experiments/provenance/full_capture_cost.py ' in line]
        self.assertEqual(len(commands),2)
        self.assertTrue(all('"${buffer_args[@]}"' in line for line in commands))
        self.assertIn('--plan-only',commands[0]);self.assertNotIn('--plan-only',commands[1])
        self.assertIn('before.read_bytes()==after.read_bytes()',workflow)
        self.assertIn('timeout-minutes: 180',workflow)


if __name__=='__main__':unittest.main(verbosity=2)
