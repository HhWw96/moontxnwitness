"""Synthetic reducer contracts only: no HTTP, subprocess or database."""
import copy,tempfile,unittest
from pathlib import Path
from protocol import workload,SEEDS
from reducer import reduce_case

class ReducerTests(unittest.TestCase):
    def run_case(self,oracle,*,keys=4,limit=100):
        with tempfile.TemporaryDirectory(prefix='mtw-http-reducer-pure-') as tmp:
            original=workload(SEEDS[0]);case=workload(SEEDS[0],original['keys'][:keys])
            self.before=copy.deepcopy(case);calls=[]
            def evaluate(candidate,out):
                calls.append(copy.deepcopy(candidate));return {'result':oracle(candidate)}
            report=reduce_case(case,Path(tmp)/'result',evaluate,max_checks=limit,min_free_bytes=0)
            self.assertEqual(case,self.before)
            self.assertLessEqual(report['candidateChecks'],limit)
            self.assertEqual(report['oracleCallsAttempted'],len(calls))
            self.assertEqual(len(calls),report['candidateChecks']*3)
            for c in calls:self.assertEqual(c,workload(c['seed'],c['keys'],c['workers']))
            return report,calls
    def verdict(self,value):
        return {'executionComplete':True,'faultPredicate':value,'predicateDisposition':'reproduced' if value else 'not-reproduced'}
    def test_reduces_only_original_keys_and_requests_and_completes_minimality(self):
        original=workload(SEEDS[0]);required=set(original['keys'][:2])
        r,calls=self.run_case(lambda c:self.verdict(required.issubset(c['keys']) and len(c['workers'])==2))
        self.assertTrue(r['oneMinimal']);self.assertEqual((r['finalKeys'],r['finalRequests']),(2,2));self.assertEqual(r['completeSingleDeletions'],r['requiredSingleDeletions'])
    def test_exact_budget_two_reserves_fresh_final_without_minimality_claim(self):
        r,calls=self.run_case(lambda c:self.verdict(True),limit=2)
        self.assertFalse(r['oneMinimal']);self.assertEqual(r['candidateChecks'],2);self.assertTrue(r['finalVerifiedReproduced']);self.assertEqual(r['status'],'retained-original')
    def test_original_not_reproduced_does_not_shrink_or_claim_final(self):
        r,_=self.run_case(lambda c:self.verdict(False))
        self.assertEqual(r['status'],'original-not-reproduced');self.assertFalse(r['oneMinimal']);self.assertEqual(r['candidateChecks'],1)
    def test_unknown_baseline_never_becomes_reproduction(self):
        r,_=self.run_case(lambda c:{'executionComplete':False,'faultPredicate':False,'predicateDisposition':'unknown'})
        self.assertEqual(r['status'],'original-inconclusive');self.assertFalse(r['finalVerifiedReproduced'])
    def test_incomplete_single_deletion_blocks_one_minimal(self):
        original=workload(SEEDS[0]);count=[0]
        def oracle(c):
            if len(c['keys'])==4 and len(c['workers'])==2:return self.verdict(True)
            return {'executionComplete':False,'faultPredicate':False,'predicateDisposition':'unknown'}
        r,_=self.run_case(oracle);self.assertFalse(r['oneMinimal']);self.assertGreater(r['unknownSingleDeletions'],0);self.assertEqual(r['finalKeys'],4)
    def test_inconsistent_oracle_fields_are_unknown(self):
        r,_=self.run_case(lambda c:{'executionComplete':True,'faultPredicate':True,'predicateDisposition':'unknown'})
        self.assertEqual(r['status'],'original-inconclusive')
    def test_only_three_complete_reproductions_accept_a_candidate(self):
        count=[0]
        def oracle(c):
            count[0]+=1
            return self.verdict(count[0]%3!=0)
        r,_=self.run_case(oracle)
        self.assertEqual(r['status'],'original-not-reproduced')
    def test_invalid_budget_and_fabricated_request_are_rejected(self):
        original=workload(SEEDS[0]);original['requests']['A']['metrics'][0]['value']=999
        with tempfile.TemporaryDirectory() as tmp:
            for n in (True,0,1,257):
                with self.assertRaises(ValueError):reduce_case(workload(SEEDS[0]),Path(tmp)/str(n),lambda *_:None,max_checks=n)
            with self.assertRaises(ValueError):reduce_case(original,Path(tmp)/'changed',lambda *_:None)
    def test_mutating_oracle_cannot_change_source_or_become_reproduced(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=workload(SEEDS[0]);before=copy.deepcopy(case)
            def mutate(candidate,out):
                candidate['keys'].clear();return {'result':self.verdict(True)}
            r=reduce_case(case,Path(tmp)/'result',mutate,min_free_bytes=0)
            self.assertEqual(case,before);self.assertEqual(r['status'],'original-inconclusive')
    def test_exception_is_unknown_and_does_not_leak_exception_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fail(*_):raise RuntimeError('private-connection-token')
            root=Path(tmp)/'result';r=reduce_case(workload(SEEDS[0]),root,fail,min_free_bytes=0)
            self.assertEqual(r['status'],'original-inconclusive');self.assertEqual(r['oracleCallsAttempted'],3)
            self.assertNotIn('private-connection-token',''.join(p.read_text() for p in root.rglob('*.json')))
if __name__=='__main__':unittest.main()
