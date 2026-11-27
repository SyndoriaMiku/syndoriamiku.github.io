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


class ConfigTest(unittest.TestCase):
    """Review Lần 8, B11: ghi nguyên tử, không xoá sạch cài đặt khi file hỏng, không mất khoá khi ghi song song."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = core.CONFIG_PATH
        core.CONFIG_PATH = os.path.join(self._tmp.name, "editor_config.json")

    def tearDown(self):
        core.CONFIG_PATH = self._old
        self._tmp.cleanup()

    def test_broken_file_is_kept_aside_not_overwritten(self):
        with open(core.CONFIG_PATH, "w", encoding="utf-8") as fh:
            fh.write('{"qt_builder_main": "abc", hong')
        self.assertEqual(core.load_config(), {})
        core.save_config({"a": 1})
        self.assertEqual(core.load_config(), {"a": 1})
        broken = [n for n in os.listdir(self._tmp.name) if ".broken-" in n]
        self.assertEqual(len(broken), 1)
        with open(os.path.join(self._tmp.name, broken[0]), encoding="utf-8") as fh:
            self.assertIn("qt_builder_main", fh.read())

    def test_concurrent_saves_keep_every_key(self):
        import editor_core
        threads = [threading.Thread(target=(core.save_config if i % 2 else editor_core.save_config),
                                    args=({f"k{i}": i},)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(core.load_config(), {f"k{i}": i for i in range(20)})


    def test_two_processes_keep_every_key(self):
        """Review Lần 9, B14: hai app cùng mở (hai tiến trình) không làm mất cài đặt của nhau."""
        import subprocess
        core.save_config({"base": 1})
        script = ("import sys; sys.path.insert(0, sys.argv[1]); import translator_core as c; "
                  "c.CONFIG_PATH = sys.argv[2]\n"
                  "for i in range(60): c.save_config({sys.argv[3] + str(i): i})")
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        procs = [subprocess.Popen([sys.executable, "-c", script, root, core.CONFIG_PATH, tag],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT) for tag in ("a", "b")]
        outputs = [proc.communicate(timeout=120)[0].decode("utf-8", "replace") for proc in procs]
        config = core.load_config()
        self.assertEqual(len(config), 121, outputs)
        self.assertNotIn("Không lưu được", "".join(outputs))


class StorySlugTest(unittest.TestCase):
    """Review Lần 8, B13: slug truyện mới tối đa 80 ký tự; truyện đã có giữ slug cũ."""

    def test_long_title_is_cut_with_hash(self):
        title = "Ta " + " ".join(["Trùng Sinh Thành Phản Diện"] * 10)
        slug = core.slugify_vn(title, max_len=80)
        self.assertLessEqual(len(slug), 80)
        self.assertRegex(slug, r"^ta-trung-sinh-.*-[0-9a-f]{6}$")
        self.assertNotEqual(slug, core.slugify_vn(title + " 2", max_len=80))
        self.assertEqual(core.slugify_vn("Hàn Lập", max_len=80), "han-lap")
        for small in (1, 3, 6, 7, 8):   # review Lần 9, B15: không vượt giới hạn khi max_len nhỏ
            self.assertLessEqual(len(core.slugify_vn(title, max_len=small)), 8)

    def test_existing_title_reuses_its_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "list.json")
            long_slug = "a" * 150
            core.store.write_json_atomic(path, [{"title": "Truyện  Dài ", "slug": long_slug}])
            self.assertEqual(core.story_slug("truyện  dài", path), long_slug)
            self.assertEqual(core.story_slug("Truyện mới", path), "truyen-moi")


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
