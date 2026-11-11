"""Name types from name.cfg and the weak BIO span pass.

Run from the repository root:

    python -m unittest discover -s tests
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.name_ner import labels


class LoadNameTypesTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "name.cfg")

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, text):
        with open(self.path, "w", encoding="utf-8") as stream:
            stream.write(text)

    def test_plain_name_is_a_person(self):
        self.write("某某=Tên\n林峰=Lâm Phong\n秦镇海=Tần Trấn Hải\n")
        self.assertEqual(labels.load_name_types(self.path),
                         {"某某": "PER", "林峰": "PER", "秦镇海": "PER"})

    def test_sect_suffix_with_matching_gloss_is_an_org(self):
        self.write("青云宗=Thanh Vân Tông\n")
        self.assertEqual(labels.load_name_types(self.path), {"青云宗": "ORG"})

    def test_place_suffix_with_matching_gloss_is_a_place(self):
        self.write("无名岛=Vô Danh Đảo\n")
        self.assertEqual(labels.load_name_types(self.path), {"无名岛": "LOC"})

    def test_given_name_chars_that_look_like_suffixes_stay_person(self):
        # 国/渊/城/堂/山/河 end plenty of real person names; the suffix must not win.
        self.write("林建国=Lâm Kiến Quốc\n陆渊=Lục Uyên\n顾城=Cố Thành\n"
                   "沈玉堂=Thẩm Ngọc Đường\n赵长河=Triệu Trường Hà\n苏青山=Tô Thanh Sơn\n")
        self.assertEqual(labels.load_name_types(self.path),
                         {"林建国": "PER", "陆渊": "PER", "顾城": "PER",
                          "沈玉堂": "PER", "赵长河": "PER", "苏青山": "PER"})

    def test_skill_suffix_with_matching_gloss_is_ignored(self):
        self.write("烈焰诀=Liệt Diễm Quyết\n")
        self.assertEqual(labels.load_name_types(self.path), {"烈焰诀": "IGNORE"})

    def test_suffix_without_matching_gloss_stays_a_person(self):
        self.write("青云宗=\n白云城=Không rõ\n")
        self.assertEqual(labels.load_name_types(self.path), {"青云宗": "PER", "白云城": "PER"})

    def test_comments_blank_and_invalid_lines_are_skipped(self):
        self.write("# ghi chú\n\nbadline\n=x\n  \n好=好的\n")
        self.assertEqual(labels.load_name_types(self.path), {"好": "PER"})

    def test_missing_file_is_an_empty_map(self):
        self.assertEqual(labels.load_name_types(os.path.join(self._tmp.name, "missing.cfg")), {})


class WeakSpansTest(unittest.TestCase):

    def test_longest_match_wins(self):
        types = {"上官": "PER", "上官婉兮": "PER"}
        self.assertEqual(labels.weak_spans("上官婉兮", types), [(0, 4, "PER")])

    def test_every_occurrence_is_reported(self):
        types = {"上官婉兮": "PER", "上官雪": "PER"}
        self.assertEqual(labels.weak_spans("上官婉兮，上官雪。", types),
                         [(0, 4, "PER"), (5, 8, "PER")])

    def test_ignored_and_unknown_names_produce_no_span(self):
        self.assertEqual(labels.weak_spans("烈焰诀", {"烈焰诀": "IGNORE"}), [])
        self.assertEqual(labels.weak_spans("别的东西", {"别处": "PER"}), [])

    def test_empty_text_or_types(self):
        self.assertEqual(labels.weak_spans("", {"甲": "PER"}), [])
        self.assertEqual(labels.weak_spans("甲", {}), [])


if __name__ == "__main__":
    unittest.main()
