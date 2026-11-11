"""Candidate filtering / span resolving for Scan Names (recall-first pass).

These are the pure parts of gpu_name_scanner: no torch, no model needed.

Run from the repository root:

    python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gpu_name_scanner as scanner


class NameShapeTest(unittest.TestCase):

    def test_keeps_two_to_forty_cjk(self):
        self.assertTrue(scanner.is_name_shape("王宏伟"))
        self.assertTrue(scanner.is_name_shape("洛·萨"))

    def test_keeps_mixed_names(self):
        self.assertTrue(scanner.is_name_shape("阿Q"))
        self.assertTrue(scanner.is_name_shape("张3"))
        self.assertTrue(scanner.is_name_shape("李A·b"))

    def test_keeps_single_cjk(self):
        self.assertTrue(scanner.is_name_shape("赵"))

    def test_rejects_non_names(self):
        for value in ("", "  ", "abc", "12", "王 宏", "王，宏", "a" * 41):
            with self.subTest(value=value):
                self.assertFalse(scanner.is_name_shape(value))


class KeepCandidateTest(unittest.TestCase):

    def test_borderline_multi_char_is_kept(self):
        # 0.6 used to be thrown away by the old 0.80 cut.
        self.assertTrue(scanner.keep_candidate("慕容雪", 0.60))

    def test_very_low_score_is_dropped(self):
        self.assertFalse(scanner.keep_candidate("慕容雪", 0.30))

    def test_single_char_needs_high_confidence(self):
        self.assertTrue(scanner.keep_candidate("赵", 0.95))
        self.assertFalse(scanner.keep_candidate("赵", 0.70))

    def test_bad_shape_is_dropped_whatever_the_score(self):
        self.assertFalse(scanner.keep_candidate("abc", 0.99))


class SavedSpansTest(unittest.TestCase):

    def test_finds_every_occurrence_of_saved_names(self):
        text = "王宏伟走进来，王宏伟笑了。"
        self.assertEqual(scanner.saved_spans(text, {"王宏伟"}), [(0, 3), (7, 10)])

    def test_no_saved_names_is_empty(self):
        self.assertEqual(scanner.saved_spans("王宏伟", set()), [])


class ResolveSpansTest(unittest.TestCase):

    def test_overlapping_different_kinds_are_both_kept(self):
        text = "青云宗"
        found = {(0, 2, "ORG"): 0.9, (1, 3, "PER"): 0.85}
        self.assertEqual(
            scanner.resolve_spans(found, text),
            [(0, 2, "ORG", 0.9), (1, 3, "PER", 0.85)])

    def test_same_kind_prefers_the_longer_span(self):
        text = "王宏伟"
        found = {(0, 2, "PER"): 0.95, (0, 3, "PER"): 0.85}
        self.assertEqual(scanner.resolve_spans(found, text), [(0, 3, "PER", 0.85)])

    def test_occurrence_inside_a_saved_name_is_dropped(self):
        text = "王宏伟"
        found = {(0, 2, "PER"): 0.95}
        self.assertEqual(
            scanner.resolve_spans(found, text, saved=scanner.saved_spans(text, {"王宏伟"})), [])

    def test_same_fragment_outside_the_saved_name_survives(self):
        text = "王宏来了，王宏伟也来了。"
        found = {(0, 2, "PER"): 0.9, (5, 7, "PER"): 0.8}
        result = scanner.resolve_spans(found, text, saved=scanner.saved_spans(text, {"王宏伟"}))
        self.assertIn((0, 2, "PER", 0.9), result)
        self.assertNotIn((5, 7, "PER", 0.8), result)

    def test_a_middle_dot_joins_two_same_kind_spans(self):
        text = "阿·明"
        found = {(0, 1, "PER"): 0.9, (2, 3, "PER"): 0.9}
        self.assertEqual(scanner.resolve_spans(found, text), [(0, 3, "PER", 0.9)])

    def test_unrelated_spans_are_all_kept(self):
        text = "王宏伟和李云"
        found = {(0, 3, "PER"): 0.9, (4, 6, "PER"): 0.8}
        self.assertEqual(len(scanner.resolve_spans(found, text)), 2)


if __name__ == "__main__":
    unittest.main()
