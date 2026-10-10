"""Safe file helpers shared by builder.py and editor.py.

Everything here is Tk-free so it can be tested on its own:
- atomic JSON writes with a .bak copy of the previous catalog,
- strict catalog reads (never treat an unreadable list.json as empty),
- chapter encoding/saving for library/<story>/<chapter>/data.json,
- text-file decoding for Chinese sources (UTF-8 / GB18030 / Big5 / UTF-16),
- splitting paragraphs into chapters and bulk replace across a story.
"""
from __future__ import annotations

import base64
import datetime
import json
import os
import re
import shutil
import tempfile
import unicodedata

DEFAULT_SPLIT_PATTERNS = [
    ("Chương X (mặc định)", r"^chương\s+[\d]+"),
    ("Chương X: Tiêu đề", r"^chương\s+[\d]+[\s:：·]"),
    ("Thứ X chương", r"^thứ\s+\d+\s+chương"),
    ("Chương X + Thứ X chương", r"^chương\s+[\d]+|^thứ\s+\d+\s+chương"),
    ("Tiết X:", r"^tiết\s+[\d\w]+[\s:：]"),
    ("Chapter X (English)", r"^chapter\s+\d+"),
]


class CatalogError(RuntimeError):
    """list.json exists but cannot be used; callers must not overwrite it."""


# ─────────────────────────── JSON / files ───────────────────────────

def write_text_atomic(path, text):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix='.tmp-', suffix='.part', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def write_json_atomic(path, data, indent=None, backup=False):
    """Write JSON via temp file + rename. backup=True keeps the old file as .bak."""
    text = json.dumps(data, ensure_ascii=False, indent=indent)
    if backup and os.path.isfile(path):
        try:
            shutil.copy2(path, path + '.bak')
        except OSError:
            pass  # a failed backup must not block the (atomic) save itself
    write_text_atomic(path, text)


def read_catalog(path):
    """Return the catalog list. Missing file -> []. Broken file -> CatalogError."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8-sig') as stream:
            data = json.load(stream)
    except (OSError, ValueError) as error:
        hint = ''
        if os.path.isfile(path + '.bak'):
            hint = f'\n\nCó bản sao lưu: {os.path.basename(path)}.bak — kiểm tra rồi đổi tên để khôi phục.'
        raise CatalogError(f'Không đọc được {path}:\n{error}{hint}') from error
    if not isinstance(data, list):
        raise CatalogError(f'{path} không phải danh sách truyện hợp lệ.')
    return data


def chapter_sort_key(chapter):
    """Numeric chapter IDs in number order; any non-numeric ID goes last."""
    chapter_id = str(chapter.get('id', ''))
    return (0, int(chapter_id), '') if chapter_id.isdigit() else (1, 0, chapter_id)


def sort_chapters(catalog):
    """Order each story's chapters by ID (the web page lists them as stored)."""
    for story in catalog:
        chapters = story.get('chapters') if isinstance(story, dict) else None
        if isinstance(chapters, list):
            chapters.sort(key=chapter_sort_key)
    return catalog


def write_catalog(path, catalog):
    write_json_atomic(path, sort_chapters(catalog), indent=4, backup=True)


# ─────────────────────────── text decoding ───────────────────────────

def decode_text_bytes(raw):
    """Return (text, encoding) for a Chinese/Vietnamese .txt file."""
    if raw.startswith(b'\xef\xbb\xbf'):
        return raw[3:].decode('utf-8'), 'UTF-8 BOM'
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        return raw.decode('utf-16'), 'UTF-16'
    try:
        return raw.decode('utf-8'), 'UTF-8'
    except UnicodeDecodeError:
        pass
    # GB18030 decodes almost any byte string, so Big5 files would come out as
    # gibberish. When both decode, keep the one with more common Chinese words.
    candidates = []
    for encoding, label in (('gb18030', 'GB18030'), ('big5', 'Big5')):
        try:
            candidates.append((raw.decode(encoding), label))
        except UnicodeDecodeError:
            continue
    if candidates:
        return max(candidates, key=lambda item: _common_ratio(item[0]))
    return raw.decode('utf-8', errors='replace'), 'UTF-8 (có ký tự lỗi)'


