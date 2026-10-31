"""Actual three-profile binding schemas, with synthetic transport regressions."""
import copy, json, unittest
from pathlib import Path
import import_postgres_ci_bundle as pg
from test_postgres_ci_import import encode, REPO
import test_postgres_ci_reproduction as reproduction
from test_postgres_ci_reproduction import full_fixture

ROOT=Path(__file__).resolve().parents[1]
PREFIX='verification/provenance-presence/ci-123-2/'
ACTUAL_PROFILES=['crud-absence-reinsert-rollback','negative-point-write-skew','read-committed-delete-source']
EXTRAS=['tamperChecks','reduction','protocol']

def producer_shaped_fixture():
    expected,run,payload=full_fixture();receipt=pg.json_bytes(payload[PREFIX+'presence-receipt.json'])
    for index,scenario in enumerate(receipt['scenarios']):
        old_name=scenario['name'];name=ACTUAL_PROFILES[index];scenario['name']=name;bindings=scenario['artifactBindings']
        for kind,row in list(bindings.items()):
            raw=payload.pop(PREFIX+row['path'])
            if kind=='tamperChecks' and EXTRAS[index]!=kind:
                del bindings[kind];continue
            row['path']=row['path'].replace(old_name,name);payload[PREFIX+row['path']]=raw
        scenario['trace']=bindings['trace']['path']
        if EXTRAS[index] not in bindings:
            leaf=name+'.'+EXTRAS[index]+'.json';raw=encode({'syntheticScenarioSpecificEvidence':EXTRAS[index]})
            bindings[EXTRAS[index]]={'path':leaf,'bytes':len(raw),'sha256':pg.digest(raw)};payload[PREFIX+leaf]=raw
    for name in ['gap-unread','gap-unknown','gap-zero']:
        bindings={}
        for kind in ['trace','coverage','audit']:
            leaf=name+'.'+kind+'.json';raw=encode({'syntheticInconclusive':kind});payload[PREFIX+leaf]=raw;bindings[kind]={'path':leaf,'bytes':len(raw),'sha256':pg.digest(raw)}
        receipt['scenarios'].append({'name':name,'trace':bindings['trace']['path'],'expectedStatus':'inconclusive','artifactBindings':bindings})
    payload[PREFIX+'presence-receipt.json']=encode(receipt)
    return expected,run,payload

class ActualPresenceSchema(unittest.TestCase):
    setUp=reproduction.ReproductionBoundaries.setUp
    tearDown=reproduction.ReproductionBoundaries.tearDown
    archive=reproduction.ReproductionBoundaries.archive
    def validate(self,payload=None):
        expected,run,original=producer_shaped_fixture();self.run=run
        path,artifact=self.archive(original if payload is None else payload)
        return pg.validate_archive(path,run,artifact,expected,REPO,reproduction=True)
    def test_actual_three_extra_roles_share_exactly_six_core_roles(self):
        files,_=self.validate();receipt=pg.json_bytes(files[PREFIX+'presence-receipt.json'])
        for scenario,extra in zip(receipt['scenarios'],EXTRAS):self.assertEqual(set(scenario['artifactBindings']),{'trace','coverage','audit','history','report','capsule',extra})
    def test_each_actual_scenario_requires_its_own_extra(self):
        for index,extra in enumerate(EXTRAS):
            _,_,payload=producer_shaped_fixture();receipt=pg.json_bytes(payload[PREFIX+'presence-receipt.json']);del receipt['scenarios'][index]['artifactBindings'][extra];payload[PREFIX+'presence-receipt.json']=encode(receipt)
            with self.subTest(extra=extra),self.assertRaises(pg.ImportFailure):self.validate(payload)
    def test_each_actual_scenario_requires_all_six_core_bindings(self):
        for index in range(3):
            for role in ['trace','coverage','audit','history','report','capsule']:
                _,_,payload=producer_shaped_fixture();receipt=pg.json_bytes(payload[PREFIX+'presence-receipt.json']);del receipt['scenarios'][index]['artifactBindings'][role];payload[PREFIX+'presence-receipt.json']=encode(receipt)
                with self.subTest(index=index,role=role),self.assertRaises(pg.ImportFailure):self.validate(payload)
    def test_all_scenario_specific_extra_hashes_are_required(self):
        for index,extra in enumerate(EXTRAS):
            _,_,payload=producer_shaped_fixture();receipt=pg.json_bytes(payload[PREFIX+'presence-receipt.json']);leaf=receipt['scenarios'][index]['artifactBindings'][extra]['path'];payload[PREFIX+leaf]=b'altered actual extra'
            with self.subTest(extra=extra),self.assertRaises(pg.ImportFailure):self.validate(payload)
    def test_unknown_binding_role_is_rejected_even_with_valid_file_hash(self):
        _,_,payload=producer_shaped_fixture();receipt=pg.json_bytes(payload[PREFIX+'presence-receipt.json']);raw=b'{}';payload[PREFIX+'unrecognized.json']=raw
        receipt['scenarios'][0]['artifactBindings']['unknownRole']={'path':'unrecognized.json','bytes':len(raw),'sha256':pg.digest(raw)};payload[PREFIX+'presence-receipt.json']=encode(receipt)
        with self.assertRaises(pg.ImportFailure):self.validate(payload)
    def test_all_inconclusive_declared_bindings_are_checked(self):
        for index in range(3,6):
            for role in ['trace','coverage','audit']:
                _,_,payload=producer_shaped_fixture();receipt=pg.json_bytes(payload[PREFIX+'presence-receipt.json']);payload[PREFIX+receipt['scenarios'][index]['artifactBindings'][role]['path']]=b'changed inconclusive original'
                with self.subTest(index=index,role=role),self.assertRaises(pg.ImportFailure):self.validate(payload)
    def test_inconclusive_binding_cannot_sneak_unknown_role_or_path(self):
        for role,path in [('unknownRole','gap-zero.audit.json'),('audit','../secret.json')]:
            _,_,payload=producer_shaped_fixture();receipt=pg.json_bytes(payload[PREFIX+'presence-receipt.json']);row=copy.deepcopy(receipt['scenarios'][5]['artifactBindings']['audit']);row['path']=path;receipt['scenarios'][5]['artifactBindings'][role]=row;payload[PREFIX+'presence-receipt.json']=encode(receipt)
            with self.subTest(role=role),self.assertRaises(pg.ImportFailure):self.validate(payload)
    def test_small_actual_metadata_records_exact_original_producer_shape(self):
        evidence=json.loads((ROOT/'fixtures/postgres-ci-import/presence-bindings-7bd-original.json').read_text('utf8'))
        self.assertEqual(evidence['archive']['sha256'],'682092fc698426b885a479086f764f986c8df328cc2a6412a4416abd912c3acc')
        self.assertEqual(evidence['archive']['artifactId'],13038525278);self.assertEqual(evidence['archive']['sourceCommit'],'7bd09da7f640e925c8e079e9f7f373ddbf72adaf')
        self.assertEqual([r['name'] for r in evidence['scenarios'][:3]],ACTUAL_PROFILES)
        for row,extra in zip(evidence['scenarios'][:3],EXTRAS):self.assertEqual(set(row['artifactBindings']),{'trace','coverage','audit','history','report','capsule',extra})
        for row in evidence['scenarios'][3:]:self.assertEqual(set(row['artifactBindings']),{'trace','coverage','audit'})

if __name__=='__main__':unittest.main()
