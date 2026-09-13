import re
import unicodedata
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from phrase_translation import render_translation, response_by_line, TranslationFormatError
from test_builder_translation import method
from test_phrase_translation import phrase


class QuickNamesTests(unittest.TestCase):
    def prepare(self, sources, responses, translations, names=None):
        app = SimpleNamespace(load_name_config=Mock(return_value=names or {}), translate_cached_fragment=Mock())
        review = SimpleNamespace(app=app, cn_lines=sources, response_lines=responses, vi_lines=translations)
        apply = method('apply_name_from_responses', source_file='builder_new.py', re=re,
                       unicodedata=unicodedata, render_translation=render_translation,
                       TranslationFormatError=TranslationFormatError)
        return review, lambda cn, vi: apply(review, cn, vi)

    def test_changes_source_match_not_identical_vietnamese_elsewhere(self):
        responses = [phrase('叶', 'lá') + phrase('云舒', 'mây thư'), phrase('白云', 'mây thư')]
        review, apply = self.prepare(['叶云舒', '白云'], responses, ['lá mây thư', 'mây thư'])
        self.assertEqual(apply('叶云舒', 'Diệp Vân Thư'), ['Diệp Vân Thư', 'mây thư'])
        review.app.translate_cached_fragment.assert_not_called()
        self.assertEqual(review.vi_lines, ['lá mây thư', 'mây thư'])

    def test_reapplying_name_uses_original_response(self):
        review, apply = self.prepare(['叶云舒知道'], [phrase('叶云舒', 'mây thư') + phrase('知道', 'biết')], ['Tên cũ biết'])
        review.vi_lines = apply('叶云舒', 'Tên mới')
        self.assertEqual(apply('叶云舒', 'Diệp Vân Thư'), ['Diệp Vân Thư biết'])

    def test_preserves_other_configured_names(self):
        review, apply = self.prepare(['叶云舒王林'], [phrase('叶云舒', 'mây thư') + phrase('王林', 'vương lâm')],
                                     ['mây thư Vương Lâm'], {'王林': 'Vương Lâm'})
        self.assertEqual(apply('叶云舒', 'Diệp Vân Thư'), ['Diệp Vân Thư Vương Lâm'])

    def test_missing_response_fails_without_partial_update(self):
        review, apply = self.prepare(['叶云舒', '叶云舒走'], [phrase('叶云舒', 'mây thư'), None], ['a', 'b'])
        with self.assertRaises(TranslationFormatError):
            apply('叶云舒', 'Diệp Vân Thư')
        self.assertEqual(review.vi_lines, ['a', 'b'])

    def test_only_retranslates_unavailable_phrase_remainder(self):
        review, apply = self.prepare(['叶云舒知道'], [phrase('叶云舒知道', 'mây thư biết')], ['mây thư biết'])
        review.app.translate_cached_fragment.return_value = 'biết'
        self.assertEqual(apply('叶云舒', 'Diệp Vân Thư'), ['Diệp Vân Thư biết'])
        review.app.translate_cached_fragment.assert_called_once_with('知道')

    def test_response_snapshots_preserve_paragraphs_entities_and_attributes(self):
        html = phrase('叶云舒', 'mây &amp; thư') + '\n' + phrase('王林', 'vương lâm')
        snapshots = response_by_line(html, '叶云舒。\n王林！')
        self.assertEqual([s for s, _ in snapshots], ['叶云舒。', '王林！'])
        self.assertEqual(render_translation(snapshots[0][1], snapshots[0][0]), 'mây & thư.')
        self.assertEqual(render_translation(snapshots[1][1], snapshots[1][0]), 'vương lâm!')
        self.assertIn('p="n"', snapshots[0][1])

    def test_cached_fragment_needs_no_api(self):
        app = SimpleNamespace(phrase_cache={'知道': phrase('知道', 'biết')}, translate_api=Mock())
        translate = method('translate_cached_fragment', source_file='builder_new.py', render_translation=render_translation)
        self.assertEqual(translate(app, '知道'), 'biết')
        app.translate_api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
