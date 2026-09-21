"""Lexicon-backed Chinese name discovery, independent of translation APIs.

Names require complete syntactic boundaries and person evidence. Dictionary
words are never promoted just because they recur. Scores are ranking weights,
not probabilities; counts are physical occurrences, not rule matches.
"""
from __future__ import annotations

import logging
import re
import sys
import threading
import unicodedata
from functools import lru_cache

import han_viet as hv

CJK = r'[\u3400-\u4dbf\u4e00-\u9fff]'
RUN = re.compile(CJK + '+')
FILLERS = frozenset('啊阿呀哎唉哦噢喔嗯唔呃诶欸哈呵嘿哼嘻哇啦嘛吧呢哟呐呜')
COMMON = frozenset('任由 任凭 刘海 花形徽帜 少年 少女 男人 女人 老人 众人 对方 自己 什么 哪里 大家 时候 办法 方法 东西 身体 目光 表情'.split())
GRAMMAR = frozenset('的了着把被这那你我他她它们吗呢吧地得和与及而则也却就都很更最仍又将正在')
INTRO = ('名叫', '叫做', '叫作', '名为', '唤作', '人称', '自称')
LEADS = ('告诉', '看见', '望向', '看向', '跟着', '跟随', '只见', '听见', '问向', '对', '向', '与', '和')
PERSON_VERBS = (
    '说道', '说', '问道', '问', '答道', '回答', '道', '笑道', '喊道', '喊',
    '叫道', '叫', '哭道', '叹道', '点头', '摇头', '皱眉', '看着', '望着',
    '抬头', '低头', '转身', '走进', '走出', '走来', '走向', '站起', '坐下',
    '冷笑', '微笑', '苦笑', '沉思', '开口', '行礼', '出手', '拔剑',
)
MODIFIERS = ('轻声', '低声', '沉声', '冷声', '大声', '缓缓', '淡淡', '突然', '连忙', '轻轻', '笑着', '哭着', '小声')
_LEXICON_LOCK = threading.Lock()


def alternatives(words):
    return '|'.join(re.escape(w) for w in sorted(words, key=lambda w: (-len(w), w)))


@lru_cache(maxsize=1)
def lexicon():
    try:
        import jieba
        import jieba.posseg
    except ImportError as error:
        raise RuntimeError('Thiếu bộ tách từ tiếng Trung. Cài bằng lệnh:\n'
                           f'"{sys.executable}" -m pip install jieba==0.42.1') from error
    jieba.setLogLevel(logging.ERROR)
    tokenizer = jieba.Tokenizer()
    tagger = jieba.posseg.POSTokenizer(tokenizer)
    tokenizer.initialize()
    return tokenizer, tagger.word_tag_tab


@lru_cache(maxsize=32768)
def word_parts(word):
    tokenizer, tags = lexicon()
    return tuple((part, tags.get(part, 'x')) for part in tokenizer.cut(word, HMM=False))


