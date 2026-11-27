"""Phần xử lý của trình biên tập thư viện (không dính giao diện).
Giao diện Qt ở editor.py. Không import Qt ở đây."""
import base64
import datetime
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata

import library_store as store
from library_store import read_catalog, write_catalog
# Cấu hình và slug: một bản duy nhất ở translator_core (review Lần 8, B11/B12).
from translator_core import CONFIG_PATH, load_config, save_config, slugify_vn  # noqa: F401

# Khi đóng gói bằng PyInstaller, thư viện nằm cạnh file exe chứ không phải thư mục tạm.
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    if os.path.basename(BASE_DIR).lower() == 'dist':
        BASE_DIR = os.path.dirname(BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY_DIR = os.path.join(BASE_DIR, "library")
CATALOG_PATH = os.path.join(LIBRARY_DIR, "list.json")
BACKUP_DIR = os.path.join(BASE_DIR, ".backups")


# ───────────────────────── tìm truyện ─────────────────────────

def search_key(value):
    """Khoá so khớp không dấu, không phân biệt hoa thường (đ → d)."""
    value = unicodedata.normalize('NFD', value.casefold().replace('đ', 'd'))
    return ''.join(c for c in value if unicodedata.category(c) != 'Mn')


def story_options(catalog):
    """"<slug> | <tên>" của mọi truyện, mới cập nhật trước."""
    def updated(item):
        try:
            stamp = float(item.get('timestamp') or 0)
            if stamp > 0:
                return stamp
        except (ValueError, TypeError):
            pass
        try:
            return datetime.datetime.strptime(item.get('date', ''), '%d/%m/%Y').timestamp()
        except (ValueError, TypeError):
            return 0
    return [f'{item["slug"]} | {item.get("title", "")}'
            for item in sorted(catalog, key=updated, reverse=True) if item.get('slug')]


def filter_options(options, query):
    """Các mục chứa đủ mọi từ của query (không dấu)."""
    words = search_key(query).split()
    return [o for o in options if all(w in search_key(o) for w in words)]


def split_option(value):
    """"<slug> | <tên>" → (slug, tên); không có "|" thì (slugify(value), value)."""
    if "|" in value:
        slug, title = value.split("|", 1)
        return slug.strip(), title.strip()
    return slugify_vn(value), value.strip()


# ───────────────────────── đọc nội dung ─────────────────────────

def safe_decode_b64(value):
    try:
        raw = base64.b64decode(value)
        text = raw.decode("utf-8")
        return unicodedata.normalize('NFC', text)
    except Exception:
        return "[Loi giai ma]"


def chapter_counter_text(content, dirty=False):
    """"N chữ · N đoạn · N ký tự" của ô nội dung chương (đoạn cách nhau bằng dòng trống)."""
    text = content.strip()
    paragraphs = len([p for p in text.split("\n\n") if p.strip()]) if text else 0
    words = len(text.split())
    mark = "  ·  ● chưa lưu" if dirty else ""
    return f"{words:,} chữ  ·  {paragraphs} đoạn  ·  {len(text):,} ký tự{mark}".replace(",", ".")


# ───────────────────────── xoá ─────────────────────────

def delete_library_chapter(story_slug, chapter_id):
    """Remove chapter files and atomically update the catalog; rollback on failure."""
    for value in (story_slug, chapter_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("Mã truyện hoặc chương không hợp lệ.")
    library_root = os.path.realpath(LIBRARY_DIR)
    story_dir = os.path.join(library_root, story_slug)
    chapter_dir = os.path.join(story_dir, chapter_id)
    for path in (story_dir, chapter_dir):
        if os.path.normcase(os.path.realpath(path)) != os.path.normcase(path):
            raise ValueError("Không xóa chương qua đường dẫn liên kết.")
    catalog = read_catalog(CATALOG_PATH)
    story = next((item for item in catalog if item.get("slug") == story_slug), None)
    if story is None or not any(ch.get("id") == chapter_id for ch in story.get("chapters", [])):
        raise ValueError("Chương không còn trong danh mục. Hãy chọn lại chương.")
    if os.path.lexists(chapter_dir) and not os.path.isdir(chapter_dir):
        raise ValueError("Đường dẫn chương không phải thư mục.")

    staging = None
    try:
        if os.path.isdir(chapter_dir):
            staging = tempfile.mkdtemp(prefix=".delete-chapter-", dir=story_dir)
            os.replace(chapter_dir, os.path.join(staging, "chapter"))
        story["chapters"] = [ch for ch in story["chapters"] if ch.get("id") != chapter_id]
        write_catalog(CATALOG_PATH, catalog)
    except Exception:
        if staging:
            staged_chapter = os.path.join(staging, "chapter")
            if os.path.exists(staged_chapter):
                os.replace(staged_chapter, chapter_dir)
            os.rmdir(staging)
        raise

    cleanup_warning = None
    if staging:
        try:
            shutil.rmtree(staging)
        except OSError as error:
            cleanup_warning = f"Chương đã được gỡ khỏi thư viện, nhưng chưa dọn được dữ liệu tạm:\n{staging}\n{error}"
    return catalog, cleanup_warning


def delete_library_story(story_slug):
    """Remove one story directory and atomically update the catalog."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", story_slug):
        raise ValueError("Mã truyện không hợp lệ.")
    library_root = os.path.realpath(LIBRARY_DIR)
    story_dir = os.path.join(library_root, story_slug)
    if os.path.normcase(os.path.realpath(story_dir)) != os.path.normcase(story_dir):
        raise ValueError("Không xóa truyện qua đường dẫn liên kết.")
    catalog = read_catalog(CATALOG_PATH)
    if not any(item.get("slug") == story_slug for item in catalog):
        raise ValueError("Truyện không còn trong danh mục. Hãy chọn lại truyện.")
    if os.path.lexists(story_dir) and not os.path.isdir(story_dir):
        raise ValueError("Đường dẫn truyện không phải thư mục.")

    staging = None
    try:
        if os.path.isdir(story_dir):
            staging = tempfile.mkdtemp(prefix=".delete-story-", dir=library_root)
            os.replace(story_dir, os.path.join(staging, "story"))
        catalog = [item for item in catalog if item.get("slug") != story_slug]
        write_catalog(CATALOG_PATH, catalog)
    except Exception:
        if staging:
            staged_story = os.path.join(staging, "story")
            if os.path.exists(staged_story):
                os.replace(staged_story, story_dir)
            os.rmdir(staging)
        raise

    cleanup_warning = None
    if staging:
        try:
            shutil.rmtree(staging)
        except OSError as error:
            cleanup_warning = f"Truyện đã được gỡ khỏi thư viện, nhưng chưa dọn được dữ liệu tạm:\n{staging}\n{error}"
    return catalog, cleanup_warning


# ───────────────────────── đọc / tạo ─────────────────────────

def ensure_catalog():
    """Tạo library/ và chép list.json cũ từ stories/ nếu library chưa có danh mục."""
    os.makedirs(LIBRARY_DIR, exist_ok=True)
    if not os.path.exists(CATALOG_PATH):
        old_catalog = os.path.join(BASE_DIR, "stories", "list.json")
        if os.path.exists(old_catalog):
            try:
                shutil.copy2(old_catalog, CATALOG_PATH)
            except Exception:
                pass


def read_library_chapter(story_slug, chapter_id):
    """(tên chương, [đoạn tiếng Việt]) của library/<truyện>/<chương>/data.json. Ném lỗi nếu thiếu/hỏng."""
    data_path = os.path.join(LIBRARY_DIR, story_slug, chapter_id, "data.json")
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"Không tìm thấy file:\n{data_path}")
    with open(data_path, "r", encoding="utf-8") as f:
        chapter_json = json.load(f)
    paragraphs = [safe_decode_b64(item["vi"]) for item in chapter_json.get("content", []) if item.get("vi")]
    return chapter_json.get("chapter_title", ""), paragraphs


def read_source_json(file_path):
    """Đọc data.json làm nguồn. Trả dict: json, title, chapter_title, count, text (các đoạn VI cách
    nhau dòng trống), story_slug/chapter_slug đoán từ đường dẫn .../<truyện>/<chương>/data.json."""
    with open(file_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    items = loaded.get("content", [])
    vi_texts = [safe_decode_b64(item["vi"]) for item in items if isinstance(item, dict) and item.get("vi")] \
        if isinstance(items, list) else []
    parts = os.path.normpath(file_path).split(os.sep)
    story_slug = chapter_slug = ""
    if len(parts) >= 3 and parts[-1].lower() == "data.json":
        chapter_slug, story_slug = parts[-2], parts[-3]
    return {"json": loaded, "title": loaded.get("title", "Không có"), "chapter_title": loaded.get("chapter_title", ""),
            "count": len(items) if isinstance(items, list) else 0, "text": "\n\n".join(vi_texts),
            "story_slug": story_slug, "chapter_slug": chapter_slug}


def add_story(catalog, title):
    """Thêm truyện mới (mã tự cấp) vào catalog và ghi list.json. Trả slug."""
    slug = store.next_story_id(catalog)
    if any(item.get('slug') == slug for item in catalog):
        raise ValueError(f"ID/Slug tự động '{slug}' đã tồn tại!")
    store.ensure_story_dir(LIBRARY_DIR, slug)
    now = datetime.datetime.now()
    catalog.append({"title": title, "slug": slug, "date": now.strftime("%d/%m/%Y"),
                    "timestamp": now.timestamp(), "chapters": []})
    write_catalog(CATALOG_PATH, catalog)
    return slug


def chapter_exists(catalog, story_slug, chap_slug):
    story = next((item for item in catalog if item.get("slug") == story_slug), None)
    return bool(story) and any(c.get("id") == chap_slug for c in story.get("chapters", []))


def chapter_options(catalog, story_slug):
    """"<mã> | <tên>" các chương đã lưu của truyện."""
    story = next((item for item in catalog if item.get("slug") == story_slug), None)
    return [f'{c.get("id", "")} | {c.get("name", "")}' for c in (story or {}).get("chapters", [])]


# ───────────────────────── phân chương ─────────────────────────

def detect_chapters(text, pattern_regex):
    """Tách các đoạn (cách nhau bằng dòng trống) thành chương theo regex tiêu đề.
    Trả [{"title", "paragraphs"}]; đoạn trước tiêu đề đầu tiên thuộc nhóm title="". Regex lỗi → []."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    try:
        groups = store.split_into_chapters(paragraphs, pattern_regex)
    except re.error:
        return []
    return [{"title": group["title"], "paragraphs": group["items"]} for group in groups]


def get_split_patterns():
    """[(tên, regex)]: mẫu mặc định + mẫu đã lưu trong cấu hình."""
    result = list(store.DEFAULT_SPLIT_PATTERNS)
    for item in load_config().get("split_patterns", []):
        if isinstance(item, (list, tuple)) and len(item) == 2:
            name, rx = item
            if not any(rx == r for _, r in result):
                # Tên trùng thì combobox chỉ chọn được mục đầu: đánh dấu mục đã lưu.
                if any(name == n for n, _ in result):
                    name = f"{name} (đã lưu)"
                result.append((name, rx))
    return result


def save_split_pattern(name, regex):
    saved = [p for p in load_config().get("split_patterns", []) if p[1] != regex]
    saved.append([name, regex])
    save_config({"split_patterns": saved})


def pattern_counts(chapters, regex):
    """Mỗi mẫu thành phần của regex gộp bắt được bao nhiêu chương; None nếu regex chỉ có một mẫu."""
    parts = store.split_alternatives(regex)
    if len(parts) <= 1:
        return None
    compiled = []
    for part in parts:
        try:
            compiled.append((part, re.compile(part, re.IGNORECASE)))
        except re.error:
            compiled.append((part, None))
    counts = dict.fromkeys(parts, 0)
    for ch in chapters:
        title = ch["title"]
        hit = next((part for part, c in compiled if title and c and c.match(title)), None)
        if hit:
            counts[hit] += 1
    return counts
