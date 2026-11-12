"""Snap NER spans to a name dictionary so phrases are whole (moxhi-style).

Run from the repository root:

    python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gpu_name_scanner as scanner


class SnapSpansTest(unittest.TestCase):

    def test_dictionary_adds_a_name_ner_missed(self):
        self.assertEqual(scanner.snap_spans("慕容雪", {"慕容雪": "PER"}, set()),
                         {(0, 3, "PER")})

    def test_fragment_inside_a_dictionary_name_is_dropped(self):
        result = scanner.snap_spans("慕容雪说道", {"慕容雪": "PER"}, {(0, 2, "PER")})
        self.assertEqual(result, {(0, 3, "PER")})

    def test_prediction_outside_the_dictionary_survives(self):
        self.assertEqual(scanner.snap_spans("上官雪", {"慕容雪": "PER"}, {(0, 3, "PER")}),
                         {(0, 3, "PER")})

    def test_longest_dictionary_match_wins(self):
        result = scanner.snap_spans("上官婉兮", {"上官": "PER", "上官婉兮": "PER"}, set())
        self.assertEqual(result, {(0, 4, "PER")})

    def test_every_occurrence_is_added(self):
        result = scanner.snap_spans("慕容雪和慕容雪", {"慕容雪": "PER"}, set())
        self.assertEqual(result, {(0, 3, "PER"), (4, 7, "PER")})

    def test_dictionary_types_are_kept(self):
        result = scanner.snap_spans("青云宗", {"青云宗": "ORG"}, set())
        self.assertEqual(result, {(0, 3, "ORG")})

    def test_longer_prediction_beats_a_dictionary_fragment(self):
        # A 1-char dictionary entry must not shatter a longer real name.
        self.assertEqual(scanner.snap_spans("洛娴韵", {"洛": "PER"}, {(0, 3, "PER")}),
                         {(0, 3, "PER")})

    def test_empty_dictionary_returns_predictions(self):
        self.assertEqual(scanner.snap_spans("慕容雪", {}, {(0, 3, "PER")}), {(0, 3, "PER")})


if __name__ == "__main__":
    unittest.main()
