"""Aggregate/select logic for mining a name dictionary from NER output.

Run from the repository root:

    python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.name_ner import mine


class AggregateTest(unittest.TestCase):

    def test_counts_occurrences_and_keeps_the_best_confidence(self):
        result = mine.aggregate([("慕容雪", "PERSON", 0.9), ("慕容雪", "PERSON", 0.8),
                                 ("慕容雪", "PERSON", 0.95)])
        self.assertEqual(result["慕容雪"], {"count": 3, "confidence": 0.95, "type": "PER"})

    def test_scanner_types_are_mapped(self):
        result = mine.aggregate([("青云宗", "ORG", 0.9), ("北京", "PLACE", 0.9)])
        self.assertEqual(result["青云宗"]["type"], "ORG")
        self.assertEqual(result["北京"]["type"], "LOC")

    def test_blank_names_are_skipped(self):
        self.assertEqual(mine.aggregate([("", "PERSON", 0.9), ("  ", "PERSON", 0.9)]), {})


class SelectTest(unittest.TestCase):

    def setUp(self):
        self.entries = mine.aggregate([
            ("慕容雪", "PERSON", 0.95), ("慕容雪", "PERSON", 0.9), ("慕容雪", "PERSON", 0.9),
            ("上官婉兮", "PERSON", 0.99), ("上官婉兮", "PERSON", 0.99), ("上官婉兮", "PERSON", 0.99),
            ("偶尔", "PERSON", 0.95), ("偶尔", "PERSON", 0.9), ("偶尔", "PERSON", 0.9),
            ("abc", "PERSON", 0.99), ("abc", "PERSON", 0.99), ("abc", "PERSON", 0.99),
        ])

    def test_min_count_and_min_confidence(self):
        result = mine.select(self.entries, known=set(), min_count=3, min_confidence=0.9)
        self.assertEqual(result, {"慕容雪": "PER", "上官婉兮": "PER"})

    def test_known_names_and_bad_shapes_are_dropped(self):
        result = mine.select(self.entries, known={"慕容雪"}, min_count=3, min_confidence=0.9)
        self.assertNotIn("慕容雪", result)
        self.assertNotIn("abc", result)

    def test_high_threshold_keeps_the_strongest_only(self):
        entries = mine.aggregate([("王小明", "PERSON", 0.95)] * 5 + [("李小强", "PERSON", 0.7)] * 5)
        self.assertEqual(mine.select(entries, min_count=3, min_confidence=0.9), {"王小明": "PER"})

    def test_single_character_and_two_character_entries_are_dropped(self):
        entries = mine.aggregate([("洛", "PERSON", 0.99)] * 5 + [("阳光", "PERSON", 0.99)] * 5
                                 + [("于是", "PERSON", 0.99)] * 5)
        self.assertEqual(mine.select(entries, min_count=3, min_confidence=0.9), {})


if __name__ == "__main__":
    unittest.main()
