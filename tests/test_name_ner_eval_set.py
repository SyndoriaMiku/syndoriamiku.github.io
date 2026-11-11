"""Held-out name evaluation set: name split and gold spans.

Run from the repository root:

    python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.name_ner import corpus, eval_set


class SplitNamesTest(unittest.TestCase):

    def make_types(self, count):
        return {f"名{n:03d}": "PER" for n in range(count)}

    def test_train_and_eval_names_are_disjoint_and_complete(self):
        types = self.make_types(100)
        train, evaluation = eval_set.split_names(types, holdout=0.1, seed=3)
        self.assertEqual(set(train) & set(evaluation), set())
        self.assertEqual(set(train) | set(evaluation), set(types))

    def test_eval_ratio_and_determinism(self):
        types = self.make_types(100)
        first = eval_set.split_names(types, holdout=0.1, seed=3)
        second = eval_set.split_names(types, holdout=0.1, seed=3)
        self.assertEqual(first, second)
        self.assertEqual(len(first[1]), 10)

    def test_ignored_names_never_land_in_eval(self):
        types = {"甲": "PER", "乙": "IGNORE", "丙": "PER"}
        _train, evaluation = eval_set.split_names(types, holdout=0.5, seed=0)
        self.assertNotIn("乙", evaluation)

    def test_zero_holdout_leaves_eval_empty(self):
        _train, evaluation = eval_set.split_names(self.make_types(10), holdout=0.0)
        self.assertEqual(evaluation, {})


class GoldSpansTest(unittest.TestCase):

    def chapter(self, cn, story="000001", slug="0001"):
        return corpus.Chapter(story, slug, "path", cn)

    def test_offsets_are_relative_to_each_chapter(self):
        gold = eval_set.gold_spans([self.chapter("你好慕容雪")], {"慕容雪": "PER"})
        self.assertEqual(gold, {("000001", "0001", 2, 5, "PER")})

    def test_unknown_names_produce_no_gold(self):
        self.assertEqual(eval_set.gold_spans([self.chapter("你好")], {"慕容雪": "PER"}), set())

    def test_longest_match_and_multiple_chapters(self):
        chapters = [self.chapter("上官婉兮"), self.chapter("上官雪", story="000002", slug="0001")]
        gold = eval_set.gold_spans(chapters, {"上官": "PER", "上官婉兮": "PER", "上官雪": "PER"})
        self.assertEqual(gold, {("000001", "0001", 0, 4, "PER"), ("000002", "0001", 0, 3, "PER")})


if __name__ == "__main__":
    unittest.main()
