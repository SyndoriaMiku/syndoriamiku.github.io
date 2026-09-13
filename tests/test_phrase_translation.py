import unittest
import unicodedata
from types import SimpleNamespace
from unittest.mock import Mock

from phrase_translation import render_translation, split_source_text, response_by_line, TranslationFormatError, PhraseParser
from test_builder_translation import method


def phrase(cn, vi):
    return f"<i t='{cn}' h='âm' v='nghĩa/khác' p='n'>{vi}</i>"


class PhraseTranslationTests(unittest.TestCase):
    def test_supplied_response(self):
        response = "<i h='cứu cực' t='究极' v='cứu cực/chung cực' p='d'>Cứu cực</i>\n<i h='thực vật' t='植物' v='thực vật/cây cối/cây' p='n'>thực vật</i>\n<i h='hạ vị' t='下位' v='hạ vị' p='n'>hạ vị</i>"
        self.assertEqual(render_translation(response, '究极植物下位'), 'Cứu cực thực vật hạ vị')

    def test_attributes_retained(self):
        parser = PhraseParser()
        parser.feed(phrase('植物', 'cây'))
        self.assertEqual(parser.phrases[0], {'source': '植物', 'text': 'cây', 'han_viet': 'âm', 'alternatives': 'nghĩa/khác', 'pos': 'n'})

    def test_name_across_multiple_phrases(self):
        html = phrase('叶', 'Lá') + phrase('云舒', 'mây thư') + phrase('知道', 'biết')
        self.assertEqual(render_translation(html, '叶云舒知道', {'叶云舒': 'Diệp Vân Thư'}), 'Diệp Vân Thư biết')

    def test_longest_names_and_repeated_occurrences(self):
        html = phrase('叶云舒', 'mây thư') * 2
        self.assertEqual(render_translation(html, '叶云舒叶云舒', {'叶': 'Lá', '叶云舒': 'Diệp Vân Thư'}), 'Diệp Vân Thư Diệp Vân Thư')

    def test_paragraphs_from_source_not_html_formatting(self):
        html = phrase('植物', 'Cây') + '\n' + phrase('下位', 'hạ vị')
        self.assertEqual(render_translation(html, '植物。\n下位！'), 'Cây.\nhạ vị!')

    def test_source_punctuation_and_quotes(self):
        html = phrase('植物', 'Cây') + phrase('下位', 'hạ vị')
        self.assertEqual(render_translation(html, '“植物，下位。”'), '“Cây, hạ vị.”')

    def test_entities_decoded(self):
        self.assertEqual(render_translation(phrase('植物', 'cây &amp; lá&#x20;'), '植物'), 'cây & lá ')

    def test_partial_phrase_retranslates_remainder(self):
        translate = Mock(side_effect=['gặp', 'biết'])
        html = phrase('见叶云舒知道', 'bản dịch không thể cắt theo chữ')
        result = render_translation(html, '见叶云舒知道', {'叶云舒': 'Diệp Vân Thư'}, translate)
        self.assertEqual(result, 'gặp Diệp Vân Thư biết')
        self.assertEqual([c.args[0] for c in translate.call_args_list], ['见', '知道'])

    def test_partial_name_crossing_tokens(self):
        html = phrase('见叶', 'gặp lá') + phrase('云舒知道', 'mây thư biết')
        translate = Mock(side_effect=['gặp', 'biết'])
        self.assertEqual(render_translation(html, '见叶云舒知道', {'叶云舒': 'Diệp Vân Thư'}, translate), 'gặp Diệp Vân Thư biết')

    def test_plaintext_login_and_malformed_responses_rejected(self):
        for html in ('Cứu cực thực vật', '<html><form>Login</form></html>', '<i t="植物">cây', '<i>cây</i>'):
            with self.subTest(html=html), self.assertRaises(TranslationFormatError):
                render_translation(html, '植物')

    def test_missing_or_wrong_tokens_rejected(self):
        for html in (phrase('植物', 'cây'), phrase('其他', 'khác')):
            with self.subTest(html=html), self.assertRaises(TranslationFormatError):
                render_translation(html, '植物下位')

    def test_api_sends_original_chinese_and_keeps_tls_verification(self):
        response = Mock(status_code=200, text=phrase('叶云舒', 'mây thư'))
        requests = Mock()
        requests.post.return_value = response
        app = Mock(api_cookie='dummy-session', phrase_cache={})
        translate = method('translate_api', source_file='builder_new.py', requests=requests,
                           API_URL='https://example.test/api', API_BASE_URL='https://example.test',
                           CHUNK_LIMIT=15000, unicodedata=unicodedata, render_translation=render_translation,
                           response_by_line=response_by_line)
        self.assertEqual(translate(app, '叶云舒', {'叶云舒': 'Diệp Vân Thư'}), 'Diệp Vân Thư')
        kwargs = requests.post.call_args.kwargs
        self.assertEqual(kwargs['data'], {'ajax': 'trans', 'content': '叶云舒'})
        self.assertNotIn('verify', kwargs)
        self.assertFalse(kwargs['allow_redirects'])
        self.assertEqual(kwargs['headers']['Origin'], 'https://example.test')
        self.assertEqual(kwargs['headers']['Referer'], 'https://example.test/trans/')

    def test_missing_session_is_actionable(self):
        translate = method('translate_api', source_file='builder_new.py', unicodedata=unicodedata)
        with self.assertRaisesRegex(RuntimeError, 'Phiên API'):
            translate(Mock(api_cookie=''), '植物')

    def test_cookie_dialog_contains_steps_and_masks_input(self):
        dialog = Mock()
        dialog.askstring.return_value = None
        prompt = method('prompt_api_session', source_file='builder_new.py', simpledialog=dialog, API_BASE_URL='https://example.test')
        prompt(Mock())
        instructions = dialog.askstring.call_args.args[1]
        for step in ('đăng nhập', 'F12', 'Network', 'Fetch/XHR', 'Request Headers', 'Cookie'):
            self.assertIn(step, instructions)
        self.assertEqual(dialog.askstring.call_args.kwargs['show'], '*')
        self.assertIn('https://example.test/trans/', instructions)

    def test_source_limits_and_exact_preservation(self):
        for text in ('甲' * 15000, '甲' * 15001, '甲' * 30001,
                     '甲' * 14999 + '\n乙', '甲' * 14000 + '。' + '乙' * 2000):
            with self.subTest(length=len(text)):
                parts = split_source_text(text)
                self.assertEqual(''.join(parts), text)
                self.assertTrue(all(0 < len(part) <= 15000 for part in parts))

    def test_does_not_split_names_at_request_boundary(self):
        text = '甲' * 14998 + '叶云舒' + '乙' * 30
        parts = split_source_text(text, names={'叶云舒': 'Diệp Vân Thư'})
        self.assertEqual(''.join(parts), text)
        self.assertEqual(parts[1][:3], '叶云舒')
        self.assertEqual(len(parts[0]), 14998)

    def test_oversized_paragraph_never_posts_more_than_limit(self):
        requests = Mock()
        requests.post.side_effect = lambda *args, **kwargs: Mock(
            status_code=200, text=phrase(kwargs['data']['content'], 'dịch'))
        translate = method('translate_api', source_file='builder_new.py', requests=requests,
                           API_URL='https://example.test/api', API_BASE_URL='https://example.test',
                           CHUNK_LIMIT=15000, DELAY=0, time=Mock(), unicodedata=unicodedata,
                           split_source_text=split_source_text, render_translation=render_translation,
                           response_by_line=response_by_line)
        app = SimpleNamespace(api_cookie='dummy-session', phrase_cache={}, translate_cached_fragment=Mock())
        app.translate_api = lambda text, names=None: translate(app, text, names)
        self.assertEqual(app.translate_api('甲' * 30001), 'dịch dịch dịch')
        payloads = [c.kwargs['data']['content'] for c in requests.post.call_args_list]
        self.assertEqual([len(p) for p in payloads], [15000, 15000, 1])
        self.assertEqual(''.join(payloads), '甲' * 30001)
        self.assertIn('甲' * 30001, app.phrase_cache)

    def test_legacy_builder_keeps_old_request_without_cookie(self):
        import unicodedata
        requests = Mock()
        requests.post.return_value = Mock(status_code=200, text='cây')
        translate = method('translate_api', requests=requests, API_URL='https://legacy.test/', unicodedata=unicodedata)
        self.assertEqual(translate(Mock(), '植物'), 'cây')
        request = requests.post.call_args.kwargs
        self.assertEqual(request['data'], {'sajax': 'trans', 'content': '植物'})
        self.assertNotIn('Cookie', request['headers'])


if __name__ == '__main__':
    unittest.main()
