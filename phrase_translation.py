"""Read SangTacViet phrase markup and apply a glossary against original text."""
from html.parser import HTMLParser
from html import escape
import re
import unicodedata


class TranslationFormatError(ValueError):
    pass


class PhraseParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.phrases = []
        self.current = None
        self.unsupported = False

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'form', 'html', 'body'):
            self.unsupported = True
        if tag == 'i':
            if self.current is not None:
                raise TranslationFormatError('Response chứa thẻ cụm từ lồng nhau.')
            self.current = {'attrs': dict(attrs), 'parts': []}

    def handle_data(self, data):
        if self.current is not None:
            self.current['parts'].append(data)

    def handle_endtag(self, tag):
        if tag == 'i' and self.current is not None:
            attrs = self.current['attrs']
            original = unicodedata.normalize('NFC', attrs.get('t', ''))
            if not original:
                raise TranslationFormatError('Thẻ cụm từ thiếu thuộc tính t (tiếng Trung gốc).')
            self.phrases.append({
                'source': original,
                'text': unicodedata.normalize('NFC', ''.join(self.current['parts'])),
                'han_viet': attrs.get('h', ''),
                'alternatives': attrs.get('v', ''),
                'pos': attrs.get('p', ''),
            })
            self.current = None


_CJK = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff]')
_PUNCTUATION = str.maketrans({'，': ',', '。': '.', '！': '!', '？': '?', '：': ':', '；': ';'})
def _omitted_tokens(source, start, end):
    """Trust API omissions instead of maintaining a fixed particle dictionary.

    Empty spans consume omitted Chinese without leaking it into Vietnamese.
    Original offsets remain available for glossary matches, including names
    crossing or entirely inside an omitted span. Punctuation and spacing stay.
    """
    return [(match.start(), match.end(), '')
            for match in _CJK.finditer(source, start, end)]


def response_by_line(response, source):
    """Snapshot phrase markup for each original paragraph after validation."""
    parser = PhraseParser()
    parser.feed(response)
    parser.close()
    lines = source.split('\n')
    buckets = [[] for _ in lines]
    cursor = 0
    for phrase in parser.phrases:
        start = source.find(phrase['source'], cursor)
        if start < 0:
            raise TranslationFormatError('Không thể lưu cụm từ theo dòng gốc.')
        line_index = source.count('\n', 0, start)
        attrs = {'t': phrase['source'], 'h': phrase['han_viet'],
                 'v': phrase['alternatives'], 'p': phrase['pos']}
        attributes = ' '.join(f'{key}="{escape(value, quote=True)}"' for key, value in attrs.items())
        buckets[line_index].append(f'<i {attributes}>{escape(phrase["text"])}</i>')
        cursor = start + len(phrase['source'])
    return [(line, ''.join(parts)) for line, parts in zip(lines, buckets)]


def split_source_text(text, limit=15000, names=None):
    """Split oversized input without losing characters or cutting glossary names."""
    if limit < 1:
        raise ValueError('Giới hạn request phải lớn hơn 0.')
    name_spans = []
    keys = [key for key in (names or {}) if key]
    if keys:
        pattern = re.compile('|'.join(re.escape(k) for k in sorted(keys, key=lambda k: (-len(k), k))))
        name_spans = [m.span() for m in pattern.finditer(text)]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            # Prefer a paragraph, then a sentence boundary in the latter half.
            floor = start + limit // 2
            newline = text.rfind('\n', floor, end)
            if newline >= 0:
                end = newline + 1
            else:
                punctuation = list(re.finditer(r'[。！？.!?；;]', text[floor:end]))
                if punctuation:
                    end = floor + punctuation[-1].end()
            for lo, hi in name_spans:
                if lo < end < hi:
                    end = lo
                    break
            if end <= start:
                raise TranslationFormatError('Một tên riêng dài hơn giới hạn request của API.')
        chunks.append(text[start:end])
        start = end
    return chunks


def render_translation(response, source, names=None, translate_fragment=None):
    """Return plain Vietnamese, preserving source paragraphs, not HTML indentation.

    Names may span several phrases. If a name only occupies part of a phrase,
    translate the remaining source fragments separately instead of guessing which
    translated words to remove. ``translate_fragment`` must return plain text.
    """
    source = unicodedata.normalize('NFC', source)
    parser = PhraseParser()
    parser.feed(response)
    parser.close()
    if parser.unsupported or parser.current is not None or not parser.phrases:
        raise TranslationFormatError(
            'API không trả các thẻ <i t="..."> hợp lệ. '
            'Hãy kiểm tra phiên đăng nhập và chế độ trả response theo cụm từ.'
        )

    tokens = []
    cursor = 0
    for phrase in parser.phrases:
        start = source.find(phrase['source'], cursor)
        if start < 0:
            raise TranslationFormatError('Không ghép được cụm từ API với tiếng Trung gốc; đã dừng để tránh mất nội dung.')
        tokens.extend(_omitted_tokens(source, cursor, start))
        end = start + len(phrase['source'])
        if '\n' in source[start:end] or '\r' in source[start:end]:
            raise TranslationFormatError('Một cụm từ API vượt qua ranh giới đoạn văn.')
        tokens.append((start, end, phrase['text']))
        cursor = end
    tokens.extend(_omitted_tokens(source, cursor, len(source)))

    glossary = {unicodedata.normalize('NFC', k): v for k, v in (names or {}).items() if k and v}
    replacements = []
    if glossary:
        pattern = re.compile('|'.join(re.escape(k) for k in sorted(glossary, key=lambda k: (-len(k), k))))
        replacements = [(m.start(), m.end(), glossary[m.group()]) for m in pattern.finditer(source)]

    spans = list(replacements)
    for start, end, translated in tokens:
        overlaps = [(lo, hi) for lo, hi, _ in replacements if lo < end and hi > start]
        if not overlaps:
            spans.append((start, end, translated))
            continue
        cursor = start
        for lo, hi in overlaps + [(end, end)]:
            if cursor < lo:
                if translate_fragment is None:
                    raise TranslationFormatError('Tên nằm trong một cụm dài; cần dịch riêng phần còn lại của cụm.')
                fragment = translate_fragment(source[cursor:lo])
                if fragment is None:
                    raise TranslationFormatError('Không dịch được phần còn lại của cụm chứa tên riêng.')
                spans.append((cursor, lo, fragment))
            cursor = max(cursor, min(end, hi))

    # The source determines real paragraph breaks. Newlines between HTML tags
    # are formatting and must not become extra paragraphs in the review window.
    result = ''
    cursor = 0
    for start, end, translated in sorted(spans):
        gap = source[cursor:start].translate(_PUNCTUATION)
        result += gap
        if (translated and result and not result[-1].isspace()
                and result[-1] not in '([{"“‘「『' and translated[0] not in ',.!?:;)]}"”’」』'):
            result += ' '
        result += translated
        cursor = end
    return result + source[cursor:].translate(_PUNCTUATION)
