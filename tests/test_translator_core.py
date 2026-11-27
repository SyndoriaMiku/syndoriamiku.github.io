"""translator_core: phần xử lý dùng chung của builder.py (Tk) và builder_qt.py (Qt)."""
import base64
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import translator_core as core  # noqa: E402


class HelpersTest(unittest.TestCase):
    def test_parse_ranges(self):
        self.assertEqual(core.parse_ranges("41-43, 8; 2-1"), {41, 42, 43, 8, 1, 2})
        self.assertEqual(core.parse_ranges("  "), set())
        with self.assertRaises(ValueError):
            core.parse_ranges("1-3, x")

    def test_counter_text(self):
        self.assertEqual(core.counter_text("\n \n"), "")
        self.assertTrue(core.counter_text("你好\n\n世界").startswith("4 ký tự · 2 đoạn · 1 đợt API"))

    def test_story_data_cleans_spaces_and_encodes(self):
        data = core.story_data("T", ["中"], ["a  b "])
        vi = base64.b64decode(data["content"][0]["vi"]).decode("utf-8")
        self.assertEqual((data["title"], vi), ("T", "a b"))

    def test_read_draft_rejects_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"cn": ["a"], "vi": []}')
            with self.assertRaises(ValueError):
                core.read_draft(path)


class TranslateStoryTest(unittest.TestCase):
    def test_pairs_lines_and_applies_names(self):
        tc = core.TranslatorCore()
        tc.load_name_config = lambda: {"韩立": "Hàn Lập"}
        sent = []

        def fake_api(text):
            sent.append(text)
            return "\n".join("dịch " + line for line in text.split("\n"))
        tc.translate_api = fake_api
        old = core.DELAY
        core.DELAY = 0
        try:
            progress = []
            cn, vi, total = tc.translate_story("韩立来了\n\n他走了", threading.Event(),
                                               on_progress=lambda *a: progress.append(a[:2]))
        finally:
            core.DELAY = old
        self.assertEqual((cn, total, progress), (["韩立来了", "他走了"], 2, [(0, 1)]))
        self.assertEqual(len(vi), 2)
        self.assertNotIn("韩立", sent[0])          # tên được thay trước khi gửi API
        self.assertIn("Hàn Lập", sent[0])

    def test_temp_names_win_and_are_cleared_when_saved(self):
        tc = core.TranslatorCore()
        tc.load_name_config = lambda: {"韩立": "Hàn Lập"}
        tc.merge_temp_names([("韩立", "Hàn Lạp")])
        self.assertEqual(tc.effective_names()["韩立"], "Hàn Lạp")
        with tempfile.TemporaryDirectory() as tmp:
            old = core.name_cfg_path
            core.name_cfg_path = lambda: os.path.join(tmp, "name.cfg")
            try:
                tc.save_names_to_cfg([("韩立", "Hàn Lạp")])
            finally:
                core.name_cfg_path = old
        self.assertEqual(tc.temp_names, {})


if __name__ == "__main__":
    unittest.main()
