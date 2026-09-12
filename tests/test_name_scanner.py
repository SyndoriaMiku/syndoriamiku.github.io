"""Behavioral regressions for syntactic person-name detection, without Tk/API."""
import ast
from pathlib import Path
import unittest

from name_scanner import NameScanner


class NameScannerTests(unittest.TestCase):
    def setUp(self):
        self.scanner = NameScanner()

    def scan(self, text, **kwargs):
        return {r['cn']: r for r in self.scanner.scan(text, **kwargs)}

    def test_single_mention_with_surname_and_verb(self):
        result = self.scan('叶云舒走进大厅。')
        self.assertEqual(set(result), {'叶云舒'})
        self.assertEqual(result['叶云舒']['confidence'], .85)
        self.assertEqual(result['叶云舒']['count'], 2)

    def test_compound_surnames(self):
        self.assertEqual(set(self.scan('欧阳雪大人点头。独孤皂低头沉思。')), {'欧阳雪', '独孤皂'})

    def test_direct_call_stops_before_verb(self):
        self.assertEqual(set(self.scan('他名叫叶云舒走进大厅。')), {'叶云舒'})

    def test_direct_call_stops_before_grammar(self):
        self.assertEqual(set(self.scan('他叫阿宝的朋友来了。')), {'阿宝'})

    def test_non_surname_direct_call_not_counted_twice(self):
        result = self.scan('名叫紫菱。')['紫菱']
        self.assertEqual(result['signals'], ['direct_call'])
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['confidence'], .60)

    def test_single_character_introduction(self):
        self.assertIn('紫', self.scan('字紫。'))

    def test_call_prefix_variants(self):
        for prefix in ('名叫', '叫做', '叫', '唤作', '名为', '称呼', '字'):
            with self.subTest(prefix=prefix):
                self.assertIn('紫菱', self.scan(prefix + '紫菱。'))

    def test_honorific_single_hit_survives(self):
        result = self.scan('紫菱姑娘来了。')['紫菱']
        self.assertEqual(result['confidence'], .30)
        self.assertEqual(result['signals'], ['honorific'])

    def test_single_surname_honorific(self):
        self.assertIn('王', self.scan('王老师说：“好。”'))

    def test_dialogue_quote_variants(self):
        for opening in ('“', '「', '『', '"'):
            with self.subTest(opening=opening):
                self.assertIn('紫菱', self.scan(opening + '紫菱！'))

    def test_no_address_from_unquoted_sentence(self):
        self.assertEqual(self.scan('紫菱，过来。'), {})

    def test_common_words_are_not_names(self):
        self.assertEqual(self.scan('然后少女说道，众人看着他。王国非常安静。' * 5), {})

    def test_no_entities_from_internal_surname(self):
        self.assertEqual(self.scan('青云宗，天剑门，玄武城。'), {})

    def test_sentence_boundaries(self):
        self.assertNotIn('叶云舒', self.scan('叶\n云舒。叶。云舒。'))
        self.assertEqual(set(self.scan('名叫紫\n菱。')), {'紫'})

    def test_possessive_and_direction(self):
        self.assertIn('林铭', self.scan('林铭的声音传来。'))
        self.assertIn('林铭', self.scan('林铭朝前方而去。'))

    def test_saved_names_and_fragments_excluded(self):
        self.assertEqual(self.scan('叶云舒说道。欧阳雪大人点头。',
                                   existing_glossary={'叶云舒', '欧阳雪'}), {})

    def test_saved_name_does_not_hide_independent_short_name(self):
        self.assertEqual(set(self.scan('林铭说道。林铭轩走来。', existing_glossary={'林铭轩'})), {'林铭'})

    def test_independent_short_name_survives_dedup(self):
        self.assertEqual(set(self.scan('林铭说道。林铭轩说道。')), {'林铭', '林铭轩'})

    def test_no_overlong_name_from_direct_call(self):
        self.assertNotIn('叶云舒走', self.scan('名叫叶云舒走进大厅。'))

    def test_score_caps_contexts_sort_and_limit(self):
        text = '林铭说道。' * 10 + '名叫紫菱。'
        results = self.scanner.scan(text)
        first = results[0]
        self.assertEqual(first['cn'], '林铭')
        self.assertEqual(first['confidence'], .99)
        self.assertEqual(first['count'], 20)
        self.assertLessEqual(len(first['contexts']), 3)
        self.assertTrue(first['suggested_vi'])
        self.assertEqual(self.scanner.scan(text, max_results=1), results[:1])
        self.assertEqual(self.scanner.scan(text, max_results=0), [])

    def test_empty_input(self):
        self.assertEqual(self.scanner.scan(''), [])

    def test_builder_wrapper_uses_glossary_and_person_type(self):
        # Extract the method so this integration check needs no GUI installation.
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'builder.py').read_text(encoding='utf-8'))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'scan_name_candidates')
        namespace = {'_NAME_SCANNER_OK': True, '_NameScanner': NameScanner}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'builder.py', 'exec'), namespace)
        app = type('App', (), {'load_name_config': lambda self: {'叶云舒': 'Diệp Vân Thư'}})()
        results = namespace['scan_name_candidates'](app, '叶云舒走来。林铭说道。', 1)
        self.assertEqual([r['cn'] for r in results], ['林铭'])
        self.assertEqual(results[0]['type'], 'PERSON')


if __name__ == '__main__':
    unittest.main()
