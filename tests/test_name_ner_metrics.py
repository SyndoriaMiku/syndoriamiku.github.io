"""Entity-level precision/recall/F1 for the fine-tuning evaluation.

Run from the repository root:

    python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.name_ner import metrics


class PrfTest(unittest.TestCase):

    def test_perfect_match(self):
        spans = {(0, 3, "PER"), (5, 8, "LOC")}
        self.assertEqual(metrics.prf(spans, set(spans)),
                         {"tp": 2, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0})

    def test_missing_entity_is_a_false_negative(self):
        result = metrics.prf({(0, 3, "PER")}, set())
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (0, 0, 1))
        self.assertEqual(result["recall"], 0.0)

    def test_extra_entity_is_a_false_positive(self):
        result = metrics.prf(set(), {(0, 3, "PER")})
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (0, 1, 0))
        self.assertEqual(result["precision"], 0.0)

    def test_right_span_wrong_type_counts_as_both(self):
        result = metrics.prf({(0, 3, "PER")}, {(0, 3, "ORG")})
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (0, 1, 1))

    def test_partial_match(self):
        gold = {(0, 3, "PER"), (5, 8, "PER")}
        pred = {(0, 3, "PER")}
        result = metrics.prf(gold, pred)
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 0, 1))
        self.assertEqual(result["precision"], 1.0)
        self.assertEqual(result["recall"], 0.5)
        self.assertAlmostEqual(result["f1"], 2 / 3)

    def test_empty_everything_is_zero(self):
        self.assertEqual(metrics.prf(set(), set()),
                         {"tp": 0, "fp": 0, "fn": 0, "precision": 0.0, "recall": 0.0, "f1": 0.0})


if __name__ == "__main__":
    unittest.main()
