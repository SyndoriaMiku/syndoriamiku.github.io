import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import moxhi_scanner as m  # noqa: E402

HV = {'韩立': 'Hàn Lập', '小龙': 'Tiểu Long', '和小龙': 'Hòa Tiểu Long', '太浩宗': 'Thái Hạo Tông',
      '太浩宗内': 'Thái Hạo Tông Nội', '青冥剑': 'Thanh Minh Kiếm', '慕云烟': 'Mộ Vân Yên'}
reading = HV.get


def cand(cn, count=1, conf=0.9, typ='PERSON', **kw):
    return dict(cn=cn, type=typ, confidence=conf, count=count, contexts=[cn], signals=[kw.pop('signal', 'X')],
                suggested_vi='', **kw)


class TaggedEntitiesTest(unittest.TestCase):
    def test_well_formed(self):
        raw = '<PER> Hàn Lập</PER> dâng lên<ITEM> Thanh Minh kiếm</ITEM> , "<ITEM> Thái Huyền Đan Kinh</ITEM> "'
        self.assertEqual(m.tagged_entities(raw), [('PER', 'Hàn Lập'), ('ITEM', 'Thanh Minh kiếm'),
                                                   ('ITEM', 'Thái Huyền Đan Kinh')])

    def test_broken_tags(self):
        # đóng sai loại → theo loại thẻ mở; thẻ mở lồng → bỏ thẻ trước; thẻ đóng thừa / mở không đóng → bỏ
        raw = '<LOC>Thiên Nam</ORG> x </PER> <PER>A <PER>Mộ Vân Yên</PER> y <ORG>Lạc'
        self.assertEqual(m.tagged_entities(raw), [('LOC', 'Thiên Nam'), ('PER', 'Mộ Vân Yên')])


class AlignTest(unittest.TestCase):
    def test_reading_first_then_order(self):
        cn = [('PER', '韩立'), ('ITEM', '青冥剑'), ('PER', '慕云烟')]
        vi = [('PER', 'Mộ Vân Yên'), ('PER', 'Hàn Lập'), ('ITEM', 'Thanh Minh kiếm')]
        self.assertEqual(m.align_names(cn, vi, reading),
                         {'韩立': 'Hàn Lập', '慕云烟': 'Mộ Vân Yên', '青冥剑': 'Thanh Minh kiếm'})

    def test_unequal_counts_not_guessed(self):
        cn = [('PER', '甲乙'), ('PER', '丙丁')]
        vi = [('PER', 'Một Người')]
        self.assertEqual(m.align_names(cn, vi), {})


class SentenceTest(unittest.TestCase):
    def test_split_and_long_cut(self):
        text = '第一句。第二句！\n' + '长' * 30 + '，' + '短' * 30 + '。'
        spans = m.split_sentences(text, limit=40)
        self.assertEqual([text[a:b] for a, b in spans][:2], ['第一句。', '第二句！'])
        self.assertTrue(all(b - a <= 40 for a, b in spans))
        self.assertEqual(''.join(text[a:b] for a, b in spans).replace('\n', ''), text.replace('\n', ''))


class TrimMergeTest(unittest.TestCase):
    def test_trim_by_translation(self):
        out = m.trim_edges([cand('和小龙', 6, moxhi_vi='Tiểu Long'), cand('小龙', 14, moxhi_vi='Tiểu Long')], reading)
        self.assertEqual([(c['cn'], c['count']) for c in out], [('小龙', 20)])

    def test_trim_function_char_only_when_core_exists(self):
        out = m.trim_edges([cand('太浩宗内', 12, typ='ORG'), cand('太浩宗', 30, typ='ORG'), cand('内门弟子', 2)])
        self.assertEqual(sorted(c['cn'] for c in out), ['内门弟子', '太浩宗'])
        self.assertEqual(next(c for c in out if c['cn'] == '太浩宗')['count'], 42)

    def test_merge_agreement_first(self):
        bert = [cand('韩立', 5, 0.99, signal='BERT'), cand('平常', 6, 0.7, signal='BERT')]
        moxhi = [cand('韩立', 5, 0.97, signal='Moxhi', moxhi_vi='Hàn Lập'),
                 cand('青冥剑', 2, 0.88, typ='ITEM', signal='Moxhi', moxhi_vi='Thanh Minh kiếm')]
        out = m.merge_candidates(bert, moxhi)
        self.assertEqual(out[0]['cn'], '韩立')
        self.assertIn(m.AGREE, out[0]['signals'])
        self.assertEqual(out[0]['moxhi_vi'], 'Hàn Lập')
        self.assertEqual(out[0]['contexts'], ['韩立'])          # ngữ cảnh trùng không lặp lại
        both = m.merge_candidates([dict(cand('甲乙'), contexts=['b1'])], [dict(cand('甲乙'), contexts=['m1', 'm2'])])
        self.assertEqual(both[0]['contexts'], ['b1', 'm1', 'm2'])  # giữ cả ngữ cảnh của Moxhi
        self.assertEqual({c['cn'] for c in out}, {'韩立', '平常', '青冥剑'})
        self.assertNotIn(m.AGREE, next(c for c in out if c['cn'] == '平常')['signals'])


if __name__ == '__main__':
    unittest.main()
