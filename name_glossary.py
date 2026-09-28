"""Safe batch updates for name.cfg."""
from __future__ import annotations

import os
import re
import tempfile
import unicodedata

_CJK = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff]')


def normalize_entries(entries):
    normalized = {}
    for cn, vi in entries:
        cn = unicodedata.normalize('NFC', cn.strip())
        vi = unicodedata.normalize('NFC', vi.strip())
        if not cn or not vi:
            continue
        if _CJK.search(vi):
            raise ValueError(f'Bản dịch của “{cn}” vẫn chứa chữ Trung: {vi}')
        if '\n' in cn or '\n' in vi or '=' in cn:
            raise ValueError(f'Tên không hợp lệ: {cn}')
        normalized[cn] = vi
    return normalized


def update_name_cfg(path, entries):
    """Add/update all entries with one read and one atomic file replacement."""
    pending = normalize_entries(entries)
    if not pending:
        return 0
    lines = []
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8', newline='') as stream:
            lines = stream.readlines()
    newline = '\r\n' if any(line.endswith('\r\n') for line in lines) else '\n'
    positions = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and '=' in stripped:
            key, _ = stripped.split('=', 1)
            positions[unicodedata.normalize('NFC', key.strip())] = index
    changed = 0
    for cn, vi in pending.items():
        replacement = f'{cn}={vi}{newline}'
        if cn in positions:
            index = positions[cn]
            if lines[index] != replacement:
                lines[index] = replacement
                changed += 1
        else:
            if lines and not lines[-1].endswith('\n'):
                lines[-1] += newline
            positions[cn] = len(lines)
            lines.append(replacement)
            changed += 1
    if not changed:
        return 0
    directory = os.path.dirname(os.path.abspath(path))
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', newline='', delete=False,
                dir=directory, prefix='.name-', suffix='.tmp') as stream:
            temp_path = stream.name
            stream.writelines(lines)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
    return changed


# --- Dấu cách quanh tên trong bản dịch ---
# Tên Việt được chèn vào câu tiếng Trung trước khi gửi API. API coi đó là chữ
# ngoại nên hay dán tên vào dấu câu/từ bên cạnh ("quang.Trần Dĩ Hàng",
# "Trần ThầnY Y") hoặc để thừa dấu cách khi bỏ hư từ ("Hương Hương ." từ 的。).
_SENTENCE_PUNCT = ',.;:!?…'
_OPENING = '([{“‘「『'
_CLOSING = ')]}”’」』'
_STRAIGHT_QUOTES = '"＂'


def compile_name_source_pattern(names):
    """Longest-first pattern over the Chinese keys of name.cfg."""
    keys = sorted((k for k in names if k), key=lambda k: (-len(k), k))
    return re.compile('|'.join(map(re.escape, keys))) if keys else None


def substitute_names(line, names, pattern=None):
    """Replace Chinese names in one pass, padding them so the API keeps word
    boundaries. Extra spaces are removed by fix_name_spacing afterwards."""
    pattern = pattern if pattern is not None else compile_name_source_pattern(names)
    if pattern is None:
        return line
    return pattern.sub(lambda match: f' {names[match.group()]} ', line)


def compile_name_loose_pattern(vi_names):
    names = sorted(set(n.strip() for n in vi_names if n and n.strip()), key=len, reverse=True)
    return re.compile('|'.join(map(re.escape, names))) if names else None


def _glued(left, right):
    """A lowercase→uppercase change never happens inside a Vietnamese word."""
    return left.islower() and right.isupper()


def _name_spans(text, pattern):
    """Whole-word name matches, plus names the API glued to a neighbour word."""
    spans = []
    pos = 0
    while True:
        match = pattern.search(text, pos)
        if not match:
            return spans
        start, end = match.span()
        before_ok = start == 0 or not text[start - 1].isalnum() or _glued(text[start - 1], text[start])
        after_ok = end == len(text) or not text[end].isalnum() or _glued(text[end - 1], text[end])
        if before_ok and after_ok:
            spans.append((start, end))
            pos = end
        else:
            pos = start + 1


def _is_opening(text, index):
    char = text[index]
    if char in _OPENING:
        return True
    return char in _STRAIGHT_QUOTES and text.count(char, 0, index) % 2 == 0


def _is_closing(text, index):
    char = text[index]
    if char in _CLOSING:
        return True
    return char in _STRAIGHT_QUOTES and text.count(char, 0, index) % 2 == 1


def fix_name_spacing(text, pattern):
    """Normalise spaces on both sides of glossary names in translated text.

    ``pattern`` comes from compile_name_loose_pattern (Vietnamese names).
    Only the spacing next to a name changes; the rest of the line is kept.
    """
    if not text or pattern is None:
        return text
    inserts = set()
    removals = set()
    for start, end in _name_spans(text, pattern):
        # Bên trái tên.
        if start and text[start - 1].isspace():
            left = start
            while left and text[left - 1] in ' \t ':
                left -= 1
            if left and left < start and _is_opening(text, left - 1):
                removals.add((left, start))  # “ Uy Ca → “Uy Ca
        elif start:
            prev = text[start - 1]
            if prev.isalnum() or _is_closing(text, start - 1):
                inserts.add(start)
            elif prev in _SENTENCE_PUNCT:
                run = start - 1
                while run and text[run - 1] in _SENTENCE_PUNCT:
                    run -= 1
                # "...Tên" ở đầu lời thoại/đầu dòng giữ nguyên.
                if run and not _is_opening(text, run - 1):
                    inserts.add(start)
        # Bên phải tên.
        if end < len(text) and text[end] in ' \t ':
            right = end
            while right < len(text) and text[right] in ' \t ':
                right += 1
            if right < len(text) and (text[right] in _SENTENCE_PUNCT or _is_closing(text, right)):
                removals.add((end, right))  # Tên ? → Tên?
        elif end < len(text):
            nxt = text[end]
            if nxt.isalnum() or _is_opening(text, end):
                inserts.add(end)
    if not inserts and not removals:
        return text
    removed = {i for lo, hi in removals for i in range(lo, hi)}
    parts = []
    for index, char in enumerate(text):
        if index in inserts:
            parts.append(' ')
        if index not in removed:
            parts.append(char)
    return ''.join(parts)
