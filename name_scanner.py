"""Chinese person-name candidates from syntactic boundaries; no n-gram counting.

Run ``python name_scanner.py`` for the sample and regression tests.
Counts are distinct (text position, signal) hits, not fabricated repetitions.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

import han_viet as hv

_CJK = r"[\u3400-\u4dbf\u4e00-\u9fff]"
_CJK_RUN = re.compile(_CJK + '+')
_SENTENCE = re.compile(r'[^。！？\r\n]+[。！？]?')


def _alternatives(words):
    return '|'.join(re.escape(word) for word in sorted(words, key=lambda s: (-len(s), s)))


class NameScanner:
    """Collect PERSON suggestions; confidence is a rule score, not probability."""

    def __init__(self):
        self.verbs = hv.VERB_SAY | hv.VERB_ACT
        self.verb_pattern = re.compile(_alternatives(self.verbs))
        self.call_pattern = re.compile(_alternatives(hv.NAME_CALL_PREFIXES))
        self.title_pattern = re.compile(_alternatives(hv.TITLE_SUFFIXES))
        self.stopword_pattern = re.compile(_alternatives(hv.STOPWORD_TERMS))
        self.surname_pattern = re.compile(_alternatives(set(hv.DOUBLE_SURNAMES) | hv.SINGLE_SURNAMES | {'阿'}))
        self.address_pattern = re.compile(r'[「『“"‘]\s*(' + _CJK + r'{1,4})(?=[，,!！])')
        self.followers = tuple(sorted(
            self.verbs | hv.TITLE_SUFFIXES | {'的', '向', '朝', '对', '与', '和', '被', '把', '也', '却', '便', '又', '正', '已', '是', '有', '行礼'},
            key=lambda s: (-len(s), s),
        ))

    def _valid(self, name):
        if not 1 <= len(name) <= 4 or not _CJK_RUN.fullmatch(name):
            return False
        if name in hv.STOPWORD_TERMS or name in self.verbs or name in hv.TITLE_SUFFIXES:
            return False
        # Do not trim grammar characters: doing so manufactures shorter names.
        return not any(ch in hv.INVALID_NAME_CHARS for ch in name)

    def _right_boundary(self, sentence, end):
        return (end == len(sentence) or not _CJK_RUN.match(sentence[end:end + 1])
                or sentence.startswith(self.followers, end))

    @staticmethod
    def _left_boundary(sentence, start):
        return (start == 0 or not _CJK_RUN.fullmatch(sentence[start - 1])
                or sentence[start - 1] in hv.INVALID_NAME_CHARS
                or sentence[:start].endswith(tuple(hv.NAME_CALL_PREFIXES) + ('朝', '和', '见', '告诉', '跟随')))

    def _before(self, sentence, end, max_length=4):
        """Prefer a complete surname-bearing subject, otherwise a bounded CJK run."""
        start = end
        while start > 0 and end - start < max_length and _CJK_RUN.fullmatch(sentence[start - 1]):
            start -= 1
        # A leading grammar word can separate the subject from earlier prose.
        candidates = []
        for pos in range(start, end):
            name = sentence[pos:end]
            if not self._valid(name):
                continue
            surname = self.surname_pattern.match(name)
            if surname and len(name) > len(surname.group()) and self._left_boundary(sentence, pos):
                candidates.append((pos, end))
        if candidates:
            return candidates[0]
        # Without a surname, require a left syntactic boundary, never arbitrary suffixes.
        while start < end and sentence[start] in hv.INVALID_NAME_CHARS:
            start += 1
        if start < end and (start == 0 or not _CJK_RUN.fullmatch(sentence[start - 1])
                            or sentence[start - 1] in hv.INVALID_NAME_CHARS):
            if self._valid(sentence[start:end]):
                return start, end
        return None

    def scan(self, text: str, existing_glossary=None, max_results: int = 200) -> list[dict]:
        if not text or max_results <= 0:
            return []
        text = unicodedata.normalize('NFC', text)
        glossary = {unicodedata.normalize('NFC', n.strip()) for n in (existing_glossary or ()) if n.strip()}
        # Protect entire saved names, including their potential shorter fragments.
        glossary_pattern = re.compile(_alternatives(glossary)) if glossary else None
        hits = defaultdict(lambda: {'events': set(), 'positions': set(), 'contexts': []})

        for sentence_match in _SENTENCE.finditer(text):
            sentence = sentence_match.group()
            offset = sentence_match.start()
            protected = [m.span() for m in glossary_pattern.finditer(sentence)] if glossary_pattern else []
            noise = [m.span() for m in self.stopword_pattern.finditer(sentence)]

            def record(start, end, signal):
                name = sentence[start:end]
                if not self._valid(name) or name in glossary:
                    return
                if any(lo <= start and end <= hi for lo, hi in protected):
                    return
                if any(lo <= start < hi for lo, hi in noise):
                    return
                event = (offset + start, offset + end, signal)
                data = hits[name]
                if event in data['events']:
                    return
                data['events'].add(event)
                data['positions'].add(event[:2])
                context = sentence[max(0, start - 12):min(len(sentence), end + 12)].strip()
                if context not in data['contexts'] and len(data['contexts']) < 3:
                    data['contexts'].append(context)

            # A: surnames trigger candidates only when the right edge is syntactic.
            # finditer consumes compound surnames, avoiding a second trigger inside them.
            for surname in self.surname_pattern.finditer(sentence):
                start = surname.start()
                if not self._left_boundary(sentence, start):
                    continue
                for end in range(surname.end() + 1, min(start + 4, len(sentence)) + 1):
                    if self._right_boundary(sentence, end) and self._valid(sentence[start:end]):
                        record(start, end, 'surname')

            # B: locate verbs first so a greedy capture cannot swallow their first char.
            for verb in self.verb_pattern.finditer(sentence):
                span = self._before(sentence, verb.start())
                if span:
                    record(*span, 'verb_context')

            # C: bound the introduced name at punctuation, grammar, title or next verb.
            for prefix in self.call_pattern.finditer(sentence):
                start = prefix.end()
                while start < len(sentence) and sentence[start] in ' :：「『“"‘':
                    start += 1
                for end in range(start + 1, min(start + 4, len(sentence)) + 1):
                    if self._valid(sentence[start:end]) and self._right_boundary(sentence, end):
                        record(start, end, 'direct_call')
                        break

            # D: honorifics also support a single-character surname (e.g. 王老师).
            for title in self.title_pattern.finditer(sentence):
                span = self._before(sentence, title.start())
                if span:
                    record(*span, 'honorific')

            # E: only the beginning of actual quoted speech, not every sentence.
            for address in self.address_pattern.finditer(sentence):
                record(*address.span(1), 'address')

        # Remove a substring only when every occurrence is inside the longer name
        # and both names have exactly the same number of physical occurrences.
        # This preserves a short name used independently, even with equal counts.
        suppressed = set()
        for name, data in hits.items():
            for length in range(1, len(name)):
                for index in range(len(name) - length + 1):
                    short = name[index:index + length]
                    if short not in hits:
                        continue
                    contained_positions = {(start + index, start + index + length)
                                           for start, _ in data['positions']}
                    if hits[short]['positions'] == contained_positions:
                        suppressed.add(short)

        results = []
        for name, data in hits.items():
            if name in suppressed:
                continue
            signals = [event[2] for event in data['events']]
            count = len(signals)
            confidence = (0.50 * ('surname' in signals)
                          + min(0.50, 0.25 * signals.count('verb_context'))
                          + 0.60 * ('direct_call' in signals)
                          + 0.30 * ('honorific' in signals)
                          + 0.30 * ('address' in signals)
                          + 0.10 * (count >= 2) + 0.10 * (count >= 5))
            if confidence < 0.30 and count == 1:
                continue
            results.append({
                'cn': name, 'confidence': round(min(confidence, 0.99), 2),
                'count': count, 'signals': sorted(set(signals)),
                'contexts': data['contexts'], 'suggested_vi': hv.han_viet_name(name),
            })
        results.sort(key=lambda item: (-item['confidence'], -item['count'], len(item['cn']), item['cn']))
        return results[:max_results]


if __name__ == '__main__':
    import sys
    import unittest
    from pathlib import Path
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sample = '林铭看着前方。“裴湘君，你来了！”他名叫阿宝。欧阳雪大人点头。独孤皂低头沉思。'
    for result in NameScanner().scan(sample):
        print(f"{result['cn']} -> {result['suggested_vi']} ({result['confidence']:.2f}, {result['signals']})")
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent / 'tests'), pattern='test_name_scanner.py')
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
