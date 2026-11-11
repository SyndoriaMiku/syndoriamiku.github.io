"""Weak labels for name-NER fine-tuning, derived from name.cfg.

Pure Python. The type is a hint (see the design doc): a name defaults to
PERSON, and a suffix only promotes it when the Vietnamese gloss agrees; a few
person names share a suffix-looking character, so gloss agreement filters those
out. SKILL/ITEM terms have no target label, so they are ignored (not trained).
"""
import re
import unicodedata

PER, LOC, ORG, IGNORE = "PER", "LOC", "ORG", "IGNORE"

# Hậu tố Hán -> từ khoá Hán-Việt phải có trong nghĩa Việt của name.cfg.
# Chỉ giữ hậu tố gần như không trùng chữ cuối tên người. Đã loại 国/渊/城/洲/
# 堂/楼/山/河 vì chúng xuất hiện cuối tên thật (林建国, 陆渊, 顾城, 沈玉堂,
# 赵长河, 苏青山) — gán nhầm loại sẽ đầu độc nhãn train.
SECT_SUFFIXES = {"宗": "Tông", "门": "Môn", "派": "Phái", "教": "Giáo",
                 "殿": "Điện", "阁": "Các"}
PLACE_SUFFIXES = {"岛": "Đảo", "湖": "Hồ", "谷": "Cốc", "界": "Giới", "域": "Vực"}
SKILL_SUFFIXES = {"诀": "Quyết", "术": "Thuật", "经": "Kinh", "功": "Công",
                  "丹": "Đan", "药": "Dược", "符": "Phù"}


def _key(text):
    text = unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def _has_word(gloss, word):
    return _key(word) in _key(gloss).split()


def _type_for(cn, vi):
    if not cn:
        return None
    last = cn[-1]
    if vi:
        if last in SECT_SUFFIXES and _has_word(vi, SECT_SUFFIXES[last]):
            return ORG
        if last in PLACE_SUFFIXES and _has_word(vi, PLACE_SUFFIXES[last]):
            return LOC
        if last in SKILL_SUFFIXES and _has_word(vi, SKILL_SUFFIXES[last]):
            return IGNORE
    return PER


def load_name_types(path):
    """Map each `cn` in name.cfg to PER/LOC/ORG/IGNORE; broken lines are skipped."""
    result = {}
    try:
        stream = open(path, "r", encoding="utf-8")
    except OSError:
        return result
    with stream:
        for line in stream:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            cn, vi = (part.strip() for part in line.split("=", 1))
            kind = _type_for(cn, vi)
            if kind:
                result[cn] = kind
    return result


def weak_spans(text, types):
    """Non-overlapping (start, end, type) spans, longest name first."""
    entries = {name: kind for name, kind in types.items() if name and kind != IGNORE}
    if not entries or not text:
        return []
    names = sorted(entries, key=lambda name: (-len(name), name))
    pattern = re.compile("|".join(re.escape(name) for name in names))
    spans = []
    end = 0
    for match in pattern.finditer(text):
        if match.start() < end:
            continue
        spans.append((match.start(), match.end(), entries[match.group()]))
        end = match.end()
    return spans
