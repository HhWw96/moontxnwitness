"""Pure helper checks for the cost protocol; no database or measurements."""
import json
import unittest

from cost_study import batch_orders, canonical_hash, nearest_rank, oracle, summarize, workloads


class CostProtocolTests(unittest.TestCase):
    def test_generator_is_frozen_by_seed_and_full_operations(self):
        first = workloads(20261020, 40, 8)
        self.assertEqual(first, workloads(20261020, 40, 8))
        self.assertNotEqual(first, workloads(20261021, 40, 8))
        self.assertEqual(len(first), 40)
        self.assertEqual(canonical_hash(first), canonical_hash(json.loads(json.dumps(first))))

    def test_rotation_balances_each_candidate_position(self):
        orders = batch_orders()
        self.assertEqual(len(orders), 3)
        for index in range(3):
            self.assertEqual({order[index] for order in orders}, {"plain", "column", "sidecar"})

    def test_oracle_preserves_unmodified_rows_and_total_delta(self):
        initial = {"key-0": 10, "key-1": 20, "key-2": 30}
        operations = [{"read": "key-0", "delta": 3}, {"read": "key-1", "delta": -1},
                      {"read": "key-0", "delta": -3}]
        final = oracle(operations, initial)
        self.assertEqual(final, {"key-0": 10, "key-1": 19, "key-2": 30})
        self.assertEqual(initial, {"key-0": 10, "key-1": 20, "key-2": 30})

    def test_p95_nearest_rank_definition(self):
        self.assertEqual(nearest_rank(list(range(1, 21)), 0.95), 19)
        self.assertEqual(nearest_rank([7], 0.95), 7)
        with self.assertRaises(ValueError):
            nearest_rank([], 0.95)

    def test_regressions_are_retained_and_no_mode_can_be_omitted(self):
        samples = []
        for batch in range(3):
            for mode, factor in (("plain", 1), ("column", 2), ("sidecar", 4)):
                samples.append({"batch": batch, "mode": mode, "status": "passed", "transactions": 2,
                                "measurementWallNs": 100 * factor, "transactionLatencyNs": [10 * factor, 20 * factor],
                                "tps": 20_000_000 / factor, "p50TxnNs": 15 * factor, "p95TxnNs": 20 * factor,
                                "walLsnDeltaBytes": 100 * factor})
        before = json.dumps(samples, sort_keys=True)
        summary = summarize(samples)
        self.assertEqual(set(summary["modes"]), {"plain", "column", "sidecar"})
        self.assertAlmostEqual(summary["candidateOverPlain"]["column"]["tpsRatioGeomean"], 0.5)
        self.assertAlmostEqual(summary["candidateOverPlain"]["sidecar"]["p95RatioGeomean"], 4)
        self.assertEqual(json.dumps(samples, sort_keys=True), before)
        with self.assertRaises(ValueError):
            summarize(samples[:-1])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CostProtocolTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"suite": "provenance-cost-protocol-unit", "tests": result.testsRun,
                      "passed": result.wasSuccessful(), "actualDatabaseExecution": False,
                      "performanceStudyExecuted": False}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
