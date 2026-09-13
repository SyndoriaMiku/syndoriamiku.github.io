"""Translation pipeline regressions without live API calls or a Tk window."""
import ast
import os
import re
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unicodedata
import unittest
from unittest.mock import Mock


TREE = ast.parse((Path(__file__).resolve().parents[1] / 'builder.py').read_text(encoding='utf-8'))


def method(name, source_file='builder.py', **namespace):
    tree = TREE if source_file == 'builder.py' else ast.parse(
        (Path(__file__).resolve().parents[1] / source_file).read_text(encoding='utf-8'))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), source_file, 'exec'), namespace)
    return namespace[name]


class TranslationTests(unittest.TestCase):
    def translate(self, lines, replies):
        app = SimpleNamespace(translate_api=Mock(side_effect=replies), lbl_status=Mock())
        translate = method('translate_lines', time=SimpleNamespace(sleep=Mock()), DELAY=0)
        return translate(app, lines), app

    def test_aligned_batch_preserves_context_and_case(self):
        result, app = self.translate(['甲', '乙'], ['Câu A\nCâu B'])
        self.assertEqual(result, ['Câu A', 'Câu B'])
        app.translate_api.assert_called_once_with('甲\n乙')

    def test_extra_output_lines_are_not_discarded(self):
        result, app = self.translate(['甲', '乙'], ['A\nB\nC', 'A\nB', 'C'])
        self.assertEqual(result, ['A B', 'C'])
        self.assertEqual(app.translate_api.call_count, 3)

    def test_merged_output_is_realigned(self):
        result, _ = self.translate(['甲', '乙'], ['A B', 'A', 'B'])
        self.assertEqual(result, ['A', 'B'])

    def test_single_paragraph_keeps_all_output(self):
        result, app = self.translate(['甲'], ['A\nB\nC'])
        self.assertEqual(result, ['A B C'])
        self.assertEqual(app.translate_api.call_count, 1)

    def test_batch_retry(self):
        result, _ = self.translate(['甲'], [None, 'A'])
        self.assertEqual(result, ['A'])

    def test_failure_is_visible_for_each_paragraph(self):
        result, _ = self.translate(['甲', '乙'], [None, None])
        self.assertEqual(result, ['[Lỗi dịch]', '[Lỗi dịch]'])

    def test_individual_retry_does_not_shift_later_paragraphs(self):
        result, _ = self.translate(['甲', '乙'], ['merged', None, None, 'B'])
        self.assertEqual(result, ['[Lỗi dịch]', 'B'])

    def test_empty_input(self):
        result, app = self.translate([], [])
        self.assertEqual(result, [])
        app.translate_api.assert_not_called()

    def test_windows_line_endings(self):
        result, _ = self.translate(['甲', '乙'], ['A\r\nB'])
        self.assertEqual(result, ['A', 'B'])

    def test_glossary_keeps_user_spelling_and_accepts_bom(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'name.cfg').write_text('智酱=Tomo-chan\n云城=Vân thành\n', encoding='utf-8-sig')
            load = method('load_name_config', os=os, sys=sys, BASE_DIR=directory, unicodedata=unicodedata)
            self.assertEqual(load(None), {'智酱': 'Tomo-chan', '云城': 'Vân thành'})


class CapitalizationTests(unittest.TestCase):
    def fix(self, text, names=()):
        return method('fix_capitalization_after_names', re=re)(text, names)

    def test_reported_sentence_with_differently_translated_name(self):
        text = '" Ta không thể để mây thư \u200c Biết, "Phòng Dục Hà\u200c thống khổ lẩm bẩm, " Ta không thể để hắn nhìn thấy ta cái dạng này..." &#x20;'
        self.assertEqual(self.fix(text, ['Diệp Vân Thư', 'Phòng Dục Hà']), text.replace('Biết', 'biết'))

    def test_hidden_boundary_without_glossary(self):
        for hidden in ('\u200b', '\u200c', '\u200d', '\u2060', '\ufeff'):
            with self.subTest(hidden=repr(hidden)):
                text = 'Tôi muốn ' + hidden + ' Biết chuyện.'
                self.assertEqual(self.fix(text), text.replace('Biết', 'biết'))

    def test_preserves_sentence_and_dialogue_starts(self):
        for text in ('Xong.\u200c Biết rồi.', 'Xong! \u200c Biết rồi.',
                     'Xong?\u200c Biết rồi.', 'Xong…\u200c Biết rồi.',
                     'Xong\n\u200c Biết rồi.', 'Nói: "\u200c Biết rồi."'):
            with self.subTest(text=text):
                self.assertEqual(self.fix(text), text)

    def test_preserves_configured_names_and_acronyms(self):
        text = 'Tôi gặp\u200c Phòng Dục Hà và\u200c VIP.'
        self.assertEqual(self.fix(text, ['Phòng Dục Hà']), text)

    def test_multiple_boundaries_and_idempotence(self):
        text = 'mây thư\u200c Đi\u200c Vào.'
        expected = 'mây thư\u200c đi\u200c vào.'
        self.assertEqual(self.fix(text), expected)
        self.assertEqual(self.fix(expected), expected)

    def test_original_name_correction_still_works(self):
        text = 'Diệp Vân Thư\u200c Đi vào.'
        self.assertEqual(self.fix(text, ['Diệp Vân Thư']), text.replace('Đi', 'đi'))

    def test_no_blanket_lowercasing(self):
        text = 'Tôi gặp Akemi tại Hà Nội.'
        self.assertEqual(self.fix(text), text)


if __name__ == '__main__':
    unittest.main()
