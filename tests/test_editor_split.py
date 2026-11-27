"""Behavior of the editor's paragraph-to-chapter split.

The split lives in editor_core (no GUI), so these tests run everywhere.

Run from the repository root:

    python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import editor_core  # noqa: E402


class DetectChaptersTest(unittest.TestCase):
    """detect_chapters(text, regex) -> [{"title", "paragraphs"}]."""

    def detect(self, text, regex):
        return editor_core.detect_chapters(text, regex)

    def test_leading_paragraphs_become_a_titleless_group(self):
        result = self.detect("Mở đầu\n\nChương 1\n\nĐoạn 1", r"^chương\s+\d+")
        self.assertEqual(result, [
            {"title": "", "paragraphs": ["Mở đầu"]},
            {"title": "Chương 1", "paragraphs": ["Đoạn 1"]},
        ])

    def test_consecutive_headers_keep_an_empty_chapter(self):
        result = self.detect("Chương 1\n\nChương 2\n\nĐoạn", r"^chương\s+\d+")
        self.assertEqual(result, [
            {"title": "Chương 1", "paragraphs": []},
            {"title": "Chương 2", "paragraphs": ["Đoạn"]},
        ])

    def test_no_header_gives_one_titleless_group(self):
        result = self.detect("a\n\nb", r"^chương\s+\d+")
        self.assertEqual(result, [{"title": "", "paragraphs": ["a", "b"]}])

    def test_headers_match_case_insensitively(self):
        result = self.detect("CHƯƠNG 3\n\nx", r"^chương\s+\d+")
        self.assertEqual(result, [{"title": "CHƯƠNG 3", "paragraphs": ["x"]}])

    def test_invalid_regex_returns_empty_list(self):
        self.assertEqual(self.detect("Chương 1\n\nx", r"("), [])

    def test_matches_library_store_grouping(self):
        text = "dẫn\n\nChương 1\n\nA\n\nChương 2\n\nB"
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        groups = editor_core.store.split_into_chapters(paragraphs, r"^chương\s+\d+")
        self.assertEqual(
            self.detect(text, r"^chương\s+\d+"),
            [{"title": g["title"], "paragraphs": g["items"]} for g in groups])


if __name__ == "__main__":
    unittest.main()