_COMMON_HANZI = frozenset('的一是不了人我在有他她这這个個们們中来來上大为為和国國地到以说說'
                          '时時要就出会會可也你对對着著那道自里裡后後看么麼没沒过過去心')


def _common_ratio(text):
    sample = text[:20000]
    hanzi = [c for c in sample if '\u4e00' <= c <= '\u9fff']
    return sum(c in _COMMON_HANZI for c in hanzi) / len(hanzi) if hanzi else 0


def read_text_file(path):
    with open(path, 'rb') as stream:
        raw = stream.read()
    text, encoding = decode_text_bytes(raw)
    return unicodedata.normalize('NFC', text.replace('\r\n', '\n').replace('\r', '\n')), encoding


# ─────────────────────────── chapters ───────────────────────────

def b64(text):
    return base64.b64encode((text or '').encode('utf-8')).decode('utf-8')


def unb64(value):
    try:
        return unicodedata.normalize('NFC', base64.b64decode(value).decode('utf-8'))
    except Exception:
        return None


def chapter_payload(story_title, chapter_title, pairs):
    """pairs: iterable of (cn, vi). cn may be ''."""
    return {
        'title': story_title,
        'chapter_title': chapter_title,
        'content': [{'cn': b64(unicodedata.normalize('NFC', cn or '')),
                     'vi': b64(unicodedata.normalize('NFC', vi or ''))} for cn, vi in pairs],
    }


def copy_templates(library_dir, base_dir, story_slug, chapter_id=None):
    story_dir = os.path.join(library_dir, story_slug)
    os.makedirs(story_dir, exist_ok=True)
    story_template = os.path.join(library_dir, 'story.html')
    story_index = os.path.join(story_dir, 'index.html')
    if os.path.exists(story_template) and not os.path.exists(story_index):
        try:
            shutil.copy2(story_template, story_index)
        except OSError:
            pass
    if chapter_id:
        reader = os.path.join(base_dir, 'reader.html')
        if os.path.exists(reader):
            try:
                shutil.copy2(reader, os.path.join(story_dir, chapter_id, 'index.html'))
            except OSError:
                pass


def write_chapter(library_dir, base_dir, story_slug, chapter_id, payload):
    chapter_dir = os.path.join(library_dir, story_slug, chapter_id)
    os.makedirs(chapter_dir, exist_ok=True)
    write_json_atomic(os.path.join(chapter_dir, 'data.json'), payload)
    copy_templates(library_dir, base_dir, story_slug, chapter_id)


def upsert_chapter(catalog, story_slug, story_title, chapter_id, chapter_name, now=None):
    """Add/update a chapter entry and bump the story timestamp. Returns the story."""
    now = now or datetime.datetime.now()
    date = now.strftime('%d/%m/%Y')
    story = next((item for item in catalog if item.get('slug') == story_slug), None)
    if story is None:
        story = {'title': story_title, 'slug': story_slug, 'date': date,
                 'timestamp': now.timestamp(), 'chapters': []}
        catalog.append(story)
    story['title'] = story_title
    story['date'] = date
    story['timestamp'] = now.timestamp()
    chapters = story.setdefault('chapters', [])
    entry = next((c for c in chapters if c.get('id') == chapter_id), None)
    if entry:
        entry['name'] = chapter_name
        entry['date'] = date
    else:
        chapters.append({'id': chapter_id, 'name': chapter_name, 'date': date})
    return story


def next_story_id(catalog):
    ids = [int(item['slug']) for item in catalog if str(item.get('slug', '')).isdigit()]
    return f'{max(ids, default=0) + 1:04d}'


def next_chapter_id(catalog, story_slug):
    story = next((item for item in catalog if item.get('slug') == story_slug), None)
    ids = [int(c['id']) for c in (story or {}).get('chapters', []) if str(c.get('id', '')).isdigit()]
    return f'{max(ids, default=0) + 1:06d}'


