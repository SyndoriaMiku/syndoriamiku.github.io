"""Corpus reader and story-disjoint split for name-NER fine-tuning.

Run from the repository root:

    python -m unittest discover -s tests
"""
import base64
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.name_ner import corpus


def write_chapter(path, paragraphs):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"content": [{"cn": base64.b64encode(cn.encode("utf-8")).decode("ascii"),
                            "vi": base64.b64encode(vi.encode("utf-8")).decode("ascii")}
                           for cn, vi in paragraphs]}
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False)


class IterChaptersTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.library = os.path.join(self.root, "library")
        self.stories = os.path.join(self.root, "stories")

    def tearDown(self):
        self._tmp.cleanup()

    def test_reads_library_chapters_and_joins_paragraphs(self):
        write_chapter(os.path.join(self.library, "000001", "0001", "data.json"),
                      [("你好", "Xin chào"), ("世界", "thế giới")])
        chapters = corpus.iter_chapters(self.library, self.stories)
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0].story, "000001")
        self.assertEqual(chapters[0].slug, "0001")
        self.assertEqual(chapters[0].cn, "你好\n世界")

    def test_reads_short_stories(self):
        write_chapter(os.path.join(self.stories, "truyen-a", "data.json"), [("测试", "thử")])
        chapters = corpus.iter_chapters(self.library, self.stories)
        self.assertEqual([(c.story, c.slug) for c in chapters], [("truyen-a", "")])

    def test_skips_empty_cn_and_broken_files(self):
        write_chapter(os.path.join(self.library, "000002", "0001", "data.json"), [("", ""), ("好", "tốt")])
        os.makedirs(os.path.join(self.stories, "bad"), exist_ok=True)
        with open(os.path.join(self.stories, "bad", "data.json"), "w", encoding="utf-8") as stream:
            stream.write("{ not json")
        chapters = corpus.iter_chapters(self.library, self.stories)
        self.assertEqual([c.cn for c in chapters], ["好"])

    def test_dedupe_keeps_the_first_copy(self):
        write_chapter(os.path.join(self.library, "000001", "0001", "data.json"), [("重复", "x")])
        write_chapter(os.path.join(self.stories, "other", "data.json"), [("重复", "y")])
        chapters = corpus.dedupe(corpus.iter_chapters(self.library, self.stories))
        self.assertEqual([(c.story, c.slug) for c in chapters], [("000001", "0001")])

    def test_dedupe_keeps_distinct_chapters(self):
        write_chapter(os.path.join(self.library, "000001", "0001", "data.json"), [("一", "x")])
        write_chapter(os.path.join(self.library, "000001", "0002", "data.json"), [("二", "y")])
        self.assertEqual(len(corpus.dedupe(corpus.iter_chapters(self.library, self.stories))), 2)


class SplitStoriesTest(unittest.TestCase):

    def test_is_disjoint_and_covers_every_story(self):
        ids = [f"{n:06d}" for n in range(20)]
        split = corpus.split_stories(ids)
        everything = split["train"] + split["val"] + split["test"]
        self.assertEqual(sorted(everything), ids)
        self.assertEqual(len(set(everything)), len(ids))

    def test_is_deterministic_for_a_seed(self):
        ids = [f"{n:06d}" for n in range(20)]
        self.assertEqual(corpus.split_stories(ids, seed=7), corpus.split_stories(ids, seed=7))

    def test_respects_the_ratio(self):
        ids = [f"{n:06d}" for n in range(20)]
        split = corpus.split_stories(ids, ratios=(0.8, 0.1, 0.1), seed=1)
        self.assertEqual((len(split["train"]), len(split["val"]), len(split["test"])), (16, 2, 2))

    def test_empty_input(self):
        self.assertEqual(corpus.split_stories([]), {"train": [], "val": [], "test": []})


if __name__ == "__main__":
    unittest.main()
