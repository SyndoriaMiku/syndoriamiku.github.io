"""Behavior of the editor's paragraph-to-chapter split.

editor.py imports tkinter, so these tests skip on a machine where it is
not available (for example a headless CI image without python3-tk).

Run from the repository root:

    python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import editor
    _EDITOR_IMPORT_ERROR = None
except Exception as error:  # pragma: no cover - depends on the host
    editor = None
    _EDITOR_IMPORT_ERROR = error


@unittest.skipIf(editor is None, f"editor import unavailable: {_EDITOR_IMPORT_ERROR}")
class DetectChaptersTest(unittest.TestCase):
    """detect_chapters(text, regex) -> [{"title", "paragraphs"}]."""

    def detect(self, text, regex):
        return editor.ChapterEditorApp.detect_chapters(None, text, regex)

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
        groups = editor.store.split_into_chapters(paragraphs, r"^chương\s+\d+")
        self.assertEqual(
            self.detect(text, r"^chương\s+\d+"),
            [{"title": g["title"], "paragraphs": g["items"]} for g in groups])


if __name__ == "__main__":
    unittest.main()