def split_alternatives(pattern_regex):
    """Split a regex at its top-level ``|`` (not inside groups or [...])."""
    parts, depth, in_class, start, i = [], 0, False, 0, 0
    while i < len(pattern_regex):
        char = pattern_regex[i]
        if char == '\\':
            i += 2
            continue
        if in_class:
            in_class = char != ']'
        elif char == '[':
            in_class = True
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        elif char == '|' and depth == 0:
            parts.append(pattern_regex[start:i])
            start = i + 1
        i += 1
    parts.append(pattern_regex[start:])
    return [part for part in parts if part.strip()]


def combine_patterns(*regexes):
    """Join several header patterns into one: a paragraph matching any is a header."""
    parts = []
    for regex in regexes:
        for part in split_alternatives(regex or ''):
            if part not in parts:
                parts.append(part)
    return '|'.join(parts)


def split_into_chapters(items, pattern_regex, text_of=lambda item: item):
    """Group items (paragraph strings or (cn, vi) pairs) by header matches.

    Returns [{'title': header text or '', 'header': header item or None,
    'items': [...]}]; items before the first header go to a title-less group.
    """
    compiled = re.compile(pattern_regex, re.IGNORECASE | re.MULTILINE)
    chapters = []
    current = None
    for item in items:
        text = text_of(item).strip()
        if compiled.match(text):
            if current is not None:
                chapters.append(current)
            current = {'title': text, 'header': item, 'items': []}
        else:
            if current is None:
                current = {'title': '', 'header': None, 'items': []}
            current['items'].append(item)
    if current is not None:
        chapters.append(current)
    return chapters


# ─────────────────────────── bulk replace ───────────────────────────

def compile_search(query, regex=False, match_case=False):
    if not query:
        raise ValueError('Chưa nhập nội dung cần tìm.')
    return re.compile(query if regex else re.escape(query), 0 if match_case else re.IGNORECASE)


def _replacement(pattern, replacement, regex):
    if regex:
        return lambda match: match.expand(replacement)
    return lambda match: replacement


def replace_in_story(library_dir, catalog, story_slug, pattern, replacement,
                     regex=False, apply=False, backup_root=None):
    """Count (apply=False) or perform replacements in every chapter of a story.

    Touches the Vietnamese text and chapter titles only. Returns
    {'chapters': [(chapter_id, count)], 'total': n, 'backup': path|None}.
    When applying, each changed data.json is copied to backup_root first and
    the catalog chapter names are updated in `catalog` (caller writes it).
    """
    story = next((item for item in catalog if item.get('slug') == story_slug), None)
    if story is None:
        raise ValueError('Không tìm thấy truyện trong danh mục.')
    repl = _replacement(pattern, replacement, regex)
    results, total, backup_dir = [], 0, None
    for chapter in story.get('chapters', []):
        chapter_id = chapter.get('id', '')
        path = os.path.join(library_dir, story_slug, chapter_id, 'data.json')
        if not os.path.isfile(path):
            continue
        with open(path, 'r', encoding='utf-8') as stream:
            data = json.load(stream)
        count = 0
        new_content = []
        for item in data.get('content', []):
            vi = unb64(item.get('vi', ''))
            if vi is None:
                new_content.append(item)
                continue
            new_vi, n = pattern.subn(repl, vi)
            count += n
            new_content.append(dict(item, vi=b64(unicodedata.normalize('NFC', new_vi))) if n else item)
        title = data.get('chapter_title', '')
        new_title, n_title = pattern.subn(repl, title)
        count += n_title
        if count:
            results.append((chapter_id, count))
            total += count
            if apply:
                if backup_root:
                    if backup_dir is None:
                        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
                        backup_dir = os.path.join(backup_root, f'{story_slug}-{stamp}')
                    target = os.path.join(backup_dir, chapter_id)
                    os.makedirs(target, exist_ok=True)
                    shutil.copy2(path, os.path.join(target, 'data.json'))
                data['content'] = new_content
                if n_title:
                    data['chapter_title'] = new_title
                    chapter['name'] = new_title
                write_json_atomic(path, data)
    return {'chapters': results, 'total': total, 'backup': backup_dir}