class NameScanner:
    def __init__(self):
        self.surnames = tuple(sorted(set(hv.DOUBLE_SURNAMES) | hv.SINGLE_SURNAMES | {'柳', '岳'}, key=lambda w: -len(w)))
        self.right = re.compile(r'(?:(?:' + alternatives(MODIFIERS) + r'))?(?:' + alternatives(PERSON_VERBS) + ')')
        self.titles = re.compile(alternatives(hv.TITLE_SUFFIXES))
        self.intros = re.compile(alternatives(INTRO))
        self.left = re.compile(alternatives(INTRO + LEADS))
        self.entity_patterns = [
            ('SECT', re.compile(r'(?:加入|拜入|出自|来自)(' + CJK + r'{2,6}[宗门派教阁])(?=$|[的中内外，。]|弟子|长老)')),
            ('PLACE', re.compile(r'(?:来到|抵达|进入|前往|返回)(' + CJK + r'{1,5}[城山岛谷湖国])(?=$|[的中内外后前，。])')),
            ('SKILL', re.compile(r'(?:施展|修炼|使出)(' + CJK + r'{2,6}(?:剑法|功法|心法|神功|诀|术))(?=$|[的后，。])')),
            ('ITEM', re.compile(r'(?:拿出|祭出|得到|获得)(' + CJK + r'{2,6}[鼎丹符镜塔])(?=$|[的后，。])')),
        ]

    def surname(self, name):
        return next((s for s in self.surnames if name.startswith(s) and len(name) > len(s)), '')

    def valid(self, name, explicit=False):
        if not 2 <= len(name) <= 6 or not RUN.fullmatch(name):
            return False
        if name in COMMON or name in hv.STOPWORD_TERMS or all(c in FILLERS for c in name):
            return False
        if any(c in GRAMMAR for c in name):
            return False
        _, tags = lexicon()
        tag = tags.get(name, '')
        # Complete ordinary dictionary words are negative evidence, regardless
        # of surname or frequency. Explicit introductions can disambiguate nouns.
        if tag and not tag.startswith('nr') and not (explicit and tag.startswith('n')):
            return False
        parts = word_parts(name)
        for i, (part, pos) in enumerate(parts):
            if pos in {'r', 'p', 'c', 'u', 'uj', 'ul', 'uz', 'y', 'e', 'o', 'f'}:
                return False
            # Compound common nouns/verbs inside a candidate indicate a phrase.
            # Given names like 林小米 remain possible under explicit introductions.
            if len(part) >= 2 and not pos.startswith(('nr', 'ns')) and not explicit:
                return False
            if i and len(part) == 1 and pos.startswith('v') and part in hv.INVALID_NAME_CHARS:
                return False
        return True

    def _discover(self, run, quoted):
        """Analyze a bounded run once; return relative spans with evidence."""
        starts = {0}
        explicit_starts = set()
        for match in self.left.finditer(run):
            starts.add(match.end())
        for match in self.intros.finditer(run):
            explicit_starts.add(match.end())
        spans = {}
        _, tags = lexicon()
        for start in sorted(starts):
            for end in range(start + 2, min(start + 6, len(run)) + 1):
                name = run[start:end]
                explicit = start in explicit_starts
                signals = set()
                tail = run[end:]
                if explicit and (not tail or tail[0] in '的是又也' or self.right.match(tail) or self.titles.match(tail)):
                    signals.add('introduction')
                surname = self.surname(name)
                plausible_length = len(name) <= (4 if len(surname) == 2 else 3) or (len(name) == 4 and name[-1] == name[-2])
                person_shape = bool(surname and plausible_length) or tags.get(name, '').startswith('nr')
                if person_shape and self.right.match(tail):
                    signals.add('subject')
                if person_shape and self.titles.match(tail):
                    signals.add('honorific')
                if person_shape and quoted and start == 0 and not tail:
                    signals.add('address')
                if signals and self.valid(name, explicit):
                    spans[(start, end)] = (name, signals)
        # Prefer a full span over a nested fragment from the same occurrence.
        found = [(a, b, n, tuple(sorted(s))) for (a, b), (n, s) in spans.items()
                 if not any(c <= a and b <= d and (c, d) != (a, b) for c, d in spans)]
        for kind, pattern in self.entity_patterns:
            for match in pattern.finditer(run):
                name = match.group(1)
                if name not in COMMON and not any(c in GRAMMAR for c in name):
                    found.append((*match.span(1), name, ('entity:' + kind,)))
        return found

    def scan(self, text, existing_glossary=None, max_results=250):
        if not text or max_results <= 0:
            return []
        with _LEXICON_LOCK:
            lexicon()
        text = unicodedata.normalize('NFC', text)
        saved = {unicodedata.normalize('NFC', n.strip()) for n in (existing_glossary or ()) if n.strip()}
        # Mask saved names to preserve offsets and prevent shorter fragments.
        if saved:
            pattern = re.compile(alternatives(saved))
            source = pattern.sub(lambda m: ' ' * len(m.group()), text)
        else:
            source = text
        local_cache = {}
        hits = {}
        for match in RUN.finditer(source):
            run = match.group()
            quoted = match.start() > 0 and source[match.start()-1] in '“「『"‘'
            key = (run, quoted)
            if key not in local_cache:
                if len(local_cache) >= 8192:
                    local_cache.clear()
                local_cache[key] = self._discover(run, quoted)
            for start, end, name, signals in local_cache[key]:
                record = hits.setdefault(name, {'positions': set(), 'signals': set(), 'contexts': []})
                absolute = match.start() + start
                record['positions'].add(absolute)
                record['signals'].update(signals)
                if len(record['contexts']) < 3:
                    context = text[max(0, absolute-24):min(len(text), match.start()+end+24)]
                    if context not in record['contexts']:
                        record['contexts'].append(context)
        results = []
        # Once a full name has evidence, count all non-overlapping occurrences,
        # including object/possessive uses not used for discovery.
        if hits:
            for data in hits.values():
                data['positions'].clear()
            for occurrence in re.finditer(alternatives(hits), source):
                hits[occurrence.group()]['positions'].add(occurrence.start())
        for name, data in hits.items():
            signals = data['signals']
            # Repetition affects ordering/count only, never confidence.
            score = max({'introduction': .92, 'subject': .76, 'honorific': .82, 'address': .68}.get(s, .72) for s in signals)
            score = min(.96, score + .04 * (len(signals)-1))
            kind = next((s.split(':')[1] for s in sorted(signals) if s.startswith('entity:')), 'PERSON')
            results.append({'cn': name, 'type': kind, 'confidence': round(score, 2),
                            'count': len(data['positions']), 'signals': sorted(signals),
                            'contexts': data['contexts'], 'suggested_vi': ''})
        results.sort(key=lambda c: (-c['confidence'], -c['count'], c['cn']))
        return results[:max_results]
